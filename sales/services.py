"""Sales commands: server permissions, revisions, locks and audit."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from workflow.activity import write_log
from .models import (Customer, IssuerConfiguration, SalesSequence, SalesOrder, SalesOrderLine,
    SalesInvoice, SalesInvoiceLine, InvoicePayment, PaymentReversal, SalesEvent, rounded)

logger = logging.getLogger(__name__)


def require(actor, permission):
    if not actor.is_authenticated or not actor.is_active or not actor.has_perm("sales." + permission):
        raise PermissionDenied("Vous ne disposez pas du droit nécessaire pour cette opération.")


def event(order, actor, action, invoice=None, **details):
    item = SalesEvent.objects.create(order=order, invoice=invoice, actor=actor,
        actor_name=actor.get_username(), action=action, details=details)
    write_log(item, "created", {"action": action, "order": order.number,
        "invoice": invoice.number if invoice else None, **details}, "default", actor=actor)


def number(series, date):
    counter, _ = SalesSequence.objects.select_for_update().get_or_create(series=series, year=date.year)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return f"{series}-{date.year}-{counter.last_number:04d}"


def locked_order(pk, revision):
    order = SalesOrder.objects.select_for_update().get(pk=pk)
    if order.revision != revision:
        raise ValidationError("La commande a changé. Rechargez la page avant de recommencer.")
    return order


def breakdown(lines):
    groups = defaultdict(lambda: Decimal(0))
    for line in lines:
        groups[(line.tax_code, line.tax_rate, line.exemption_reason)] += line.subtotal
    return [{"code": code, "rate": str(rate), "reason": reason,
        "base": str(base), "tax": str(rounded(base * rate / 100))}
        for (code, rate, reason), base in sorted(groups.items())]


def totals(order, lines):
    # Allocate group rounding cumulatively so the sum of stored line taxes
    # equals the VAT breakdown (including many very small lines).
    bases = defaultdict(lambda: Decimal(0))
    taxes = defaultdict(lambda: Decimal(0))
    for line in lines:
        key = (line.tax_code, line.tax_rate, line.exemption_reason)
        bases[key] += line.subtotal
        cumulative = rounded(bases[key] * line.tax_rate / 100)
        line.tax_amount = cumulative - taxes[key]
        line.total = line.subtotal + line.tax_amount
        taxes[key] = cumulative
    order.subtotal = sum((line.subtotal for line in lines), Decimal(0))
    order.tax_total = sum((Decimal(t["tax"]) for t in breakdown(lines)), Decimal(0))
    order.total = order.subtotal + order.tax_total


ORDER_FIELDS = {"customer", "order_date", "customer_reference", "currency", "notes"}
LINE_FIELDS = {f.name for f in SalesOrderLine._meta.fields} - {"id", "order", "subtotal", "tax_amount", "total"}


@transaction.atomic
def save_order(*, actor, values, lines, pk=None, revision=0):
    require(actor, "change_salesorder" if pk else "add_salesorder")
    if set(values) - ORDER_FIELDS:
        raise ValidationError("Champ de commande non autorisé.")
    order = locked_order(pk, revision) if pk else SalesOrder(created_by=actor)
    if order.status != SalesOrder.Status.DRAFT:
        raise ValidationError("Seuls les brouillons sont modifiables.")
    for key, value in values.items():
        setattr(order, key, value)
    if not Customer.objects.select_for_update().get(pk=order.customer_id).is_active:
        raise ValidationError("Le client doit être actif.")
    if not lines:
        raise ValidationError("Ajoutez au moins une ligne de formation.")
    if not order.number:
        order.number = number("CV", order.order_date)
    order.full_clean()
    order.save()
    # Validate every replacement before removing any existing line.
    prepared = []
    for values in lines:
        if set(values) - LINE_FIELDS:
            raise ValidationError("Champ de ligne non autorisé.")
        line = SalesOrderLine(order=order, **values)
        line.full_clean()
        if line.service_id and not line.service.is_active:
            raise ValidationError("Une formation sélectionnée est inactive.")
        line.calculate()
        prepared.append(line)
    order.lines.all().delete()
    for line in prepared:
        line.save()
    totals(order, prepared)
    SalesOrderLine.objects.bulk_update(prepared, ["tax_amount", "total"])
    order.revision += 1
    order.full_clean()
    order.save()
    event(order, actor, "Commande enregistrée", revision=order.revision)
    return order


@transaction.atomic
def transition(*, actor, pk, revision, action):
    if action not in ("confirm", "cancel"):
        raise ValidationError("Action inconnue.")
    require(actor, "confirm_salesorder" if action == "confirm" else "cancel_salesorder")
    order = locked_order(pk, revision)
    if action == "confirm":
        if order.status != SalesOrder.Status.DRAFT:
            raise ValidationError("Seul un brouillon peut être confirmé.")
        if not Customer.objects.select_for_update().get(pk=order.customer_id).is_active:
            raise ValidationError("Ce client est inactif.")
        lines = list(order.lines.all())
        if not lines:
            raise ValidationError("Ajoutez au moins une ligne.")
        for line in lines:
            line.full_clean()
            line.calculate()
        totals(order, lines)
        order.full_clean()
        order.status = SalesOrder.Status.CONFIRMED
    else:
        if order.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED) or hasattr(order, "invoice"):
            raise ValidationError("Cette commande ne peut plus être annulée.")
        order.status = SalesOrder.Status.CANCELLED
    order.revision += 1
    order.save()
    event(order, actor, "Commande confirmée" if action == "confirm" else "Commande annulée")
    return order


PARTY_FIELDS = ("name", "street", "zip_code", "city", "country", "vat_number", "email",
    "peppol_endpoint_id", "peppol_endpoint_scheme")


def party_snapshot(party, extra):
    return {f: getattr(party, f) for f in PARTY_FIELDS + extra}


def validate_parties(customer, issuer, lines):
    customer.full_clean()
    issuer.full_clean()
    errors = []
    for label, party in (("Client", customer), ("Émetteur", issuer)):
        for field in ("name", "street", "zip_code", "city", "country"):
            if not getattr(party, field):
                errors.append(f"{label} : {party._meta.get_field(field).verbose_name} manquant.")
        if customer.invoice_format == "PEPPOL_XML":
            for field in ("peppol_endpoint_id", "peppol_endpoint_scheme"):
                if not getattr(party, field):
                    errors.append(f"{label} : {party._meta.get_field(field).verbose_name} manquant.")
    if not customer.is_active:
        errors.append("Le client est inactif.")
    if not customer.invoice_format:
        errors.append("Sélectionnez le format de facturation du client.")
    categories = {line.tax_code for line in lines}
    if categories & {"S", "Z", "E", "AE"} and not issuer.vat_number:
        errors.append("Le numéro de TVA de l’émetteur est requis pour ces catégories.")
    if "AE" in categories and not customer.vat_number:
        errors.append("L’autoliquidation exige le numéro de TVA du client.")
    if "O" in categories and len(categories) > 1:
        errors.append("Les lignes hors champ ne peuvent pas être mélangées avec d’autres catégories.")
    # Prevent multiple exemption descriptions for the same fiscal grouping.
    reasons = defaultdict(set)
    for line in lines:
        reasons[(line.tax_code, line.tax_rate)].add(line.exemption_reason)
    if any(len(values) > 1 for values in reasons.values()):
        errors.append("Utilisez un même motif fiscal pour une même catégorie et un même taux.")
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def _issue(*, actor, pk, revision):
    require(actor, "issue_salesinvoice")
    order = locked_order(pk, revision)
    if order.status != SalesOrder.Status.CONFIRMED or SalesInvoice.objects.filter(order=order).exists():
        raise ValidationError("La commande doit être confirmée et ne pas avoir de facture.")
    from accounting import sales_posting
    posting_config = sales_posting.locked_configuration()
    customer = Customer.objects.select_for_update().get(pk=order.customer_id)
    issuer = IssuerConfiguration.objects.select_for_update().filter(pk=1).first()
    if issuer is None:
        raise ValidationError("Configurez l’émetteur avant de facturer.")
    lines = list(order.lines.all())
    if not lines:
        raise ValidationError("La commande ne contient aucune ligne.")
    for line in lines:
        line.full_clean()
        line.calculate()
    validate_parties(customer, issuer, lines)
    if customer.invoice_format == "PEPPOL_XML" and not (order.customer_reference or customer.reference):
        raise ValidationError("Pour le XML, renseignez la référence de commande du client ou sa référence acheteur.")
    fiscal = breakdown(lines)
    totals(order, lines)
    today = timezone.localdate()
    invoice = SalesInvoice(order=order, number=number("FV", today), issue_date=today,
        due_date=today + timedelta(days=customer.payment_days), currency=order.currency,
        invoice_format=customer.invoice_format, subtotal=order.subtotal,
        tax_total=order.tax_total, total=order.total, tax_breakdown=fiscal,
        customer_snapshot=party_snapshot(customer, ("code", "reference", "payment_days", "payment_terms")),
        issuer_snapshot=party_snapshot(issuer, ("legal_id", "iban")),
        order_snapshot={"number": order.number, "date": order.order_date.isoformat(),
            "customer_reference": order.customer_reference},
        payment_status="PAID" if order.total == 0 else "UNPAID")
    copies = []
    for position, line in enumerate(lines, 1):
        values = {f.name: getattr(line, f.name) for f in SalesInvoiceLine._meta.fields
            if f.name not in ("id", "invoice", "position", "dimension_snapshot")}
        values["dimension_snapshot"] = {key: str(getattr(line, key)) if getattr(line, key) else ""
            for key in ("cost_center", "funding", "budget_product", "support")}
        copies.append(SalesInvoiceLine(position=position, **values))
    from .documents import render_document, validate_xml
    try:
        data = render_document(invoice, copies)
    except Exception as cause:
        logger.exception("Invoice preparation failed for order %s", order.pk)
        error = ValidationError("La préparation du document a échoué. Aucune facture n’a été émise. Contactez l’administrateur.")
        error.preparation_failure = type(cause).__name__
        raise error from cause
    validation = validate_xml(data, invoice.issue_date) if invoice.invoice_format == "PEPPOL_XML" else None
    if validation and validation["status"] != "VALID":
        # Persist the refusal outside the transaction in the public wrapper.
        error = ValidationError(["Émission XML bloquée : validation incomplète ou non conforme."] +
            [str(e) for e in validation["details"][:15]])
        error.validation_result = validation
        raise error
    invoice.full_clean()
    invoice.save(force_insert=True)
    for line in copies:
        line.invoice = invoice
    SalesInvoiceLine.objects.bulk_create(copies)
    invoice.sealed = True
    invoice.save(update_fields=["sealed"])
    sales_posting.create_invoice_draft(
        actor=actor, config=posting_config, invoice=invoice, invoice_lines=copies, customer=customer)
    order.status = SalesOrder.Status.INVOICED
    order.revision += 1
    order.save()
    event(order, actor, "Facture émise", invoice=invoice)
    return invoice, data, validation


def issue_invoice(*, actor, pk, revision):
    try:
        invoice, data, validation = _issue(actor=actor, pk=pk, revision=revision)
    except ValidationError as error:
        if hasattr(error, "validation_result"):
            with transaction.atomic():
                order = SalesOrder.objects.select_for_update().get(pk=pk)
                event(order, actor, "Émission XML refusée", validation=error.validation_result)
        elif hasattr(error, "preparation_failure"):
            with transaction.atomic():
                order = SalesOrder.objects.select_for_update().get(pk=pk)
                event(order, actor, "Préparation documentaire refusée", error=error.preparation_failure)
        raise
    from .documents import archive
    archive(invoice.pk, actor, data, validation)
    invoice.refresh_from_db()
    return invoice


def paid_amount(invoice):
    return invoice.payments.filter(reversal__isnull=True).aggregate(value=Sum("amount"))["value"] or Decimal(0)


def update_payment_status(invoice):
    paid = paid_amount(invoice)
    invoice.payment_status = "PAID" if paid >= invoice.total else "PARTIALLY_PAID" if paid > 0 else "UNPAID"
    invoice.save(update_fields=["payment_status"])


@transaction.atomic
def record_payment(*, actor, pk, amount, payment_date, reference, token):
    require(actor, "record_invoicepayment")
    invoice = SalesInvoice.objects.select_for_update().get(pk=pk)
    existing = InvoicePayment.objects.filter(token=token).first()
    if existing:
        if (existing.invoice_id, existing.amount, existing.payment_date, existing.reference) != (pk, amount, payment_date, reference):
            raise ValidationError("Cette référence technique a déjà été utilisée pour un autre paiement.")
        return existing
    if amount > invoice.total - paid_amount(invoice):
        raise ValidationError("Le paiement dépasse le solde restant dû.")
    if payment_date > timezone.localdate():
        raise ValidationError("Un paiement reçu ne peut pas être daté dans le futur.")
    payment = InvoicePayment(invoice=invoice, amount=amount, payment_date=payment_date,
        reference=reference.strip(), token=token, created_by=actor)
    payment.full_clean()
    payment.save()
    update_payment_status(invoice)
    event(invoice.order, actor, "Paiement enregistré", invoice=invoice, payment=payment.pk, amount=str(amount))
    return payment


@transaction.atomic
def reverse_payment(*, actor, pk, payment_id, reason):
    require(actor, "record_invoicepayment")
    invoice = SalesInvoice.objects.select_for_update().get(pk=pk)
    payment = invoice.payments.get(pk=payment_id)
    reversal = PaymentReversal(payment=payment, reason=reason.strip(), created_by=actor)
    reversal.full_clean()
    reversal.save()
    update_payment_status(invoice)
    event(invoice.order, actor, "Paiement corrigé", invoice=invoice, payment=payment.pk, reason=reason)
