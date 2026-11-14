from uuid import uuid4
from decimal import Decimal
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.contrib import messages
from purchasing.models import DetailedProduct, PurchaseRequest
from purchasing.flow import require
from .models import Warehouse, StockBalance, StockMovement
from .services import move
from .purchases import receive_purchase, purchase_progress, line_progress
from config import excel


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["code", "label"]


class MovementForm(forms.Form):
    warehouse = forms.ModelChoiceField(Warehouse.objects.all(), label="Dépôt source")
    destination = forms.ModelChoiceField(Warehouse.objects.all(), required=False, label="Dépôt destination (transfert)")
    product = forms.ModelChoiceField(DetailedProduct.objects.all(), label="Produit")
    kind = forms.ChoiceField(choices=StockMovement._meta.get_field("kind").choices, label="Opération")
    quantity = forms.DecimalField(max_digits=18, decimal_places=4, min_value=0, label="Quantité (quantité comptée pour un inventaire)")
    reason = forms.CharField(widget=forms.Textarea, label="Justification / référence")
    token = forms.UUIDField(widget=forms.HiddenInput)


class PurchaseReceiptForm(forms.Form):
    warehouse = forms.ModelChoiceField(Warehouse.objects.all(), label="Dépôt de réception")
    reason = forms.CharField(label="Référence du bon de livraison / commentaire", widget=forms.Textarea(attrs={"rows": 2}))
    token = forms.UUIDField(widget=forms.HiddenInput)


class PurchaseReceiptQuantityForm(forms.Form):
    line_id = forms.IntegerField(widget=forms.HiddenInput)
    quantity = forms.DecimalField(max_digits=18, decimal_places=4, min_value=0, required=False,
                                 label="Quantité réceptionnée aujourd’hui")


ReceiptFormSet = forms.formset_factory(PurchaseReceiptQuantityForm, extra=0,
    min_num=1, validate_min=True, max_num=1000, validate_max=True, absolute_max=1000)


@login_required
@require_http_methods(["GET"])
def purchase_receipts(request):
    require(request.user, "receiving.manage_stock")
    rows = PurchaseRequest.objects.filter(status="ORDERED", order__isnull=False).select_related("supplier", "created_by")
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(number__icontains=query)
    page = Paginator(rows, 50).get_page(request.GET.get("page"))
    page.object_list = purchase_progress(page.object_list)
    return render(request, "receiving/purchase_receipts.html", {"page": page, "query": query})


@login_required
@require_http_methods(["GET", "POST"])
def purchase_receive(request, pk):
    require(request.user, "receiving.manage_stock")
    purchase = get_object_or_404(PurchaseRequest.objects.select_related("supplier", "order"), pk=pk, status="ORDERED", order__isnull=False)
    lines = line_progress(purchase, list(purchase.lines.select_related("detailed_product", "cost_center", "funding")))
    data = request.POST if request.method == "POST" else None
    form = PurchaseReceiptForm(data, initial={"token": uuid4()})
    formset = ReceiptFormSet(data, prefix="lines", initial=[{"line_id": line.pk, "quantity": 0} for line in lines])
    error = None
    if request.method == "POST":
        header_valid, lines_valid = form.is_valid(), formset.is_valid()
        if header_valid and lines_valid:
            try:
                receipt = receive_purchase(actor=request.user, purchase_id=purchase.pk, **form.cleaned_data,
                    quantities=[(row.cleaned_data["line_id"], row.cleaned_data["quantity"] or Decimal(0)) for row in formset])
                messages.success(request, f"Réception {receipt.pk} enregistrée pour la demande {purchase.number}.")
                return redirect("purchase_receive", pk=pk)
            except ValidationError as exc:
                error = " · ".join(exc.messages)
    by_id = {line.pk: line for line in lines}
    rows = []
    for row in formset:
        try:
            line = by_id.get(int(row["line_id"].value()))
        except (TypeError, ValueError):
            line = None
        rows.append({"form": row, "line": line})
    purchase_progress([purchase])
    receipts = purchase.order.receipts.select_related("warehouse", "actor").prefetch_related("lines__purchase_line__detailed_product", "lines__movement")
    return render(request, "receiving/purchase_receive.html", {"purchase": purchase, "form": form,
        "formset": formset, "rows": rows, "error": error, "receipts": receipts})


