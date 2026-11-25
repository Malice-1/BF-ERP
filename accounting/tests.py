from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, transaction, DatabaseError
from django.test import TestCase, Client
from django.urls import reverse

from budgeting.models import BudgetProduct
from sales.models import IssuerConfiguration, Customer, SalesInvoice
from suppliers.models import Supplier
from receiving.models import StockMovement
from purchasing.models import BudgetEntry
from .models import (AccountingProfile, Account, FiscalYear, AccountingPeriod, Journal,
    JournalEntry, JournalEntryLine, EntrySequence, AccountingEvent, BudgetProductAccount, SalesBudgetProductAccount)
from . import services


class LedgerFixture:
    def setUp(self):
        super().setUp()
        self.actor = get_user_model().objects.create_superuser("ledger-admin", "ledger@example.test", "password")
        self.issuer = IssuerConfiguration.objects.create(name="Entité QA publique", legal_id="QA-001",
            street="Rue QA 1", zip_code="1000", city="Bruxelles", country="BE", iban="BE68539007547034")
        self.customer = Customer.objects.create(code="QA-C", name="Client QA")
        self.supplier = Supplier.objects.create(code="QA-F", name="Fournisseur QA")
        self.debit = services.save_account(actor=self.actor, values={"code": "600001", "label": "Charge QA",
            "postable": True, "is_active": True, "party_requirement": "NONE", "source_reference": "Plan QA non réglementaire"})
        self.credit = services.save_account(actor=self.actor, values={"code": "440001", "label": "Fournisseur QA",
            "postable": True, "is_active": True, "party_requirement": "SUPPLIER", "source_reference": "Plan QA non réglementaire"})
        self.journal = services.save_journal(actor=self.actor,
            values={"code": "OD", "label": "Opérations diverses", "kind": "GENERAL", "is_active": True})
        self.year = services.create_year(actor=self.actor, code="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.period = services.create_period(actor=self.actor, fiscal_year=self.year, label="Année QA",
            start_date=self.year.start_date, end_date=self.year.end_date)
        current = AccountingProfile.objects.get(pk=1)
        self.profile = services.configure_profile(actor=self.actor, issuer=self.issuer, framework="PUBLIC",
            chart_reference="Plan QA — aucune valeur réglementaire", revision=current.revision)
        self.client.force_login(self.actor)

    def values(self, **changes):
        return {"journal": self.journal, "period": self.period, "accounting_date": date(2026, 11, 16),
            "document_date": date(2026, 11, 15), "description": "Opération de test", "document_reference": "PIECE-QA-1", **changes}

    def lines(self, credit="100.00"):
        return [{"account": self.debit, "debit": Decimal("100.00"), "credit": Decimal(0)},
            {"account": self.credit, "debit": Decimal(0), "credit": Decimal(credit), "supplier": self.supplier}]

    def draft(self, **changes):
        return services.save_draft(actor=self.actor, values=self.values(**changes), lines=self.lines(), token=uuid4())

    def posted(self):
        entry = self.draft()
        return services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision)


