from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Funding, Support


class SupportConfigurationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("admin_support", password="test")
        self.user = get_user_model().objects.create_user("membre", first_name="Alex", last_name="Martin")
        self.support = Support.objects.create(code="RH", label="Ressources humaines")
        self.funding = Funding.objects.create(code="RH", label="Financement indépendant")
        self.client.force_login(self.admin)

    def test_support_managers_are_independent_from_funding_and_membership(self):
        response = self.client.post(reverse("admin:budgeting_support_change", args=[self.support.pk]), {
            "code": "RH", "label": "Ressources humaines", "managers": [self.user.pk], "_save": "Enregistrer"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.support.managers.all()), [self.user])
        self.assertFalse(self.funding.managers.exists())
        self.assertFalse(self.user.supports.exists())
        data = self.client.get(reverse("admin:budgeting_support_manager_choices"), {"term": "mart al"}).json()
        self.assertEqual(data["results"], [{"id": str(self.user.pk), "text": "Alex Martin (membre)"}])

    def test_user_fiche_records_multiple_supports_without_manager_rights(self):
        other = Support.objects.create(code="IT", label="Informatique")
        response = self.client.post(reverse("admin:accounts_user_change", args=[self.user.pk]), {
            "username": self.user.username, "first_name": "Alex", "last_name": "Martin",
            "is_active": "on", "date_joined_0": "2026-11-04", "date_joined_1": "10:00:00",
            "supports": [self.support.pk, other.pk], "_save": "Enregistrer"})
        self.assertEqual(response.status_code, 302)
        self.assertSetEqual(set(self.user.supports.all()), {self.support, other})
        self.assertFalse(self.user.managed_supports.exists())

    def test_shared_manager_configuration_edits_support_not_funding(self):
        response = self.client.post(reverse("entity_managers"), {
            "kind": "support", "entity_id": self.support.pk, "managers": [self.user.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.support.managers.all()), [self.user])
        self.assertFalse(self.funding.managers.exists())
