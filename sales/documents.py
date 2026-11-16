"""Offline document generation, full validation and private versioned archives."""
import hashlib
import json
import logging
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction

from .models import SalesInvoice, InvoiceDocument, InvoiceValidationRun


logger = logging.getLogger(__name__)
NS = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
      "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"}
UBL = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"


def xml_invoice(invoice, lines):
    from lxml import etree
    root = etree.Element(f"{{{UBL}}}Invoice", nsmap={None: UBL, **NS})

    def node(parent, name, value=None, **attrs):
        prefix, local = name.split(":")
        result = etree.SubElement(parent, f"{{{NS[prefix]}}}{local}", **attrs)
        if value is not None:
            result.text = str(value)
        return result

    def amount(parent, name, value):
        return node(parent, name, value, currencyID=invoice.currency)

    def tax_category(parent, data):
        node(parent, "cbc:ID", data["code"])
        if data["code"] != "O":
            node(parent, "cbc:Percent", data["rate"])
        if data.get("reason"):
            node(parent, "cbc:TaxExemptionReason", data["reason"])
        node(node(parent, "cac:TaxScheme"), "cbc:ID", "VAT")

    def party(parent_name, data, supplier=False):
        parent = node(node(root, parent_name), "cac:Party")
        node(parent, "cbc:EndpointID", data["peppol_endpoint_id"], schemeID=data["peppol_endpoint_scheme"])
        node(node(parent, "cac:PartyName"), "cbc:Name", data["name"])
        address = node(parent, "cac:PostalAddress")
        node(address, "cbc:StreetName", data["street"])
        node(address, "cbc:CityName", data["city"])
        node(address, "cbc:PostalZone", data["zip_code"])
        node(node(address, "cac:Country"), "cbc:IdentificationCode", data["country"])
        if data.get("vat_number") and not all(group["code"] == "O" for group in invoice.tax_breakdown):
            tax = node(parent, "cac:PartyTaxScheme")
            node(tax, "cbc:CompanyID", data["vat_number"])
            node(node(tax, "cac:TaxScheme"), "cbc:ID", "VAT")
        legal = node(parent, "cac:PartyLegalEntity")
        node(legal, "cbc:RegistrationName", data["name"])
        if supplier:
            node(legal, "cbc:CompanyID", data["legal_id"])
        if data.get("email"):
            node(node(parent, "cac:Contact"), "cbc:ElectronicMail", data["email"])

    node(root, "cbc:CustomizationID", "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0")
    node(root, "cbc:ProfileID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    node(root, "cbc:ID", invoice.number)
    node(root, "cbc:IssueDate", invoice.issue_date.isoformat())
    node(root, "cbc:DueDate", invoice.due_date.isoformat())
    node(root, "cbc:InvoiceTypeCode", "380")
    if not invoice.order_snapshot["customer_reference"]:
        node(root, "cbc:Note", "Commande de vente : " + invoice.order_snapshot["number"])
    node(root, "cbc:DocumentCurrencyCode", invoice.currency)
    if invoice.customer_snapshot.get("reference"):
        node(root, "cbc:BuyerReference", invoice.customer_snapshot["reference"])
    if invoice.order_snapshot["customer_reference"]:
        reference = node(root, "cac:OrderReference")
        node(reference, "cbc:ID", invoice.order_snapshot["customer_reference"])
        node(reference, "cbc:SalesOrderID", invoice.order_snapshot["number"])
    party("cac:AccountingSupplierParty", invoice.issuer_snapshot, True)
    party("cac:AccountingCustomerParty", invoice.customer_snapshot)
    payment = node(root, "cac:PaymentMeans")
    node(payment, "cbc:PaymentMeansCode", "30")
    node(payment, "cbc:PaymentID", invoice.number)
    node(node(payment, "cac:PayeeFinancialAccount"), "cbc:ID", invoice.issuer_snapshot["iban"])
    if invoice.customer_snapshot.get("payment_terms"):
        node(node(root, "cac:PaymentTerms"), "cbc:Note", invoice.customer_snapshot["payment_terms"])
    tax = node(root, "cac:TaxTotal")
    amount(tax, "cbc:TaxAmount", invoice.tax_total)
    for group in invoice.tax_breakdown:
        subtotal = node(tax, "cac:TaxSubtotal")
        amount(subtotal, "cbc:TaxableAmount", group["base"])
        amount(subtotal, "cbc:TaxAmount", group["tax"])
        tax_category(node(subtotal, "cac:TaxCategory"), group)
    monetary = node(root, "cac:LegalMonetaryTotal")
    amount(monetary, "cbc:LineExtensionAmount", invoice.subtotal)
    amount(monetary, "cbc:TaxExclusiveAmount", invoice.subtotal)
    amount(monetary, "cbc:TaxInclusiveAmount", invoice.total)
    amount(monetary, "cbc:PayableAmount", invoice.total)
    for line in lines:
        item = node(root, "cac:InvoiceLine")
        node(item, "cbc:ID", line.position)
        node(item, "cbc:InvoicedQuantity", line.quantity, unitCode=line.unit)
        amount(item, "cbc:LineExtensionAmount", line.subtotal)
        if line.service_start:
            period = node(item, "cac:InvoicePeriod")
            node(period, "cbc:StartDate", line.service_start.isoformat())
            node(period, "cbc:EndDate", line.service_end.isoformat())
        if line.discount:
            discount = node(item, "cac:AllowanceCharge")
            node(discount, "cbc:ChargeIndicator", "false")
            node(discount, "cbc:AllowanceChargeReason", "Remise commerciale")
            amount(discount, "cbc:Amount", line.discount)
        product = node(item, "cac:Item")
        node(product, "cbc:Name", line.description)
        # Exemption reasons belong to the VAT breakdown, not the item category.
        tax_category(node(product, "cac:ClassifiedTaxCategory"),
            {"code": line.tax_code, "rate": line.tax_rate})
        amount(node(item, "cac:Price"), "cbc:PriceAmount", line.unit_price)
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)


