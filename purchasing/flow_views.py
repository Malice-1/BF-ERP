from decimal import Decimal
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin
from . import flow
from .models import (PurchaseRequest, ApprovalStep, Submission, PurchaseOrder,
    AnnualEnvelope, WorkflowVersion, PurchaseNotice, Delegation)
from .forms import RevisionForm, BudgetCheckForm
from .flow_forms import DecisionForm, ReassignForm, DelegationForm
from .exceptions import PurchaseRequestError


def _refresh():
    for pk in Submission.objects.filter(active=True).values_list("pk", flat=True):
        flow.refresh_submission(pk)


def _operational_step(step, user):
    # Template gets an explicit safe dictionary; no financial model available.
    return dict(id=step.pk, request_id=step.snapshot.submission.purchase_request_id,
        number=step.snapshot.submission.purchase_request.number, line=step.snapshot.original_line_id,
        function=step.function_label, level=step.level, status=step.get_state_display(),
        candidates=", ".join(step.candidates.values_list("username", flat=True)) or "À affecter",
        waiting_since=step.waiting_since, state=step.state,
        actionable=step.state == "pending" and bool(flow.authority(user, step)),
        revision=step.snapshot.submission.purchase_request.revision)


@login_required
@require_http_methods(["GET"])
def inbox(request):
    _refresh()
    steps = ApprovalStep.objects.filter(snapshot__submission__active=True).select_related(
        "snapshot__submission__purchase_request", "function").prefetch_related("candidates")
    owned = [s for s in steps if flow.authority(request.user, s) or s.candidates.filter(pk=request.user.pk).exists()]
    notices = PurchaseNotice.objects.filter(recipient=request.user, active=True)
    return render(request, "purchasing/inbox.html", {"steps": [_operational_step(s, request.user) for s in owned], "notices": notices})


@login_required
@permission_required("purchasing.monitor_purchases", raise_exception=True)
@require_http_methods(["GET"])
def monitor(request):
    _refresh()
    steps = ApprovalStep.objects.filter(snapshot__submission__active=True).select_related(
        "snapshot__submission__purchase_request", "function").prefetch_related("candidates")
    state = request.GET.get("state", "")
    number = request.GET.get("number", "").strip()
    if state:
        steps = steps.filter(state=state)
    if number:
        steps = steps.filter(snapshot__submission__purchase_request__number__icontains=number)
    return render(request, "purchasing/monitor.html", {"steps": [_operational_step(s, request.user) for s in steps], "state": state, "number": number})


@login_required
@require_http_methods(["GET", "POST"])
def submit(request, pk):
    purchase = get_object_or_404(PurchaseRequest, pk=pk, created_by=request.user)
    if not request.user.has_perm("purchasing.add_purchaserequest"):
        raise PermissionDenied
    return _action(request, purchase, RevisionForm, flow.submit_purchase,
        "Soumettre la demande pour validation — réservation du budget TVAC")


@login_required
@require_http_methods(["GET", "POST"])
def decision(request, pk, step_id):
    step = get_object_or_404(ApprovalStep.objects.select_related("snapshot__submission__purchase_request", "function"),
        pk=step_id, snapshot__submission__purchase_request_id=pk, snapshot__submission__active=True)
    flow.refresh_submission(step.snapshot.submission_id)
    step.refresh_from_db()
    if not flow.authority(request.user, step):
        raise PermissionDenied
    purchase = step.snapshot.submission.purchase_request
    return _action(request, purchase, DecisionForm, flow.decide,
        f"Traiter {purchase.number} · ligne {step.snapshot.line_id} · {step.function_label}", {"step_id": step.pk})


@login_required
@permission_required("purchasing.reassign_approvals", raise_exception=True)
@require_http_methods(["GET", "POST"])
def reassign(request, pk, step_id):
    step = get_object_or_404(ApprovalStep, pk=step_id, snapshot__submission__purchase_request_id=pk,
        snapshot__submission__active=True)
    purchase = step.snapshot.submission.purchase_request
    return _action(request, purchase, ReassignForm, flow.reassign,
        "Réaffecter l’étape avec justification", {"step_id": step.pk})


