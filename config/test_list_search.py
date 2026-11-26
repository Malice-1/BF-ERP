from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from sales.models import Customer, InvoiceFormat
from suppliers.models import Supplier, SupplierAddress, SupplierContact


class ListSearchTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser("admin"))
        Supplier.objects.create(code="ALPHA-1", name="Premier fournisseur")
        Supplier.objects.create(code="002", name="Alpha fournisseur", enterprise_number="0123456789")

    def test_supplier_search_filters_server_results_by_column(self):
        url = reverse("purchasing:suppliers")
        default = self.client.get(url, {"q": "alpha"})
        self.assertContains(default, "Premier fournisseur")
        self.assertContains(default, "Alpha fournisseur")
        selected = self.client.get(url, {"q": "alpha", "field": "code"})
        self.assertContains(selected, '<option value="code" selected>Code</option>')
        self.assertContains(selected, "Premier fournisseur")
        self.assertNotContains(selected, "Alpha fournisseur")
        normalized = self.client.get(url, {"q": "BE 0123.456.789", "field": "enterprise"})
        self.assertContains(normalized, "Alpha fournisseur")

    def test_admin_search_filters_server_results_by_column(self):
        url = reverse("admin:suppliers_supplier_changelist")
        selected = self.client.get(url, {"q": "alpha", "search_column": "name"})
        self.assertContains(selected, '<option value="name" selected>Nom</option>')
        self.assertContains(selected, "Alpha fournisseur")
        self.assertNotContains(selected, "Premier fournisseur")
        fallback = self.client.get(url, {"q": "alpha", "search_column": "unknown"})
        self.assertContains(fallback, "Premier fournisseur")
        self.assertContains(fallback, "Alpha fournisseur")


class PartyQualityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("lecteur")
        self.client.force_login(self.user)

    def grant(self, app, *codes):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label=app, codename__in=codes,
        ))

    def test_supplier_review_uses_legacy_details_and_reports_inconsistencies(self):
        url = reverse("purchasing:suppliers")
        self.assertEqual(self.client.get(url, {"quality": "1"}).status_code, 403)
        self.grant("suppliers", "view_supplier", "change_supplier")
        complete = Supplier.objects.create(
            code="OK", name="Fournisseur complet", enterprise_number="0123456749",
            bank_account="BE68 5390 0754 7034",
        )
        SupplierAddress.objects.create(supplier=complete, label="Siège", street="Rue QA", zip_code="1000",
                                       city="Bruxelles", country="Belgique")
        SupplierContact.objects.create(supplier=complete, label="Contact QA", phone="+32 2 555 01 23")
        problem = Supplier.objects.create(
            code="ERR", name="Fournisseur à corriger", enterprise_number="0123456749",
            vat_number="BE0123456848", country="BE", zip_code="123", bank_account="BE00", email="invalide",
        )
        response = self.client.get(url, {"quality": "1"})
        self.assertNotContains(response, complete.name)
        for message in (
            problem.name, "Format du courriel invalide", "IBAN belge invalide",
            "Le numéro d’entreprise et la TVA belge diffèrent", "Code postal belge attendu",
            reverse("purchasing:supplier_edit", args=[problem.pk]),
        ):
            self.assertContains(response, message)
        self.assertContains(self.client.get(url, {"quality": "1", "q": "OK", "field": "code"}),
                            "Aucune fiche à vérifier")

    def test_customer_review_checks_peppol_only_when_selected(self):
        url = reverse("sales:customers")
        self.assertEqual(self.client.get(url, {"quality": "1"}).status_code, 403)
        self.grant("sales", "view_customer", "configure_customer_billing")
        common = {"street": "Rue QA", "zip_code": "1000", "city": "Bruxelles", "email": "qa@example.test"}
        complete = Customer.objects.create(code="PDF", name="Client PDF complet", invoice_format=InvoiceFormat.PDF,
                                           **common)
        problem = Customer.objects.create(code="XML", name="Client XML à corriger", invoice_format=InvoiceFormat.XML,
                                          vat_number="BE0123456748", peppol_endpoint_scheme="XXX", **common)
        response = self.client.get(url, {"quality": "1", "q": "Client", "field": "name"})
        self.assertNotContains(response, complete.name)
        for message in (
            problem.name, "Identifiant Peppol", "Schéma Peppol attendu", "Numéro de TVA belge invalide",
            reverse("sales:customer_billing", args=[problem.pk]),
        ):
            self.assertContains(response, message)
        self.assertNotContains(response, f'href="{reverse("sales:customer_edit", args=[problem.pk])}"')
        self.assertContains(response, 'name="quality" value="1"')
        self.assertContains(self.client.get(url), complete.name)
