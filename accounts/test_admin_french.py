from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Authorization, ValidationFunction
from purchasing.models import ApprovalStep, PurchaseNotice, PurchaseOrder
from workflow.models import ActivityLog


class FrenchAdministrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin_fr", "admin@example.test", "test")
        self.client.force_login(self.user)

    def test_index_and_creation_forms_are_french(self):
        response = self.client.get(reverse("admin:index"))
        for label in ("Habilitations", "Fournisseurs", "Bons de commande", "Étapes de validation"):
            self.assertContains(response, label)
        for english in ("Validation functions", "Authorizations", "Suppliers", "Purchase orders", "Approval steps"):
            self.assertNotContains(response, english)
        response = self.client.get(reverse("admin:suppliers_supplier_add"))
        for label in ("Nom", "Numéro de TVA"):
            self.assertContains(response, label)
        self.assertFalse(admin.site.is_registered(ValidationFunction))

    def test_readonly_fields_states_and_object_names_are_french(self):
        notice = PurchaseNotice.objects.create(key="fr", message="Test")
        response = self.client.get(reverse("admin:purchasing_purchasenotice_change", args=[notice.pk]))
        self.assertContains(response, "État d’envoi du courriel")
        self.assertContains(response, "En attente")
        event = ActivityLog.objects.create(actor_identifier="1", actor_username="test", action="created",
            object_type="test", object_identifier="1")
        response = self.client.get(reverse("admin:workflow_activitylog_changelist"))
        self.assertContains(response, "Création")
        for model in (Authorization, ApprovalStep, PurchaseOrder):
            self.assertNotIn(" object ", str(model(pk=1)))

    def test_registered_business_fields_have_explicit_labels(self):
        for model in admin.site._registry:
            if model._meta.app_label not in {"accounts", "budgeting", "purchasing", "suppliers", "workflow"}:
                continue
            for field in (*model._meta.local_fields, *model._meta.local_many_to_many):
                if "_" in field.name:
                    with self.subTest(model=model.__name__, field=field.name):
                        self.assertNotEqual(str(field.verbose_name), field.name.replace("_", " "))
