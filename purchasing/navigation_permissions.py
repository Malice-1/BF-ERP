"""Shared visibility and entry-point checks for application sections."""


def has_category_permission(user, *categories):
    if not user.is_authenticated or not user.is_active:
        return False
    prefixes = tuple(f"{category}." for category in categories)
    return any(permission.startswith(prefixes) for permission in user.get_all_permissions())


def can_access_purchases(user):
    return has_category_permission(user, "purchasing")


def can_access_budget(user):
    return has_category_permission(user, "budgeting")


def can_access_configuration(user):
    if has_category_permission(user, "accounts", "auth", "workflow", "suppliers"):
        return True
    if not user.is_authenticated or not user.is_active:
        return False
    return any(
        permission == "budgeting.manage_cost_center_managers"
        or (permission.startswith("purchasing.") and permission.endswith(("_workflowversion", "_approvalrule")))
        for permission in user.get_all_permissions()
    )
