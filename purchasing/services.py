from django.db import transaction

from budgeting.services import commit_budget
from budgeting.validators import validate_budget_availability
from budgeting.exceptions import BudgetValidationError, BudgetInsufficientError


@transaction.atomic
def approve_purchase_request(purchase_request):

    errors = []

     # Phase 1 : validation complète
    for line in purchase_request.lines.all():
        try:
            validate_budget_availability(line)

        except BudgetInsufficientError as error:
            errors.append({
                "line": line,
                "error": str(error),
            })

    if errors:
        raise BudgetValidationError(errors)

    # Phase 2 : engagement
    for line in purchase_request.lines.all():
        commit_budget(line)

    return purchase_request