def _action(request, purchase, form_type, command, title, extra=None):
    form = form_type(request.POST if request.method == "POST" else None, initial={"expected_revision": purchase.revision})
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            command(request_id=purchase.pk, actor=request.user, **form.cleaned_data, **(extra or {}))
            if request.user.pk == purchase.created_by_id or request.user.has_perm("purchasing.view_purchase_financial"):
                return redirect("purchasing:detail", pk=purchase.pk)
            return redirect("my_validations")
        except (ValidationError, PurchaseRequestError) as error:
            form.add_error(None, " · ".join(error.messages) if isinstance(error, ValidationError) else str(error))
            status = 409
    return render(request, "purchasing/form.html", {"form": form, "title": title}, status=status)


@login_required
@require_http_methods(["GET"])
def order_document(request, pk):
    order = get_object_or_404(PurchaseOrder.objects.select_related("purchase_request"), purchase_request_id=pk)
    if order.purchase_request.created_by_id != request.user.pk and not (
            request.user.has_perm("purchasing.view_purchase_financial")
            or request.user.has_perm("purchasing.view_all_purchase_requests")):
        raise Http404
    lines = list(order.submission.lines.all())
    return render(request, "purchasing/order.html", {"order": order, "lines": lines,
        "total": sum((line.amount for line in lines), Decimal(0))})


@login_required
@permission_required("budgeting.view_budget_balances", raise_exception=True)
@require_http_methods(["GET"])
def budgets(request):
    rows = []
    for envelope in AnnualEnvelope.objects.select_related("active_version").filter(active_version__isnull=False):
        version = envelope.active_version
        # Include combinations removed by a later budget version too.
        from .models import BudgetEntry
        combinations = set(version.allocations.values_list("cost_center_id", "funding_id", "budget_product_id"))
        combinations.update(BudgetEntry.objects.filter(snapshot__submission__budget_version__envelope=envelope,
            state__in=["reserved", "committed"]).values_list("snapshot__cost_center_id", "snapshot__funding_id", "snapshot__budget_product_id"))
        from budgeting.models import CostCenter, Funding, BudgetProduct
        for cdf, funding, product in sorted(combinations):
            allocation = version.allocations.filter(cost_center_id=cdf, funding_id=funding, budget_product_id=product).first()
            entries = BudgetEntry.objects.filter(snapshot__submission__budget_version__envelope=envelope,
                snapshot__cost_center_id=cdf, snapshot__funding_id=funding, snapshot__budget_product_id=product)
            rows.append(dict(year=envelope.year, version=version.label, cdf=CostCenter.objects.get(pk=cdf),
                funding=Funding.objects.get(pk=funding), product=BudgetProduct.objects.get(pk=product),
                allocated=allocation.amount if allocation else 0,
                reserved=sum((e.amount for e in entries if e.state == "reserved"), Decimal(0)),
                committed=sum((e.amount for e in entries if e.state == "committed"), Decimal(0)),
                available=flow.available(version, cdf, funding, product)))
    return render(request, "purchasing/budgets.html", {"rows": rows})


@login_required
@require_http_methods(["GET"])
@xframe_options_sameorigin
def budget_check(request):
    form = BudgetCheckForm(request.GET if request.GET else None)
    result = None
    if form.is_bound and form.is_valid():
        data = form.cleaned_data
        version = data["version"]
        combination = dict(cost_center_id=data["cost_center"].pk,
            funding_id=data["funding"].pk, budget_product_id=data["budget_product"].pk)
        result = dict(available=flow.available(version, **combination),
            allocated=version.allocations.filter(**combination).exists(), year=version.envelope.year,
            version=version.label)
    return render(request, "purchasing/budget_check.html", {"form": form, "result": result})


@login_required
@require_http_methods(["GET", "POST"])
def delegations(request):
    form = DelegationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            flow.create_delegation(actor=request.user, principal=request.user, **form.cleaned_data)
            return redirect("my_delegations")
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, "purchasing/delegations.html", {"form": form,
        "delegations": Delegation.objects.filter(principal=request.user).select_related("delegate")})
