from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .exceptions import PurchaseRequestError
from .forms import EditPurchaseRequestForm, PurchaseRequestForm, PurchaseRequestLineForm, RevisionForm
from .models import PurchaseRequest
from . import services


def _owned(request, pk):
    return get_object_or_404(PurchaseRequest, pk=pk, created_by=request.user)


def _form_error(form, error):
    for message in error.messages if isinstance(error, ValidationError) else [str(error)]:
        form.add_error(None, message)


@login_required
@require_http_methods(["GET"])
def request_list(request):
    return render(request, "purchasing/list.html", {
        "requests": PurchaseRequest.objects.filter(created_by=request.user).select_related("supplier")})


@login_required
@require_http_methods(["GET", "POST"])
def request_create(request):
    form = PurchaseRequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        result = services.create_purchase_request(actor=request.user, **form.cleaned_data)
        return redirect("purchasing:detail", pk=result.pk)
    return render(request, "purchasing/form.html", {"form": form, "title": "Nouvelle demande"})


@login_required
@require_http_methods(["GET"])
def request_detail(request, pk):
    purchase = _owned(request, pk)
    return render(request, "purchasing/detail.html", {
        "purchase": purchase, "lines": purchase.lines.select_related("detailed_product", "cost_center", "funding"),
        "editable": purchase.status in ("DRAFT", "CORRECTION")})


@login_required
@require_http_methods(["GET", "POST"])
def request_edit(request, pk):
    purchase = _owned(request, pk)
    form = EditPurchaseRequestForm(request.POST if request.method == "POST" else None,
        instance=purchase, initial={"expected_revision": purchase.revision})
    return _command_form(request, purchase, form, services.update_purchase_request, "Modifier le fournisseur")


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
