from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import SupplierForm
from .models import Supplier


@login_required
@require_http_methods(["GET"])
def supplier_list(request):
    if not any(request.user.has_perm("suppliers." + action + "_supplier") for action in ("view", "add", "change")):
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    suppliers = Supplier.objects.all()
    if query:
        from .identifiers import normalize_enterprise_number
        filters = Q(code__icontains=query) | Q(name__icontains=query) | Q(vat_number__icontains=query)
        enterprise = normalize_enterprise_number(query)
        if enterprise:
            filters |= Q(enterprise_number__icontains=enterprise)
        suppliers = suppliers.filter(filters)
    return render(request, "suppliers/list.html", {"suppliers": suppliers, "query": query})


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
