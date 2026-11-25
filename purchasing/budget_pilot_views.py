from collections import defaultdict
from urllib.parse import urlencode

from django import forms
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from budgeting.models import CostCenter, TrainingActivity
from .budget_analysis import balance_rows
from .budget_pilot import STAGES, ZERO, budget_metrics, elapsed_percent, purchase_activity, training_activity
from .forms import BudgetVersionSelectionForm
from .models import AnnualEnvelope


class PilotScopeForm(BudgetVersionSelectionForm):
    cdf = forms.ModelChoiceField(label="Centre de frais (CDF)", queryset=CostCenter.objects.all(), required=False,
        empty_label="Tous les CDF")


class PurchaseFilter(forms.Form):
    stage = forms.ChoiceField(label="Statut", required=False, choices=[("", "Tous les statuts"), *STAGES.items()])
    search = forms.CharField(label="Fournisseur, produit ou numéro", required=False, max_length=200)
    order = forms.ChoiceField(label="Trier", required=False,
        choices=[("", "Plus récents"), ("age", "Plus anciens")])
    overdue = forms.BooleanField(label="Commandes ouvertes depuis plus de 90 jours", required=False)


def _budget_url(version, cdf, **filters):
    return "?" + urlencode(dict(version=version.pk, cdf=cdf.pk if cdf else "", **filters))


def _bars(items):
    maximum = max((value for _, value in items), default=ZERO)
    return [(name, value, value * 100 / maximum if maximum > 0 else ZERO) for name, value in items]


def _annual_history(versions, selected, cdf, today, balances, show_training):
    by_year = defaultdict(list)
    for version in versions.filter(published_at__isnull=False).order_by("envelope__year", "published_at", "pk"):
        by_year[version.envelope.year].append(version)
    if selected not in by_year[selected.envelope.year]:
        by_year[selected.envelope.year].append(selected)
    hours_by_year = {}
    if show_training:
        activity = TrainingActivity.objects.filter(month__lte=today)
        if cdf:
            activity = activity.filter(cost_center=cdf)
        hours_by_year = dict(activity.values("month__year").annotate(total=Sum("hours")).values_list("month__year", "total"))
    rows = []
    for year, published in sorted(by_year.items()):
        initial = next((item for item in published if item.published_at), None)
        opening = initial.allocations.all() if initial else None
        if cdf and opening is not None:
            opening = opening.filter(cost_center=cdf)
        active = next((item for item in published if item.pk == item.envelope.active_version_id), None)
        active = active or next((item for item in reversed(published) if item.published_at), published[-1])
        metrics = budget_metrics(balances(active), elapsed_percent(year, today))
        rows.append(dict(year=year, opening=(opening.aggregate(total=Sum("amount"))["total"] or ZERO) if opening is not None else None,
            hours=hours_by_year.get(year), url=_budget_url(active, cdf), **metrics))
    return rows


