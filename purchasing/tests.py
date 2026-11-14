from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from budgeting.models import BudgetProduct, CostCenter, DetailedProduct, Funding
from suppliers.models import Supplier
from workflow.models import AuditEvent
from .exceptions import PurchaseRequestConflict, PurchaseRequestError
from .models import PurchaseRequest
from .services import add_purchase_request_line, cancel_purchase_request, create_purchase_request
from .services import update_purchase_request_line, delete_purchase_request_line


class PurchaseDraftTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="owner")
        from django.contrib.auth.models import Permission
        self.owner.user_permissions.add(Permission.objects.get(
            content_type__app_label="purchasing", codename="add_purchaserequest"))
        self.other = get_user_model().objects.create_user(username="other")
        self.supplier = Supplier.objects.create(code="S", name="Supplier")
        product = BudgetProduct.objects.create(code="BP", label="Product")
        self.values = dict(
            detailed_product=DetailedProduct.objects.create(code="P", label="Detail", budget_product=product),
            cost_center=CostCenter.objects.create(code="C", label="CDF"),
            funding=Funding.objects.create(code="F", label="Funding"),
            description="Line", quantity=Decimal("1.23"),
            unit_price=Decimal("4.57"), vat_rate=Decimal("21"),
        )
        self.request = create_purchase_request(actor=self.owner, supplier=self.supplier)

    def add_line(self, **overrides):
        arguments = dict(request_id=self.request.pk, actor=self.owner,
                         expected_revision=self.request.revision, **self.values)
        arguments.update(overrides)
        return add_purchase_request_line(**arguments)

    def test_ach001_exact_amounts_without_rounding(self):
        line = self.add_line()
        self.assertEqual(line.total_htva, Decimal("5.6211"))
        self.assertEqual(line.total_vat, Decimal("1.180431"))
        self.assertEqual(line.total_tvac, Decimal("6.801531"))
        self.assertEqual(AuditEvent.objects.count(), 2)
        self.assertEqual(self.request.status, PurchaseRequest.Status.DRAFT)

    def test_ach005_only_requester_can_edit(self):
        with self.assertRaises(PermissionDenied):
            self.add_line(actor=self.other)
        self.assertFalse(self.request.lines.exists())
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_stale_revision_is_rejected_without_side_effects(self):
        self.add_line()
        with self.assertRaises(PurchaseRequestConflict):
            self.add_line()
        self.assertEqual(self.request.lines.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 2)

    def test_validation_and_audit_rollback(self):
        for values in ({"quantity": Decimal("0")}, {"unit_price": Decimal("-1")},
                       {"vat_rate": None}, {"vat_rate": Decimal("101")},
                       {"id": 999}):
            with self.assertRaises(ValidationError):
                self.add_line(**values)
        self.request.refresh_from_db()
        self.assertEqual(self.request.revision, 1)
        self.assertFalse(self.request.lines.exists())
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_explicit_zero_vat_is_allowed(self):
        self.assertEqual(self.add_line(vat_rate=Decimal("0")).total_vat, 0)

    def test_ach003_ach005_terminal_and_submitted_requests_are_not_editable(self):
        for status in ("SUBMITTED", "REJECTED", "CANCELLED", "ORDERED"):
            self.request.status = status
            self.request.save()
            with self.assertRaises(PurchaseRequestError):
                self.add_line()

    def test_ach004_draft_cancellation_is_idempotent_and_audited(self):
        result = cancel_purchase_request(request_id=self.request.pk, actor=self.owner, expected_revision=1)
        repeated = cancel_purchase_request(request_id=result.pk, actor=self.owner, expected_revision=result.revision)
        self.assertEqual(repeated.status, "CANCELLED")
        self.assertEqual(AuditEvent.objects.count(), 2)
        with self.assertRaises(PurchaseRequestError):
            self.add_line(expected_revision=repeated.revision)

    def test_inactive_requester_is_denied(self):
        self.owner.is_active = False
        self.owner.save()
        with self.assertRaises(PermissionDenied):
            self.add_line()

    def test_numbers_are_generated_and_unique(self):
        other = create_purchase_request(actor=self.owner, supplier=self.supplier)
        self.assertNotEqual(other.number, self.request.number)
        self.assertRegex(other.number, r"^DA-\d{4}-\d{4,}$")

    def test_line_edit_and_delete_are_audited(self):
        line = self.add_line()
        edited = update_purchase_request_line(request_id=self.request.pk, line_id=line.pk,
            actor=self.owner, expected_revision=2, quantity=Decimal("2"))
        self.assertEqual(edited.quantity, 2)
        delete_purchase_request_line(request_id=self.request.pk, line_id=line.pk,
            actor=self.owner, expected_revision=3)
        self.assertFalse(self.request.lines.exists())
        event = self.request.audit_events.last()
        self.assertEqual(event.action, "line.deleted")
        self.assertEqual(event.payload["quantity"], "2.00")

    def test_pages_are_private_even_when_ids_are_known(self):
        self.client.force_login(self.other)
        self.assertRedirects(self.client.get("/achats/"), reverse("my_validations"))
        self.assertNotContains(self.client.get("/achats/", follow=True), self.request.number)
        for path in (f"/achats/{self.request.pk}/", f"/achats/{self.request.pk}/modifier/",
                     f"/achats/{self.request.pk}/annuler/", f"/achats/{self.request.pk}/lignes/ajouter/"):
            self.assertEqual(self.client.get(path).status_code, 404)
            self.assertIn(self.client.post(path, {"expected_revision": 1}).status_code, (404, 405))

    def test_interface_line_creation_edit_and_cancellation(self):
        self.client.force_login(self.owner)
        data = {key: value.pk if hasattr(value, "pk") else str(value) for key, value in self.values.items()}
        data["expected_revision"] = 1
        result = self.client.post(f"/achats/{self.request.pk}/lignes/ajouter/", data)
        self.assertEqual(result.status_code, 302)
        detail = self.client.get(f"/achats/{self.request.pk}/")
        self.assertContains(detail, "6,80")
        self.assertNotContains(detail, "6,801531")
        stale = self.client.post(f"/achats/{self.request.pk}/lignes/ajouter/", data)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.request.lines.count(), 1)
        self.assertEqual(self.client.get(f"/achats/{self.request.pk}/annuler/").status_code, 200)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "DRAFT")
        self.assertEqual(self.client.post(f"/achats/{self.request.pk}/annuler/", {"expected_revision": 2}).status_code, 302)
        self.assertNotContains(self.client.get(f"/achats/{self.request.pk}/"), "Ajouter une ligne")

    def test_authentication_and_csrf_required(self):
        from django.test import Client
        self.assertEqual(self.client.get("/achats/").status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(f"/achats/{self.request.pk}/annuler/", {"expected_revision": 1}).status_code, 403)

    def test_edit_post_cannot_change_owner_or_status(self):
        self.client.force_login(self.owner)
        result = self.client.post(f"/achats/{self.request.pk}/modifier/", {
            "supplier": self.supplier.pk, "expected_revision": 1, "status": "ORDERED", "created_by": self.other.pk})
        self.assertEqual(result.status_code, 302)
        self.request.refresh_from_db()
        self.assertEqual(self.request.created_by, self.owner)
        self.assertEqual(self.request.status, "DRAFT")
