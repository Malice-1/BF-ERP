from zipfile import BadZipFile

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .models import CostCenter, Funding


REFERENCE_HEADERS = ("Code", "Libellé", "Statut")


class ReferenceImportForm(forms.Form):
    headers = REFERENCE_HEADERS
    file = forms.FileField(label="Fichier Excel (.xlsx)", widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}))

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".xlsx"):
            raise ValidationError("Sélectionnez un fichier .xlsx.")
        try:
            workbook = load_workbook(upload, read_only=True, keep_links=False)
            try:
                return self.read_centers(workbook.worksheets[0])
            finally:
                workbook.close()
        except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError, IndexError, SyntaxError) as exc:
            raise ValidationError("Le fichier Excel est illisible.") from exc

    def read_centers(self, sheet):
        rows = sheet.iter_rows(max_col=len(self.headers))
        headers = tuple(str(cell.value or "").strip().casefold() for cell in next(rows, ()))
        if headers != tuple(header.casefold() for header in self.headers):
            raise ValidationError(f"Utilisez le patron Excel avec les colonnes {', '.join(self.headers)}.")

        centers = {}
        errors = []
        for number, cells in enumerate(rows, 2):
            values = [str(cell.value).strip() if cell.value is not None else "" for cell in cells]
            if not any(values):
                continue
            code, label, status, *manager_values = values
            manager_username = next(iter(manager_values), "")
            try:
                if any(cell.data_type in {"f", "e"} for cell in cells):
                    raise ValidationError("Utilisez des valeurs sans formule ni erreur Excel.")
                if status.casefold() not in {"", "actif", "inactif"}:
                    raise ValidationError("Le statut doit être Actif ou Inactif.")
                if code in centers:
                    raise ValidationError(f"Le code {code} apparaît plusieurs fois dans le fichier.")
                center = self.model(code=code, label=label, is_active=status.casefold() != "inactif")
                center.full_clean(validate_unique=False)
            except ValidationError as exc:
                errors.append(f"Ligne {number} — {' '.join(exc.messages)}")
            else:
                centers[code] = (number, center, manager_username)

        for code in self.model.objects.filter(code__in=centers).values_list("code", flat=True):
            errors.append(f"Ligne {centers[code][0]} — Le {self.model._meta.verbose_name} {code} existe déjà.")
        usernames = {username for _, _, username in centers.values() if username}
        managers = {
            user.username: user
            for user in get_user_model().objects.filter(username__in=usernames, is_active=True)
        }
        for number, _, username in centers.values():
            if username and username not in managers:
                errors.append(f"Ligne {number} — Aucun utilisateur actif avec l’identifiant {username}.")
        if errors:
            raise ValidationError(errors)
        if not centers:
            raise ValidationError(f"Le fichier ne contient aucun {self.model._meta.verbose_name} à créer.")
        return [(center, managers.get(username)) for _, center, username in centers.values()]


class CostCenterImportForm(ReferenceImportForm):
    model = CostCenter
    headers = (*REFERENCE_HEADERS, "Responsable")


class FundingImportForm(ReferenceImportForm):
    model = Funding
