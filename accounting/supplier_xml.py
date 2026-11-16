"""Untrusted UBL supplier invoices. No HTTP, external entities or attachments executed."""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from lxml import etree

from sales.documents import private_storage, validate_xml, NS, UBL
from sales.models import IssuerConfiguration
from suppliers.models import Supplier
from suppliers.identifiers import normalize_enterprise_number
from .models import SupplierInvoice, SupplierInvoiceValidation, AccountingProfile
from .services import require, profile_lock, audit


CUSTOMIZATION = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"


def normalized(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def store():
    return private_storage(settings.SUPPLIER_DOCUMENT_ROOT)


def text(node, path):
    return node.findtext(path, default="", namespaces=NS).strip() if node is not None else ""


def elements(node, path):
    return node.findall(path, namespaces=NS) if node is not None else []


def allowances(node):
    return [{"charge": text(item, "cbc:ChargeIndicator"), "amount": text(item, "cbc:Amount"),
        "base": text(item, "cbc:BaseAmount"), "percent": text(item, "cbc:MultiplierFactorNumeric"),
        "reason": text(item, "cbc:AllowanceChargeReason")} for item in elements(node, "cac:AllowanceCharge")]


def party(node):
    endpoint = node.find("cbc:EndpointID", NS) if node is not None else None
    company = node.find("cac:PartyLegalEntity/cbc:CompanyID", NS) if node is not None else None
    vats = [text(item, "cbc:CompanyID") for item in elements(node, "cac:PartyTaxScheme") if text(item, "cac:TaxScheme/cbc:ID") == "VAT"]
    return {"name": text(node, "cac:PartyLegalEntity/cbc:RegistrationName") or text(node, "cac:PartyName/cbc:Name"),
        "vat_number": vats[0] if vats else "", "legal_id": text(node, "cac:PartyLegalEntity/cbc:CompanyID"),
        "legal_id_scheme": company.get("schemeID", "") if company is not None else "",
        "identifications": [{"id": text(item, "cbc:ID"), "scheme": item.find("cbc:ID", NS).get("schemeID", "")}
            for item in elements(node, "cac:PartyIdentification") if item.find("cbc:ID", NS) is not None],
        "endpoint_id": endpoint.text.strip() if endpoint is not None and endpoint.text else "",
        "endpoint_scheme": endpoint.get("schemeID", "") if endpoint is not None else "",
        "street": text(node, "cac:PostalAddress/cbc:StreetName"), "city": text(node, "cac:PostalAddress/cbc:CityName"),
        "zip_code": text(node, "cac:PostalAddress/cbc:PostalZone"), "country": text(node, "cac:PostalAddress/cac:Country/cbc:IdentificationCode"),
        "email": text(node, "cac:Contact/cbc:ElectronicMail")}


def parse(data):
    if not data or len(data) > settings.SUPPLIER_XML_MAX_BYTES:
        raise ValidationError("Le XML est vide ou dépasse la taille autorisée (5 Mo par défaut).")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, recover=False)
    try:
        root = etree.fromstring(data, parser)
    except (etree.XMLSyntaxError, ValueError) as cause:
        raise ValidationError("Fichier XML illisible ou mal formé.") from cause
    if root.getroottree().docinfo.doctype:
        raise ValidationError("Les DTD et entités externes sont interdites.")
    if root.tag != f"{{{UBL}}}Invoice":
        raise ValidationError("Importez une facture UBL Invoice seule. Les avoirs, enveloppes et autres formats ne sont pas pris en charge ici.")
    if text(root, "cbc:CustomizationID") != CUSTOMIZATION:
        raise ValidationError("Le fichier ne déclare pas le profil Peppol BIS Billing 3.0 attendu.")
    if text(root, "cbc:InvoiceTypeCode") != "380":
        raise ValidationError("Seules les factures commerciales de type 380 sont prises en charge par cet import.")
    errors = []

    def parsed_date(path, required=False):
        value = text(root, path)
        if not value and not required:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            errors.append({"stage": "EXTRACTION", "message": f"Date absente ou invalide : {path}"})
            return None

    def amount(value, label):
        try:
            number = Decimal(value)
            if not number.is_finite() or abs(number) >= Decimal("1e18") or number != number.quantize(Decimal("0.01")):
                raise InvalidOperation
            return number
        except (InvalidOperation, ValueError):
            errors.append({"stage": "EXTRACTION", "message": f"Montant absent, hors capacité ou invalide : {label}"})
            return None

    currency = text(root, "cbc:DocumentCurrencyCode")
    taxes = elements(root, "cac:TaxTotal")
    selected = [item for item in taxes if item.find("cbc:TaxAmount", NS) is not None and item.find("cbc:TaxAmount", NS).get("currencyID") == currency]
    tax = selected[0] if selected else None
    seller = party(root.find("cac:AccountingSupplierParty/cac:Party", NS))
    buyer = party(root.find("cac:AccountingCustomerParty/cac:Party", NS))
    rows = []
    for row in elements(root, "cac:InvoiceLine"):
        quantity = row.find("cbc:InvoicedQuantity", NS)
        rows.append({"id": text(row, "cbc:ID"), "description": text(row, "cac:Item/cbc:Name"),
            "detail": text(row, "cac:Item/cbc:Description"), "quantity": text(row, "cbc:InvoicedQuantity"),
            "unit": quantity.get("unitCode", "") if quantity is not None else "",
            "subtotal": text(row, "cbc:LineExtensionAmount"), "unit_price": text(row, "cac:Price/cbc:PriceAmount"),
            "price_base_quantity": text(row, "cac:Price/cbc:BaseQuantity"),
            "tax_code": text(row, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID"),
            "tax_rate": text(row, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent"), "allowances": allowances(row)})
    extracted = {"seller": seller, "buyer": buyer, "lines": rows,
        "profile_id": text(root, "cbc:ProfileID"), "buyer_reference": text(root, "cbc:BuyerReference"),
        "payee": party(root.find("cac:PayeeParty", NS)),
        "order_reference": text(root, "cac:OrderReference/cbc:ID"), "notes": [item.text or "" for item in elements(root, "cbc:Note")],
        "payment_terms": text(root, "cac:PaymentTerms/cbc:Note"),
        "payment_means": [{"code": text(item, "cbc:PaymentMeansCode"), "reference": text(item, "cbc:PaymentID"),
            "account_id": text(item, "cac:PayeeFinancialAccount/cbc:ID")} for item in elements(root, "cac:PaymentMeans")],
        "taxes": [{"base": text(item, "cbc:TaxableAmount"), "tax": text(item, "cbc:TaxAmount"),
            "code": text(item, "cac:TaxCategory/cbc:ID"), "rate": text(item, "cac:TaxCategory/cbc:Percent"),
            "reason": text(item, "cac:TaxCategory/cbc:TaxExemptionReason"),
            "reason_code": text(item, "cac:TaxCategory/cbc:TaxExemptionReasonCode")} for item in elements(tax, "cac:TaxSubtotal")],
        "allowances": allowances(root), "prepaid": text(root, "cac:LegalMonetaryTotal/cbc:PrepaidAmount"),
        "rounding": text(root, "cac:LegalMonetaryTotal/cbc:PayableRoundingAmount"),
        "attachments": [{"id": text(item, "cbc:ID"), "external_reference": text(item, "cac:Attachment/cac:ExternalReference/cbc:URI"),
            "embedded": item.find("cac:Attachment/cbc:EmbeddedDocumentBinaryObject", NS) is not None}
            for item in elements(root, "cac:AdditionalDocumentReference")]}
    fields = {"invoice_number": text(root, "cbc:ID"), "issue_date": parsed_date("cbc:IssueDate", True),
        "due_date": parsed_date("cbc:DueDate"), "currency": currency,
        "subtotal": amount(text(root, "cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount"), "HT"),
        "tax_total": amount(text(tax, "cbc:TaxAmount"), "TVA"),
        "total": amount(text(root, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"), "TTC"),
        "payable": amount(text(root, "cac:LegalMonetaryTotal/cbc:PayableAmount"), "À payer")}
    if not fields["invoice_number"] or len(fields["invoice_number"]) > 255 or len(currency) != 3:
        raise ValidationError("Numéro de facture absent/trop long ou devise invalide.")
    extracted["extraction_errors"] = errors
    # The supplier's invoice ID is unique in the seller's context, not per buyer/year.
    identity = ("VAT:" + normalized(seller["vat_number"]) if seller["vat_number"] else
        "ENDPOINT:" + seller["endpoint_scheme"] + ":" + seller["endpoint_id"] if seller["endpoint_id"] else
        "LEGAL:" + seller["country"] + ":" + normalized(seller["legal_id"]) if seller["legal_id"] else "")
    business_key = hashlib.sha256(json.dumps([identity, fields["invoice_number"]], ensure_ascii=True).encode()).hexdigest() if identity else None
    return fields, extracted, business_key


def validation(data, fields, extracted):
    if fields["issue_date"] is None:
        return {"status": "INVALID", "details": extracted["extraction_errors"], "rules_version": ""}
    result = validate_xml(data, fields["issue_date"])
    if extracted["extraction_errors"]:
        result["details"] = [*result["details"], *extracted["extraction_errors"]]
        if result["status"] == "VALID":
            result["status"] = "INVALID"
    return result


def seller_enterprise_numbers(seller):
    """Legal registration ID; Belgian 0208 endpoints/party IDs also carry BCE."""
    values = []
    scheme = seller.get("legal_id_scheme", "")
    if seller.get("legal_id") and (scheme in ("", "0208") or seller.get("endpoint_scheme") != "0208"):
        values.append(seller["legal_id"])
    if seller.get("endpoint_scheme") == "0208" and seller.get("endpoint_id"):
        values.append(seller["endpoint_id"])
    values.extend(item["id"] for item in seller.get("identifications", []) if item.get("scheme") == "0208")
    return {normalize_enterprise_number(value) for value in values if value}


def seller_for_matching(invoice):
    seller = invoice.extracted_data["seller"]
    if "legal_id_scheme" not in seller or "identifications" not in seller:
        # Older imports did not retain these attributes. Read the verified
        # original without rewriting its immutable extraction snapshot.
        try:
            _, extracted, _ = parse(read_original(invoice))
            return extracted["seller"]
        except (ValidationError, OSError):
            return {}
    return seller


def supplier_candidates(invoice):
    seller = seller_for_matching(invoice)
    numbers = seller_enterprise_numbers(seller)
    if len(numbers) > 1:
        return []
    if numbers:
        matches = list(Supplier.objects.filter(enterprise_number__in=numbers))
        if matches:
            return matches
    vat = normalized(seller.get("vat_number", ""))
    return [item for item in Supplier.objects.exclude(vat_number__isnull=True).exclude(vat_number="")
        if normalized(item.vat_number) == vat and (not numbers or not item.enterprise_number
            or normalize_enterprise_number(item.enterprise_number) in numbers)] if vat else []


def read_original(invoice):
    with store().open(invoice.storage_path, "rb") as stream:
        data = stream.read(settings.SUPPLIER_XML_MAX_BYTES + 1)
    if len(data) > settings.SUPPLIER_XML_MAX_BYTES or hashlib.sha256(data).hexdigest() != invoice.checksum:
        raise ValidationError("L’intégrité du XML fournisseur archivé n’est plus garantie.")
    return data


@transaction.atomic
def import_invoice(*, actor, data, filename):
    require(actor, "import_supplierinvoice")
    # Serialises duplicate detection on PostgreSQL, also across differing XML bytes.
    profile_lock()
    checksum = hashlib.sha256(data).hexdigest()
    existing = SupplierInvoice.objects.filter(checksum=checksum).first()
    if existing:
        audit(actor, existing, "Import XML identique reconnu", checksum=checksum)
        return existing, False
    fields, extracted, key = parse(data)
    duplicate = SupplierInvoice.objects.filter(business_key=key).first() if key else None
    if duplicate:
        raise ValidationError(f"Une facture du même fournisseur portant ce numéro est déjà importée (import {duplicate.pk}). Le nouveau fichier est différent : vérifiez l’original avant toute correction.")
    result = validation(data, fields, extracted)
    safe_name = PurePosixPath(filename.replace("\\", "/")).name[:255] or "facture.xml"
    invoice = SupplierInvoice(checksum=checksum, business_key=key, original_filename=safe_name,
        extracted_data=extracted, created_by=actor, **fields)
    numbers = seller_enterprise_numbers(extracted["seller"])
    matches = supplier_candidates(invoice)
    if len(numbers) == 1 and len(matches) == 1 and matches[0].enterprise_number:
        seller_vat = normalized(extracted["seller"]["vat_number"])
        if not (seller_vat and matches[0].vat_number and normalized(matches[0].vat_number) != seller_vat):
            invoice.supplier = matches[0]
    # Never use an uploaded filename as a storage path.
    path = f"{timezone.localdate().year}/{uuid4().hex}.xml"
    invoice.storage_path = path
    invoice.full_clean()
    saved_path = store().save(path, ContentFile(data))
    invoice.storage_path = saved_path
    # A failed DB transaction can leave an orphan file; retain it for recovery.
    invoice.save(force_insert=True)
    SupplierInvoiceValidation.objects.create(invoice=invoice, actor=actor, **result)
    audit(actor, invoice, "Facture fournisseur XML importée", checksum=checksum, validation=result["status"])
    return invoice, True


def receiver_check(invoice, issuer):
    buyer = invoice.extracted_data["buyer"]
    checks = []
    for incoming, configured in ((buyer["vat_number"], issuer.vat_number),):
        if incoming and configured:
            checks.append(normalized(incoming) == normalized(configured))
    if buyer["legal_id"] and issuer.legal_id:
        incoming, configured = normalized(buyer["legal_id"]), normalized(issuer.legal_id)
        if buyer["country"] == issuer.country == "BE":
            incoming, configured = incoming.removeprefix("BE"), configured.removeprefix("BE")
        checks.append(incoming == configured)
    if buyer["endpoint_id"] and issuer.peppol_endpoint_id:
        checks.append(buyer["endpoint_scheme"] == issuer.peppol_endpoint_scheme and
            buyer["endpoint_id"].strip() == issuer.peppol_endpoint_id.strip())
    if not checks or not all(checks):
        raise ValidationError("Le destinataire du XML ne correspond pas de façon vérifiable à l’entité configurée. Vérifiez ses identifiants TVA, légaux et Peppol.")


@transaction.atomic
def revalidate_invoice(*, actor, pk):
    require(actor, "revalidate_supplierinvoice")
    profile_lock()
    invoice = SupplierInvoice.objects.select_for_update().get(pk=pk)
    data = read_original(invoice)
    fields, extracted, _ = parse(data)
    result = validation(data, fields, extracted)
    run = SupplierInvoiceValidation.objects.create(invoice=invoice, actor=actor, **result)
    audit(actor, invoice, "XML fournisseur revalidé", validation=result["status"], rules=result["rules_version"])
    return run


@transaction.atomic
def review_invoice(*, actor, pk, revision, supplier, note, action):
    require(actor, "review_supplierinvoice")
    profile = profile_lock()
    invoice = SupplierInvoice.objects.select_for_update().get(pk=pk)
    if invoice.revision != revision or invoice.status != "RECEIVED":
        raise ValidationError("La facture a déjà été revue ou a changé. Rechargez la page.")
    if action not in ("approve", "reject") or not note.strip():
        raise ValidationError("Choisissez une action et renseignez la justification de revue.")
    snapshot = {}
    if action == "approve":
        read_original(invoice)
        latest = invoice.validations.first()
        if not latest or latest.status != "VALID":
            raise ValidationError("L’approbation exige une validation XML complète et réussie.")
        if supplier is None:
            raise ValidationError("Sélectionnez un fournisseur existant.")
        supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
        seller = seller_for_matching(invoice)
        numbers = seller_enterprise_numbers(seller)
        if len(numbers) > 1:
            raise ValidationError("Les numéros d’entreprise déclarés dans le XML sont contradictoires.")
        if numbers and supplier.enterprise_number and normalize_enterprise_number(supplier.enterprise_number) not in numbers:
            raise ValidationError("Le numéro d’entreprise du fournisseur sélectionné ne correspond pas au XML.")
        seller_vat = normalized(seller.get("vat_number", ""))
        company_match = bool(numbers and supplier.enterprise_number and normalize_enterprise_number(supplier.enterprise_number) in numbers)
        if seller_vat and ((supplier.vat_number and normalized(supplier.vat_number) != seller_vat)
                or (not supplier.vat_number and not company_match)):
            raise ValidationError("Le numéro de TVA du fournisseur sélectionné ne correspond pas au XML.")
        if not profile.issuer_id:
            raise ValidationError("Configurez l’entité destinataire avant d’approuver cette facture.")
        issuer = IssuerConfiguration.objects.select_for_update().get(pk=profile.issuer_id)
        receiver_check(invoice, issuer)
        snapshot = {"supplier_id": supplier.pk, "supplier_code": supplier.code, "supplier_name": supplier.name,
            "supplier_enterprise_number": supplier.enterprise_number,
            "supplier_vat": supplier.vat_number or "", "issuer_id": issuer.pk, "issuer_name": issuer.name,
            "issuer_legal_id": issuer.legal_id, "validation_id": latest.pk, "rules_version": latest.rules_version,
            "checksum": invoice.checksum}
    invoice.supplier = supplier if action == "approve" else None
    invoice.status = "REVIEWED" if action == "approve" else "REJECTED"
    invoice.review_note, invoice.review_snapshot = note.strip(), snapshot
    invoice.reviewed_at, invoice.reviewed_by, invoice.reviewed_by_name = timezone.now(), actor, actor.get_username()
    invoice.revision += 1
    invoice.full_clean()
    invoice.save()
    audit(actor, invoice, "Facture fournisseur approuvée" if action == "approve" else "Facture fournisseur rejetée",
        note=note, review=snapshot)
    return invoice
