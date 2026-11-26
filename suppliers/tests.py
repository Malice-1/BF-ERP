from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from .models import Supplier
from .spreadsheet import EXPORT_HEADERS, IMPORT_HEADERS


class SupplierManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="supplier-manager")
        self.client.force_login(self.user)

    def grant(self, *codes):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="suppliers", codename__in=codes))

    def test_permissions_are_checked_on_each_action(self):
        supplier = Supplier.objects.create(code="A", name="Alpha")
        listing = reverse("purchasing:suppliers")
        create = reverse("purchasing:supplier_create")
        edit = reverse("purchasing:supplier_edit", args=[supplier.pk])
        for url in (listing, create, edit):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.grant("view_supplier")
        self.assertContains(self.client.get(listing), "Alpha")
        for url in (create, edit):
            self.assertEqual(self.client.post(url, {"code": "X", "name": "Changed"}).status_code, 403)
        supplier.refresh_from_db()
        self.assertEqual(supplier.name, "Alpha")

    def test_create_edit_search_and_unique_code(self):
        self.grant("view_supplier", "add_supplier", "change_supplier")
        listing = reverse("purchasing:suppliers")
        create = reverse("purchasing:supplier_create")
        response = self.client.post(create, {"code": "F01", "name": "Alpha", "vat_number": "BE123"})
        self.assertRedirects(response, listing)
        supplier = Supplier.objects.get(code="F01")
        response = self.client.post(create, {"code": "F01", "name": "Duplicate"})
        self.assertIn("code", response.context["form"].errors)
        edit = reverse("purchasing:supplier_edit", args=[supplier.pk])
        self.assertRedirects(self.client.post(edit, {"code": "F01", "name": "Beta", "vat_number": "BE123"}), listing)
        supplier.refresh_from_db()
        self.assertEqual(supplier.name, "Beta")
        self.assertContains(self.client.get(listing, {"q": "BE123"}), "Beta")
        self.assertNotContains(self.client.get(listing, {"q": "unmatched"}), "Beta")
        response = self.client.get(reverse("purchasing:list"))
        self.assertContains(response, 'href="' + listing + '"')
        self.assertEqual(response.context["nav_section"], "purchases")

    def test_enterprise_number_create_edit_normalization_and_search(self):
        self.grant("view_supplier", "add_supplier", "change_supplier")
        listing = reverse("purchasing:suppliers")
        self.assertContains(self.client.get(reverse("purchasing:supplier_create")), 'name="enterprise_number"')
        response = self.client.post(reverse("purchasing:supplier_create"), {
            "code": "BCE", "name": "Fournisseur BCE", "enterprise_number": "BE 0123.456.749"})
        self.assertRedirects(response, listing)
        supplier = Supplier.objects.get(code="BCE")
        self.assertEqual(supplier.enterprise_number, "0123456749")
        self.assertFalse(supplier.vat_number)
        for query in ("0123456749", "0123.456.749", "BE0123456749"):
            self.assertContains(self.client.get(listing, {"q": query}), "Fournisseur BCE")
        edit = reverse("purchasing:supplier_edit", args=[supplier.pk])
        response = self.client.post(edit, {"code": "BCE", "name": "Fournisseur modifié", "enterprise_number": "0234.567.890"})
        self.assertRedirects(response, listing)
        supplier.refresh_from_db()
        self.assertEqual(supplier.enterprise_number, "0234567890")

    def test_enterprise_number_optional_and_model_save_normalizes(self):
        supplier = Supplier.objects.create(code="NUM", name="Numéro", enterprise_number="BE0123.456.749")
        self.assertEqual(Supplier.objects.get(pk=supplier.pk).enterprise_number, "0123456749")
        legacy = Supplier.objects.create(code="OLD", name="Sans numéro")
        self.assertEqual(legacy.enterprise_number, "")

    def upload_suppliers(self, *rows, headers=IMPORT_HEADERS):
        workbook = Workbook()
        workbook.active.append(headers)
        for row in rows:
            workbook.active.append(row)
        output = BytesIO()
        workbook.save(output)
        return self.client.post(reverse("purchasing:supplier_import"), {
            "file": SimpleUploadedFile("fournisseurs.xlsx", output.getvalue()),
        })

    def test_spreadsheet_permissions(self):
        listing = reverse("purchasing:suppliers")
        importer = reverse("purchasing:supplier_import")
        template = reverse("purchasing:supplier_template")
        self.assertEqual(self.client.get(listing, {"export": "xlsx"}).status_code, 403)
        self.grant("view_supplier")
        self.assertEqual(self.client.get(listing, {"export": "xlsx"}).status_code, 200)
        self.assertEqual(self.client.get(template).status_code, 403)
        self.assertEqual(self.client.get(importer).status_code, 403)
        self.assertEqual(self.upload_suppliers(("F01", "Alpha")).status_code, 403)

    def test_template_import_and_filtered_export(self):
        self.grant("add_supplier")
        self.assertContains(self.client.get(reverse("purchasing:supplier_import")), "Télécharger le patron")
        response = self.client.get(reverse("purchasing:supplier_template"))
        template = load_workbook(BytesIO(response.content)).active
        self.assertEqual(list(template.values), [IMPORT_HEADERS])
        self.assertEqual(template.column_dimensions["C"].number_format, "@")
        self.assertNotIn("Mode de facturation", IMPORT_HEADERS)
        row = ("001", "Alpha", 123456749, "BE00123", "Rue 1", "0100", "Bruxelles", "BE",
               "021234567", "0470123456", "Contact QA", "qa@example.test")
        response = self.upload_suppliers((*row, "TVA ignorée"), ("F02", "Beta", "FR123"),
                                         headers=EXPORT_HEADERS)
        listing = reverse("purchasing:suppliers")
        self.assertRedirects(response, listing, fetch_redirect_response=False)
        self.assertContains(self.client.get(listing), "Fournisseurs importés : 2.")
        self.assertIsNone(Supplier.objects.get(code="F02").vat_number)
        response = self.client.get(listing, {"export": "xlsx", "q": "001", "field": "code"})
        workbook = load_workbook(BytesIO(response.content))
        expected = (*row[:2], "0123456749", *row[3:], "BE0123456749")
        self.assertEqual(list(workbook.active.values), [EXPORT_HEADERS, expected])

    def test_invalid_or_duplicate_rows_reject_the_whole_file(self):
        self.grant("add_supplier")
        Supplier.objects.create(code="F02", name="Existant")
        response = self.upload_suppliers(("F01", "Alpha"), ("F01", "Doublon"), ("F02", "Existant"),
                                         ("F03", None))
        for line in (3, 4, 5):
            self.assertContains(response, f"Ligne {line}")
        self.assertEqual(list(Supplier.objects.values_list("code", flat=True)), ["F02"])
