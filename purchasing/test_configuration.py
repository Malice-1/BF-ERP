from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


class ConfigurationGroupingTests(TestCase):
    def test_django_admin_groups_workflow_models_and_application_links(self):
        user = get_user_model().objects.create_superuser("django_config_admin", password="test")
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Responsables et validations")
        html = response.content.decode()
        group = html.split('class="app-workflow-settings module', 1)[1].split('</table>', 1)[0]
        for name in ("admin:accounts_role_changelist", "admin:budgeting_support_changelist",
                     "admin:budgeting_costcenter_changelist", "entity_managers"):
            self.assertIn(reverse(name), group)
        self.assertNotIn('id="workflow-settings-validationfunction"', html)
        self.assertNotIn(reverse("authorizations"), group)
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertContains(response, "Responsables et validations")
        self.assertContains(response, reverse("entity_managers"))

    def test_django_admin_workflow_group_preserves_permissions(self):
        user = get_user_model().objects.create_user("django_roles_reader", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="view_role"))
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Responsables et validations")
        self.assertContains(response, reverse("admin:accounts_role_changelist"))
        for name in ("authorizations", "entity_managers"):
            self.assertNotContains(response, f'href="{reverse(name)}"')

    def test_workflow_settings_are_grouped_with_direct_links(self):
        user = get_user_model().objects.create_superuser("config_admin", password="test")
        self.client.force_login(user)
        response = self.client.get(reverse("purchasing:configuration"))
        groups = response.context["configuration_groups"]
        workflow = next(group for group in groups if group["id"] == "workflow-settings")
        self.assertEqual({link["url"] for link in workflow["links"]}, {
            reverse("admin:accounts_role_changelist"),
            reverse("admin:budgeting_costcenter_changelist"),
            reverse("admin:budgeting_support_changelist"),
            reverse("entity_managers"),
        })
        self.assertContains(response, 'id="workflow-settings"')

    def test_nonstaff_manager_only_sees_authorized_application_links(self):
        user = get_user_model().objects.create_user("config_manager")
        user.user_permissions.add(Permission.objects.get(codename="manage_cost_center_managers"))
        self.client.force_login(user)
        response = self.client.get(reverse("purchasing:configuration"))
        links = [link["url"] for group in response.context["configuration_groups"] for link in group["links"]]
        self.assertEqual(links, [reverse("entity_managers")])
        self.assertNotContains(response, "/admin/accounts/validationfunction/")
