from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from config import excel
from config.list_search import filter_rows
from config.party_quality import review_rows

from .forms import SupplierForm
from .identifiers import normalize_enterprise_number
from .models import Supplier
from .quality import supplier_issues
from .spreadsheet import EXPORT_HEADERS, IMPORT_HEADERS, SupplierImportForm, export_rows


@login_required
@require_http_methods(["GET"])
def supplier_list(request):
    if not any(request.user.has_perm("suppliers." + action + "_supplier") for action in ("view", "add", "change")):
        raise PermissionDenied
    suppliers, query = filter_rows(request, Supplier.objects.all(), {
        "code": ("Code", "code__icontains"), "name": ("Nom", "name__icontains"),
        "vat": ("TVA", "vat_number__icontains"),
        "enterprise": ("Numéro d’entreprise", lambda term: Q(enterprise_number__icontains=number)
                       if (number := normalize_enterprise_number(term)) else Q(pk__in=[])),
    })
    if excel.requested(request):
        return excel.response("fournisseurs", [("Fournisseurs", EXPORT_HEADERS, export_rows(suppliers))])
    quality = request.GET.get("quality") == "1"
    context = {"suppliers": suppliers, "query": query, "quality": quality}
    if quality:
        context["review_rows"] = review_rows(suppliers.prefetch_related("addresses", "contacts"), supplier_issues)
    return render(request, "suppliers/list.html", context)


@login_required
@permission_required("suppliers.add_supplier", raise_exception=True)
@require_http_methods(["GET"])
def supplier_template(request):
    return excel.response("patron-fournisseurs", [("Fournisseurs", IMPORT_HEADERS, [])], text_columns=(1, 3, 4, 6, 9, 10))


@login_required
@permission_required("suppliers.add_supplier", raise_exception=True)
@require_http_methods(["GET", "POST"])
def supplier_import(request):
    form = SupplierImportForm(request.POST, request.FILES) if request.method == "POST" else SupplierImportForm()
    if request.method == "POST" and form.is_valid():
        suppliers = form.cleaned_data["file"]
        try:
            with transaction.atomic():
                Supplier.objects.bulk_create(suppliers)
        except IntegrityError:
            form.add_error("file", "Un code fournisseur existe déjà. Vérifiez les codes puis relancez l’import.")
        else:
            messages.success(request, f"Fournisseurs importés : {len(suppliers)}.")
            return redirect("purchasing:suppliers")
    return render(request, "suppliers/import.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def supplier_edit(request, pk=None):
    permission = "suppliers.change_supplier" if pk is not None else "suppliers.add_supplier"
    if not request.user.has_perm(permission):
        raise PermissionDenied
    supplier = get_object_or_404(Supplier, pk=pk) if pk is not None else None
    form = SupplierForm(request.POST if request.method == "POST" else None, instance=supplier)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("purchasing:suppliers")
    return render(request, "suppliers/form.html", {"form": form, "supplier": supplier})
