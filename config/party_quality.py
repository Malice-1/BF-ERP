import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


ADDRESS_FIELDS = (
    ("street", "Adresse"),
    ("zip_code", "Code postal"),
    ("city", "Ville"),
    ("country", "Pays"),
)


def missing_fields(record, fields):
    return [label for field, label in fields if not (getattr(record, field) or "").strip()]


def compact_identifier(value):
    return re.sub(r"[\s.-]", "", (value or "").upper())


def valid_belgian_number(value):
    return bool(re.fullmatch(r"[01][0-9]{9}", value)) and int(value[-2:]) == 97 - int(value[:8]) % 97


def belgian_country(value):
    return value.strip().casefold() in {"be", "belgique", "belgië", "belgium", "belgien"}


def address_issues(record):
    missing = missing_fields(record, ADDRESS_FIELDS)
    postal_code = record.zip_code.strip()
    suspect = []
    if belgian_country(record.country) and postal_code and not re.fullmatch(r"[0-9]{4}", postal_code):
        suspect.append("Code postal belge attendu sur quatre chiffres")
    return missing, suspect


def email_issue(value):
    if value.strip():
        try:
            validate_email(value.strip())
        except ValidationError:
            return "Format du courriel invalide"
    return None


def vat_issue(value, country):
    vat = compact_identifier(value)
    if vat.startswith("BE") or (belgian_country(country) and vat.isascii() and vat.isdigit()):
        if not valid_belgian_number(vat.removeprefix("BE")):
            return "Numéro de TVA belge invalide"
    return None


def review_rows(rows, assess):
    for record in rows:
        missing, suspect = assess(record)
        if missing or suspect:
            yield record, missing, suspect
