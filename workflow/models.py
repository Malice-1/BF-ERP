from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only through application services; no admin mutation interface."""

    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    purchase_request = models.ForeignKey(
        "purchasing.PurchaseRequest", on_delete=models.PROTECT, related_name="audit_events"
    )
    action = models.CharField(max_length=60)
    revision = models.PositiveIntegerField()
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_request", "revision"], name="unique_request_audit_revision"
            )
        ]


class ConfigurationAuditEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.PositiveBigIntegerField()
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["id"]
