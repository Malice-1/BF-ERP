from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from workflow.activity import snapshot, write_log
from .models import FixedAsset


ZERO = Decimal("0.00")


def _term_end(asset):
    start = asset.in_service_on
    year, month = divmod(start.year * 12 + start.month - 1 + asset.useful_life_months, 12)
    month += 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def depreciation(asset, cutoff):
    """Cumulative straight-line depreciation up to, excluding, cutoff."""
    start, end = asset.in_service_on, _term_end(asset)
    last = min(cutoff, end, asset.disposed_on or end)
    days = max(0, (last - start).days)
    base = asset.cost - asset.residual_value
    return (base * days / (end - start).days).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def schedule(asset):
    start, end = asset.in_service_on, _term_end(asset)
    end = min(end, asset.disposed_on or end)
    previous = ZERO
    while start < end:
        cutoff = min(end, date(start.year + 1, 1, 1))
        cumulative = depreciation(asset, cutoff)
        yield (start.year, (cutoff - start).days, cumulative - previous, cumulative, asset.cost - cumulative)
        previous = cumulative
        start = cutoff


def check_revision(asset, expected):
    if asset.revision != expected:
        raise ValidationError("La fiche a été modifiée. Rechargez la page avant de réessayer.")


def audit(asset, action, actor, before=None):
    write_log(asset, f"fixed_asset.{action}", {"before": before, "after": snapshot(asset)},
        asset._state.db, actor=actor)


@transaction.atomic
def transition(*, pk, actor, action, revision, disposed_on=None, disposal_reason="", proceeds=ZERO):
    asset = get_object_or_404(FixedAsset.objects.select_for_update(), pk=pk)
    check_revision(asset, revision)
    before = snapshot(asset)
    today = timezone.localdate()
    if action == "activate" and asset.status == FixedAsset.Status.DRAFT:
        if asset.in_service_on > today:
            raise ValidationError("La date de mise en service n’est pas encore atteinte.")
        asset.status = FixedAsset.Status.ACTIVE
    elif action == "dispose" and asset.status == FixedAsset.Status.ACTIVE:
        if not disposed_on or not asset.in_service_on <= disposed_on <= today:
            raise ValidationError("La date de sortie doit être comprise entre la mise en service et aujourd’hui.")
        asset.status = FixedAsset.Status.DISPOSED
        asset.disposed_on, asset.disposal_reason, asset.proceeds = disposed_on, disposal_reason, proceeds
    else:
        raise ValidationError("Cette action est indisponible pour l’état actuel de l’immobilisation.")
    asset.revision += 1
    asset.full_clean()
    asset.save()
    audit(asset, action, actor, before)
    return asset
