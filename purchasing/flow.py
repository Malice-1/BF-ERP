"""Transactional purchase lifecycle. Lock order: request, annual envelope, steps."""
from collections import defaultdict
from decimal import Decimal, localcontext
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, connection
from django.db.models import Q
from django.utils import timezone
from accounts.services import eligible_authorization
from accounts.models import Role
from workflow.models import ConfigurationAuditEvent
from .models import (PurchaseRequest, AnnualEnvelope, EnvelopeVersion,
    ApprovalStep, Submission, LineSnapshot, BudgetEntry, PurchaseOrder,
    Delegation, PurchaseNotice)
from .exceptions import PurchaseRequestError, PurchaseRequestConflict
from .services import _audit


def require(actor, permission):
    if not actor.is_active or not actor.has_perm(permission):
        raise PermissionDenied


def context(snapshot):
    return dict(cost_center=snapshot.cost_center_id, funding=snapshot.funding_id,
                budget_product=snapshot.budget_product_id)


def _step_grant(user, step):
    if not user.is_active:
        return None
    if step.manager_source:
        entity = step.snapshot.cost_center if step.manager_source == "cdf" else step.snapshot.support
        return user if entity is not None and entity.managers.filter(pk=user.pk).exists() else None
    if step.role_id:
        return step.role if user.roles.filter(pk=step.role_id).exists() else None
    if step.rule_snapshot.get("rule_based") and step.rule_snapshot.get("named_user_id"):
        return user if user.pk == step.rule_snapshot["named_user_id"] else None
    return eligible_authorization(user=user, function=step.function, context=context(step.snapshot)) if step.function_id else None


def _record_grant(step, auth):
    grant, represented = auth
    step.authorization = grant if not isinstance(grant, (Role, get_user_model())) else None
    step.evaluated_scope = {**context(step.snapshot), "represented_user": represented.pk}
    if step.manager_source:
        step.evaluated_scope["manager_source"] = step.manager_source
        if step.manager_source == "support":
            step.evaluated_scope.update(support_id=step.snapshot.support_id,
                                       support=step.snapshot.data.get("support"))
    if isinstance(grant, Role):
        step.evaluated_scope.update(role_id=grant.pk, role_code=grant.code, role_label=grant.label)


def authority(user, step):
    """Return the complete current grant and the represented user, no delegation chains."""
    if user is None or not user.is_active:
        return None
    candidates = list(step.candidates.filter(is_active=True).order_by("pk"))
    now = timezone.now()
    delegated = set(Delegation.objects.filter(delegate=user, valid_from__lte=now,
        valid_until__gt=now, principal__is_active=True).values_list("principal_id", flat=True))
    for candidate in candidates:
        if candidate.pk != user.pk and candidate.pk not in delegated:
            continue
        grant = _step_grant(candidate, step)
        if grant:
            return grant, candidate
    return None


def pending_validation_count(user):
    """Count actionable tasks, including replacements, using current assignments."""
    if not user.is_authenticated or not user.is_active:
        return 0
    now = timezone.now()
    principals = [user.pk, *Delegation.objects.filter(
        delegate=user, principal__is_active=True, valid_from__lte=now,
        valid_until__gt=now).values_list("principal_id", flat=True)]
    relevant = ApprovalStep.objects.filter(snapshot__submission__active=True).filter(
        Q(candidates__pk__in=principals)
        | Q(manager_source="cdf", snapshot__cost_center__managers__pk__in=principals)
        | Q(manager_source="support", snapshot__support__managers__pk__in=principals)
    )
    submission_ids = list(relevant.order_by("snapshot__submission_id").values_list(
        "snapshot__submission_id", flat=True).distinct())
    for submission_id in submission_ids:
        refresh_submission(submission_id)
    steps = ApprovalStep.objects.filter(
        snapshot__submission_id__in=submission_ids, snapshot__submission__active=True,
        state="pending").select_related("function", "role", "snapshot__cost_center", "snapshot__funding").prefetch_related("candidates")
    return sum(authority(user, step) is not None for step in steps)


