from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class ValidationSchemesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("schema-reader")
        self.admin = get_user_model().objects.create_superuser("schema-admin")
        self.url = reverse("purchasing:validation_schemes")

    def test_requires_login(self):
        self.assertRedirects(self.client.get(self.url), reverse("login") + "?next=" + self.url)

    def test_admin_can_read_both_fixed_schemes_in_configuration(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.context["nav_section"], "configuration")
        self.assertContains(response, 'id="schema-da"')
        self.assertContains(response, 'id="schema-transfert"')
        self.assertContains(response, "Responsable du CDF source")
        self.assertContains(response, "Responsable du CDF destination")
        self.assertContains(response, "Retour pour correction")
        self.assertContains(response, "Annulation après approbation")
        self.assertContains(response, reverse("purchasing:configuration"))
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_scheme_link_is_only_in_admin_configuration(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("my_validations"))
        self.assertNotContains(response, 'href="' + self.url + '"')
        self.assertContains(self.client.get(reverse("purchasing:configuration")), 'href="' + self.url + '"')

    def test_non_admin_cannot_read_even_with_configuration_permissions(self):
        from django.contrib.auth.models import Permission
        self.user.user_permissions.add(Permission.objects.get(codename="manage_cost_center_managers"))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertNotContains(self.client.get(reverse("purchasing:configuration")), self.url)
        self.user.is_staff = True
        self.user.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
