import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from receiving.models import StockMovement
from . import services, documents
from .models import (Customer, IssuerConfiguration, SalesOrder, SalesOrderLine, SalesInvoice, SalesInvoiceLine,
    InvoiceDocument, InvoicePayment, PaymentReversal, SalesEvent, SalesSequence)


class SalesFixture:
    def setUp(self):
        super().setUp()
        fixed_date = patch("sales.services.timezone.localdate", return_value=date(2026, 11, 16))
        fixed_date.start()
        self.addCleanup(fixed_date.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = override_settings(SALES_DOCUMENT_ROOT=self.directory.name)
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.actor = get_user_model().objects.create_superuser("sales-admin", "admin@example.test", "password")
        self.customer = Customer.objects.create(code="CLIENT", name="Client formation", street="Rue des Tests 1",
            zip_code="1000", city="Bruxelles", country="BE", invoice_format="PDF", vat_number="BE0123456749",
            peppol_endpoint_id="0123456749", peppol_endpoint_scheme="0208")
        self.issuer = IssuerConfiguration.objects.create(name="Émetteur Formation", street="Rue Formation 2",
            zip_code="1000", city="Bruxelles", country="BE", vat_number="BE0123456749", legal_id="0123456749",
            iban="BE68539007547034", peppol_endpoint_id="0123456749", peppol_endpoint_scheme="0208")
        self.client.force_login(self.actor)

    def values(self, **extra):
        return {"customer": self.customer, "order_date": date(2026, 11, 16), "customer_reference": "REF-123",
            "currency": "EUR", "notes": "Interne", **extra}

    def line(self, **extra):
        return {"description": "Formation Python", "quantity": Decimal("2"), "unit": "C62",
            "unit_price": Decimal("100"), "discount": Decimal("10"), "tax_code": "S", "tax_rate": Decimal("21"), **extra}

    def order(self, **extra):
        return services.save_order(actor=self.actor, values=self.values(),
            lines=[self.line(**extra), self.line(**{**extra, "description": "Formation SQL"})])

    def confirm(self, order):
        return services.transition(actor=self.actor, pk=order.pk, revision=order.revision, action="confirm")

    def invoice(self):
        order = self.confirm(self.order())
        return services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)


