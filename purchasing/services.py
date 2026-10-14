"""Purchase commands: permission, lock, revision and audit in one transaction."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from workflow.models import AuditEvent
from .exceptions import PurchaseRequestConflict, PurchaseRequestError
from .models import PurchaseRequest, PurchaseRequestLine


def _locked(request_id, actor, expected_revision):
    request = PurchaseRequest.objects.select_for_update().get(pk=request_id)
    if not actor.is_active or request.created_by_id != actor.pk:
        raise PermissionDenied("Action réservée au demandeur actif.")
    if request.revision != expected_revision:
        raise PurchaseRequestConflict("La demande a changé. Rechargez-la.")
    return request


def _editable(request):
    if request.status not in (PurchaseRequest.Status.DRAFT, PurchaseRequest.Status.CORRECTION):
        raise PurchaseRequestError("Cette demande ne peut plus être modifiée.")


def _audit(request, actor, action, payload=None):
    request.revision += 1
    request.save(update_fields=["revision", "status", "updated_at"])
    AuditEvent.objects.create(purchase_request=request, actor=actor, action=action,
                             revision=request.revision, payload=payload or {})


@transaction.atomic
def create_purchase_request(*, actor, supplier):
    if not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied("Un demandeur actif est requis.")
    request = PurchaseRequest.objects.create(created_by=actor, supplier=supplier)
    _audit(request, actor, "request.created")
    return request


@transaction.atomic
def add_purchase_request_line(*, request_id, actor, expected_revision, **values):
    request = _locked(request_id, actor, expected_revision)
    _editable(request)
    allowed = {"detailed_product", "cost_center", "funding", "description", "quantity", "unit_price", "vat_rate"}
    if set(values) - allowed:
        raise ValidationError("Champ de ligne non autorisé.")
    if values.get("vat_rate") is None:
        raise ValidationError("Le taux de TVA est obligatoire, y compris un taux nul.")
    line = PurchaseRequestLine(purchase_request=request, **values)
    line.full_clean()
    line.save()
    _audit(request, actor, "line.created", {"line_id": line.pk})
    return line


@transaction.atomic
def cancel_purchase_request(*, request_id, actor, expected_revision):
    request = _locked(request_id, actor, expected_revision)
    if request.status == PurchaseRequest.Status.CANCELLED:
        return request
    if request.status not in (PurchaseRequest.Status.DRAFT, PurchaseRequest.Status.CORRECTION):
        raise PurchaseRequestError("Annulation de ce statut non disponible dans cet incrément.")
    request.status = PurchaseRequest.Status.CANCELLED
    _audit(request, actor, "request.cancelled")
    return request


def approve_purchase_request(purchase_request):
    """Legacy shortcut bypassed line approvals and reservations."""
    raise PurchaseRequestError("Approbation directe désactivée : workflow et réservation atomique requis.")


@transaction.atomic
def update_purchase_request(*, request_id, actor, expected_revision, supplier):
    request = _locked(request_id, actor, expected_revision)
    _editable(request)
    before = request.supplier_id
    request.supplier = supplier
    request.save(update_fields=["supplier"])
    _audit(request, actor, "request.updated", {"supplier_before": before, "supplier_after": supplier.pk})
    return request


@transaction.atomic
def update_purchase_request_line(*, request_id, line_id, actor, expected_revision, **values):
    request = _locked(request_id, actor, expected_revision)
    _editable(request)
    line = request.lines.get(pk=line_id)
    allowed = {"detailed_product", "cost_center", "funding", "description", "quantity", "unit_price", "vat_rate"}
    if set(values) - allowed:
        raise ValidationError("Champ de ligne non autorisé.")
    before = {key: str(getattr(line, key)) for key in allowed}
    for key, value in values.items():
        setattr(line, key, value)
    if line.vat_rate is None:
        raise ValidationError("Le taux de TVA est obligatoire.")
    line.full_clean()
    line.save()
    _audit(request, actor, "line.updated", {"line_id": line.pk, "before": before,
        "after": {key: str(getattr(line, key)) for key in allowed}})
    return line


@transaction.atomic
def delete_purchase_request_line(*, request_id, line_id, actor, expected_revision):
    request = _locked(request_id, actor, expected_revision)
    _editable(request)
    line = request.lines.get(pk=line_id)
    payload = {"line_id": line.pk, "description": line.description,
        "detailed_product_id": line.detailed_product_id, "cost_center_id": line.cost_center_id,
        "funding_id": line.funding_id, "quantity": str(line.quantity),
        "unit_price": str(line.unit_price), "vat_rate": str(line.vat_rate)}
    line.delete()
    _audit(request, actor, "line.deleted", payload)
