from decimal import Decimal
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase
from django.urls import reverse
from budgeting.models import BudgetProduct
from purchasing.models import DetailedProduct
from .models import Warehouse, StockBalance, StockMovement
from .services import move


class StockTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_superuser("stock", password="test")
        self.source = Warehouse.objects.create(code="A", label="A")
        self.target = Warehouse.objects.create(code="B", label="B")
        bi = BudgetProduct.objects.create(code="P", label="P")
        self.product = DetailedProduct.objects.create(code="P", label="P", budget_product=bi)

    def move(self, kind="receipt", quantity="10", **kwargs):
        data = dict(actor=self.actor, warehouse=self.source, product=self.product, kind=kind,
                    quantity=Decimal(quantity), reason="Test", token=uuid4())
        data.update(kwargs)
        return move(**data)

    def quantity(self, warehouse):
        return StockBalance.objects.get(warehouse=warehouse, product=self.product).quantity

    def test_receipt_issue_transfer_inventory_and_history(self):
        self.move()
        self.move("issue", "2")
        self.move("transfer", "3", destination=self.target)
        self.assertEqual(self.quantity(self.source), 5)
        self.assertEqual(self.quantity(self.target), 3)
        adjustment = self.move("inventory", "4")
        self.assertEqual(adjustment.delta, -1)
        self.move("inventory", "0")
        self.assertEqual(self.quantity(self.source), 0)
        self.assertEqual(StockMovement.objects.count(), 5)

    def test_insufficient_transfer_is_atomic(self):
        self.move()
        with self.assertRaises(ValidationError):
            self.move("transfer", "11", destination=self.target)
        self.assertEqual(self.quantity(self.source), 10)
        self.assertFalse(StockBalance.objects.filter(warehouse=self.target).exists())
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_idempotency_and_conflicting_replay(self):
        token = uuid4()
        first = self.move(token=token)
        self.assertEqual(self.move(token=token).pk, first.pk)
        self.assertEqual(self.quantity(self.source), 10)
        with self.assertRaises(ValidationError):
            self.move(quantity="9", token=token)

    def test_permissions_and_movement_immutability(self):
        other = get_user_model().objects.create_user("other")
        with self.assertRaises(PermissionDenied):
            self.move(actor=other)
        movement = self.move()
        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("stock")).status_code, 403)
        self.client.force_login(self.actor)
        self.assertContains(self.client.get(reverse("stock")), "Configuration des dépôts")

    def test_invalid_quantities_or_depot_pairs_leave_no_writes(self):
        for kind, quantity, destination in [("receipt", "0", None), ("issue", "-1", None), ("transfer", "1", self.source), ("receipt", "1", self.target)]:
            with self.assertRaises(ValidationError):
                self.move(kind, quantity, destination=destination)
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(StockBalance.objects.exists())

    def test_http_movement_form_round_trip(self):
        self.client.force_login(self.actor)
        token = self.client.get(reverse("stock_movements")).context["form"].initial["token"]
        data = {"action": "movement", "warehouse": self.source.pk, "product": self.product.pk,
                "kind": "receipt", "quantity": "2.5", "reason": "Livraison", "token": str(token)}
        self.assertEqual(self.client.post(reverse("stock_movements"), data).status_code, 302)
        self.assertEqual(self.client.post(reverse("stock_movements"), data).status_code, 302)
        self.assertEqual(self.quantity(self.source), Decimal("2.5"))

    def test_warehouse_tab_creation_and_configuration(self):
        self.client.force_login(self.actor)
        response = self.client.get(reverse("stock"))
        self.assertContains(response, reverse("warehouses"))
        self.assertContains(response, reverse("stock_movements"))
        self.assertContains(response, reverse("stock_balances"))
        self.assertNotContains(response, "<table")
        self.assertNotIn("form", response.context)
        self.assertNotContains(response, "<summary>")
        self.assertEqual(self.client.post(reverse("warehouses"), {"code": "C", "label": "Central"}).status_code, 302)
        warehouse = Warehouse.objects.get(code="C")
        self.assertEqual(self.client.post(reverse("warehouse_edit", args=[warehouse.pk]),
            {"code": "CENT", "label": "Central principal"}).status_code, 302)
        warehouse.refresh_from_db()
        self.assertEqual(warehouse.label, "Central principal")
        response = self.client.post(reverse("warehouse_edit", args=[warehouse.pk]),
            {"code": self.source.code, "label": "Doublon"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        warehouse.refresh_from_db()
        self.assertEqual(warehouse.code, "CENT")

    def test_warehouse_read_only_and_write_permissions(self):
        reader = get_user_model().objects.create_user("reader")
        reader.user_permissions.add(Permission.objects.get(codename="view_stockbalance"))
        self.client.force_login(reader)
        response = self.client.get(reverse("warehouses"))
        self.assertContains(response, self.source.code)
        self.assertNotContains(response, "Nouveau dépôt")
        self.assertEqual(self.client.post(reverse("warehouses"), {"code": "C", "label": "C"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("warehouse_edit", args=[self.source.pk]),
            {"code": "A", "label": "Modifié"}).status_code, 403)
        self.source.refresh_from_db()
        self.assertEqual(self.source.label, "A")

    def test_warehouse_only_permissions_expose_stock_section(self):
        manager = get_user_model().objects.create_user("warehouse_manager")
        manager.user_permissions.add(Permission.objects.get(codename="change_warehouse"))
        self.client.force_login(manager)
        response = self.client.get(reverse("warehouse_edit", args=[self.source.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["nav_section"], "stock")
        self.assertContains(response, reverse("warehouses"))
        self.assertNotContains(response, "Nouveau dépôt")
        self.assertEqual(self.client.post(reverse("warehouses"), {"code": "C", "label": "C"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("warehouse_edit", args=[self.source.pk]),
            {"code": "A", "label": "Modifié"}).status_code, 302)
        self.assertEqual(self.client.get(reverse("stock")).status_code, 200)
        self.assertEqual(self.client.get(reverse("stock_movements")).status_code, 403)
        self.assertEqual(self.client.get(reverse("stock_balances")).status_code, 403)
