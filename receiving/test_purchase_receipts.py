from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from purchasing import test_flow as fixtures
from .models import Warehouse, StockBalance, StockMovement, PurchaseReceipt
from .purchases import receive_purchase, purchase_progress, line_progress
from .services import move


class PurchaseReceiptTests(TestCase):
    grant = fixtures.PurchaseFlowTests.grant
    budget = fixtures.PurchaseFlowTests.budget
    draft = fixtures.PurchaseFlowTests.draft
    submit = fixtures.PurchaseFlowTests.submit
    act = fixtures.PurchaseFlowTests.act

    def setUp(self):
        fixtures.PurchaseFlowTests.setUp(self)
        self.warehouse = Warehouse.objects.create(code="WH", label="Réception")
        self.other_warehouse = Warehouse.objects.create(code="WH2", label="Second dépôt")
        self.line = self.purchase.lines.get()
        self.line.quantity = Decimal("5")
        self.line.save()
        self.order(self.purchase)
        self.receiver = get_user_model().objects.create_user("receiver")
        self.receiver.user_permissions.add(Permission.objects.get(codename="manage_stock"))

    def order(self, purchase):
        self.submit(purchase)
        purchase.refresh_from_db()
        while purchase.status != "ORDERED":
            self.act(self.first, purchase=purchase)
            purchase.refresh_from_db()

    def receive(self, quantity="2", **kwargs):
        data = dict(actor=self.receiver, purchase_id=self.purchase.pk, warehouse=self.warehouse,
                    reason="Livraison BL-001", token=uuid4(), quantities=[(self.line.pk, Decimal(quantity))])
        data.update(kwargs)
        return receive_purchase(**data)

    def test_partial_then_complete_receipt_updates_stock_and_purchase_progress(self):
        self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "none")
        first = self.receive()
        self.assertEqual(first.lines.get().movement.quantity, 2)
        self.assertEqual(StockBalance.objects.get(warehouse=self.warehouse, product=self.detail).quantity, 2)
        self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "partial")
        line_progress(self.purchase, [self.line])
        self.assertEqual(self.line.received_quantity, 2)
        self.assertEqual(self.line.remaining_quantity, 3)
        self.receive("3", warehouse=self.other_warehouse)
        self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "complete")
        self.assertEqual(self.purchase.audit_events.filter(action="stock.purchase_receipt").count(), 2)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "ORDERED")

    def test_cannot_receive_more_than_ordered_and_does_not_write_anything(self):
        self.receive("4")
        with self.assertRaises(ValidationError):
            self.receive("2")
        self.assertEqual(PurchaseReceipt.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(StockBalance.objects.get().quantity, 4)

    def test_idempotency_and_conflicting_replay(self):
        token = uuid4()
        receipt = self.receive("5", token=token)
        self.assertEqual(self.receive("5", token=token).pk, receipt.pk)
        with self.assertRaises(ValidationError):
            self.receive("4", token=token)
        self.assertEqual(StockBalance.objects.get().quantity, 5)
        self.assertEqual(PurchaseReceipt.objects.count(), 1)

    def test_permission_state_foreign_lines_zero_and_negative_quantities(self):
        with self.assertRaises(PermissionDenied):
            self.receive(actor=self.owner)
        draft = self.draft("1")
        with self.assertRaises(ValidationError):
            self.receive(purchase_id=draft.pk)
        for quantities in ([(draft.lines.get().pk, Decimal(1))], [(self.line.pk, Decimal(0))],
                           [(self.line.pk, Decimal(-1))], [(self.line.pk, Decimal(1)), (self.line.pk, Decimal(1))]):
            with self.assertRaises(ValidationError):
                self.receive(quantities=quantities)
        self.assertFalse(PurchaseReceipt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_receipt_is_atomic_if_a_stock_write_fails(self):
        other = self.draft("1", lines=2)
        self.order(other)
        lines = list(other.lines.all())
        original = move
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise ValidationError("Échec du second mouvement")
            return original(**kwargs)

        with patch("receiving.purchases.move", side_effect=fail_second):
            with self.assertRaises(ValidationError):
                self.receive(purchase_id=other.pk, quantities=[(line.pk, Decimal(1)) for line in lines])
        self.assertFalse(PurchaseReceipt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(StockBalance.objects.exists())

    def test_stock_operations_without_receipt_do_not_change_purchase_fulfilment(self):
        move(actor=self.receiver, warehouse=self.warehouse, product=self.detail, kind="receipt",
             quantity=Decimal(10), reason="Entrée manuelle", token=uuid4())
        self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "none")
        self.receive("5")
        move(actor=self.receiver, warehouse=self.warehouse, product=self.detail, kind="issue",
             quantity=Decimal(15), reason="Utilisation", token=uuid4())
        self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "complete")

    def test_stock_user_can_receive_without_financial_permissions(self):
        self.client.force_login(self.receiver)
        response = self.client.get(reverse("purchase_receipts"))
        self.assertContains(response, self.purchase.number)
        response = self.client.get(reverse("purchase_receive", args=[self.purchase.pk]))
        self.assertContains(response, "Reste à recevoir")
        self.assertNotContains(response, "Prix HTVA")
        token = str(uuid4())
        data = {"warehouse": self.warehouse.pk, "reason": "Bon BL-2", "token": token,
                "lines-TOTAL_FORMS": 1, "lines-INITIAL_FORMS": 1,
                "lines-0-line_id": self.line.pk, "lines-0-quantity": "2"}
        response = self.client.post(reverse("purchase_receive", args=[self.purchase.pk]), data, follow=True)
        self.assertContains(response, "Partiellement réceptionnée")
        self.assertEqual(PurchaseReceipt.objects.count(), 1)
        self.client.post(reverse("purchase_receive", args=[self.purchase.pk]), data)
        self.assertEqual(PurchaseReceipt.objects.count(), 1)
        self.assertContains(self.client.get(reverse("stock_movements")), self.purchase.number)

    def test_requester_sees_received_quantities_and_receipt_history(self):
        self.receive()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("purchasing:detail", args=[self.purchase.pk]))
        self.assertContains(response, "Partiellement réceptionnée")
        self.assertContains(response, "Réceptions liées à la demande")
        self.assertEqual(response.context["lines"][0].received_quantity, 2)
        self.assertEqual(response.context["lines"][0].remaining_quantity, 3)
        self.assertContains(self.client.get(reverse("purchasing:list")), "Partiellement réceptionnée")
        self.assertEqual(self.client.get(reverse("purchase_receipts")).status_code, 403)

    def test_immutable_receipt_and_receipt_line(self):
        receipt = self.receive()
        for record in (receipt, receipt.lines.get()):
            with self.assertRaises(ValidationError):
                record.save()
            with self.assertRaises(ValidationError):
                record.delete()
