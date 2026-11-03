"""Explicit, previewable maintenance deletion for the system superuser."""
from collections import defaultdict, deque

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import connections, models, router, transaction
from django.urls import reverse
from django.utils.html import format_html


def deletion_plan(queryset):
    """Follow required dependents; detach optional references; retain the journal."""
    alias = queryset.db
    planned = defaultdict(set)
    detached = defaultdict(set)
    queue = deque([(queryset.model._meta.concrete_model, set(queryset.values_list("pk", flat=True)))])
    while queue:
        model, keys = queue.popleft()
        if model._meta.label_lower == "workflow.activitylog":
            raise PermissionDenied("Le journal des actions ne peut pas être supprimé.")
        fresh = keys - planned[model]
        if not fresh:
            continue
        planned[model].update(fresh)
        for relation in model._meta.get_fields(include_hidden=True):
            if not relation.auto_created or relation.concrete or not (relation.one_to_many or relation.one_to_one):
                continue
            child, field = relation.related_model, relation.field
            ids = set(child._base_manager.using(alias).filter(
                **{field.attname + "__in": fresh}).values_list("pk", flat=True))
            if not ids:
                continue
            if field.null and field.remote_field.on_delete is not models.CASCADE:
                detached[(child, field.attname)].update(ids)
            else:
                queue.append((child, ids))
    return planned, detached


def interrupted_submissions(planned, alias):
    from purchasing.models import ApprovalStep, BudgetEntry, LineSnapshot, PurchaseRequestLine, Submission
    ids = set(planned.get(Submission, set()))
    for model in (ApprovalStep, BudgetEntry):
        ids.update(model.objects.using(alias).filter(pk__in=planned.get(model, set())).values_list(
            "snapshot__submission_id", flat=True))
    ids.update(LineSnapshot.objects.using(alias).filter(pk__in=planned.get(LineSnapshot, set())).values_list("submission_id", flat=True))
    ids.update(LineSnapshot.objects.using(alias).filter(line_id__in=planned.get(PurchaseRequestLine, set())).values_list("submission_id", flat=True))
    return Submission.objects.using(alias).filter(pk__in=ids, active=True)


def delete_as_superuser(queryset, actor):
    from workflow.activity import current_actor, snapshot, write_log

    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied
    alias = queryset.db
    with transaction.atomic(using=alias):
        # Serialize maintenance operations; normal FK checks remain enabled.
        if connections[alias].vendor == "postgresql":
            with connections[alias].cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(104211, 1)")
        list(queryset.select_for_update())
        planned, detached = deletion_plan(queryset)
        # Lock all affected existing rows before writing snapshots.
        for model, keys in planned.items():
            list(model._base_manager.using(alias).filter(pk__in=keys).order_by("pk").select_for_update())
        token = current_actor.set(actor)
        try:
            for model, keys in planned.items():
                if not model._meta.auto_created:
                    for obj in model._base_manager.using(alias).filter(pk__in=keys):
                        write_log(obj, "maintenance.deleted", {"before": snapshot(obj)}, alias, actor=actor)
            for (model, field), keys in detached.items():
                remaining = keys - planned.get(model, set())
                for obj in model._base_manager.using(alias).filter(pk__in=remaining):
                    write_log(obj, "maintenance.detached", {
                        "field": field, "previous_value": getattr(obj, field), "new_value": None,
                    }, alias, actor=actor)
            previous = None
            if connections[alias].vendor == "postgresql":
                with connections[alias].cursor() as cursor:
                    cursor.execute("SELECT current_setting('bf_erp.maintenance_delete', true)")
                    previous = cursor.fetchone()[0] or ""
                    cursor.execute("SELECT set_config('bf_erp.maintenance_delete', 'on', true)")
            from purchasing.models import ApprovalRule, ApprovalStep, BudgetEntry, PurchaseRequest
            for submission in interrupted_submissions(planned, alias):
                write_log(submission, "maintenance.workflow_stopped", {
                    "purchase_request_id": submission.purchase_request_id,
                    "reason": "Suppression d'une donnée du circuit ; réservations libérées et correction requise.",
                }, alias, actor=actor)
                submission.active = False
                # Queryset update intentionally scoped to this maintenance transaction.
                type(submission).objects.using(alias).filter(pk=submission.pk).update(active=False)
                BudgetEntry.objects.using(alias).filter(snapshot__submission=submission, state="reserved").update(state="released")
                PurchaseRequest.objects.using(alias).filter(pk=submission.purchase_request_id,
                    status="SUBMITTED").update(status="CORRECTION")
            for (model, field), keys in detached.items():
                remaining = model._base_manager.using(alias).filter(pk__in=keys - planned.get(model, set()))
                if model is ApprovalRule and field in {"role_id", "cost_center_id", "funding_id", "budget_product_id"}:
                    remaining.update(named_user_reference=f"[référence supprimée: {field}]")
                if model is ApprovalStep and field == "role_id":
                    for step in remaining.exclude(state="approved"):
                        step.candidates.clear()
                remaining.update(**{field: None})
            # FKs are deferred by Django on both supported databases. Delete the
            # whole previewed graph within this transaction, not unrelated rows.
            for model, keys in reversed(list(planned.items())):
                model._base_manager.using(alias).filter(pk__in=keys)._raw_delete(alias)
            if previous is not None:
                with connections[alias].cursor() as cursor:
                    cursor.execute("SELECT set_config('bf_erp.maintenance_delete', %s, true)", [previous])
        finally:
            current_actor.reset(token)


