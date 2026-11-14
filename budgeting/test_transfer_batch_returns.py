from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import BudgetTransfer, BudgetTransferBatch
from . import test_transfers as fixtures
from .transfers import act, close_batch, approve_batch


class BatchReturnTests(TestCase):
    setUp = fixtures.TransferTests.setUp
    create_transfer = fixtures.TransferTests.create_transfer
    payload = fixtures.TransferTests.payload
    batch_payload = fixtures.TransferTests.batch_payload
    create_pending_batch = fixtures.TransferVisibilityTests.create_pending_batch
    approve_transfer = fixtures.TransferTests.approve_transfer
    balance = fixtures.TransferTests.balance

    def batch(self, lines):
        return BudgetTransferBatch.objects.get(key=lines[0].batch_id)

    def revisions(self, lines):
        return {str(line.pk): line.revision for line in lines}

    def test_completed_batch_cannot_be_refused_but_can_be_cancelled_with_permission(self):
        lines = self.create_pending_batch()
        for line in lines:
            self.approve_transfer(line)
            line.refresh_from_db()
        batch = self.batch(lines)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("transfer_monitor"), {"number": batch.pk})
        group = list(response.context["page"])[0]
        self.assertEqual(group["status_label"], "Accompli")
        self.assertFalse(group["can_return_all"])
        self.assertTrue(group["can_cancel_all"])
        response = self.client.post(reverse("transfer_batch_close", args=[batch.pk]), {
            "action": "return_batch", "snapshot": group["snapshot"], "reason": "Trop tard",
        }, follow=True)
        self.assertContains(response, "Un transfert accompli ne peut plus être refusé")
        with self.assertRaises(ValidationError):
            act(pk=lines[0].pk, actor=self.admin, revision=lines[0].revision,
                action="return", reason="Contournement")
        self.assertFalse(BudgetTransfer.objects.filter(batch_id=batch.key).exclude(status="approved").exists())
        with self.assertRaises(PermissionDenied):
            close_batch(batch_pk=batch.pk, actor=self.owner, revisions=self.revisions(lines),
                        action="cancel", reason="Sans droit")
        close_batch(batch_pk=batch.pk, actor=self.admin, revisions=self.revisions(lines),
                    action="cancel", reason="Annulation autorisée")
        self.assertFalse(BudgetTransfer.objects.filter(batch_id=batch.key).exclude(status="cancelled").exists())
        self.assertEqual(self.balance(self.source), 100)
        self.assertEqual(self.balance(self.target), 0)

    def test_global_refusal_returns_every_line_and_notifies_requester(self):
        lines = self.create_pending_batch()
        self.approve_transfer(lines[0])
        self.client.force_login(self.admin)
        group = list(self.client.get(reverse("transfer_monitor")).context["page"])[0]
        response = self.client.post(reverse("transfer_batch_close", args=[group["number"]]), {
            "action": "return_batch", "snapshot": group["snapshot"], "reason": "Corriger les montants",
        }, follow=True)
        self.assertContains(response, "renvoyée(s) au demandeur")
        for line in lines:
            line.refresh_from_db()
            self.assertEqual(line.status, "returned")
            self.assertEqual(line.return_reason, "Corriger les montants")
            self.assertFalse(line.steps.filter(active=True).exists())
        self.assertEqual(self.balance(self.source), 100)
        self.assertEqual(self.balance(self.target), 0)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("my_validations"))
        self.assertEqual(len(response.context["returned_transfers"]), 3)
        self.assertEqual(response.context["pending_validation_count"], 3)
        self.assertContains(response, "Corriger les montants")

    def test_requester_can_correct_and_resubmit_without_losing_previous_decisions(self):
        lines = self.create_pending_batch()
        self.approve_transfer(lines[0])
        lines[0].refresh_from_db()
        close_batch(batch_pk=self.batch(lines).pk, actor=self.admin, revisions=self.revisions(lines),
                    action="return", reason="À revoir")
        line = lines[0]
        line.refresh_from_db()
        previous = list(line.steps.values_list("pk", "approved_by_id", "approved_at"))
        self.client.force_login(self.owner)
        response = self.client.get(reverse("transfer_correct", args=[line.pk]))
        self.assertEqual(response.status_code, 200)
        data = {field: getattr(line, field + "_id") or "" for field in (
            "source_cdf", "source_product", "source_funding", "source_support",
            "destination_cdf", "destination_product", "destination_funding", "destination_support")}
        data.update(amount="15", reason="Montant corrigé", revision=line.revision)
        response = self.client.post(reverse("transfer_correct", args=[line.pk]), data)
        self.assertRedirects(response, reverse("transfer_detail", args=[line.pk]))
        line.refresh_from_db()
        self.assertEqual(line.status, "pending")
        self.assertEqual(line.amount, Decimal("15"))
        self.assertEqual(line.batch_id, lines[1].batch_id)
        self.assertEqual(list(line.steps.filter(active=False).values_list("pk", "approved_by_id", "approved_at")), previous)
        self.assertEqual(line.steps.filter(active=True).count(), 2)
        with self.assertRaises(PermissionDenied):
            act(pk=line.pk, actor=self.admin, revision=line.revision, action="approve", step_id=previous[0][0])
        act(pk=line.pk, actor=self.admin, revision=line.revision, action="approve_all")
        line.refresh_from_db()
        self.assertEqual(line.status, "approved")

    def test_global_cancellation_is_permanent_and_has_no_more_actions(self):
        lines = self.create_pending_batch()
        batch = self.batch(lines)
        close_batch(batch_pk=batch.pk, actor=self.admin, revisions=self.revisions(lines),
                    action="cancel", reason="Abandon définitif")
        for line in lines:
            line.refresh_from_db()
            self.assertEqual(line.status, "cancelled")
            with self.assertRaises(ValidationError):
                act(pk=line.pk, actor=self.owner, revision=line.revision, action="submit")
        with self.assertRaises(ValidationError):
            close_batch(batch_pk=batch.pk, actor=self.admin, revisions=self.revisions(lines),
                        action="return", reason="Réouvrir")
        with self.assertRaises(ValidationError):
            approve_batch(batch_pk=batch.pk, actor=self.admin, revisions=self.revisions(lines))
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("transfer_correct", args=[lines[0].pk])).status_code, 403)
        self.client.force_login(self.admin)
        group = list(self.client.get(reverse("transfer_monitor")).context["page"])[0]
        self.assertEqual(group["status_label"], "Annulé")
        self.assertFalse(group["can_return_all"] or group["can_cancel_all"] or group["can_approve_all"])

    def test_global_close_requires_permission_reason_and_fresh_snapshot(self):
        lines = self.create_pending_batch()
        batch = self.batch(lines)
        for action in ("return", "cancel"):
            with self.assertRaises(PermissionDenied):
                close_batch(batch_pk=batch.pk, actor=self.reviewer, revisions=self.revisions(lines), action=action, reason="Erreur")
            with self.assertRaises(ValidationError):
                close_batch(batch_pk=batch.pk, actor=self.admin, revisions=self.revisions(lines), action=action, reason="  ")
            with self.assertRaises(ValidationError):
                close_batch(batch_pk=batch.pk, actor=self.admin, revisions={}, action=action, reason="Erreur")

    def test_failed_reversal_rolls_back_the_entire_global_action(self):
        lines = self.create_pending_batch()
        for line in lines:
            self.approve_transfer(line)
            line.refresh_from_db()
        outgoing = self.create_transfer("25")
        outgoing.source_cdf, outgoing.destination_cdf = self.target, self.source
        outgoing.save()
        act(pk=outgoing.pk, actor=self.owner, revision=0, action="submit")
        for action in ("return", "cancel"):
            with self.assertRaises(ValidationError):
                close_batch(batch_pk=self.batch(lines).pk, actor=self.admin, revisions=self.revisions(lines),
                            action=action, reason="Erreur")
            for line in lines:
                line.refresh_from_db()
                self.assertEqual(line.status, "approved")
                self.assertTrue(line.steps.filter(active=True).exists())
        self.assertEqual(self.balance(self.target), 35)

    def test_correction_cannot_exceed_budget_or_be_submitted_by_someone_else(self):
        lines = self.create_pending_batch()
        close_batch(batch_pk=self.batch(lines).pk, actor=self.admin, revisions=self.revisions(lines),
                    action="return", reason="Corriger")
        line = lines[0]
        line.refresh_from_db()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("transfer_correct", args=[line.pk])).status_code, 404)
        self.client.force_login(self.owner)
        data = {field: getattr(line, field + "_id") or "" for field in (
            "source_cdf", "source_product", "source_funding", "source_support",
            "destination_cdf", "destination_product", "destination_funding", "destination_support")}
        data.update(amount="101", reason="Trop élevé", revision=line.revision)
        response = self.client.post(reverse("transfer_correct", args=[line.pk]), data)
        self.assertContains(response, "Budget source insuffisant")
        line.refresh_from_db()
        self.assertEqual(line.status, "returned")
        self.assertEqual(line.amount, Decimal("10"))
