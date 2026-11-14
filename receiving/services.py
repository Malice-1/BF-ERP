from django.core.exceptions import ValidationError
from django.db import transaction
from purchasing.flow import require
from workflow.models import ConfigurationAuditEvent
from .models import Warehouse, StockBalance, StockMovement


@transaction.atomic
def move(*, actor, warehouse, product, kind, quantity, reason, token, destination=None):
    require(actor, "receiving.manage_stock")
    # Lock even empty stock slots; stable depot ordering prevents opposing transfers deadlocking.
    list(Warehouse.objects.select_for_update().filter(pk__in=[warehouse.pk, destination.pk if destination else warehouse.pk]).order_by("pk"))
    previous = StockMovement.objects.filter(token=token).first()
    if previous:
        if (previous.warehouse_id, previous.destination_id, previous.product_id, previous.kind, previous.quantity, previous.reason, previous.actor_id) != (warehouse.pk, destination.pk if destination else None, product.pk, kind, quantity, reason, actor.pk):
            raise ValidationError("Cette opération a déjà été enregistrée avec d’autres données.")
        return previous
    if kind not in ("receipt", "issue", "transfer", "inventory") or not quantity.is_finite() or quantity < 0 or (kind != "inventory" and quantity == 0) or not reason.strip():
        raise ValidationError("Type, quantité ou justification invalide.")
    if (kind == "transfer" and (not destination or destination.pk == warehouse.pk)) or (kind != "transfer" and destination):
        raise ValidationError("Choisissez un dépôt destination différent uniquement pour un transfert.")
    balance, _ = StockBalance.objects.get_or_create(warehouse=warehouse, product=product)
    delta = quantity - balance.quantity if kind == "inventory" else quantity if kind == "receipt" else -quantity
    if balance.quantity + delta < 0:
        raise ValidationError("Stock insuffisant : aucune écriture enregistrée.")
    balance.quantity += delta
    balance.full_clean()
    balance.save()
    if destination:
        target, _ = StockBalance.objects.get_or_create(warehouse=destination, product=product)
        target.quantity += quantity
        target.full_clean()
        target.save()
    movement = StockMovement(warehouse=warehouse, destination=destination, product=product,
        kind=kind, quantity=quantity, delta=delta, reason=reason, actor=actor, token=token)
    movement.full_clean()
    movement.save()
    ConfigurationAuditEvent.objects.create(actor=actor, action="stock.movement", object_type="stock_movement",
        object_id=movement.pk, payload={"kind": kind, "delta": str(delta), "reason": reason})
    return movement
