"""Purchase receipts: physical quantities, separate from purchasing approval and budget."""
from decimal import Decimal
from uuid import uuid5

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from purchasing.flow import require
from purchasing.models import PurchaseRequest, PurchaseOrder
from workflow.models import AuditEvent
from .models import PurchaseReceipt, PurchaseReceiptLine
from .services import move


def received_quantities(purchase):
    return dict(PurchaseReceiptLine.objects.filter(purchase_line__purchase_request=purchase)
                .values("purchase_line_id").annotate(total=Sum("movement__quantity"))
                .values_list("purchase_line_id", "total"))


def receipt_label(ordered, received):
    if ordered > 0 and received >= ordered:
        return "complete", "Réceptionnée"
    if received > 0:
        return "partial", "Partiellement réceptionnée"
    return "none", "Non réceptionnée"


def purchase_progress(rows):
    rows = list(rows)
    ids = [row.pk for row in rows]
    from purchasing.models import PurchaseRequestLine
    ordered = dict(PurchaseRequestLine.objects.filter(purchase_request_id__in=ids)
                   .values("purchase_request_id").annotate(total=Sum("quantity"))
                   .values_list("purchase_request_id", "total"))
    received = dict(PurchaseReceiptLine.objects.filter(purchase_line__purchase_request_id__in=ids)
                    .values("purchase_line__purchase_request_id").annotate(total=Sum("movement__quantity"))
                    .values_list("purchase_line__purchase_request_id", "total"))
    for row in rows:
        row.receipt_status, row.receipt_label = receipt_label(ordered.get(row.pk, 0), received.get(row.pk, 0))
    return rows


def line_progress(purchase, lines):
    received = received_quantities(purchase)
    for line in lines:
        line.received_quantity = received.get(line.pk, Decimal(0))
        line.remaining_quantity = max(Decimal(0), line.quantity - line.received_quantity)
        line.receipt_status, line.receipt_label = receipt_label(line.quantity, line.received_quantity)
    return lines


@transaction.atomic
def receive_purchase(*, actor, purchase_id, warehouse, reason, token, quantities):
    require(actor, "receiving.manage_stock")
    purchase = PurchaseRequest.objects.select_for_update().get(pk=purchase_id)
    if purchase.status != "ORDERED":
        raise ValidationError("Seule une demande validée et commandée peut être réceptionnée.")
    order = PurchaseOrder.objects.filter(purchase_request=purchase).first()
    if order is None:
        raise ValidationError("Le bon de commande est introuvable.")
    normalized = {}
    for line_id, quantity in quantities:
        if line_id in normalized or not quantity.is_finite() or quantity < 0:
            raise ValidationError("Ligne ou quantité de réception invalide.")
        normalized[line_id] = quantity
    positive = {line_id: quantity for line_id, quantity in normalized.items() if quantity > 0}
    if not positive or not reason.strip():
        raise ValidationError("Renseignez une référence et au moins une quantité à réceptionner.")
    previous = PurchaseReceipt.objects.filter(token=token).first()
    if previous:
        recorded = dict(previous.lines.values_list("purchase_line_id", "movement__quantity"))
        if (previous.order_id != order.pk or previous.warehouse_id != warehouse.pk
                or previous.actor_id != actor.pk or previous.reason != reason or recorded != positive):
            raise ValidationError("Cette réception a déjà été enregistrée avec d’autres données.")
        return previous
    lines = {line.pk: line for line in purchase.lines.select_related("detailed_product")}
    if not set(normalized) <= set(lines):
        raise ValidationError("Une ligne ne fait pas partie de cette demande d’achat.")
    ordered = {snapshot.original_line_id: Decimal(snapshot.data["quantity"])
               for snapshot in order.submission.lines.all()}
    received = received_quantities(purchase)
    for line_id, quantity in positive.items():
        if line_id not in ordered or quantity > ordered[line_id] - received.get(line_id, Decimal(0)):
            raise ValidationError(f"Quantité supérieure au reste à recevoir pour le produit {lines[line_id].detailed_product}.")
    receipt = PurchaseReceipt.objects.create(order=order, warehouse=warehouse, actor=actor, reason=reason, token=token)
    for line_id, quantity in sorted(positive.items()):
        movement = move(actor=actor, warehouse=warehouse, product=lines[line_id].detailed_product,
                        kind="receipt", quantity=quantity, reason=reason, token=uuid5(token, str(line_id)))
        PurchaseReceiptLine.objects.create(receipt=receipt, purchase_line=lines[line_id], movement=movement)
    purchase.revision += 1
    purchase.save(update_fields=["revision", "updated_at"])
    AuditEvent.objects.create(purchase_request=purchase, actor=actor, action="stock.purchase_receipt",
        revision=purchase.revision, payload={"receipt_id": receipt.pk, "warehouse": str(warehouse), "reason": reason,
        "quantities": {str(key): str(value) for key, value in positive.items()}})
    return receipt
