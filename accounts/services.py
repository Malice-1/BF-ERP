from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from budgeting.models import BudgetProduct, CostCenter, Funding
from workflow.models import ConfigurationAuditEvent
from .models import Authorization, AuthorizationVersion


SCOPE_MODELS = {"cost_center": CostCenter, "funding": Funding, "budget_product": BudgetProduct}


def validate_scope(scope):
    if not isinstance(scope, dict) or set(scope) - SCOPE_MODELS.keys():
        raise ValidationError("Critères permis : cost_center, funding, budget_product.")
    for criterion, values in scope.items():
        if not isinstance(values, list) or not values or any(type(value) is not int or value <= 0 for value in values):
            raise ValidationError("Chaque critère doit contenir une liste non vide d'identifiants.")
        if SCOPE_MODELS[criterion].objects.filter(pk__in=values).count() != len(set(values)):
            raise ValidationError("Le périmètre contient une référence inconnue.")


@transaction.atomic
def publish_authorization(*, actor, user, function, valid_from, valid_until=None, scope=None,
                          enabled=True, authorization_id=None, expected_version=None):
    if not actor.is_active or not actor.has_perm("accounts.manage_authorizations"):
        raise PermissionDenied
    scope = {} if scope is None else scope
    validate_scope(scope)
    if authorization_id is None:
        authorization = Authorization.objects.create(user=user, function=function)
    else:
        authorization = Authorization.objects.select_for_update().get(pk=authorization_id)
        if authorization.user_id != user.pk or authorization.function_id != function.pk:
            raise ValidationError("L'utilisateur et la fonction d'une habilitation sont fixes.")
        current = authorization.current_version
        if current is None or current.version != expected_version:
            raise ValidationError("L'habilitation a changé. Rechargez-la.")
    version = (authorization.versions.aggregate(value=Max("version"))["value"] or 0) + 1
    record = AuthorizationVersion(authorization=authorization, version=version, valid_from=valid_from,
                                  valid_until=valid_until, scope=scope, enabled=enabled, created_by=actor)
    record.full_clean(exclude=["scope"])
    record.save()
    authorization.current_version = record
    authorization.save(update_fields=["current_version"])
    ConfigurationAuditEvent.objects.create(actor=actor, action="authorization.published",
        object_type="authorization", object_id=authorization.pk,
        payload={"version_id": record.pk, "version": version})
    return record


def eligible_authorization(*, user, function, context, at=None):
    """One complete authorization must match; deterministic choice by grant ID."""
    if not user.is_active:
        return None
    at = at or timezone.now()
    for grant in Authorization.objects.filter(user=user, function=function).select_related("current_version").order_by("pk"):
        record = grant.current_version
        if not record or record.authorization_id != grant.pk or not record.enabled:
            continue
        if record.valid_from > at or (record.valid_until is not None and at >= record.valid_until):
            continue
        if all(context.get(key) in values for key, values in record.scope.items()):
            return record
    return None