def _notice(step, recipient, kind, message):
    # Each state transition has a new request revision. Repeated refreshes deduplicate.
    revision = step.snapshot.submission.purchase_request.revision
    PurchaseNotice.objects.get_or_create(key=f"{step.pk}:{revision}:{kind}:{recipient.pk}",
        defaults=dict(step=step, recipient=recipient, message=message))


def _administrators():
    return get_user_model().objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(user_permissions__codename="reassign_approvals") |
        Q(groups__permissions__codename="reassign_approvals") |
        Q(roles__permissions__codename="reassign_approvals")).distinct()


def _state_notice(step, old):
    if step.state == old:
        return
    PurchaseNotice.objects.filter(step=step, active=True).update(active=False)
    event = ConfigurationAuditEvent.objects.create(actor=step.snapshot.submission.purchase_request.created_by,
        action="step.state_changed", object_type="approval_step", object_id=step.pk,
        payload={"from": old, "to": step.state, "origin": "system"})
    if step.state in ("pending", "blocked", "unassigned"):
        users = {u.pk: u for u in step.candidates.filter(is_active=True)}
        if step.state in ("blocked", "unassigned"):
            users.update({u.pk: u for u in _administrators()})
        for user in users.values():
            _notice(step, user, f"{step.state}:{event.pk}",
                f"{step.snapshot.submission.purchase_request.number}, ligne {step.snapshot.original_line_id} — {step.function_label} : {step.get_state_display()}.")


def _advance(submission):
    """Validate lines in parallel and follow the steps of each line in order."""
    waiting = False
    current_snapshot_id = None
    steps = ApprovalStep.objects.filter(snapshot__submission=submission).select_related(
        "function", "snapshot__submission__purchase_request", "snapshot__cost_center", "snapshot__support"
    ).order_by("snapshot__original_line_id", "snapshot_id", "level", "pk")
    for step in steps:
        if step.snapshot_id != current_snapshot_id:
            current_snapshot_id = step.snapshot_id
            waiting = False
        if step.state == "approved":
            continue
        if waiting:
            if step.state != "future" or step.waiting_since is not None:
                step.state = "future"
                step.waiting_since = None
                step.save(update_fields=["state", "waiting_since"])
            PurchaseNotice.objects.filter(step=step, active=True).update(active=False)
            continue
        snapshot = step.snapshot
        old = step.state
        if step.rule_snapshot.get("automatic"):
            step.state = "approved"
            step.approved_at = timezone.now()
            step.evaluated_scope = {"origin": "system", "reason": "configured_automatic_rule"}
            step.save()
            _state_notice(step, old)
            continue
        previous_candidates = set(step.candidates.values_list("pk", flat=True))
        if step.manager_source:
            entity = snapshot.cost_center if step.manager_source == "cdf" else snapshot.support
            step.candidates.set(entity.managers.filter(is_active=True) if entity else [])
            PurchaseNotice.objects.filter(step=step, active=True, recipient_id__in=previous_candidates).exclude(
                recipient_id__in=step.candidates.values_list("pk", flat=True)).update(active=False)
        candidates = list(step.candidates.filter(is_active=True))
        eligible = [u for u in candidates if _step_grant(u, step)]
        step.state = "pending" if eligible else ("blocked" if step.candidates.exists() else "unassigned")
        if step.waiting_since is None:
            step.waiting_since = timezone.now()
        for proof in snapshot.steps.filter(state="approved", evidence__isnull=True).select_related("approved_by"):
            if not step.rule_snapshot.get("reuse_evidence", True):
                break
            auth = authority(proof.approved_by, step)
            if auth:
                step.state = "approved"
                step.approved_by = proof.approved_by
                step.approved_at = timezone.now()
                _record_grant(step, auth)
                step.evidence = proof
                break
        step.save()
        _state_notice(step, old)
        if old == step.state == "pending" and step.manager_source:
            for candidate in step.candidates.exclude(pk__in=previous_candidates):
                _notice(step, candidate, "manager_assigned", "Une validation vous a été affectée.")
        waiting = step.state != "approved"


