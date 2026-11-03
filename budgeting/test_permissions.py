from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.permission_labels import localize_permissions
from purchasing.budget_views import MANAGER_PERMISSIONS


class BudgetPermissionTests(TestCase):
    def test_section_menus_follow_categories_and_survive_last_permission_removal(self):
        user = get_user_model().objects.create_user("section_access", is_staff=True)
        role = Role.objects.create(code="SECTION_ACCESS", label="Accès rubrique")
        user.roles.add(role)
        self.client.force_login(user)
        urls = {
            "purchases": reverse("purchasing:list"),
            "budget": reverse("purchasing:budget_home"),
            "configuration": reverse("purchasing:configuration"),
        }
        cases = (
            ("purchasing", "view_all_purchase_requests", "purchases"),
            ("budgeting", "view_costcenter", "budget"),
            ("accounts", "view_user", "configuration"),
        )
        for app, code, expected in cases:
            with self.subTest(category=app):
                role.permissions.set([Permission.objects.get(content_type__app_label=app, codename=code)])
                response = self.client.get(reverse("my_delegations"))
                for section, url in urls.items():
                    if section == expected:
                        self.assertContains(response, f'href="{url}"')
                    else:
                        self.assertNotContains(response, f'href="{url}"')
                role.permissions.clear()
                response = self.client.get(reverse("my_delegations"))
                for url in urls.values():
                    self.assertNotContains(response, f'href="{url}"')
                self.assertContains(response, 'id="my-validations"')
                self.assertContains(response, 'id="my-delegations"')
        self.assertRedirects(self.client.get(urls["purchases"]), reverse("my_validations"))
        self.assertEqual(self.client.get(urls["configuration"]).status_code, 403)

    def test_purchase_reader_cannot_access_budget_navigation_or_urls(self):
        user = get_user_model().objects.create_user("ctrl_da")
        user.user_permissions.add(Permission.objects.get(codename="view_all_purchase_requests"))
        self.client.force_login(user)
        response = self.client.get(reverse("purchasing:all_requests"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'href="{reverse("purchasing:budget_home")}"')
        for name in ("budget_home", "budgets", "budget_versions", "allocation_versions", "budget_products"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"purchasing:{name}")).status_code, 403)

    def test_budget_navigation_follows_actual_permissions_including_roles(self):
        user = get_user_model().objects.create_user("budget_access")
        role = Role.objects.create(code="BUDGET_ACCESS", label="Accès budget")
        user.roles.add(role)
        self.client.force_login(user)
        home = reverse("purchasing:budget_home")
        self.assertEqual(self.client.get(home).status_code, 403)
        for permissions in (
            *((f"budgeting.{code}",) for code in Permission.objects.filter(
                content_type__app_label="budgeting").values_list("codename", flat=True)),
            MANAGER_PERMISSIONS,
        ):
            with self.subTest(permissions=permissions):
                role.permissions.set([
                    Permission.objects.get(content_type__app_label=app, codename=code)
                    for app, code in (p.split(".") for p in permissions)
                ])
                self.assertContains(self.client.get(home), f'href="{home}"')
        role.permissions.clear()
        self.assertEqual(self.client.get(home).status_code, 403)
        user.user_permissions.add(Permission.objects.get(
            content_type__app_label="budgeting", codename="view_costcenter"))
        self.assertContains(self.client.get(home), f'href="{home}"')
        # L'accès à l'onglet n'accorde pas les permissions de ses actions.
        self.assertEqual(self.client.get(reverse("purchasing:budget_versions")).status_code, 403)
        self.assertEqual(self.client.get(reverse("purchasing:budgets")).status_code, 403)
        user.user_permissions.clear()
        self.assertEqual(self.client.get(home).status_code, 403)

    def test_detailed_product_grants_move_to_purchases_without_duplicate_or_data_loss(self):
        from budgeting.models import BudgetProduct, DetailedProduct
        product = BudgetProduct.objects.create(code="BI", label="BI")
        detail = DetailedProduct.objects.create(code="DETAIL", label="Détail", budget_product=product)
        user = get_user_model().objects.create_user("catalogue")
        group = Group.objects.create(name="Catalogue")
        role = Role.objects.create(code="CATALOGUE", label="Catalogue")
        user.roles.add(role)
        user.groups.add(group)
        old_ct = ContentType.objects.get(app_label="budgeting", model="detailedproduct")
        for action in ("add", "change", "view", "delete"):
            old = Permission.objects.create(content_type=old_ct, codename=f"{action}_detailedproduct", name="Old")
            for relation in (user.user_permissions, group.permissions, role.permissions):
                relation.add(old)
        import_module("purchasing.migrations.0014_move_detailed_product_permissions").transfer(
            apps, SimpleNamespace(connection=connection))
        create_permissions(apps.get_app_config("budgeting"), verbosity=0)
        create_permissions(apps.get_app_config("purchasing"), verbosity=0)
        for action in ("add", "change", "view", "delete"):
            new = Permission.objects.get(content_type__app_label="purchasing", codename=f"{action}_detailedproduct")
            self.assertIn(new, user.user_permissions.all())
            self.assertIn(new, group.permissions.all())
            self.assertIn(new, role.permissions.all())
        self.assertFalse(Permission.objects.filter(content_type=old_ct).exists())
        self.assertEqual(Permission.objects.get(codename="add_budgetproduct").content_type.app_label, "budgeting")
        detail.refresh_from_db()
        self.assertEqual(detail.budget_product_id, product.pk)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("purchasing:detailed_products")).status_code, 200)
        for relation in (user.user_permissions, group.permissions, role.permissions):
            relation.clear()
        self.assertEqual(self.client.get(reverse("purchasing:detailed_products")).status_code, 403)

    def test_budget_permissions_have_one_namespace_and_french_labels(self):
        for permission in MANAGER_PERMISSIONS:
            app, code = permission.split(".")
            self.assertEqual(app, "budgeting")
            row = Permission.objects.get(content_type__app_label=app, codename=code)
            self.assertTrue(row.name.startswith(("Ajouter :", "Modifier :", "Supprimer :")))
            self.assertFalse(Permission.objects.filter(content_type__app_label="purchasing", codename=code).exists())
        self.assertFalse(Permission.objects.filter(content_type__app_label="budgeting",
                                                 content_type__model__in=["budget", "budgetline"]).exists())
        Permission.objects.filter(pk=row.pk).update(name="Can add allocation")
        localize_permissions()
        row.refresh_from_db()
        self.assertFalse(row.name.startswith("Can "))

    def test_transfer_preserves_individual_group_role_and_legacy_grants(self):
        user = get_user_model().objects.create_user("old_grants")
        group = Group.objects.create(name="Legacy")
        role = Role.objects.create(code="LEGACY", label="Legacy")
        user.roles.add(role)
        user.groups.add(group)
        old_ct, _ = ContentType.objects.get_or_create(app_label="purchasing", model="envelopeversion")
        old = Permission.objects.create(content_type=old_ct, codename="change_envelopeversion", name="Can change")
        user.user_permissions.add(old)
        role.permissions.add(old)
        group.permissions.add(old)
        legacy_ct = ContentType.objects.get(app_label="budgeting", model="budgetline")
        legacy = Permission.objects.create(content_type=legacy_ct, codename="add_budgetline", name="Can add")
        role.permissions.add(legacy)
        financial = Permission.objects.get(codename="view_purchase_financial")
        role.permissions.add(financial)
        module = import_module("budgeting.migrations.0012_unify_budget_permissions")
        module.transfer(apps, SimpleNamespace(connection=connection))
        replacement = Permission.objects.get(content_type__app_label="budgeting", codename="change_envelopeversion")
        self.assertIn(replacement, user.user_permissions.all())
        self.assertIn(replacement, group.permissions.all())
        self.assertIn(replacement, role.permissions.all())
        self.assertFalse(Permission.objects.filter(pk=old.pk).exists())
        user = get_user_model().objects.get(pk=user.pk)
        self.assertTrue(user.has_perm("budgeting.add_allocation"))
        self.assertTrue(user.has_perm("budgeting.view_budget_balances"))
        self.assertTrue(user.has_perm("purchasing.view_purchase_financial"))
        # A subsequent migrate must not reintroduce the retired duplicates.
        create_permissions(apps.get_app_config("purchasing"), verbosity=0)
        create_permissions(apps.get_app_config("budgeting"), verbosity=0)
        self.assertFalse(Permission.objects.filter(content_type__app_label="purchasing", codename="change_envelopeversion").exists())
        self.assertFalse(Permission.objects.filter(content_type__model="budgetline").exists())

    def test_permission_choices_are_in_french_for_role_and_user(self):
        admin = get_user_model().objects.create_superuser("admin", "admin@example.test", "test")
        self.client.force_login(admin)
        for name in ("admin:accounts_role_add", "admin:accounts_user_change"):
            args = [admin.pk] if name.endswith("change") else None
            response = self.client.get(reverse(name, args=args))
            self.assertContains(response, "Budgets | version budgétaire | Ajouter : version budgétaire")
            self.assertNotContains(response, "Can add")
            self.assertNotContains(response, "Can change")
            self.assertNotContains(response, "Can delete")

    def test_budget_balance_reading_does_not_require_purchase_financial_access(self):
        user = get_user_model().objects.create_user("budget_reader")
        user.user_permissions.add(Permission.objects.get(codename="view_budget_balances"))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("purchasing:budgets")).status_code, 200)
        self.assertFalse(get_user_model().objects.get(pk=user.pk).has_perm("purchasing.view_purchase_financial"))
        user.user_permissions.clear()
        self.assertEqual(self.client.get(reverse("purchasing:budgets")).status_code, 403)