class LedgerTests(LedgerFixture, TestCase):
    def test_account_groups_share_navigation_and_preserve_mapping_permissions(self):
        url = reverse("accounting:account_groups")
        purchases = reverse("accounting:account_groups", query={"section": "achats"})
        sales = reverse("accounting:account_groups", query={"section": "ventes"})
        product = BudgetProduct.objects.create(code="BI-QA", label="Produit QA")
        self.assertContains(self.client.get(url), 'aria-label="Groupes de comptes par opération"')
        self.assertRedirects(self.client.post(purchases, {
            "action": "mapping", "product": product.pk, "account": self.debit.pk,
        }), purchases)
        self.assertRedirects(self.client.post(sales, {
            "action": "mapping", "product": product.pk, "account": self.debit.pk,
        }), sales)
        self.assertEqual(BudgetProductAccount.objects.get(product=product).account, self.debit)
        self.assertEqual(SalesBudgetProductAccount.objects.get(product=product).account, self.debit)

        user = get_user_model().objects.create_user("sales-config")
        user.user_permissions.add(Permission.objects.get(codename="change_salespostingconfiguration"))
        self.client.force_login(user)
        self.assertContains(self.client.get(url), "Imputations des ventes")
        self.assertEqual(self.client.get(purchases).status_code, 403)
        self.assertEqual(self.client.post(purchases, {"action": "mapping"}).status_code, 403)

    def test_balanced_post_number_snapshots_and_idempotence(self):
        entry = self.draft()
        self.assertIsNone(entry.number)
        self.assertFalse(EntrySequence.objects.exists())
        posted = services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision)
        self.assertEqual(posted.number, "OD-2026-000001")
        self.assertEqual(posted.status, "POSTED")
        self.assertEqual(posted.debit_total, posted.credit_total)
        self.assertEqual(posted.issuer_snapshot["framework"], "PUBLIC")
        self.assertEqual(posted.lines.last().party_snapshot["name"], "Fournisseur QA")
        self.assertEqual(services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision).pk, entry.pk)
        self.assertEqual(EntrySequence.objects.get().last_number, 1)

    def test_unbalanced_draft_allowed_but_post_refused_atomically(self):
        entry = services.save_draft(actor=self.actor, values=self.values(), lines=self.lines(credit="99.99"), token=uuid4())
        self.assertEqual(entry.status, "DRAFT")
        with self.assertRaises(ValidationError):
            services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision)
        self.assertFalse(EntrySequence.objects.exists())
        self.assertEqual(JournalEntry.objects.get(pk=entry.pk).status, "DRAFT")

    def test_draft_replay_and_revision(self):
        token = uuid4()
        args = {"actor": self.actor, "values": self.values(), "lines": self.lines(), "token": token}
        entry = services.save_draft(**args)
        self.assertEqual(services.save_draft(**args).pk, entry.pk)
        with self.assertRaises(ValidationError):
            services.save_draft(**{**args, "values": self.values(description="Autre")})
        edited = services.save_draft(**{**args, "pk": entry.pk, "revision": entry.revision,
            "values": self.values(description="Corrigée")})
        self.assertEqual(edited.lines.count(), 2)
        with self.assertRaises(ValidationError):
            services.save_draft(**{**args, "pk": entry.pk, "revision": entry.revision})

    def test_account_change_does_not_prevent_posting(self):
        entry = self.draft()
        services.save_account(actor=self.actor, pk=self.debit.pk, values={"label": "Libellé révisé"})
        posted = services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision)
        self.assertEqual(posted.lines.first().account_snapshot["label"], "Libellé révisé")

    def test_entry_requires_reference_and_valid_period(self):
        entry = self.draft(document_reference="")
        with self.assertRaises(ValidationError):
            services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision)
        with self.assertRaises(ValidationError):
            self.draft(accounting_date=date(2027, 1, 1))

    def test_invalid_lines_nonfinite_negative_zero_both_sides_and_precision(self):
        for debit, credit in (("-1", "0"), ("0", "0"), ("1", "1"), ("NaN", "0"), ("Infinity", "0"), ("1.001", "0")):
            rows = self.lines()
            rows[0].update(debit=debit, credit=credit)
            with self.subTest(debit=debit, credit=credit), self.assertRaises(ValidationError):
                services.save_draft(actor=self.actor, values=self.values(), lines=rows, token=uuid4())
        self.assertFalse(JournalEntry.objects.exists())

    def test_required_supplier_and_grouping_account(self):
        rows = self.lines()
        rows[1].pop("supplier")
        with self.assertRaises(ValidationError):
            services.save_draft(actor=self.actor, values=self.values(), lines=rows, token=uuid4())
        services.save_account(actor=self.actor, pk=self.debit.pk, values={"postable": False})
        with self.assertRaises(ValidationError):
            self.draft()

    def test_period_close_reopen_and_posting(self):
        entry = self.draft()
        services.set_period_open(actor=self.actor, pk=self.period.pk, is_open=False, reason="Contrôle QA")
        with self.assertRaises(ValidationError):
            services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision)
        with self.assertRaises(ValidationError):
            services.set_period_open(actor=self.actor, pk=self.period.pk, is_open=True, reason="")
        services.set_period_open(actor=self.actor, pk=self.period.pk, is_open=True, reason="Correction justifiée")
        self.assertEqual(services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision).status, "POSTED")

    def test_year_and_period_overlaps_rejected(self):
        with self.assertRaises(ValidationError):
            services.create_year(actor=self.actor, code="OTHER", start_date=date(2026, 12, 31), end_date=date(2027, 12, 31))
        with self.assertRaises(ValidationError):
            services.create_period(actor=self.actor, fiscal_year=self.year, label="Overlap", start_date=date(2026, 2, 1), end_date=date(2026, 2, 28))
        with self.assertRaises(ValidationError):
            services.create_period(actor=self.actor, fiscal_year=self.year, label="Outside", start_date=date(2027, 1, 1), end_date=date(2027, 2, 1))

    def test_posted_entry_and_lines_immutable_including_raw_sql(self):
        entry = self.posted()
        entry.description = "Altération"
        with self.assertRaises(ValidationError):
            entry.save()
        with self.assertRaises(ValidationError):
            entry.lines.first().save()
        with self.assertRaises(ValidationError):
            JournalEntry.objects.filter(pk=entry.pk).update(description="Autre")
        for sql in ("UPDATE accounting_journalentry SET description='Altered' WHERE id=%s",
            "UPDATE accounting_journalentryline SET description='Altered' WHERE entry_id=%s",
            "DELETE FROM accounting_journalentryline WHERE entry_id=%s"):
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, [entry.pk])

    def test_reversal_preserves_original_and_snapshots_is_idempotent(self):
        entry = self.posted()
        args = dict(actor=self.actor, pk=entry.pk, period=self.period, accounting_date=date(2026, 11, 17), reason="Correction QA", token=uuid4())
        reversal = services.reverse_entry(**args)
        self.assertEqual(reversal.status, "POSTED")
        self.assertEqual(reversal.reversal_of_id, entry.pk)
        self.assertEqual(reversal.lines.first().credit, entry.lines.first().debit)
        self.assertEqual(reversal.lines.first().account_snapshot, entry.lines.first().account_snapshot)
        self.assertEqual(services.reverse_entry(**args).pk, reversal.pk)
        self.assertEqual(JournalEntry.objects.get(pk=entry.pk).status, "POSTED")
        with self.assertRaises(ValidationError):
            services.reverse_entry(**{**args, "token": uuid4()})
        with self.assertRaises(ValidationError):
            services.reverse_entry(**{**args, "pk": reversal.pk})

    def test_reversal_in_new_exercise_after_original_period_closed(self):
        entry = self.posted()
        services.set_period_open(actor=self.actor, pk=self.period.pk, is_open=False, reason="Période contrôlée")
        year = services.create_year(actor=self.actor, code="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31))
        period = services.create_period(actor=self.actor, fiscal_year=year, label="Janvier", start_date=date(2027, 1, 1), end_date=date(2027, 1, 31))
        result = services.reverse_entry(actor=self.actor, pk=entry.pk, period=period, accounting_date=date(2027, 1, 1), reason="Correction", token=uuid4())
        self.assertEqual(result.number, "OD-2027-000001")

    def test_chronological_numbering_rejects_silent_backdate(self):
        self.posted()
        entry = self.draft(accounting_date=date(2026, 11, 15))
        with self.assertRaises(ValidationError):
            services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision)
        self.assertEqual(EntrySequence.objects.get().last_number, 1)

    def test_frozen_labels_survive_reference_changes(self):
        entry = self.posted()
        services.save_account(actor=self.actor, pk=self.debit.pk, values={"label": "Nouveau libellé"})
        self.supplier.name = "Nouveau nom fournisseur"
        self.supplier.save()
        entry.refresh_from_db()
        self.assertEqual(entry.lines.first().account_snapshot["label"], "Charge QA")
        self.assertEqual(entry.lines.last().party_snapshot["name"], "Fournisseur QA")
        with self.assertRaises(ValidationError):
            services.save_account(actor=self.actor, pk=self.debit.pk, values={"code": "600002"})

    def test_post_using_existing_chart_without_an_import_or_reference(self):
        current_accounts = list(Account.objects.values_list("pk", "code"))
        profile = services.configure_profile(actor=self.actor, issuer=self.issuer, framework="PUBLIC",
            chart_reference="", revision=self.profile.revision)
        self.assertEqual(profile.chart_reference, "Plan de comptes actuel")
        self.assertEqual(profile.chart_manifest, [])
        self.assertCountEqual(Account.objects.values_list("pk", "code"), current_accounts)
        self.assertEqual(self.posted().issuer_snapshot["chart_reference"], "Plan de comptes actuel")
        former_url = reverse("accounting:accounts") + "importer/"
        self.assertEqual(self.client.get(former_url).status_code, 404)
        self.assertEqual(self.client.post(former_url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("accounting:home")), "approbation")
        self.assertEqual(self.client.post(reverse("accounting:profile") + "approuver/").status_code, 404)

    def test_permissions_services_http_and_csrf(self):
        user = get_user_model().objects.create_user("no-ledger", password="password")
        self.client.force_login(user)
        for route in ("home", "profile", "accounts", "journals", "years", "entries", "entry_new"):
            self.assertEqual(self.client.get(reverse("accounting:" + route)).status_code, 403)
        entry = self.draft()
        with self.assertRaises(PermissionDenied):
            services.post_entry(actor=user, pk=entry.pk, revision=entry.revision)
        self.assertEqual(self.client.post(reverse("accounting:post", args=[entry.pk]), {"revision": entry.revision}).status_code, 403)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.actor)
        self.assertEqual(browser.post(reverse("accounting:post", args=[entry.pk]), {"revision": entry.revision}).status_code, 403)
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse("accounting:post", args=[entry.pk])).status_code, 405)

    def test_screens_and_accounting_only_landing(self):
        entry = self.draft()
        for name, args in (("home", []), ("profile", []), ("accounts", []),
            ("account_new", []), ("account_edit", [self.debit.pk]), ("journals", []), ("journal_new", []),
            ("years", []), ("year_new", []), ("period_new", []), ("entries", []), ("entry_new", []),
            ("entry_detail", [entry.pk]), ("entry_edit", [entry.pk])):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse("accounting:" + name, args=args)).status_code, 200)
        user = get_user_model().objects.create_user("ledger-reader")
        user.user_permissions.add(Permission.objects.get(content_type__app_label="accounting", codename="view_journalentry"))
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("purchasing:list")), reverse("accounting:home"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("accounting:entries")), "Comptabilité")
        self.assertEqual(self.client.post(reverse("accounting:post", args=[entry.pk]), {"revision": entry.revision}).status_code, 403)

    def test_no_automatic_invoice_stock_or_budget_side_effect(self):
        counts = (SalesInvoice.objects.count(), StockMovement.objects.count(), BudgetEntry.objects.count())
        self.posted()
        self.assertEqual(counts, (SalesInvoice.objects.count(), StockMovement.objects.count(), BudgetEntry.objects.count()))

    def test_http_create_edit_and_post(self):
        token = uuid4()
        data = {"journal": self.journal.pk, "period": self.period.pk, "accounting_date": "2026-11-16",
            "document_date": "2026-11-15", "description": "Saisie HTTP", "document_reference": "HTTP-1",
            "token": str(token), "revision": "0", "lines-TOTAL_FORMS": "2", "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "2", "lines-MAX_NUM_FORMS": "200",
            "lines-0-account": self.debit.pk, "lines-0-description": "Débit", "lines-0-debit": "100.00", "lines-0-credit": "0",
            "lines-1-account": self.credit.pk, "lines-1-description": "Crédit", "lines-1-debit": "0", "lines-1-credit": "100.00",
            "lines-1-supplier": self.supplier.pk}
        response = self.client.post(reverse("accounting:entry_new"), data)
        self.assertEqual(response.status_code, 302, response.content.decode())
        entry = JournalEntry.objects.get(idempotency_key=token)
        data.update({"revision": str(entry.revision), "description": "Saisie corrigée", "lines-INITIAL_FORMS": "2"})
        for i, row in enumerate(entry.lines.all()):
            data[f"lines-{i}-id"] = str(row.pk)
        response = self.client.post(reverse("accounting:entry_edit", args=[entry.pk]), data)
        self.assertEqual(response.status_code, 302, response.content.decode())
        entry.refresh_from_db()
        self.assertEqual(entry.description, "Saisie corrigée")
        self.client.post(reverse("accounting:post", args=[entry.pk]), {"revision": entry.revision})
        entry.refresh_from_db()
        self.assertEqual(entry.status, "POSTED")
        self.assertContains(self.client.get(reverse("accounting:entry_detail", args=[entry.pk])), entry.number)

    def test_new_entity_name_is_used_and_legal_identity_is_preserved(self):
        entry = self.draft()
        self.issuer.name = "Entité QA renommée"
        self.issuer.save()
        posted = services.post_entry(actor=self.actor, pk=entry.pk, revision=entry.revision)
        self.assertEqual(posted.issuer_snapshot["name"], self.issuer.name)
        self.issuer.legal_id = "AUTRE-ENTITE"
        self.issuer.save()
        next_entry = self.draft()
        with self.assertRaises(ValidationError):
            services.post_entry(actor=self.actor, pk=next_entry.pk, revision=next_entry.revision)

    def test_deleted_actor_name_remains_in_history(self):
        entry = self.posted()
        self.actor.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.posted_by_id)
        self.assertEqual(entry.posted_by_name, "ledger-admin")
        self.assertEqual(entry.events.filter(action="Écriture validée").get().actor_name, "ledger-admin")

    def test_maintenance_cannot_delete_or_detach_ledger_data(self):
        from accounts.admin_deletion import delete_as_superuser
        entry = self.posted()
        for queryset in (JournalEntry.objects.filter(pk=entry.pk), Supplier.objects.filter(pk=self.supplier.pk)):
            with self.subTest(model=queryset.model), self.assertRaises(PermissionDenied):
                delete_as_superuser(queryset, self.actor)
        self.assertEqual(entry.lines.last().supplier_id, self.supplier.pk)

    def test_inactive_historical_account_can_still_be_reversed(self):
        entry = self.posted()
        with self.assertRaises(ValidationError):
            services.save_account(actor=self.actor, pk=self.credit.pk, values={"party_requirement": "CUSTOMER"})
        services.save_account(actor=self.actor, values={"code": "550001", "label": "Autre compte QA",
            "postable": True, "is_active": True, "party_requirement": "NONE"})
        services.save_account(actor=self.actor, pk=self.debit.pk, values={"is_active": False})
        result = services.reverse_entry(actor=self.actor, pk=entry.pk, period=self.period,
            accounting_date=date(2026, 11, 17), reason="Correction compte inactif", token=uuid4())
        self.assertEqual(result.status, "POSTED")
