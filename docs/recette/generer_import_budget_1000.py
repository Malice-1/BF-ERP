"""Prepare a 1,000-line workbook and isolated draft in the local demo database."""
import os
import sys
from decimal import Decimal
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.demo_settings"

import django
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from budgeting.models import BudgetProduct, CostCenter, Funding
from config.excel import response
from purchasing.allocation_excel import HEADERS, parse_allocations, import_allocations
from purchasing.models import AnnualEnvelope, EnvelopeVersion
from workflow.models import ConfigurationAuditEvent


def main():
    assert Path(settings.DATABASES["default"]["NAME"]).resolve() == ROOT / "db.demo.sqlite3"
    cdfs = list(CostCenter.objects.order_by("code")[:2])
    funding = Funding.objects.order_by("code").first()
    if len(cdfs) != 2 or funding is None:
        raise RuntimeError("Il faut deux CDF et un financement dans la base de démonstration.")
    actor = get_user_model().objects.get(username="admin")
    products = [(f"CHARGE-{index:04d}", f"Recette import Excel · BI {index:04d}") for index in range(1, 501)]
    with transaction.atomic():
        envelope = AnnualEnvelope.objects.order_by("-year").first()
        if envelope is None:
            raise RuntimeError("Aucune enveloppe annuelle dans la base de démonstration.")
        version, _ = EnvelopeVersion.objects.get_or_create(envelope=envelope, label="RECETTE-IMPORT-1000")
        if version.published_at or version.locked_at or version.deleted_at:
            raise RuntimeError("La version de recette doit rester un brouillon modifiable.")
        existing = dict(BudgetProduct.objects.filter(code__in=[code for code, _ in products]).values_list("code", "label"))
        if any(code in existing and existing[code] != label for code, label in products):
            raise RuntimeError("Un code CHARGE existe déjà avec un autre libellé.")
        missing = [BudgetProduct(code=code, label=label) for code, label in products if code not in existing]
        BudgetProduct.objects.bulk_create(missing)
        ConfigurationAuditEvent.objects.create(actor=actor, action="created", object_type="load_test_dataset", object_id=version.pk,
            payload={"dataset": "IMPORT_BUDGET_1000_LIGNES", "created_products": len(missing), "version": version.label})
    rows = []
    for code, _ in products:
        for cdf in cdfs:
            amount = Decimal("100") + Decimal(len(rows)) * Decimal("0.25")
            rows.append((code, cdf.code, funding.code, amount, envelope.year, version.label))
    total = sum((row[3] for row in rows), Decimal(0))
    workbook = response("import-budget-1000", [
        ("Allocations", HEADERS + ["Année", "Version"], rows),
        ("Produits BI", ["Code BI", "Libellé"], products),
        ("CDF", ["Code CDF", "Libellé"], [(cdf.code, cdf.label) for cdf in cdfs]),
        ("Financements", ["Code financement", "Libellé"], [(funding.code, funding.label)]),
        ("Consignes", ["Information", "Valeur"], [
            ("Version cible", version.label), ("Année", envelope.year),
            ("Lignes de données", len(rows)), ("Total TVAC", total),
            ("Utilisation", "Budget → Alimenter une version → RECETTE-IMPORT-1000 → Importer les allocations Excel"),
            ("Montants", "Budgets totaux fictifs ; aucune version existante n’est alimentée automatiquement."),
        ]),
    ])
    target = Path(__file__).parent / "IMPORT_BUDGET_1000_LIGNES.xlsx"
    target.write_bytes(workbook.content)
    started = perf_counter()
    parsed = parse_allocations(SimpleUploadedFile(target.name, workbook.content), version)
    parse_seconds = perf_counter() - started
    assert len(parsed) == 1000
    assert len({(row["budget_product_id"], row["cost_center_id"], row["funding_id"]) for row in parsed}) == 1000
    before = version.allocations.count()
    started = perf_counter()
    # Exercise the real import, then undo allocations and its audit/history.
    with transaction.atomic():
        counts = import_allocations(actor=actor, version_id=version.pk, rows=parsed, filename=target.name)
        assert version.allocations.count() == 1000
        transaction.set_rollback(True)
    import_seconds = perf_counter() - started
    assert version.allocations.count() == before
    print(f"Fichier : {target}")
    print(f"Version : {envelope.year} / {version.label} (id {version.pk})")
    print(f"Lignes : {len(rows)} ; total TVAC : {total} EUR ; nouveaux produits de recette : {len(missing)}")
    print(f"Contrôle du fichier : {parse_seconds:.2f} s ; import de contrôle annulé : {import_seconds:.2f} s ; {counts}")
    print(f"Allocations conservées dans la version après contrôle : {before}")


if __name__ == "__main__":
    main()