def _lock_request(request_id, actor, expected_revision, owner=False):
    purchase = PurchaseRequest.objects.select_for_update().get(pk=request_id)
    if not actor.is_active or (owner and purchase.created_by_id != actor.pk):
        raise PermissionDenied
    if purchase.revision != expected_revision:
        raise PurchaseRequestConflict("La demande a changé. Rechargez la page.")
    return purchase


def _config_audit(actor, obj, action):
    ConfigurationAuditEvent.objects.create(actor=actor, object_type=obj._meta.model_name,
        object_id=obj.pk, action=action)


def available(version, cost_center_id, funding_id, budget_product_id):
    allocation = version.allocations.filter(cost_center_id=cost_center_id, funding_id=funding_id,
        budget_product_id=budget_product_id).first()
    entries = BudgetEntry.objects.filter(state__in=["reserved", "committed"],
        snapshot__submission__budget_version__envelope_id=version.envelope_id,
        snapshot__cost_center_id=cost_center_id, snapshot__funding_id=funding_id,
        snapshot__budget_product_id=budget_product_id)
    from budgeting.transfers import transfer_balance
    return (allocation.amount if allocation else Decimal(0)) - sum((e.amount for e in entries), Decimal(0)) + transfer_balance(version.pk, cost_center_id, funding_id, budget_product_id)


@transaction.atomic
def activate_envelope(*, actor, version_id):
    require(actor, "budgeting.change_envelopeversion")
    initial = EnvelopeVersion.objects.get(pk=version_id)
    envelope = AnnualEnvelope.objects.select_for_update().get(pk=initial.envelope_id)
    version = EnvelopeVersion.objects.select_for_update().get(pk=version_id)
    if version.locked_at or version.deleted_at:
        raise ValidationError("Cette version est bloquée ou supprimée et ne peut plus être publiée.")
    if version.published_at or not version.allocations.exists():
        raise ValidationError("Version déjà publiée ou sans allocations.")
    for allocation in version.allocations.all():
        allocation.full_clean()
    version.published_at = timezone.now()
    version.save(update_fields=["published_at"])
    envelope.active_version = version
    envelope.save(update_fields=["active_version"])
    _config_audit(actor, version, "budget.activated")
    return version


@transaction.atomic
def lock_envelope(*, actor, version_id):
    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied
    initial = EnvelopeVersion.objects.get(pk=version_id)
    AnnualEnvelope.objects.select_for_update().get(pk=initial.envelope_id)
    version = EnvelopeVersion.objects.select_for_update().get(pk=version_id)
    if version.deleted_at or (version.locked_at and not version.editing_unlocked_at) or (version.published_at and not version.editing_unlocked_at):
        raise ValidationError("Cette version est déjà bloquée ou publiée et en lecture seule.")
    # A published version stays operational; only its allocation editing is closed.
    if not version.published_at:
        version.locked_at = timezone.now()
    version.editing_unlocked_at = None
    version._history_actor = actor
    version._history_reason = "Blocage des modifications de la version budgétaire"
    _save_editing_state(version, actor)
    _config_audit(actor, version, "budget.edit_locked")
    return version


@transaction.atomic
def unlock_envelope(*, actor, version_id):
    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied
    initial = EnvelopeVersion.objects.get(pk=version_id)
    AnnualEnvelope.objects.select_for_update().get(pk=initial.envelope_id)
    version = EnvelopeVersion.objects.select_for_update().get(pk=version_id)
    if version.deleted_at:
        raise ValidationError("Une version supprimée ne peut pas être débloquée.")
    if version.editing_unlocked_at or (not version.published_at and not version.locked_at):
        raise ValidationError("Les modifications de cette version sont déjà débloquées.")
    version.locked_at = None
    version.editing_unlocked_at = timezone.now() if version.published_at else None
    version._history_actor = actor
    version._history_reason = "Déblocage des modifications de la version budgétaire"
    _save_editing_state(version, actor)
    _config_audit(actor, version, "budget.edit_unlocked")
    return version


