from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from . import framework_contracts
from .forms import FrameworkContractForm, FrameworkPriceForm
from .models import FrameworkContract


@login_required
@permission_required("purchasing.view_frameworkcontract", raise_exception=True)
@require_GET
def contract_list(request):
    contracts = FrameworkContract.objects.select_related("supplier")
    search = request.GET.get("q", "").strip()
    if search:
        contracts = contracts.filter(Q(reference__icontains=search) | Q(title__icontains=search)
                                     | Q(supplier__name__icontains=search))
    return render(request, "purchasing/framework_contracts.html", {
        "page": Paginator(contracts, 50).get_page(request.GET.get("page")), "search": search,
    })


@login_required
@require_http_methods(["GET", "POST"])
def contract_edit(request, pk=None):
    if not request.user.has_perm("purchasing.change_frameworkcontract" if pk else "purchasing.add_frameworkcontract"):
        raise PermissionDenied
    contract = get_object_or_404(FrameworkContract, pk=pk) if pk else None
    form = FrameworkContractForm(request.POST if request.method == "POST" else None, instance=contract)
    if request.method == "POST" and form.is_valid():
        try:
            saved = framework_contracts.save_contract(actor=request.user, values=form.cleaned_data, pk=pk)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            if request.user.has_perm("purchasing.view_frameworkcontract"):
                return redirect("purchasing:framework_contract_detail", pk=saved.pk)
            return redirect("purchasing:list")
    return render(request, "purchasing/form.html", {"form": form,
        "title": "Modifier le contrat-cadre" if pk else "Nouveau contrat-cadre"})


@login_required
@permission_required("purchasing.view_frameworkcontract", raise_exception=True)
@require_http_methods(["GET", "POST"])
def contract_detail(request, pk):
    contract = get_object_or_404(FrameworkContract.objects.select_related("supplier"), pk=pk)
    prices = contract.prices.select_related("product").order_by("product__code")
    can_edit = request.user.has_perm("purchasing.change_frameworkcontract")
    if request.method == "POST" and not can_edit:
        raise PermissionDenied
    price_form = FrameworkPriceForm(request.POST if request.method == "POST" else None) if can_edit else None
    if request.method == "POST" and price_form.is_valid():
        try:
            framework_contracts.save_price(actor=request.user, contract_id=pk, values=price_form.cleaned_data)
        except ValidationError as error:
            price_form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Tarif enregistré.")
            return redirect("purchasing:framework_contract_detail", pk=pk)
    totals = framework_contracts.usage(contract)
    remaining = contract.ceiling - sum(totals.values()) if contract.ceiling is not None else None
    return render(request, "purchasing/framework_contract.html", {
        "contract": contract, "prices": prices, "price_form": price_form, "totals": totals,
        "remaining": remaining, "available": framework_contracts.available_contracts().filter(pk=pk).exists(),
    })
