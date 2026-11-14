from decimal import Decimal
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.cache import never_cache
from . import flow
from .models import (PurchaseRequest, ApprovalStep, Submission, PurchaseOrder,
    AnnualEnvelope, PurchaseNotice, Delegation)
from .forms import RevisionForm, BudgetCheckForm, BudgetVersionSelectionForm
from .flow_forms import DecisionForm, ReassignForm, DelegationForm
from .exceptions import PurchaseRequestError
from config import excel


@login_required
@require_http_methods(["GET"])
def validation_schemes(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    return render(request, "purchasing/validation_schemes.html")


def _refresh():
    for pk in Submission.objects.filter(active=True).values_list("pk", flat=True):
        flow.refresh_submission(pk)


def _operational_step(step, user):
    # Template gets an explicit safe dictionary; no financial model available.
    return dict(id=step.pk, request_id=step.snapshot.submission.purchase_request_id,
        number=step.snapshot.submission.purchase_request.number, line=step.snapshot.original_line_id,
        function=step.function_label, level=step.level, status=step.get_state_display(),
        candidates=", ".join(candidate.username for candidate in step.candidates.all()) or "À affecter",
        waiting_since=step.waiting_since, state=step.state,
        actionable=step.state == "pending" and bool(flow.authority(user, step)))


@login_required
@require_http_methods(["GET"])
def inbox(request):
    _refresh()
    from budgeting.models import BudgetTransfer
    from budgeting import transfers
    transfer_tasks = []
    for pk in BudgetTransfer.objects.filter(status="pending").values_list("pk", flat=True):
        transfer = transfers.refresh(pk)
        if transfer.status == "pending":
            transfer_tasks.extend(step for step in transfer.steps.filter(state="pending") if transfers.is_assigned_validator(request.user, step))
    steps = ApprovalStep.objects.filter(snapshot__submission__active=True).select_related(
        "snapshot__submission__purchase_request", "function").prefetch_related("candidates")
    owned = [s for s in steps if flow.authority(request.user, s) or s.candidates.filter(pk=request.user.pk).exists()]
    notices = PurchaseNotice.objects.filter(recipient=request.user, active=True)
    return render(request, "purchasing/inbox.html", {"steps": [_operational_step(s, request.user) for s in owned], "notices": notices, "transfer_tasks": transfer_tasks,
        "returned_transfers": BudgetTransfer.objects.filter(status="returned", created_by=request.user)})


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
    rows = [_operational_step(s, request.user) for s in steps]
    if excel.requested(request):
        return excel.response("suivi-achats", [("Étapes de validation", ["Demande", "Ligne", "Niveau", "Étape", "État", "Valideurs", "En attente depuis"],
            ((r["number"], r["line"], r["level"], r["function"], r["status"], r["candidates"], r["waiting_since"]) for r in rows))])
    return render(request, "purchasing/monitor.html", {"steps": rows, "state": state, "number": number})


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
    if not flow.authority(request.user, step) and not request.user.has_perm("purchasing.decide_any_purchaserequest"):
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
    if form_type is DecisionForm and not request.user.has_perm("purchasing.decide_any_purchaserequest"):
        form.fields["decision"].choices = [(value, label) for value, label in form.fields["decision"].choices if value != "approve_all"]
    status = 200
    wants_json = form_type in (RevisionForm, DecisionForm) and request.headers.get("Accept") == "application/json"
    if request.method == "POST" and form.is_valid():
        try:
            command(request_id=purchase.pk, actor=request.user, **form.cleaned_data, **(extra or {}))
            destination = redirect("purchasing:detail", pk=purchase.pk) if (
                request.user.pk == purchase.created_by_id
                or request.user.has_perm("purchasing.view_purchase_financial")
                or request.user.has_perm("purchasing.decide_any_purchaserequest")) else redirect("my_validations")
            if wants_json:
                return JsonResponse({"redirect": destination.url})
            return destination
        except (ValidationError, PurchaseRequestError) as error:
            form.add_error(None, " · ".join(error.messages) if isinstance(error, ValidationError) else str(error))
            status = 409
    if wants_json and request.method == "POST":
        return JsonResponse({"errors": [str(error) for errors in form.errors.values() for error in errors]}, status=status if status != 200 else 400)
    return render(request, "purchasing/form.html", {"form": form, "title": title, "purchase": purchase,
        "action_failed": form_type is RevisionForm and request.method == "POST" and bool(form.errors)}, status=status)


@login_required
@xframe_options_sameorigin
@require_http_methods(["GET"])
def order_document(request, pk):
    order = get_object_or_404(PurchaseOrder.objects.select_related("purchase_request"), purchase_request_id=pk)
    if order.purchase_request.created_by_id != request.user.pk and not (
            request.user.has_perm("purchasing.view_purchase_financial")
            or request.user.has_perm("purchasing.view_all_purchase_requests")
            or request.user.has_perm("purchasing.decide_any_purchaserequest")):
        raise Http404
    lines = list(order.submission.lines.all())
    return render(request, "purchasing/order.html", {"order": order, "lines": lines,
        "total": sum((line.amount for line in lines), Decimal(0))})


@login_required
@permission_required("budgeting.view_budget_balances", raise_exception=True)
@require_http_methods(["GET"])
def budgets(request):
    data = request.GET.copy()
    form = BudgetVersionSelectionForm()
    versions = form.fields["version"].queryset
    if not data.get("version"):
        default = versions.filter(pk__in=AnnualEnvelope.objects.values("active_version_id")).first() or versions.first()
        if default:
            data["version"] = str(default.pk)
    form = BudgetVersionSelectionForm(data if data else None)
    form.fields["version"].empty_label = None
    selected_version = form.cleaned_data["version"] if form.is_bound and form.is_valid() else None
    rows = []
    if selected_version:
        version = selected_version
        envelope = version.envelope
        # Include combinations removed by a later budget version too.
        from .models import BudgetEntry
        combinations = set(version.allocations.values_list("cost_center_id", "funding_id", "budget_product_id"))
        from budgeting.models import BudgetTransfer
        from budgeting.transfers import transfer_balance
        transfers = BudgetTransfer.objects.filter(budget_version=version, status__in=["pending", "approved"])
        for transfer in transfers:
            combinations.add(transfer.combination("source"))
            if transfer.status == "approved":
                combinations.add(transfer.combination("destination"))
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
                transfers=transfer_balance(version.pk, cdf, funding, product),
                available=flow.available(version, cdf, funding, product)))
    if excel.requested(request) and not form.errors:
        return excel.response("budgets-disponibilites", [("Budgets et disponibilités", ["Année", "Version", "CDF", "Financement", "BI", "Allocation TVAC", "Réservé", "Engagé", "Solde transferts", "Disponible"],
            ((r["year"], r["version"], r["cdf"], r["funding"], r["product"], r["allocated"], r["reserved"], r["committed"], r["transfers"], r["available"]) for r in rows))])
    return render(request, "purchasing/budgets.html", {"rows": rows, "form": form, "selected_version": selected_version})


@login_required
@require_http_methods(["GET"])
@xframe_options_sameorigin
@never_cache
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