class SalesTests(SalesFixture, TestCase):
    def test_two_lines_totals_number_and_confirmation(self):
        order = self.order()
        self.assertEqual(order.number, "CV-2026-0001")
        self.assertEqual(order.status, "DRAFT")
        self.assertEqual(order.lines.count(), 2)
        self.assertEqual(order.subtotal, Decimal("380.00"))
        self.assertEqual(order.tax_total, Decimal("79.80"))
        self.assertEqual(order.total, Decimal("459.80"))
        order = self.confirm(order)
        self.assertEqual(order.status, "CONFIRMED")
        with self.assertRaises(ValidationError):
            services.save_order(actor=self.actor, pk=order.pk, revision=order.revision, values=self.values(), lines=[self.line()])
        line = order.lines.first()
        line.quantity = 3
        with self.assertRaises(ValidationError):
            line.save()

    def test_vat_rounding_is_by_category(self):
        lines = [self.line(quantity=Decimal(1), unit_price=Decimal("0.03"), discount=0) for _ in range(2)]
        order = services.save_order(actor=self.actor, values=self.values(), lines=lines)
        self.assertEqual(order.subtotal, Decimal("0.06"))
        self.assertEqual(order.tax_total, Decimal("0.01"))
        self.assertEqual(sum(line.tax_amount for line in order.lines.all()), order.tax_total)
        self.assertEqual(sum(line.total for line in order.lines.all()), order.total)

    def test_invalid_lines_never_persist(self):
        for changes in ({"quantity": Decimal(0)}, {"unit_price": Decimal(-1)}, {"discount": Decimal(201)},
                {"tax_code": "E", "tax_rate": Decimal(0)}, {"tax_code": "S", "tax_rate": Decimal(0)}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.order(**changes)
        self.assertEqual(SalesOrder.objects.count(), 0)
        self.assertEqual(SalesSequence.objects.count(), 0)

    def test_inactive_client_and_empty_order_rejected(self):
        with self.assertRaises(ValidationError):
            services.save_order(actor=self.actor, values=self.values(), lines=[])
        self.customer.is_active = False
        self.customer.save()
        with self.assertRaises(ValidationError):
            self.order()

    def test_revision_conflict_and_cancellation(self):
        order = self.order()
        with self.assertRaises(ValidationError):
            services.transition(actor=self.actor, pk=order.pk, revision=0, action="confirm")
        order = self.confirm(order)
        order = services.transition(actor=self.actor, pk=order.pk, revision=order.revision, action="cancel")
        self.assertEqual(order.status, "CANCELLED")
        with self.assertRaises(ValidationError):
            self.confirm(order)

    def test_pdf_complete_archive_and_download(self):
        invoice = self.invoice()
        self.assertEqual(invoice.document_status, "ISSUED")
        self.assertEqual(invoice.lines.count(), 2)
        self.assertEqual(invoice.total, Decimal("459.80"))
        self.assertEqual(invoice.order.status, "INVOICED")
        document = invoice.documents.get()
        self.assertTrue(documents.read_document(document).startswith(b"%PDF-"))
        self.assertEqual(document.validations.get().status, "NOT_REQUIRED")
        response = self.client.get(reverse("sales:download", args=[invoice.pk, document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertFalse(StockMovement.objects.exists())

    def test_duplicate_invoice_cancellation_and_regeneration(self):
        invoice = self.invoice()
        order = SalesOrder.objects.get(pk=invoice.order_id)
        with self.assertRaises(ValidationError):
            services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)
        with self.assertRaises(ValidationError):
            services.transition(actor=self.actor, pk=order.pk, revision=order.revision, action="cancel")
        documents.regenerate(actor=self.actor, pk=invoice.pk)
        self.assertEqual(SalesInvoice.objects.count(), 1)
        self.assertEqual(invoice.documents.count(), 2)
        self.assertEqual(invoice.number, "FV-2026-0001")

    def test_snapshot_immutable_and_document_reproduction(self):
        invoice = self.invoice()
        self.customer.name = "Nouveau nom"
        self.customer.street = "Nouvelle adresse"
        self.customer.invoice_format = "PEPPOL_XML"
        self.customer.save()
        self.issuer.name = "Nouvel émetteur"
        self.issuer.save()
        documents.regenerate(actor=self.actor, pk=invoice.pk)
        invoice.refresh_from_db()
        self.assertEqual(invoice.customer_snapshot["name"], "Client formation")
        self.assertEqual(invoice.issuer_snapshot["name"], "Émetteur Formation")
        self.assertEqual(invoice.invoice_format, "PDF")
        invoice.total = 1
        with self.assertRaises(ValidationError):
            invoice.save()
        with self.assertRaises(ValidationError):
            invoice.delete()
        line = invoice.lines.first()
        with self.assertRaises(ValidationError):
            line.save()

    def test_storage_error_keeps_issued_number_and_can_retry(self):
        with patch("sales.documents.FileSystemStorage.save", side_effect=OSError("disk full")):
            invoice = self.invoice()
        self.assertEqual(invoice.document_status, "DOCUMENT_ERROR")
        self.assertEqual(SalesInvoice.objects.count(), 1)
        self.assertEqual(invoice.order.status, "INVOICED")
        documents.regenerate(actor=self.actor, pk=invoice.pk)
        invoice.refresh_from_db()
        self.assertEqual(invoice.document_status, "ISSUED")
        self.assertEqual(invoice.number, "FV-2026-0001")

    def test_preparation_failure_does_not_issue_or_consume_number(self):
        order = self.confirm(self.order())
        with patch("sales.documents.render_document", side_effect=RuntimeError("renderer unavailable")):
            with self.assertRaises(ValidationError):
                services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)
        self.assertFalse(SalesInvoice.objects.exists())
        self.assertFalse(SalesSequence.objects.filter(series="FV").exists())
        self.assertTrue(order.events.filter(action="Préparation documentaire refusée").exists())

    def test_missing_billing_configuration_blocks_emission(self):
        order = self.confirm(self.order())
        for changes in ({"street": ""}, {"invoice_format": ""}, {"invoice_format": "PEPPOL_XML", "peppol_endpoint_id": ""}):
            for field, value in changes.items():
                setattr(self.customer, field, value)
            self.customer.save()
            with self.assertRaises(ValidationError):
                services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)
        self.assertFalse(SalesInvoice.objects.exists())

    def test_payments_partial_full_reversal_and_idempotence(self):
        invoice = self.invoice()
        token = uuid4()
        args = dict(actor=self.actor, pk=invoice.pk, amount=Decimal("100"),
            payment_date=date(2026, 11, 16), reference="Virement", token=token)
        first = services.record_payment(**args)
        self.assertEqual(services.record_payment(**args).pk, first.pk)
        invoice.refresh_from_db()
        self.assertEqual(invoice.payment_status, "PARTIALLY_PAID")
        services.record_payment(**{**args, "amount": Decimal("359.80"), "token": uuid4()})
        invoice.refresh_from_db()
        self.assertEqual(invoice.payment_status, "PAID")
        with self.assertRaises(ValidationError):
            services.record_payment(**{**args, "token": uuid4()})
        services.reverse_payment(actor=self.actor, pk=invoice.pk, payment_id=first.pk, reason="Erreur de saisie")
        invoice.refresh_from_db()
        self.assertEqual(invoice.payment_status, "PARTIALLY_PAID")
        self.assertEqual(services.paid_amount(invoice), Decimal("359.80"))
        self.assertEqual(InvoicePayment.objects.count(), 2)
        self.assertEqual(PaymentReversal.objects.count(), 1)

    def test_document_tampering_and_cross_invoice_access(self):
        first = self.invoice()
        second = self.invoice()
        document = first.documents.get()
        self.assertEqual(self.client.get(reverse("sales:download", args=[second.pk, document.pk])).status_code, 404)
        Path(self.directory.name, document.storage_path).write_bytes(b"tampered")
        self.assertEqual(self.client.get(reverse("sales:download", args=[first.pk, document.pk])).status_code, 409)

    def test_html_screens_render(self):
        invoice = self.invoice()
        routes = [("home", []), ("customers", []), ("customer_edit", [self.customer.pk]),
            ("customer_billing", [self.customer.pk]), ("issuer", []), ("trainings", []),
            ("training_new", []), ("orders", []), ("order_new", []), ("order_detail", [invoice.order_id]),
            ("invoices", []), ("invoice_detail", [invoice.pk]), ("report", [])]
        for name, args in routes:
            with self.subTest(route=name):
                response = self.client.get(reverse("sales:" + name, args=args))
                self.assertIn(response.status_code, (200, 302))

    def test_permission_checks_in_services_and_http(self):
        invoice = self.invoice()
        user = get_user_model().objects.create_user("no-sales", password="password")
        self.client.force_login(user)
        with self.assertRaises(PermissionDenied):
            services.issue_invoice(actor=user, pk=invoice.order_id, revision=0)
        for url in (reverse("sales:invoices"), reverse("sales:orders"), reverse("sales:customers"),
                reverse("sales:download", args=[invoice.pk, invoice.documents.get().pk]), reverse("sales:report")):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse("sales:order_action", args=[invoice.order_id, "invoice"]), {}).status_code, 403)
        self.assertEqual(self.client.post(reverse("sales:payment", args=[invoice.pk]), {}).status_code, 403)

    def test_sales_only_user_landing_and_billing_field_permissions(self):
        user = get_user_model().objects.create_user("sales-only", password="password")
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="sales",
            codename__in=["view_customer", "change_customer"]))
        self.client.force_login(user)
        response = self.client.get(reverse("purchasing:list"))
        self.assertRedirects(response, reverse("sales:home"), fetch_redirect_response=False)
        response = self.client.get(reverse("sales:customer_edit", args=[self.customer.pk]))
        self.assertNotContains(response, 'name="invoice_format"')
        data = {field.name: getattr(self.customer, field.name) for field in Customer._meta.fields
            if field.name not in ("id",)}
        data["invoice_format"] = "PEPPOL_XML"
        data["name"] = "Modification autorisée"
        self.client.post(reverse("sales:customer_edit", args=[self.customer.pk]), data)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.invoice_format, "PDF")
        self.assertEqual(self.customer.name, "Modification autorisée")

    def test_actions_require_post(self):
        order = self.order()
        self.assertEqual(self.client.get(reverse("sales:order_action", args=[order.pk, "confirm"])).status_code, 405)

    def test_order_form_posts_multiple_lines_and_preserves_invalid_draft(self):
        data = {"customer": self.customer.pk, "order_date": "2026-11-16", "currency": "EUR",
            "customer_reference": "WEB", "notes": "", "revision": "0", "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "100"}
        for i in range(2):
            for name, value in self.line().items():
                data[f"lines-{i}-{name}"] = str(value)
        response = self.client.post(reverse("sales:order_new"), data)
        self.assertEqual(response.status_code, 302, response.content.decode())
        order = SalesOrder.objects.get()
        self.assertEqual(order.lines.count(), 2)
        data.update({"revision": str(order.revision), "lines-INITIAL_FORMS": "2"})
        for index, line in enumerate(order.lines.all()):
            data[f"lines-{index}-id"] = str(line.pk)
        data["lines-0-quantity"] = "-1"
        response = self.client.post(reverse("sales:order_edit", args=[order.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.lines.first().quantity, Decimal("2"))

    def test_post_actions_require_csrf(self):
        from django.test import Client
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.actor)
        order = self.order()
        response = browser.post(reverse("sales:order_action", args=[order.pk, "confirm"]), {"revision": order.revision})
        self.assertEqual(response.status_code, 403)

    def test_payment_and_document_history_cannot_be_overwritten(self):
        invoice = self.invoice()
        payment = services.record_payment(actor=self.actor, pk=invoice.pk, amount=Decimal("10"),
            payment_date=date(2026, 11, 16), reference="Test", token=uuid4())
        payment.amount = 1
        with self.assertRaises(ValidationError):
            payment.save()
        with self.assertRaises(ValidationError):
            invoice.documents.all().delete()
        with self.assertRaises(ValidationError):
            SalesInvoice.objects.filter(pk=invoice.pk).update(total=0)


class XmlTests(SalesFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.customer.invoice_format = "PEPPOL_XML"
        self.customer.save()

    def test_real_xsd_and_schematron_validation(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("No invoice network access")):
            invoice = self.invoice()
        self.assertEqual(invoice.document_status, "ISSUED")
        document = invoice.documents.get()
        run = document.validations.get()
        self.assertEqual(run.status, "VALID", run.details)
        self.assertTrue(run.rules_version)
        data = documents.read_document(document)
        self.assertIn(b"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2", data)
        self.assertFalse(StockMovement.objects.exists())
        run2 = documents.revalidate(actor=self.actor, pk=invoice.pk, document_id=document.pk)
        self.assertEqual(run2.status, "VALID", run2.details)
        self.assertEqual(document.validations.count(), 2)

    def test_supported_tax_categories_pass_official_rules(self):
        for code in ("Z", "E", "AE", "O"):
            with self.subTest(code=code):
                order = self.confirm(self.order(tax_code=code, tax_rate=Decimal(0),
                    exemption_reason="Motif fiscal de test" if code in ("E", "AE", "O") else ""))
                invoice = services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)
                run = invoice.documents.get().validations.get()
                self.assertEqual(run.status, "VALID", run.details)

    def test_xml_requires_real_buyer_or_purchase_reference(self):
        order = services.save_order(actor=self.actor, values=self.values(customer_reference=""), lines=[self.line()])
        order = self.confirm(order)
        with self.assertRaises(ValidationError):
            services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)
        self.customer.reference = "BUYER-ROUTING"
        self.customer.save()
        invoice = services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)
        data = documents.read_document(invoice.documents.get())
        self.assertIn(b"<cbc:BuyerReference>BUYER-ROUTING</cbc:BuyerReference>", data)
        self.assertNotIn(b"<cac:OrderReference>", data)

    def test_invalid_unit_blocks_issue_and_records_failure(self):
        order = self.confirm(self.order(unit="BAD"))
        with self.assertRaises(ValidationError):
            services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)
        self.assertFalse(SalesInvoice.objects.exists())
        self.assertTrue(SalesEvent.objects.filter(action="Émission XML refusée").exists())
        self.assertFalse(SalesSequence.objects.filter(series="FV").exists())

    def test_missing_rules_fail_closed(self):
        order = self.confirm(self.order())
        with override_settings(SALES_RULES_ROOT=Path(self.directory.name)), self.assertRaises(ValidationError):
            services.issue_invoice(actor=self.actor, pk=order.pk, revision=order.revision)
        self.assertFalse(SalesInvoice.objects.exists())

    def test_invalid_schema_and_business_rules_are_rejected(self):
        result = documents.validate_xml(b'<Invoice/>', date(2026, 11, 16))
        self.assertEqual(result["status"], "INVALID", result)
        invoice = self.invoice()
        data = documents.read_document(invoice.documents.get())
        data = data.replace(b'<cbc:PayableAmount currencyID="EUR">459.80</cbc:PayableAmount>',
            b'<cbc:PayableAmount currencyID="EUR">999.00</cbc:PayableAmount>')
        result = documents.validate_xml(data, invoice.issue_date)
        self.assertEqual(result["status"], "INVALID", result)
        self.assertTrue(any(e["stage"] == "CEN-EN16931-UBL" for e in result["details"]))

    def test_rule_dates_and_dtd_rejected(self):
        result = documents.validate_xml(b'<Invoice/>', date(2050, 1, 1))
        self.assertEqual(result["status"], "UNAVAILABLE")
        result = documents.validate_xml(b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><x>&a;</x>', date(2026, 11, 16))
        self.assertEqual(result["status"], "UNAVAILABLE")
