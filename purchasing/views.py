from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from decimal import Decimal
from .exceptions import PurchaseRequestError
from .forms import EditPurchaseRequestForm, PurchaseRequestForm, PurchaseRequestLineForm, RevisionForm
from .models import PurchaseRequest
from . import services
from .navigation_permissions import can_access_purchases, can_access_budget, can_access_configuration
from config import excel
from receiving.purchases import purchase_progress, line_progress


def export_requests(rows):
    return excel.response("demandes-achat", [("Demandes d’achat", ["Demande", "Demandeur", "Fournisseur", "Statut", "Création", "Réception"],
        ((p.number, p.created_by, p.supplier, p.get_status_display(), p.created_at, p.receipt_label) for p in purchase_progress(rows)))])


def _owned(request, pk):
    purchase = get_object_or_404(PurchaseRequest, pk=pk, created_by=request.user)
    if not request.user.has_perm("purchasing.add_purchaserequest"):
        raise PermissionDenied
    return purchase


def _form_error(form, error):
    for message in error.messages if isinstance(error, ValidationError) else [str(error)]:
        form.add_error(None, message)


@login_required
@require_http_methods(["GET"])
def request_list(request):
    if not can_access_purchases(request.user):
        if can_access_budget(request.user):
            return redirect("purchasing:budget_home")
        if can_access_configuration(request.user):
            return redirect("purchasing:configuration")
        return redirect("my_validations")
    if not request.user.has_perm("purchasing.add_purchaserequest"):
        return render(request, "purchasing/purchase_home.html")
    rows = PurchaseRequest.objects.filter(created_by=request.user).select_related("supplier", "created_by")
    if excel.requested(request):
        return export_requests(rows)
    return render(request, "purchasing/list.html", {
        "requests": purchase_progress(rows)})


@login_required
@permission_required("purchasing.view_all_purchase_requests", raise_exception=True)
@require_http_methods(["GET"])
def all_requests(request):
    rows = PurchaseRequest.objects.select_related("supplier", "created_by")
    if excel.requested(request):
        return export_requests(rows)
    return render(request, "purchasing/list.html", {
        "all_requests": True,
        "requests": purchase_progress(rows)})


@login_required
@require_http_methods(["GET", "POST"])
def request_create(request):
    if not request.user.has_perm("purchasing.add_purchaserequest"):
        raise PermissionDenied
    form = PurchaseRequestForm(request.POST if request.method == "POST" else None, user=request.user)
    if request.method == "POST" and form.is_valid():
        result = services.create_purchase_request(actor=request.user, **form.cleaned_data)
        return redirect("purchasing:detail", pk=result.pk)
    return render(request, "purchasing/form.html", {"form": form, "title": "Nouvelle demande"})


