from django.core.exceptions import ValidationError
from django.db import transaction

from suppliers.models import Supplier
from .models import SupplierInvoice
from .services import audit, profile_lock, require
from .supplier_xml import supplier_candidates


@transaction.atomic
def save_invoice(*, actor, values, pk=None, revision=None):
    require(actor, "change_supplierinvoice" if pk else "add_supplierinvoice")
    profile_lock()
    invoice = (SupplierInvoice.objects.select_for_update().get(pk=pk) if pk
               else SupplierInvoice(origin="MANUAL", created_by=actor))
    if invoice.origin != "MANUAL" or invoice.status != "RECEIVED" or (pk and invoice.revision != revision):
        raise ValidationError("Cette facture ne peut plus être modifiée ou a changé. Rechargez la page.")

    supplier = Supplier.objects.select_for_update().get(pk=values["supplier"].pk)
    number = values["invoice_number"].strip()
    duplicates = SupplierInvoice.objects.filter(invoice_number__iexact=number).exclude(pk=invoice.pk)
    if duplicates.filter(supplier=supplier).exists() or any(
        supplier in supplier_candidates(other)
        for other in duplicates.filter(origin="PEPPOL", supplier__isnull=True)
    ):
        raise ValidationError("Une facture portant ce numéro existe déjà pour ce fournisseur.")

    subtotal, tax = values["subtotal"], values["tax_total"]
    total = subtotal + tax
    payable = values["payable"] if values["payable"] is not None else total
    if subtotal < 0 or tax < 0 or not 0 <= payable <= total:
        raise ValidationError("Le montant à payer doit être compris entre zéro et le total TTC.")
    if values["due_date"] and values["due_date"] < values["issue_date"]:
        raise ValidationError("L’échéance doit être égale ou postérieure à la date de la facture.")

    invoice.supplier, invoice.invoice_number = supplier, number
    invoice.issue_date, invoice.due_date = values["issue_date"], values["due_date"]
    invoice.currency = values["currency"]
    invoice.subtotal, invoice.tax_total, invoice.total, invoice.payable = subtotal, tax, total, payable
    invoice.extracted_data = {"description": values["description"], "order_reference": values["order_reference"]}
    if pk:
        invoice.revision += 1
    invoice.full_clean()
    invoice.save()
    audit(actor, invoice, "Facture fournisseur modifiée" if pk else "Facture fournisseur saisie",
          invoice_number=number, supplier_id=supplier.pk, revision=invoice.revision,
          currency=invoice.currency, subtotal=str(subtotal), tax_total=str(tax), payable=str(payable))
    return invoice
