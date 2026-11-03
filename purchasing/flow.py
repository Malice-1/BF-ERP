"""Transactional purchase lifecycle. Lock order: request, annual envelope, steps."""
from collections import defaultdict
from decimal import Decimal, localcontext
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from accounts.services import eligible_authorization
from accounts.models import Role
from workflow.models import ConfigurationAuditEvent
from .models import (PurchaseRequest, AnnualEnvelope, EnvelopeVersion, Allocation,
    WorkflowVersion, ApprovalStep, Submission, LineSnapshot, BudgetEntry, PurchaseOrder,
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
        entity = step.snapshot.cost_center if step.manager_source == "cdf" else step.snapshot.funding
        return user if entity.managers.filter(pk=user.pk).exists() else None
    if step.role_id:
        return step.role if user.roles.filter(pk=step.role_id).exists() else None
    return eligible_authorization(user=user, function=step.function, context=context(step.snapshot))


def _record_grant(step, auth):
    grant, represented = auth
    step.authorization = grant if not isinstance(grant, (Role, get_user_model())) else None
    step.evaluated_scope = {**context(step.snapshot), "represented_user": represented.pk}
    if step.manager_source:
        step.evaluated_scope["manager_source"] = step.manager_source
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
        | Q(manager_source="support", snapshot__funding__managers__pk__in=principals)
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
    """Sequential levels; parallel steps; real manual evidence only."""
    for snapshot in submission.lines.all():
        steps = list(snapshot.steps.select_related("function", "snapshot__submission__purchase_request").order_by("level", "pk"))
        for level in sorted({s.level for s in steps}):
            current = [s for s in steps if s.level == level]
            if any(s.state != "approved" for s in steps if s.level < level):
                break
            for step in current:
                if step.state == "approved":
                    continue
                old = step.state
                previous_candidates = set(step.candidates.values_list("pk", flat=True))
                if step.manager_source:
                    entity = snapshot.cost_center if step.manager_source == "cdf" else snapshot.funding
                    step.candidates.set(entity.managers.filter(is_active=True))
                    PurchaseNotice.objects.filter(step=step, active=True, recipient_id__in=previous_candidates).exclude(
                        recipient_id__in=step.candidates.values_list("pk", flat=True)).update(active=False)
                candidates = list(step.candidates.filter(is_active=True))
                eligible = [u for u in candidates if _step_grant(u, step)]
                step.state = "pending" if eligible else ("blocked" if step.candidates.exists() else "unassigned")
                if step.waiting_since is None:
                    step.waiting_since = timezone.now()
                for proof in snapshot.steps.filter(state="approved", evidence__isnull=True).select_related("approved_by"):
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
            if any(s.state != "approved" for s in current):
                break


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


@transaction.atomic
def activate_workflow(*, actor, version_id):
    require(actor, "purchasing.change_workflowversion")
    # Activation locks all configuration rows in stable order, including drafts.
    list(WorkflowVersion.objects.select_for_update().order_by("pk"))
    version = WorkflowVersion.objects.select_for_update().get(pk=version_id)
    if version.published_at:
        raise ValidationError("Cette version a déjà été publiée. Créez une nouvelle version.")
    rules = list(version.rules.select_related("function"))
    if not rules:
        raise ValidationError("Ajoutez au moins une règle.")
    for rule in rules:
        if rule.level < 1 or rule.minimum_htva < 0 or (rule.maximum_htva is not None and rule.maximum_htva <= rule.minimum_htva):
            raise ValidationError("Niveau ou intervalle HTVA invalide (maximum exclusif).")
        if sum((bool(rule.named_user_id), bool(rule.cdf_manager), bool(rule.support_manager), bool(rule.role_id))) > 1:
            raise ValidationError("Choisissez un seul mode : utilisateur nommé, responsables CDF, responsables du support ou rôle valideur.")
        if rule.named_user_id and not rule.named_user.is_active:
            raise ValidationError("Le valideur nommé doit être actif.")
    for first in rules:
        for second in rules:
            if first.level < second.level and first.function.position > second.function.position:
                raise ValidationError("Les niveaux doivent respecter l'ordre global des fonctions.")
            if first.pk >= second.pk or first.mode != "exclusive" or second.mode != "exclusive" or first.priority != second.priority:
                continue
            scopes_overlap = all(getattr(first, k) is None or getattr(second, k) is None or getattr(first, k) == getattr(second, k) for k in ("cost_center_id", "funding_id", "budget_product_id"))
            if scopes_overlap and (first.maximum_htva is None or second.minimum_htva < first.maximum_htva) and (second.maximum_htva is None or first.minimum_htva < second.maximum_htva):
                raise ValidationError("Conflit de règles exclusives de même priorité.")
    WorkflowVersion.objects.filter(active=True).update(active=False)
    version.active, version.published_at = True, timezone.now()
    version.save(update_fields=["active", "published_at"])
    _config_audit(actor, version, "workflow.activated")
    return version


def available(version, cost_center_id, funding_id, budget_product_id):
    allocation = version.allocations.filter(cost_center_id=cost_center_id, funding_id=funding_id,
        budget_product_id=budget_product_id).first()
    entries = BudgetEntry.objects.filter(state__in=["reserved", "committed"],
        snapshot__submission__budget_version__envelope_id=version.envelope_id,
        snapshot__cost_center_id=cost_center_id, snapshot__funding_id=funding_id,
        snapshot__budget_product_id=budget_product_id)
    return (allocation.amount if allocation else Decimal(0)) - sum((e.amount for e in entries), Decimal(0))


@transaction.atomic
def activate_envelope(*, actor, version_id):
    require(actor, "budgeting.change_envelopeversion")
    initial = EnvelopeVersion.objects.get(pk=version_id)
    envelope = AnnualEnvelope.objects.select_for_update().get(pk=initial.envelope_id)
    version = EnvelopeVersion.objects.select_for_update().get(pk=version_id)
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


def _matching_rules(workflow, line, total):
    rules = [r for r in workflow.rules.select_related("function", "named_user")
        if not r.named_user_reference.startswith("[référence supprimée:")
        and r.minimum_htva <= total and (r.maximum_htva is None or total < r.maximum_htva)
        and (r.cost_center_id is None or r.cost_center_id == line.cost_center_id)
        and (r.funding_id is None or r.funding_id == line.funding_id)
        and (r.budget_product_id is None or r.budget_product_id == line.detailed_product.budget_product_id)]
    exclusive = [r for r in rules if r.mode == "exclusive"]
    if exclusive:
        winners = [r for r in exclusive if r.priority == max(x.priority for x in exclusive)]
        if len(winners) != 1:
            raise PurchaseRequestError("Conflit de règles exclusives : aucune réservation effectuée.")
        rules = [r for r in rules if r.mode == "cumulative"] + winners
    if not rules:
        raise PurchaseRequestError(f"Aucune règle applicable à la ligne {line.pk}.")
    return rules


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
        workflow = WorkflowVersion.objects.filter(active=True).first()
        if not workflow:
            raise PurchaseRequestError("Aucune configuration de validation active.")
        total = sum((line.total_htva for line in lines), Decimal(0))
        planned = [(line, _matching_rules(workflow, line, total)) for line in lines]
        envelope = AnnualEnvelope.objects.select_for_update().filter(year=timezone.localdate().year).first()
        if not envelope or not envelope.active_version_id:
            raise PurchaseRequestError("Aucune version budgétaire active pour l'année courante.")
        version = envelope.active_version
        totals = defaultdict(Decimal)
        for line in lines:
            totals[(line.cost_center_id, line.funding_id, line.detailed_product.budget_product_id)] += line.total_tvac
        for combination, amount in totals.items():
            balance = available(version, *combination)
            if balance < amount or balance < 0:
                raise PurchaseRequestError(f"Budget insuffisant : disponible {balance} EUR, nécessaire {amount} EUR. Aucune réservation effectuée.")
        submission = Submission.objects.create(purchase_request=purchase, workflow=workflow, budget_version=version,
            supplier_data={"name": purchase.supplier.name, "code": purchase.supplier.code, "vat_number": purchase.supplier.vat_number})
        now = timezone.now()
        for line, rules in planned:
            data = {key: str(getattr(line, key)) for key in ("description", "quantity", "unit_price", "vat_rate", "total_htva", "total_vat", "total_tvac")}
            data.update(product=str(line.detailed_product), cost_center=str(line.cost_center), funding=str(line.funding))
            snapshot = LineSnapshot.objects.create(submission=submission, line=line, original_line_id=line.pk, data=data,
                amount=line.total_tvac, cost_center=line.cost_center, funding=line.funding,
                budget_product=line.detailed_product.budget_product)
            BudgetEntry.objects.create(snapshot=snapshot, amount=line.total_tvac)
            for rule in rules:
                step = ApprovalStep.objects.create(snapshot=snapshot, function=rule.function,
                    function_label=rule.function.label, level=rule.level, role=rule.role,
                    manager_source="cdf" if rule.cdf_manager else ("support" if rule.support_manager else ""))
                if rule.role_id:
                    users = get_user_model().objects.filter(is_active=True, roles=rule.role)
                elif rule.named_user_id or rule.named_user_reference:
                    users = [rule.named_user] if rule.named_user_id else []
                elif rule.cdf_manager or rule.support_manager:
                    entity = line.cost_center if rule.cdf_manager else line.funding
                    users = entity.managers.filter(is_active=True)
                else:
                    users = get_user_model().objects.filter(is_active=True, authorizations__function=rule.function).distinct()
                step.candidates.set([u for u in users if _step_grant(u, step)])
        purchase.status = "SUBMITTED"
        _audit(purchase, actor, "request.submitted", {"submission": submission.pk})
        _advance(submission)
        return purchase


def _finish(purchase, submission):
    if not submission.lines.exists() or submission.lines.filter(steps__isnull=True).exists():
        return
    if submission.lines.filter(steps__state__in=["future", "pending", "blocked", "unassigned"]).exists():
        return
    PurchaseOrder.objects.get_or_create(purchase_request=purchase, defaults=dict(submission=submission,
        supplier_data=submission.supplier_data))
    BudgetEntry.objects.filter(snapshot__submission=submission, state="reserved").update(state="committed")
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
    step = ApprovalStep.objects.select_for_update().select_related("snapshot", "function").get(pk=step_id, snapshot__submission=submission)
    auth = authority(actor, step)
    if step.state != "pending" or not auth:
        raise PermissionDenied("Étape inaccessible ou habilitation absente.")
    if decision not in ("approve", "correct", "reject"):
        raise ValidationError("Décision inconnue.")
    if decision != "approve" and not reason.strip():
        raise ValidationError("Un motif est obligatoire.")
    if decision == "approve":
        step.state, step.approved_by, step.approved_at = "approved", actor, timezone.now()
        _record_grant(step, auth)
        step.save()
        PurchaseNotice.objects.filter(step=step, active=True).update(active=False)
        _advance(submission)
        _finish(purchase, submission)
    else:
        _stop(submission)
        purchase.status = "CORRECTION" if decision == "correct" else "REJECTED"
    _audit(purchase, actor, "request." + decision, {"step": step.pk, "reason": reason,
        "authorization": None if isinstance(auth[0], Role) else auth[0].pk,
        "role": auth[0].pk if isinstance(auth[0], Role) else None, "represented_user": auth[1].pk})
    return purchase


def _stop(submission):
    BudgetEntry.objects.filter(snapshot__submission=submission, state="reserved").update(state="released")
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
    step = ApprovalStep.objects.select_for_update().select_related("snapshot", "function").get(
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
        _finish(purchase, submission)
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
