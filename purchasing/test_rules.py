from purchasing.test_helpers import record_legacy_workflow
"""Fixed validation routes replace configurable conditions and workflows."""
from decimal import Decimal
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from budgeting.models import CostCenter, Funding, BudgetProduct
from suppliers.models import Supplier
from . import flow
from .models import (DetailedProduct, AnnualEnvelope, EnvelopeVersion, Allocation,
                     WorkflowVersion, ApprovalRule, ApprovalStep, Submission, BudgetEntry, PurchaseOrder)
from .services import create_purchase_request, add_purchase_request_line


class FixedValidationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin")
        self.owner = User.objects.create_user("owner")
        self.first = User.objects.create_user("first")
        self.second = User.objects.create_user("second")
        self.source = CostCenter.objects.create(code="A", label="A")
        self.target = CostCenter.objects.create(code="B", label="B")
        self.source.managers.add(self.first)
        self.target.managers.add(self.second)
        self.funding = Funding.objects.create(code="F", label="F")
        self.product = BudgetProduct.objects.create(code="P", label="P")
        self.detail = DetailedProduct.objects.create(code="D", label="D", budget_product=self.product)
        supplier = Supplier.objects.create(code="S", name="Supplier")
        envelope = AnnualEnvelope.objects.create(year=timezone.localdate().year)
        self.budget = EnvelopeVersion.objects.create(envelope=envelope, label="Budget")
        for cdf in (self.source, self.target):
            Allocation.objects.create(version=self.budget, cost_center=cdf, funding=self.funding,
                                      budget_product=self.product, amount=1000)
        flow.activate_envelope(actor=self.admin, version_id=self.budget.pk)
        self.purchase = create_purchase_request(actor=self.owner, supplier=supplier)

    def add_line(self, cdf):
        self.purchase.refresh_from_db()
        return add_purchase_request_line(request_id=self.purchase.pk, actor=self.owner,
            expected_revision=self.purchase.revision, detailed_product=self.detail, cost_center=cdf,
            funding=self.funding, description="Line", quantity=1, unit_price=100, vat_rate=0)

    def submit(self):
        self.purchase.refresh_from_db()
        return flow.submit_purchase(request_id=self.purchase.pk, actor=self.owner,
                                    expected_revision=self.purchase.revision)

    def decide(self, step, actor, decision="approve", reason=""):
        self.purchase.refresh_from_db()
        return flow.decide(request_id=self.purchase.pk, actor=actor,
            expected_revision=self.purchase.revision, step_id=step.pk, decision=decision, reason=reason)

    def test_each_line_goes_only_to_its_cdf_manager_and_all_must_approve(self):
        first_line = self.add_line(self.source)
        second_line = self.add_line(self.target)
        self.submit()
        self.assertFalse(WorkflowVersion.objects.exists())
        self.assertIsNone(Submission.objects.get().workflow_id)
        first = ApprovalStep.objects.get(snapshot__original_line_id=first_line.pk)
        second = ApprovalStep.objects.get(snapshot__original_line_id=second_line.pk)
        self.assertEqual(ApprovalStep.objects.count(), 2)
        self.assertEqual((first.state, second.state), ("pending", "pending"))
        with self.assertRaises(PermissionDenied):
            self.decide(second, self.first)
        self.assertEqual(flow.pending_validation_count(self.first), 1)
        self.assertEqual(flow.pending_validation_count(self.second), 1)
        self.decide(second, self.second)
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertEqual(BudgetEntry.objects.filter(state="reserved").count(), 2)
        self.decide(first, self.first)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "ORDERED")
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(BudgetEntry.objects.filter(state="committed").count(), 2)
        for cdf in (self.source, self.target):
            self.assertEqual(flow.available(self.budget, cdf.pk, self.funding.pk, self.product.pk), Decimal(900))

    def test_same_cdf_still_requires_one_decision_per_line(self):
        self.add_line(self.source)
        self.add_line(self.source)
        self.submit()
        steps = list(ApprovalStep.objects.order_by("pk"))
        self.decide(steps[0], self.first)
        steps[1].refresh_from_db()
        self.assertEqual(steps[1].state, "pending")
        self.assertIsNone(steps[1].evidence_id)
        self.assertFalse(PurchaseOrder.objects.exists())
        self.decide(steps[1], self.first)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_any_active_manager_of_the_line_cdf_can_validate(self):
        self.source.managers.add(self.second)
        self.add_line(self.source)
        self.submit()
        step = ApprovalStep.objects.get()
        self.assertCountEqual(step.candidates.all(), [self.first, self.second])
        self.decide(step, self.second)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        event = self.purchase.audit_events.get(action="request.approve")
        self.assertIsNone(event.payload["authorization"])
        self.assertEqual(event.payload["represented_user"], self.second.pk)

    def test_missing_manager_blocks_its_line_without_blocking_others(self):
        self.target.managers.clear()
        first_line = self.add_line(self.source)
        second_line = self.add_line(self.target)
        self.submit()
        first = ApprovalStep.objects.get(snapshot__original_line_id=first_line.pk)
        second = ApprovalStep.objects.get(snapshot__original_line_id=second_line.pk)
        self.assertEqual(second.state, "unassigned")
        self.decide(first, self.first)
        second.refresh_from_db()
        self.assertEqual(second.state, "unassigned")
        self.assertFalse(PurchaseOrder.objects.exists())
        self.target.managers.add(self.second)
        self.assertEqual(flow.pending_validation_count(self.second), 1)
        self.decide(second, self.second)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_revoked_or_inactive_manager_cannot_validate(self):
        self.add_line(self.source)
        self.submit()
        step = ApprovalStep.objects.get()
        self.source.managers.set([self.second])
        with self.assertRaises(PermissionDenied):
            self.decide(step, self.first)
        self.second.is_active = False
        self.second.save()
        flow.refresh_submission(step.snapshot.submission_id)
        step.refresh_from_db()
        self.assertEqual(step.state, "unassigned")
        self.second.is_active = True
        self.second.save()
        self.decide(step, self.second)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_old_automatic_configuration_is_ignored_for_new_submissions(self):
        version = WorkflowVersion.objects.create(label="Old auto", rule_based=True)
        ApprovalRule.objects.create(version=version, label="Auto", automatic=True, conditions={"all": []})
        record_legacy_workflow(version)
        self.add_line(self.source)
        self.submit()
        step = ApprovalStep.objects.get()
        self.assertEqual(step.manager_source, "cdf")
        self.assertFalse(step.rule_snapshot["automatic"])
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_support_is_not_required_and_does_not_add_validation(self):
        self.add_line(self.source)
        self.submit()
        self.assertIsNone(self.purchase.support_id)
        self.assertEqual(ApprovalStep.objects.count(), 1)
        self.decide(ApprovalStep.objects.get(), self.first)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_rejection_of_one_line_releases_the_whole_request(self):
        self.add_line(self.source)
        self.add_line(self.target)
        self.submit()
        self.decide(ApprovalStep.objects.get(snapshot__cost_center=self.source), self.first)
        self.decide(ApprovalStep.objects.get(snapshot__cost_center=self.target), self.second,
                    decision="reject", reason="Refus")
        self.assertEqual(BudgetEntry.objects.filter(state="released").count(), 2)
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_old_recorded_steps_are_not_rewritten(self):
        self.add_line(self.source)
        self.submit()
        # Represent a recorded submission from the previous named-user engine.
        step = ApprovalStep.objects.get()
        step.manager_source = ""
        step.rule_snapshot = {"rule_based": True, "named_user_id": self.second.pk}
        step.save()
        step.candidates.set([self.second])
        flow.refresh_submission(step.snapshot.submission_id)
        step.refresh_from_db()
        self.assertEqual(step.rule_snapshot["named_user_id"], self.second.pk)
        self.assertIsNone(flow.authority(self.first, step))
        self.decide(step, self.second)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_editor_and_admin_configuration_are_retired(self):
        self.client.force_login(self.admin)
        for name, args in (("rule_sets", []), ("rule_set", [1]), ("rule_add", [1]),
                           ("rule_edit", [1, 1]), ("rule_delete", [1, 1]), ("rule_simulate", [self.purchase.pk])):
            url = reverse("purchasing:" + name, args=args)
            self.assertRedirects(self.client.get(url), reverse("purchasing:configuration"))
            self.assertEqual(self.client.post(url, {}).status_code, 410)
        self.assertFalse(admin.site.is_registered(WorkflowVersion))
        self.assertFalse(admin.site.is_registered(ApprovalRule))
        self.assertFalse(WorkflowVersion.objects.exists())
        self.assertNotContains(self.client.get(reverse("purchasing:configuration")), "Si… alors…")

    def test_request_page_explains_line_validation_without_rule_editor(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("purchasing:detail", args=[self.purchase.pk]))
        self.assertContains(response, "Chaque ligne est valid&eacute;e par le responsable de son CDF")
        self.assertNotContains(response, "Simuler les validations")

    def test_steps_follow_order_within_each_line(self):
        self.add_line(self.source)
        self.add_line(self.target)
        self.submit()
        steps = list(ApprovalStep.objects.order_by("snapshot__original_line_id"))
        next_step = ApprovalStep.objects.create(snapshot=steps[0].snapshot, level=2,
            function_label="Validation suivante", manager_source="cdf",
            rule_snapshot={"automatic": False, "reuse_evidence": False})
        next_step.candidates.set([self.first])
        flow.refresh_submission(steps[0].snapshot.submission_id)
        next_step.refresh_from_db()
        self.assertEqual(next_step.state, "future")
        with self.assertRaises(PermissionDenied):
            self.decide(next_step, self.first)
        with self.assertRaises(PermissionDenied):
            self.decide(next_step, self.admin)
        self.decide(steps[0], self.first)
        next_step.refresh_from_db()
        steps[1].refresh_from_db()
        self.assertEqual(next_step.state, "pending")
        self.assertEqual(steps[1].state, "pending")
        self.decide(next_step, self.first)
        self.assertFalse(PurchaseOrder.objects.exists())
        self.decide(steps[1], self.second)
        self.assertTrue(PurchaseOrder.objects.exists())
