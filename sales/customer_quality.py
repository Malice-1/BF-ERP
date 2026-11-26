import re

from config.party_quality import address_issues, email_issue, missing_fields, vat_issue

from .models import InvoiceFormat


def customer_issues(customer):
    missing, suspect = address_issues(customer)
    missing.extend(missing_fields(customer, (
        ("code", "Code"), ("name", "Nom"), ("email", "Courriel"),
        ("invoice_format", "Format de facturation"),
    )))
    if customer.country.strip() and not re.fullmatch(r"[A-Z]{2}", customer.country):
        suspect.append("Code pays attendu sur deux lettres majuscules")
    if error := email_issue(customer.email):
        suspect.append(error)
    if error := vat_issue(customer.vat_number, customer.country):
        suspect.append(error)
    if customer.invoice_format.strip() and customer.invoice_format not in InvoiceFormat.values:
        suspect.append("Format de facturation inconnu")
    if customer.invoice_format == InvoiceFormat.XML:
        missing.extend(missing_fields(customer, (
            ("peppol_endpoint_id", "Identifiant Peppol"), ("peppol_endpoint_scheme", "Schéma Peppol"),
        )))
        if customer.peppol_endpoint_scheme.strip() and not re.fullmatch(r"[0-9]{4}", customer.peppol_endpoint_scheme):
            suspect.append("Schéma Peppol attendu sur quatre chiffres")
    return missing, suspect