class SystemDeletionMixin:
    def get_list_display(self, request):
        columns = super().get_list_display(request)
        if request.user.is_superuser and self.has_delete_permission(request):
            return (*columns, "system_delete_link")
        return columns

    @admin.display(description="Suppression")
    def system_delete_link(self, obj):
        return format_html('<a href="{}">Supprimer</a>', reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_delete", args=[obj.pk]))

    def has_delete_permission(self, request, obj=None):
        if request.user.is_active and request.user.is_superuser:
            return True
        return super().has_delete_permission(request, obj)

    def get_deleted_objects(self, objs, request):
        if not request.user.is_superuser:
            return super().get_deleted_objects(objs, request)
        alias = router.db_for_write(self.model)
        queryset = self.model._base_manager.using(alias).filter(pk__in=[obj.pk for obj in objs])
        planned, detached = deletion_plan(queryset)
        rows = ["Suppression de maintenance : les dépendances obligatoires ci-dessous seront également supprimées. Les références facultatives seront détachées. Les traces du journal seront conservées. Les règles privées d'une référence ne seront plus applicables tant qu'elles ne sont pas remplacées."]
        for submission in interrupted_submissions(planned, alias):
            rows.append(f"Arrêter le cycle de {submission.purchase_request} : libérer ses réservations et retourner la DA soumise en correction.")
        counts = {}
        for model, keys in planned.items():
            if model._meta.auto_created:
                continue
            counts[str(model._meta.verbose_name_plural)] = len(keys)
            rows.extend(f"Supprimer — {model._meta.verbose_name} : {obj}" for obj in model._base_manager.using(alias).filter(pk__in=keys))
        for (model, field), keys in detached.items():
            remaining = keys - planned.get(model, set())
            if remaining:
                rows.append(f"Détacher — {model._meta.verbose_name_plural} : {len(remaining)} référence(s), champ {field}")
        return rows, counts, set(), []

    def delete_model(self, request, obj):
        if request.user.is_superuser:
            return delete_as_superuser(self.model._base_manager.using(
                router.db_for_write(self.model)).filter(pk=obj.pk), request.user)
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        if request.user.is_superuser:
            return delete_as_superuser(queryset, request.user)
        return super().delete_queryset(request, queryset)


class SystemModelAdmin(SystemDeletionMixin, admin.ModelAdmin):
    pass
