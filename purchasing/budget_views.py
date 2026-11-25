"""Budget manager workspace, using the procurement budget versions."""
from django import forms
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.urls import reverse
from urllib.parse import urlencode
from django.db.models.functions import Trim
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from decimal import Decimal
from config import excel
from django.views.decorators.http import require_http_methods

from .flow import activate_envelope, lock_envelope, unlock_envelope, delete_envelope_version
from .models import AnnualEnvelope, EnvelopeVersion, Allocation
from budgeting.models import BudgetProduct
from .models import DetailedProduct
from .navigation_permissions import can_access_budget, can_access_configuration
from .forms import BudgetAmountInput

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
    if excel.requested(request):
        return excel.response("produits-detailles", [("Produits détaillés", ["Code", "Dénomination", "BI"],
            ((p.code, p.label, p.budget_product) for p in DetailedProduct.objects.select_related("budget_product").order_by("code").iterator()))])
    return render(request, "purchasing/detailed_products.html", {
        "form": form, "products": DetailedProduct.objects.select_related("budget_product")})


@login_required
@require_http_methods(["GET"])
def budget_home(request):
    if not can_access_budget(request.user):
        raise PermissionDenied
    return render(request, "purchasing/budget_home.html", {
        "can_manage": request.user.has_perms(MANAGER_PERMISSIONS),
        "can_view_budget_history": can_view_budget_history(request.user)})


@login_required
@permission_required(MANAGER_PERMISSIONS, raise_exception=True)
@require_http_methods(["GET"])
def allocation_versions(request):
    if request.GET.get("template") == "xlsx":
        from .allocation_excel import template_sheets
        return excel.response("modele-alimentation-budget", template_sheets())
    versions = EnvelopeVersion.objects.filter(deleted_at__isnull=True).select_related("envelope").annotate(allocation_total=Sum("allocations__amount")).order_by("-envelope__year", "-pk")
    if excel.requested(request):
        return excel.response("versions-budgetaires", [("Versions", ["Année", "Version", "État", "Publication", "Blocage", "Total TVAC"],
            ((v.envelope.year, v.label, "Bloquée" if v.locked_at else "Active" if v.envelope.active_version_id == v.pk else "Publiée remplacée" if v.published_at else "Brouillon", v.published_at, v.locked_at, v.allocation_total or 0) for v in versions.iterator()))])
    return render(request, "purchasing/allocation_versions.html", {
        "versions": versions})


@login_required
@require_http_methods(["GET"])
def configuration(request):
    if not can_access_configuration(request.user):
        raise PermissionDenied
    def admin_link(model, label, description):
        app, name = model.split(".")
        if not request.user.is_staff:
            return None
        if any(request.user.has_perm(f"{app}.{action}_{name}") for action in ("view", "change")):
            target = "changelist"
        elif request.user.has_perm(f"{app}.add_{name}"):
            target = "add"
        else:
            return None
        return {"url": reverse(f"admin:{app}_{name}_{target}"), "label": label, "description": description}

    workflow = [
        admin_link("accounts.role", "Rôles et permissions", "Définir les droits d’accès des utilisateurs."),
    ]
    workflow += [
        admin_link("budgeting.costcenter", "CDF", "Gérer les CDF et les responsables qui valident les demandes et les transferts."),
        admin_link("budgeting.support", "Supports", "Gérer les supports choisis sur les demandes et leurs responsables."),
    ]
    access = [admin_link("accounts.user", "Comptes utilisateurs et droits individuels",
                         "Gérer les comptes, attribuer leurs rôles et leurs supports d’appartenance.")]
    technical = [
        link for link in (
            admin_link("budgeting.funding", "Financements", "Gérer les codes et libellés des financements."),
            admin_link("budgeting.subproject", "Sous-projets", "Gérer les codes et libellés des sous-projets."),
            admin_link("budgeting.section", "Sections", "Gérer les codes et libellés des sections."),
        ) if link
    ]
    if request.user.is_staff:
        technical.append({"url": reverse("admin:index"), "label": "Administration et référentiels techniques",
                          "description": "Retrouver notamment les fournisseurs et les produits."})
    if request.user.is_superuser:
        access.append({"url": reverse("session_settings"), "label": "Déconnexion automatique",
                       "description": "Définir la durée d’inactivité autorisée."})
        technical.append({"url": reverse("admin:workflow_activitylog_changelist"), "label": "Journal des actions par utilisateur",
                          "description": "Consulter la traçabilité des actions et des modifications."})
    groups = [
        {"id": "workflow-settings", "title": "Responsables et validations", "links": [link for link in workflow if link]},
        {"id": "access-settings", "title": "Utilisateurs et accès", "links": [link for link in access if link]},
        {"id": "technical-settings", "title": "Référentiels et suivi technique", "links": technical},
    ]
    return render(request, "purchasing/configuration.html", {"configuration_groups": groups})


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
    search = request.GET.get("q", "").strip()
    products = BudgetProduct.objects.order_by("code")
    if search:
        products = products.filter(Q(code__icontains=search) | Q(label__icontains=search))
    if excel.requested(request):
        return excel.response("produits-budgetaires", [("Produits budgétaires", ["Code", "Libellé"],
            ((p.code, p.label) for p in products.iterator()))])
    template = "purchasing/budget_products_results.html" if request.headers.get("X-Requested-With") == "XMLHttpRequest" else "purchasing/budget_products.html"
    return render(request, template, {
        "form": form, "products": products, "search": search})


