from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Supplier


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
