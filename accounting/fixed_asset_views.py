from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from config import excel
from workflow.activity import snapshot
from . import fixed_assets
from .models import FixedAsset, SupplierInvoice


VIEW = "accounting.view_fixedasset"
ADD = "accounting.add_fixedasset"
CHANGE = "accounting.change_fixedasset"


class AssetForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = FixedAsset
        fields = ("code", "label", "category", "location", "cost_center", "supplier_invoice",
            "acquired_on", "in_service_on", "cost", "residual_value", "useful_life_months")
        widgets = {key: forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
            for key in ("acquired_on", "in_service_on")}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["revision"] = self.instance.revision
        if user.has_perm("accounting.view_supplierinvoice"):
            self.fields["supplier_invoice"].queryset = SupplierInvoice.objects.filter(status="REVIEWED", currency="EUR")
        else:
            self.fields.pop("supplier_invoice")


class TransitionForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class AssetLocationForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = FixedAsset
        fields = ("location", "cost_center")


class DisposalForm(TransitionForm):
    disposed_on = forms.DateField(label="Date de sortie", widget=forms.DateInput(
        format="%Y-%m-%d", attrs={"type": "date"}))
    disposal_reason = forms.CharField(label="Motif de sortie", max_length=250)
    proceeds = forms.DecimalField(label="Prix de sortie (€)", min_value=0, max_digits=18, decimal_places=2, initial=0)


def _rows(assets):
    today = timezone.localdate()
    cutoff = today + timedelta(days=1)
    for asset in assets:
        accumulated = fixed_assets.depreciation(asset, cutoff) if asset.status != FixedAsset.Status.DRAFT else None
        yield {"asset": asset, "accumulated": accumulated,
            "net": asset.cost - accumulated if accumulated is not None else None}


@login_required
@permission_required(VIEW, raise_exception=True)
@require_GET
def asset_list(request):
    q = request.GET.get("q", "").strip()[:200]
    status = request.GET.get("status", "")
    assets = FixedAsset.objects.select_related("cost_center")
    if q:
        assets = assets.filter(Q(code__icontains=q) | Q(label__icontains=q) | Q(category__icontains=q)
            | Q(location__icontains=q) | Q(cost_center__code__icontains=q))
    if status in FixedAsset.Status.values:
        assets = assets.filter(status=status)
    if excel.requested(request):
        return excel.response("registre-immobilisations", [("Immobilisations",
            ["Inventaire", "Désignation", "Catégorie", "Localisation", "CDF", "État", "Acquisition",
                "Mise en service", "Valeur d’acquisition (€)", "Amortissement calculé (€)", "Valeur nette (€)", "Sortie"],
            ((a.code, a.label, a.category, a.location, a.cost_center, a.get_status_display(),
                a.acquired_on, a.in_service_on, a.cost, row["accumulated"], row["net"], a.disposed_on)
                for row in _rows(assets.iterator()) for a in (row["asset"],)))])
    page = Paginator(assets, 50).get_page(request.GET.get("page"))
    return render(request, "accounting/fixed_assets.html", {"page": page, "rows": list(_rows(page)),
        "q": q, "status": status, "statuses": FixedAsset.Status.choices})


@login_required
@permission_required(VIEW, raise_exception=True)
@require_GET
def asset_detail(request, pk):
    asset = get_object_or_404(FixedAsset.objects.select_related("cost_center"), pk=pk)
    row = next(_rows((asset,)))
    return render(request, "accounting/fixed_asset_detail.html", {
        **row, "schedule": list(fixed_assets.schedule(asset)),
        "invoice": asset.supplier_invoice if request.user.has_perm("accounting.view_supplierinvoice") else None,
        "disposal_result": asset.proceeds - row["net"] if asset.status == FixedAsset.Status.DISPOSED else None,
    })


@login_required
@permission_required(VIEW, raise_exception=True)
@require_http_methods(["GET", "POST"])
def asset_edit(request, pk=None):
    if not request.user.has_perm(CHANGE if pk is not None else ADD):
        raise PermissionDenied
    with transaction.atomic():
        assets = FixedAsset.objects.select_for_update() if request.method == "POST" else FixedAsset.objects.all()
        asset = get_object_or_404(assets.exclude(status=FixedAsset.Status.DISPOSED), pk=pk) if pk is not None else FixedAsset()
        before = snapshot(asset) if pk is not None else None
        data = request.POST if request.method == "POST" else None
        active = asset.status == FixedAsset.Status.ACTIVE
        if active:
            form = AssetLocationForm(data, instance=asset, initial={"revision": asset.revision})
        else:
            form = AssetForm(data, instance=asset, user=request.user)
        if request.method == "POST" and form.is_valid():
            try:
                fixed_assets.check_revision(asset, form.cleaned_data["revision"])
                with transaction.atomic():
                    asset.revision += 1
                    asset.save()
                    action = "relocated" if active else "updated" if pk is not None else "created"
                    fixed_assets.audit(asset, action, request.user, before)
            except ValidationError as error:
                form.add_error(None, " ".join(error.messages))
            except IntegrityError:
                if not FixedAsset.objects.filter(code=asset.code).exclude(pk=pk).exists():
                    raise
                form.add_error("code", "Ce numéro d’inventaire est déjà utilisé.")
            else:
                messages.success(request, "Fiche d’immobilisation enregistrée.")
                return redirect("accounting:asset_detail", pk=asset.pk)
    title = "Nouvelle immobilisation" if pk is None else "Modifier l’affectation" if active else "Modifier l’immobilisation"
    return render(request, "accounting/form.html", {"form": form, "title": title,
        "back_url": reverse("accounting:asset_detail", args=[pk]) if pk is not None else reverse("accounting:assets")})


@login_required
@permission_required((VIEW, CHANGE), raise_exception=True)
@require_http_methods(["GET", "POST"])
def asset_transition(request, pk, action):
    if action == "activate":
        form_type, title = TransitionForm, "Confirmer la mise en service"
        expected_status = FixedAsset.Status.DRAFT
        intro = "La mise en service fige les données d’acquisition et le plan d’amortissement."
    else:
        form_type, title = DisposalForm, "Enregistrer la sortie"
        expected_status = FixedAsset.Status.ACTIVE
        intro = "La date de sortie arrête le calcul de l’amortissement."
    asset = get_object_or_404(FixedAsset, pk=pk, status=expected_status)
    form = form_type(request.POST if request.method == "POST" else None,
        initial={"revision": asset.revision, "disposed_on": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            fixed_assets.transition(pk=asset.pk, actor=request.user, action=action, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "État de l’immobilisation enregistré.")
            return redirect("accounting:asset_detail", pk=asset.pk)
    return render(request, "accounting/form.html", {"form": form, "title": f"{title} · {asset.code}",
        "intro": intro, "back_url": reverse("accounting:asset_detail", args=[asset.pk])})
