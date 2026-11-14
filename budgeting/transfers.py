"""Annual-envelope locking shared with purchase reservations and budget publication."""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from purchasing.flow import require
from purchasing.models import AnnualEnvelope, EnvelopeVersion
from workflow.models import ConfigurationAuditEvent
from .models import BudgetTransfer, BudgetTransferBatch, TransferStep


def ensure_writable(version):
    if version.locked_at or version.deleted_at:
        raise ValidationError("La version budgétaire est bloquée ou supprimée.")


def batch_status(line_statuses):
    states = set(line_statuses)
    if "returned" in states:
        return "REJECTED", "À corriger"
    if states == {"approved"}:
        return "APPROVED", "Accompli"
    if not states or states == {"draft"}:
        return "DRAFT", "Brouillon"
    if states & {"pending", "draft"}:
        return "SUBMITTED", "En cours"
    if states == {"cancelled"}:
        return "CANCELLED", "Annulé"
    if states == {"rejected"}:
        return "REJECTED", "Refusé"
    if "approved" in states:
        return "SUBMITTED", "Partiellement accompli"
    return "REJECTED", "Non accompli"


def transfer_balance(version_id, cdf, funding, product):
    result = Decimal(0)
    combination = (cdf, funding, product)
    for transfer in BudgetTransfer.objects.filter(budget_version_id=version_id, status__in=["pending", "approved"]):
        if transfer.combination("source") == combination:
            result -= transfer.amount
        if transfer.status == "approved" and transfer.combination("destination") == combination:
            result += transfer.amount
    return result


def candidates(step):
    rule, transfer = step.rule, step.transfer
    users = get_user_model().objects.filter(is_active=True)
    if rule.get("automatic"):
        return users.none()
    if rule.get("cdf_manager"):
        return users.filter(managed_cost_centers=transfer.source_cdf)
    if rule.get("destination_cdf_manager"):
        return users.filter(managed_cost_centers=transfer.destination_cdf)
    if rule.get("support_manager"):
        return users.filter(managed_supports=transfer.support) if transfer.support_id else users.none()
    if rule.get("role_id"):
        return users.filter(roles=rule["role_id"])
    return users.filter(pk=rule.get("named_user_id"))


def is_assigned_validator(actor, step):
    return (actor.is_active and step.active and step.transfer.status == "pending"
            and step.state == "pending"
            and candidates(step).filter(pk=actor.pk).exists())


def can_decide(actor, step):
    return actor.is_active and step.active and (
        actor.has_perm("budgeting.decide_any_budgettransfer")
        or candidates(step).filter(pk=actor.pk).exists()
    )


def can_cancel(actor, transfer):
    if actor.has_perm("budgeting.cancel_any_budgettransfer"):
        return transfer.status in ("draft", "pending", "approved", "returned", "rejected")
    return (actor.has_perm("budgeting.add_budgettransfer") and transfer.created_by_id == actor.pk
            and transfer.status in ("draft", "pending", "returned"))


def audit(transfer, actor, action, **payload):
    ConfigurationAuditEvent.objects.create(actor=actor, action=action,
        object_type="budget_transfer", object_id=transfer.pk, payload=payload)


def advance(transfer):
    steps = list(transfer.steps.filter(active=True))
    for level in sorted({step.level for step in steps}):
        current = [step for step in steps if step.level == level]
        for step in current:
            if step.state == "approved":
                continue
            proof = next((proof for proof in steps if proof.state == "approved" and proof.approved_by_id
                          and proof.evidence_id is None and candidates(step).filter(pk=proof.approved_by_id).exists()), None)
            if step.rule.get("automatic") or (step.rule.get("reuse_evidence", True) and proof):
                step.state, step.approved_at = "approved", timezone.now()
                if not step.rule.get("automatic"):
                    step.approved_by, step.evidence = proof.approved_by, proof
                audit(transfer, None, "transfer.step_automatic", step_id=step.pk,
                      evidence_id=step.evidence_id, origin="system")
            else:
                step.state = "pending" if candidates(step).exists() else "unassigned"
            step.save()
        if any(step.state != "approved" for step in current):
            break
    if steps and all(step.state == "approved" for step in steps):
        transfer.status = "approved"
        audit(transfer, None, "transfer.approved", origin="system")


