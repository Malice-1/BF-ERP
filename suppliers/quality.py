import re

from config.party_quality import (
    ADDRESS_FIELDS, address_issues, belgian_country, compact_identifier, email_issue,
    missing_fields, valid_belgian_number, vat_issue,
)

from .identifiers import normalize_enterprise_number
from .models import Supplier


def supplier_issues(supplier):
    missing = missing_fields(supplier, (
        ("code", "Code"), ("name", "Nom"), ("bank_account", "Compte bancaire"),
    ))
    address = supplier
    address_missing, suspect = address_issues(address)
    if len(address_missing) == len(ADDRESS_FIELDS):
        for legacy_address in supplier.addresses.all():
            absent, issues = address_issues(legacy_address)
            if (len(absent), len(issues)) < (len(address_missing), len(suspect)):
                address, address_missing, suspect = legacy_address, absent, issues
    missing.extend(address_missing)

    contacts = supplier.contacts.all()
    if not any(value.strip() for value in (supplier.email, supplier.phone, supplier.mobile)) and not any(
        contact.email.strip() or contact.phone.strip() for contact in contacts
    ):
        missing.append("Courriel, téléphone ou mobile")
    if not supplier.contact_person.strip() and not any(
        contact.firstname.strip() or contact.lastname.strip() or contact.label.strip() for contact in contacts
    ):
        missing.append("Personne de contact")
    if error := email_issue(supplier.email):
        suspect.append(error)

    enterprise = normalize_enterprise_number(supplier.enterprise_number)
    vat = compact_identifier(supplier.vat_number)
    if not enterprise and not vat:
        missing.append("Numéro d’entreprise ou numéro de TVA")
    if error := vat_issue(vat, address.country):
        suspect.append(error)
    if enterprise and (belgian_country(address.country) or vat.startswith("BE")):
        if not valid_belgian_number(enterprise):
            suspect.append("Numéro d’entreprise belge invalide")
        elif vat.startswith("BE") and enterprise != vat[2:]:
            suspect.append("Le numéro d’entreprise et la TVA belge diffèrent")

    account = "".join(supplier.bank_account.upper().split())
    if account.startswith("BE") and (
        not re.fullmatch(r"BE[0-9]{14}", account) or int(f"{account[4:]}1114{account[2:4]}") % 97 != 1
    ):
        suspect.append("IBAN belge invalide")
    return missing, suspect