def _save_editing_state(version, actor):
    """Allow only this admin transition through the PostgreSQL publication guard."""
    version._editing_state_actor = actor
    previous = ""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('bf_erp.budget_edit_state', true)")
            previous = cursor.fetchone()[0] or ""
            cursor.execute("SELECT set_config('bf_erp.budget_edit_state', 'on', true)")
    try:
        version.save(update_fields=["locked_at", "editing_unlocked_at"])
    finally:
        del version._editing_state_actor
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('bf_erp.budget_edit_state', %s, true)", [previous])


@transaction.atomic
def delete_envelope_version(*, actor, version_id):
    require(actor, "budgeting.delete_envelopeversion")
    initial = EnvelopeVersion.objects.get(pk=version_id)
    envelope = AnnualEnvelope.objects.select_for_update().get(pk=initial.envelope_id)
    version = EnvelopeVersion.objects.select_for_update().get(pk=version_id)
    if (version.published_at or version.locked_at or version.deleted_at
            or envelope.active_version_id == version.pk or Submission.objects.filter(budget_version=version).exists() or version.transfers.exists()):
        raise ValidationError("Seul un brouillon non bloqué et non utilisé peut être supprimé.")
    version.deleted_at = timezone.now()
    version._history_actor = actor
    version._history_reason = "Suppression de la version budgétaire"
    version.save(update_fields=["deleted_at"])
    return version


@transaction.atomic
def submit_purchase(*, request_id, actor, expected_revision):
    with localcontext() as precision:
        precision.prec = 50
        purchase = _lock_request(request_id, actor, expected_revision, owner=True)
        if purchase.status not in ("DRAFT", "CORRECTION"):
            raise PurchaseRequestError("Seul un brouillon ou une demande à corriger peut être soumis.")
        lines = list(purchase.lines.select_related("detailed_product__budget_product", "cost_center", "funding"))
        if not lines:
            raise PurchaseRequestError("Ajoutez au moins une ligne.")
        for line in lines:
            line.full_clean()
            if line.vat_rate is None:
                raise PurchaseRequestError("Renseignez tous les taux de TVA.")
            if line.total_tvac >= Decimal("1000000000000000000"):
                raise PurchaseRequestError("Le montant de la ligne dépasse la capacité budgétaire de stockage.")
        envelope = AnnualEnvelope.objects.select_for_update().filter(year=timezone.localdate().year).first()
        if not envelope or not envelope.active_version_id:
            raise PurchaseRequestError("Aucune version budgétaire active pour l'année courante.")
        version = envelope.active_version
        contract_snapshot = None
        if purchase.framework_contract_id:
            from .framework_contracts import reserve_for_submission
            contract_snapshot = reserve_for_submission(purchase, lines)
        totals = defaultdict(Decimal)
        for line in lines:
            totals[(line.cost_center_id, line.funding_id, line.detailed_product.budget_product_id)] += line.total_tvac
        for combination, amount in totals.items():
            balance = available(version, *combination)
            if balance < amount or balance < 0:
                raise PurchaseRequestError("Budget insuffisant : disponible "
                    f"{balance:.2f} EUR, nécessaire {amount:.2f} EUR. Aucune réservation effectuée.".replace(".", ",", 2))
        submission = Submission.objects.create(purchase_request=purchase, budget_version=version,
            supplier_data={"name": purchase.supplier.name, "code": purchase.supplier.code, "vat_number": purchase.supplier.vat_number})
        for line in lines:
            data = {key: str(getattr(line, key)) for key in ("description", "quantity", "unit_price", "vat_rate", "total_htva", "total_vat", "total_tvac")}
            data.update(product=str(line.detailed_product), cost_center=str(line.cost_center), funding=str(line.funding),
                        support=str(purchase.support) if purchase.support_id else None)
            if contract_snapshot:
                data["framework_contract"] = contract_snapshot
            snapshot = LineSnapshot.objects.create(submission=submission, line=line, original_line_id=line.pk, data=data,
                amount=line.total_tvac, cost_center=line.cost_center, funding=line.funding, support=purchase.support,
                budget_product=line.detailed_product.budget_product)
            BudgetEntry.objects.create(snapshot=snapshot, amount=line.total_tvac)
            step = ApprovalStep.objects.create(snapshot=snapshot,
                function_label="Responsable du CDF de la ligne", level=1, manager_source="cdf",
                rule_snapshot={"fixed_flow": True, "operation": "purchase", "automatic": False,
                               "reuse_evidence": False, "cdf_manager": True})
            step.candidates.set(line.cost_center.managers.filter(is_active=True))
        purchase.status = "SUBMITTED"
        _audit(purchase, actor, "request.submitted", {"submission": submission.pk})
        _advance(submission)
        _finish(purchase, submission, actor)
        if purchase.status == "ORDERED":
            _audit(purchase, None, "request.ordered", {"origin": "system", "submission": submission.pk})
        return purchase


