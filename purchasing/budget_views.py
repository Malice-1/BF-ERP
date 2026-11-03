"""Budget manager workspace, using the procurement budget versions."""
from django import forms
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .flow import activate_envelope
from .models import AnnualEnvelope, EnvelopeVersion, Allocation
from budgeting.models import BudgetProduct
from .models import DetailedProduct
from .navigation_permissions import can_access_budget, can_access_configuration

MANAGER_PERMISSIONS = tuple("budgeting." + name for name in (
    "add_annualenvelope", "add_envelopeversion", "change_envelopeversion",
    "add_allocation", "change_allocation", "delete_allocation"))


class DetailedProductForm(forms.ModelForm):
    class Meta:
        model = DetailedProduct
        fields = ("code", "label", "budget_product")
        labels = {"code": "Code produit détaillé", "label": "Dénomination",
                  "budget_product": "Produit budgétaire (BI)"}


@login_required
@permission_required("purchasing.add_detailedproduct", raise_exception=True)
@require_http_methods(["GET", "POST"])
def detailed_products(request):
    form = DetailedProductForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("purchasing:detailed_products")
    return render(request, "purchasing/detailed_products.html", {
        "form": form, "products": DetailedProduct.objects.select_related("budget_product")})


@login_required
@require_http_methods(["GET"])
def budget_home(request):
    if not can_access_budget(request.user):
        raise PermissionDenied
    return render(request, "purchasing/budget_home.html", {
        "can_manage": request.user.has_perms(MANAGER_PERMISSIONS)})


@login_required
@permission_required(MANAGER_PERMISSIONS, raise_exception=True)
@require_http_methods(["GET"])
def allocation_versions(request):
    return render(request, "purchasing/allocation_versions.html", {
        "versions": EnvelopeVersion.objects.select_related("envelope").order_by("-envelope__year", "-pk")})


@login_required
@require_http_methods(["GET"])
def configuration(request):
    if not can_access_configuration(request.user):
        raise PermissionDenied
    return render(request, "purchasing/configuration.html")


class BudgetProductForm(forms.ModelForm):
    class Meta:
        model = BudgetProduct
        fields = ("code", "label")
        labels = {"code": "Code BI / produit budgétaire", "label": "Libellé"}


@login_required
@permission_required("budgeting.add_budgetproduct", raise_exception=True)
@require_http_methods(["GET", "POST"])
def budget_products(request):
    form = BudgetProductForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("purchasing:budget_products")
    return render(request, "purchasing/budget_products.html", {
        "form": form, "products": BudgetProduct.objects.all()})


class VersionForm(forms.Form):
    year = forms.IntegerField(label="Année budgétaire", min_value=2000, max_value=9999)
    label = forms.CharField(label="Nom de la version", max_length=100)


AllocationFormSet = inlineformset_factory(EnvelopeVersion, Allocation,
    fields=("budget_product", "cost_center", "funding", "amount"), extra=3,
    labels={"budget_product": "BI / produit budgétaire", "cost_center": "CDF",
            "funding": "Financement", "amount": "Montant TVAC (€)"},
    widgets={"amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"})})


@login_required
@permission_required(MANAGER_PERMISSIONS, raise_exception=True)
@require_http_methods(["GET", "POST"])
def versions(request):
    form = VersionForm(request.POST if request.method == "POST" else None,
                       initial={"year": timezone.localdate().year})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            envelope, _ = AnnualEnvelope.objects.get_or_create(year=form.cleaned_data["year"])
            version = EnvelopeVersion.objects.create(envelope=envelope, label=form.cleaned_data["label"])
        return redirect("purchasing:budget_version", pk=version.pk)
    return render(request, "purchasing/budget_versions.html", {
        "form": form})


@login_required
@permission_required(MANAGER_PERMISSIONS, raise_exception=True)
@require_http_methods(["GET", "POST"])
def version_detail(request, pk):
    version = get_object_or_404(EnvelopeVersion.objects.select_related("envelope"), pk=pk)
    error = None
    formset = AllocationFormSet(instance=version)
    if request.method == "POST":
        with transaction.atomic():
            # Match the lock order used by publication and purchase submission.
            AnnualEnvelope.objects.select_for_update().get(pk=version.envelope_id)
            version = EnvelopeVersion.objects.select_for_update().select_related("envelope").get(pk=pk)
            if version.published_at:
                error = "Cette version est publiée et ne peut plus être modifiée. Créez une nouvelle version."
            elif request.POST.get("action") == "publish":
                try:
                    activate_envelope(actor=request.user, version_id=version.pk)
                    return redirect("purchasing:budget_version", pk=pk)
                except ValidationError as exc:
                    error = " · ".join(exc.messages)
            else:
                formset = AllocationFormSet(request.POST, instance=version)
                if formset.is_valid():
                    formset.save()
                    return redirect("purchasing:budget_version", pk=pk)
    return render(request, "purchasing/budget_version.html", {
        "version": version, "formset": formset, "error": error,
        "lines": version.allocations.select_related("budget_product", "cost_center", "funding")})
