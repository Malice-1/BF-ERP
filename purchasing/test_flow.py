from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import ValidationFunction, Role
from accounts.services import publish_authorization
from budgeting.models import CostCenter, Funding, Support, BudgetProduct, DetailedProduct
from suppliers.models import Supplier
from .models import (AnnualEnvelope, EnvelopeVersion, Allocation, WorkflowVersion, ApprovalRule,
    Submission, ApprovalStep, BudgetEntry, PurchaseOrder, PurchaseNotice)
from .services import (create_purchase_request, add_purchase_request_line,
    delete_purchase_request_line, update_purchase_request_line, cancel_purchase_request)
from . import flow
from .exceptions import PurchaseRequestError, PurchaseRequestConflict


class PurchaseFlowTests(TestCase):
    def test_support_is_chosen_from_memberships_and_independent_from_funding(self):
        from .forms import PurchaseRequestForm
        other_support = Support.objects.create(code="OTHER", label="Autre support")
        form = PurchaseRequestForm(user=self.owner)
        self.assertEqual(list(form.fields["support"].queryset), [self.support])
        with self.assertRaises(ValidationError):
            create_purchase_request(actor=self.owner, supplier=self.supplier, support=other_support)
        self.owner.supports.add(other_support)
        other_support.managers.add(self.first)
        self.manager_workflow()
        self.cdf.managers.add(self.other)
        self.support.managers.add(self.second)
        self.funding.managers.add(self.first)
        self.submit()
        self.act(self.other)
        step = ApprovalStep.objects.get(snapshot__submission__purchase_request=self.purchase, level=2)
        self.assertEqual(step.snapshot.support, self.support)
        self.assertEqual(step.snapshot.data["support"], str(self.support))
        self.assertIsNotNone(flow.authority(self.second, step))
        self.assertIsNone(flow.authority(self.first, step))
        self.assertEqual(flow.pending_validation_count(self.second), 1)
        self.support.managers.set([self.first])
        self.assertEqual(flow.pending_validation_count(self.first), 1)
        self.assertIsNone(flow.authority(self.second, step))

    def test_support_workflow_requires_a_current_membership_before_any_reservation(self):
        self.manager_workflow()
        self.purchase.support = None
        self.purchase.save(update_fields=["support"])
        with self.assertRaisesMessage(PurchaseRequestError, "Choisissez un support"):
            self.submit()
        self.assertFalse(BudgetEntry.objects.exists())
        self.purchase.support = self.support
        self.purchase.save(update_fields=["support"])
        self.owner.supports.clear()
        with self.assertRaisesMessage(PurchaseRequestError, "Vous n’appartenez plus"):
            self.submit()
        self.assertFalse(BudgetEntry.objects.exists())

    def test_global_personal_icons_and_pending_badge(self):
        self.submit()
        self.client.force_login(self.first)
        response = self.client.get(reverse("my_validations"))
        self.assertEqual(response.context["pending_validation_count"], 1)
        self.assertContains(response, 'id="validation-count"')
        self.assertContains(response, f'href="{reverse("my_validations")}"')
        self.assertContains(response, f'href="{reverse("my_delegations")}"')
        self.assertNotContains(response, f'href="{reverse("purchasing:inbox")}"')
        self.assertNotContains(response, f'href="{reverse("purchasing:delegations")}"')
        self.client.force_login(self.second)
        response = self.client.get(reverse("my_validations"))
        self.assertEqual(response.context["pending_validation_count"], 0)
        self.assertNotContains(response, 'id="validation-count"')
        self.act(self.first)
        response = self.client.get(reverse("my_validations"))
        self.assertEqual(response.context["pending_validation_count"], 1)
        self.act(self.second)
        self.assertEqual(flow.pending_validation_count(self.second), 0)

    def test_global_badge_uses_current_manager_and_delegation(self):
        self.manager_workflow()
        self.submit()
        self.assertEqual(flow.pending_validation_count(self.other), 0)
        self.cdf.managers.add(self.other)
        self.assertEqual(flow.pending_validation_count(self.other), 1)
        flow.create_delegation(actor=self.other, principal=self.other, delegate=self.first,
            valid_from=timezone.now() - timedelta(hours=1), valid_until=timezone.now() + timedelta(days=1))
        self.assertEqual(flow.pending_validation_count(self.first), 1)
        self.cdf.managers.clear()
        self.assertEqual(flow.pending_validation_count(self.first), 0)
        self.assertEqual(flow.pending_validation_count(self.other), 0)

    def test_personal_pages_are_global_and_do_not_select_purchases(self):
        for name in ("my_validations", "my_delegations"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)
        self.client.force_login(self.other)
        for name in ("my_validations", "my_delegations"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["nav_section"], "personal")
            self.assertContains(response, 'aria-label="Espace personnel"')
        response = self.client.post(reverse("my_delegations"), {
            "delegate": self.first.pk,
            "valid_from": (timezone.now() - timedelta(hours=1)).isoformat(),
            "valid_until": (timezone.now() + timedelta(days=1)).isoformat(),
        })
        self.assertRedirects(response, reverse("my_delegations"))
        self.client.force_login(self.admin)
        for name in ("purchasing:budget_home", "purchasing:configuration"):
            response = self.client.get(reverse(name))
            self.assertContains(response, 'id="my-validations"')
            self.assertContains(response, 'id="my-delegations"')

    def manager_workflow(self):
        workflow = WorkflowVersion.objects.create(label="Responsables par ligne")
        ApprovalRule.objects.create(version=workflow, label="CDF", function=self.function1,
                                    level=1, cdf_manager=True)
        ApprovalRule.objects.create(version=workflow, label="Support", function=self.function2,
                                    level=2, support_manager=True)
        flow.activate_workflow(actor=self.admin, version_id=workflow.pk)

    def test_entity_managers_validate_without_roles_or_authorizations(self):
        self.manager_workflow()
        self.cdf.managers.add(self.other)
        self.support.managers.add(self.second)
        self.second.authorizations.update(current_version=None)
        self.submit()
        steps = ApprovalStep.objects.filter(snapshot__submission__purchase_request=self.purchase).order_by("level")
        first, second = list(steps)
        self.assertEqual(first.state, "pending")
        self.assertEqual(second.state, "future")
        self.assertIsNone(flow.authority(self.first, first))
        self.assertIsNotNone(flow.authority(self.other, first))
        self.act(self.other)
        second.refresh_from_db()
        self.assertEqual(second.state, "pending")
        self.act(self.second)
        self.assertTrue(PurchaseOrder.objects.filter(purchase_request=self.purchase).exists())
        first.refresh_from_db()
        self.assertIsNone(first.authorization_id)
        self.assertEqual(first.evaluated_scope["manager_source"], "cdf")

    def test_missing_manager_and_replacement_refresh_candidates(self):
        self.manager_workflow()
        self.submit()
        step = ApprovalStep.objects.get(snapshot__submission__purchase_request=self.purchase, level=1)
        self.assertEqual(step.state, "unassigned")
        self.cdf.managers.add(self.other)
        flow.refresh_submission(step.snapshot.submission_id)
        step.refresh_from_db()
        self.assertEqual(step.state, "pending")
        self.cdf.managers.set([self.first])
        flow.refresh_submission(step.snapshot.submission_id)
        self.assertIsNone(flow.authority(self.other, step))
        self.assertIsNotNone(flow.authority(self.first, step))
        self.assertTrue(PurchaseNotice.objects.filter(step=step, recipient=self.first, active=True).exists())

    def test_manager_configuration_screen_permissions_and_save(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("entity_managers")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("entity_managers")), self.cdf.code)
        response = self.client.post(reverse("entity_managers"), {
            "kind": "support", "entity_id": self.support.pk, "managers": [self.other.pk]})
        self.assertRedirects(response, reverse("entity_managers"))
        self.assertEqual(list(self.support.managers.all()), [self.other])

    def role_workflow(self, member=True):
        role = Role.objects.create(code="ACHATS", label="Validation achats")
        if member:
            self.other.roles.add(role)
        workflow = WorkflowVersion.objects.create(label="Validation par rôle")
        ApprovalRule.objects.create(version=workflow, label="Achats", function=self.function1,
                                    level=1, role=role)
        flow.activate_workflow(actor=self.admin, version_id=workflow.pk)
        return role

    def test_role_approval_requires_current_membership_and_records_evidence(self):
        role = self.role_workflow()
        self.submit()
        step = ApprovalStep.objects.get(snapshot__submission__purchase_request=self.purchase)
        self.assertEqual(step.role_id, role.pk)
        self.assertIsNotNone(flow.authority(self.other, step))
        self.assertIsNone(flow.authority(self.first, step))
        self.other.roles.remove(role)
        flow.refresh_submission(step.snapshot.submission_id)
        step.refresh_from_db()
        self.assertEqual(step.state, "blocked")
        self.assertIsNone(flow.authority(self.other, step))
        self.purchase.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            flow.decide(request_id=self.purchase.pk, actor=self.other, expected_revision=self.purchase.revision,
                        step_id=step.pk, decision="approve")
        self.other.roles.add(role)
        flow.refresh_submission(step.snapshot.submission_id)
        self.act(self.other)
        step.refresh_from_db()
        self.assertEqual(step.state, "approved")
        self.assertIsNone(step.authorization_id)
        self.assertEqual(step.evaluated_scope["role_id"], role.pk)
        self.assertEqual(step.evaluated_scope["role_code"], role.code)
        self.assertTrue(PurchaseOrder.objects.filter(purchase_request=self.purchase).exists())

    def test_role_without_members_and_conflicting_assignment(self):
        self.role_workflow(member=False)
        self.submit()
        self.assertEqual(ApprovalStep.objects.get(snapshot__submission__purchase_request=self.purchase).state, "unassigned")
        workflow = WorkflowVersion.objects.create(label="Invalid")
        ApprovalRule.objects.create(version=workflow, label="Invalid", function=self.function1,
            level=1, role=Role.objects.get(code="ACHATS"), named_user=self.first)
        with self.assertRaises(ValidationError):
            flow.activate_workflow(actor=self.admin, version_id=workflow.pk)

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", "admin@example.test", "secret")
        self.owner = User.objects.create_user("owner", email="owner@example.test")
        self.owner.user_permissions.add(Permission.objects.get(
            content_type__app_label="purchasing", codename="add_purchaserequest"))
        self.first = User.objects.create_user("first", email="first@example.test")
        self.second = User.objects.create_user("second", email="second@example.test")
        self.other = User.objects.create_user("other")
        self.supplier = Supplier.objects.create(code="S", name="Supplier snapshot")
        self.cdf = CostCenter.objects.create(code="C", label="CDF")
        self.funding = Funding.objects.create(code="F", label="Funding")
        self.support = Support.objects.create(code="SP", label="Support")
        self.owner.supports.add(self.support)
        self.product = BudgetProduct.objects.create(code="B", label="Product")
        self.detail = DetailedProduct.objects.create(code="D", label="Detail", budget_product=self.product)
        self.function1 = ValidationFunction.objects.create(code="CDF", label="CDF", position=1)
        self.function2 = ValidationFunction.objects.create(code="FIN", label="Finance", position=2)
        self.grant1 = self.grant(self.first, self.function1)
        self.grant2 = self.grant(self.second, self.function2)
        self.envelope = AnnualEnvelope.objects.create(year=timezone.localdate().year)
        self.version = self.budget("1000")
        self.workflow = WorkflowVersion.objects.create(label="Workflow 1")
        ApprovalRule.objects.create(version=self.workflow, label="CDF", function=self.function1, level=1)
        ApprovalRule.objects.create(version=self.workflow, label="Finance", function=self.function2, level=2)
        flow.activate_workflow(actor=self.admin, version_id=self.workflow.pk)
        self.purchase = self.draft()

    def grant(self, user, function):
        return publish_authorization(actor=self.admin, user=user, function=function,
            valid_from=timezone.now() - timedelta(days=1), scope={})

    def budget(self, amount):
        version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Budget " + amount)
        Allocation.objects.create(version=version, cost_center=self.cdf, funding=self.funding, budget_product=self.product, amount=Decimal(amount))
        flow.activate_envelope(actor=self.admin, version_id=version.pk)
        return version

    def draft(self, price="100", lines=1):
        purchase = create_purchase_request(actor=self.owner, supplier=self.supplier, support=self.support)
        for index in range(lines):
            purchase.refresh_from_db()
            add_purchase_request_line(request_id=purchase.pk, actor=self.owner, expected_revision=purchase.revision,
                detailed_product=self.detail, cost_center=self.cdf, funding=self.funding,
                description=f"Sensitive item {index}", quantity=Decimal("1"), unit_price=Decimal(price), vat_rate=Decimal("21"))
        purchase.refresh_from_db()
        return purchase

    def submit(self, purchase=None):
        purchase = purchase or self.purchase
        purchase.refresh_from_db()
        return flow.submit_purchase(request_id=purchase.pk, actor=self.owner, expected_revision=purchase.revision)

    def act(self, actor, decision="approve", purchase=None, reason=""):
        purchase = purchase or self.purchase
        purchase.refresh_from_db()
        step = next(s for s in ApprovalStep.objects.filter(snapshot__submission__purchase_request=purchase,
            snapshot__submission__active=True, state="pending").select_related("snapshot", "function") if flow.authority(actor, s))
        return flow.decide(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision,
            step_id=step.pk, decision=decision, reason=reason)

    def balance(self):
        self.envelope.refresh_from_db()
        return flow.available(self.envelope.active_version, self.cdf.pk, self.funding.pk, self.product.pk)

    def test_budget_check_standard_user_sees_live_balance(self):
        self.client.force_login(self.owner)
        data = dict(version=self.version.pk, budget_product=self.product.pk,
                    funding=self.funding.pk, cost_center=self.cdf.pk)
        response = self.client.get(reverse("purchasing:budget_check"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(response.context["result"]["available"], Decimal("1000"))
        self.submit()
        response = self.client.get(reverse("purchasing:budget_check"), data)
        self.assertEqual(response.context["result"]["available"], Decimal("879"))

        self.act(self.first)
        self.act(self.second)
        response = self.client.get(reverse("purchasing:budget_check"), data)
        self.assertEqual(response.context["result"]["available"], Decimal("879"))

    def test_all_requests_grant_revoke_and_read_only(self):
        url = reverse("purchasing:all_requests")
        detail = reverse("purchasing:detail", args=[self.purchase.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(detail).status_code, 404)
        permission = Permission.objects.get(content_type__app_label="purchasing", codename="view_all_purchase_requests")
        group = Group.objects.create(name="Consultation globale des DA")
        group.permissions.add(permission)
        self.other.groups.add(group)
        response = self.client.get(url)
        self.assertContains(response, self.purchase.number)
        self.assertContains(response, self.owner.username)
        response = self.client.get(detail)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["editable"])
        self.assertFalse(response.context["can_cancel"])
        for name in ("edit", "line_add", "cancel", "submit"):
            self.assertEqual(self.client.post(reverse("purchasing:" + name, args=[self.purchase.pk]), {}).status_code, 404)
        self.assertNotContains(self.client.get(reverse("purchasing:list")), self.purchase.number)
        self.other.groups.remove(group)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.other.user_permissions.add(permission)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_budget_check_validation_and_missing_allocation(self):
        self.client.force_login(self.owner)
        other = BudgetProduct.objects.create(code="OTHER", label="Other")
        data = dict(version=self.version.pk, budget_product=other.pk,
                    funding=self.funding.pk, cost_center=self.cdf.pk)
        response = self.client.get(reverse("purchasing:budget_check"), data)
        self.assertFalse(response.context["result"]["allocated"])
        self.assertEqual(response.context["result"]["available"], Decimal("0"))
        data["budget_product"] = "invalid"
        response = self.client.get(reverse("purchasing:budget_check"), data)
        self.assertIsNone(response.context["result"])
        self.assertIn("budget_product", response.context["form"].errors)
        AnnualEnvelope.objects.update(active_version=None)
        response = self.client.get(reverse("purchasing:budget_check"))
        self.assertContains(response, "Version budgétaire")

    def test_budget_check_uses_selected_draft_or_replaced_version(self):
        self.client.force_login(self.owner)
        self.submit()
        replacement = self.budget("2000")
        draft = EnvelopeVersion.objects.create(envelope=self.envelope, label="Simulation")
        Allocation.objects.create(version=draft, cost_center=self.cdf, funding=self.funding,
            budget_product=self.product, amount=Decimal("3000"))
        data = dict(budget_product=self.product.pk, funding=self.funding.pk, cost_center=self.cdf.pk)
        for version, expected in ((self.version, "879"), (replacement, "1879"), (draft, "2879")):
            response = self.client.get(reverse("purchasing:budget_check"), {**data, "version": version.pk})
            self.assertEqual(response.context["result"]["available"], Decimal(expected))
            self.assertEqual(response.context["result"]["version"], version.label)
        response = self.client.get(reverse("purchasing:budget_check"), {**data, "version": "invalid"})
        self.assertIn("version", response.context["form"].errors)
        self.assertIsNone(response.context["result"])

    def test_budget_check_requires_login_and_button_is_visible(self):
        self.assertEqual(self.client.get(reverse("purchasing:budget_check")).status_code, 302)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("purchasing:list"))
        self.assertContains(response, 'id="budget-check-open"')
        self.assertContains(response, "Vérifier un budget")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    def test_t001_t004_complete_flow_preserves_budget_and_creates_one_order(self):
        self.submit()
        self.assertEqual(self.balance(), Decimal("879"))
        self.act(self.first)
        self.assertFalse(PurchaseOrder.objects.exists())
        self.act(self.second)
        self.assertEqual(self.balance(), Decimal("879"))
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(BudgetEntry.objects.get().state, "committed")
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "ORDERED")
        with self.assertRaises(PurchaseRequestError):
            self.submit()
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_t002_combination_aggregate_shortage_rolls_back_all(self):
        purchase = self.draft("500", lines=2)
        with self.assertRaises(PurchaseRequestError):
            self.submit(purchase)
        self.assertFalse(BudgetEntry.objects.exists())
        self.assertFalse(Submission.objects.exists())
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, "DRAFT")

    def test_one_missing_combination_rolls_back_other_lines(self):
        other_fund = Funding.objects.create(code="F2", label="No budget")
        add_purchase_request_line(request_id=self.purchase.pk, actor=self.owner, expected_revision=self.purchase.revision,
            detailed_product=self.detail, cost_center=self.cdf, funding=other_fund,
            description="No allocation", quantity=1, unit_price=1, vat_rate=0)
        with self.assertRaises(PurchaseRequestError):
            self.submit()
        self.assertFalse(BudgetEntry.objects.exists())

    def test_t003_correction_releases_every_line_and_preserves_history(self):
        purchase = self.draft(lines=2)
        self.submit(purchase)
        self.act(self.first, purchase=purchase)
        self.act(self.first, decision="correct", reason="Corriger la quantité", purchase=purchase)
        self.assertEqual(self.balance(), Decimal("1000"))
        self.assertEqual(ApprovalStep.objects.filter(state="approved").count(), 1)
        old = purchase.submissions.get()
        self.assertFalse(old.active)
        purchase.refresh_from_db()
        line = purchase.lines.first()
        delete_purchase_request_line(request_id=purchase.pk, line_id=line.pk, actor=self.owner, expected_revision=purchase.revision)
        self.assertEqual(old.lines.count(), 2)
        self.submit(purchase)
        self.assertEqual(purchase.submissions.count(), 2)
        self.assertEqual(self.balance(), Decimal("879"))

    def test_rejection_is_terminal_and_no_reservation_remains(self):
        self.submit()
        self.act(self.first, "reject", reason="Non nécessaire")
        self.assertEqual(self.balance(), 1000)
        with self.assertRaises(PurchaseRequestError):
            self.submit()

    def test_requester_can_cancel_submitted_without_order(self):
        purchase = self.submit()
        cancel_purchase_request(request_id=purchase.pk, actor=self.owner, expected_revision=purchase.revision)
        self.assertEqual(self.balance(), 1000)
        self.assertFalse(Submission.objects.get().active)

    def test_t006_one_manual_approval_per_real_user_per_line(self):
        self.grant(self.first, self.function2)
        self.submit()
        self.act(self.first)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        steps = list(ApprovalStep.objects.order_by("level"))
        self.assertEqual(steps[1].evidence_id, steps[0].pk)
        self.assertIsNotNone(steps[1].authorization_id)

    def test_same_level_deduplication(self):
        config = WorkflowVersion.objects.create(label="Parallel")
        for index in range(2):
            ApprovalRule.objects.create(version=config, label=str(index), function=self.function1, level=1)
        flow.activate_workflow(actor=self.admin, version_id=config.pk)
        self.submit()
        self.act(self.first)
        self.assertEqual(ApprovalStep.objects.filter(evidence__isnull=True, state="approved").count(), 1)
        self.assertEqual(ApprovalStep.objects.filter(evidence__isnull=False, state="approved").count(), 1)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_eligibility_at_earlier_level_is_not_manual_evidence(self):
        self.grant(self.second, self.function1)
        self.submit()
        self.act(self.first)
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertEqual(ApprovalStep.objects.get(level=2).state, "pending")

    def test_levels_cannot_be_skipped_or_approved_by_superuser_without_grant(self):
        purchase = self.submit()
        step = ApprovalStep.objects.get(level=2)
        for actor in (self.second, self.admin, self.other):
            with self.assertRaises(PermissionDenied):
                flow.decide(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision, step_id=step.pk, decision="approve")
        self.assertFalse(PurchaseOrder.objects.exists())

    def test_t007_revocation_restoration_and_notifications(self):
        self.submit()
        grant = self.grant1
        disabled = publish_authorization(actor=self.admin, user=self.first, function=self.function1,
            valid_from=grant.valid_from, enabled=False, authorization_id=grant.authorization_id, expected_version=grant.version)
        flow.refresh_submission(Submission.objects.get().pk)
        step = ApprovalStep.objects.get(level=1)
        self.assertEqual(step.state, "blocked")
        self.assertTrue(PurchaseNotice.objects.filter(recipient=self.admin, active=True).exists())
        self.assertFalse(PurchaseNotice.objects.filter(recipient=self.owner).exists())
        publish_authorization(actor=self.admin, user=self.first, function=self.function1, valid_from=grant.valid_from,
            authorization_id=grant.authorization_id, expected_version=disabled.version)
        flow.refresh_submission(Submission.objects.get().pk)
        step.refresh_from_db()
        self.assertEqual(step.state, "pending")
        self.assertIsNone(step.approved_by_id)
        self.assertEqual(self.balance(), 879)

    def test_t008_new_deficit_blocks_new_reservation_allows_existing_conversion(self):
        self.submit()
        self.budget("50")
        self.assertEqual(self.balance(), -71)
        other = self.draft("1")
        with self.assertRaises(PurchaseRequestError):
            self.submit(other)
        self.act(self.first)
        self.act(self.second)
        self.assertEqual(self.balance(), -71)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(PurchaseOrder.objects.get().submission.budget_version_id, self.version.pk)

    def test_no_eligible_approver_reserves_and_can_be_reassigned(self):
        self.first.is_active = False
        self.first.save()
        self.submit()
        step = ApprovalStep.objects.get(level=1)
        self.assertEqual(step.state, "unassigned")
        self.assertEqual(self.balance(), 879)
        self.grant(self.other, self.function1)
        self.purchase.refresh_from_db()
        flow.reassign(request_id=self.purchase.pk, actor=self.admin, expected_revision=self.purchase.revision,
            step_id=step.pk, user=self.other, reason="Remplacement")
        self.act(self.other)
        self.assertEqual(ApprovalStep.objects.get(level=2).state, "pending")

    def test_reassignment_requires_permission_reason_and_scope(self):
        purchase = self.submit()
        step = ApprovalStep.objects.get(level=1)
        for actor, user, reason, error in ((self.owner, self.first, "x", PermissionDenied),
                (self.admin, self.second, "x", ValidationError), (self.admin, self.first, "", ValidationError)):
            with self.assertRaises(error):
                flow.reassign(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision,
                    step_id=step.pk, user=user, reason=reason)

    def test_threshold_is_total_request_htva_not_line_or_tvac(self):
        config = WorkflowVersion.objects.create(label="Threshold")
        ApprovalRule.objects.create(version=config, label="Total 100 minimum", function=self.function1,
            level=1, minimum_htva=100, maximum_htva=110)
        flow.activate_workflow(actor=self.admin, version_id=config.pk)
        self.submit(self.draft("50", lines=2))
        self.assertEqual(ApprovalStep.objects.count(), 2)

    def test_no_matching_rule_blocks_before_reservation(self):
        config = WorkflowVersion.objects.create(label="No match")
        ApprovalRule.objects.create(version=config, label="High", function=self.function1, minimum_htva=1000)
        flow.activate_workflow(actor=self.admin, version_id=config.pk)
        with self.assertRaises(PurchaseRequestError):
            self.submit()
        self.assertFalse(BudgetEntry.objects.exists())

    def test_incoherent_activation_preserves_active_configuration(self):
        config = WorkflowVersion.objects.create(label="Conflict")
        for index in range(2):
            ApprovalRule.objects.create(version=config, label=str(index), function=self.function1, mode="exclusive")
        with self.assertRaises(ValidationError):
            flow.activate_workflow(actor=self.admin, version_id=config.pk)
        self.assertTrue(WorkflowVersion.objects.get(pk=self.workflow.pk).active)

    def test_configuration_and_budget_published_rows_cannot_be_changed(self):
        self.workflow.refresh_from_db()
        self.workflow.label = "Mutation"
        with self.assertRaises(ValidationError):
            self.workflow.save()
        rule = self.workflow.rules.first()
        with self.assertRaises(ValidationError):
            rule.save()
        self.version.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.version.save()
        with self.assertRaises(ValidationError):
            self.version.allocations.first().delete()

    def test_global_delegation_uses_principal_authorization_and_real_actor(self):
        self.submit()
        flow.create_delegation(actor=self.first, principal=self.first, delegate=self.other,
            valid_from=timezone.now() - timedelta(hours=1), valid_until=timezone.now() + timedelta(hours=1))
        self.act(self.other)
        step = ApprovalStep.objects.get(level=1)
        self.assertEqual(step.approved_by, self.other)
        self.assertEqual(step.authorization, self.grant1)
        self.assertEqual(step.evaluated_scope["represented_user"], self.first.pk)

    def test_delegation_chains_and_overlaps_are_rejected(self):
        now = timezone.now()
        flow.create_delegation(actor=self.first, principal=self.first, delegate=self.other,
            valid_from=now, valid_until=now + timedelta(days=1))
        with self.assertRaises(ValidationError):
            flow.create_delegation(actor=self.other, principal=self.other, delegate=self.second,
                valid_from=now, valid_until=now + timedelta(days=1))

    def test_document_uses_immutable_supplier_and_line_snapshot(self):
        self.submit()
        self.supplier.name = "Changed later"
        self.supplier.save()
        self.act(self.first)
        self.act(self.second)
        self.client.force_login(self.owner)
        response = self.client.get(f"/achats/{self.purchase.pk}/commande/")
        self.assertContains(response, "Supplier snapshot")
        self.assertNotContains(response, "Changed later")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/achats/{self.purchase.pk}/commande/").status_code, 404)

    def test_operational_monitor_does_not_leak_financial_payload(self):
        self.submit()
        self.other.user_permissions.add(Permission.objects.get(content_type__app_label="purchasing", codename="monitor_purchases"))
        self.client.force_login(self.other)
        response = self.client.get("/achats/suivi/")
        self.assertContains(response, self.purchase.number)
        self.assertNotContains(response, "Sensitive item")
        self.assertNotContains(response, self.supplier.name)
        self.assertEqual(self.client.get(f"/achats/{self.purchase.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/achats/budgets/").status_code, 403)

    def test_browser_submit_approve_and_role_pages(self):
        self.client.force_login(self.owner)
        url = f"/achats/{self.purchase.pk}/soumettre/"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertFalse(Submission.objects.exists())
        self.assertEqual(self.client.post(url, {"expected_revision": self.purchase.revision}).status_code, 302)
        self.client.force_login(self.first)
        inbox = self.client.get("/achats/validations/")
        self.assertContains(inbox, "Traiter")
        step = ApprovalStep.objects.get(level=1)
        self.purchase.refresh_from_db()
        url = f"/achats/{self.purchase.pk}/etapes/{step.pk}/decision/"
        self.assertEqual(self.client.post(url, {"expected_revision": self.purchase.revision, "decision": "approve"}).status_code, 302)
        self.client.force_login(self.admin)
        for url in ("/achats/suivi/", "/achats/budgets/", "/admin/", "/admin/purchasing/workflowversion/",
                f"/admin/purchasing/workflowversion/{self.workflow.pk}/change/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_decision_requires_post_csrf_and_fresh_revision(self):
        purchase = self.submit()
        step = ApprovalStep.objects.get(level=1)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.first)
        url = f"/achats/{purchase.pk}/etapes/{step.pk}/decision/"
        self.assertEqual(client.get(url).status_code, 200)
        step.refresh_from_db()
        self.assertEqual(step.state, "pending")
        self.assertEqual(client.post(url, {"expected_revision": purchase.revision, "decision": "approve"}).status_code, 403)
        with self.assertRaises(PurchaseRequestConflict):
            flow.decide(request_id=purchase.pk, actor=self.first, expected_revision=0, step_id=step.pk, decision="approve")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_notification_delivery_and_obsolete_suppression(self):
        self.submit()
        call_command("process_purchase_notifications", stdout=StringIO())
        from django.core import mail
        self.assertTrue(mail.outbox)
        self.act(self.first)
        self.act(self.second)
        count = len(mail.outbox)
        call_command("process_purchase_notifications", stdout=StringIO())
        self.assertEqual(len(mail.outbox), count)
        self.assertFalse(PurchaseNotice.objects.filter(active=True).exists())

    def test_mail_failure_does_not_undo_submission(self):
        self.submit()
        with patch("purchasing.management.commands.process_purchase_notifications.send_mail", side_effect=OSError("offline")):
            call_command("process_purchase_notifications", stdout=StringIO(), stderr=StringIO())
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "SUBMITTED")
        self.assertTrue(PurchaseNotice.objects.filter(email_state="failed").exists())

    def test_demo_seed_refuses_usual_database(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("seed_purchase_demo", stdout=StringIO())

    @override_settings(SETTINGS_MODULE="config.demo_settings")
    def test_demo_seed_is_repeatable_and_preserves_password_and_draft(self):
        call_command("seed_purchase_demo", stdout=StringIO())
        user = get_user_model().objects.get(username="demo.demandeur")
        self.assertTrue(user.check_password("TestAchats!2026"))
        user.set_password("PersonalTestPassword")
        user.save()
        from .models import PurchaseRequest
        purchase = PurchaseRequest.objects.get(created_by=user)
        self.assertEqual(purchase.lines.count(), 2)
        call_command("seed_purchase_demo", stdout=StringIO())
        user.refresh_from_db()
        self.assertTrue(user.check_password("PersonalTestPassword"))
        self.assertEqual(PurchaseRequest.objects.filter(created_by=user).count(), 1)

    def test_admin_can_clone_and_publish_configuration_and_budget(self):
        self.client.force_login(self.admin)
        for model_name, source, cls in (("workflowversion", self.workflow, WorkflowVersion), ("envelopeversion", self.version, EnvelopeVersion)):
            app_label = "budgeting" if model_name == "envelopeversion" else "purchasing"
            url = f"/admin/{app_label}/{model_name}/"
            response = self.client.post(url, {"action": "clone", "_selected_action": [source.pk]})
            self.assertEqual(response.status_code, 302)
            clone = cls.objects.exclude(pk=source.pk).get()
            self.assertIsNone(clone.published_at)
            response = self.client.post(url, {"action": "activate", "_selected_action": [clone.pk]})
            self.assertEqual(response.status_code, 302)
            clone.refresh_from_db()
            self.assertIsNotNone(clone.published_at)
