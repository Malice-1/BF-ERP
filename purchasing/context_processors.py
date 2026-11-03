from .budget_views import MANAGER_PERMISSIONS, can_access_budget
from .flow import pending_validation_count
from .navigation_permissions import can_access_purchases, can_access_configuration


def navigation(request):
    name = request.resolver_match.url_name if request.resolver_match else ""
    if name in {"inbox", "delegations", "my_validations", "my_delegations", "decision"}:
        section = "personal"
    elif name in {"budget_home", "budget_versions", "allocation_versions", "budget_version", "budget_products", "budgets"}:
        section = "budget"
    elif name in {"entity_managers", "session_settings", "configuration", "authorizations", "authorization_create", "authorization_edit", "managers", "manager_create", "manager_end"}:
        section = "configuration"
    else:
        section = "purchases"
    return {"nav_section": section,
            "pending_validation_count": pending_validation_count(request.user),
            "can_access_budget": can_access_budget(request.user),
            "can_access_purchases": can_access_purchases(request.user),
            "can_manage_budgets": request.user.has_perms(MANAGER_PERMISSIONS),
            "can_configure": can_access_configuration(request.user)}