class VersionForm(forms.Form):
    year = forms.IntegerField(label="Année budgétaire", min_value=2000, max_value=9999)
    label = forms.CharField(label="Nom de la version", max_length=100)

    def clean(self):
        data = super().clean()
        if data.get("year") and data.get("label") and EnvelopeVersion.objects.filter(
                envelope__year=data["year"]).annotate(trimmed_label=Trim("label")).filter(
                    trimmed_label__iexact=data["label"]).exists():
            self.add_error("label", "Une version portant ce nom existe déjà pour cette année.")
        return data


class BudgetVersionSelectionForm(forms.Form):
    version = forms.ModelChoiceField(queryset=EnvelopeVersion.objects.select_related("envelope").order_by("-envelope__year", "-pk"), label="Version budgétaire")


class BudgetHistoryForm(BudgetVersionSelectionForm):
    at = forms.DateTimeField(required=False, label="État à la date et à l’heure", widget=forms.DateTimeInput(attrs={"type": "datetime-local", "step": "1"}))


def can_view_budget_history(user):
    return (user.has_perm("budgeting.view_budget_balances") or user.has_perm("budgeting.view_envelopeversion")
            or user.has_perms(MANAGER_PERMISSIONS))


@login_required
@require_http_methods(["GET"])
def budget_history(request, version_id=None):
    if not can_view_budget_history(request.user):
        raise PermissionDenied
    from budgeting.models import BudgetHistoryEvent
    from budgeting.history import describe_timeline
    data = request.GET.copy()
    scoped_version = version_id is not None or bool(data.get("version"))
    if version_id is not None:
        get_object_or_404(EnvelopeVersion, pk=version_id)
        data["version"] = str(version_id)
    if not data.get("version"):
        latest = EnvelopeVersion.objects.filter(deleted_at__isnull=True).order_by("-envelope__year", "-pk").first()
        if latest is None:
            latest = EnvelopeVersion.objects.order_by("-envelope__year", "-pk").first()
        if latest:
            data["version"] = str(latest.pk)
    form = BudgetHistoryForm(data)
    if scoped_version:
        form.fields["version"].widget = forms.HiddenInput()
    state, selected, first, timeline, version = None, None, None, [], None
    valid = form.is_valid()
    version = form.cleaned_data.get("version")
    if valid:
        events = BudgetHistoryEvent.objects.filter(envelope_id=version.envelope_id).order_by("created_at", "pk")
        # Earlier snapshots may precede this version's creation.
        timeline = [event for event in events if event.version_id in (None, version.pk) and str(version.pk) in event.state.get("versions", {})]
        describe_timeline(timeline, version.pk)
        first = timeline[0] if timeline else None
        at = form.cleaned_data["at"] or timezone.now()
        if at > timezone.now():
            form.add_error("at", "Choisissez une date passée ou actuelle.")
        else:
            selected = next((event for event in reversed(timeline) if event.created_at <= at), None)
            if selected:
                state = selected.state["versions"][str(version.pk)]
    export_scope = request.GET.get("section", "all")
    if excel.requested(request) and valid and not form.errors and export_scope == "timeline":
        return excel.response("chronologie-budgetaire", [
            ("Chronologie", ["Date", "Auteur", "Événement"], ((e.created_at, e.actor, e.display_reason) for e in timeline)),
            ("Contexte", ["Année", "Version"], [(version.envelope.year, version.label)])])
    if excel.requested(request) and state and export_scope in ("state", "all"):
        sheets = [
            ("État budgétaire", ["CDF", "Financement", "BI", "Montant alloué", "Réservé", "Engagé", "Solde transferts", "Disponible"],
             ((row["cdf"], row["funding"], row["product"], *(Decimal(row[key]) for key in ("allocated", "reserved", "committed", "transfers", "available"))) for row in state["rows"])),
            ("Contexte", ["Année", "Version", "État", "Date demandée", "Date de l’état", "Auteur", "Événement"],
             [(selected.state["year"], state["label"], state["status"], form.cleaned_data["at"], selected.created_at, selected.actor, selected.display_reason)])]
        if export_scope == "all":
            sheets.append(("Chronologie", ["Date", "Auteur", "Événement"], ((e.created_at, e.actor, e.display_reason) for e in timeline)))
        return excel.response("etat-budgetaire" if export_scope == "state" else "historique-budgetaire", sheets)
    return render(request, "purchasing/budget_history.html", {"form": form, "state": state,
        "selected": selected, "first": first, "timeline": timeline, "version": version,
        "scoped_version": scoped_version})


