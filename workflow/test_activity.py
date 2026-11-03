from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import DatabaseError, transaction
from django.test import TestCase
from django.urls import reverse

from purchasing import test_flow as fixtures
from purchasing import flow
from purchasing.models import ApprovalRule, ApprovalStep, BudgetEntry, PurchaseOrder
from .models import ActivityLog


class IndependentHistoryTests(TestCase):
    setUp = fixtures.PurchaseFlowTests.setUp
    grant = fixtures.PurchaseFlowTests.grant
    budget = fixtures.PurchaseFlowTests.budget
    draft = fixtures.PurchaseFlowTests.draft
    submit = fixtures.PurchaseFlowTests.submit
    act = fixtures.PurchaseFlowTests.act

    def test_admin_deletes_requester_and_approvers_without_losing_order_or_log(self):
        self.submit()
        self.act(self.first)
        self.act(self.second)
        owner_id, first_id = self.owner.pk, self.first.pk
        existing_logs = set(ActivityLog.objects.filter(actor_identifier=str(owner_id)).values_list("pk", flat=True))
        self.assertTrue(existing_logs)
        self.client.force_login(self.admin)
        for user in (self.owner, self.first, self.second):
            response = self.client.post(reverse("admin:accounts_user_delete", args=[user.pk]), {"post": "yes"})
            self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=owner_id).exists())
        self.purchase.refresh_from_db()
        self.assertIsNone(self.purchase.created_by_id)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(BudgetEntry.objects.get().state, "committed")
        self.assertTrue(existing_logs.issubset(set(ActivityLog.objects.values_list("pk", flat=True))))
        self.assertEqual(ActivityLog.objects.filter(actor_identifier=str(owner_id)).first().actor_username, "owner")
        self.assertFalse(ApprovalStep.objects.filter(approved_by_id=first_id).exists())
        flow.refresh_submission(self.purchase.submissions.get().pk)
        response = self.client.get(reverse("admin:workflow_activitylog_changelist"), {"actor": owner_id})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(row.actor_identifier == str(owner_id) for row in response.context["cl"].queryset))
        response = self.client.get(reverse("purchasing:detail", args=[self.purchase.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(event.actor_display == "owner" for event in response.context["events"]))

    def test_deleted_named_approver_never_broadens_rule(self):
        # Fixture configuration is already published; create a fresh named circuit.
        from purchasing.models import WorkflowVersion
        config = WorkflowVersion.objects.create(label="Named")
        rule = ApprovalRule.objects.create(version=config, label="Named", function=self.function1,
                                           level=1, named_user=self.first)
        flow.activate_workflow(actor=self.admin, version_id=config.pk)
        self.first.delete()
        rule.refresh_from_db()
        self.assertIsNone(rule.named_user_id)
        self.assertIn("first", rule.named_user_reference)
        self.submit()
        step = ApprovalStep.objects.get(snapshot__submission__purchase_request=self.purchase)
        self.assertEqual(step.state, "unassigned")
        self.assertFalse(step.candidates.exists())
        # Copying a circuit must not silently turn the deleted named assignment
        # into an assignment to everyone authorized for the function.
        copied = WorkflowVersion.objects.create(label="Copy after deletion")
        rule.pk = None
        rule.version = copied
        rule.save()
        self.assertIn("first", rule.named_user_reference)

    def test_deleted_requester_does_not_break_pending_workflow(self):
        self.submit()
        self.owner.delete()
        self.act(self.first)
        self.act(self.second)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_deleted_publisher_and_pending_candidate_can_be_removed(self):
        self.submit()
        self.admin.delete()
        self.first.delete()
        flow.refresh_submission(self.purchase.submissions.get().pk)
        self.assertEqual(ApprovalStep.objects.get(level=1).state, "unassigned")

    def test_journal_is_read_only_and_no_secrets_are_logged(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("admin:accounts_user_change", args=[self.other.pk]), {})
        logs = ActivityLog.objects.filter(object_type="accounts.user")
        self.assertTrue(logs.exists())
        self.assertNotIn('"password"', str(list(logs.values_list("details", flat=True))))
        row = ActivityLog.objects.first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            ActivityLog.objects.filter(pk=row.pk).update(actor_username="rewritten")
        with self.assertRaises(DatabaseError), transaction.atomic():
            ActivityLog.objects.filter(pk=row.pk).delete()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("admin:workflow_activitylog_changelist")).status_code, 302)

    def test_user_deletion_requires_superuser_even_with_standard_permission(self):
        self.other.is_staff = True
        self.other.save()
        self.other.user_permissions.add(Permission.objects.get(codename="delete_user"))
        self.client.force_login(self.other)
        response = self.client.post(reverse("admin:accounts_user_delete", args=[self.owner.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=self.owner.pk).exists())

    def test_failed_transaction_does_not_leave_phantom_log(self):
        before = ActivityLog.objects.count()
        try:
            with transaction.atomic():
                get_user_model().objects.create_user("rolled_back")
                raise ValueError
        except ValueError:
            pass
        self.assertEqual(ActivityLog.objects.count(), before)

    def test_deleted_manager_can_be_replaced_and_notifications_become_obsolete(self):
        from datetime import timedelta
        from django.core.management import call_command
        from django.utils import timezone
        from budgeting.services import assign_cost_center_manager
        from purchasing.models import PurchaseNotice
        from io import StringIO
        begin = timezone.now() - timedelta(days=1)
        assignment = assign_cost_center_manager(actor=self.admin, cost_center=self.cdf,
                                               user=self.first, valid_from=begin)
        self.submit()
        self.first.delete()
        assignment.refresh_from_db()
        self.assertIsNone(assignment.user_id)
        replacement = assign_cost_center_manager(actor=self.admin, cost_center=self.cdf,
                                                 user=self.other, valid_from=begin)
        self.assertEqual(replacement.user_id, self.other.pk)
        call_command("process_purchase_notifications", stdout=StringIO(), stderr=StringIO())
        self.assertFalse(PurchaseNotice.objects.filter(recipient__isnull=True, email_state="pending").exists())