def pdf_invoice(invoice, lines):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle

    output = BytesIO()
    styles = getSampleStyleSheet()
    p = lambda text: Paragraph(escape(str(text)).replace("\n", "<br/>"), styles["BodyText"])
    story = [Paragraph("FACTURE " + escape(invoice.number), styles["Title"]), Spacer(1, 6 * mm)]
    for title, data in (("Émetteur", invoice.issuer_snapshot), ("Client", invoice.customer_snapshot)):
        story.append(Paragraph(title, styles["Heading2"]))
        for value in (data["name"], data["street"], f'{data["zip_code"]} {data["city"]} — {data["country"]}',
                f'TVA : {data["vat_number"]}' if data["vat_number"] else "", data.get("legal_id", "")):
            if value:
                story.append(p(value))
    story += [Spacer(1, 4 * mm), p(f"Émission : {invoice.issue_date:%d/%m/%Y} — Échéance : {invoice.due_date:%d/%m/%Y}"),
        p(f'Commande : {invoice.order_snapshot["number"]} — Référence client : {invoice.order_snapshot["customer_reference"] or "—"}'),
        Spacer(1, 5 * mm)]
    rows = [[p(s) for s in ("Formation", "Qté / unité", "PU HT", "Remise HT", "TVA", "HT")]]
    for line in lines:
        description = line.description
        if line.service_start:
            description += f"\nPrestation du {line.service_start:%d/%m/%Y} au {line.service_end:%d/%m/%Y}"
        rows.append([p(description), p(f"{line.quantity:f} {line.unit}"), p(f"{line.unit_price:f}"),
            p(f"{line.discount:.2f}"), p(f"{line.tax_code} / {line.tax_rate:f}%"), p(f"{line.subtotal:.2f}")])
    table = LongTable(rows, colWidths=[60*mm, 28*mm, 25*mm, 23*mm, 26*mm, 22*mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce8f2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), .3, colors.lightgrey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [table, Spacer(1, 5*mm)]
    for group in invoice.tax_breakdown:
        story.append(p(f'TVA {group["code"]} {group["rate"]}% — Base : {group["base"]} — Taxe : {group["tax"]} {invoice.currency}'))
        if group["reason"]:
            story.append(p(group["reason"]))
    for label, value in (("Total HT", invoice.subtotal), ("TVA", invoice.tax_total), ("Total TTC", invoice.total)):
        story.append(p(f"{label} : {value:.2f} {invoice.currency}"))
    story += [Spacer(1, 4*mm), p(f'Paiement par virement : {invoice.issuer_snapshot["iban"]}'),
        p(f"Communication : {invoice.number}"), p(invoice.customer_snapshot.get("payment_terms", ""))]

    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(14*mm, 10*mm, invoice.number)
        canvas.drawRightString(196*mm, 10*mm, f"Page {document.page}")

    SimpleDocTemplate(output, pagesize=A4, rightMargin=13*mm, leftMargin=13*mm,
        topMargin=14*mm, bottomMargin=18*mm, title=invoice.number).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def render_document(invoice, lines):
    return xml_invoice(invoice, lines) if invoice.invoice_format == "PEPPOL_XML" else pdf_invoice(invoice, lines)


def validate_xml(data, issue_date):
    """Fail closed if any artifact/engine/date check is missing. Never uses HTTP."""
    result = {"status": "UNAVAILABLE", "details": [], "rules_version": ""}
    try:
        from lxml import etree
        from saxonche import PySaxonProcessor
        root = Path(settings.SALES_RULES_ROOT)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        result["rules_version"] = manifest["version"]
        required = {"xsd/maindoc/UBL-Invoice-2.1.xsd", "CEN-EN16931-UBL.xsl", "PEPPOL-EN16931-UBL.xsl"}
        if not required.issubset(manifest["files"]):
            raise ValueError("Le manifeste de validation est incomplet.")
        if not date.fromisoformat(manifest["valid_from"]) <= issue_date < date.fromisoformat(manifest["valid_until"]):
            raise ValueError("Aucun jeu de règles approuvé pour la date d’émission.")
        for relative, entry in manifest["files"].items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("Chemin de règle non autorisé.")
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError(f"Empreinte de règle incorrecte : {relative}")
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        document = etree.fromstring(data, parser)
        if document.getroottree().docinfo.doctype:
            raise ValueError("Les déclarations DTD sont interdites.")
        schema = etree.XMLSchema(etree.parse(str(root / "xsd/maindoc/UBL-Invoice-2.1.xsd"), parser))
        if not schema.validate(document):
            result["status"] = "INVALID"
            result["details"] = [{"stage": "XSD", "message": str(error)} for error in schema.error_log]
            return result
        failures = []
        with PySaxonProcessor(license=False) as proc:
            xslt = proc.new_xslt30_processor()
            source = proc.parse_xml(xml_text=data.decode("utf-8"))
            for name in ("CEN-EN16931-UBL", "PEPPOL-EN16931-UBL"):
                executable = xslt.compile_stylesheet(stylesheet_file=str(root / (name + ".xsl")))
                report = executable.transform_to_string(xdm_node=source)
                svrl = etree.fromstring(report.encode("utf-8"), parser)
                for failure in svrl.findall(".//{http://purl.oclc.org/dsdl/svrl}failed-assert"):
                    failures.append({"stage": name, "id": failure.get("id"), "flag": failure.get("flag", "fatal"),
                        "location": failure.get("location"), "message": " ".join(failure.itertext()).strip()})
        result["details"] = failures
        result["status"] = "INVALID" if any(e["flag"].lower() not in ("warning", "info") for e in failures) else "VALID"
    except Exception as error:
        logger.warning("Invoice validation unavailable: %s", error)
        result["details"].append({"stage": "ENGINE", "message": str(error)})
    return result


def storage():
    return private_storage(settings.SALES_DOCUMENT_ROOT)


def private_storage(location):
    return FileSystemStorage(location=location)


def read_document(document):
    with storage().open(document.storage_path, "rb") as stream:
        data = stream.read()
    if hashlib.sha256(data).hexdigest() != document.checksum:
        raise ValidationError("L’intégrité du document archivé n’est plus garantie.")
    return data


def archive(pk, actor, data, validation=None):
    from .services import event
    try:
        with transaction.atomic():
            invoice = SalesInvoice.objects.select_for_update().get(pk=pk)
            if invoice.invoice_format == "PEPPOL_XML" and validation is None:
                validation = validate_xml(data, invoice.issue_date)
            suffix = "xml" if invoice.invoice_format == "PEPPOL_XML" else "pdf"
            saved_path = storage().save(f"{invoice.issue_date.year}/{invoice.pk}/{uuid4().hex}.{suffix}", ContentFile(data))
            document = InvoiceDocument.objects.create(invoice=invoice, document_type=invoice.invoice_format,
                storage_path=saved_path, checksum=hashlib.sha256(data).hexdigest())
            InvoiceValidationRun.objects.create(document=document, **(validation or {
                "status": "NOT_REQUIRED", "details": [], "rules_version": ""}))
            invoice.document_status = "ISSUED" if validation is None or validation["status"] == "VALID" else "DOCUMENT_ERROR"
            invoice.document_error = "" if invoice.document_status == "ISSUED" else json.dumps(validation["details"], ensure_ascii=False)
            invoice.save(update_fields=["document_status", "document_error"])
            event(invoice.order, actor, "Document archivé", invoice=invoice,
                document=document.pk, checksum=document.checksum, validation=validation)
            return document
    except Exception as error:
        logger.exception("Could not archive invoice %s", pk)
        # Do not delete or renumber an invoice on storage/DB failure.
        with transaction.atomic():
            invoice = SalesInvoice.objects.select_for_update().get(pk=pk)
            invoice.document_status = "DOCUMENT_ERROR"
            invoice.document_error = "Échec d’archivage. Régénérez le document ou contactez l’administrateur."
            invoice.save(update_fields=["document_status", "document_error"])
            event(invoice.order, actor, "Erreur documentaire", invoice=invoice, error=type(error).__name__)
        return None


def regenerate(*, actor, pk):
    from .services import require, event
    require(actor, "regenerate_salesinvoice")
    invoice = SalesInvoice.objects.get(pk=pk)
    try:
        data = render_document(invoice, list(invoice.lines.all()))
    except Exception as error:
        with transaction.atomic():
            invoice = SalesInvoice.objects.select_for_update().get(pk=pk)
            invoice.document_status = "DOCUMENT_ERROR"
            invoice.document_error = "La génération a échoué. Contactez l’administrateur."
            invoice.save(update_fields=["document_status", "document_error"])
            event(invoice.order, actor, "Erreur de génération", invoice=invoice, error=type(error).__name__)
        return None
    return archive(pk, actor, data)


@transaction.atomic
def revalidate(*, actor, pk, document_id):
    from .services import require, event
    require(actor, "regenerate_salesinvoice")
    invoice = SalesInvoice.objects.select_for_update().get(pk=pk)
    document = invoice.documents.get(pk=document_id)
    if document.document_type != "PEPPOL_XML":
        raise ValidationError("Seuls les documents XML nécessitent cette validation.")
    data = read_document(document)
    result = validate_xml(data, invoice.issue_date)
    run = InvoiceValidationRun.objects.create(document=document, **result)
    if invoice.documents.first().pk == document.pk:
        invoice.document_status = "ISSUED" if result["status"] == "VALID" else "DOCUMENT_ERROR"
        invoice.document_error = "" if result["status"] == "VALID" else json.dumps(result["details"], ensure_ascii=False)
        invoice.save(update_fields=["document_status", "document_error"])
    event(invoice.order, actor, "Document revalidé", invoice=invoice, document=document.pk, validation=result)
    return run
