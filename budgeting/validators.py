from .selectors import find_budget_line
from .exceptions import BudgetInsufficientError


def validate_budget_availability(purchase_request_line):
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
            f"Budget insuffisant pour la ligne {purchase_request_line}"
        )

    return True
