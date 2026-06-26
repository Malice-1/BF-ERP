from .models import Budget
from django.db import transaction
from .selectors import find_budget_line
from .exceptions import BudgetInsufficientError

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



