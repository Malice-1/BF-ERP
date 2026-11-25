from purchasing.test_helpers import record_legacy_workflow
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
from accounts.models import ValidationFunction
from accounts.services import publish_authorization
from budgeting.models import CostCenter, Funding, Support, BudgetProduct, DetailedProduct
from suppliers.models import Supplier
from .models import (AnnualEnvelope, EnvelopeVersion, Allocation, WorkflowVersion, ApprovalRule,
    Submission, ApprovalStep, BudgetEntry, PurchaseOrder, PurchaseNotice)
from .services import (create_purchase_request, add_purchase_request_line,
    delete_purchase_request_line, cancel_purchase_request)
from . import flow
from .exceptions import PurchaseRequestError, PurchaseRequestConflict


class PurchaseFlowTests(TestCase):
    def test_framework_contract_catalogue_ceiling_and_order_snapshot(self):
        from .framework_contracts import usage
        from .models import FrameworkContract, PurchaseRequest

        today = timezone.localdate()
        self.client.force_login(self.admin)
        new_contract_url = reverse("purchasing:framework_contract_new")
        contract_data = {"reference": "CC-001", "title": "Catalogue original", "supplier": self.supplier.pk,
                         "start_date": today.isoformat(), "end_date": today.isoformat(), "ceiling": "200", "is_active": "on"}
        response = self.client.post(new_contract_url, contract_data)
        contract = FrameworkContract.objects.get(reference="CC-001")
        contract_url = reverse("purchasing:framework_contract_detail", args=[contract.pk])
        self.assertRedirects(response, contract_url)
        price_data = {"product": self.detail.pk, "unit_price": "100", "vat_rate": "21", "is_active": "on"}
        self.assertRedirects(self.client.post(contract_url, price_data), contract_url)

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(contract_url).status_code, 403)
        create_url = reverse("purchasing:create")

        def create_request():
            response = self.client.post(create_url, {"framework_contract": contract.pk, "support": self.support.pk})
            purchase = PurchaseRequest.objects.filter(framework_contract=contract).latest("pk")
            self.assertRedirects(response, reverse("purchasing:detail", args=[purchase.pk]))
            self.assertEqual(purchase.supplier, self.supplier)
            add_url = reverse("purchasing:line_add", args=[purchase.pk])
            response = self.client.post(add_url, {"expected_revision": purchase.revision,
                "detailed_product": self.detail.pk, "quantity": "1", "description": "Article du catalogue",
                "cost_center": self.cdf.pk, "funding": self.funding.pk, "unit_price": "1", "vat_rate": "0"})
            self.assertRedirects(response, reverse("purchasing:detail", args=[purchase.pk]))
            line = purchase.lines.get()
            self.assertEqual((line.unit_price, line.vat_rate), (Decimal("100"), Decimal("21")))
            return purchase

        first, second = create_request(), create_request()
        self.submit(first)
        self.assertEqual(usage(contract)["reserved"], Decimal("121"))
        with self.assertRaisesMessage(ValidationError, "Plafond du contrat-cadre dépassé"):
            self.submit(second)
        self.assertEqual(self.balance(), Decimal("879"))
        first.refresh_from_db()
        cancel_purchase_request(actor=self.owner, request_id=first.pk, expected_revision=first.revision)
        self.assertEqual(usage(contract)["reserved"], Decimal(0))
        self.submit(second)
        self.act(self.first, purchase=second)
        self.assertEqual(usage(contract), {"reserved": Decimal(0), "committed": Decimal("121")})

        self.client.force_login(self.admin)
        edit = reverse("purchasing:framework_contract_edit", args=[contract.pk])
        self.assertContains(self.client.post(edit, {**contract_data, "ceiling": "100"}), "inférieur aux montants")
        self.assertRedirects(self.client.post(edit, {**contract_data, "title": "Catalogue modifié"}), contract_url)
        order = self.client.get(reverse("purchasing:order", args=[second.pk]))
        self.assertContains(order, "CC-001")
        self.assertContains(order, "Catalogue original")
        self.assertNotContains(order, "Catalogue modifié")

    def test_purchase_approval_creates_one_balanced_draft_with_budget_product_accounts(self):
        from accounting.models import Account, AccountingPeriod, FiscalYear, Journal, JournalEntry
        from accounting.purchase_posting import SOURCE_KIND, create_engagement_draft

        journal = Journal.objects.create(code="ENG", label="Engagements", kind="GENERAL")
        offset = Account.objects.create(code="090", label="Contrepartie")
        first_account = Account.objects.create(code="091", label="Premier BI")
        second_account = Account.objects.create(code="092", label="Second BI")
        today = timezone.localdate()
        year = FiscalYear.objects.create(code="ENG", start_date=today, end_date=today)
        AccountingPeriod.objects.create(fiscal_year=year, label="Ouverte", start_date=today, end_date=today)
        another_product = BudgetProduct.objects.create(code="B2", label="Autre BI")
        another_detail = DetailedProduct.objects.create(code="D2", label="Autre détail", budget_product=another_product)
        version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Deux BI")
        for product in (self.product, another_product):
            Allocation.objects.create(version=version, cost_center=self.cdf, funding=self.funding,
                                      budget_product=product, amount=1000)
        flow.activate_envelope(actor=self.admin, version_id=version.pk)
        add_purchase_request_line(request_id=self.purchase.pk, actor=self.owner,
            expected_revision=self.purchase.revision, detailed_product=another_detail, cost_center=self.cdf,
            funding=self.funding, description="Autre achat", quantity=Decimal("1"),
            unit_price=Decimal("50"), vat_rate=Decimal("0"))

        url = reverse("accounting:purchase_imputations")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(url, {"action": "settings", "enabled": "on",
            "journal": journal.pk, "offset_account": offset.pk}), url)
        self.assertRedirects(self.client.post(url, {"action": "mapping", "product": self.product.pk,
            "account": first_account.pk}), url)

        self.submit()
        self.act(self.first)
        self.assertFalse(JournalEntry.objects.exists())
        with self.assertRaisesMessage(ValidationError, "Compte d’imputation manquant"):
            self.act(self.first)
        self.assertFalse(PurchaseOrder.objects.exists())
        self.assertFalse(JournalEntry.objects.exists())
        self.assertEqual(BudgetEntry.objects.filter(state="reserved").count(), 2)

        self.assertRedirects(self.client.post(url, {"action": "mapping", "product": another_product.pk,
            "account": second_account.pk}), url)
        self.act(self.first)
        order = PurchaseOrder.objects.get(purchase_request=self.purchase)
        entry = JournalEntry.objects.get(source_kind=SOURCE_KIND, source_identifier=str(self.purchase.pk))
        self.assertEqual((entry.status, entry.journal, entry.document_reference), ("DRAFT", journal, order.number))
        self.assertEqual(entry.debit_total, Decimal("171"))
        self.assertEqual(entry.credit_total, entry.debit_total)
        self.assertCountEqual(entry.lines.values_list("account_id", "debit", "credit"), [
            (first_account.pk, Decimal("121"), Decimal(0)),
            (second_account.pk, Decimal("50"), Decimal(0)),
            (offset.pk, Decimal(0), Decimal("171")),
        ])
        self.assertEqual(create_engagement_draft(order, self.first).pk, entry.pk)
        self.assertEqual(JournalEntry.objects.count(), 1)
        entry_url = reverse("accounting:entry_detail", args=[entry.pk])
        purchase_url = reverse("purchasing:detail", args=[self.purchase.pk])
        self.assertContains(self.client.get(purchase_url), entry_url)
        self.client.force_login(self.owner)
        self.assertNotContains(self.client.get(purchase_url), entry_url)

    def test_admin_budget_edit_preserves_reservations_and_live_order_flow(self):
        self.submit()
        self.version.refresh_from_db()
        publication = self.version.published_at
        flow.unlock_envelope(actor=self.admin, version_id=self.version.pk)
        allocation = self.version.allocations.get()
        allocation.amount = Decimal("50")
        allocation.save()
        self.assertEqual(self.balance(), Decimal("-71"))
        flow.lock_envelope(actor=self.admin, version_id=self.version.pk)
        self.version.refresh_from_db()
        self.assertEqual(self.version.published_at, publication)
        self.assertIsNone(self.version.locked_at)
        with self.assertRaises(PurchaseRequestError):
            self.submit(self.draft("1"))
        self.act(self.first)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(BudgetEntry.objects.get().state, "committed")
        self.assertEqual(self.balance(), Decimal("-71"))



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
        self.assertEqual(response.context["pending_validation_count"], 0)
        self.assertEqual(flow.pending_validation_count(self.second), 0)

    def test_global_badge_uses_current_manager_and_delegation(self):
        self.cdf.managers.clear()
        self.submit()
        self.assertEqual(flow.pending_validation_count(self.other), 0)
        self.cdf.managers.set([self.other])
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


    def test_entity_managers_validate_without_roles_or_authorizations(self):
        self.cdf.managers.set([self.other])
        self.submit()
        step = ApprovalStep.objects.get(snapshot__submission__purchase_request=self.purchase)
        self.assertEqual(step.state, "pending")
        self.assertIsNone(step.function_id)
        self.assertIsNone(step.role_id)
        self.assertIsNone(flow.authority(self.first, step))
        self.assertIsNotNone(flow.authority(self.other, step))
        self.act(self.other)
        self.assertTrue(PurchaseOrder.objects.filter(purchase_request=self.purchase).exists())
        step.refresh_from_db()
        self.assertIsNone(step.authorization_id)
        self.assertEqual(step.evaluated_scope["manager_source"], "cdf")

    def test_missing_manager_and_replacement_refresh_candidates(self):
        self.cdf.managers.clear()
        self.submit()
        step = ApprovalStep.objects.get(snapshot__submission__purchase_request=self.purchase, level=1)
        self.assertEqual(step.state, "unassigned")
        self.cdf.managers.set([self.other])
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
        record_legacy_workflow(self.workflow)
        self.cdf.managers.add(self.first)
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
        response = self.client.get(reverse("purchasing:budget_check"), data)
        self.assertEqual(response.context["result"]["available"], Decimal("879"))

    def test_purchase_list_search_uses_visible_columns_and_preserves_scope(self):
        from django.utils import formats

        other_supplier = Supplier.objects.create(code="AUTRE", name="Matériel électrique")
        other_request = create_purchase_request(actor=self.owner, supplier=other_supplier, support=self.support)
        type(other_request).objects.filter(pk=other_request.pk).update(created_by=self.other)
        self.client.force_login(self.admin)
        url = reverse("purchasing:all_requests")
        searches = {
            "number": (other_request.number, other_request),
            "requester": (str(self.other), other_request),
            "supplier": ("materiel electrique", other_request),
            "status": ("brouillon", self.purchase),
            "receipt": ("non receptionnee", self.purchase),
            "created": (formats.date_format(timezone.template_localtime(self.purchase.created_at), "DATETIME_FORMAT"), self.purchase),
        }
        for field, (query, expected) in searches.items():
            with self.subTest(field=field):
                response = self.client.get(url, {"field": field, "q": query},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest")
                self.assertEqual(response.headers["X-Purchase-Request-Results"], "1")
                self.assertContains(response, expected.number)
                self.assertNotContains(response, 'id="purchase-request-filter"')
                if field in {"number", "requester", "supplier"}:
                    self.assertNotContains(response, self.purchase.number)

        self.client.force_login(self.owner)
        personal = reverse("purchasing:list")
        response = self.client.get(personal, {"q": "electrique"})
        self.assertNotContains(response, other_request.number)
        self.assertNotContains(response, 'value="requester"')
        self.assertContains(response, "Aucune demande ne correspond")
        response = self.client.get(personal, {"field": "supplier", "q": "snapshot", "export": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheet", response["Content-Type"])

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

    def test_budget_table_selects_one_version_and_keeps_annual_reservations(self):
        self.submit()
        replacement = self.budget("2000")
        draft = EnvelopeVersion.objects.create(envelope=self.envelope, label="Draft selection")
        Allocation.objects.create(version=draft, cost_center=self.cdf, funding=self.funding,
            budget_product=self.product, amount=3000)
        self.client.force_login(self.admin)
        url = reverse("purchasing:budgets")
        self.assertEqual(self.client.get(url).context["selected_version"].pk, replacement.pk)
        for version, amount in ((self.version, "879"), (replacement, "1879"), (draft, "2879")):
            response = self.client.get(url, {"version": version.pk})
            self.assertEqual(response.context["selected_version"].pk, version.pk)
            self.assertEqual(len(response.context["rows"]), 1)
            self.assertEqual(response.context["rows"][0]["available"], Decimal(amount))
            self.assertNotContains(response, "<th>Année / version</th>")
            self.assertContains(response, 'name="version"')

    def test_budget_analysis_keeps_deficits_visible_and_filters_drilldowns(self):
        self.submit()
        draft = EnvelopeVersion.objects.create(envelope=self.envelope, label="Analyse")
        other = CostCenter.objects.create(code="AUTRE", label="Autre centre")
        Allocation.objects.create(version=draft, cost_center=self.cdf, funding=self.funding,
                                  budget_product=self.product, amount=100)
        Allocation.objects.create(version=draft, cost_center=other, funding=self.funding,
                                  budget_product=self.product, amount=300)
        self.client.force_login(self.admin)
        url = reverse("purchasing:budgets")
        page = self.client.get(url, {"version": draft.pk, "group_by": "funding"})
        analysis = page.context["analysis"]
        self.assertEqual(analysis["totals"]["available"], Decimal("279"))
        self.assertEqual(analysis["charts"][0]["total"], Decimal("300"))
        self.assertEqual(analysis["charts"][1]["total"], Decimal("21"))
        self.assertContains(page, "Analyse du budget restant")
        self.assertContains(page, "transparent 100%", count=2)

        excluded = CostCenter.objects.create(code="EXCLU", label="Centre exclu")
        Allocation.objects.create(version=draft, cost_center=excluded, funding=self.funding,
                                  budget_product=self.product, amount=500)
        page = self.client.get(url, {
            "version": draft.pk, "group_by": "cdf", "cdf": [self.cdf.pk, other.pk],
            "status": ["positive", "deficit"], "funding": self.funding.pk, "product": "",
        })
        analysis = page.context["analysis"]
        self.assertEqual(analysis["totals"]["available"], Decimal("279"))
        self.assertEqual(len(page.context["rows"]), 2)
        self.assertContains(page, 'name="cdf"')
        self.assertContains(page, 'type="checkbox"')
        drilldown = self.client.get(url + analysis["groups"][0]["url"])
        self.assertEqual(drilldown.context["analysis_form"].cleaned_data["cdf"], [other.pk])
        self.assertEqual(drilldown.context["analysis_form"].cleaned_data["status"], ["positive", "deficit"])
        self.assertEqual(drilldown.context["analysis_form"].cleaned_data["funding"], [self.funding.pk])

    def test_budget_pilot_uses_live_balances_and_checks_tab_permissions(self):
        url = reverse("purchasing:budget_pilot")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.owner.user_permissions.add(Permission.objects.get(
            content_type__app_label="budgeting", codename="view_budget_balances"))
        self.submit()
        limited = self.client.get(url, {"tab": "purchases"})
        self.assertContains(limited, "Situation budgétaire")
        self.assertNotContains(limited, self.purchase.number)
        self.assertNotContains(limited, "Achats et factures")
        self.assertEqual(limited.context["metrics"]["available"], self.balance())

        self.client.force_login(self.admin)
        response = self.client.get(url, {"tab": "purchases", "stage": "validation"})
        self.assertContains(response, self.purchase.number)
        self.assertEqual(response.context["waiting_amount"], Decimal("121"))
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertContains(self.client.get(url, {"tab": "history"}), "Budget initial")
        self.assertContains(self.client.get(url, {"tab": "training"}), "Aucune activité mensuelle")

    def test_budget_pilot_matches_only_approved_supplier_invoices_and_reports_training(self):
        from accounting.models import SupplierInvoice
        from budgeting.models import TrainingActivity
        from sales.models import TrainingService

        self.submit()
        self.act(self.first)
        order = PurchaseOrder.objects.get(purchase_request=self.purchase)
        PurchaseOrder.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=91))
        other = Supplier.objects.create(code="OTHER", name="Autre fournisseur")
        for supplier, status, total in ((self.supplier, "REVIEWED", 50), (other, "REVIEWED", 90),
                                        (self.supplier, "RECEIVED", 70)):
            SupplierInvoice.objects.create(supplier=supplier, status=status, currency="EUR", total=total,
                extracted_data={"order_reference": order.number})
        course = TrainingService.objects.create(code="T", description="Formation de test")
        TrainingActivity.objects.create(training=course, cost_center=self.cdf,
            month=timezone.localdate().replace(day=1), trainees=5, hours=10, sessions=1)
        self.client.force_login(self.admin)
        url = reverse("purchasing:budget_pilot")
        response = self.client.get(url, {"tab": "purchases", "overdue": "1", "cdf": self.cdf.pk})
        self.assertContains(response, order.number)
        row, = response.context["page"].object_list
        self.assertEqual((row["billed"], row["remaining"], row["overdue"]), (Decimal("50"), Decimal("71"), True))
        response = self.client.get(url, {"tab": "training", "cdf": self.cdf.pk})
        self.assertContains(response, course.description)
        self.assertEqual(response.context["cost_per_hour"], Decimal("12.1"))

    def test_budget_table_refuses_deleted_or_invalid_selection(self):
        deleted = EnvelopeVersion.objects.create(envelope=self.envelope, label="Deleted selection")
        flow.delete_envelope_version(actor=self.admin, version_id=deleted.pk)
        self.client.force_login(self.admin)
        url = reverse("purchasing:budgets")
        self.assertNotContains(self.client.get(url), deleted.label)
        for value in (str(deleted.pk), "invalid"):
            response = self.client.get(url, {"version": value, "export": "xlsx"})
            self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
            self.assertIn("version", response.context["form"].errors)
            self.assertEqual(response.context["rows"], [])

    def test_budget_check_requires_login_and_button_is_visible(self):
        self.assertEqual(self.client.get(reverse("purchasing:budget_check")).status_code, 302)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("purchasing:list"))
        self.assertContains(response, 'id="budget-check-open"')
        self.assertContains(response, "Vérifier un budget")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    def test_budget_check_excludes_deleted_versions_and_refuses_direct_selection(self):
        from .flow import delete_envelope_version
        deleted = EnvelopeVersion.objects.create(envelope=self.envelope, label="Deleted version")
        delete_envelope_version(actor=self.admin, version_id=deleted.pk)
        self.client.force_login(self.owner)
        url = reverse("purchasing:budget_check")
        response = self.client.get(url)
        self.assertNotContains(response, deleted.label)
        self.assertContains(response, self.version.label)
        self.assertIn("no-store", response.headers["Cache-Control"])
        response = self.client.get(url, dict(version=deleted.pk, budget_product=self.product.pk,
            funding=self.funding.pk, cost_center=self.cdf.pk))
        self.assertIn("version", response.context["form"].errors)
        self.assertIsNone(response.context["result"])

    def test_budget_check_displays_locked_version_as_locked(self):
        from .flow import lock_envelope
        locked = EnvelopeVersion.objects.create(envelope=self.envelope, label="Locked version")
        lock_envelope(actor=self.admin, version_id=locked.pk)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("purchasing:budget_check"))
        self.assertContains(response, locked.label + " · Bloquée")

    def test_t001_t004_complete_flow_preserves_budget_and_creates_one_order(self):
        self.submit()
        from budgeting.models import BudgetHistoryEvent
        reserved_history = BudgetHistoryEvent.objects.latest("pk")
        reserved_rows = next(iter(reserved_history.state["versions"].values()))["rows"]
        self.assertEqual(sum(Decimal(row["reserved"]) for row in reserved_rows), Decimal("121"))
        self.assertEqual(self.balance(), Decimal("879"))
        self.act(self.first)
        self.assertTrue(PurchaseOrder.objects.exists())
        self.assertEqual(self.balance(), Decimal("879"))
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(BudgetEntry.objects.get().state, "committed")
        committed_rows = next(iter(BudgetHistoryEvent.objects.latest("pk").state["versions"].values()))["rows"]
        self.assertEqual(sum(Decimal(row["committed"]) for row in committed_rows), Decimal("121"))
        self.assertEqual(sum(Decimal(row["reserved"]) for row in committed_rows), 0)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "ORDERED")
        with self.assertRaises(PurchaseRequestError):
            self.submit()
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_budget_transactions_distinguish_reservations_commitments_and_releases(self):
        self.submit()
        self.act(self.first)
        rejected = self.draft()
        self.submit(rejected)
        self.act(self.first, decision="reject", reason="Non nécessaire", purchase=rejected)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("purchasing:budget_transactions"))
        rows = [row for row in response.context["page"] if row["reserved"] or row["committed"]]
        self.assertEqual(
            [(row["reserved"], row["committed"], row["debit"], row["credit"]) for row in rows],
            [(-121, 0, 0, 121), (121, 0, 121, 0), (-121, 121, 0, 0), (121, 0, 121, 0)],
        )

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
        from budgeting.models import BudgetHistoryEvent
        rows = next(iter(BudgetHistoryEvent.objects.latest("pk").state["versions"].values()))["rows"]
        self.assertEqual(sum(Decimal(row["reserved"]) for row in rows), 0)


    def test_users_without_grant_cannot_approve(self):
        purchase = self.submit()
        step = ApprovalStep.objects.get(level=1)
        for actor in (self.second, self.other):
            with self.assertRaises(PermissionDenied):
                flow.decide(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision, step_id=step.pk, decision="approve")
        self.assertFalse(PurchaseOrder.objects.exists())


    def test_t008_new_deficit_blocks_new_reservation_allows_existing_conversion(self):
        self.submit()
        self.budget("50")
        self.assertEqual(self.balance(), -71)
        other = self.draft("1")
        with self.assertRaises(PurchaseRequestError):
            self.submit(other)
        self.act(self.first)
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
        self.cdf.managers.add(self.other)
        self.purchase.refresh_from_db()
        flow.reassign(request_id=self.purchase.pk, actor=self.admin, expected_revision=self.purchase.revision,
            step_id=step.pk, user=self.other, reason="Remplacement")
        self.act(self.other)
        self.assertTrue(PurchaseOrder.objects.exists())

    def test_reassignment_requires_permission_reason_and_scope(self):
        purchase = self.submit()
        step = ApprovalStep.objects.get(level=1)
        for actor, user, reason, error in ((self.owner, self.first, "x", PermissionDenied),
                (self.admin, self.second, "x", ValidationError), (self.admin, self.first, "", ValidationError)):
            with self.assertRaises(error):
                flow.reassign(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision,
                    step_id=step.pk, user=user, reason=reason)


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
        self.assertIsNone(step.authorization_id)
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
        for url in ("/achats/suivi/", "/achats/budgets/", "/admin/"):
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

    @override_settings(SETTINGS_MODULE="config.settings")
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

    def test_admin_can_clone_and_publish_budget(self):
        self.client.force_login(self.admin)
        for model_name, source, cls in (("envelopeversion", self.version, EnvelopeVersion),):
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
