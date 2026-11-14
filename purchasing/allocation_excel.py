"""Validated XLSX allocation imports; amounts are totals, never additive increments."""
from decimal import Decimal, InvalidOperation
from io import BytesIO
from unicodedata import normalize
from zipfile import ZipFile

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from openpyxl import load_workbook

from budgeting.models import BudgetProduct, CostCenter, Funding
from workflow.models import ConfigurationAuditEvent
from .models import AnnualEnvelope, EnvelopeVersion, Allocation


HEADERS = ["Code BI", "Code CDF", "Code financement", "Montant TVAC"]
MAX_ROWS = 10000


def template_sheets(version=None):
    return [
        ("Allocations", HEADERS, ((line.budget_product.code, line.cost_center.code, line.funding.code, line.amount)
            for line in version.allocations.select_related("budget_product", "cost_center", "funding").order_by("pk")) if version else []),
        ("Produits BI", ["Code BI", "Libellé"], BudgetProduct.objects.order_by("code").values_list("code", "label")),
        ("CDF", ["Code CDF", "Libellé"], CostCenter.objects.order_by("code").values_list("code", "label")),
        ("Financements", ["Code financement", "Libellé"], Funding.objects.order_by("code").values_list("code", "label")),
    ]


def _header(value):
    return " ".join(normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper().split())


def _code(value):
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_allocations(upload, version):
    if not upload.name.lower().endswith(".xlsx") or upload.size > 5 * 1024 * 1024:
        raise ValidationError("Sélectionnez un fichier Excel .xlsx de 5 Mo maximum.")
    content = BytesIO(upload.read())
    try:
        with ZipFile(content) as archive:
            if sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024:
                raise ValidationError("Ce classeur Excel est trop volumineux une fois décompressé.")
        content.seek(0)
        workbook = load_workbook(content, read_only=True, data_only=False, keep_links=False)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("Le fichier ne peut pas être lu comme un classeur Excel .xlsx.") from exc
    try:
        if not workbook.worksheets:
            raise ValidationError("Le classeur ne contient aucune feuille de données.")
        sheet = workbook["Allocations"] if "Allocations" in workbook.sheetnames else workbook.worksheets[0]
        if sheet.max_column and sheet.max_column > 30:
            raise ValidationError("Utilisez la feuille Allocations du modèle, avec ses colonnes d’origine.")
        if sheet.max_row and sheet.max_row > MAX_ROWS + 1:
            raise ValidationError(f"Le fichier dépasse la limite de {MAX_ROWS} lignes.")
        iterator = sheet.iter_rows(max_row=MAX_ROWS + 2)
        header_cells = next(iterator, ())
        names = [_header(cell.value) for cell in header_cells]
        required = [_header(name) for name in HEADERS]
        if any(names.count(name) != 1 for name in required):
            raise ValidationError("Colonnes requises, une seule fois chacune : " + ", ".join(HEADERS) + ".")
        positions = {name: names.index(name) for name in required}
        references = {
            "CODE BI": dict(BudgetProduct.objects.values_list("code", "pk")),
            "CODE CDF": dict(CostCenter.objects.values_list("code", "pk")),
            "CODE FINANCEMENT": dict(Funding.objects.values_list("code", "pk")),
        }
        result, errors, seen = [], [], set()
        amount_field = Allocation._meta.get_field("amount")
        for row_number, cells in enumerate(iterator, 2):
            if all(cell.value is None or str(cell.value).strip() == "" for cell in cells):
                continue
            if row_number > MAX_ROWS + 1:
                errors.append(f"Le fichier dépasse la limite de {MAX_ROWS} lignes.")
                break
            try:
                if any(cell.data_type in ("f", "e") for cell in cells):
                    raise ValidationError("Les formules et cellules en erreur ne sont pas acceptées. Collez les valeurs.")
                if "ANNEE" in names and _code(cells[names.index("ANNEE")].value) != str(version.envelope.year):
                    raise ValidationError("L’année ne correspond pas à la version sélectionnée.")
                if "VERSION" in names and _code(cells[names.index("VERSION")].value) != version.label:
                    raise ValidationError("La version du fichier ne correspond pas à la version sélectionnée.")
                codes = {name: _code(cells[positions[name]].value) for name in references}
                for name, mapping in references.items():
                    if codes[name] not in mapping:
                        raise ValidationError(f"{name} inconnu ou vide : {codes[name] or '(vide)' }.")
                key = tuple(codes[name] for name in references)
                if key in seen:
                    raise ValidationError("Cette combinaison BI, CDF et financement figure plusieurs fois dans le fichier.")
                seen.add(key)
                raw = cells[positions["MONTANT TVAC"]].value
                if raw is None or isinstance(raw, bool):
                    raise ValidationError("Le montant TVAC est obligatoire et doit être un nombre positif ou nul.")
                text = str(raw).replace(" ", "").replace("\u00a0", "").replace("\u202f", "").replace(",", ".")
                try:
                    amount = Decimal(text)
                except InvalidOperation:
                    raise ValidationError("Montant TVAC invalide.")
                if not amount.is_finite() or amount < 0:
                    raise ValidationError("Le montant TVAC doit être positif ou nul.")
                amount = amount_field.clean(amount, None)
                result.append({"row": row_number, "budget_product_id": references["CODE BI"][codes["CODE BI"]],
                    "cost_center_id": references["CODE CDF"][codes["CODE CDF"]],
                    "funding_id": references["CODE FINANCEMENT"][codes["CODE FINANCEMENT"]], "amount": amount})
            except ValidationError as exc:
                errors.extend(f"Ligne {row_number} : {message}" for message in exc.messages)
                if len(errors) >= 50:
                    errors.append("Corrigez ces erreurs avant de relancer l’import.")
                    break
        if errors:
            raise ValidationError(errors)
        if not result:
            raise ValidationError("Le fichier ne contient aucune allocation à importer.")
        return result
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("Le contenu du classeur est invalide. Utilisez le modèle Excel proposé.") from exc
    finally:
        workbook.close()


