from decimal import Decimal, localcontext
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.http import Http404
from .models import WorkflowVersion, ApprovalRule, PurchaseRequest, LineSnapshot
from .rule_forms import RuleSetForm, RuleForm, ConditionFormSet, condition_catalog
from .rule_adapter import describe, legacy_conditions, validate_references, facts_for_line
from . import flow
from .exceptions import PurchaseRequestError


def require_config(user, action="view"):
    if not user.is_active or not any(user.has_perm(f"purchasing.{name}_workflowversion")
                                    for name in ({"view", "change", "add"} if action == "view" else {action})):
        raise PermissionDenied


def summary(rule):
    return {"rule": rule, "condition": describe(rule.version.operation, rule.conditions) if rule.version.rule_based else describe("purchase", legacy_conditions(rule)),
            "target": "Responsables CDF" if rule.cdf_manager else "Responsables du support" if rule.support_manager else str(rule.role) if rule.role_id else str(rule.named_user) if rule.named_user_id else str(rule.function)}


@login_required
@require_http_methods(["GET", "POST"])
def rule_sets(request):
    require_config(request.user)
    form = RuleSetForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        require_config(request.user, "add")
        if form.is_valid():
            version = form.save(commit=False)
            version.rule_based = True
            version.operation = "purchase"
            version.save()
            return redirect("purchasing:rule_set", pk=version.pk)
    return render(request, "purchasing/rule_sets.html", {"form": form,
        "versions": WorkflowVersion.objects.filter(operation="purchase").order_by("-pk")})


@login_required
@require_http_methods(["GET", "POST"])
def rule_set(request, pk):
    require_config(request.user)
    version = get_object_or_404(WorkflowVersion, pk=pk, operation="purchase")
    if request.method == "POST":
        action = request.POST.get("action")
        require_config(request.user, "change" if action == "publish" else "add")
        try:
            with transaction.atomic():
                version = WorkflowVersion.objects.select_for_update().get(pk=pk)
                if action == "publish":
                    flow.activate_workflow(actor=request.user, version_id=pk)
                    messages.success(request, "Version publiée et activée pour les nouvelles soumissions.")
                elif action == "copy":
                    if not request.user.has_perm("purchasing.add_approvalrule"):
                        raise PermissionDenied
                    if version.rules.filter(mode="exclusive").exists():
                        raise ValidationError("Ce circuit contient des règles exclusives : sa conversion automatique serait ambiguë. Créez une nouvelle version de règles cumulatives.")
                    target = WorkflowVersion.objects.create(label=version.label[:90] + " (copie)", operation=version.operation, rule_based=True)
                    for source in version.rules.all():
                        data = {field.attname: getattr(source, field.attname) for field in ApprovalRule._meta.fields
                                if not field.primary_key and field.name != "version"}
                        data["conditions"] = source.conditions if version.rule_based else legacy_conditions(source)
                        data["mode"] = "cumulative"
                        ApprovalRule.objects.create(version=target, **data)
                    return redirect("purchasing:rule_set", pk=target.pk)
                else:
                    raise ValidationError("Action inconnue.")
        except ValidationError as error:
            messages.error(request, " · ".join(error.messages))
        return redirect("purchasing:rule_set", pk=pk)
    purchases = PurchaseRequest.objects.all() if request.user.has_perm("purchasing.view_all_purchase_requests") else PurchaseRequest.objects.filter(created_by=request.user)
    return render(request, "purchasing/rule_set.html", {"version": version, "purchases": purchases.order_by("-pk")[:100],
        "rules": [summary(rule) for rule in version.rules.select_related("version", "role", "named_user", "function")],
        "can_add_rule": request.user.has_perms(["purchasing.change_workflowversion", "purchasing.add_approvalrule"]),
        "can_edit_rule": request.user.has_perms(["purchasing.change_workflowversion", "purchasing.change_approvalrule"]),
        "can_delete_rule": request.user.has_perms(["purchasing.change_workflowversion", "purchasing.delete_approvalrule"])})


