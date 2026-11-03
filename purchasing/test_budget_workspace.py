from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.test import TestCase
from django.urls import reverse
from budgeting.models import BudgetProduct, CostCenter, Funding
from .budget_views import MANAGER_PERMISSIONS
from .models import EnvelopeVersion, Allocation


class BudgetWorkspaceTests(TestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user("manager")
        for permission in MANAGER_PERMISSIONS:
            self.manager.user_permissions.add(Permission.objects.get(
                content_type__app_label=permission.split(".")[0], codename=permission.split(".")[1]))
        self.product = BudgetProduct.objects.create(code="BI", label="Budget")
        self.cdf = CostCenter.objects.create(code="CDF", label="Centre")
        self.funding = Funding.objects.create(code="F", label="Fonds")
        self.client.force_login(self.manager)
        self.index = reverse("purchasing:budget_versions")

    def create_version(self, label="V1"):
        response = self.client.post(self.index, {"year": 2026, "label": label})
        version = EnvelopeVersion.objects.latest("pk")
        self.assertRedirects(response, reverse("purchasing:budget_version", args=[version.pk]))
        return version

    def line_data(self, amount="1200.00", count=1):
        data = {"allocations-TOTAL_FORMS": count, "allocations-INITIAL_FORMS": 0}
        for i in range(count):
            data.update({f"allocations-{i}-budget_product": self.product.pk,
                f"allocations-{i}-cost_center": self.cdf.pk,
                f"allocations-{i}-funding": self.funding.pk,
                f"allocations-{i}-amount": amount})
        return data

    def test_create_fill_publish_and_replace(self):
        version = self.create_version()
        url = reverse("purchasing:budget_version", args=[version.pk])
        self.assertRedirects(self.client.post(url, self.line_data()), url)
        self.assertEqual(version.allocations.get().amount, Decimal("1200"))
        self.assertRedirects(self.client.post(url, {"action": "publish"}), url)
        version.refresh_from_db()
        self.assertIsNotNone(version.published_at)
        self.assertContains(self.client.get(url), "Version active")
        self.client.post(url, self.line_data("500"))
        self.assertEqual(version.allocations.get().amount, Decimal("1200"))
        replacement = self.create_version("V2")
        url2 = reverse("purchasing:budget_version", args=[replacement.pk])
        self.client.post(url2, self.line_data("1500"))
        self.client.post(url2, {"action": "publish"})
        version.envelope.refresh_from_db()
        self.assertEqual(version.envelope.active_version_id, replacement.pk)
        self.assertEqual(version.allocations.get().amount, Decimal("1200"))

    def test_invalid_duplicate_negative_and_empty_publication(self):
        version = self.create_version()
        url = reverse("purchasing:budget_version", args=[version.pk])
        self.client.post(url, {"action": "publish"})
        version.refresh_from_db()
        self.assertIsNone(version.published_at)
        for data in (self.line_data("-1"), self.line_data(count=2)):
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context["formset"].is_valid())
            self.assertFalse(Allocation.objects.exists())

    def test_access_control(self):
        version = self.create_version()
        user = get_user_model().objects.create_user("requester")
        self.client.force_login(user)
        for url in (self.index, reverse("purchasing:budget_version", args=[version.pk])):
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {"action": "publish"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.index).status_code, 302)

    def test_budget_manager_cannot_create_requests_without_permission(self):
        self.assertRedirects(self.client.get(reverse("purchasing:list")), reverse("purchasing:budget_home"))
        response = self.client.get(reverse("purchasing:budget_home"))
        self.assertNotContains(response, "Mes demandes")
        self.assertNotContains(response, "Créer une demande")
        url = reverse("purchasing:create")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        from accounts.models import Role
        role = Role.objects.create(code="DA", label="Demandeur")
        role.permissions.add(Permission.objects.get(
            content_type__app_label="purchasing", codename="add_purchaserequest"))
        self.manager.roles.add(role)
        self.assertContains(self.client.get(reverse("purchasing:list")), "Mes demandes")
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_sections_and_detailed_product_permissions(self):
        url = reverse("purchasing:detailed_products")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.manager.user_permissions.add(Permission.objects.get(
            content_type__app_label="purchasing", codename="add_detailedproduct"))
        self.assertContains(self.client.get(reverse("purchasing:list")), "Produits détaillés")
        data = {"code": "DETAIL", "label": "Produit détaillé", "budget_product": self.product.pk}
        self.assertRedirects(self.client.post(url, data), url)
        from budgeting.models import DetailedProduct
        self.assertEqual(DetailedProduct.objects.get(code="DETAIL").budget_product, self.product)
        self.assertIn("code", self.client.post(url, data).context["form"].errors)
        response = self.client.get(reverse("purchasing:allocation_versions"))
        self.assertContains(response, "Alimenter une version budgétaire")
        self.assertEqual(response.context["nav_section"], "budget")
        self.assertEqual(self.client.get(reverse("purchasing:configuration")).status_code, 403)
        self.manager.is_staff = True
        self.manager.is_superuser = True
        self.manager.save()
        response = self.client.get(reverse("purchasing:configuration"))
        self.assertContains(response, reverse("admin:accounts_user_changelist"))
        self.assertNotContains(response, "Groupes et permissions")
        self.assertEqual(response.context["nav_section"], "configuration")

    def test_product_permission_grant_group_and_revocation(self):
        url = reverse("purchasing:budget_products")
        data = {"code": "NEW-BI", "label": "Nouveau produit"}
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, data).status_code, 403)
        permission = Permission.objects.get(content_type__app_label="budgeting", codename="add_budgetproduct")
        self.manager.user_permissions.add(permission)
        self.assertContains(self.client.get(reverse("purchasing:budget_home")), url)
        self.assertRedirects(self.client.post(url, data), url)
        self.assertTrue(BudgetProduct.objects.filter(code="NEW-BI").exists())
        response = self.client.post(url, data)
        self.assertIn("code", response.context["form"].errors)
        self.assertEqual(BudgetProduct.objects.filter(code="NEW-BI").count(), 1)
        response = self.client.post(url, {"code": "", "label": ""})
        self.assertFalse(response.context["form"].is_valid())
        self.manager.user_permissions.remove(permission)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertNotContains(self.client.get(reverse("purchasing:budget_home")), url)
        group = Group.objects.create(name="Créateurs de produits")
        group.permissions.add(permission)
        self.manager.groups.add(group)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.manager.groups.remove(group)
        self.assertEqual(self.client.post(url, {"code": "DENIED", "label": "Denied"}).status_code, 403)
        self.assertFalse(BudgetProduct.objects.filter(code="DENIED").exists())
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
