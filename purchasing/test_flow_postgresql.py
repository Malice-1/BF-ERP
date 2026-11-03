from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, close_old_connections, transaction, DatabaseError
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from accounts.models import ValidationFunction
from accounts.services import publish_authorization
from budgeting.models import CostCenter, Funding, BudgetProduct, DetailedProduct
from suppliers.models import Supplier
from .models import (AnnualEnvelope, EnvelopeVersion, Allocation, WorkflowVersion, ApprovalRule,
    ApprovalStep, PurchaseOrder, BudgetEntry, Submission)
from .services import create_purchase_request, add_purchase_request_line
from . import flow
from .exceptions import PurchaseRequestError, PurchaseRequestConflict


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL transaction locks")
class PostgreSQLPurchaseFlowTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", "a@example.test", "password")
        self.owner = User.objects.create_user("owner")
        self.first = User.objects.create_user("first")
        self.second = User.objects.create_user("second")
        self.supplier = Supplier.objects.create(code="S", name="Supplier")
        self.cdf = CostCenter.objects.create(code="C", label="CDF")
        self.funding = Funding.objects.create(code="F", label="Funding")
        self.product = BudgetProduct.objects.create(code="B", label="Product")
        self.detail = DetailedProduct.objects.create(code="D", label="Detail", budget_product=self.product)
        self.function = ValidationFunction.objects.create(code="VALID", label="Validation", position=1)
        for user in (self.first, self.second):
            publish_authorization(actor=self.admin, user=user, function=self.function,
                valid_from=timezone.now() - timedelta(days=1))
        self.envelope = AnnualEnvelope.objects.create(year=timezone.localdate().year)
        self.budget = EnvelopeVersion.objects.create(envelope=self.envelope, label="Initial")
        Allocation.objects.create(version=self.budget, cost_center=self.cdf, funding=self.funding,
            budget_product=self.product, amount=1000)
        flow.activate_envelope(actor=self.admin, version_id=self.budget.pk)
        self.workflow = WorkflowVersion.objects.create(label="Initial")
        ApprovalRule.objects.create(version=self.workflow, label="Role", function=self.function)
        flow.activate_workflow(actor=self.admin, version_id=self.workflow.pk)

    def draft(self, price="600"):
        purchase = create_purchase_request(actor=self.owner, supplier=self.supplier)
        add_purchase_request_line(request_id=purchase.pk, actor=self.owner, expected_revision=purchase.revision,
            detailed_product=self.detail, cost_center=self.cdf, funding=self.funding,
            description="Line", quantity=Decimal("1"), unit_price=Decimal(price), vat_rate=Decimal("0"))
        purchase.refresh_from_db()
        return purchase

    def parallel(self, tasks):
        barrier = Barrier(len(tasks))
        def run(task):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return task()
            except PurchaseRequestError:
                return "blocked"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            return list(executor.map(run, tasks))

    def test_t001_t002_concurrent_reservations_do_not_overspend(self):
        purchases = [self.draft(), self.draft()]
        def submit(purchase):
            actor = get_user_model().objects.get(pk=self.owner.pk)
            flow.submit_purchase(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision)
            return "submitted"
        result = self.parallel([lambda p=p: submit(p) for p in purchases])
        self.assertCountEqual(result, ["submitted", "blocked"])
        self.assertEqual(BudgetEntry.objects.filter(state="reserved").count(), 1)
        self.assertEqual(flow.available(self.budget, self.cdf.pk, self.funding.pk, self.product.pk), 400)

    def test_t005_simultaneous_role_approval_creates_one_order(self):
        purchase = self.draft()
        purchase = flow.submit_purchase(request_id=purchase.pk, actor=self.owner, expected_revision=purchase.revision)
        step = ApprovalStep.objects.get()
        def approve(user_id):
            actor = get_user_model().objects.get(pk=user_id)
            flow.decide(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision,
                step_id=step.pk, decision="approve")
            return "approved"
        result = self.parallel([lambda: approve(self.first.pk), lambda: approve(self.second.pk)])
        self.assertCountEqual(result, ["approved", "blocked"])
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(BudgetEntry.objects.filter(state="committed").count(), 1)
        self.assertEqual(ApprovalStep.objects.filter(state="approved", evidence__isnull=True).count(), 1)

    def test_activation_and_reservation_share_annual_lock(self):
        purchase = self.draft()
        new = EnvelopeVersion.objects.create(envelope=self.envelope, label="Reduced")
        Allocation.objects.create(version=new, cost_center=self.cdf, funding=self.funding, budget_product=self.product, amount=100)
        def activate():
            actor = get_user_model().objects.get(pk=self.admin.pk)
            flow.activate_envelope(actor=actor, version_id=new.pk)
            return "activated"
        def submit():
            actor = get_user_model().objects.get(pk=self.owner.pk)
            flow.submit_purchase(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision)
            return "submitted"
        result = self.parallel([activate, submit])
        self.assertIn("activated", result)
        self.envelope.refresh_from_db()
        self.assertEqual(self.envelope.active_version_id, new.pk)
        balance = flow.available(new, self.cdf.pk, self.funding.pk, self.product.pk)
        self.assertEqual(balance, -500 if "submitted" in result else 100)

    def test_same_request_double_submission_does_not_duplicate_ledger(self):
        purchase = self.draft()
        def submit():
            flow.submit_purchase(request_id=purchase.pk, actor=get_user_model().objects.get(pk=self.owner.pk),
                expected_revision=purchase.revision)
            return "submitted"
        self.assertCountEqual(self.parallel([submit, submit]), ["submitted", "blocked"])
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(BudgetEntry.objects.count(), 1)

    def test_sql_guards_protect_published_configuration_and_history(self):
        purchase = self.draft()
        flow.submit_purchase(request_id=purchase.pk, actor=self.owner, expected_revision=purchase.revision)
        for mutation in (
            lambda: WorkflowVersion.objects.filter(pk=self.workflow.pk).update(label="Changed"),
            lambda: self.workflow.rules.all().update(minimum_htva=999),
            lambda: self.budget.allocations.all().update(amount=9999),
            lambda: Submission.objects.all().update(supplier_data={"name": "Changed"}),
            lambda: purchase.audit_events.all().update(action="Changed"),
        ):
            with self.assertRaises(DatabaseError), transaction.atomic():
                mutation()
