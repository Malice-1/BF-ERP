from collections import defaultdict
from datetime import date
from decimal import Decimal

from accounting.models import SupplierInvoice
from budgeting.models import TrainingActivity
from django.utils import timezone

from .budget_analysis import budget_totals
from .models import BudgetEntry, PurchaseOrder


ZERO = Decimal(0)
STAGES = {
    "validation": "En validation",
    "validated": "Validée, à commander",
    "open": "Commande ouverte",
    "invoiced": "Commande facturée",
    "ordered": "Commande au rapprochement indéterminé",
}


def elapsed_percent(year, today):
    if year != today.year:
        return Decimal(100) if year < today.year else ZERO
    start, end = date(year, 1, 1), date(year, 12, 31)
    return Decimal(100) * ((today - start).days + 1) / ((end - start).days + 1)


def budget_metrics(rows, elapsed):
    totals = budget_totals(rows)
    granted = totals["allocated"] + totals["transfers"]
    rate = totals["committed"] * 100 / granted if granted > 0 else None
    return dict(totals, granted=granted, rate=rate,
        bar=max(ZERO, min(Decimal(100), rate or ZERO)),
        underused=bool(rate is not None and elapsed >= 50 and elapsed - rate >= 15 and totals["available"] > 0))


def _matched_invoices(orders):
    by_number = {order.number: order for order in orders}
    amounts = defaultdict(Decimal)
    invoices = SupplierInvoice.objects.filter(
        status="REVIEWED", currency="EUR", total__isnull=False,
        extracted_data__order_reference__in=list(by_number),
    ).values_list("extracted_data__order_reference", "supplier_id", "total")
    for number, supplier_id, total in invoices.iterator():
        order = by_number[number]
        if supplier_id == order.purchase_request.supplier_id:
            amounts[order.pk] += total
    return amounts


def purchase_activity(version, cdf, user, today):
    entries = BudgetEntry.objects.filter(
        snapshot__submission__budget_version__envelope_id=version.envelope_id,
        state__in=("reserved", "committed"),
    ).select_related("snapshot__submission__purchase_request", "snapshot__budget_product").prefetch_related("snapshot__steps")
    grouped = defaultdict(list)
    for entry in entries.iterator(chunk_size=500):
        grouped[entry.snapshot.submission_id].append(entry)
    orders = {order.submission_id: order for order in PurchaseOrder.objects.filter(
        submission__budget_version__envelope_id=version.envelope_id,
    ).select_related("purchase_request")}
    can_match = user.has_perm("accounting.view_supplierinvoice")
    candidates = [
        order for submission_id, order in orders.items()
        if grouped.get(submission_id) and all(
            cdf is None or entry.snapshot.cost_center_id == cdf.pk for entry in grouped[submission_id]
        )
    ]
    invoiced = _matched_invoices(candidates) if can_match and candidates else {}
    matchable = {order.pk for order in candidates} if can_match else set()
    purchases, suppliers, supplier_labels, stages = [], defaultdict(Decimal), {}, defaultdict(Decimal)
    for submission_id, all_entries in grouped.items():
        scoped = [entry for entry in all_entries if cdf is None or entry.snapshot.cost_center_id == cdf.pk]
        if not scoped:
            continue
        submission = scoped[0].snapshot.submission
        purchase = submission.purchase_request
        order = orders.get(submission_id)
        amount = sum(entry.amount for entry in scoped)
        committed = sum((entry.amount for entry in scoped if entry.state == "committed"), ZERO)
        supplier_data = order.supplier_data if order else submission.supplier_data
        supplier = supplier_data.get("name") or supplier_data.get("code") or "Fournisseur non renseigné"
        suppliers[purchase.supplier_id] += committed
        supplier_labels[purchase.supplier_id] = supplier
        created = timezone.localdate(order.created_at if order else submission.created_at)
        age = max(0, (today - created).days)
        steps = [step for entry in scoped for step in entry.snapshot.steps.all()]
        waiting = sorted({step.function_label for step in steps if step.state in ("pending", "unassigned", "blocked")})
        billed = remaining = None
        if order and order.pk in matchable:
            billed = invoiced.get(order.pk, ZERO)
            remaining = max(ZERO, amount - billed)
            stage = "open" if remaining > 0 else "invoiced"
            stages["open"] += remaining
            stages["invoiced"] += min(max(ZERO, billed), amount)
        else:
            stage = "ordered" if order else "validated" if steps and all(
                step.state == "approved" for step in steps
            ) else "validation"
            stages[stage] += amount
        purchases.append(dict(
            pk=purchase.pk, created=created, age=age, request_number=purchase.number,
            order_number=order.number if order else "", stage=stage, stage_label=STAGES[stage],
            amount=amount, billed=billed, remaining=remaining, supplier=supplier, waiting=waiting,
            products=sorted({entry.snapshot.data.get("product") or str(entry.snapshot.budget_product) for entry in scoped}),
            overdue=stage == "open" and age > 90,
        ))
    top = sorted(((supplier_labels[pk], amount) for pk, amount in suppliers.items() if amount > 0),
        key=lambda item: (-item[1], item[0].casefold()))[:10]
    return dict(rows=purchases, stages=[(label, stages[key]) for key, label in STAGES.items()],
        suppliers=top, can_match=can_match)


def training_activity(year, cdf, today):
    entries = TrainingActivity.objects.filter(month__year=year, month__lte=today).select_related("training")
    if cdf:
        entries = entries.filter(cost_center=cdf)
    months, courses = {}, {}
    fields = ("trainees", "hours", "sessions")
    totals = dict.fromkeys(fields, 0)
    for entry in entries.order_by("month", "training__code"):
        month = months.setdefault(entry.month, dict.fromkeys(fields, 0))
        course = courses.setdefault(entry.training, dict.fromkeys(fields, 0))
        for key in fields:
            value = getattr(entry, key)
            totals[key] += value
            month[key] += value
            course[key] += value
    return dict(totals=totals, months=months.items(), courses=courses.items())
