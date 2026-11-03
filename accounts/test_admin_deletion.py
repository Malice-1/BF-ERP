from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.admin_deletion import delete_as_superuser
from accounts.models import Role
from purchasing import test_flow as fixtures
from purchasing.models import Allocation, ApprovalRule, BudgetEntry, EnvelopeVersion, PurchaseOrder
from workflow.models import ActivityLog


class SystemDeletionTests(TestCase):
    setUp = fixtures.PurchaseFlowTests.setUp
    grant = fixtures.PurchaseFlowTests.grant
    budget = fixtures.PurchaseFlowTests.budget
    draft = fixtures.PurchaseFlowTests.draft
    submit = fixtures.PurchaseFlowTests.submit
    act = fixtures.PurchaseFlowTests.act

    def test_role_has_visible_delete_link_and_members_survive(self):
        role = Role.objects.create(code="DELETE", label="Role to remove")
        self.other.roles.add(role)
        self.client.force_login(self.admin)
        url = reverse("admin:accounts_role_delete", args=[role.pk])
        self.assertContains(self.client.get(reverse("admin:accounts_role_changelist")), url)
        before = ActivityLog.objects.count()
        self.assertContains(self.client.get(url), "Suppression de maintenance")
        self.assertEqual(ActivityLog.objects.count(), before)
        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Role.objects.filter(pk=role.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.other.pk).exists())
        self.assertFalse(self.other.roles.exists())
        self.assertTrue(ActivityLog.objects.filter(action="maintenance.deleted",
                        object_type="accounts.role", actor_identifier=str(self.admin.pk)).exists())

    def test_published_budget_deletion_previews_required_dependents(self):
        self.submit()
        self.act(self.first)
        self.act(self.second)
        self.client.force_login(self.admin)
        url = reverse("admin:budgeting_envelopeversion_delete", args=[self.version.pk])
        response = self.client.get(url)
        self.assertContains(response, "Supprimer")
        self.assertEqual(response.context["protected"], [])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 302)
        self.assertFalse(EnvelopeVersion.objects.filter(pk=self.version.pk).exists())
        self.assertFalse(Allocation.objects.exists())
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertFalse(BudgetEntry.objects.exists())
        self.envelope.refresh_from_db()
        self.assertIsNone(self.envelope.active_version_id)
        self.assertTrue(ActivityLog.objects.filter(action="maintenance.deleted", object_type="purchasing.purchaseorder").exists())

    def test_all_registered_business_tables_have_superuser_delete(self):
        from django.test import RequestFactory
        request = RequestFactory().get("/admin/")
        request.user = self.admin
        for model, model_admin in admin.site._registry.items():
            if model._meta.app_label not in {"accounts", "budgeting", "suppliers", "purchasing", "workflow"}:
                continue
            if model is ActivityLog:
                self.assertFalse(model_admin.has_delete_permission(request))
                continue
            self.assertTrue(model_admin.has_delete_permission(request), model._meta.label)
            self.assertIn("system_delete_link", model_admin.get_list_display(request))

    def test_bulk_role_deletion_and_no_bypass_for_non_superuser(self):
        roles = [Role.objects.create(code=f"R{i}", label=f"Role {i}") for i in range(2)]
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            delete_as_superuser(Role.objects.all(), self.other)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:accounts_role_changelist"), {
            "action": "delete_selected", "_selected_action": [role.pk for role in roles], "post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Role.objects.exists())

    def test_journal_cannot_be_targeted_by_service(self):
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            delete_as_superuser(ActivityLog.objects.all(), self.admin)

    def test_deleting_a_step_stops_cycle_and_releases_remaining_budget(self):
        from purchasing.models import ApprovalStep, Submission
        self.submit()
        step = ApprovalStep.objects.filter(level=1).first()
        self.client.force_login(self.admin)
        url = reverse("admin:purchasing_approvalstep_delete", args=[step.pk])
        self.assertContains(self.client.get(url), "libérer ses réservations")
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 302)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "CORRECTION")
        self.assertFalse(Submission.objects.get().active)
        self.assertEqual(BudgetEntry.objects.get().state, "released")
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_deleting_used_role_does_not_broaden_rule_or_approval(self):
        from purchasing import flow
        from purchasing.exceptions import PurchaseRequestError
        from purchasing.models import ApprovalStep, WorkflowVersion
        role = Role.objects.create(code="VALID", label="Approvers")
        self.first.roles.add(role)
        config = WorkflowVersion.objects.create(label="Role circuit")
        rule = ApprovalRule.objects.create(version=config, label="Role rule", function=self.function1,
                                           role=role, level=1)
        flow.activate_workflow(actor=self.admin, version_id=config.pk)
        self.submit()
        delete_as_superuser(Role.objects.filter(pk=role.pk), self.admin)
        step = ApprovalStep.objects.get()
        self.assertFalse(step.candidates.exists())
        self.assertIsNone(flow.authority(self.first, step))
        new_purchase = self.draft()
        with self.assertRaises(PurchaseRequestError):
            self.submit(new_purchase)
        rule.refresh_from_db()
        self.assertTrue(rule.named_user_reference.startswith("[référence supprimée:"))

    def test_each_populated_business_table_can_be_deleted_without_orphans(self):
        self.submit()
        self.act(self.first)
        self.act(self.second)
        class RestoreFixture(Exception):
            pass
        for model in admin.site._registry:
            if model._meta.app_label not in {"accounts", "budgeting", "suppliers", "purchasing", "workflow"} or model is ActivityLog:
                continue
            obj = model._base_manager.first()
            if obj is None:
                continue
            with self.subTest(model=model._meta.label):
                try:
                    with transaction.atomic():
                        delete_as_superuser(model._base_manager.filter(pk=obj.pk), self.admin)
                        self.assertFalse(model._base_manager.filter(pk=obj.pk).exists())
                        connection.check_constraints()
                        raise RestoreFixture
                except RestoreFixture:
                    pass

    def test_postgres_history_guards_remain_enabled_outside_deletion(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL guard")
        self.client.force_login(self.admin)
        role = Role.objects.create(code="TEMP", label="Temporary")
        self.client.post(reverse("admin:accounts_role_delete", args=[role.pk]), {"post": "yes"})
        with self.assertRaises(DatabaseError), transaction.atomic():
            Allocation.objects.all().update(amount=1)
        with self.assertRaises(DatabaseError), transaction.atomic():
            ActivityLog.objects.all().delete()
