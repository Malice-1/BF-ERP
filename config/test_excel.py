from io import BytesIO
from decimal import Decimal
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook
from budgeting import test_transfers as fixtures
from budgeting.models import BudgetHistoryEvent
from purchasing.models import EnvelopeVersion, AnnualEnvelope, PurchaseRequest, PurchaseRequestLine, DetailedProduct
from receiving.models import Warehouse, StockBalance, StockMovement
from suppliers.models import Supplier


class ExcelExportTests(TestCase):
    setUp = fixtures.TransferTests.setUp
    create_transfer = fixtures.TransferTests.create_transfer
    submit = fixtures.TransferTests.submit

    def test_budget_product_export_follows_search(self):
        from budgeting.models import BudgetProduct
        BudgetProduct.objects.create(code="MATCH-01", label="Selected product")
        BudgetProduct.objects.create(code="OTHER-02", label="Other product")
        self.client.force_login(self.admin)
        workbook = self.workbook("purchasing:budget_products", {"q": "match"})
        self.assertEqual(list(workbook.active.values), [("Code", "Libellé"), ("MATCH-01", "Selected product")])
        workbook.close()

    def test_budget_export_contains_only_the_selected_version(self):
        from purchasing.models import Allocation
        version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Selected export")
        Allocation.objects.create(version=version, cost_center=self.source, funding=self.funding,
                                  budget_product=self.product, amount=250)
        self.client.force_login(self.admin)
        workbook = self.workbook("purchasing:budgets", {"version": version.pk})
        rows = list(workbook.active.values)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], version.label)
        self.assertEqual(rows[1][5], 250)
        workbook.close()

    def workbook(self, name, params=None, args=None):
        response = self.client.get(reverse(name, args=args), dict(params or {}, export="xlsx"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("attachment;", response["Content-Disposition"])
        return load_workbook(BytesIO(response.content))

    def test_exports_are_valid_workbooks_and_preserve_number_types(self):
        self.client.force_login(self.admin)
        for name in ("transfer_list", "transfer_monitor", "purchasing:allocation_versions", "purchasing:budgets"):
            workbook = self.workbook(name)
            self.assertGreaterEqual(workbook.active.max_row, 2)
            self.assertEqual(workbook.active.freeze_panes, "A2")
            self.assertTrue(workbook.active.auto_filter.ref)
            workbook.close()
        workbook = self.workbook("purchasing:budget_version", args=[self.budget.pk])
        self.assertEqual(workbook["Allocations"]["I2"].value, 100)
        self.assertEqual(workbook["Allocations"]["I2"].data_type, "n")
        self.assertIn("Version", workbook.sheetnames)
        for name in ("purchasing:budget_products", "purchasing:detailed_products"):
            self.workbook(name).close()

    def test_warehouse_text_cannot_become_a_formula(self):
        warehouse = Warehouse.objects.create(code="=1+1", label="Dépôt spécial & <test>")
        product = DetailedProduct.objects.create(code="DETAIL", label="Produit", budget_product=self.product)
        StockBalance.objects.create(warehouse=warehouse, product=product, quantity=Decimal("12.3456"))
        self.client.force_login(self.admin)
        workbook = self.workbook("warehouses")
        self.assertEqual(workbook.active["A2"].value, "=1+1")
        self.assertEqual(workbook.active["A2"].data_type, "s")
        self.assertEqual(workbook.active["B2"].value, warehouse.label)
        workbook = self.workbook("stock_balances")
        self.assertEqual(workbook.active["E2"].value, 12.3456)
        self.assertEqual(workbook.active["E2"].data_type, "n")
        self.assertEqual(self.workbook("stock_movements").active.max_row, 1)
        StockMovement.objects.bulk_create([
            StockMovement(warehouse=warehouse, product=product, kind="receipt", quantity=1, delta=1,
                          reason="Historique complet", actor=self.admin, token=uuid4()) for _ in range(201)])
        self.assertEqual(self.workbook("stock_movements").active.max_row, 202)

    def test_transfer_filters_export_all_matching_pages(self):
        for index in range(51):
            self.create_transfer("1")
        other_year = AnnualEnvelope.objects.create(year=self.envelope.year + 1)
        other_version = EnvelopeVersion.objects.create(envelope=other_year, label="Other")
        other = self.create_transfer("2", version=other_version)
        other.status = "cancelled"
        other.save()
        self.client.force_login(self.admin)
        workbook = self.workbook("transfer_monitor", {"year": self.envelope.year, "status": "draft", "page": "2"})
        rows = list(workbook.active.values)
        self.assertEqual(len(rows), 53)  # Header plus all 52 matching transfers.
        self.assertNotIn(str(other), [row[0] for row in rows[1:]])
        self.assertTrue(all(row[1] == self.envelope.year for row in rows[1:]))

    def test_history_exports_the_selected_past_state(self):
        before = BudgetHistoryEvent.objects.latest("pk")
        self.submit()
        self.client.force_login(self.admin)
        workbook = self.workbook("purchasing:budget_history", {"version": self.budget.pk, "at": before.created_at.isoformat()})
        self.assertEqual(workbook["État budgétaire"]["H2"].value, 100)
        self.assertIn("Contexte", workbook.sheetnames)
        self.assertIn("Chronologie", workbook.sheetnames)
        response = self.client.get(reverse("purchasing:budget_history"), {"export": "xlsx", "version": self.budget.pk, "at": "invalid"})
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        workbook = self.workbook("version_transfers", args=[self.budget.pk])
        self.assertIn("Historique", workbook.sheetnames)
        self.assertEqual(workbook["Transferts"]["C2"].value, self.budget.label)

    def test_history_exports_are_scoped_to_their_sections(self):
        before = BudgetHistoryEvent.objects.latest("pk")
        self.submit()
        self.client.force_login(self.admin)
        params = {"version": self.budget.pk, "at": before.created_at.isoformat(), "section": "state"}
        workbook = self.workbook("purchasing:budget_history", params)
        self.assertEqual(workbook.sheetnames, ["État budgétaire", "Contexte"])
        self.assertEqual(workbook["État budgétaire"]["H2"].value, 100)
        workbook.close()
        workbook = self.workbook("purchasing:budget_history", {**params, "section": "timeline"})
        self.assertEqual(workbook.sheetnames, ["Chronologie", "Contexte"])
        self.assertGreater(workbook["Chronologie"].max_row, 1)
        self.assertGreaterEqual(workbook["Chronologie"].column_dimensions["A"].width, 26)
        self.assertEqual(workbook["Chronologie"]["A2"].number_format, "dd/mm/yyyy hh:mm:ss")
        self.assertEqual(workbook["Chronologie"]["A2"].data_type, "d")
        workbook.close()

    def test_purchase_and_transfer_exports_do_not_expose_other_owners(self):
        supplier = Supplier.objects.create(code="S", name="Fournisseur")
        own = PurchaseRequest.objects.create(created_by=self.owner, supplier=supplier)
        other = PurchaseRequest.objects.create(created_by=self.reviewer, supplier=supplier)
        product = DetailedProduct.objects.create(code="D", label="Produit", budget_product=self.product)
        PurchaseRequestLine.objects.create(purchase_request=own, detailed_product=product, cost_center=self.source,
            funding=self.funding, description="Article", quantity=2, unit_price=10, vat_rate=None)
        self.owner.user_permissions.add(Permission.objects.get(codename="add_purchaserequest"))
        foreign_transfer = self.create_transfer()
        foreign_transfer.created_by = self.reviewer
        foreign_transfer.save()
        self.client.force_login(self.owner)
        rows = list(self.workbook("purchasing:list").active.values)
        self.assertEqual([r[0] for r in rows[1:]], [own.number])
        workbook = self.workbook("purchasing:detail", args=[own.pk])
        self.assertEqual(workbook["Lignes"]["J2"].value, 20)
        self.assertIsNone(workbook["Lignes"]["K2"].value)  # Unknown VAT stays unknown.
        self.assertEqual(self.client.get(reverse("purchasing:detail", args=[other.pk]), {"export": "xlsx"}).status_code, 404)
        rows = list(self.workbook("transfer_list").active.values)
        self.assertEqual([r[0] for r in rows[1:]], [str(self.transfer)])
        self.assertEqual(self.client.get(reverse("purchasing:all_requests"), {"export": "xlsx"}).status_code, 403)
        self.client.force_login(self.admin)
        rows = list(self.workbook("purchasing:all_requests").active.values)
        self.assertEqual({r[0] for r in rows[1:]}, {own.number, other.number})

    def test_exports_enforce_view_permissions_and_monitor_has_no_financial_columns(self):
        user = get_user_model().objects.create_user("no_export_access")
        self.client.force_login(user)
        for name in ("warehouses", "stock_balances", "stock_movements", "transfer_list", "transfer_monitor",
                     "purchasing:allocation_versions", "purchasing:budgets", "purchasing:budget_history", "purchasing:monitor"):
            self.assertEqual(self.client.get(reverse(name), {"export": "xlsx"}).status_code, 403, name)
        self.assertEqual(self.client.get(reverse("purchasing:budget_version", args=[self.budget.pk]), {"export": "xlsx"}).status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="monitor_purchases"))
        headers = next(self.workbook("purchasing:monitor").active.values)
        self.assertNotIn("Fournisseur", headers)
        self.assertNotIn("Montant TVAC", headers)
