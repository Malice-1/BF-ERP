import hashlib
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction, DatabaseError
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from sales.documents import xml_invoice
from .tests import LedgerFixture
from .models import SupplierInvoice, SupplierInvoiceValidation, JournalEntry, AccountingEvent
from . import supplier_xml


class SupplierXmlFixture(LedgerFixture):
    def setUp(self):
        super().setUp()
        parent = Path(settings.BASE_DIR) / ".qa"
        parent.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="supplier-xml-", dir=parent)
        self.addCleanup(self.directory.cleanup)
        self.config = override_settings(SUPPLIER_DOCUMENT_ROOT=self.directory.name)
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.issuer.vat_number = "BE0123456749"
        self.issuer.peppol_endpoint_id = "0123456749"
        self.issuer.peppol_endpoint_scheme = "0208"
        self.issuer.save()
        self.supplier.vat_number = "BE0123456749"
        self.supplier.save()
        seller = {"name": "Fournisseur XML QA", "street": "Rue QA 2", "zip_code": "1000", "city": "Bruxelles",
            "country": "BE", "vat_number": "BE0123456749", "email": "vendor@example.test", "legal_id": "0123456749",
            "peppol_endpoint_id": "0123456749", "peppol_endpoint_scheme": "0208", "iban": "BE68539007547034"}
        buyer = {**seller, "name": self.issuer.name, "payment_terms": "À 30 jours", "reference": "ACHAT-QA"}
        self.xml_model = SimpleNamespace(number="SUP-2026-001", issue_date=date(2026, 11, 16), due_date=date(2026, 12, 16),
            currency="EUR", subtotal=Decimal("100.00"), tax_total=Decimal("21.00"), total=Decimal("121.00"),
            tax_breakdown=[{"code": "S", "rate": "21", "base": "100.00", "tax": "21.00", "reason": ""}],
            issuer_snapshot=seller, customer_snapshot=buyer,
            order_snapshot={"number": "CV-QA", "customer_reference": "PO-QA"})
        self.xml_line = SimpleNamespace(position=1, description="Fourniture QA", quantity=Decimal(1), unit="C62",
            unit_price=Decimal("100"), discount=Decimal(0), subtotal=Decimal("100.00"), tax_code="S", tax_rate=Decimal(21),
            service_start=None, service_end=None)
        self.data = xml_invoice(self.xml_model, [self.xml_line])

    def imported(self, data=None):
        return supplier_xml.import_invoice(actor=self.actor, data=data or self.data, filename="invoice.xml")[0]

    def approved(self, invoice):
        return supplier_xml.review_invoice(actor=self.actor, pk=invoice.pk, revision=invoice.revision,
            supplier=self.supplier, note="Vérification QA de la pièce et de la prestation", action="approve")