@login_required
@permission_required("budgeting.view_budget_balances", raise_exception=True)
@require_GET
@never_cache
def budget_pilot(request):
    today = timezone.localdate()
    data = request.GET.copy()
    versions = PilotScopeForm().fields["version"].queryset
    if not data.get("version"):
        active_ids = AnnualEnvelope.objects.values("active_version_id")
        active = versions.filter(pk__in=active_ids)
        default = active.filter(envelope__year=today.year).first() or active.first() or versions.first()
        if default:
            data["version"] = str(default.pk)
    show_purchases = request.user.has_perm("purchasing.view_purchase_financial")
    show_training = request.user.has_perm("budgeting.view_trainingactivity")
    tabs = {"budget": "Synthèse", "history": "Comparaison annuelle"}
    if show_purchases:
        tabs["purchases"] = "Achats et factures"
    if show_training:
        tabs["training"] = "Formations"
    tab = data.get("tab", "budget")
    if tab not in tabs:
        tab = "budget"
    form = PilotScopeForm(data if data else None)
    context = dict(form=form, tab=tab, today=today)
    if form.is_valid():
        version, cdf = form.cleaned_data["version"], form.cleaned_data["cdf"]

        def balances(item):
            return [row for row in balance_rows(item) if cdf is None or row["cdf"] == cdf]

        rows = balances(version)
        year = version.envelope.year
        elapsed = elapsed_percent(year, today)
        metrics = budget_metrics(rows, elapsed)
        dimension = "product" if cdf else "cdf"
        grouped = defaultdict(list)
        for row in rows:
            grouped[row[dimension]].append(row)
        groups = []
        for item, items in grouped.items():
            if cdf:
                url = reverse("purchasing:budgets") + _budget_url(version, cdf, product=item.pk, group_by="funding")
            else:
                url = _budget_url(version, item) + "#postes"
            groups.append(dict(label=item, url=url, **budget_metrics(items, elapsed)))
        groups.sort(key=lambda group: (group["available"], str(group["label"]).casefold()))
        activity = purchase_activity(version, cdf, request.user, today) if show_purchases and tab in ("budget", "purchases") else None
        purchases = activity["rows"] if activity else []
        training = training_activity(year, cdf, today) if tab == "training" else None
        waiting = [row for row in purchases if row["stage"] == "validation"]
        overdue = [row for row in purchases if row["overdue"]]
        context.update(
            version=version, cdf=cdf, tabs=[(key, label, _budget_url(version, cdf, tab=key)) for key, label in tabs.items()],
            metrics=metrics, elapsed=elapsed, groups=groups, dimension=dimension,
            deficit_groups=[group for group in groups if group["deficit"]],
            underused_groups=[group for group in groups if group["underused"]],
            activity=activity, waiting_count=len(waiting), waiting_amount=sum((row["amount"] for row in waiting), ZERO),
            overdue_count=len(overdue), overdue_amount=sum((row["remaining"] for row in overdue), ZERO),
            waiting_url=_budget_url(version, cdf, tab="purchases", stage="validation"),
            overdue_url=_budget_url(version, cdf, tab="purchases", overdue=1, order="age"),
            training=training, show_training=show_training,
        )
        if training:
            hours = training["totals"]["hours"]
            context.update(cost_per_hour=metrics["committed"] / hours if hours else None,
                training_hours=_bars([(month.strftime("%m/%Y"), item["hours"]) for month, item in training["months"]]),
                training_trainees=_bars([(month.strftime("%m/%Y"), item["trainees"]) for month, item in training["months"]]))
        if tab == "purchases":
            transfers = version.transfers.filter(status__in=("approved", "pending"))
            if cdf:
                transfers = transfers.filter(Q(source_cdf=cdf) | Q(destination_cdf=cdf))
            transfers = transfers.select_related(
                "source_cdf", "source_product", "destination_cdf", "destination_product",
            ).order_by("-created_at", "-pk")
            filters = PurchaseFilter(data)
            if filters.is_valid():
                choices = filters.cleaned_data
                terms = choices["search"].casefold().split()
                purchases = [
                    row for row in purchases
                    if (not choices["stage"] or row["stage"] == choices["stage"])
                    and (not choices["overdue"] or row["overdue"])
                    and all(term in " ".join((row["supplier"], row["request_number"], row["order_number"], *row["products"])).casefold() for term in terms)
                ]
                purchases.sort(key=lambda row: (row["created"], row["pk"]), reverse=choices["order"] != "age")
            else:
                purchases = []
            context.update(purchase_filters=filters, page=Paginator(purchases, 30).get_page(data.get("page")),
                stage_bars=_bars(activity["stages"]), supplier_bars=_bars(activity["suppliers"]),
                recent_transfers=transfers[:10])
        if tab == "history":
            history = _annual_history(versions, version, cdf, today, balances, show_training)
            context.update(history=history, history_grants=_bars([(item["year"], max(ZERO, item["granted"])) for item in history]),
                history_engaged=_bars([(item["year"], item["committed"]) for item in history]),
                history_hours=_bars([(item["year"], item["hours"]) for item in history if item["hours"] is not None]))
    return render(request, "purchasing/budget_pilot.html", context)
