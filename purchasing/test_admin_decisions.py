from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from . import flow, test_flow as fixtures
from .exceptions import PurchaseRequestConflict, PurchaseRequestError
from .models import ApprovalStep, BudgetEntry, PurchaseOrder


class AdminDecisionTests(TestCase):
    setUp = fixtures.PurchaseFlowTests.setUp
    grant = fixtures.PurchaseFlowTests.grant
    budget = fixtures.PurchaseFlowTests.budget
    draft = fixtures.PurchaseFlowTests.draft
    submit = fixtures.PurchaseFlowTests.submit

    def decide(self, decision, actor=None, reason=""):
        self.purchase.refresh_from_db()
        step = ApprovalStep.objects.filter(snapshot__submission__purchase_request=self.purchase).first()
        return flow.decide(request_id=self.purchase.pk, actor=actor or self.admin,
            expected_revision=self.purchase.revision, step_id=step.pk, decision=decision, reason=reason)

    def test_admin_can_validate_unassigned_step_with_audit(self):
        self.cdf.managers.clear()
        self.submit()
        self.decide("approve")
        step = ApprovalStep.objects.get()
        self.assertEqual(step.approved_by, self.admin)
        self.assertTrue(step.evaluated_scope["admin_override"])
        self.assertTrue(self.purchase.audit_events.get(action="request.approve").payload["admin_override"])
        self.assertTrue(PurchaseOrder.objects.filter(purchase_request=self.purchase).exists())
        self.assertEqual(BudgetEntry.objects.get().state, "committed")

    def test_admin_can_approve_all_lines(self):
        self.purchase = self.draft(lines=2)
        self.submit()
        self.decide("approve_all")
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "ORDERED")
        steps = ApprovalStep.objects.filter(snapshot__submission__purchase_request=self.purchase)
        self.assertEqual(steps.count(), 2)
        self.assertEqual(steps.filter(state="approved", approved_by=self.admin).count(), 2)
        self.assertEqual(BudgetEntry.objects.filter(snapshot__submission__purchase_request=self.purchase, state="committed").count(), 2)

    def test_admin_correction_requires_reason_and_releases_budget(self):
        self.submit()
        with self.assertRaises(ValidationError):
            self.decide("correct", reason=" ")
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "SUBMITTED")
        self.decide("correct", reason="Corriger le montant")
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "CORRECTION")
        self.assertEqual(BudgetEntry.objects.get().state, "released")
        self.assertEqual(self.purchase.audit_events.get(action="request.correct").payload["reason"], "Corriger le montant")

    def test_admin_rejection_is_terminal(self):
        self.submit()
        self.decide("reject", reason="Achat refuse")
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "REJECTED")
        self.assertEqual(BudgetEntry.objects.get().state, "released")
        with self.assertRaises(PurchaseRequestError):
            self.decide("approve_all")

    def test_regular_validator_cannot_approve_all(self):
        self.submit()
        with self.assertRaises(PermissionDenied):
            self.decide("approve_all", actor=self.first)
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_stale_revision_cannot_validate(self):
        self.submit()
        step = ApprovalStep.objects.get()
        with self.assertRaises(PurchaseRequestConflict):
            flow.decide(request_id=self.purchase.pk, actor=self.admin, expected_revision=0,
                step_id=step.pk, decision="approve_all")
        step.refresh_from_db()
        self.assertEqual(step.state, "pending")

    def test_permission_allows_non_superuser_and_actions_on_timeline(self):
        self.submit()
        self.other.user_permissions.add(Permission.objects.get(codename="decide_any_purchaserequest"))
        self.client.force_login(self.other)
        detail = self.client.get(reverse("purchasing:detail", args=[self.purchase.pk]))
        self.assertContains(detail, 'data-purchase-decision')
        self.assertContains(detail, 'value="approve_all"')
        step = ApprovalStep.objects.get()
        self.purchase.refresh_from_db()
        response = self.client.post(reverse("purchasing:decision", args=[self.purchase.pk, step.pk]),
            {"decision": "approve_all", "expected_revision": self.purchase.revision}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        step.refresh_from_db()
        self.assertEqual(step.approved_by, self.other)
        self.assertNotContains(self.client.get(reverse("purchasing:detail", args=[self.purchase.pk])), 'data-purchase-decision')

    def test_actions_are_on_lines_and_da_but_not_timeline(self):
        self.purchase = self.draft(lines=2)
        self.submit()
        self.client.force_login(self.admin)
        url = reverse("purchasing:detail", args=[self.purchase.pk])
        response = self.client.get(url)
        html = response.content.decode()
        table, rest = html.split("</tbody></table>", 1)
        self.assertEqual(sum(step.state == "approved" for step in response.context["steps"]), 0)
        self.assertEqual(sum(step.is_current for step in response.context["steps"]), 2)
        self.assertEqual(html.count('aria-current="step"'), 2)
        self.assertEqual(table.count('value="approve"'), 2)
        self.assertNotIn('value="approve_all"', table)
        self.assertEqual(html.count('value="approve_all"'), 1)
        timeline = rest.split('id="purchase-workflow-title"', 1)[1].split('<h2>Historique</h2>', 1)[0]
        self.assertNotIn('data-purchase-decision', timeline)
        step = ApprovalStep.objects.filter(snapshot__submission__purchase_request=self.purchase).first()
        self.purchase.refresh_from_db()
        result = self.client.post(reverse("purchasing:decision", args=[self.purchase.pk, step.pk]),
            {"decision": "approve", "expected_revision": self.purchase.revision}, HTTP_ACCEPT="application/json")
        self.assertEqual(result.status_code, 200)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "SUBMITTED")
        steps = ApprovalStep.objects.filter(snapshot__submission__purchase_request=self.purchase)
        self.assertEqual(steps.filter(state="approved").count(), 1)
        self.assertEqual(steps.filter(state="pending").count(), 1)
        response = self.client.get(url)
        self.assertEqual(sum(step.state == "approved" for step in response.context["steps"]), 1)
        self.assertEqual(sum(step.is_current for step in response.context["steps"]), 1)
        html = response.content.decode()
        self.assertEqual(html.count('aria-current="step"'), 1)
        self.assertNotContains(response, 'class="purchase-validation-summary"')
        self.assertEqual(html.count('value="approve"'), 1)
        self.assertEqual(html.count('value="approve_all"'), 1)
