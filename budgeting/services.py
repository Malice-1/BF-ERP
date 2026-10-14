from .models import Budget
from django.db import transaction
from .selectors import find_budget_line
from .exceptions import BudgetInsufficientError
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from .models import CostCenter, CostCenterManagerAssignment
from workflow.models import ConfigurationAuditEvent


@transaction.atomic
def assign_cost_center_manager(*, actor, cost_center, user, valid_from, valid_until=None):
    if not actor.is_active or not actor.has_perm("budgeting.manage_cost_center_managers"):
        raise PermissionDenied
    CostCenter.objects.select_for_update().get(pk=cost_center.pk)
    if not user.is_active:
        raise ValidationError("Le responsable doit être actif.")
    assignment = CostCenterManagerAssignment(cost_center=cost_center, user=user,
        valid_from=valid_from, valid_until=valid_until)
    assignment.full_clean()
    overlaps = CostCenterManagerAssignment.objects.filter(cost_center=cost_center).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=valid_from))
    if valid_until is not None:
        overlaps = overlaps.filter(valid_from__lt=valid_until)
    if overlaps.exists():
        raise ValidationError("Cette période chevauche une affectation existante.")
    assignment.save()
    ConfigurationAuditEvent.objects.create(actor=actor, action="manager.assigned",
        object_type="cost_center", object_id=cost_center.pk,
        payload={"assignment_id": assignment.pk, "user_id": user.pk})
    return assignment


@transaction.atomic
def end_cost_center_manager_assignment(*, actor, assignment_id, valid_until):
    if not actor.is_active or not actor.has_perm("budgeting.manage_cost_center_managers"):
        raise PermissionDenied
    original = CostCenterManagerAssignment.objects.get(pk=assignment_id)
    CostCenter.objects.select_for_update().get(pk=original.cost_center_id)
    assignment = CostCenterManagerAssignment.objects.select_for_update().get(pk=assignment_id)
    if assignment.valid_until is not None:
        raise ValidationError("Cette affectation est déjà clôturée.")
    assignment.valid_until = valid_until
    assignment.full_clean()
    assignment.save(update_fields=["valid_until"])
    ConfigurationAuditEvent.objects.create(actor=actor, action="manager.ended",
        object_type="cost_center", object_id=assignment.cost_center_id,
        payload={"assignment_id": assignment.pk, "valid_until": valid_until.isoformat()})
    return assignment

def activate_budget(budget):
    """
    Active un budget et désactive tous les autres.
    """
    Budget.objects.filter(is_active=True).exclude(
        pk=budget.pk
    ).update(is_active=False)

    budget.is_active = True
    budget.save(update_fields=["is_active"])


@transaction.atomic
def commit_budget(purchase_request_line):

    budget_line = find_budget_line(
        budget_product=(
            purchase_request_line
            .detailed_product
            .budget_product
        ),
        cost_center=purchase_request_line.cost_center,
        funding=purchase_request_line.funding,
    )

    if budget_line.available_amount < purchase_request_line.total_amount:
        raise BudgetInsufficientError(
            "Budget insuffisant pour cette demande."
        )

    budget_line.committed_amount += (
        purchase_request_line.total_amount
    )

    return budget_line