@transaction.atomic
def act(*, pk, actor, revision, action, step_id=None, reason=""):
    transfer = BudgetTransfer.objects.select_for_update().get(pk=pk)
    envelope = AnnualEnvelope.objects.select_for_update().get(pk=transfer.envelope_id)
    version = EnvelopeVersion.objects.select_for_update().get(pk=transfer.budget_version_id)
    if not actor.is_active:
        raise PermissionDenied
    if transfer.revision != revision:
        raise ValidationError("Le transfert a changé. Rechargez la page.")
    if action == "cancel":
        if not can_cancel(actor, transfer):
            raise PermissionDenied
    if action == "submit":
        require(actor, "budgeting.add_budgettransfer")
        if transfer.created_by_id != actor.pk:
            raise PermissionDenied
    if action == "submit":
        ensure_writable(version)
        if transfer.status not in ("draft", "returned"):
            raise ValidationError("Seul un brouillon ou une ligne à corriger peut être soumis.")
        transfer.full_clean()
        if not transfer.reason.strip() or transfer.combination("source") == transfer.combination("destination"):
            raise ValidationError("Précisez un motif et deux combinaisons budgétaires différentes.")
        from purchasing.flow import available
        if available(version, *transfer.combination("source")) < transfer.amount:
            raise ValidationError("Budget source insuffisant.")
        transfer.workflow, transfer.status = None, "pending"
        for level, label, target in (
            (1, "Responsable du CDF source", "cdf_manager"),
            (2, "Responsable du CDF destination", "destination_cdf_manager"),
        ):
            TransferStep.objects.create(transfer=transfer, label=label, level=level,
                rule={"fixed_flow": True, "automatic": False, "reuse_evidence": False, target: True})
        advance(transfer)
    elif action in ("cancel", "return"):
        if action == "return":
            require(actor, "budgeting.decide_any_budgettransfer")
            if not BudgetTransfer.objects.filter(batch_id=transfer.batch_id).exclude(status="approved").exists():
                raise ValidationError("Un transfert accompli ne peut plus être refusé. Utilisez l’annulation si vous disposez du droit.")
        privileged = actor.has_perm("budgeting.cancel_any_budgettransfer")
        if (privileged or action == "return") and not reason.strip():
            raise ValidationError("Un motif de retour est obligatoire." if action == "return" else "Un motif d’annulation est obligatoire.")
        if transfer.status not in ("draft", "pending", "approved", "returned", "rejected"):
            raise ValidationError("Ce transfert ne peut plus être annulé.")
        if transfer.status == "approved":
            from purchasing.flow import available
            ensure_writable(version)
            if available(version, *transfer.combination("destination")) < transfer.amount:
                raise ValidationError("Retour impossible : les fonds à destination ont déjà été utilisés." if action == "return"
                                      else "Annulation impossible : les fonds à destination ont déjà été utilisés.")
        transfer.status = "returned" if action == "return" else "cancelled"
        if action == "return":
            transfer.return_reason = reason.strip()
        transfer.steps.exclude(state="approved").update(state="stopped")
        transfer.steps.update(active=False)
    elif action == "approve_all":
        require(actor, "budgeting.decide_any_budgettransfer")
        ensure_writable(version)
        if transfer.status != "pending":
            raise ValidationError("Ce transfert n’est plus en validation.")
        if not transfer.steps.filter(active=True).exists():
            raise ValidationError("Ce transfert ne possède aucune étape de validation.")
        advance(transfer)
        while transfer.status == "pending":
            step = transfer.steps.filter(active=True, state__in=["pending", "unassigned"]).first()
            if step is None:
                raise ValidationError("Le circuit de validation ne peut pas être terminé.")
            step.state, step.approved_by, step.approved_at = "approved", actor, timezone.now()
            step.save()
            audit(transfer, actor, "transfer.approve", step_id=step.pk, full_workflow=True)
            advance(transfer)
    elif action in ("approve", "reject"):
        if action == "approve":
            ensure_writable(version)
        if transfer.status != "pending":
            raise ValidationError("Ce transfert n’est plus en validation.")
        advance(transfer)
        step = transfer.steps.filter(pk=step_id, active=True).first()
        if step is None or step.state not in ("pending", "unassigned") or not can_decide(actor, step):
            raise PermissionDenied
        if action == "reject":
            if not reason.strip():
                raise ValidationError("Justifiez le rejet.")
            transfer.status = "rejected"
            transfer.steps.exclude(state="approved").update(state="stopped")
        else:
            step.state, step.approved_by, step.approved_at = "approved", actor, timezone.now()
            step.save()
            advance(transfer)
    else:
        raise ValidationError("Action inconnue.")
    transfer.revision += 1
    transfer._history_actor = actor
    action_label = {"submit": "Soumission", "cancel": "Annulation", "return": "Retour au demandeur",
                    "approve": "Validation", "approve_all": "Validation du circuit complet", "reject": "Rejet"}.get(action, action)
    transfer._history_reason = f"{transfer} · {action_label} · {reason}"[:200]
    transfer.save()
    audit(transfer, actor, f"transfer.{action}", reason=reason, step_id=step_id, revision=transfer.revision)
    return transfer


