from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections, DatabaseError, transaction
from django.test import TransactionTestCase

from .tests import LedgerFixture
from .models import JournalEntry, EntrySequence, FiscalYear, AccountingPeriod, AccountingProfile
from . import services


@skipUnless(connection.vendor == "postgresql", "PostgreSQL locks and ledger constraints required")
class LedgerPostgreSQLTests(LedgerFixture, TransactionTestCase):
    def parallel(self, jobs):
        barrier = Barrier(len(jobs))
        actor_id = self.actor.pk

        def worker(job):
            connections.close_all()
            try:
                actor = get_user_model().objects.get(pk=actor_id)
                barrier.wait(timeout=15)
                try:
                    return job(actor)
                except ValidationError:
                    return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
            return list(executor.map(worker, jobs))

    def test_simultaneous_posting_same_entry_is_idempotent(self):
        entry = self.draft()
        job = lambda actor: services.post_entry(actor=actor, pk=entry.pk, revision=entry.revision).number
        results = self.parallel([job, job])
        self.assertEqual(results, ["OD-2026-000001", "OD-2026-000001"])
        self.assertEqual(EntrySequence.objects.get().last_number, 1)
        self.assertEqual(entry.events.filter(action="Écriture validée").count(), 1)

    def test_simultaneous_first_counter_allocation(self):
        first, second = self.draft(), self.draft()
        results = self.parallel([
            lambda actor: services.post_entry(actor=actor, pk=first.pk, revision=first.revision).number,
            lambda actor: services.post_entry(actor=actor, pk=second.pk, revision=second.revision).number])
        self.assertEqual(set(results), {"OD-2026-000001", "OD-2026-000002"})
        self.assertEqual(EntrySequence.objects.get().last_number, 2)

    def test_simultaneous_draft_import_key_creates_one_entry(self):
        token = uuid4()
        job = lambda actor: services.save_draft(actor=actor, values=self.values(), lines=self.lines(), token=token).pk
        results = self.parallel([job, job])
        self.assertEqual(results[0], results[1])
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_closing_period_serializes_with_posting(self):
        entry = self.draft()
        results = self.parallel([
            lambda actor: services.post_entry(actor=actor, pk=entry.pk, revision=entry.revision).status,
            lambda actor: services.set_period_open(actor=actor, pk=self.period.pk, is_open=False, reason="QA race").is_open])
        self.assertIn(results[0], ("POSTED", "rejected"))
        self.assertFalse(AccountingPeriod.objects.get(pk=self.period.pk).is_open)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "POSTED" if results[0] == "POSTED" else "DRAFT")

    def test_simultaneous_reversals_create_one(self):
        entry = self.posted()
        token = uuid4()
        job = lambda actor: services.reverse_entry(actor=actor, pk=entry.pk, period=self.period,
            accounting_date=date(2026, 11, 17), reason="QA correction", token=token).pk
        results = self.parallel([job, job])
        self.assertEqual(results[0], results[1])
        self.assertEqual(JournalEntry.objects.filter(reversal_of=entry).count(), 1)

    def test_raw_unbalanced_posting_rejected_even_with_fake_totals(self):
        entry = services.save_draft(actor=self.actor, values=self.values(), lines=self.lines("99.00"), token=uuid4())
        with self.assertRaisesMessage(DatabaseError, "Unbalanced accounting entry"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE accounting_journalentry SET status='POSTED', number='FAKE',
                    posted_at=CURRENT_TIMESTAMP, debit_total=100, credit_total=100,
                    posted_by_id=%s, posted_by_name='SQL' WHERE id=%s""", [self.actor.pk, entry.pk])

    def test_raw_overlapping_year_and_period_rejected(self):
        for sql, values in (
            ("INSERT INTO accounting_fiscalyear (code,start_date,end_date,is_open) VALUES (%s,%s,%s,TRUE)",
                ["BAD", date(2026, 12, 31), date(2027, 12, 31)]),
            ("INSERT INTO accounting_accountingperiod (fiscal_year_id,label,start_date,end_date,is_open) VALUES (%s,%s,%s,%s,TRUE)",
                [self.year.pk, "BAD", date(2026, 2, 1), date(2026, 2, 28)])):
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, values)

    def test_raw_counter_and_audit_mutations_rejected(self):
        entry = self.posted()
        for sql in ("UPDATE accounting_entrysequence SET last_number=0",
                    "DELETE FROM accounting_entrysequence", "DELETE FROM accounting_accountingevent"):
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql)

    def test_raw_account_change_revokes_plan_approval(self):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE accounting_account SET label='QA revision' WHERE id=%s", [self.debit.pk])
        self.assertIsNone(AccountingProfile.objects.get(pk=1).approved_at)
