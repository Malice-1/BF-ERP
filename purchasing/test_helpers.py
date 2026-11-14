"""Recorded legacy configurations for history tests, never for new submissions."""
from django.db import transaction
from django.utils import timezone

from .models import WorkflowVersion


@transaction.atomic
def record_legacy_workflow(version):
    """Represent a configuration published before fixed validation was introduced."""
    WorkflowVersion.objects.filter(operation=version.operation, active=True).update(active=False)
    version.active = True
    version.published_at = timezone.now()
    version.save(update_fields=["active", "published_at"])
    return version
