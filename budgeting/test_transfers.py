from purchasing.test_helpers import record_legacy_workflow
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from purchasing.models import AnnualEnvelope, EnvelopeVersion, Allocation, WorkflowVersion, ApprovalRule
from purchasing.flow import activate_envelope, available
from .models import CostCenter, Funding, BudgetProduct, BudgetTransfer, TransferConfiguration, BudgetHistoryEvent
from .transfers import act, refresh


class TransferTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="test")
        self.owner = User.objects.create_user("owner")
        self.owner.user_permissions.add(Permission.objects.get(codename="add_budgettransfer"))
        self.reviewer = User.objects.create_user("reviewer")
        self.source = CostCenter.objects.create(code="A", label="A")
        self.target = CostCenter.objects.create(code="B", label="B")
        self.funding = Funding.objects.create(code="F", label="F")
        self.product = BudgetProduct.objects.create(code="P", label="P")
        self.envelope = AnnualEnvelope.objects.create(year=timezone.localdate().year)
        self.budget = EnvelopeVersion.objects.create(envelope=self.envelope, label="V1")
        Allocation.objects.create(version=self.budget, cost_center=self.source, funding=self.funding, budget_product=self.product, amount=100)
        activate_envelope(actor=self.admin, version_id=self.budget.pk)
        self.source.managers.add(self.reviewer)
        self.target.managers.add(self.admin)
        self.transfer = self.create_transfer()

    def create_transfer(self, amount="60", version=None):
        version = version or self.budget
        return BudgetTransfer.objects.create(envelope=version.envelope, budget_version=version, source_cdf=self.source, destination_cdf=self.target,
            source_funding=self.funding, destination_funding=self.funding, source_product=self.product,
            destination_product=self.product, amount=Decimal(amount), reason="Rééquilibrage", created_by=self.owner)

    def submit(self):
        return act(pk=self.transfer.pk, actor=self.owner, revision=0, action="submit")

    def balance(self, cdf):
        return available(self.budget, cdf.pk, self.funding.pk, self.product.pk)

    def approve_transfer(self, transfer):
        act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve", step_id=transfer.steps.get(level=1).pk)
        return act(pk=transfer.pk, actor=self.admin, revision=2, action="approve", step_id=transfer.steps.get(level=2).pk)

    def test_fixed_steps_without_any_configuration(self):
        transfer = self.submit()
        self.assertIsNone(transfer.workflow_id)
        self.assertFalse(WorkflowVersion.objects.exists())
        self.assertEqual(list(transfer.steps.values_list("level", "state")), [(1, "pending"), (2, "future")])
        self.assertTrue(transfer.steps.get(level=2).rule["destination_cdf_manager"])
        with self.assertRaises(PermissionDenied):
            act(pk=transfer.pk, actor=self.admin, revision=1, action="approve", step_id=transfer.steps.get(level=2).pk)
        with self.assertRaises(PermissionDenied):
            act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve", step_id=transfer.steps.get(level=2).pk)
        self.approve_transfer(transfer)
        self.assertEqual(self.balance(self.target), 60)

    def test_same_manager_requires_two_successive_decisions(self):
        self.target.managers.set([self.reviewer])
        transfer = self.submit()
        act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve", step_id=transfer.steps.get(level=1).pk)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "pending")
        self.assertEqual(transfer.steps.get(level=2).state, "pending")
        act(pk=transfer.pk, actor=self.reviewer, revision=2, action="approve", step_id=transfer.steps.get(level=2).pk)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "approved")
        self.assertFalse(transfer.steps.filter(evidence__isnull=False).exists())

    def test_missing_manager_waits_then_follows_current_assignments(self):
        self.source.managers.clear()
        transfer = self.submit()
        self.assertEqual(transfer.steps.get(level=1).state, "unassigned")
        self.assertEqual(transfer.steps.get(level=2).state, "future")
        self.source.managers.add(self.reviewer)
        refresh(transfer.pk)
        self.assertEqual(transfer.steps.get(level=1).state, "pending")
        act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve", step_id=transfer.steps.get(level=1).pk)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("my_validations")), reverse("transfer_detail", args=[transfer.pk]))

    def test_reservation_then_balanced_posting_and_double_decision(self):
        transfer = self.submit()
        self.assertEqual(self.balance(self.source), 40)
        self.assertEqual(self.balance(self.target), 0)
        step = transfer.steps.get(level=1)
        self.approve_transfer(transfer)
        self.assertEqual(self.balance(self.source), 40)
        self.assertEqual(self.balance(self.target), 60)
        with self.assertRaises(ValidationError):
            act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve", step_id=step.pk)
        self.assertEqual(self.balance(self.target), 60)

    def test_insufficient_budget_rolls_back_all_steps(self):
        self.submit()
        other = self.create_transfer()
        with self.assertRaises(ValidationError):
            act(pk=other.pk, actor=self.owner, revision=0, action="submit")
        self.assertFalse(other.steps.exists())
        other.refresh_from_db()
        self.assertEqual(other.status, "draft")

    def test_rejection_releases_reservation_and_requires_reason(self):
        transfer = self.submit()
        step = transfer.steps.get(level=1)
        with self.assertRaises(ValidationError):
            act(pk=transfer.pk, actor=self.reviewer, revision=1, action="reject", step_id=step.pk)
        self.assertEqual(self.balance(self.source), 40)
        act(pk=transfer.pk, actor=self.reviewer, revision=1, action="reject", step_id=step.pk, reason="Refus")
        self.assertEqual(self.balance(self.source), 100)
        self.assertEqual(self.balance(self.target), 0)

    def test_cancel_and_owner_permissions(self):
        self.submit()
        with self.assertRaises(PermissionDenied):
            act(pk=self.transfer.pk, actor=self.reviewer, revision=1, action="cancel")
        act(pk=self.transfer.pk, actor=self.owner, revision=1, action="cancel")
        self.assertEqual(self.balance(self.source), 100)

    def test_transfer_survives_budget_version_replacement(self):
        transfer = self.submit()
        self.approve_transfer(transfer)
        new = EnvelopeVersion.objects.create(envelope=self.envelope, label="V2")
        Allocation.objects.create(version=new, cost_center=self.source, funding=self.funding, budget_product=self.product, amount=200)
        activate_envelope(actor=self.admin, version_id=new.pk)
        self.assertEqual(available(new, self.source.pk, self.funding.pk, self.product.pk), 200)
        self.assertEqual(available(new, self.target.pk, self.funding.pk, self.product.pk), 0)

    def test_inbox_and_detail_authorization(self):
        self.submit()
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("my_validations"))
        self.assertContains(response, reverse("transfer_detail", args=[self.transfer.pk]))
        self.assertEqual(response.context["pending_validation_count"], 1)
        self.assertEqual(self.client.get(reverse("transfer_detail", args=[self.transfer.pk])).status_code, 200)
        stranger = get_user_model().objects.create_user("stranger")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse("transfer_detail", args=[self.transfer.pk])).status_code, 403)

    def test_budget_table_includes_destination_without_allocation(self):
        transfer = self.submit()
        self.approve_transfer(transfer)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("purchasing:budgets"))
        self.assertEqual(len(response.context["rows"]), 2)
        self.assertEqual(sum(row["available"] for row in response.context["rows"]), 100)

    def test_budget_selection_isolates_transfers_by_version(self):
        self.submit()
        other = EnvelopeVersion.objects.create(envelope=self.envelope, label="Other budget")
        Allocation.objects.create(version=other, cost_center=self.source, funding=self.funding,
                                  budget_product=self.product, amount=200)
        self.client.force_login(self.admin)
        for version, balance, movements in ((self.budget, 40, -60), (other, 200, 0)):
            response = self.client.get(reverse("purchasing:budgets"), {"version": version.pk})
            row = response.context["rows"][0]
            self.assertEqual(row["available"], balance)
            self.assertEqual(row["transfers"], movements)

    def test_pending_transfer_prevents_purchase_overspend(self):
        from purchasing.models import DetailedProduct, BudgetEntry
        from purchasing.services import create_purchase_request, add_purchase_request_line
        from purchasing.flow import submit_purchase
        from purchasing.exceptions import PurchaseRequestError
        from suppliers.models import Supplier
        self.submit()
        supplier = Supplier.objects.create(code="S", name="S")
        detail = DetailedProduct.objects.create(code="D", label="D", budget_product=self.product)
        version = WorkflowVersion.objects.create(label="Achats", rule_based=True)
        ApprovalRule.objects.create(version=version, label="Manuelle", named_user=self.reviewer, conditions={"all": []})
        record_legacy_workflow(version)
        purchase = create_purchase_request(actor=self.owner, supplier=supplier)
        add_purchase_request_line(request_id=purchase.pk, actor=self.owner, expected_revision=purchase.revision,
            detailed_product=detail, cost_center=self.source, funding=self.funding,
            description="Achat", quantity=Decimal(1), unit_price=Decimal(50), vat_rate=Decimal(0))
        purchase.refresh_from_db()
        with self.assertRaises(PurchaseRequestError):
            submit_purchase(request_id=purchase.pk, actor=self.owner, expected_revision=purchase.revision)
        self.assertFalse(BudgetEntry.objects.exists())

    def test_configured_automatic_rule_cannot_bypass_fixed_http_validation(self):
        version = WorkflowVersion.objects.create(label="Auto", operation="transfer", rule_based=True)
        ApprovalRule.objects.create(version=version, label="Auto", automatic=True, conditions={"all": []})
        record_legacy_workflow(version)
        self.client.force_login(self.owner)
        payload = {"budget_version": self.budget.pk, "source_cdf": self.source.pk, "destination_cdf": self.target.pk,
            "source_funding": self.funding.pk, "destination_funding": self.funding.pk,
            "source_product": self.product.pk, "destination_product": self.product.pk, "amount": "20", "reason": "Rééquilibrage"}
        response = self.client.post(reverse("transfer_list"), payload)
        self.assertEqual(response.status_code, 302)
        transfer = BudgetTransfer.objects.latest("pk")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "pending")
        self.assertEqual(transfer.revision, 1)
        self.assertEqual(transfer.steps.count(), 2)
        self.assertEqual(self.balance(self.target), 0)

    def payload(self, version):
        return {"budget_version": version.pk, "source_cdf": self.source.pk, "destination_cdf": self.target.pk,
            "source_funding": self.funding.pk, "destination_funding": self.funding.pk,
            "source_product": self.product.pk, "destination_product": self.product.pk,
            "amount": "10", "reason": "Test"}

    def test_selected_version_determines_year_without_configuration(self):
        self.assertFalse(TransferConfiguration.objects.exists())
        other = AnnualEnvelope.objects.create(year=self.envelope.year+1)
        version = EnvelopeVersion.objects.create(envelope=other, label="Draft")
        Allocation.objects.create(version=version, cost_center=self.source, funding=self.funding, budget_product=self.product, amount=100)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("transfer_list"))
        self.assertContains(response, 'name="budget_version"')
        payload = self.payload(version)
        payload["envelope"] = self.envelope.pk
        self.assertEqual(self.client.post(reverse("transfer_list"), payload).status_code, 302)
        transfer = BudgetTransfer.objects.latest("pk")
        self.assertEqual(transfer.envelope_id, other.pk)
        self.assertEqual(transfer.budget_version_id, version.pk)
        self.assertEqual(transfer.status, "pending")
        self.assertEqual(available(version, self.source.pk, self.funding.pk, self.product.pk), 90)
        self.assertEqual(self.balance(self.source), 100)

    def test_locked_and_deleted_versions_cannot_receive_transfers(self):
        from purchasing.flow import lock_envelope, delete_envelope_version
        locked = EnvelopeVersion.objects.create(envelope=self.envelope, label="Locked")
        lock_envelope(actor=self.admin, version_id=locked.pk)
        deleted = EnvelopeVersion.objects.create(envelope=self.envelope, label="Deleted")
        delete_envelope_version(actor=self.admin, version_id=deleted.pk)
        self.client.force_login(self.owner)
        for version in (locked, deleted):
            response = self.client.post(reverse("transfer_list"), self.payload(version))
            self.assertEqual(response.status_code, 200)
            self.assertIn("budget_version", response.context["header"].errors)
        pending_version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Before lock")
        transfer = self.create_transfer(version=pending_version)
        lock_envelope(actor=self.admin, version_id=pending_version.pk)
        with self.assertRaises(ValidationError):
            act(pk=transfer.pk, actor=self.owner, revision=0, action="submit")

    def test_direct_submission_failure_preserves_form_without_creating_a_draft(self):
        self.client.force_login(self.owner)
        payload = self.payload(self.budget)
        payload["amount"] = "101"
        before = BudgetTransfer.objects.count()
        events = BudgetHistoryEvent.objects.count()
        response = self.client.post(reverse("transfer_list"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["submission_errors"], ["Budget source insuffisant."])
        self.assertContains(response, '<div class="login-error" role="alert">')
        self.assertContains(response, "Budget source insuffisant.", count=1)
        self.assertEqual(response.context["formset"][0]["amount"].value(), "101")
        self.assertEqual(BudgetTransfer.objects.count(), before)
        self.assertEqual(BudgetHistoryEvent.objects.count(), events)
        self.assertEqual(self.balance(self.source), 100)

    def batch_payload(self, amounts):
        data = {"budget_version": self.budget.pk, "lines-TOTAL_FORMS": str(len(amounts)), "lines-INITIAL_FORMS": "0"}
        for index, amount in enumerate(amounts):
            for name, value in self.payload(self.budget).items():
                if name != "budget_version":
                    data[f"lines-{index}-{name}"] = value
            data[f"lines-{index}-amount"] = amount
        return data

    def shared_destination_payload(self, amounts):
        from .models import Support
        support = Support.objects.create(code="COMMON-DST", label="Destination commune")
        data = self.batch_payload(amounts)
        data.update({"shared_destination": "1", "destination_cdf": self.target.pk,
                     "destination_product": self.product.pk, "destination_funding": self.funding.pk,
                     "destination_support": support.pk})
        return data

    def test_multiple_sources_feed_common_destination_with_individual_approvals(self):
        self.client.force_login(self.owner)
        other_source = CostCenter.objects.create(code="OTHER-SRC", label="Autre source")
        other_source.managers.add(self.reviewer)
        self.budget = EnvelopeVersion.objects.create(envelope=self.envelope, label="Sources multiples")
        Allocation.objects.create(version=self.budget, cost_center=self.source, funding=self.funding,
                                  budget_product=self.product, amount=100)
        Allocation.objects.create(version=self.budget, cost_center=other_source, funding=self.funding,
                                  budget_product=self.product, amount=100)
        data = self.shared_destination_payload(["25.10", "35.20"])
        data["lines-1-source_cdf"] = other_source.pk
        # Per-row destination and a forged displayed total cannot change the common destination or amounts.
        data["lines-1-destination_cdf"] = self.source.pk
        data["destination_total"] = "9999"
        response = self.client.post(reverse("transfer_list"), data)
        self.assertEqual(response.status_code, 302)
        rows = list(BudgetTransfer.objects.exclude(pk=self.transfer.pk).order_by("pk"))
        self.assertEqual(sum(row.amount for row in rows), Decimal("60.30"))
        self.assertEqual([(row.source_cdf_id, row.destination_cdf_id) for row in rows],
                         [(self.source.pk, self.target.pk), (other_source.pk, self.target.pk)])
        self.assertTrue(all(row.destination_support_id == data["destination_support"] for row in rows))
        self.assertEqual(self.balance(self.target), 0)
        self.approve_transfer(rows[0])
        self.assertEqual(self.balance(self.target), Decimal("25.10"))
        rows[1].refresh_from_db()
        self.assertEqual(rows[1].status, "pending")
        self.approve_transfer(rows[1])
        self.assertEqual(self.balance(self.target), Decimal("60.30"))

    def test_transfer_without_source_or_destination_support_can_be_submitted(self):
        self.client.force_login(self.owner)
        data = self.shared_destination_payload(["25.10", "35.20"])
        data["destination_support"] = ""
        data["lines-0-source_support"] = ""
        data["lines-1-source_support"] = ""
        response = self.client.post(reverse("transfer_list"), data)
        self.assertRedirects(response, reverse("transfer_monitor"))
        rows = list(BudgetTransfer.objects.exclude(pk=self.transfer.pk).order_by("pk"))
        self.assertEqual([row.amount for row in rows], [Decimal("25.10"), Decimal("35.20")])
        self.assertTrue(all(row.source_support_id is None and row.destination_support_id is None
                            and row.status == "pending" for row in rows))

    def test_common_destination_ignores_deleted_and_blank_sources(self):
        self.client.force_login(self.owner)
        data = self.shared_destination_payload(["20", "200"])
        data["lines-1-DELETE"] = "on"
        data["lines-TOTAL_FORMS"] = "3"
        response = self.client.post(reverse("transfer_list"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BudgetTransfer.objects.count(), 2)
        self.assertEqual(self.balance(self.source), 80)

    def test_common_destination_budget_failure_rolls_back_every_source(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("transfer_list"), self.shared_destination_payload(["60", "60"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["submission_errors"], ["Budget source insuffisant."])
        self.assertEqual(BudgetTransfer.objects.count(), 1)
        self.assertEqual(self.balance(self.source), 100)

    def test_table_submits_each_row_with_its_own_validation(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("transfer_list"), self.batch_payload(["20", "30"]))
        self.assertRedirects(response, reverse("transfer_monitor"))
        rows = BudgetTransfer.objects.exclude(pk=self.transfer.pk)
        self.assertEqual(rows.count(), 2)
        for row in rows:
            self.assertEqual(row.status, "pending")
            self.assertEqual(row.steps.count(), 2)
        self.assertEqual(self.balance(self.source), 50)

    def test_table_stores_distinct_supports_per_side_and_per_row(self):
        from .models import Support
        source = Support.objects.create(code="SRC", label="Source")
        destination = Support.objects.create(code="DST", label="Destination")
        self.client.force_login(self.owner)
        data = self.batch_payload(["20", "30"])
        data.update({"lines-0-source_support": source.pk, "lines-0-destination_support": destination.pk,
                     "lines-1-source_support": destination.pk, "lines-1-destination_support": source.pk})
        response = self.client.post(reverse("transfer_list"), data)
        self.assertEqual(response.status_code, 302)
        rows = list(BudgetTransfer.objects.exclude(pk=self.transfer.pk).order_by("pk"))
        self.assertEqual([(t.source_support_id, t.destination_support_id) for t in rows],
                         [(source.pk, destination.pk), (destination.pk, source.pk)])
        self.assertTrue(all(t.support_id is None and t.status == "pending" for t in rows))
        response = self.client.get(reverse("transfer_detail", args=[rows[0].pk]))
        self.assertContains(response, '<th scope="row">Support</th>')
        self.assertContains(response, f"<td>{source}</td>", html=True)
        self.assertContains(response, f"<td>{destination}</td>", html=True)
        from io import BytesIO
        from openpyxl import load_workbook
        exported = self.client.get(reverse("transfer_list"), {"export": "xlsx"})
        workbook = load_workbook(BytesIO(exported.content))
        values = list(workbook.active.values)
        records = [dict(zip(values[0], row)) for row in values[1:]]
        record = next(row for row in records if row["Transfert"] == str(rows[0]))
        self.assertEqual(record["Support source"], str(source))
        self.assertEqual(record["Support destination"], str(destination))
        workbook.close()

    def test_table_header_has_no_common_support_and_rejects_unknown_row_support(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("transfer_list"))
        self.assertNotIn("support", response.context["header"].fields)
        self.assertContains(response, 'name="lines-0-source_support"')
        self.assertContains(response, 'name="lines-0-destination_support"')
        data = self.batch_payload(["20"])
        data["lines-0-destination_support"] = "999999"
        response = self.client.post(reverse("transfer_list"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("destination_support", response.context["formset"].forms[0].errors)
        self.assertEqual(BudgetTransfer.objects.count(), 1)

    def test_table_rolls_back_all_rows_when_combined_budget_is_insufficient(self):
        self.client.force_login(self.owner)
        events = BudgetHistoryEvent.objects.count()
        response = self.client.post(reverse("transfer_list"), self.batch_payload(["60", "60"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["submission_errors"], ["Budget source insuffisant."])
        self.assertEqual(BudgetTransfer.objects.count(), 1)
        self.assertEqual(BudgetHistoryEvent.objects.count(), events)
        self.assertEqual(self.balance(self.source), 100)

    def test_table_ignores_removed_and_empty_rows(self):
        self.client.force_login(self.owner)
        data = self.batch_payload(["20", "200"])
        data["lines-1-DELETE"] = "on"
        data["lines-TOTAL_FORMS"] = "3"
        response = self.client.post(reverse("transfer_list"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BudgetTransfer.objects.count(), 2)
        self.assertEqual(self.balance(self.source), 80)

    def test_table_requires_at_least_one_valid_row(self):
        self.client.force_login(self.owner)
        data = self.batch_payload(["20"])
        data["lines-0-DELETE"] = "on"
        response = self.client.post(reverse("transfer_list"), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["formset"].non_form_errors())
        self.assertEqual(BudgetTransfer.objects.count(), 1)

    def test_version_history_isolated_from_other_versions(self):
        other = EnvelopeVersion.objects.create(envelope=self.envelope, label="Other")
        foreign = self.create_transfer(version=other)
        transfer = self.submit()
        self.approve_transfer(transfer)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("version_transfers", args=[self.budget.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([t.pk for t in response.context["transfers"]], [transfer.pk])
        self.assertTrue(response.context["events"].exists())
        response = self.client.get(reverse("purchasing:budget_history"), {"version": self.budget.pk})
        self.assertTrue(any(str(transfer) in e.reason for e in response.context["timeline"]))
        response = self.client.get(reverse("purchasing:budget_history"), {"version": other.pk})
        self.assertFalse(any(str(transfer) in e.reason for e in response.context["timeline"]))
        source = next(r for r in response.context["state"]["rows"] if r["cdf"] == str(self.source))
        self.assertEqual(Decimal(source["transfers"]), 0)

    def test_version_history_enforces_owner_scope(self):
        foreign = self.create_transfer()
        foreign.created_by = self.reviewer
        foreign.save()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("version_transfers", args=[self.budget.pk]))
        self.assertEqual([t.pk for t in response.context["transfers"]], [self.transfer.pk])
        stranger = get_user_model().objects.create_user("no_history")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse("version_transfers", args=[self.budget.pk])).status_code, 403)

    def test_existing_transfer_cannot_switch_version(self):
        version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Other")
        self.transfer.budget_version = version
        with self.assertRaises(ValidationError):
            self.transfer.save()

    def test_approval_after_version_lock_is_refused_and_rejection_remains_possible(self):
        from purchasing.flow import lock_envelope
        version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Draft transfer")
        Allocation.objects.create(version=version, cost_center=self.source, funding=self.funding, budget_product=self.product, amount=100)
        transfer = self.create_transfer(version=version)
        transfer = act(pk=transfer.pk, actor=self.owner, revision=0, action="submit")
        step = transfer.steps.get(level=1)
        lock_envelope(actor=self.admin, version_id=version.pk)
        with self.assertRaises(ValidationError):
            act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve", step_id=step.pk)
        transfer = act(pk=transfer.pk, actor=self.reviewer, revision=1, action="reject", step_id=step.pk, reason="Version locked")
        self.assertEqual(transfer.status, "rejected")

    def test_version_with_transfers_cannot_be_deleted(self):
        from purchasing.flow import delete_envelope_version
        version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Used draft")
        self.create_transfer(version=version)
        with self.assertRaises(ValidationError):
            delete_envelope_version(actor=self.admin, version_id=version.pk)


class TransferVisibilityTests(TestCase):
    setUp = TransferTests.setUp
    create_transfer = TransferTests.create_transfer
    submit = TransferTests.submit
    payload = TransferTests.payload
    batch_payload = TransferTests.batch_payload
    approve_transfer = TransferTests.approve_transfer

    def create_pending_batch(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("transfer_list"), self.batch_payload(["10", "20", "30"]))
        return list(BudgetTransfer.objects.exclude(pk=self.transfer.pk).order_by("pk"))

    def test_global_batch_approval_validates_all_lines_and_workflows(self):
        lines = self.create_pending_batch()
        self.approve_transfer(lines[0])
        previous = list(lines[0].steps.values_list("approved_by_id", "approved_at"))
        self.client.force_login(self.admin)
        response = self.client.get(reverse("transfer_monitor"), {"status": "pending"})
        group = list(response.context["page"])[0]
        self.assertTrue(group["can_approve_all"])
        response = self.client.post(reverse("transfer_batch_approve", args=[group["number"]]),
                                    {"snapshot": group["snapshot"]}, follow=True)
        self.assertContains(response, "ligne(s) validée(s).")
        for line in lines:
            line.refresh_from_db()
            self.assertEqual(line.status, "approved")
            self.assertEqual(line.steps.filter(state="approved").count(), 2)
        self.assertEqual(list(lines[0].steps.values_list("approved_by_id", "approved_at")), previous)
        self.assertContains(response, 'status-APPROVED">Accompli')

    def test_batch_approval_is_forbidden_for_regular_manager(self):
        self.create_pending_batch()
        self.client.force_login(self.admin)
        group = list(self.client.get(reverse("transfer_monitor")).context["page"])[0]
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.post(reverse("transfer_batch_approve", args=[group["number"]]),
                         {"snapshot": group["snapshot"]}).status_code, 403)

    def test_batch_approval_rolls_back_all_lines_if_later_line_is_invalid(self):
        from .transfers import approve_batch
        from .models import BudgetTransferBatch
        lines = self.create_pending_batch()
        lines[-1].steps.all().delete()
        batch = BudgetTransferBatch.objects.get(key=lines[0].batch_id)
        with self.assertRaises(ValidationError):
            approve_batch(batch_pk=batch.pk, actor=self.admin,
                          revisions={str(line.pk): line.revision for line in lines})
        for line in lines:
            line.refresh_from_db()
            self.assertEqual(line.status, "pending")
            self.assertFalse(line.steps.filter(state="approved").exists())

    def test_batch_approval_rejects_stale_snapshot_and_terminal_lines(self):
        from .transfers import approve_batch
        from .models import BudgetTransferBatch
        lines = self.create_pending_batch()
        batch = BudgetTransferBatch.objects.get(key=lines[0].batch_id)
        revisions = {str(line.pk): line.revision for line in lines}
        act(pk=lines[0].pk, actor=self.admin, revision=1, action="cancel", reason="Erreur")
        with self.assertRaises(ValidationError):
            approve_batch(batch_pk=batch.pk, actor=self.admin, revisions=revisions)
        revisions[str(lines[0].pk)] = 2
        with self.assertRaises(ValidationError):
            approve_batch(batch_pk=batch.pk, actor=self.admin, revisions=revisions)
        self.assertFalse(lines[1].steps.filter(state="approved").exists())

    def test_admin_can_approve_entire_remaining_workflow(self):
        from workflow.models import ConfigurationAuditEvent
        transfer = self.submit()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("transfer_timeline", args=[transfer.pk])),
                            'value="approve_all"')
        response = self.client.post(reverse("transfer_detail", args=[transfer.pk]),
                                    {"action": "approve_all", "revision": 1})
        self.assertEqual(response.status_code, 302)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "approved")
        self.assertEqual(transfer.steps.filter(state="approved", approved_by=self.admin).count(), 2)
        self.assertEqual(ConfigurationAuditEvent.objects.filter(object_type="budget_transfer",
            object_id=transfer.pk, action="transfer.approve", actor=self.admin,
            payload__full_workflow=True).count(), 2)

    def test_full_workflow_preserves_previous_validator(self):
        transfer = self.submit()
        first = transfer.steps.get(level=1)
        act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve", step_id=first.pk)
        act(pk=transfer.pk, actor=self.admin, revision=2, action="approve_all")
        first.refresh_from_db()
        self.assertEqual(first.approved_by, self.reviewer)
        self.assertEqual(transfer.steps.get(level=2).approved_by, self.admin)

    def test_full_workflow_requires_global_permission_and_checks_revision_and_lock(self):
        transfer = self.submit()
        with self.assertRaises(PermissionDenied):
            act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve_all")
        with self.assertRaises(ValidationError):
            act(pk=transfer.pk, actor=self.admin, revision=0, action="approve_all")
        EnvelopeVersion.objects.filter(pk=self.budget.pk).update(locked_at=timezone.now())
        with self.assertRaises(ValidationError):
            act(pk=transfer.pk, actor=self.admin, revision=1, action="approve_all")
        self.assertFalse(transfer.steps.filter(state="approved").exists())

    def test_global_status_is_accomplished_only_after_all_lines_are_approved(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("transfer_list"), self.batch_payload(["10", "20", "30"]))
        lines = list(BudgetTransfer.objects.exclude(pk=self.transfer.pk).order_by("pk"))
        response = self.client.get(reverse("transfer_monitor"))
        self.assertEqual(list(response.context["page"])[0]["status_label"], "En cours")
        self.approve_transfer(lines[0])
        response = self.client.get(reverse("transfer_monitor"), {"status": "approved"})
        self.assertEqual(list(response.context["page"])[0]["status_label"], "En cours")
        self.approve_transfer(lines[1])
        self.approve_transfer(lines[2])
        response = self.client.get(reverse("transfer_monitor"))
        self.assertEqual(list(response.context["page"])[0]["status_label"], "Accompli")
        self.assertContains(response, 'status-badge status-APPROVED">Accompli')
        act(pk=lines[0].pk, actor=self.admin, revision=3, action="cancel", reason="Correction")
        response = self.client.get(reverse("transfer_monitor"))
        self.assertEqual(list(response.context["page"])[0]["status_label"], "Partiellement accompli")

    def test_global_status_handles_rejected_and_cancelled_lines(self):
        from .transfers import batch_status
        self.assertEqual(batch_status(["rejected"])[1], "Refusé")
        self.assertEqual(batch_status(["cancelled", "cancelled"])[1], "Annulé")
        self.assertEqual(batch_status(["approved", "rejected"])[1], "Partiellement accompli")

    def test_multiple_lines_share_a_group_and_separate_submissions_do_not(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("transfer_list"), self.batch_payload(["10", "20", "30"])).status_code, 302)
        lines = BudgetTransfer.objects.exclude(pk=self.transfer.pk).order_by("pk")
        batch_ids = set(lines.values_list("batch_id", flat=True))
        self.assertEqual(len(batch_ids), 1)
        self.assertNotIn(self.transfer.batch_id, batch_ids)
        response = self.client.get(reverse("transfer_monitor"))
        groups = list(response.context["page"])
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["line_count"], 3)
        self.assertEqual(groups[0]["total"], Decimal("60"))
        self.assertEqual(len(groups[0]["lines"]), 3)
        self.assertContains(response, "3 lignes")
        self.assertEqual(groups[0]["number"], groups[1]["number"] + 1)
        self.assertContains(response, f'aria-label="Numéro unique du transfert global : {groups[0]["number"]}">{groups[0]["number"]}</h3>')
        self.assertContains(response, "Numéro de transaction")
        for line in groups[0]["lines"]:
            self.assertContains(response, f'aria-label="Voir le workflow de la transaction {line.pk}"')
        filtered = self.client.get(reverse("transfer_monitor"), {"status": "pending"})
        self.assertEqual(list(filtered.context["page"])[0]["number"], groups[0]["number"])

    def test_filter_by_global_transfer_number(self):
        self.create_pending_batch()
        response = self.client.get(reverse("transfer_monitor"))
        number = list(response.context["page"])[0]["number"]
        response = self.client.get(reverse("transfer_monitor"), {"number": number, "status": "pending"})
        groups = list(response.context["page"])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["number"], number)
        self.assertEqual(len(groups[0]["lines"]), 3)
        self.assertEqual(response.context["number"], str(number))
        for value in ("999999999999999999", "invalid", "-1", "9" * 100):
            response = self.client.get(reverse("transfer_monitor"), {"number": value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page"].paginator.count, 0)

    def test_group_totals_only_include_visible_and_filtered_lines(self):
        transfer = self.submit()
        other = self.create_transfer("20")
        other.batch_id = transfer.batch_id
        other.created_by = self.admin
        other.source_cdf = self.target
        other.destination_cdf = self.source
        other.save()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("transfer_monitor"))
        group = list(response.context["page"])[0]
        self.assertEqual(group["total"], Decimal("60"))
        self.assertEqual(group["line_count"], 1)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("transfer_monitor"), {"status": "pending"})
        group = list(response.context["page"])[0]
        self.assertEqual(group["total"], Decimal("60"))
        self.assertEqual(group["line_count"], 1)

    def test_creation_page_only_contains_creation_form(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("transfer_list"))
        self.assertContains(response, "Créer un transfert")
        self.assertContains(response, 'id="transfer-lines-form"')
        self.assertContains(response, '<summary>Transferts</summary>')
        self.assertNotContains(response, "Demandes de transfert")
        self.assertNotContains(response, "Exporter les demandes de transfert")

    def test_read_only_user_is_directed_to_transfer_list(self):
        actor = get_user_model().objects.create_user("transfer_reader")
        actor.user_permissions.add(Permission.objects.get(codename="view_all_transfers"))
        self.client.force_login(actor)
        self.assertRedirects(self.client.get(reverse("transfer_list")), reverse("transfer_monitor"))
        response = self.client.get(reverse("purchasing:budget_home"))
        self.assertContains(response, '<summary>Transferts</summary>')
        self.assertNotContains(response, "Créer un transfert")

    def test_global_permission_does_not_assign_personal_notifications(self):
        transfer = self.submit()
        self.target.managers.set([self.owner])
        self.client.force_login(self.admin)
        response = self.client.get(reverse("my_validations"))
        self.assertEqual(response.context["transfer_tasks"], [])
        self.assertEqual(response.context["pending_validation_count"], 0)
        act(pk=transfer.pk, actor=self.reviewer, revision=1, action="approve",
            step_id=transfer.steps.get(level=1).pk)
        response = self.client.get(reverse("my_validations"))
        self.assertEqual(response.context["transfer_tasks"], [])
        self.assertEqual(response.context["pending_validation_count"], 0)
        self.assertContains(self.client.get(reverse("transfer_timeline", args=[transfer.pk])),
                            'name="action" value="approve"')
        self.target.managers.set([self.admin])
        response = self.client.get(reverse("my_validations"))
        self.assertEqual([step.pk for step in response.context["transfer_tasks"]],
                         [transfer.steps.get(level=2).pk])
        self.assertEqual(response.context["pending_validation_count"], 1)

    def test_unassigned_step_does_not_notify_global_validator(self):
        self.source.managers.clear()
        self.submit()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("my_validations"))
        self.assertEqual(response.context["transfer_tasks"], [])
        self.assertEqual(response.context["pending_validation_count"], 0)

    def test_global_decision_permission_works_outside_managed_cdf(self):
        transfer = self.submit()
        actor = get_user_model().objects.create_user("global_validator")
        actor.user_permissions.add(Permission.objects.get(codename="decide_any_budgettransfer"))
        self.client.force_login(actor)
        self.assertContains(self.client.get(reverse("transfer_monitor")), f'aria-label="Voir le workflow de la transaction {transfer.pk}"')
        self.assertContains(self.client.get(reverse("transfer_monitor")), 'aria-label="Valider"')
        self.assertContains(self.client.get(reverse("transfer_monitor")), 'aria-label="Refuser"')
        response = self.client.get(reverse("transfer_timeline", args=[transfer.pk]))
        self.assertContains(response, 'name="action" value="approve"')
        self.assertContains(response, 'name="action" value="reject"')
        self.assertEqual(response.context["actionable_step_ids"], [transfer.steps.get(level=1).pk])
        for revision, level in ((1, 1), (2, 2)):
            response = self.client.post(reverse("transfer_detail", args=[transfer.pk]), {
                "action": "approve", "revision": revision,
                "step_id": transfer.steps.get(level=level).pk,
            })
            self.assertEqual(response.status_code, 302)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "approved")
        self.assertEqual(transfer.steps.filter(approved_by=actor).count(), 2)
        response = self.client.get(reverse("transfer_timeline", args=[transfer.pk]))
        self.assertNotContains(response, 'name="action" value="approve"')

    def test_global_validator_can_reject_unassigned_step(self):
        self.source.managers.clear()
        transfer = self.submit()
        step = transfer.steps.get(level=1)
        self.assertEqual(step.state, "unassigned")
        act(pk=transfer.pk, actor=self.admin, revision=1, action="reject",
            step_id=step.pk, reason="Transfert incorrect")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "rejected")

    def test_staff_status_alone_does_not_allow_global_decision(self):
        transfer = self.submit()
        actor = get_user_model().objects.create_user("staff_validator", is_staff=True)
        with self.assertRaises(PermissionDenied):
            act(pk=transfer.pk, actor=actor, revision=1, action="approve",
                step_id=transfer.steps.get(level=1).pk)

    def test_requester_cannot_decide_from_timeline(self):
        transfer = self.submit()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("transfer_timeline", args=[transfer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="action" value="approve"')
        self.assertNotContains(response, 'name="action" value="reject"')
    def test_reviewer_sees_only_current_validation_and_separate_timeline(self):
        transfer = self.submit()
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse("transfer_detail", args=[transfer.pk]))
        self.assertEqual(len(response.context["rows"]), 1)
        self.assertNotContains(response, "Responsable du CDF destination")
        response = self.client.get(reverse("transfer_timeline", args=[transfer.pk]))
        self.assertContains(response, "Responsable du CDF destination")
        self.assertContains(response, 'aria-current="step"')
        self.assertContains(self.client.get(reverse("transfer_monitor")), f'aria-label="Voir le workflow de la transaction {transfer.pk}"')

    def test_unrelated_user_cannot_read_timeline_or_listed_transfer(self):
        transfer = self.submit()
        outsider = get_user_model().objects.create_user("outsider")
        outsider.user_permissions.add(Permission.objects.get(codename="add_budgettransfer"))
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("transfer_timeline", args=[transfer.pk])).status_code, 404)
        response = self.client.get(reverse("transfer_monitor"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].paginator.count, 0)
