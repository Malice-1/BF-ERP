from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from budgeting.models import BudgetProduct, CostCenter, Funding
from .budget_views import MANAGER_PERMISSIONS
from .models import EnvelopeVersion, Allocation


class BudgetWorkspaceTests(TestCase):
    def test_deleted_row_can_be_saved_with_only_its_hidden_fields(self):
        version = self.create_version()
        allocation = Allocation.objects.create(version=version, budget_product=self.product,
            cost_center=self.cdf, funding=self.funding, amount=100)
        url = reverse("purchasing:budget_version", args=[version.pk])
        self.client.get(url)
        self.assertTrue(Allocation.objects.filter(pk=allocation.pk).exists())
        payload = {"action": "save", "allocations-TOTAL_FORMS": 1, "allocations-INITIAL_FORMS": 1,
            "allocations-0-id": allocation.pk, "allocations-0-version": version.pk,
            "allocations-0-DELETE": "on"}
        self.assertRedirects(self.client.post(url, payload), url)
        self.assertFalse(Allocation.objects.filter(pk=allocation.pk).exists())

    def test_allocation_input_displays_two_decimals_without_changing_stored_precision(self):
        version = self.create_version()
        allocation = Allocation.objects.create(version=version, budget_product=self.product,
            cost_center=self.cdf, funding=self.funding, amount=Decimal("1200.1234567890"))
        response = self.client.get(reverse("purchasing:budget_version", args=[version.pk]))
        self.assertContains(response, 'value="1200.12"')
        self.assertNotContains(response, 'value="1200.1234567890"')
        allocation.refresh_from_db()
        self.assertEqual(allocation.amount, Decimal("1200.1234567890"))

    def test_budget_product_search_matches_code_or_label(self):
        self.manager.user_permissions.add(Permission.objects.get(codename="add_budgetproduct"))
        first = BudgetProduct.objects.create(code="MAT-01", label="Materiel")
        second = BudgetProduct.objects.create(code="SERV-02", label="Formation")
        url = reverse("purchasing:budget_products")
        for search, expected in (("mat-", [first]), ("  formation  ", [second]), ("missing", [])):
            response = self.client.get(url, {"q": search})
            self.assertEqual(list(response.context["products"]), expected)
            self.assertEqual(response.context["search"], search.strip())
        self.assertEqual(self.client.get(url).context["products"].count(), 3)

    def test_live_product_search_returns_only_results_and_filtered_export_link(self):
        self.manager.user_permissions.add(Permission.objects.get(codename="add_budgetproduct"))
        BudgetProduct.objects.create(code="LIVE-01", label="Live product")
        url = reverse("purchasing:budget_products")
        page = self.client.get(url)
        self.assertContains(page, 'id="budget-product-search"')
        self.assertNotContains(page, 'aria-label="Rechercher les produits"')
        response = self.client.get(url, {"q": "LIVE"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertContains(response, "LIVE-01")
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "q=LIVE")
        response = self.client.get(url, {}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.context["products"].count(), 2)

    def test_admin_unlocks_edits_and_relocks_published_allocations(self):
        from .flow import activate_envelope
        from budgeting.models import BudgetHistoryEvent
        version = self.create_version()
        url = reverse("purchasing:budget_version", args=[version.pk])
        self.client.post(url, self.line_data())
        activate_envelope(actor=self.manager, version_id=version.pk)
        version.refresh_from_db()
        publication = version.published_at
        before = BudgetHistoryEvent.objects.latest("pk")
        self.assertEqual(self.client.post(url, {"action": "unlock"}).status_code, 403)
        admin = get_user_model().objects.create_superuser("budget_editor")
        self.client.force_login(admin)
        self.assertContains(self.client.get(url), "Débloquer pour modification")
        self.assertRedirects(self.client.post(url, {"action": "unlock"}), url)
        version.refresh_from_db()
        self.assertIsNotNone(version.editing_unlocked_at)
        self.assertEqual(version.published_at, publication)
        self.assertEqual(version.envelope.active_version_id, version.pk)
        response = self.client.get(url)
        self.assertContains(response, "Enregistrer les lignes")
        self.assertNotContains(response, "Publier et activer cette version")
        payload = self.line_data("1500")
        payload.update({"allocations-INITIAL_FORMS": 1, "allocations-0-id": version.allocations.get().pk})
        self.client.force_login(self.manager)
        self.assertNotContains(self.client.get(url), "Enregistrer les lignes")
        self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.client.force_login(admin)
        self.assertRedirects(self.client.post(url, payload), url)
        self.assertEqual(version.allocations.get().amount, Decimal("1500"))
        before.refresh_from_db()
        self.assertEqual(Decimal(before.state["versions"][str(version.pk)]["rows"][0]["allocated"]), Decimal("1200"))
        self.assertRedirects(self.client.post(url, {"action": "lock"}), url)
        version.refresh_from_db()
        self.assertIsNone(version.editing_unlocked_at)
        self.assertIsNone(version.locked_at)
        self.assertEqual(version.published_at, publication)
        self.assertNotContains(self.client.get(url), "Enregistrer les lignes")
        self.client.post(url, {**payload, "allocations-0-amount": "10"})
        self.assertEqual(version.allocations.get().amount, Decimal("1500"))
        from budgeting.transfers import ensure_writable
        ensure_writable(version)

    def test_draft_unlock_and_deleted_version_refusal(self):
        from .flow import lock_envelope, unlock_envelope, delete_envelope_version
        from django.core.exceptions import PermissionDenied
        version = self.create_version()
        admin = get_user_model().objects.create_superuser("budget_unlocker")
        lock_envelope(actor=admin, version_id=version.pk)
        with self.assertRaises(PermissionDenied):
            unlock_envelope(actor=self.manager, version_id=version.pk)
        unlocked = unlock_envelope(actor=admin, version_id=version.pk)
        self.assertTrue(unlocked.allocations_editable)
        self.assertIsNone(unlocked.locked_at)
        delete_envelope_version(actor=admin, version_id=version.pk)
        with self.assertRaises(ValidationError):
            unlock_envelope(actor=admin, version_id=version.pk)

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

    def test_empty_version_is_saved_and_can_be_reopened(self):
        version = self.create_version("À compléter")
        self.assertFalse(version.allocations.exists())
        self.assertContains(self.client.get(reverse("purchasing:allocation_versions")), "À compléter")
        url = reverse("purchasing:budget_version", args=[version.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(self.client.post(url, self.line_data()), url)
        self.assertEqual(version.allocations.get().amount, Decimal("1200"))

    def test_version_name_is_unique_within_the_year(self):
        version = self.create_version("AJ2")
        for label in ("AJ2", "aj2", "  AJ2  "):
            response = self.client.post(self.index, {"year": 2026, "label": label})
            self.assertEqual(response.status_code, 200)
            self.assertIn("label", response.context["form"].errors)
        self.assertEqual(EnvelopeVersion.objects.count(), 1)
        response = self.client.post(self.index, {"year": 2027, "label": "AJ2"})
        self.assertEqual(response.status_code, 302)
        for label in ("AJ2", "aj2", " AJ2 "):
            with self.assertRaises(IntegrityError), transaction.atomic():
                EnvelopeVersion.objects.create(envelope=version.envelope, label=label)

    def test_delete_draft_preserves_history_and_requires_confirmation(self):
        from budgeting.models import BudgetHistoryEvent
        version = self.create_version("À supprimer")
        detail = reverse("purchasing:budget_version", args=[version.pk])
        self.client.post(detail, self.line_data())
        delete_url = reverse("purchasing:budget_version_delete", args=[version.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 403)
        admin = get_user_model().objects.create_superuser("admin_delete", password="test")
        self.client.force_login(admin)
        response = self.client.get(delete_url)
        self.assertContains(response, "Confirmer la suppression")
        version.refresh_from_db()
        self.assertIsNone(version.deleted_at)
        self.assertRedirects(self.client.post(delete_url), reverse("purchasing:allocation_versions"))
        version.refresh_from_db()
        self.assertIsNotNone(version.deleted_at)
        self.assertEqual(version.allocations.count(), 1)
        self.assertNotContains(self.client.get(reverse("purchasing:allocation_versions")), version.label)
        self.assertEqual(self.client.get(detail).status_code, 404)
        response = self.client.get(reverse("purchasing:budget_history"), {"version": version.pk})
        self.assertEqual(response.context["state"]["status"], "Supprimée")
        self.assertEqual(BudgetHistoryEvent.objects.latest("pk").actor, "admin_delete")
        self.assertEqual(self.client.post(delete_url).status_code, 404)

    def test_delete_empty_draft_and_refuse_published_or_locked_versions(self):
        from purchasing.flow import lock_envelope, activate_envelope, delete_envelope_version
        empty = self.create_version("Vide")
        published = self.create_version("Publiée")
        self.client.post(reverse("purchasing:budget_version", args=[published.pk]), self.line_data())
        locked = self.create_version("Bloquée")
        admin = get_user_model().objects.create_superuser("admin_delete", password="test")
        activate_envelope(actor=admin, version_id=published.pk)
        lock_envelope(actor=admin, version_id=locked.pk)
        self.client.force_login(admin)
        for version in (published, locked):
            response = self.client.post(reverse("purchasing:budget_version_delete", args=[version.pk]))
            self.assertEqual(response.status_code, 200)
            version.refresh_from_db()
            self.assertIsNone(version.deleted_at)
        delete_envelope_version(actor=admin, version_id=empty.pk)
        with self.assertRaises(ValidationError):
            activate_envelope(actor=admin, version_id=empty.pk)
        with self.assertRaises(ValidationError):
            Allocation.objects.create(version=empty, cost_center=self.cdf, funding=self.funding, budget_product=self.product, amount=1)

    def test_only_superuser_can_lock_an_empty_version(self):
        version = self.create_version()
        url = reverse("purchasing:budget_version", args=[version.pk])
        self.assertEqual(self.client.post(url, {"action": "lock"}).status_code, 403)
        admin = get_user_model().objects.create_superuser("admin_lock", password="test")
        self.client.force_login(admin)
        self.assertRedirects(self.client.post(url, {"action": "lock"}), url)
        version.refresh_from_db()
        self.assertIsNotNone(version.locked_at)
        self.assertFalse(version.allocations.exists())
        self.assertContains(self.client.get(url), "Version bloquée")
        self.assertContains(self.client.get(reverse("purchasing:allocation_versions")), "Bloquée")
        self.assertNotContains(self.client.get(url), "Enregistrer les lignes")
        self.client.post(url, self.line_data())
        self.assertFalse(version.allocations.exists())
        from budgeting.models import BudgetHistoryEvent
        event = BudgetHistoryEvent.objects.latest("pk")
        self.assertEqual(event.state["versions"][str(version.pk)]["status"], "Bloquée")
        self.assertEqual(event.actor, "admin_lock")

    def test_locked_version_rejects_allocation_and_version_writes(self):
        from purchasing.flow import lock_envelope, activate_envelope
        version = self.create_version()
        self.client.post(reverse("purchasing:budget_version", args=[version.pk]), self.line_data())
        allocation = version.allocations.get()
        stale_version = EnvelopeVersion.objects.get(pk=version.pk)
        admin = get_user_model().objects.create_superuser("admin_lock", password="test")
        lock_envelope(actor=admin, version_id=version.pk)
        allocation.amount = 1
        with self.assertRaises(ValidationError):
            allocation.save()
        with self.assertRaises(ValidationError):
            allocation.delete()
        with self.assertRaises(ValidationError):
            Allocation.objects.create(version=version, cost_center=self.cdf, funding=self.funding, budget_product=self.product, amount=1)
        with self.assertRaises(ValidationError):
            stale_version.save()
        with self.assertRaises(ValidationError):
            stale_version.delete()
        with self.assertRaises(ValidationError):
            activate_envelope(actor=admin, version_id=version.pk)
        self.assertEqual(Allocation.objects.get(pk=allocation.pk).amount, Decimal("1200"))

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
