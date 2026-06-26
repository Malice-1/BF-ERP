from .models import Budget


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
