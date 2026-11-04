"""Typed, side-effect-free validation predicates shared by operation adapters.

An adapter registers its fields and supplies facts; evaluation never accesses
business models or executes user-provided code. Future transfers supply a
separate field registry and facts without changing this evaluator.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class Field:
    label: str
    kind: str = "number"
    model: str = ""


OPERATIONS = {}
OPERATORS = {"eq": "est égal à", "ne": "est différent de", "gte": "est supérieur ou égal à",
             "gt": "est supérieur à", "lte": "est inférieur ou égal à", "lt": "est inférieur à"}


def register_operation(name, label, fields):
    OPERATIONS[name] = {"label": label, "fields": dict(fields)}


def schema(operation):
    if operation not in OPERATIONS:
        raise ValidationError("Ce type d’opération n’est pas encore pris en charge.")
    return OPERATIONS[operation]["fields"]


def normalize(field, value):
    try:
        if isinstance(value, (bool, dict, list)) or value is None:
            raise ValueError
        if field.kind == "number":
            result = Decimal(str(value).replace(",", "."))
            if not result.is_finite() or result < 0 or result.adjusted() > 27 or result.as_tuple().exponent < -10:
                raise ValueError
            return result
        result = int(str(value))
        if result < 1:
            raise ValueError
        return result
    except (ValueError, InvalidOperation, OverflowError):
        raise ValidationError(f"Valeur invalide pour « {field.label} ».")


def validate(operation, expression, depth=0):
    fields = schema(operation)
    if depth > 5 or not isinstance(expression, dict):
        raise ValidationError("Conditions invalides ou trop imbriquées.")
    if set(expression) in ({"all"}, {"any"}):
        children = next(iter(expression.values()))
        if not isinstance(children, list) or len(children) > 50:
            raise ValidationError("Une règle accepte au maximum 50 conditions par groupe.")
        if "any" in expression and not children:
            raise ValidationError("Ajoutez au moins une condition pour le mode OU.")
        for child in children:
            validate(operation, child, depth + 1)
        return
    if set(expression) != {"field", "op", "value"} or not isinstance(expression.get("field"), str) or expression["field"] not in fields:
        raise ValidationError("Champ de condition inconnu.")
    field = fields[expression["field"]]
    if not isinstance(expression["op"], str) or expression["op"] not in OPERATORS or (field.kind != "number" and expression["op"] not in {"eq", "ne"}):
        raise ValidationError("Comparaison incompatible avec ce champ.")
    normalize(field, expression["value"])


def matches(operation, expression, facts):
    validate(operation, expression)
    def evaluate(node):
        if "all" in node:
            return all(evaluate(child) for child in node["all"])
        if "any" in node:
            return any(evaluate(child) for child in node["any"])
        actual = facts.get(node["field"])
        # A missing fact never grants a validation, including for "different".
        if actual is None:
            return False
        field = schema(operation)[node["field"]]
        left, right = normalize(field, actual), normalize(field, node["value"])
        return {"eq": lambda: left == right, "ne": lambda: left != right,
                "gte": lambda: left >= right, "gt": lambda: left > right,
                "lte": lambda: left <= right, "lt": lambda: left < right}[node["op"]]()
    return evaluate(expression)


register_operation("purchase", "Demande d’achat", {
    "line.htva": Field("Montant de la ligne HTVA"),
    "line.tvac": Field("Montant de la ligne TVAC"),
    "line.quantity": Field("Quantité de la ligne"),
    "request.htva": Field("Montant total de la DA HTVA"),
    "request.tvac": Field("Montant total de la DA TVAC"),
    "line.cdf": Field("CDF de la ligne", "reference", "budgeting.CostCenter"),
    "line.funding": Field("Financement de la ligne", "reference", "budgeting.Funding"),
    "line.product": Field("Produit budgétaire de la ligne", "reference", "budgeting.BudgetProduct"),
    "request.support": Field("Support choisi sur la DA", "reference", "budgeting.Support"),
})