class BudgetMovementsForm(BudgetVersionSelectionForm):
    product = forms.CharField(label="Produit budgétaire (BI)", required=False, max_length=200)
    cdf = forms.CharField(label="CDF", required=False, max_length=200)
    funding = forms.CharField(label="Financement", required=False, max_length=200)


@login_required
@require_http_methods(["GET"])
def budget_transactions(request):
    if not can_view_budget_history(request.user):
        raise PermissionDenied
    from budgeting.history import budget_movements, describe_timeline
    from budgeting.models import BudgetHistoryEvent

    data = request.GET.copy()
    if "version" not in data:
        latest = EnvelopeVersion.objects.filter(deleted_at__isnull=True).order_by("-envelope__year", "-pk").first()
        if latest:
            data["version"] = str(latest.pk)
    form = BudgetMovementsForm(data if data else None)
    context = {"form": form}
    if form.is_valid():
        version = form.cleaned_data["version"]
        events = [
            event for event in BudgetHistoryEvent.objects.filter(envelope_id=version.envelope_id).order_by("created_at", "pk").iterator()
            if str(version.pk) in event.state.get("versions", {})
        ]
        describe_timeline(events, version.pk)
        filters = {field: form.cleaned_data[field].casefold() for field in ("product", "cdf", "funding")}
        rows = [
            row for row in budget_movements(events, version.pk)
            if all(value in row[field].casefold() for field, value in filters.items())
        ]
        context.update(
            version=version, first=events[0] if events else None,
            page=Paginator(list(reversed(rows)), 50).get_page(request.GET.get("page")),
            debit=sum(row["debit"] for row in rows), credit=sum(row["credit"] for row in rows),
        )
    return render(request, "purchasing/budget_transactions.html", context)


AllocationFormSet = inlineformset_factory(EnvelopeVersion, Allocation,
    fields=("budget_product", "cost_center", "funding", "amount"), extra=3,
    labels={"budget_product": "BI / produit budgétaire", "cost_center": "CDF",
            "funding": "Financement", "amount": "Montant TVAC (€)"},
    widgets={"amount": BudgetAmountInput(attrs={"step": "0.01", "min": "0"})})


