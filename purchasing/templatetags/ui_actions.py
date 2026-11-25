"""Consistent, deterministic parent links for application pages."""
from django import template
from django.template.loader import render_to_string
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.html import format_html
from django.utils.numberformat import format as number_format

register = template.Library()


@register.filter
def amount(value):
    """Display up to two decimals, with dots for thousands and a decimal comma."""
    rounded = floatformat(value, "-2u")
    if not rounded:
        return ""
    return number_format(rounded, decimal_sep=",", grouping=3, thousand_sep=".", force_grouping=True)


@register.simple_tag(takes_context=True)
def back_action(context):
    request = context["request"]
    name = request.resolver_match.url_name
    purchase = context.get("purchase")
    order = context.get("order")
    if name in {"decision", "reassign"}:
        target, args, label = "my_validations", (), "Retour à mes validations"
    elif purchase and name in {"detail", "edit", "line_add", "line_edit", "line_delete", "submit", "cancel"}:
        if name == "detail":
            target, args, label = "purchasing:list", (), "Retour aux demandes d’achat"
        else:
            target, args, label = "purchasing:detail", (purchase.pk,), "Retour à la demande"
    elif name == "order" and order:
        target, args, label = "purchasing:detail", (order.purchase_request_id,), "Retour à la demande"
    elif name in {"budget_version_delete", "allocation_import"}:
        target, args, label = "purchasing:budget_version", (context["version"].pk,), "Retour à la version"
    elif (name == "budget_version_history" or name == "budget_history" and context.get("scoped_version")) and context.get("version"):
        from purchasing.budget_views import MANAGER_PERMISSIONS
        if request.user.has_perms(MANAGER_PERMISSIONS):
            target, args, label = "purchasing:budget_version", (context["version"].pk,), "Retour à la version"
        else:
            target, args, label = "purchasing:budget_history", (), "Retour à l’historique budgétaire"
    elif name in {"supplier_create", "supplier_edit"}:
        target, args, label = "purchasing:suppliers", (), "Retour aux fournisseurs"
    elif name in {"create", "all_requests", "detailed_products", "suppliers"}:
        target, args, label = "purchasing:list", (), "Retour aux demandes d’achat"
    elif name in {"budget_versions", "allocation_versions", "budget_products", "budgets", "budget_history",
                  "budget_transactions", "budget_pilot", "transfer_list", "transfer_monitor"}:
        target, args, label = "purchasing:budget_home", (), "Retour à l’espace Budget"
    elif name in {"transfer_correct", "transfer_detail", "transfer_timeline", "version_transfers"}:
        target, args, label = "transfer_monitor", (), "Retour aux transferts"
    elif name == "purchase_receive":
        target, args, label = "purchase_receipts", (), "Retour aux réceptions"
    elif name in {"stock_movements", "stock_balances", "warehouses", "warehouse_edit", "purchase_receipts"}:
        target, args, label = ("warehouses", (), "Retour aux dépôts") if name == "warehouse_edit" else ("stock", (), "Retour à l’espace Stocks")
    elif name in {"authorization_create", "authorization_edit"}:
        target, args, label = "authorizations", (), "Retour aux habilitations"
    elif name in {"validation_schemes", "entity_managers", "session_settings", "authorizations"}:
        target, args, label = "purchasing:configuration", (), "Retour à la configuration"
    else:
        return ""
    icon = render_to_string("purchasing/action_icon.html", {"icon": "exit"})
    return format_html('<div class="ui-back-row"><a class="ui-icon ui-back" href="{}" aria-label="{}" title="{}">{}</a></div>',
                       reverse(target, args=args), label, label, icon)
