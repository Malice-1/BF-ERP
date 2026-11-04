from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from budgeting.models import CostCenter, Funding, Support, BudgetProduct
from suppliers.models import Supplier
from .models import (DetailedProduct, WorkflowVersion, ApprovalRule, AnnualEnvelope, EnvelopeVersion,
                     Allocation, ApprovalStep, Submission, BudgetEntry, PurchaseNotice)
from .services import create_purchase_request, add_purchase_request_line
from .exceptions import PurchaseRequestError
from . import flow


class ConditionalRulesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("rules-admin", password="test")
        self.owner = User.objects.create_user("rules-owner")
        self.owner.user_permissions.add(Permission.objects.get(codename="add_purchaserequest"))
        self.reviewer = User.objects.create_user("rules-reviewer")
        self.second = User.objects.create_user("rules-second")
        self.cdf = CostCenter.objects.create(code="RULE", label="CDF")
        self.funding = Funding.objects.create(code="RULE", label="Financement")
        self.support = Support.objects.create(code="RULE", label="Support")
        self.owner.supports.add(self.support)
        product = BudgetProduct.objects.create(code="RULE", label="Produit")
        self.detail = DetailedProduct.objects.create(code="RULE", label="Détail", budget_product=product)
        supplier = Supplier.objects.create(code="RULE", name="Fournisseur")
        envelope = AnnualEnvelope.objects.create(year=timezone.localdate().year)
        budget = EnvelopeVersion.objects.create(envelope=envelope, label="Budget")
        Allocation.objects.create(version=budget, cost_center=self.cdf, funding=self.funding, budget_product=product, amount=100000)
        flow.activate_envelope(actor=self.admin, version_id=budget.pk)
        self.purchase = create_purchase_request(actor=self.owner, supplier=supplier, support=self.support)
        self.line = self.add_line()
        self.version = WorkflowVersion.objects.create(label="Règles conditionnelles", rule_based=True)
        self.client.force_login(self.admin)

    def add_line(self):
        self.purchase.refresh_from_db()
        return add_purchase_request_line(request_id=self.purchase.pk, actor=self.owner, expected_revision=self.purchase.revision,
            detailed_product=self.detail, cost_center=self.cdf, funding=self.funding, description="Ligne de test",
            quantity=Decimal("1"), unit_price=Decimal("100"), vat_rate=Decimal("21"))

    def rule(self, label="Validation", **kwargs):
        values = {"version": self.version, "label": label, "conditions": {"all": []}, "named_user": self.reviewer}
        values.update(kwargs)
        return ApprovalRule.objects.create(**values)

    def publish(self):
        flow.activate_workflow(actor=self.admin, version_id=self.version.pk)

    def submit(self):
        self.purchase.refresh_from_db()
        flow.submit_purchase(request_id=self.purchase.pk, actor=self.owner, expected_revision=self.purchase.revision)

    def test_editor_saves_typed_conditions_and_blocks_published_edits(self):
        response = self.client.get(reverse("purchasing:rule_add", args=[self.version.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="rule-editor"')
        self.assertContains(response, "condition-catalog")
        payload = {"label": "Montant et CDF", "level": 2, "target": "user", "named_user": self.reviewer.pk,
            "junction": "all", "conditions-TOTAL_FORMS": 2, "conditions-INITIAL_FORMS": 0,
            "conditions-0-field": "line.tvac", "conditions-0-op": "gte", "conditions-0-value": "100.01",
            "conditions-1-field": "line.cdf", "conditions-1-op": "eq", "conditions-1-value": self.cdf.pk}
        response = self.client.post(reverse("purchasing:rule_add", args=[self.version.pk]), payload)
        self.assertEqual(response.status_code, 302)
        rule = self.version.rules.get()
        self.assertIsNone(rule.function_id)
        self.assertEqual(rule.conditions["all"][1]["value"], str(self.cdf.pk))
        self.publish()
        self.assertEqual(self.client.post(reverse("purchasing:rule_edit", args=[self.version.pk, rule.pk]), payload).status_code, 403)
        rule.label = "Modification interdite"
        with self.assertRaises(ValidationError):
            rule.save()

    def test_editor_requires_explicit_unconditional_rule_and_accepts_unused_empty_row(self):
        payload = {"label": "Toujours", "level": 1, "target": "user", "named_user": self.reviewer.pk,
            "junction": "all", "conditions-TOTAL_FORMS": 1, "conditions-INITIAL_FORMS": 0,
            "conditions-0-field": "", "conditions-0-op": "eq", "conditions-0-value": ""}
        url = reverse("purchasing:rule_add", args=[self.version.pk])
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.version.rules.exists())
        response = self.client.post(url, {**payload, "unconditional": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.version.rules.get().conditions, {"all": []})

    def test_replacing_historical_function_clears_its_reference_and_new_function_mode_is_rejected(self):
        from accounts.models import ValidationFunction
        function = ValidationFunction.objects.create(code="SWITCH", label="Fonction", position=1)
        rule = self.rule(named_user=None, function=function)
        response = self.client.post(reverse("purchasing:rule_edit", args=[self.version.pk, rule.pk]), {
            "label": "Responsables", "level": 1, "target": "cdf",
            "junction": "all", "unconditional": "on", "conditions-TOTAL_FORMS": 1, "conditions-INITIAL_FORMS": 0,
            "conditions-0-field": "", "conditions-0-op": "eq", "conditions-0-value": ""})
        self.assertEqual(response.status_code, 302)
        rule.refresh_from_db()
        self.assertIsNone(rule.named_user_id)
        self.assertEqual(rule.named_user_reference, "")
        self.assertIsNone(rule.function_id)
        self.assertTrue(rule.cdf_manager)
        self.rule(label="Ancienne fonction", named_user=None, function=function)
        with self.assertRaises(ValidationError):
            self.publish()
        response = self.client.post(reverse("purchasing:rule_add", args=[self.version.pk]), {
            "label": "Interdit", "level": 1, "target": "function", "function": function.pk,
            "junction": "all", "unconditional": "on", "conditions-TOTAL_FORMS": 0, "conditions-INITIAL_FORMS": 0})
        self.assertEqual(response.status_code, 200)
        self.assertIn("target", response.context["form"].errors)

    def test_simulation_respects_historical_named_user_habilitation(self):
        from accounts.models import ValidationFunction
        function = ValidationFunction.objects.create(code="RULE", label="Fonction", position=1)
        self.version.rule_based = False
        self.version.save()
        self.rule(function=function)
        self.publish()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("purchasing:rule_simulate", args=[self.purchase.pk]))
        self.assertEqual(response.context["rows"][0]["candidates"], [])
        self.submit()
        self.assertFalse(ApprovalStep.objects.get().candidates.exists())

    def test_cumulative_conditions_create_parallel_and_sequential_steps_with_evidence(self):
        self.rule("Montant", conditions={"all": [{"field": "line.tvac", "op": "gte", "value": "121"}]})
        self.rule("CDF ou support", conditions={"any": [{"field": "line.cdf", "op": "eq", "value": str(self.cdf.pk)},
                                                         {"field": "request.support", "op": "eq", "value": str(self.support.pk)}]})
        self.rule("Après", level=2, named_user=self.second)
        self.publish()
        self.submit()
        steps = list(ApprovalStep.objects.order_by("level", "pk"))
        self.assertEqual([s.state for s in steps], ["pending", "pending", "future"])
        self.assertEqual(steps[0].rule_snapshot["facts"]["line.cdf"], str(self.cdf.pk))
        self.assertEqual(steps[0].rule_snapshot["label"], "Montant")
        self.purchase.refresh_from_db()
        flow.decide(request_id=self.purchase.pk, actor=self.reviewer, expected_revision=self.purchase.revision,
                    step_id=steps[0].pk, decision="approve")
        steps[1].refresh_from_db(); steps[2].refresh_from_db()
        self.assertEqual(steps[1].state, "approved")
        self.assertEqual(steps[1].evidence_id, steps[0].pk)
        self.assertEqual(steps[2].state, "pending")

    def test_line_amount_is_distinct_from_request_total_and_simulation_writes_nothing(self):
        self.add_line()
        self.rule("Socle")
        self.rule("Grande ligne", conditions={"all": [{"field": "line.htva", "op": "gte", "value": "150"}]})
        self.rule("Grande DA", conditions={"all": [{"field": "request.htva", "op": "gte", "value": "150"}]})
        self.publish()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("purchasing:rule_simulate", args=[self.purchase.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 4)
        self.assertNotContains(response, "Grande ligne")
        self.assertContains(response, "Grande DA")
        for model in (Submission, ApprovalStep, BudgetEntry):
            self.assertEqual(model.objects.count(), 0)
        self.submit()
        self.assertEqual(ApprovalStep.objects.count(), 4)

    def test_no_match_or_invalid_configuration_cannot_reserve_budget(self):
        rule = self.rule(conditions={"all": [{"field": "line.tvac", "op": "gte", "value": "1000"}]})
        self.publish()
        with self.assertRaises(PurchaseRequestError):
            self.submit()
        self.assertFalse(BudgetEntry.objects.exists())
        version = WorkflowVersion.objects.create(label="Invalide", rule_based=True)
        self.rule(version=version, conditions={"field": "unknown", "op": "eq", "value": "1"})
        with self.assertRaises(ValidationError):
            flow.activate_workflow(actor=self.admin, version_id=version.pk)
        self.version.refresh_from_db()
        self.assertTrue(self.version.active)

    def test_permissions_copy_and_simulation_privacy(self):
        self.rule()
        self.publish()
        response = self.client.post(reverse("purchasing:rule_set", args=[self.version.pk]), {"action": "copy"})
        self.assertEqual(response.status_code, 302)
        copy = WorkflowVersion.objects.exclude(pk=self.version.pk).get()
        self.assertFalse(copy.active)
        self.assertIsNone(copy.published_at)
        self.assertTrue(copy.rule_based)
        self.assertEqual(copy.rules.get().conditions, {"all": []})
        self.client.force_login(self.second)
        self.assertEqual(self.client.get(reverse("purchasing:rule_sets")).status_code, 403)
        self.assertEqual(self.client.get(reverse("purchasing:rule_simulate", args=[self.purchase.pk])).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("purchasing:rule_simulate", args=[self.purchase.pk]), {"version": copy.pk}).status_code, 403)

    def test_admin_copy_preserves_new_engine_and_simulation_allows_financial_readers(self):
        rule = self.rule(conditions={"all": [{"field": "line.htva", "op": "gte", "value": "50"}]})
        self.publish()
        response = self.client.get(reverse("admin:purchasing_workflowversion_change", args=[self.version.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ouvrir les règles et la simulation")
        response = self.client.post(reverse("admin:purchasing_workflowversion_changelist"), {
            "action": "clone", "_selected_action": [self.version.pk]})
        self.assertEqual(response.status_code, 302)
        copy = WorkflowVersion.objects.exclude(pk=self.version.pk).get()
        self.assertTrue(copy.rule_based)
        self.assertEqual(copy.rules.get().conditions, rule.conditions)
        self.second.user_permissions.add(Permission.objects.get(codename="view_purchase_financial"))
        self.client.force_login(self.second)
        self.assertEqual(self.client.get(reverse("purchasing:rule_simulate", args=[self.purchase.pk])).status_code, 200)

    def test_simulation_does_not_refresh_existing_steps_or_emit_notifications_from_header(self):
        self.rule(named_user=None, cdf_manager=True)
        self.publish()
        self.submit()
        step = ApprovalStep.objects.get()
        self.assertEqual(step.state, "unassigned")
        self.cdf.managers.add(self.reviewer)
        self.reviewer.user_permissions.add(Permission.objects.get(codename="view_purchase_financial"))
        self.client.force_login(self.reviewer)
        notices = PurchaseNotice.objects.count()
        response = self.client.get(reverse("purchasing:rule_simulate", args=[self.purchase.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["rows"][0]["candidates"], [self.reviewer])
        step.refresh_from_db()
        self.assertEqual(step.state, "unassigned")
        self.assertFalse(step.candidates.exists())
        self.assertEqual(PurchaseNotice.objects.count(), notices)