@login_required
@permission_required(MANAGER_PERMISSIONS, raise_exception=True)
@require_http_methods(["GET", "POST"])
def versions(request):
    form = VersionForm(request.POST if request.method == "POST" else None,
                       initial={"year": timezone.localdate().year})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                envelope, _ = AnnualEnvelope.objects.get_or_create(year=form.cleaned_data["year"])
                version = EnvelopeVersion.objects.create(envelope=envelope, label=form.cleaned_data["label"])
        except IntegrityError:
            # A concurrent creation may have passed the same form validation.
            if EnvelopeVersion.objects.filter(envelope__year=form.cleaned_data["year"]).annotate(
                    trimmed_label=Trim("label")).filter(trimmed_label__iexact=form.cleaned_data["label"]).exists():
                form.add_error("label", "Une version portant ce nom existe déjà pour cette année.")
            else:
                raise
        else:
            return redirect("purchasing:budget_version", pk=version.pk)
    return render(request, "purchasing/budget_versions.html", {
        "form": form})


@login_required
@permission_required(MANAGER_PERMISSIONS, raise_exception=True)
@require_http_methods(["GET", "POST"])
def version_detail(request, pk):
    version = get_object_or_404(EnvelopeVersion.objects.filter(deleted_at__isnull=True).select_related("envelope"), pk=pk)
    error = None
    search = request.GET.get("q", "").strip()
    all_lines = version.allocations.select_related("budget_product", "cost_center", "funding").order_by("pk")
    filtered = all_lines.filter(Q(budget_product__code__icontains=search) | Q(budget_product__label__icontains=search)) if search else all_lines
    if excel.requested(request):
        lines = filtered
        return excel.response("allocations-budgetaires", [
            ("Allocations", ["Année", "Version", "Code BI", "BI", "Code CDF", "CDF", "Code financement", "Financement", "Montant TVAC"],
             ((version.envelope.year, version.label, line.budget_product.code, line.budget_product.label, line.cost_center.code, line.cost_center.label, line.funding.code, line.funding.label, line.amount) for line in lines.iterator())),
            ("Version", ["Année", "Version", "Publication", "Blocage"], [(version.envelope.year, version.label, version.published_at, version.locked_at)])])
    page = Paginator(filtered, 25).get_page(request.GET.get("page"))
    page_lines = list(page.object_list)
    selected = all_lines.filter(pk__in=[line.pk for line in page_lines])
    formset = AllocationFormSet(instance=version, queryset=selected)
    query = {"q": search} if search else {}
    full_choices = request.GET.get("full_choices") == "1"
    if full_choices:
        query["full_choices"] = "1"
    if page.number > 1:
        query["page"] = page.number
    form_action = reverse("purchasing:budget_version", args=[pk]) + ("?" + urlencode(query) if query else "")
    if request.method == "POST":
        with transaction.atomic():
            # Match the lock order used by publication and purchase submission.
            AnnualEnvelope.objects.select_for_update().get(pk=version.envelope_id)
            version = EnvelopeVersion.objects.select_for_update().select_related("envelope").get(pk=pk)
            if request.POST.get("action") in ("lock", "unlock"):
                try:
                    change_state = lock_envelope if request.POST.get("action") == "lock" else unlock_envelope
                    change_state(actor=request.user, version_id=version.pk)
                    return redirect("purchasing:budget_version", pk=pk)
                except ValidationError as exc:
                    error = " · ".join(exc.messages)
            elif version.deleted_at:
                error = "Cette version a été supprimée et ne peut plus être modifiée."
            elif version.locked_at:
                error = "Cette version est bloquée et ne peut plus être modifiée."
            elif version.published_at and not version.editing_unlocked_at:
                error = "Cette version publiée est en lecture seule. Un administrateur système peut débloquer ses modifications."
            elif version.published_at and not request.user.is_superuser:
                raise PermissionDenied
            elif request.POST.get("action") == "publish":
                try:
                    activate_envelope(actor=request.user, version_id=version.pk)
                    return redirect("purchasing:budget_version", pk=pk)
                except ValidationError as exc:
                    error = " · ".join(exc.messages)
            else:
                formset = AllocationFormSet(request.POST, instance=version, queryset=selected)
                if formset.is_valid():
                    formset.save()
                    return redirect(form_action)
    can_edit = version.allocations_editable and (not version.published_at or request.user.is_superuser)
    choices = {}
    if can_edit:
        # Send each reference list once, rather than repeating it in every row.
        choices = {name: [("", "---------")] + [(obj.pk, str(obj)) for obj in formset.empty_form.fields[name].queryset]
                   for name in ("budget_product", "cost_center", "funding")}
        labels = {name: {str(key): label for key, label in options} for name, options in choices.items()}
        for form in formset:
            for name, options in choices.items():
                if full_choices:
                    form.fields[name].choices = options
                else:
                    value = str(form[name].value() or "")
                    selected_option = [(value, labels[name].get(value, "Valeur invalide"))] if value else []
                    form.fields[name].choices = [("", "---------")] + selected_option
                    form.fields[name].widget.attrs["data-allocation-reference"] = name
    context = {
        "version": version, "formset": formset, "error": error,
        "can_edit_allocations": can_edit, "reference_choices": choices if not full_choices else {},
        "full_choices": full_choices,
        "lines": page_lines, "page": page, "search": search, "form_action": form_action,
        "total": all_lines.aggregate(total=Sum("amount"))["total"] or Decimal(0),
        "filtered_total": filtered.aggregate(total=Sum("amount"))["total"] or Decimal(0)}
    template = "purchasing/budget_allocations_results.html" if request.method == "GET" and request.headers.get("X-Requested-With") == "XMLHttpRequest" else "purchasing/budget_version.html"
    return render(request, template, context)