def _finish(purchase, submission, actor):
    if not submission.lines.exists() or submission.lines.filter(steps__isnull=True).exists():
        return
    if submission.lines.filter(steps__state__in=["future", "pending", "blocked", "unassigned"]).exists():
        return
    order, _ = PurchaseOrder.objects.get_or_create(purchase_request=purchase, defaults=dict(submission=submission,
        supplier_data=submission.supplier_data))
    from accounting.purchase_posting import create_engagement_draft
    create_engagement_draft(order, actor)
    BudgetEntry.objects.filter(snapshot__submission=submission, state="reserved").update(state="committed")
    from budgeting.history import capture
    capture(submission.budget_version.envelope_id, "Réservations converties en engagements")
    purchase.status = "ORDERED"
    submission.active = False
    submission.save(update_fields=["active"])


@transaction.atomic
def decide(*, request_id, actor, expected_revision, step_id, decision, reason=""):
    purchase = _lock_request(request_id, actor, expected_revision)
    if purchase.status != "SUBMITTED":
        raise PurchaseRequestError("Cette demande n'est plus en validation.")
    submission = purchase.submissions.get(active=True)
    AnnualEnvelope.objects.select_for_update().get(pk=submission.budget_version.envelope_id)
    _advance(submission)
    step = ApprovalStep.objects.select_for_update(of=("self",)).select_related("snapshot", "function").get(pk=step_id, snapshot__submission=submission)
    auth = authority(actor, step)
    admin_override = actor.is_active and actor.has_perm("purchasing.decide_any_purchaserequest")
    if decision == "approve_all":
        require(actor, "purchasing.decide_any_purchaserequest")
        while purchase.status == "SUBMITTED":
            current = ApprovalStep.objects.filter(snapshot__submission=submission,
                state__in=["pending", "unassigned", "blocked"]).first()
            if current is None:
                raise PurchaseRequestError("Le circuit de validation ne peut pas être terminé.")
            decide(request_id=purchase.pk, actor=actor, expected_revision=purchase.revision,
                step_id=current.pk, decision="approve")
            purchase.refresh_from_db()
        return purchase
    if not (admin_override and step.state in ("pending", "unassigned", "blocked")) and (step.state != "pending" or not auth):
        raise PermissionDenied("Étape inaccessible ou habilitation absente.")
    if decision not in ("approve", "correct", "reject"):
        raise ValidationError("Décision inconnue.")
    if decision != "approve" and not reason.strip():
        raise ValidationError("Un motif est obligatoire.")
    if decision == "approve":
        step.state, step.approved_by, step.approved_at = "approved", actor, timezone.now()
        if admin_override:
            step.authorization = None
            step.evaluated_scope = {**context(step.snapshot), "admin_override": True, "represented_user": actor.pk}
        else:
            _record_grant(step, auth)
        step.save()
        PurchaseNotice.objects.filter(step=step, active=True).update(active=False)
        _advance(submission)
        _finish(purchase, submission, actor)
    else:
        _stop(submission)
        purchase.status = "CORRECTION" if decision == "correct" else "REJECTED"
    _audit(purchase, actor, "request." + decision, {"step": step.pk, "reason": reason,
        "admin_override": admin_override,
        "authorization": None if admin_override or isinstance(auth[0], (Role, get_user_model())) else auth[0].pk,
        "role": auth[0].pk if not admin_override and isinstance(auth[0], Role) else None,
        "represented_user": actor.pk if admin_override else auth[1].pk})
    return purchase


