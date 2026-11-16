from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TransactionTestCase

from .test_supplier_xml import SupplierXmlFixture
from .models import SupplierInvoice
from . import supplier_xml


@skipUnless(connection.vendor == "postgresql", "PostgreSQL import/review locking required")
class SupplierXmlPostgreSQLTests(SupplierXmlFixture, TransactionTestCase):
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

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            return list(pool.map(worker, jobs))

    def test_concurrent_same_file_one_invoice_one_archive(self):
        job = lambda actor: supplier_xml.import_invoice(actor=actor, data=self.data, filename="invoice.xml")[0].pk
        results = self.parallel([job, job])
        self.assertEqual(results[0], results[1])
        self.assertEqual(SupplierInvoice.objects.count(), 1)
        from pathlib import Path
        self.assertEqual(len(list(Path(self.directory.name).rglob("*.xml"))), 1)

    def test_concurrent_different_bytes_same_business_identity_no_duplicate(self):
        changed = self.data.replace(b">\n", b">\n\n")
        results = self.parallel([
            lambda actor: supplier_xml.import_invoice(actor=actor, data=self.data, filename="first.xml")[0].pk,
            lambda actor: supplier_xml.import_invoice(actor=actor, data=changed, filename="second.xml")[0].pk])
        self.assertEqual(results.count("rejected"), 1)
        self.assertEqual(SupplierInvoice.objects.count(), 1)

    def test_concurrent_reviews_only_one_approval(self):
        invoice = self.imported()
        job = lambda actor: supplier_xml.review_invoice(actor=actor, pk=invoice.pk, revision=0,
            supplier=self.supplier, note="Contrôle QA", action="approve").status
        self.assertEqual(sorted(self.parallel([job, job])), ["REVIEWED", "rejected"])
        invoice.refresh_from_db()
        self.assertEqual(invoice.revision, 1)
