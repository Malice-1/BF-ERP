from .budget_views import MANAGER_PERMISSIONS, can_access_budget
from .flow import pending_validation_count
from .navigation_permissions import can_access_purchases, can_access_configuration


def navigation(request):
    name = request.resolver_match.url_name if request.resolver_match else ""
    if request.resolver_match and request.resolver_match.namespace == "accounting":
        section = "accounting"
    elif request.resolver_match and request.resolver_match.namespace == "sales":
        section = "sales"
    elif request.resolver_match and request.resolver_match.namespace == "hr":
        section = "hr"
    elif name in {"inbox", "delegations", "my_validations", "my_delegations", "decision"}:
        section = "personal"
    elif name in {"allocation_import", "transfer_correct", "version_transfers", "transfer_timeline", "transfer_monitor", "budget_history", "budget_version_history", "transfer_list", "transfer_detail", "budget_home", "budget_versions", "allocation_versions", "budget_version", "budget_products", "budgets"}:
        section = "budget"
    elif name in {"stock", "stock_movements", "stock_balances", "warehouses", "warehouse_edit", "purchase_receipts", "purchase_receive"}:
        section = "stock"
    elif name in {"validation_schemes", "rule_sets", "rule_set", "rule_add", "rule_edit", "rule_delete", "entity_managers", "session_settings", "configuration", "authorizations", "authorization_create", "authorization_edit", "managers", "manager_create", "manager_end"}:
        section = "configuration"
    else:
        section = "purchases"
    from budgeting.models import BudgetTransfer, TransferStep
    from budgeting.transfers import refresh, is_assigned_validator
    transfer_count = 0
    if request.user.is_authenticated and request.user.is_active:
        for pk in BudgetTransfer.objects.filter(status="pending").values_list("pk", flat=True):
            refresh(pk)
        transfer_count = sum(is_assigned_validator(request.user, step) for step in TransferStep.objects.filter(transfer__status="pending", state="pending").select_related("transfer"))
        transfer_count += BudgetTransfer.objects.filter(status="returned", created_by=request.user).count()
    from budgeting.transfer_views import can_view_version_transfers, visible_transfers
    can_access_transfers = request.user.is_authenticated and (can_view_version_transfers(request.user) or request.user.has_perm("budgeting.add_budgettransfer") or request.user.managed_cost_centers.exists() or visible_transfers(request.user).exists())
    from .navigation_permissions import has_category_permission
    return {"nav_section": section, "can_access_transfers": can_access_transfers,
            "can_access_sales": has_category_permission(request.user, "sales"),
            "can_access_accounting": has_category_permission(request.user, "accounting"),
            "can_access_stock": any(request.user.has_perm("receiving." + permission) for permission in (
                "view_warehouse", "add_warehouse", "change_warehouse", "view_stockbalance", "manage_stock", "view_stockmovement")),
            "can_view_stock_movements": any(request.user.has_perm("receiving." + permission) for permission in (
                "view_stockbalance", "manage_stock", "view_stockmovement")),
            "can_view_stock": request.user.has_perm("receiving.view_stockbalance") or request.user.has_perm("receiving.manage_stock"),
            "can_access_warehouses": any(request.user.has_perm("receiving." + permission) for permission in (
                "view_warehouse", "add_warehouse", "change_warehouse", "view_stockbalance", "manage_stock")),
            "pending_validation_count": pending_validation_count(request.user) + transfer_count,
            "can_access_budget": can_access_budget(request.user),
            "can_access_purchases": can_access_purchases(request.user),
            "can_manage_budgets": request.user.has_perms(MANAGER_PERMISSIONS),
            "can_configure": can_access_configuration(request.user)}