@login_required
@require_http_methods(["GET"])
def request_detail(request, pk):
    purchase = get_object_or_404(PurchaseRequest, pk=pk)
    if purchase.created_by_id != request.user.pk and not (
            request.user.has_perm("purchasing.view_purchase_financial")
            or request.user.has_perm("purchasing.view_all_purchase_requests")
            or request.user.has_perm("purchasing.decide_any_purchaserequest")):
        from django.http import Http404
        raise Http404
    from .models import ApprovalStep
    from . import flow
    for submission_id in purchase.submissions.filter(active=True).values_list("pk", flat=True):
        flow.refresh_submission(submission_id)
    purchase.refresh_from_db()
    steps = list(ApprovalStep.objects.filter(snapshot__submission__purchase_request=purchase)
        .select_related("function", "role", "approved_by", "snapshot__submission")
        .prefetch_related("candidates")
        .order_by("-snapshot__submission__active", "-snapshot__submission_id", "snapshot__original_line_id", "snapshot_id", "level", "pk"))
    for step in steps:
        step.is_current = purchase.status == "SUBMITTED" and step.snapshot.submission.active and step.state in ("pending", "unassigned", "blocked")
        step.actionable = purchase.status == "SUBMITTED" and step.snapshot.submission.active and (
            request.user.has_perm("purchasing.decide_any_purchaserequest") and step.state in ("pending", "unassigned", "blocked")
            or step.state == "pending" and bool(flow.authority(request.user, step)))
    lines = list(purchase.lines.select_related("detailed_product__budget_product", "cost_center", "funding"))
    active_steps = [step for step in steps if step.snapshot.submission.active]
    for line in lines:
        line.validation_steps = [step for step in active_steps if step.snapshot.original_line_id == line.pk]
        line.actionable_steps = [step for step in line.validation_steps if step.actionable]
        line.validation_approved = bool(line.validation_steps) and all(step.state == "approved" for step in line.validation_steps)
    actionable_steps = [step for step in steps if step.actionable]
    admin_validation_step = actionable_steps[0] if actionable_steps and request.user.has_perm("purchasing.decide_any_purchaserequest") else None
    line_progress(purchase, lines)
    purchase_progress([purchase])
    if excel.requested(request):
        return excel.response("detail-demande-achat", [
            ("Demande", ["Demande", "Demandeur", "Fournisseur", "Statut", "Création"],
             [(purchase.number, purchase.created_by, purchase.supplier, purchase.get_status_display(), purchase.created_at)]),
            ("Lignes", ["Code produit", "Produit", "BI", "Description", "CDF", "Financement", "Quantité", "Prix HTVA", "TVA %", "Total HTVA", "Total TVAC", "Réceptionné", "Reste à recevoir", "Réception"],
             ((line.detailed_product.code, line.detailed_product.label, line.detailed_product.budget_product, line.description,
               line.cost_center, line.funding, line.quantity, line.unit_price, line.vat_rate, line.total_htva,
               line.total_tvac if line.vat_rate is not None else None, line.received_quantity,
               line.remaining_quantity, line.receipt_label) for line in lines))])
    from workflow.models import ActivityLog
    events = list(purchase.audit_events.select_related("actor"))
    sources = [f"workflow.auditevent:{event.pk}" for event in events]
    identities = dict(ActivityLog.objects.filter(source__in=sources).values_list("source", "actor_username"))
    for event in events:
        event.actor_display = identities.get(f"workflow.auditevent:{event.pk}", str(event.actor) if event.actor else "Système")
    vat_known = all(line.vat_rate is not None for line in lines)
    return render(request, "purchasing/detail.html", {
        "purchase": purchase, "lines": lines,
        "receipts": purchase.order.receipts.select_related("warehouse", "actor") if hasattr(purchase, "order") else [],
        "total_htva": sum((line.total_htva for line in lines), Decimal(0)),
        "total_vat": sum((line.total_vat for line in lines), Decimal(0)) if vat_known else None,
        "total_tvac": sum((line.total_tvac for line in lines), Decimal(0)) if vat_known else None,
        "steps": steps, "has_line_actions": bool(actionable_steps),
        "admin_validation_step": admin_validation_step,
        "events": events,
        "can_cancel": request.user.has_perm("purchasing.add_purchaserequest") and purchase.created_by_id == request.user.pk and purchase.status == "SUBMITTED",
        "editable": request.user.has_perm("purchasing.add_purchaserequest") and purchase.created_by_id == request.user.pk and purchase.status in ("DRAFT", "CORRECTION")})


@login_required
@require_http_methods(["GET", "POST"])
def request_edit(request, pk):
    purchase = _owned(request, pk)
    form = EditPurchaseRequestForm(request.POST if request.method == "POST" else None,
        instance=purchase, initial={"expected_revision": purchase.revision}, user=request.user)
    return _command_form(request, purchase, form, services.update_purchase_request, "Modifier le fournisseur et le support")


@login_required
@require_http_methods(["GET", "POST"])
def line_edit(request, pk, line_id=None):
    purchase = _owned(request, pk)
    line = get_object_or_404(purchase.lines, pk=line_id) if line_id else None
    form = PurchaseRequestLineForm(request.POST if request.method == "POST" else None,
        instance=line, initial={"expected_revision": purchase.revision})
    command = services.update_purchase_request_line if line else services.add_purchase_request_line
    return _command_form(request, purchase, form, command, "Modifier la ligne" if line else "Ajouter une ligne",
                         {"line_id": line_id} if line else {})


@login_required
@require_http_methods(["GET", "POST"])
def line_delete(request, pk, line_id):
    purchase = _owned(request, pk)
    line = get_object_or_404(purchase.lines, pk=line_id)
    form = RevisionForm(request.POST if request.method == "POST" else None,
                        initial={"expected_revision": purchase.revision})
    return _command_form(request, purchase, form, services.delete_purchase_request_line,
                         "Supprimer la ligne : " + line.description, {"line_id": line.pk})


@login_required
@require_http_methods(["GET", "POST"])
def request_cancel(request, pk):
    purchase = _owned(request, pk)
    form = RevisionForm(request.POST if request.method == "POST" else None,
                        initial={"expected_revision": purchase.revision})
    return _command_form(request, purchase, form, services.cancel_purchase_request, "Confirmer l’annulation de la demande")


def _command_form(request, purchase, form, command, title, extra=None):
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            command(request_id=purchase.pk, actor=request.user, **form.cleaned_data, **(extra or {}))
            return redirect("purchasing:detail", pk=purchase.pk)
        except (ValidationError, PurchaseRequestError) as error:
            _form_error(form, error)
            status = 409
    return render(request, "purchasing/form.html", {"form": form, "title": title, "purchase": purchase}, status=status)
