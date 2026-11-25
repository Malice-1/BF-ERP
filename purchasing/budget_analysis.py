from decimal import Decimal

from django import forms


DIMENSIONS = {"cdf": "CDF", "funding": "Financement", "product": "Produit budgétaire"}
AMOUNTS = ("allocated", "reserved", "committed", "transfers", "available")
CHART_COLORS = ("#2475ac", "#198674", "#ad6a12", "#8055ac", "#bc4f74", "#44784c", "#8b6044", "#697e91")


def balance_rows(version):
    from budgeting.models import BudgetProduct, CostCenter, Funding
    from budgeting.transfers import transfer_balances
    from .models import BudgetEntry

    allocations = {
        (item.cost_center_id, item.funding_id, item.budget_product_id): item.amount
        for item in version.allocations.all()
    }
    transfers = transfer_balances(version.pk)
    entries = {}
    # Sum the original decimals in Python, including on SQLite.
    for cdf, funding, product, state, amount in BudgetEntry.objects.filter(
        snapshot__submission__budget_version__envelope_id=version.envelope_id,
        state__in=("reserved", "committed"),
    ).values_list(
        "snapshot__cost_center_id", "snapshot__funding_id", "snapshot__budget_product_id", "state", "amount",
    ).iterator():
        amounts = entries.setdefault((cdf, funding, product), {})
        amounts[state] = amounts.get(state, Decimal(0)) + amount
    combinations = sorted(allocations.keys() | entries.keys() | transfers.keys())
    cdfs = CostCenter.objects.in_bulk(key[0] for key in combinations)
    fundings = Funding.objects.in_bulk(key[1] for key in combinations)
    products = BudgetProduct.objects.in_bulk(key[2] for key in combinations)
    rows = []
    for key in combinations:
        cdf, funding, product = key
        allocated = allocations.get(key, Decimal(0))
        reserved = entries.get(key, {}).get("reserved", Decimal(0))
        committed = entries.get(key, {}).get("committed", Decimal(0))
        moved = transfers.get(key, Decimal(0))
        rows.append(dict(
            year=version.envelope.year, version=version.label, cdf=cdfs[cdf],
            funding=fundings[funding], product=products[product], allocated=allocated,
            reserved=reserved, committed=committed, transfers=moved,
            available=allocated + moved - reserved - committed,
        ))
    return rows


class BudgetAnalysisForm(forms.Form):
    status = forms.MultipleChoiceField(
        label="Solde", required=False, widget=forms.CheckboxSelectMultiple,
        choices=[("positive", "Positif"), ("deficit", "Déficitaire"), ("zero", "Nul")],
    )
    group_by = forms.ChoiceField(label="Regrouper par", required=False, choices=list(DIMENSIONS.items()))

    def __init__(self, data, rows):
        data = data.copy()
        for key in (*DIMENSIONS, "status"):
            if key in data:
                data.setlist(key, [value for value in data.getlist(key) if value])
        super().__init__(data)
        for key, label in DIMENSIONS.items():
            options = {row[key].pk: str(row[key]) for row in rows}
            ordered = sorted(options.items(), key=lambda option: option[1].casefold())
            self.fields[key] = forms.TypedMultipleChoiceField(
                label=label, choices=ordered, coerce=int, required=False,
                widget=forms.CheckboxSelectMultiple,
            )
        self.order_fields([*DIMENSIONS, "status", "group_by"])

    def filter_rows(self, rows):
        dimensions = {key: set(self.cleaned_data[key]) for key in DIMENSIONS if self.cleaned_data[key]}
        rows = [row for row in rows if all(row[key].pk in selected for key, selected in dimensions.items())]
        statuses = set(self.cleaned_data["status"])
        if statuses:
            status_by_sign = {-1: "deficit", 0: "zero", 1: "positive"}
            rows = [row for row in rows if status_by_sign[row["available"].compare(0)] in statuses]
        return rows


def budget_totals(rows):
    totals = {key: sum((row[key] for row in rows), Decimal(0)) for key in AMOUNTS}
    totals["positive"] = sum((row["available"] for row in rows if row["available"] > 0), Decimal(0))
    totals["deficit"] = -sum((row["available"] for row in rows if row["available"] < 0), Decimal(0))
    return totals


def _chart(groups, key, total):
    ranked = sorted((group for group in groups if group[key] > 0), key=lambda group: -group[key])
    if len(ranked) > len(CHART_COLORS):
        limit = len(CHART_COLORS) - 1
        other = {"label": "Autres", key: sum(group[key] for group in ranked[limit:])}
        ranked = [*ranked[:limit], other]
    segments = []
    cumulative = Decimal(0)
    for group, color in zip(ranked, CHART_COLORS):
        amount = group[key]
        start = cumulative / total * 100
        cumulative += amount
        segments.append({
            "label": group["label"], "url": group.get("url"), "amount": amount, "color": color,
            "start": start, "end": cumulative / total * 100, "share": amount / total * 100,
        })
    return {"total": total, "segments": segments}


def summarize(rows, group_by, query):
    grouped = {}
    for row in rows:
        item = row[group_by]
        grouped.setdefault(item, []).append(row)

    groups = []
    for item, group_rows in grouped.items():
        params = query.copy()
        params[group_by] = item.pk
        groups.append({"label": str(item), "url": "?" + params.urlencode(), **budget_totals(group_rows)})
    groups.sort(key=lambda group: (-group["available"], group["label"].casefold()))

    totals = budget_totals(rows)
    return {
        "totals": totals, "groups": groups, "dimension": DIMENSIONS[group_by],
        "charts": [
            {"title": "Soldes positifs", **_chart(groups, "positive", totals["positive"])},
            {"title": "Déficits à couvrir", **_chart(groups, "deficit", totals["deficit"])},
        ],
    }
