from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import CostCenter


class CostCenterAdminManagersTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("cdf.admin", password="test")
        self.user = User.objects.create_user("responsable", first_name="Alex", last_name="Martin")
        self.inactive = User.objects.create_user("inactif", is_active=False)
        self.cdf = CostCenter.objects.create(code="CDF01", label="Formation")
        self.url = reverse("admin:budgeting_costcenter_change", args=[self.cdf.pk])
        self.client.force_login(self.admin)

    def payload(self, managers):
        return {"code": self.cdf.code, "label": self.cdf.label, "managers": managers, "_save": "Enregistrer"}

    def test_choices_include_active_application_users_without_staff_status(self):
        response = self.client.get(self.url)
        field = response.context["adminform"].form.fields["managers"]
        self.assertIn(self.user, field.queryset)
        self.assertNotIn(self.inactive, field.queryset)
        self.assertContains(response, 'class="admin-autocomplete"')
        self.assertContains(response, 'data-minimum-input-length="0"')
        self.assertContains(response, reverse("admin:budgeting_costcenter_manager_choices"))

    def test_dropdown_loads_active_users_and_searches_partial_names_and_identifiers(self):
        url = reverse("admin:budgeting_costcenter_manager_choices")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(str(self.user.pk), ids)
        self.assertNotIn(str(self.inactive.pk), ids)
        for term in ("ale", "ART", "pons", "mart al", "Alex responsable"):
            with self.subTest(term=term):
                data = self.client.get(url, {"term": term}).json()
                self.assertEqual(data["results"], [{"id": str(self.user.pk), "text": "Alex Martin (responsable)"}])
        self.assertEqual(self.client.get(url, {"term": "inconnu"}).json()["results"], [])

    def test_dropdown_is_paginated_and_permission_protected(self):
        url = reverse("admin:budgeting_costcenter_manager_choices")
        get_user_model().objects.bulk_create([
            get_user_model()(username=f"personne-{n:02}", is_active=True) for n in range(25)])
        first = self.client.get(url).json()
        second = self.client.get(url, {"page": 2}).json()
        self.assertEqual(len(first["results"]), 20)
        self.assertTrue(first["pagination"]["more"])
        self.assertFalse(second["pagination"]["more"])
        self.assertFalse({r["id"] for r in first["results"]} & {r["id"] for r in second["results"]})
        editor = get_user_model().objects.create_user("no_manager_access", is_staff=True)
        editor.user_permissions.add(Permission.objects.get(codename="change_costcenter"))
        self.client.force_login(editor)
        self.assertEqual(self.client.get(url).status_code, 403)
        editor.user_permissions.add(Permission.objects.get(codename="manage_cost_center_managers"))
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_create_and_update_responsables_from_cdf_form(self):
        response = self.client.post(reverse("admin:budgeting_costcenter_add"), {
            "code": "NEW", "label": "Nouveau CDF", "managers": [self.user.pk], "_save": "Enregistrer"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(CostCenter.objects.get(code="NEW").managers.all()), [self.user])
        response = self.client.post(self.url, self.payload([self.user.pk, self.admin.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertSetEqual(set(self.cdf.managers.all()), {self.user, self.admin})
        self.assertContains(self.client.get(reverse("admin:budgeting_costcenter_changelist")), "Alex Martin")
        self.assertEqual(self.client.post(self.url, self.payload([])).status_code, 302)
        self.assertFalse(self.cdf.managers.exists())

    def test_inactive_user_cannot_be_newly_assigned(self):
        response = self.client.post(self.url, self.payload([self.inactive.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("managers", response.context["adminform"].form.errors)
        self.assertFalse(self.cdf.managers.exists())

    def test_existing_inactive_assignment_is_preserved_and_can_be_removed(self):
        self.cdf.managers.add(self.inactive)
        response = self.client.get(self.url)
        self.assertContains(response, "inactif — compte inactif")
        self.assertEqual(self.client.post(self.url, self.payload([self.inactive.pk])).status_code, 302)
        self.assertIn(self.inactive, self.cdf.managers.all())
        self.assertEqual(self.client.post(self.url, self.payload([])).status_code, 302)
        self.assertFalse(self.cdf.managers.exists())

    def test_change_cdf_permission_alone_cannot_change_managers(self):
        editor = get_user_model().objects.create_user("cdf.editor", is_staff=True)
        editor.user_permissions.add(Permission.objects.get(codename="change_costcenter"))
        self.cdf.managers.add(self.user)
        self.client.force_login(editor)
        response = self.client.get(self.url)
        self.assertNotIn("managers", response.context["adminform"].form.fields)
        self.assertEqual(self.client.post(self.url, self.payload([self.admin.pk])).status_code, 302)
        self.assertEqual(list(self.cdf.managers.all()), [self.user])
        editor.user_permissions.add(Permission.objects.get(codename="manage_cost_center_managers"))
        response = self.client.post(self.url, self.payload([self.admin.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.cdf.managers.all()), [self.admin])
