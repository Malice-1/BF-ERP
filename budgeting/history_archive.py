"""Export and remove dated budget history while retaining a continuity snapshot."""
from collections import defaultdict
from datetime import datetime, time
import gzip
from hashlib import sha256
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from purchasing.models import AnnualEnvelope
from workflow.activity import budget_history_archive_deletion, write_log
from workflow.models import ActivityLog
from .models import BudgetHistoryEvent


FORMAT = "bf-erp.budget-history.v1"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_JSON_BYTES = 128 * 1024 * 1024


def _require_admin(actor):
    if not (actor.is_active and actor.is_superuser):
        raise PermissionDenied


def _eligible(before, year):
    cutoff = timezone.make_aware(datetime.combine(before, time.min))
    events = BudgetHistoryEvent.objects.filter(created_at__lt=cutoff)
    if year is not None:
        events = events.filter(envelope__year=year)
    return events.order_by("envelope_id", "created_at", "pk")


def _record(event):
    return {
        "id": event.pk, "envelope_id": event.envelope_id, "version_id": event.version_id,
        "created_at": event.created_at.isoformat(), "actor": event.actor, "reason": event.reason,
        "state": event.state,
    }


def _audit(event_id, source, action, actor, details):
    write_log(BudgetHistoryEvent(pk=event_id), action, details, "default", actor=actor, source=source)


def export_archive(*, actor, before, year=None):
    _require_admin(actor)
    if before > timezone.localdate():
        raise ValidationError("Choisissez une date limite passée ou aujourd’hui.")
    anchors = {}
    events = []
    payload_size = 0
    for event in _eligible(before, year).iterator(chunk_size=250):
        anchors[event.envelope_id] = event.pk
        record = _record(event)
        payload_size += len(json.dumps(record, ensure_ascii=False).encode("utf-8")) + 2
        if payload_size >= MAX_JSON_BYTES:
            raise ValidationError("Archive trop volumineuse. Choisissez une date limite plus ancienne ou un seul exercice.")
        events.append(record)
    purgeable_count = len(events) - len(anchors)
    if not events:
        raise ValidationError("Aucun événement ne correspond aux critères de l’archive.")

    payload = {"format": FORMAT, "exported_at": timezone.now().isoformat(),
        "before": before.isoformat(), "year": year, "retained_ids": list(anchors.values()), "events": events}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_JSON_BYTES:
        raise ValidationError("Archive trop volumineuse. Choisissez une date limite plus ancienne ou un seul exercice.")
    archive = gzip.compress(raw, mtime=0)
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValidationError("Archive trop volumineuse. Choisissez une date limite plus ancienne ou un seul exercice.")
    digest = sha256(archive).hexdigest()
    _audit(events[0]["id"], f"budget-history-export:{digest}", "admin.action", actor,
        {"operation": "Export de l’historique budgétaire", "before": payload["before"], "year": year,
         "sha256": digest, "exported": len(events), "purgeable": purgeable_count})
    return archive


@transaction.atomic
def purge_archive(*, actor, archive):
    _require_admin(actor)
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValidationError("Le fichier dépasse la taille maximale d’une archive.")
    digest = sha256(archive).hexdigest()
    receipt = ActivityLog.objects.select_for_update().filter(source=f"budget-history-export:{digest}").first()
    if receipt is None:
        raise ValidationError("Ce fichier ne correspond à aucune archive exportée depuis cette base.")
    if not receipt.details["purgeable"]:
        raise ValidationError("Cette archive ne contient que les états de référence à conserver.")
    purge_source = f"budget-history-purge:{digest}"
    if ActivityLog.objects.filter(source=purge_source).exists():
        raise ValidationError("Cette archive a déjà été utilisée pour une purge.")

    # The receipt matches the exact exported bytes before any decompression.
    payload = json.loads(gzip.decompress(archive))
    if payload.get("format") != FORMAT:
        raise ValidationError("Format d’archive non pris en charge.")
    archived = defaultdict(list)
    for record in payload["events"]:
        archived[record["envelope_id"]].append(record)
    envelopes = list(AnnualEnvelope.objects.select_for_update().filter(pk__in=archived).order_by("pk"))
    if len(envelopes) != len(archived):
        raise ValidationError("Les exercices ont changé depuis l’export. Téléchargez une nouvelle archive.")
    before = datetime.fromisoformat(payload["before"]).date()
    before_cutoff = _eligible(before, payload["year"])
    removed = 0
    for envelope in envelopes:
        records = archived[envelope.pk]
        actual = [_record(event) for event in before_cutoff.filter(envelope=envelope)]
        if actual != records or records[-1]["id"] not in payload["retained_ids"]:
            raise ValidationError("L’historique a changé depuis l’export. Téléchargez une nouvelle archive.")
        ids = [record["id"] for record in records[:-1]]
        token = budget_history_archive_deletion.set(True)
        try:
            for offset in range(0, len(ids), 500):
                count, _ = BudgetHistoryEvent.objects.filter(pk__in=ids[offset:offset + 500]).delete()
                removed += count
        finally:
            budget_history_archive_deletion.reset(token)

    _audit(payload["events"][0]["id"], purge_source, "maintenance.deleted", actor,
        {"operation": "Purge d’une archive budgétaire", "before": payload["before"], "year": payload["year"],
         "sha256": digest, "removed": removed, "retained_ids": payload["retained_ids"]})
    return removed
