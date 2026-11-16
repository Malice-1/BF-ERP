import re


def normalize_enterprise_number(value):
    """Normalise registration formatting, keeping significant leading zeroes."""
    value = re.sub(r"[\s.\-]", "", (value or "").upper())
    if value.startswith("BE") and re.fullmatch(r"[0-9]{10}", value[2:]):
        value = value[2:]
    return value
