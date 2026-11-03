from django.conf import settings
from django.db import models
from django.utils import timezone
from .labels import ACTION_LABELS


class ActivityLog(models.Model):
    """Independent identity/object snapshots; deliberately no foreign keys."""

    def __str__(self):
        return f"Action n° {self.pk} — {self.get_action_display()}"

    created_at = models.DateTimeField(default=timezone.now, verbose_name='Date de création')
    actor_identifier = models.CharField(max_length=100, db_index=True, verbose_name='Identifiant de l’utilisateur')
    actor_username = models.CharField(max_length=150, db_index=True, verbose_name='Nom de l’utilisateur')
    action = models.CharField(max_length=100, db_index=True, verbose_name='Action', choices=ACTION_LABELS)
    object_type = models.CharField(max_length=100, db_index=True, verbose_name='Type d’objet')
    object_identifier = models.CharField(max_length=100, verbose_name='Identifiant de l’objet')
    details = models.JSONField(default=dict, verbose_name='Détails')
    source = models.CharField(max_length=150, null=True, unique=True, verbose_name='Source')

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Journal des actions"
        verbose_name_plural = "Journal des actions"


class AuditEvent(models.Model):
    """Append-only through application services; no admin mutation interface."""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Auteur')
    purchase_request = models.ForeignKey(
        "purchasing.PurchaseRequest", on_delete=models.PROTECT, related_name="audit_events",
        verbose_name='Demande d’achat',
    )
    action = models.CharField(max_length=60, verbose_name='Action', choices=ACTION_LABELS)
    revision = models.PositiveIntegerField(verbose_name='Révision')
    payload = models.JSONField(default=dict, verbose_name='Données de l’événement')

    class Meta:
        verbose_name = 'événement d’achat'
        verbose_name_plural = 'événements d’achat'
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_request", "revision"], name="unique_request_audit_revision"
            )
        ]

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"


class ConfigurationAuditEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Auteur')
    action = models.CharField(max_length=80, verbose_name='Action', choices=ACTION_LABELS)
    object_type = models.CharField(max_length=80, verbose_name='Type d’objet')
    object_id = models.PositiveBigIntegerField(verbose_name='Identifiant de l’objet')
    payload = models.JSONField(default=dict, verbose_name='Données de l’événement')

    class Meta:
        verbose_name = 'événement de configuration'
        verbose_name_plural = 'événements de configuration'
        ordering = ["id"]

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"
