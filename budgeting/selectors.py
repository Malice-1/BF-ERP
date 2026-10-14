from .models import Budget
from django.db.models import Q
from django.utils import timezone
from .models import CostCenterManagerAssignment


def active_cost_center_manager(cost_center, at=None):
    at = at or timezone.now()
    return CostCenterManagerAssignment.objects.filter(cost_center=cost_center,
        user__is_active=True, valid_from__lte=at).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gt=at)).select_related("user").first()


def get_active_budget():
    """
    Retourne le budget actuellement actif.
    """
    return Budget.objects.get(is_active=True)


def find_budget_line(budget_product, cost_center, funding):
    budget = get_active_budget()

    return budget.lines.get(
        budget_product=budget_product,
        cost_center=cost_center,
        funding=funding,
    )