@login_required
@require_http_methods(["GET", "POST"])
def rule_edit(request, pk, rule_id=None):
    require_config(request.user, "change")
    permission = "change" if rule_id else "add"
    if not request.user.has_perm(f"purchasing.{permission}_approvalrule"):
        raise PermissionDenied
    version = get_object_or_404(WorkflowVersion, pk=pk, rule_based=True, operation="purchase")
    with transaction.atomic():
        version = WorkflowVersion.objects.select_for_update().get(pk=pk)
        if version.published_at:
            raise PermissionDenied("Copiez la version publiée en brouillon avant de la modifier.")
        rule = get_object_or_404(ApprovalRule, pk=rule_id, version=version) if rule_id else ApprovalRule(version=version)
        # UI edits flat groups; preserve imported nested expressions without flattening.
        children = next(iter(rule.conditions.values()), []) if rule.conditions else []
        if any("field" not in child for child in children):
            raise PermissionDenied("Cette règle imbriquée doit être conservée ou remplacée dans une nouvelle version.")
        form = RuleForm(request.POST if request.method == "POST" else None, instance=rule)
        conditions = ConditionFormSet(request.POST if request.method == "POST" else None,
            initial=children, prefix="conditions", form_kwargs={"operation": version.operation})
        if request.method == "POST":
            valid_form, valid_conditions = form.is_valid(), conditions.is_valid()
            if valid_form and valid_conditions:
                nodes = [{"field": row.cleaned_data["field"], "op": row.cleaned_data["op"], "value": str(row.cleaned_data["value"])}
                         for row in conditions if row.cleaned_data and not row.cleaned_data.get("DELETE")]
                if not nodes and not form.cleaned_data["unconditional"]:
                    form.add_error(None, "Ajoutez une condition ou cochez explicitement « Toujours appliquer ».")
                elif nodes and form.cleaned_data["unconditional"]:
                    form.add_error("unconditional", "Retirez les conditions ou décochez cette option.")
                else:
                    expression = {form.cleaned_data["junction"]: nodes} if nodes else {"all": []}
                    try:
                        validate_references(version.operation, expression)
                        rule = form.save(commit=False)
                        rule.conditions = expression
                        rule.save()
                        return redirect("purchasing:rule_set", pk=pk)
                    except ValidationError as error:
                        form.add_error(None, error)
    return render(request, "purchasing/rule_edit.html", {"form": form, "conditions": conditions,
        "version": version, "catalog": condition_catalog(version.operation)})


@login_required
@require_http_methods(["POST"])
def rule_delete(request, pk, rule_id):
    require_config(request.user, "change")
    if not request.user.has_perm("purchasing.delete_approvalrule"):
        raise PermissionDenied
    with transaction.atomic():
        version = get_object_or_404(WorkflowVersion.objects.select_for_update(), pk=pk, rule_based=True)
        if version.published_at:
            raise PermissionDenied
        get_object_or_404(ApprovalRule, pk=rule_id, version=version).delete()
    return redirect("purchasing:rule_set", pk=pk)


@login_required
@require_http_methods(["GET"])
def simulate(request, pk):
    purchase = get_object_or_404(PurchaseRequest, pk=pk)
    if purchase.created_by_id != request.user.pk and not (
            request.user.has_perm("purchasing.view_all_purchase_requests")
            or request.user.has_perm("purchasing.view_purchase_financial")):
        raise PermissionDenied
    version = WorkflowVersion.objects.filter(active=True, operation="purchase").first()
    if request.GET.get("version"):
        require_config(request.user)
        try:
            version_id = int(request.GET["version"])
        except (ValueError, TypeError):
            raise Http404
        version = get_object_or_404(WorkflowVersion, pk=version_id, operation="purchase")
    lines = list(purchase.lines.select_related("detailed_product__budget_product", "cost_center", "funding", "purchase_request"))
    rows, warnings = [], []
    if not version:
        warnings.append("Aucune version de règles active.")
    if not lines:
        warnings.append("La demande ne contient aucune ligne.")
    with localcontext() as precision:
        precision.prec = 50
        total = sum((line.total_htva for line in lines), Decimal(0))
        for line in lines:
            try:
                rules = flow._matching_rules(version, line, total, facts_for_line(line, lines)) if version else []
            except (PurchaseRequestError, ValidationError) as error:
                warnings.append(f"Ligne {line.pk} : {error}")
                rules = []
            for rule in rules:
                snapshot = LineSnapshot(cost_center=line.cost_center, funding=line.funding,
                    budget_product=line.detailed_product.budget_product, support=purchase.support)
                candidates = flow.initial_candidates(rule, snapshot, rule_based=version.rule_based)
                row = summary(rule)
                row.update(line=line, candidates=candidates)
                rows.append(row)
        if any(row["rule"].support_manager for row in rows) and (not purchase.support_id or not purchase.created_by_id or not purchase.created_by.supports.filter(pk=purchase.support_id).exists()):
            warnings.append("Le demandeur doit choisir un support auquel il appartient avant de soumettre.")
    if any(line.vat_rate is None for line in lines):
        warnings.append("TVA manquante : certains montants TVAC ne peuvent pas être évalués.")
    return render(request, "purchasing/rule_simulation.html", {"purchase": purchase, "version": version,
        "rows": rows, "warnings": warnings})
