from decimal import Decimal
from datetime import timedelta
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from purchasing.models import EnvelopeVersion, Allocation
from purchasing.flow import activate_envelope
from . import test_transfers as fixtures
from .models import BudgetHistoryEvent
from .transfers import act


class BudgetHistoryTests(TestCase):
    def test_history_export_actions_are_attached_to_their_sections(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("purchasing:budget_version_history", args=[self.budget.pk]))
        html = response.content.decode()
        state_zone = html.split('aria-labelledby="budget-state-title"', 1)[1].split('</section>', 1)[0]
        timeline_zone = html.split('aria-labelledby="budget-timeline-title"', 1)[1].split('</section>', 1)[0]
        self.assertIn('section=state', state_zone)
        self.assertNotIn('section=timeline', state_zone)
        self.assertIn('section=timeline', timeline_zone)
        self.assertNotIn('section=state', timeline_zone)

    def test_allocation_history_records_product_amount_cdf_and_funding(self):
        version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Detailed history")
        allocation = Allocation.objects.create(version=version, budget_product=self.product,
            cost_center=self.source, funding=self.funding, amount=Decimal("1234.50"))
        added = BudgetHistoryEvent.objects.latest("pk")
        self.assertEqual(added.state["change"]["kind"], "added")
        self.assertIn("Produit ajouté", added.reason)
        self.assertIn("1.234,50", added.reason)
        self.assertIn(str(self.product), added.reason)
        self.assertIn(str(self.source), added.reason)
        self.assertIn(self.funding.code, added.reason)
        allocation.delete()
        removed = BudgetHistoryEvent.objects.latest("pk")
        self.assertEqual(removed.state["change"]["kind"], "removed")
        self.assertEqual(removed.state["change"]["amount"], "1234.50")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("purchasing:budget_version_history", args=[version.pk]))
        self.assertContains(response, "Produit ajouté")
        self.assertContains(response, "Produit supprimé")
        self.assertNotContains(response, "TVAC")

    def test_generic_legacy_allocation_label_is_explained_without_rewriting_it(self):
        from types import SimpleNamespace
        from .history import describe_timeline
        before = SimpleNamespace(reason="Création de version", state={"versions": {"1": {"rows": []}}})
        after = SimpleNamespace(reason="Allocation TVAC · 42", state={"versions": {"1": {"rows": [
            {"product": "BI-1", "cdf": "CDF-A", "funding": "F-1", "allocated": "10000"}]}}})
        describe_timeline([before, after], 1)
        self.assertIn("Produit ajouté : BI-1", after.display_reason)
        self.assertIn("10.000,00", after.display_reason)
        self.assertIn("CDF-A", after.display_reason)
        self.assertIn("F-1", after.display_reason)
        self.assertEqual(after.reason, "Allocation TVAC · 42")

    def test_version_history_is_fixed_and_only_date_remains_selectable(self):
        other = EnvelopeVersion.objects.create(envelope=self.envelope, label="Other history")
        self.client.force_login(self.admin)
        url = reverse("purchasing:budget_version_history", args=[self.budget.pk])
        response = self.client.get(url, {"version": other.pk})
        self.assertEqual(response.context["version"].pk, self.budget.pk)
        self.assertTrue(response.context["form"].fields["version"].widget.is_hidden)
        self.assertContains(response, 'name="at"')
        self.assertContains(response, reverse("purchasing:budget_version", args=[self.budget.pk]))
        self.assertTrue(all(str(self.budget.pk) in event.state["versions"] for event in response.context["timeline"]))
        invalid = self.client.get(url, {"at": "invalid"})
        self.assertEqual(invalid.context["version"].pk, self.budget.pk)
        self.assertIn("at", invalid.context["form"].errors)
        self.assertFalse(self.client.get(reverse("purchasing:budget_history")).context["form"].fields["version"].widget.is_hidden)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 403)

    setUp = fixtures.TransferTests.setUp
    create_transfer = fixtures.TransferTests.create_transfer
    submit = fixtures.TransferTests.submit
    balance = fixtures.TransferTests.balance
    approve_transfer = fixtures.TransferTests.approve_transfer

    def approve(self):
        transfer = self.submit()
        return self.approve_transfer(transfer)

    def source_row(self, event):
        return next(row for row in event.state["versions"][str(self.budget.pk)]["rows"] if row["cdf"] == str(self.source))

    def test_cancel_approved_is_audited_and_restores_balances_once(self):
        transfer = self.approve()
        before = BudgetHistoryEvent.objects.latest("pk")
        self.assertEqual(Decimal(self.source_row(before)["available"]), 40)
        act(pk=transfer.pk, actor=self.admin, revision=3, action="cancel", reason="Correction de saisie")
        self.assertEqual(self.balance(self.source), 100)
        self.assertEqual(self.balance(self.target), 0)
        after = BudgetHistoryEvent.objects.latest("pk")
        self.assertEqual(after.actor, "admin")
        self.assertIn("Correction de saisie", after.reason)
        self.assertEqual(Decimal(self.source_row(after)["available"]), 100)
        before.refresh_from_db()
        self.assertEqual(Decimal(self.source_row(before)["available"]), 40)
        with self.assertRaises(PermissionDenied):
            act(pk=transfer.pk, actor=self.admin, revision=4, action="cancel", reason="Deuxième essai")

    def test_transactions_show_both_transfer_legs_and_filter_combined_dimensions(self):
        transfer = self.approve()
        act(pk=transfer.pk, actor=self.admin, revision=3, action="cancel", reason="Correction")
        url = reverse("purchasing:budget_transactions")
        self.client.force_login(self.admin)
        response = self.client.get(url, {"version": self.budget.pk})
        movements = [row for row in response.context["page"] if row["transfers"]]
        self.assertEqual(
            [(row["cdf"], row["debit"], row["credit"]) for row in movements if row["cdf"] == str(self.source)],
            [(str(self.source), 0, 60), (str(self.source), 60, 0)],
        )
        self.assertEqual(
            [(row["debit"], row["credit"]) for row in movements if row["cdf"] == str(self.target)],
            [(60, 0), (0, 60)],
        )
        filters = {"version": self.budget.pk, "cdf": self.target.code.lower(),
                   "product": self.product.code.lower(), "funding": self.funding.code.lower()}
        response = self.client.get(url, filters)
        self.assertEqual(response.context["debit"], 60)
        self.assertEqual(response.context["credit"], 60)
        self.assertTrue(all(row["cdf"] == str(self.target) for row in response.context["page"]))
        response = self.client.get(url, {**filters, "funding": "unknown-funding"})
        self.assertEqual(response.context["page"].paginator.count, 0)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_cancel_approved_refused_if_destination_is_reserved(self):
        transfer = self.approve()
        outgoing = self.create_transfer("30")
        outgoing.source_cdf, outgoing.destination_cdf = self.target, self.source
        outgoing.save()
        act(pk=outgoing.pk, actor=self.owner, revision=0, action="submit")
        count = BudgetHistoryEvent.objects.count()
        with self.assertRaises(ValidationError):
            act(pk=transfer.pk, actor=self.admin, revision=3, action="cancel", reason="Annulation")
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "approved")
        self.assertEqual(BudgetHistoryEvent.objects.count(), count)

    def test_cancellation_permission_and_reason_are_required(self):
        transfer = self.approve()
        with self.assertRaises(PermissionDenied):
            act(pk=transfer.pk, actor=self.owner, revision=3, action="cancel")
        with self.assertRaises(ValidationError):
            act(pk=transfer.pk, actor=self.admin, revision=3, action="cancel")
        self.reviewer.user_permissions.add(Permission.objects.get(codename="cancel_any_budgettransfer"))
        self.reviewer = type(self.reviewer).objects.get(pk=self.reviewer.pk)
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.get(reverse("transfer_monitor")).status_code, 200)
        response = self.client.post(reverse("transfer_detail", args=[transfer.pk]),
            {"action": "cancel", "revision": 3, "reason": "Correction autorisée"})
        self.assertEqual(response.status_code, 302)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, "cancelled")

    def test_monitor_filters_and_permissions(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("transfer_monitor")).status_code, 200)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("transfer_monitor")), f'aria-label="Voir le workflow de la transaction {self.transfer.pk}"')
        self.assertNotContains(self.client.get(reverse("transfer_monitor"), {"status": "approved"}), f'aria-label="Voir le workflow de la transaction {self.transfer.pk}"')

    def test_history_at_date_and_before_first_record(self):
        before = BudgetHistoryEvent.objects.latest("pk")
        self.submit()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("purchasing:budget_history"), {"version": self.budget.pk, "at": before.created_at.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected"].pk, before.pk)
        self.assertEqual(Decimal(self.source_row(response.context["selected"])["available"]), 100)
        first = BudgetHistoryEvent.objects.first()
        response = self.client.get(reverse("purchasing:budget_history"), {"version": self.budget.pk, "at": (first.created_at-timedelta(days=1)).isoformat()})
        self.assertIsNone(response.context["state"])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("purchasing:budget_history")).status_code, 403)

    def test_allocation_changes_publication_and_replacement_are_frozen(self):
        before = BudgetHistoryEvent.objects.latest("pk")
        replacement = EnvelopeVersion.objects.create(envelope=self.envelope, label="V2")
        allocation = Allocation.objects.create(version=replacement, cost_center=self.source, funding=self.funding, budget_product=self.product, amount=200)
        allocation.amount = 250
        allocation.save()
        activate_envelope(actor=self.admin, version_id=replacement.pk)
        after = BudgetHistoryEvent.objects.latest("pk")
        self.assertEqual(after.state["versions"][str(self.budget.pk)]["status"], "Publiée remplacée")
        self.assertEqual(after.state["versions"][str(replacement.pk)]["status"], "Active")
        before.refresh_from_db()
        self.assertEqual(before.state["versions"][str(self.budget.pk)]["status"], "Active")
        with self.assertRaises(ValidationError):
            before.save()

    def test_history_rolls_back_with_budget_transaction(self):
        count = BudgetHistoryEvent.objects.count()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.create_transfer("10")
                raise RuntimeError("Rollback")
        self.assertEqual(BudgetHistoryEvent.objects.count(), count)