class SupplierXmlTests(SupplierXmlFixture, TestCase):
    def test_import_extract_validate_archive_and_download(self):
        before = JournalEntry.objects.count()
        with patch("urllib.request.urlopen", side_effect=AssertionError("No network access")):
            invoice = self.imported()
        self.assertEqual(invoice.invoice_number, "SUP-2026-001")
        self.assertEqual(invoice.subtotal, Decimal("100.00"))
        self.assertEqual(invoice.tax_total, Decimal("21.00"))
        self.assertEqual(invoice.total, Decimal("121.00"))
        self.assertEqual(invoice.payable, Decimal("121.00"))
        self.assertEqual(invoice.extracted_data["lines"][0]["description"], "Fourniture QA")
        self.assertEqual(invoice.extracted_data["payment_means"][0]["account_id"], "BE68539007547034")
        self.assertEqual(invoice.validations.get().status, "VALID", invoice.validations.get().details)
        self.assertEqual(supplier_xml.read_original(invoice), self.data)
        self.assertEqual(invoice.checksum, hashlib.sha256(self.data).hexdigest())
        self.assertEqual(JournalEntry.objects.count(), before)
        response = self.client.get(reverse("accounting:supplier_invoice_download", args=[invoice.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.data)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_same_bytes_idempotent_and_changed_same_invoice_rejected(self):
        invoice = self.imported()
        again, created = supplier_xml.import_invoice(actor=self.actor, data=self.data, filename="renamed.xml")
        self.assertFalse(created)
        self.assertEqual(again.pk, invoice.pk)
        reformatted = self.data.replace(b">\n", b">\n\n")
        with self.assertRaises(ValidationError):
            self.imported(reformatted)
        self.assertEqual(SupplierInvoice.objects.count(), 1)

    def test_supplier_matching_is_suggestion_and_review_is_explicit(self):
        invoice = self.imported()
        self.assertIsNone(invoice.supplier_id)
        self.assertEqual([item.pk for item in supplier_xml.supplier_candidates(invoice)], [self.supplier.pk])
        invoice = self.approved(invoice)
        self.assertEqual(invoice.status, "REVIEWED")
        self.assertEqual(invoice.supplier_id, self.supplier.pk)
        self.assertEqual(invoice.review_snapshot["supplier_name"], self.supplier.name)
        self.assertEqual(invoice.review_snapshot["checksum"], invoice.checksum)
        with self.assertRaises(ValidationError):
            self.approved(invoice)

    def test_wrong_supplier_and_wrong_receiver_block_approval(self):
        invoice = self.imported()
        self.supplier.vat_number = "BE0000000097"
        self.supplier.save()
        with self.assertRaises(ValidationError):
            self.approved(invoice)
        self.supplier.vat_number = "BE0123456749"
        self.supplier.save()
        self.issuer.vat_number = "BE0000000097"
        self.issuer.save()
        with self.assertRaises(ValidationError):
            self.approved(invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "RECEIVED")

    def test_unknown_receiver_cannot_be_approved_by_name_only(self):
        invoice = self.imported()
        self.issuer.vat_number = ""
        self.issuer.peppol_endpoint_id = ""
        self.issuer.save()
        # The generated customer has no legal ID; a matching name isn't proof.
        with self.assertRaises(ValidationError):
            self.approved(invoice)

    def test_endpoint_identifiers_are_not_compared_with_punctuation_removed(self):
        invoice = self.imported()
        self.issuer.peppol_endpoint_id = "0123-456749"
        self.issuer.save()
        with self.assertRaises(ValidationError):
            self.approved(invoice)

    def test_invalid_totals_are_archived_but_cannot_be_approved(self):
        bad = self.data.replace(b'<cbc:PayableAmount currencyID="EUR">121.00</cbc:PayableAmount>',
            b'<cbc:PayableAmount currencyID="EUR">999.00</cbc:PayableAmount>')
        invoice = self.imported(bad)
        self.assertEqual(invoice.validations.get().status, "INVALID")
        self.assertEqual(supplier_xml.read_original(invoice), bad)
        with self.assertRaises(ValidationError):
            self.approved(invoice)

    def test_rules_unavailable_and_old_date_never_marked_valid(self):
        with override_settings(SALES_RULES_ROOT=Path(self.directory.name)):
            invoice = self.imported()
        self.assertEqual(invoice.validations.first().status, "UNAVAILABLE")
        with self.assertRaises(ValidationError):
            self.approved(invoice)
        result = supplier_xml.revalidate_invoice(actor=self.actor, pk=invoice.pk)
        self.assertEqual(result.status, "VALID", result.details)
        self.assertEqual(invoice.validations.count(), 2)
        self.approved(invoice)

    def test_uncovered_issue_date_preserved_with_validation_unavailable(self):
        data = self.data.replace(b"2026-11-16", b"2025-11-16")
        invoice = self.imported(data)
        self.assertEqual(invoice.issue_date, date(2025, 11, 16))
        self.assertEqual(invoice.validations.get().status, "UNAVAILABLE")
        with self.assertRaises(ValidationError):
            self.approved(invoice)

    def test_invalid_issue_date_archived_with_extraction_error(self):
        data = self.data.replace(b"2026-11-16", b"not-a-date")
        invoice = self.imported(data)
        self.assertIsNone(invoice.issue_date)
        self.assertEqual(invoice.validations.get().status, "INVALID")
        self.assertTrue(invoice.extracted_data["extraction_errors"])

    def test_duplicate_supplier_vat_does_not_automatically_choose(self):
        from suppliers.models import Supplier
        Supplier.objects.create(code="SECOND", name="Autre fiche QA", vat_number=self.supplier.vat_number)
        invoice = self.imported()
        self.assertEqual(len(supplier_xml.supplier_candidates(invoice)), 2)
        self.assertIsNone(invoice.supplier_id)

    def test_reviewer_name_survives_user_deletion(self):
        invoice = self.approved(self.imported())
        self.actor.delete()
        invoice.refresh_from_db()
        self.assertIsNone(invoice.reviewed_by_id)
        self.assertEqual(invoice.reviewed_by_name, "ledger-admin")

    def test_malformed_dtd_oversize_and_wrong_document_rejected(self):
        samples = [b"not XML", b"<Invoice/>", b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>',
            self.data.replace(b"<cbc:InvoiceTypeCode>380", b"<cbc:InvoiceTypeCode>381")]
        for data in samples:
            with self.subTest(data=data[:40]), self.assertRaises(ValidationError):
                self.imported(data)
        with override_settings(SUPPLIER_XML_MAX_BYTES=10), self.assertRaises(ValidationError):
            self.imported()
        self.assertFalse(SupplierInvoice.objects.exists())

    def test_no_external_attachments_are_fetched(self):
        extra = b'<cac:AdditionalDocumentReference><cbc:ID>EXT</cbc:ID><cac:Attachment><cac:ExternalReference><cbc:URI>https://example.test/private</cbc:URI></cac:ExternalReference></cac:Attachment></cac:AdditionalDocumentReference>'
        data = self.data.replace(b"<cac:AccountingSupplierParty>", extra + b"<cac:AccountingSupplierParty>", 1)
        with patch("urllib.request.urlopen", side_effect=AssertionError("No attachments fetched")):
            invoice = self.imported(data)
        self.assertEqual(invoice.extracted_data["attachments"][0]["external_reference"], "https://example.test/private")

    def test_prepaid_amount_does_not_get_lost_or_create_payment(self):
        data = self.data.replace(b'<cbc:PayableAmount currencyID="EUR">121.00</cbc:PayableAmount>',
            b'<cbc:PrepaidAmount currencyID="EUR">20.00</cbc:PrepaidAmount><cbc:PayableAmount currencyID="EUR">101.00</cbc:PayableAmount>')
        invoice = self.imported(data)
        self.assertEqual(invoice.total, Decimal("121"))
        self.assertEqual(invoice.payable, Decimal("101"))
        self.assertEqual(invoice.extracted_data["prepaid"], "20.00")
        self.assertEqual(invoice.validations.first().status, "VALID", invoice.validations.first().details)

    def test_reject_requires_reason_and_is_final(self):
        invoice = self.imported()
        with self.assertRaises(ValidationError):
            supplier_xml.review_invoice(actor=self.actor, pk=invoice.pk, revision=0, supplier=None, note="", action="reject")
        invoice = supplier_xml.review_invoice(actor=self.actor, pk=invoice.pk, revision=0, supplier=None, note="Commande inconnue", action="reject")
        self.assertEqual(invoice.status, "REJECTED")
        self.assertIsNone(invoice.supplier_id)
        with self.assertRaises(ValidationError):
            self.approved(invoice)

    def test_original_review_and_validation_history_immutable(self):
        invoice = self.approved(self.imported())
        for sql in ("UPDATE accounting_supplierinvoice SET total=1 WHERE id=%s",
            "UPDATE accounting_supplierinvoice SET status='RECEIVED' WHERE id=%s",
            "DELETE FROM accounting_supplierinvoicevalidation WHERE invoice_id=%s"):
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, [invoice.pk])
        invoice.extracted_data = {}
        with self.assertRaises(ValidationError):
            invoice.save()

    def test_tampered_file_download_review_and_revalidation_refused(self):
        invoice = self.imported()
        Path(self.directory.name, invoice.storage_path).write_bytes(b"changed")
        with self.assertRaises(ValidationError):
            self.approved(invoice)
        with self.assertRaises(ValidationError):
            supplier_xml.revalidate_invoice(actor=self.actor, pk=invoice.pk)
        self.assertEqual(self.client.get(reverse("accounting:supplier_invoice_download", args=[invoice.pk])).status_code, 409)

    def test_archiving_failure_rolls_back_invoice(self):
        with patch("django.core.files.storage.FileSystemStorage.save", side_effect=OSError("disk unavailable")), self.assertRaises(OSError):
            self.imported()
        self.assertFalse(SupplierInvoice.objects.exists())

    def test_safe_filename_and_http_upload_screens_review(self):
        response = self.client.post(reverse("accounting:supplier_invoice_upload"),
            {"file": SimpleUploadedFile("invoice.xml", self.data, content_type="application/xml")})
        self.assertEqual(response.status_code, 302)
        invoice = SupplierInvoice.objects.get()
        for name, args in (("supplier_invoices", []), ("supplier_invoice_upload", []), ("supplier_invoice_detail", [invoice.pk])):
            self.assertEqual(self.client.get(reverse("accounting:" + name, args=args)).status_code, 200)
        response = self.client.post(reverse("accounting:supplier_invoice_review", args=[invoice.pk]),
            {"revision": 0, "supplier": self.supplier.pk, "note": "Contrôle HTTP QA", "action": "approve"})
        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "REVIEWED")
        self.assertNotIn("invoice.xml", invoice.storage_path)

    def test_permissions_csrf_and_http_methods(self):
        invoice = self.imported()
        user = get_user_model().objects.create_user("no-import", password="password")
        self.client.force_login(user)
        for name, args in (("supplier_invoices", []), ("supplier_invoice_upload", []),
            ("supplier_invoice_detail", [invoice.pk]), ("supplier_invoice_download", [invoice.pk])):
            self.assertEqual(self.client.get(reverse("accounting:" + name, args=args)).status_code, 403)
        with self.assertRaises(PermissionDenied):
            supplier_xml.import_invoice(actor=user, data=self.data, filename="invoice.xml")
        self.assertEqual(self.client.post(reverse("accounting:supplier_invoice_review", args=[invoice.pk]), {}).status_code, 403)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.actor)
        self.assertEqual(browser.post(reverse("accounting:supplier_invoice_upload"), {}).status_code, 403)
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse("accounting:supplier_invoice_revalidate", args=[invoice.pk])).status_code, 405)

    def test_reader_has_no_download_or_review_implicitly(self):
        invoice = self.imported()
        user = get_user_model().objects.create_user("supplier-reader")
        user.user_permissions.add(Permission.objects.get(content_type__app_label="accounting", codename="view_supplierinvoice"))
        self.client.force_login(user)
        response = self.client.get(reverse("accounting:supplier_invoice_detail", args=[invoice.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Télécharger le XML original")
        self.assertNotContains(response, "Enregistrer la décision")
        self.assertEqual(self.client.get(reverse("accounting:supplier_invoice_download", args=[invoice.pk])).status_code, 403)