@transaction.atomic
def import_allocations(*, actor, version_id, rows, filename):
    from .budget_views import MANAGER_PERMISSIONS
    if not actor.is_active or not actor.has_perms(MANAGER_PERMISSIONS):
        raise PermissionDenied
    initial = EnvelopeVersion.objects.get(pk=version_id)
    AnnualEnvelope.objects.select_for_update().get(pk=initial.envelope_id)
    version = EnvelopeVersion.objects.select_for_update().get(pk=version_id)
    if not version.allocations_editable:
        raise ValidationError("Cette version est en lecture seule, bloquée ou supprimée. Aucun import effectué.")
    if version.published_at and not actor.is_superuser:
        raise PermissionDenied
    existing = {(line.budget_product_id, line.cost_center_id, line.funding_id): line for line in version.allocations.all()}
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    to_create, to_update, changes = [], [], []
    for row in rows:
        key = (row["budget_product_id"], row["cost_center_id"], row["funding_id"])
        line = existing.get(key)
        if line and line.amount == row["amount"]:
            counts["unchanged"] += 1
            continue
        if line:
            previous = line.amount
            line.amount = row["amount"]
            counts["updated"] += 1
            to_update.append(line)
        else:
            previous = None
            line = Allocation(version=version, **{name: row[name] for name in ("budget_product_id", "cost_center_id", "funding_id", "amount")})
            counts["created"] += 1
            to_create.append(line)
        line.full_clean()
        changes.append({"row": row["row"], "budget_product_id": key[0], "cost_center_id": key[1],
            "funding_id": key[2], "before": str(previous) if previous is not None else None, "after": str(line.amount)})
        existing[key] = line
    # Parent locks and editability checks above apply to the whole import. Record
    # one final budget snapshot instead of a full snapshot for each imported row.
    Allocation.objects.bulk_create(to_create, batch_size=500)
    Allocation.objects.bulk_update(to_update, ["amount"], batch_size=500)
    if changes:
        from budgeting.history import capture
        capture(version.envelope_id, f"Import Excel : {counts['created']} allocation(s) créée(s), "
            f"{counts['updated']} modifiée(s)", actor=actor, version_id=version.pk)
    ConfigurationAuditEvent.objects.create(actor=actor, action="budget.allocations_import",
        object_type="budget_version", object_id=version.pk,
        payload={"filename": filename, **counts, "mode": "replace_listed_totals", "changes": changes})
    return counts
