"""Dated budget states, captured in the transaction that changes the budget."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from django.utils.numberformat import format as number_format
from django.db import connections, transaction
from django.db.models.signals import post_save, post_delete, post_migrate
from purchasing.models import AnnualEnvelope, EnvelopeVersion, Allocation, BudgetEntry
from .models import BudgetHistoryEvent, BudgetTransfer


def capture(envelope_id, reason, actor=None, using="default", version_id=None, change=None):
    envelope = AnnualEnvelope.objects.using(using).filter(pk=envelope_id).first()
    if envelope is None:
        return
    from workflow.activity import current_actor
    actor = actor or current_actor.get()
    entries = defaultdict(lambda: {"reserved": Decimal(0), "committed": Decimal(0)})
    labels = {}

    def combination(obj, prefix=""):
        names = ("cost_center", "funding", "budget_product") if not prefix else (prefix + "_cdf", prefix + "_funding", prefix + "_product")
        key = tuple(getattr(obj, name + "_id") for name in names)
        labels[key] = [str(getattr(obj, name)) for name in names]
        return key

    for entry in BudgetEntry.objects.using(using).filter(
            snapshot__submission__budget_version__envelope_id=envelope_id,
            state__in=["reserved", "committed"]).select_related(
                "snapshot__cost_center", "snapshot__funding", "snapshot__budget_product"):
        entries[combination(entry.snapshot)][entry.state] += entry.amount
    transfers_by_version = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    for transfer in BudgetTransfer.objects.using(using).filter(envelope_id=envelope_id, status__in=["pending", "approved"]).select_related(
            "source_cdf", "source_funding", "source_product", "destination_cdf", "destination_funding", "destination_product"):
        transfers_by_version[transfer.budget_version_id][combination(transfer, "source")] -= transfer.amount
        if transfer.status == "approved":
            transfers_by_version[transfer.budget_version_id][combination(transfer, "destination")] += transfer.amount
    versions = {}
    for version in EnvelopeVersion.objects.using(using).filter(envelope_id=envelope_id):
        transfers = transfers_by_version[version.pk]
        allocations = {}
        for allocation in version.allocations.using(using).select_related("cost_center", "funding", "budget_product"):
            allocations[combination(allocation)] = allocation.amount
        rows = []
        for key in sorted(set(allocations) | set(entries) | set(transfers)):
            allocated = allocations.get(key, Decimal(0))
            reserved, committed = entries[key]["reserved"], entries[key]["committed"]
            rows.append(dict(zip(("cdf", "funding", "product"), labels[key]),
                             allocated=str(allocated), reserved=str(reserved), committed=str(committed),
                             transfers=str(transfers[key]), available=str(allocated-reserved-committed+transfers[key])))
        versions[str(version.pk)] = {"label": version.label,
            "editing_unlocked_at": version.editing_unlocked_at.isoformat() if version.editing_unlocked_at else None,
            "status": "Supprimée" if version.deleted_at else "Bloquée" if version.locked_at else "Active" if envelope.active_version_id == version.pk else "Publiée remplacée" if version.published_at else "Brouillon",
            "rows": rows}
    return BudgetHistoryEvent.objects.using(using).create(envelope_id=envelope_id,
        version_id=version_id,
        actor=actor.get_username() if actor else "Système", reason=reason,
        state={"year": envelope.year, "versions": versions, "change": change})


def allocation_description(change):
    action = {"added": "Produit ajouté", "updated": "Produit modifié", "removed": "Produit supprimé"}[change["kind"]]
    value = format(Decimal(change["amount"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    amount = number_format(value, decimal_sep=",", grouping=3, thousand_sep=".", force_grouping=True)
    return f"{action} : {change['product']} · montant : {amount} € · CDF : {change['cdf']} · financement : {change['funding']}"


def describe_timeline(events, version_id):
    """Explain recorded changes without modifying immutable historical events."""
    previous = {}
    for event in events:
        current = event.state.get("versions", {}).get(str(version_id), {})
        change = event.state.get("change")
        event.display_reason = event.reason.replace(" TVAC", "")
        if change and change.get("version_id") == version_id:
            event.display_reason = allocation_description(change)
        elif event.reason.casefold().startswith("allocation"):
            # Old entries have only a generic label; recover an unambiguous
            # allocation change from their preserved before/after snapshots.
            old = {(r["cdf"], r["funding"], r["product"]): r for r in previous.get("rows", [])}
            new = {(r["cdf"], r["funding"], r["product"]): r for r in current.get("rows", [])}
            changed = [key for key in old.keys() | new.keys()
                       if Decimal(old.get(key, {}).get("allocated", "0")) != Decimal(new.get(key, {}).get("allocated", "0"))]
            if len(changed) == 1:
                key = changed[0]
                row = new.get(key, old.get(key))
                event.display_reason = allocation_description({
                    "kind": "added" if key not in old else "removed" if key not in new else "updated",
                    "product": row["product"], "cdf": row["cdf"], "funding": row["funding"],
                    "amount": row["allocated"],
                })
        previous = current


def changed(sender, instance, using, raw=False, created=False, signal=None, **kwargs):
    if raw:
        return
    model = sender._meta.concrete_model
    change = None
    if model is AnnualEnvelope:
        envelope_id = instance.pk
    elif model in (EnvelopeVersion, BudgetTransfer):
        envelope_id = instance.envelope_id
    elif model is Allocation:
        envelope_id = instance.version.envelope_id
        change = dict(kind="removed" if signal is post_delete else "added" if created else "updated",
                      version_id=instance.version_id, product=str(instance.budget_product),
                      cdf=str(instance.cost_center), funding=instance.funding.code, amount=str(instance.amount))
    elif model is BudgetEntry:
        envelope_id = instance.snapshot.submission.budget_version.envelope_id
    else:
        return
    default_reason = allocation_description(change)[:200] if change else f"{instance._meta.verbose_name} · {instance.pk}"
    capture(envelope_id, getattr(instance, "_history_reason", default_reason),
            actor=getattr(instance, "_history_actor", None), using=using,
            version_id=instance.pk if model is EnvelopeVersion else instance.version_id if model is Allocation else instance.budget_version_id if model is BudgetTransfer else None,
            change=change)


def connect():
    # A global receiver also handles the budgeting proxy models.
    post_save.connect(changed, dispatch_uid="budget_history_save")
    post_delete.connect(changed, dispatch_uid="budget_history_delete")
    post_migrate.connect(initialize_after_migrate, dispatch_uid="budget_history_initialize")


def initialize(using="default"):
    count = 0
    for pk in AnnualEnvelope.objects.using(using).values_list("pk", flat=True):
        with transaction.atomic(using=using):
            AnnualEnvelope.objects.using(using).select_for_update().get(pk=pk)
            if not BudgetHistoryEvent.objects.using(using).filter(envelope_id=pk).exists():
                capture(pk, "État initial lors de l’activation de l’historique", using=using)
                count += 1
    return count


def initialize_after_migrate(sender, using, **kwargs):
    if sender.name == "budgeting" and BudgetHistoryEvent._meta.db_table in connections[using].introspection.table_names():
        initialize(using)
