from contextvars import ContextVar

from django.db.models.signals import post_save, pre_save, pre_delete, m2m_changed

from .models import ActivityLog


current_actor = ContextVar("activity_actor", default=None)
BUSINESS_APPS = {"accounts", "budgeting", "purchasing", "suppliers"}
EXCLUDED_FIELDS = {"password", "last_login"}


def identity(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return "system", "Système"
    return str(user.pk), user.get_username()


def snapshot(instance):
    return {field.attname: field.value_to_string(instance)
            for field in instance._meta.concrete_fields
            if field.name not in EXCLUDED_FIELDS}


def write_log(instance, action, details, using, actor=None, source=None):
    identifier, username = identity(actor if actor is not None else current_actor.get())
    ActivityLog.objects.using(using).create(
        actor_identifier=identifier, actor_username=username, action=action,
        object_type=instance._meta.label_lower, object_identifier=str(instance.pk),
        details=details, source=source,
    )


def before_save(sender, instance, using, raw=False, **kwargs):
    if raw or sender._meta.app_label not in BUSINESS_APPS:
        return
    old = sender.objects.using(using).filter(pk=instance.pk).first() if instance.pk else None
    instance._activity_before = snapshot(old) if old else None


def after_save(sender, instance, created, using, raw=False, **kwargs):
    if raw:
        return
    if sender._meta.label_lower == "admin.logentry":
        if created:
            write_log(instance, {1: "admin.created", 2: "admin.updated", 3: "admin.deleted"}.get(
                instance.action_flag, "admin.action"), {
                    "object_type": str(instance.content_type), "object_id": instance.object_id,
                    "label": instance.object_repr, "message": instance.change_message,
                }, using, actor=instance.user, source=f"admin.logentry:{instance.pk}")
        return
    if sender._meta.label_lower in {"workflow.auditevent", "workflow.configurationauditevent"}:
        if created:
            details = {"payload": instance.payload}
            if hasattr(instance, "purchase_request_id"):
                details.update(purchase_request_id=instance.purchase_request_id, revision=instance.revision)
            else:
                details.update(object_type=instance.object_type, object_id=instance.object_id)
            write_log(instance, instance.action, details, using,
                      actor=False if instance.payload.get("origin") == "system" else instance.actor,
                      source=f"{sender._meta.label_lower}:{instance.pk}")
        return
    if sender._meta.app_label not in BUSINESS_APPS:
        return
    before = getattr(instance, "_activity_before", None)
    after = snapshot(instance)
    if before != after:
        write_log(instance, "created" if created else "updated", {"before": before, "after": after}, using)


def before_delete(sender, instance, using, **kwargs):
    if sender._meta.app_label in BUSINESS_APPS:
        details = {"before": snapshot(instance)}
        if sender._meta.label_lower == "accounts.user":
            # Record references before Django detaches nullable user relations.
            references = {}
            for relation in sender._meta.related_objects:
                if relation.one_to_many or relation.one_to_one:
                    ids = list(relation.related_model.objects.using(using).filter(
                        **{relation.field.attname: instance.pk}).values_list("pk", flat=True))
                    if ids:
                        references[f"{relation.related_model._meta.label_lower}.{relation.field.name}"] = ids
            details["references"] = references
        write_log(instance, "deleted", details, using)


def membership_changed(sender, instance, action, reverse, model, pk_set, using, **kwargs):
    if action not in {"post_add", "post_remove", "pre_clear"}:
        return
    if instance._meta.app_label not in BUSINESS_APPS:
        return
    write_log(instance, f"membership.{action}", {
        "relation": sender._meta.label_lower, "reverse": reverse,
        "related_model": model._meta.label_lower,
        "related_ids": sorted(pk_set) if pk_set is not None else None,
    }, using)


def connect():
    pre_save.connect(before_save, dispatch_uid="activity.before_save", weak=False)
    post_save.connect(after_save, dispatch_uid="activity.after_save", weak=False)
    pre_delete.connect(before_delete, dispatch_uid="activity.before_delete", weak=False)
    m2m_changed.connect(membership_changed, dispatch_uid="activity.membership", weak=False)


class ActivityActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current_actor.set(request.user if request.user.is_authenticated else None)
        try:
            return self.get_response(request)
        finally:
            current_actor.reset(token)
