import re
from zipfile import BadZipFile

from django import forms
from django.core.exceptions import ValidationError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .identifiers import normalize_enterprise_number
from .models import Supplier


COLUMNS = (
    ("Code", "code"),
    ("Nom", "name"),
    ("Numéro d’entreprise", "enterprise_number"),
    ("Compte bancaire", "bank_account"),
    ("Adresse", "street"),
    ("Code postal", "zip_code"),
    ("Ville", "city"),
    ("Pays", "country"),
    ("Téléphone", "phone"),
    ("Mobile", "mobile"),
    ("Personne de contact", "contact_person"),
    ("Email", "email"),
)
IMPORT_HEADERS = tuple(label for label, _ in COLUMNS)
EXPORT_HEADERS = (*IMPORT_HEADERS, "Numéro de TVA")


def export_rows(suppliers):
    for supplier in suppliers.iterator():
        values = [getattr(supplier, field) for _, field in COLUMNS]
        yield (*values, supplier.vat_number)


class SupplierImportForm(forms.Form):
    file = forms.FileField(label="Fichier Excel (.xlsx)", widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}))

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".xlsx"):
            raise ValidationError("Sélectionnez un fichier .xlsx.")
        try:
            workbook = load_workbook(upload, read_only=True, keep_links=False)
            try:
                return self.read_suppliers(workbook.worksheets[0])
            finally:
                workbook.close()
        except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError, IndexError, SyntaxError) as exc:
            raise ValidationError("Le fichier Excel est illisible.") from exc

    def read_suppliers(self, sheet):
        rows = sheet.iter_rows(max_col=len(EXPORT_HEADERS))
        headers = [str(cell.value or "").strip().casefold() for cell in next(rows, ())]
        if headers and headers[-1] == "":
            headers.pop()
        if tuple(headers) not in (tuple(h.casefold() for h in IMPORT_HEADERS), tuple(h.casefold() for h in EXPORT_HEADERS)):
            raise ValidationError("Utilisez les colonnes du patron Excel des fournisseurs.")

        suppliers = {}
        errors = []
        for number, cells in enumerate(rows, 2):
            data = dict(zip(
                (field for _, field in COLUMNS),
                (str(cell.value).strip() if cell.value is not None else "" for cell in cells),
            ))
            if not any(data.values()):
                continue
            try:
                if any(cell.data_type in {"f", "e"} for cell in cells):
                    raise ValidationError("Utilisez des valeurs sans formule ni erreur Excel.")
                supplier = self.build_supplier(data, cells[2].value)
                if supplier.code in suppliers:
                    raise ValidationError(f"Le code {supplier.code} apparaît plusieurs fois dans le fichier.")
            except ValidationError as exc:
                errors.append(f"Ligne {number} — {' '.join(exc.messages)}")
            else:
                suppliers[supplier.code] = (number, supplier)

        for code in Supplier.objects.filter(code__in=suppliers).values_list("code", flat=True):
            errors.append(f"Ligne {suppliers[code][0]} — Le fournisseur {code} existe déjà.")
        if errors:
            raise ValidationError(errors)
        if not suppliers:
            raise ValidationError("Le fichier ne contient aucun fournisseur à créer.")
        return [supplier for _, supplier in suppliers.values()]

    @staticmethod
    def build_supplier(data, raw_enterprise):
        if isinstance(raw_enterprise, (int, float)):
            if isinstance(raw_enterprise, bool) or raw_enterprise < 0 or not float(raw_enterprise).is_integer():
                raise ValidationError("Le numéro d’entreprise doit être saisi comme texte ou comme entier positif.")
            digits = str(int(raw_enterprise))
            data["enterprise_number"] = digits.zfill(10) if len(digits) == 9 else digits
        enterprise = normalize_enterprise_number(data["enterprise_number"])
        data["enterprise_number"] = enterprise
        vat = f"BE{enterprise}" if re.fullmatch(r"[01][0-9]{9}", enterprise) else None
        supplier = Supplier(**data, vat_number=vat)
        supplier.full_clean(validate_unique=False)
        return supplier
