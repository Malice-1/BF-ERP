from zipfile import BadZipFile

from django import forms
from django.core.exceptions import ValidationError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .models import User


HEADERS = ("Nom d’utilisateur", "Nom", "Prénom", "Mail", "Responsable", "Statut")
INITIAL_PASSWORD = "User123!"


class UserImportForm(forms.Form):
    file = forms.FileField(label="Fichier Excel (.xlsx)", widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}))

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".xlsx"):
            raise ValidationError("Sélectionnez un fichier .xlsx.")
        try:
            workbook = load_workbook(upload, read_only=True, keep_links=False)
            try:
                return self.read_users(workbook.worksheets[0])
            finally:
                workbook.close()
        except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError, IndexError, SyntaxError) as exc:
            raise ValidationError("Le fichier Excel est illisible.") from exc

    def read_users(self, sheet):
        rows = sheet.iter_rows(max_col=len(HEADERS))
        headers = [str(cell.value or "").strip().casefold() for cell in next(rows, ())]
        expected = [header.casefold() for header in HEADERS if header not in {"Mail", "Responsable", "Statut"}
                    or header.casefold() in headers]
        if headers[:len(expected)] != expected or any(headers[len(expected):]):
            raise ValidationError("Utilisez le patron Excel des utilisateurs.")

        users = {}
        errors = []
        for number, cells in enumerate(rows, 2):
            values = [str(cell.value).strip() if cell.value is not None else "" for cell in cells]
            if not any(values):
                continue
            if any(values[len(expected):]):
                errors.append(f"Ligne {number} — Une valeur figure dans une colonne sans en-tête.")
                continue
            data = dict(zip(expected, values))
            username, last_name, first_name = (data[header.casefold()] for header in HEADERS[:3])
            email = data.get("mail", "")
            manager = data.get("responsable", "")
            status = data.get("statut", "").casefold()
            user = User(username=User.normalize_username(username), last_name=last_name, first_name=first_name,
                        email=User.objects.normalize_email(email), is_active=status != "inactif")
            manager = User.normalize_username(manager)
            try:
                if any(cell.data_type in {"f", "e"} for cell in cells):
                    raise ValidationError("Utilisez des valeurs sans formule ni erreur Excel.")
                if status not in {"", "actif", "inactif"}:
                    raise ValidationError("Le statut doit être Actif ou Inactif.")
                user.full_clean(exclude={"password"}, validate_unique=False)
                if user.username in users:
                    raise ValidationError(f"L’identifiant {user.username} apparaît plusieurs fois dans le fichier.")
                if manager == user.username:
                    raise ValidationError("Un utilisateur ne peut pas être son propre responsable.")
            except ValidationError as exc:
                errors.append(f"Ligne {number} — {' '.join(exc.messages)}")
            else:
                users[user.username] = (number, user, manager)

        manager_names = {manager for _, _, manager in users.values() if manager}
        existing = User.objects.in_bulk(set(users) | manager_names, field_name="username")
        for username, (number, _, manager) in users.items():
            if username in existing:
                errors.append(f"Ligne {number} — L’utilisateur {username} existe déjà.")
            if manager and manager not in users and manager not in existing:
                errors.append(f"Ligne {number} — Aucun utilisateur avec l’identifiant {manager}.")
        if errors:
            raise ValidationError(errors)
        if not users:
            raise ValidationError("Le fichier ne contient aucun utilisateur à créer.")
        return [(user, manager) for _, user, manager in users.values()], existing