@transaction.atomic
def approve_batch(*, batch_pk, actor, revisions):
    require(actor, "budgeting.decide_any_budgettransfer")
    batch = BudgetTransferBatch.objects.get(pk=batch_pk)
    lines = list(BudgetTransfer.objects.select_for_update().filter(batch_id=batch.key).order_by("pk"))
    if not lines or {str(line.pk): line.revision for line in lines} != revisions:
        raise ValidationError("Le transfert a changé. Rechargez la liste avant de valider.")
    if any(line.status not in ("pending", "approved") for line in lines):
        raise ValidationError("La validation globale nécessite des lignes en validation ou déjà approuvées. Une ligne est en brouillon, refusée ou annulée.")
    pending = [line for line in lines if line.status == "pending"]
    if not pending:
        raise ValidationError("Ce transfert est déjà accompli.")
    for line in pending:
        act(pk=line.pk, actor=actor, revision=line.revision, action="approve_all")
    return len(pending)


@transaction.atomic
def close_batch(*, batch_pk, actor, revisions, action, reason):
    if action not in ("return", "cancel"):
        raise ValidationError("Action globale invalide.")
    require(actor, "budgeting.decide_any_budgettransfer" if action == "return" else "budgeting.cancel_any_budgettransfer")
    if not reason.strip():
        raise ValidationError("Un motif est obligatoire.")
    batch = BudgetTransferBatch.objects.get(pk=batch_pk)
    lines = list(BudgetTransfer.objects.select_for_update().filter(batch_id=batch.key).order_by("pk"))
    if not lines or {str(line.pk): line.revision for line in lines} != revisions:
        raise ValidationError("Le transfert a changé. Rechargez la liste avant de continuer.")
    if action == "return" and all(line.status == "approved" for line in lines):
        raise ValidationError("Un transfert accompli ne peut plus être refusé. Utilisez l’annulation si vous disposez du droit.")
    if action == "return" and any(line.status == "cancelled" for line in lines):
        raise ValidationError("Un transfert annulé ne peut pas être renvoyé au demandeur.")
    active = [line for line in lines if line.status != "cancelled"]
    if not active:
        raise ValidationError("Ce transfert est définitivement annulé.")
    for line in active:
        act(pk=line.pk, actor=actor, revision=line.revision, action=action, reason=reason)
    return len(active)


@transaction.atomic
def refresh(pk):
    transfer = BudgetTransfer.objects.select_for_update().get(pk=pk)
    if transfer.status == "pending":
        AnnualEnvelope.objects.select_for_update().get(pk=transfer.envelope_id)
        version = EnvelopeVersion.objects.select_for_update().get(pk=transfer.budget_version_id)
        if version.locked_at or version.deleted_at:
            return transfer
        advance(transfer)
        transfer.save()
    return transfer