class AllocationImportForm(forms.Form):
    file = forms.FileField(label="Fichier Excel", widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}))


@login_required
@permission_required(MANAGER_PERMISSIONS, raise_exception=True)
@require_http_methods(["GET", "POST"])
def allocation_import(request, pk):
    from .allocation_excel import parse_allocations, import_allocations, template_sheets
    from django.contrib import messages
    from django.http import JsonResponse
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    version = get_object_or_404(EnvelopeVersion.objects.filter(deleted_at__isnull=True).select_related("envelope"), pk=pk)
    if request.method == "GET" and request.GET.get("template") == "xlsx":
        return excel.response(f"modele-allocations-{version.envelope.year}-{version.pk}", template_sheets(version))
    form = AllocationImportForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            upload = form.cleaned_data["file"]
            rows = parse_allocations(upload, version)
            counts = import_allocations(actor=request.user, version_id=pk, rows=rows, filename=upload.name)
            message = (f"Import Excel terminé : {counts['created']} ligne(s) créée(s), "
                f"{counts['updated']} mise(s) à jour, {counts['unchanged']} inchangée(s).")
            if ajax:
                return JsonResponse({"ok": True, "message": message, "counts": counts})
            messages.success(request, message)
            return redirect("purchasing:budget_version", pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    if request.method == "POST" and ajax:
        errors = [str(error) for values in form.errors.values() for error in values]
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    return render(request, "purchasing/allocation_import.html", {"version": version, "form": form,
        "can_import": version.allocations_editable and (not version.published_at or request.user.is_superuser)})


@login_required
@permission_required("budgeting.delete_envelopeversion", raise_exception=True)
@require_http_methods(["GET", "POST"])
def version_delete(request, pk):
    version = get_object_or_404(EnvelopeVersion.objects.filter(deleted_at__isnull=True).select_related("envelope"), pk=pk)
    error = None
    can_delete = not (version.published_at or version.locked_at or version.envelope.active_version_id == version.pk or version.submission_set.exists() or version.transfers.exists())
    if request.method == "POST":
        try:
            delete_envelope_version(actor=request.user, version_id=pk)
            return redirect("purchasing:allocation_versions")
        except ValidationError as exc:
            error = " · ".join(exc.messages)
    return render(request, "purchasing/budget_version_delete.html", {
        "version": version, "can_delete": can_delete, "error": error, "allocation_count": version.allocations.count()})