def _stop(submission):
    BudgetEntry.objects.filter(snapshot__submission=submission, state="reserved").update(state="released")
    from budgeting.history import capture
    capture(submission.budget_version.envelope_id, "Réservations libérées")
    ApprovalStep.objects.filter(snapshot__submission=submission).exclude(state="approved").update(state="stopped")
    PurchaseNotice.objects.filter(step__snapshot__submission=submission, active=True).update(active=False)
    submission.active = False
    submission.save(update_fields=["active"])


@transaction.atomic
def cancel_submitted(*, request_id, actor, expected_revision):
    purchase = _lock_request(request_id, actor, expected_revision, owner=True)
    if purchase.status != "SUBMITTED":
        raise PurchaseRequestError("La demande n'est plus en validation.")
    submission = purchase.submissions.get(active=True)
    AnnualEnvelope.objects.select_for_update().get(pk=submission.budget_version.envelope_id)
    _stop(submission)
    purchase.status = "CANCELLED"
    _audit(purchase, actor, "request.cancelled")
    return purchase


@transaction.atomic
def reassign(*, request_id, actor, expected_revision, step_id, user, reason):
    require(actor, "purchasing.reassign_approvals")
    purchase = _lock_request(request_id, actor, expected_revision)
    step = ApprovalStep.objects.select_for_update(of=("self",)).select_related("snapshot", "function").get(
        pk=step_id, snapshot__submission__purchase_request=purchase, snapshot__submission__active=True)
    if step.state not in ("pending", "blocked", "unassigned") or not reason.strip():
        raise ValidationError("Étape non réaffectable ou justification manquante.")
    grant = _step_grant(user, step)
    if not grant:
        raise ValidationError("Utilisateur inactif ou non habilité à cette fonction et ce périmètre.")
    old_users = list(step.candidates.all())
    PurchaseNotice.objects.filter(step=step, active=True).update(active=False)
    step.candidates.set([user])
    _audit(purchase, actor, "step.reassigned", {"step": step.pk, "old": [u.pk for u in old_users], "new": user.pk, "reason": reason})
    _advance(step.snapshot.submission)
    for recipient in {u.pk: u for u in [*old_users, user, actor]}.values():
        _notice(step, recipient, "reassigned", "Réaffectation d'une étape de validation enregistrée.")
    return purchase


@transaction.atomic
def refresh_submission(submission_id):
    initial = Submission.objects.get(pk=submission_id)
    purchase = PurchaseRequest.objects.select_for_update().get(pk=initial.purchase_request_id)
    submission = Submission.objects.get(pk=submission_id)
    if submission.active:
        AnnualEnvelope.objects.select_for_update().get(pk=submission.budget_version.envelope_id)
        _advance(submission)
        _finish(purchase, submission, None)
        if purchase.status == "ORDERED":
            _audit(purchase, purchase.created_by, "request.ordered", {"origin": "system"})


@transaction.atomic
def create_delegation(*, actor, principal, delegate, valid_from, valid_until):
    if not actor.is_active or (actor.pk != principal.pk and not actor.has_perm("purchasing.reassign_approvals")):
        raise PermissionDenied
    list(get_user_model().objects.select_for_update().filter(pk__in=[principal.pk, delegate.pk]).order_by("pk"))
    if not principal.is_active or not delegate.is_active or principal == delegate or valid_until <= valid_from:
        raise ValidationError("Délégation invalide.")
    overlaps = Delegation.objects.filter(valid_from__lt=valid_until, valid_until__gt=valid_from)
    if overlaps.filter(Q(principal=principal) | Q(delegate=principal) | Q(principal=delegate)).exists():
        raise ValidationError("Délégation chevauchante ou en chaîne non prise en charge. Définissez une période distincte.")
    result = Delegation.objects.create(principal=principal, delegate=delegate, valid_from=valid_from, valid_until=valid_until)
    _config_audit(actor, result, "delegation.created")
    return result
