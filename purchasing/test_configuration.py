from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


class ConfigurationGroupingTests(TestCase):
    def test_subprojects_and_sections_can_be_configured_with_reference_permissions(self):
        from budgeting.models import Section, Subproject

        user = get_user_model().objects.create_user("reference_editor", is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="budgeting",
            codename__in=("view_subproject", "add_subproject", "change_subproject", "add_section")))
        self.client.force_login(user)

        configuration = self.client.get(reverse("purchasing:configuration"))
        self.assertContains(configuration, reverse("admin:budgeting_subproject_changelist"))
        self.assertContains(configuration, reverse("admin:budgeting_section_add"))
        self.assertNotContains(configuration, reverse("admin:budgeting_funding_changelist"))

        payload = {"code": "001", "label": "Activité pilote"}
        self.assertEqual(self.client.post(reverse("admin:budgeting_subproject_add"), payload).status_code, 302)
        self.assertEqual(self.client.post(reverse("admin:budgeting_section_add"), payload).status_code, 302)
        self.assertEqual(Section.objects.get().code, "001")
        project = Subproject.objects.get(code="001")
        change = reverse("admin:budgeting_subproject_change", args=[project.pk])
        self.assertEqual(self.client.post(change, {**payload, "label": "Activité actualisée"}).status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.label, "Activité actualisée")
        self.assertEqual(self.client.get(reverse("admin:budgeting_section_changelist")).status_code, 403)

    def test_django_admin_groups_workflow_models_and_application_links(self):
        user = get_user_model().objects.create_superuser("django_config_admin", password="test")
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Responsables et validations")
        html = response.content.decode()
        group = html.split('class="app-workflow-settings module', 1)[1].split('</table>', 1)[0]
        for name in ("admin:accounts_role_changelist", "admin:budgeting_support_changelist",
                     "admin:budgeting_costcenter_changelist"):
            self.assertIn(reverse(name), group)
        self.assertNotIn('id="workflow-settings-validationfunction"', html)
        self.assertNotIn(reverse("authorizations"), group)
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertContains(response, "Responsables et validations")
        self.assertNotContains(response, f'href="{reverse("entity_managers")}"')

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
        })
        self.assertContains(response, 'id="workflow-settings"')

    def test_nonstaff_manager_only_sees_authorized_application_links(self):
        user = get_user_model().objects.create_user("config_manager")
        user.user_permissions.add(Permission.objects.get(codename="manage_cost_center_managers"))
        self.client.force_login(user)
        response = self.client.get(reverse("purchasing:configuration"))
        links = [link["url"] for group in response.context["configuration_groups"] for link in group["links"]]
        self.assertEqual(links, [])
        self.assertNotContains(response, "/admin/accounts/validationfunction/")
