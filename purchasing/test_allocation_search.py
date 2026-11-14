from decimal import Decimal
from io import BytesIO

from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from budgeting.models import BudgetProduct, Funding
from . import test_budget_workspace as fixtures
from .flow import activate_envelope
from .models import Allocation


class AllocationSearchTests(TestCase):
    setUp = fixtures.BudgetWorkspaceTests.setUp
    create_version = fixtures.BudgetWorkspaceTests.create_version

    def add_line(self, version, product, amount, funding=None):
        return Allocation.objects.create(version=version, budget_product=product, cost_center=self.cdf,
                                         funding=funding or self.funding, amount=amount)

    def many_lines(self, version):
        products = [BudgetProduct.objects.create(code=f"LOAD-{index:03}", label=f"Produit {index}") for index in range(35)]
        Allocation.objects.bulk_create([Allocation(version=version, budget_product=product, cost_center=self.cdf,
            funding=self.funding, amount=index + 1) for index, product in enumerate(products)])

    def test_search_by_product_code_or_label_returns_filtered_total_and_full_total(self):
        version = self.create_version()
        self.add_line(version, self.product, 100)
        other = BudgetProduct.objects.create(code="OTHER", label="Fournitures")
        self.add_line(version, other, 200)
        self.add_line(version, self.product, 30, Funding.objects.create(code="F2", label="Second fonds"))
        url = reverse("purchasing:budget_version", args=[version.pk])
        for query in ("BI", "Budget"):
            response = self.client.get(url, {"q": query}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            self.assertEqual(response.context["total"], 330)
            self.assertEqual(response.context["filtered_total"], 130)
            self.assertEqual(len(response.context["lines"]), 2)
            self.assertTemplateUsed(response, "purchasing/budget_allocations_results.html")
            self.assertNotContains(response, "<!doctype html>")
        response = self.client.get(url, {"q": "Absent"})
        self.assertEqual(response.context["filtered_total"], 0)
        self.assertEqual(response.context["total"], 330)
        self.assertEqual(response.context["page"].paginator.count, 0)
        response = self.client.get(reverse("purchasing:allocation_versions"))
        self.assertEqual(list(response.context["versions"])[0].allocation_total, 330)

    def test_pagination_limits_edit_forms_and_totals_cover_all_pages(self):
        version = self.create_version()
        self.many_lines(version)
        url = reverse("purchasing:budget_version", args=[version.pk])
        first = self.client.get(url)
        self.assertEqual(first.context["formset"].initial_form_count(), 25)
        self.assertEqual(first.context["total"], 630)
        second = self.client.get(url, {"page": 2}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(second.context["formset"].initial_form_count(), 10)
        self.assertEqual(second.context["filtered_total"], 630)
        self.assertFalse({line.pk for line in first.context["lines"]} & {line.pk for line in second.context["lines"]})

    def test_filtered_edits_and_deletions_preserve_other_allocations(self):
        version = self.create_version()
        line = self.add_line(version, self.product, 100)
        other = self.add_line(version, BudgetProduct.objects.create(code="OTHER", label="Autre"), 200)
        url = reverse("purchasing:budget_version", args=[version.pk]) + "?q=BI"
        data = {"action": "save", "allocations-TOTAL_FORMS": 1, "allocations-INITIAL_FORMS": 1,
            "allocations-0-id": line.pk, "allocations-0-version": version.pk,
            "allocations-0-budget_product": self.product.pk, "allocations-0-cost_center": self.cdf.pk,
            "allocations-0-funding": self.funding.pk, "allocations-0-amount": "150"}
        self.assertRedirects(self.client.post(url, data), url)
        line.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(line.amount, 150)
        self.assertEqual(other.amount, 200)
        data["allocations-0-DELETE"] = "on"
        self.assertRedirects(self.client.post(url, data), url)
        self.assertFalse(Allocation.objects.filter(pk=line.pk).exists())
        self.assertTrue(Allocation.objects.filter(pk=other.pk).exists())

    def test_filtered_export_includes_all_matching_pages(self):
        version = self.create_version()
        self.many_lines(version)
        self.add_line(version, self.product, 500)
        response = self.client.get(reverse("purchasing:budget_version", args=[version.pk]),
                                   {"q": "LOAD-", "export": "xlsx", "page": 2})
        workbook = load_workbook(BytesIO(response.content))
        rows = list(workbook["Allocations"].values)
        self.assertEqual(len(rows), 36)
        self.assertEqual(sum(Decimal(str(row[-1])) for row in rows[1:]), 630)
        workbook.close()

    def test_published_read_only_allocations_have_the_same_search_and_totals(self):
        version = self.create_version()
        self.add_line(version, self.product, 100)
        activate_envelope(actor=self.manager, version_id=version.pk)
        response = self.client.get(reverse("purchasing:budget_version", args=[version.pk]), {"q": "BI"})
        self.assertFalse(response.context["can_edit_allocations"])
        self.assertEqual(response.context["total"], 100)
        self.assertEqual(response.context["filtered_total"], 100)
        self.assertNotContains(response, 'id="budget-allocations"')

    def test_large_reference_list_is_sent_once_and_response_stays_small(self):
        version = self.create_version()
        products = BudgetProduct.objects.bulk_create([
            BudgetProduct(code=f"REF-{index:04}", label=f"Produit {index}") for index in range(500)])
        Allocation.objects.bulk_create([
            Allocation(version=version, budget_product=product, cost_center=self.cdf,
                       funding=self.funding, amount=100) for product in products[:25]])
        response = self.client.get(reverse("purchasing:budget_version", args=[version.pk]),
                                   HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(response.content), 100000)
        self.assertEqual(len(response.context["reference_choices"]["budget_product"]), 502)
        self.assertEqual(response.content.count(b'id="allocation-reference-data"'), 1)
        for form in response.context["formset"]:
            self.assertLessEqual(len(form.fields["budget_product"].choices), 2)

    def test_lightweight_selects_still_allow_changing_to_another_valid_product(self):
        version = self.create_version()
        line = self.add_line(version, self.product, 100)
        replacement = BudgetProduct.objects.create(code="REPLACE", label="Remplacement")
        url = reverse("purchasing:budget_version", args=[version.pk])
        data = {"action": "save", "allocations-TOTAL_FORMS": 1, "allocations-INITIAL_FORMS": 1,
            "allocations-0-id": line.pk, "allocations-0-version": version.pk,
            "allocations-0-budget_product": replacement.pk, "allocations-0-cost_center": self.cdf.pk,
            "allocations-0-funding": self.funding.pk, "allocations-0-amount": "150"}
        self.assertRedirects(self.client.post(url, data), url)
        line.refresh_from_db()
        self.assertEqual(line.budget_product_id, replacement.pk)
        self.assertEqual(line.amount, 150)
        data["allocations-0-budget_product"] = 999999
        response = self.client.post(url, data)
        self.assertTrue(response.context["formset"].forms[0].errors)
        line.refresh_from_db()
        self.assertEqual(line.budget_product_id, replacement.pk)

    def test_complete_selects_remain_available_without_javascript(self):
        version = self.create_version()
        self.add_line(version, self.product, 100)
        BudgetProduct.objects.create(code="EXTRA", label="Autre")
        url = reverse("purchasing:budget_version", args=[version.pk])
        response = self.client.get(url, {"full_choices": 1})
        self.assertEqual(response.context["reference_choices"], {})
        self.assertEqual(len(response.context["formset"].forms[0].fields["budget_product"].choices), 3)
        self.assertIn("full_choices=1", response.context["form_action"])
