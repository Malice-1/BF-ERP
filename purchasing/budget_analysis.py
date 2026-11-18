from decimal import Decimal

from django import forms


DIMENSIONS = {"cdf": "CDF", "funding": "Financement", "product": "Produit budgétaire"}
AMOUNTS = ("allocated", "reserved", "committed", "transfers", "available")
CHART_COLORS = ("#2475ac", "#198674", "#ad6a12", "#8055ac", "#bc4f74", "#44784c", "#8b6044", "#697e91")


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


def _totals(rows):
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
        groups.append({"label": str(item), "url": "?" + params.urlencode(), **_totals(group_rows)})
    groups.sort(key=lambda group: (-group["available"], group["label"].casefold()))

    totals = _totals(rows)
    return {
        "totals": totals, "groups": groups, "dimension": DIMENSIONS[group_by],
        "charts": [
            {"title": "Soldes positifs", **_chart(groups, "positive", totals["positive"])},
            {"title": "Déficits à couvrir", **_chart(groups, "deficit", totals["deficit"])},
        ],
    }
