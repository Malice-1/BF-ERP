"""Purchase facts and reference validation for the shared predicate engine."""
from decimal import Decimal
from django.apps import apps
from django.core.exceptions import ValidationError
from workflow.rules import schema, validate, normalize, OPERATORS


def facts_for_line(line, lines=None):
    lines = list(lines) if lines is not None else list(line.purchase_request.lines.all())
    return {
        "line.htva": line.total_htva, "line.tvac": line.total_tvac if line.vat_rate is not None else None,
        "line.quantity": line.quantity, "line.cdf": line.cost_center_id,
        "line.funding": line.funding_id, "line.product": line.detailed_product.budget_product_id,
        "request.support": line.purchase_request.support_id,
        "request.htva": sum((item.total_htva for item in lines), Decimal(0)),
        "request.tvac": sum((item.total_tvac for item in lines), Decimal(0)) if all(item.vat_rate is not None for item in lines) else None,
    }


def validate_references(operation, expression):
    validate(operation, expression)
    if "all" in expression or "any" in expression:
        for child in next(iter(expression.values())):
            validate_references(operation, child)
    else:
        field = schema(operation)[expression["field"]]
        if field.model and not apps.get_model(field.model).objects.filter(pk=normalize(field, expression["value"])).exists():
            raise ValidationError(f"La référence choisie pour « {field.label} » n’existe plus.")


def describe(operation, expression):
    if not expression:
        return "Critères historiques"
    if "all" in expression or "any" in expression:
        key = "all" if "all" in expression else "any"
        if not expression[key]:
            return "Toujours (toutes les lignes)"
        return (" ET " if key == "all" else " OU ").join("(" + describe(operation, child) + ")" for child in expression[key])
    field = schema(operation)[expression["field"]]
    value = expression["value"]
    if field.model:
        obj = apps.get_model(field.model).objects.filter(pk=value).first()
        value = str(obj) if obj else "Référence supprimée"
    return f"{field.label} {OPERATORS[expression['op']]} {value}"


def legacy_conditions(rule):
    children = [{"field": "request.htva", "op": "gte", "value": str(rule.minimum_htva)}]
    if rule.maximum_htva is not None:
        children.append({"field": "request.htva", "op": "lt", "value": str(rule.maximum_htva)})
    for field, value in (("line.cdf", rule.cost_center_id), ("line.funding", rule.funding_id), ("line.product", rule.budget_product_id)):
        if value:
            children.append({"field": field, "op": "eq", "value": str(value)})
    return {"all": children}
