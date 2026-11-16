from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from budgeting.models import BudgetProduct
from workflow.models import ConfigurationAuditEvent
from . import test_budget_workspace as fixtures
from .allocation_excel import HEADERS
from .flow import activate_envelope, unlock_envelope, lock_envelope
from .models import Allocation, EnvelopeVersion


class AllocationExcelTests(TestCase):
    setUp = fixtures.BudgetWorkspaceTests.setUp
    create_version = fixtures.BudgetWorkspaceTests.create_version

    def upload(self, rows, headers=None, filename="allocations.xlsx"):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Allocations"
        sheet.append(headers or HEADERS)
        for row in rows:
            sheet.append(row)
        output = BytesIO()
        workbook.save(output)
        return SimpleUploadedFile(filename, output.getvalue())

    def test_template_contains_current_allocations_and_reference_codes(self):
        version = self.create_version()
        Allocation.objects.create(version=version, budget_product=self.product, cost_center=self.cdf, funding=self.funding, amount=123)
        response = self.client.get(reverse("purchasing:allocation_import", args=[version.pk]), {"template": "xlsx"})
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook.sheetnames, ["Allocations", "Produits BI", "CDF", "Financements"])
        self.assertEqual(list(workbook["Allocations"].values), [tuple(HEADERS), ("BI", "CDF", "F", 123)])
        self.assertEqual(workbook["Allocations"]["A2"].data_type, "s")
        workbook.close()

    def test_template_can_be_downloaded_from_allocation_versions_page(self):
        url = reverse("purchasing:allocation_versions")
        self.assertContains(self.client.get(url), 'aria-label="Télécharger le modèle Excel d’alimentation du budget"')
        response = self.client.get(url, {"template": "xlsx"})
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(list(workbook["Allocations"].values), [tuple(HEADERS)])
        self.assertIn(("BI", "Budget"), list(workbook["Produits BI"].values))
        workbook.close()

    def test_async_import_reports_success_without_redirecting_to_large_form(self):
        version = self.create_version()
        BudgetProduct.objects.bulk_create([BudgetProduct(code=f"LOAD-{index:04}", label=f"Load {index}") for index in range(1000)])
        rows = [[f"LOAD-{index:04}", "CDF", "F", 100] for index in range(1000)]
        response = self.client.post(reverse("purchasing:allocation_import", args=[version.pk]),
            {"file": self.upload(rows)}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"], {"created": 1000, "updated": 0, "unchanged": 0})
        self.assertTrue(response.json()["ok"])
        self.assertNotIn("Location", response.headers)
        self.assertLess(len(response.content), 1000)
        self.assertEqual(version.allocations.count(), 1000)

    def test_async_errors_are_returned_to_the_import_page_without_changes(self):
        version = self.create_version()
        url = reverse("purchasing:allocation_import", args=[version.pk])
        response = self.client.post(url, {"file": self.upload([["UNKNOWN", "CDF", "F", 10]])},
                                   HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("Ligne 2", response.json()["errors"][0])
        self.assertFalse(version.allocations.exists())
        response = self.client.post(url, {}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["errors"])

    def test_import_creates_updates_preserves_other_allocations_and_is_not_additive(self):
        version = self.create_version()
        original = Allocation.objects.create(version=version, budget_product=self.product, cost_center=self.cdf, funding=self.funding, amount=100)
        new = BudgetProduct.objects.create(code="NEW", label="New")
        untouched_product = BudgetProduct.objects.create(code="KEEP", label="Keep")
        untouched = Allocation.objects.create(version=version, budget_product=untouched_product, cost_center=self.cdf, funding=self.funding, amount=500)
        url = reverse("purchasing:allocation_import", args=[version.pk])
        rows = [["BI", "CDF", "F", "1 234,56"], ["NEW", "CDF", "F", 70]]
        for _ in range(2):
            response = self.client.post(url, {"file": self.upload(rows)})
            self.assertRedirects(response, reverse("purchasing:budget_version", args=[version.pk]))
        original.refresh_from_db()
        untouched.refresh_from_db()
        self.assertEqual(original.amount, Decimal("1234.56"))
        self.assertEqual(untouched.amount, 500)
        self.assertEqual(version.allocations.get(budget_product=new).amount, 70)
        self.assertEqual(version.allocations.count(), 3)
        self.assertIsNone(EnvelopeVersion.objects.get(pk=version.pk).published_at)
        self.assertEqual(ConfigurationAuditEvent.objects.filter(action="budget.allocations_import", object_id=version.pk).count(), 2)

    def test_invalid_rows_abort_entire_file_with_row_numbers(self):
        version = self.create_version()
        original = Allocation.objects.create(version=version, budget_product=self.product, cost_center=self.cdf, funding=self.funding, amount=100)
        url = reverse("purchasing:allocation_import", args=[version.pk])
        cases = [
            ["UNKNOWN", "CDF", "F", 20], ["BI", "UNKNOWN", "F", 20],
            ["BI", "CDF", "UNKNOWN", 20], ["BI", "CDF", "F", -1],
            ["BI", "CDF", "F", "=1+2"], ["BI", "CDF", "F", "NaN"],
            ["BI", "CDF", "F", None], ["BI", "CDF", "F", "0.12345678901"],
        ]
        for row in cases:
            response = self.client.post(url, {"file": self.upload([row])})
            self.assertContains(response, "Ligne 2")
            self.assertContains(response, "Aucune modification enregistrée")
            original.refresh_from_db()
            self.assertEqual(original.amount, 100)
        response = self.client.post(url, {"file": self.upload([["BI", "CDF", "F", 200], ["BAD", "CDF", "F", 30]])})
        self.assertContains(response, "Ligne 3")
        original.refresh_from_db()
        self.assertEqual(original.amount, 100)

    def test_duplicate_combination_empty_file_invalid_headers_and_invalid_workbook(self):
        version = self.create_version()
        url = reverse("purchasing:allocation_import", args=[version.pk])
        row = ["BI", "CDF", "F", 0]
        cases = [self.upload([row, row]), self.upload([]), self.upload([row], headers=["Wrong"]),
                 SimpleUploadedFile("bad.xlsx", b"not a workbook"), self.upload([row], filename="old.xls")]
        for upload in cases:
            response = self.client.post(url, {"file": upload})
            self.assertContains(response, "Import impossible")
        self.assertFalse(version.allocations.exists())

    def test_current_export_can_be_imported_and_wrong_year_or_version_is_rejected(self):
        version = self.create_version()
        Allocation.objects.create(version=version, budget_product=self.product, cost_center=self.cdf, funding=self.funding, amount=10)
        exported = self.client.get(reverse("purchasing:budget_version", args=[version.pk]), {"export": "xlsx"})
        url = reverse("purchasing:allocation_import", args=[version.pk])
        self.assertEqual(self.client.post(url, {"file": SimpleUploadedFile("export.xlsx", exported.content)}).status_code, 302)
        for year, label in ((2025, version.label), (2026, "Autre version")):
            response = self.client.post(url, {"file": self.upload(
                [["BI", "CDF", "F", 900, year, label]], headers=HEADERS + ["Année", "Version"])})
            self.assertContains(response, "Import impossible")
        self.assertEqual(version.allocations.get().amount, 10)

    def test_permissions_and_published_version_rules_match_manual_editing(self):
        version = self.create_version()
        Allocation.objects.create(version=version, budget_product=self.product, cost_center=self.cdf, funding=self.funding, amount=10)
        activate_envelope(actor=self.manager, version_id=version.pk)
        url = reverse("purchasing:allocation_import", args=[version.pk])
        response = self.client.post(url, {"file": self.upload([["BI", "CDF", "F", 20]])})
        self.assertContains(response, "Import impossible")
        admin = get_user_model().objects.create_superuser("excel-admin", password="test")
        unlock_envelope(actor=admin, version_id=version.pk)
        self.assertEqual(self.client.post(url, {"file": self.upload([["BI", "CDF", "F", 20]])}).status_code, 403)
        self.client.force_login(admin)
        self.assertEqual(self.client.post(url, {"file": self.upload([["BI", "CDF", "F", 20]])}).status_code, 302)
        self.assertEqual(version.allocations.get().amount, 20)
        lock_envelope(actor=admin, version_id=version.pk)
        self.assertContains(self.client.post(url, {"file": self.upload([["BI", "CDF", "F", 30]])}), "Import impossible")
        outsider = get_user_model().objects.create_user("excel-outsider")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(url, {"template": "xlsx"}).status_code, 403)

    def test_import_rolls_back_previous_rows_when_a_save_fails(self):
        version = self.create_version()
        BudgetProduct.objects.create(code="NEW", label="New")
        existing = Allocation.objects.create(version=version, budget_product=self.product, cost_center=self.cdf, funding=self.funding, amount=5)
        with patch.object(Allocation.objects, "bulk_update", side_effect=ValidationError("Erreur d’enregistrement")):
            response = self.client.post(reverse("purchasing:allocation_import", args=[version.pk]),
                {"file": self.upload([["BI", "CDF", "F", 10], ["NEW", "CDF", "F", 20]])})
        self.assertContains(response, "Erreur d’enregistrement")
        existing.refresh_from_db()
        self.assertEqual(existing.amount, 5)
        self.assertEqual(version.allocations.count(), 1)
        self.assertFalse(ConfigurationAuditEvent.objects.filter(action="budget.allocations_import").exists())