@login_required
@require_http_methods(["GET"])
def stock(request):
    if not any(request.user.has_perm("receiving." + permission) for permission in (
            "view_warehouse", "add_warehouse", "change_warehouse", "view_stockbalance", "manage_stock", "view_stockmovement")):
        raise PermissionDenied
    return render(request, "receiving/stock_home.html")


@login_required
@require_http_methods(["GET", "POST"])
def stock_movements(request):
    if not any(request.user.has_perm("receiving." + permission) for permission in (
            "view_stockbalance", "manage_stock", "view_stockmovement")):
        raise PermissionDenied
    movement_form = MovementForm(initial={"token": uuid4()})
    if request.method == "POST":
        require(request.user, "receiving.manage_stock")
        movement_form = MovementForm(request.POST)
        if movement_form.is_valid():
            try:
                move(actor=request.user, **movement_form.cleaned_data)
                return redirect("stock_movements")
            except ValidationError as error:
                movement_form.add_error(None, error)
    movements = StockMovement.objects.select_related("warehouse", "destination", "product", "actor", "receipt_line__receipt__order__purchase_request")
    if excel.requested(request):
        return excel.response("mouvements-stock", [("Mouvements", ["Date", "Opération", "Dépôt source", "Destination", "Code produit", "Produit", "Quantité", "Variation source", "Justification", "Auteur", "Demande d’achat", "Réception"],
            ((m.created_at, m.get_kind_display(), m.warehouse, m.destination, m.product.code, m.product.label, m.quantity, m.delta, m.reason, m.actor,
              m.receipt_line.receipt.order.purchase_request.number if hasattr(m, "receipt_line") else None,
              m.receipt_line.receipt_id if hasattr(m, "receipt_line") else None) for m in movements.iterator()))])
    return render(request, "receiving/stock.html", {"form": movement_form, "movements": movements[:200]})


@login_required
@require_http_methods(["GET"])
def stock_balances(request):
    if not (request.user.has_perm("receiving.view_stockbalance") or request.user.has_perm("receiving.manage_stock")):
        raise PermissionDenied
    balances = StockBalance.objects.select_related("warehouse", "product").order_by("warehouse__code", "product__code")
    if excel.requested(request):
        return excel.response("stocks", [("Quantités disponibles", ["Code dépôt", "Dépôt", "Code produit", "Produit", "Quantité"],
            ((b.warehouse.code, b.warehouse.label, b.product.code, b.product.label, b.quantity) for b in balances.iterator()))])
    return render(request, "receiving/stock_balances.html", {"balances": balances})


@login_required
@require_http_methods(["GET", "POST"])
def warehouses(request, pk=None):
    if not any(request.user.has_perm("receiving." + permission) for permission in (
            "view_warehouse", "add_warehouse", "change_warehouse", "view_stockbalance", "manage_stock")):
        raise PermissionDenied
    warehouse = None
    if pk is not None:
        require(request.user, "receiving.change_warehouse")
        warehouse = get_object_or_404(Warehouse, pk=pk)
    can_edit = request.user.has_perm("receiving.change_warehouse" if warehouse else "receiving.add_warehouse")
    form = WarehouseForm(request.POST if request.method == "POST" else None, instance=warehouse)
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            form.save()
            return redirect("warehouses")
    rows = Warehouse.objects.order_by("code")
    if excel.requested(request):
        return excel.response("depots", [("Dépôts", ["Code", "Dépôt"], ((w.code, w.label) for w in rows.iterator()))])
    return render(request, "receiving/warehouses.html", {"warehouses": rows,
        "warehouse": warehouse, "form": form, "can_edit": can_edit})
