"""Actualise le classeur ODS en conservant les résultats, avant export Excel."""
from copy import deepcopy
from collections import Counter
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile
import argparse

ROOT = Path(__file__).resolve().parent
ODS = ROOT / "BF_ERP_Recette_Complete_Enrichie.ods"
NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
}


def q(prefix, name):
    return "{" + NS[prefix] + "}" + name


def value(cell):
    return "\n".join("".join(p.itertext()) for p in cell.findall("text:p", NS))


def cells(row, width):
    result = []
    for cell in row.findall("table:table-cell", NS):
        repeat = min(int(cell.get(q("table", "number-columns-repeated"), 1)), width - len(result))
        for _ in range(repeat):
            item = deepcopy(cell)
            item.attrib.pop(q("table", "number-columns-repeated"), None)
            result.append(item)
        if len(result) == width:
            break
    while len(result) < width:
        result.append(ET.Element(q("table", "table-cell")))
    return result


def set_value(cell, text):
    for name in list(cell.attrib):
        if name.startswith("{" + NS["office"] + "}") or name.endswith("}formula") or name.endswith("}value-type"):
            del cell.attrib[name]
    for child in list(cell):
        cell.remove(child)
    cell.set(q("office", "value-type"), "string")
    ET.SubElement(cell, q("text", "p")).text = text


def new_row(values):
    row = ET.Element(q("table", "table-row"))
    for text in values:
        cell = ET.SubElement(row, q("table", "table-cell"))
        set_value(cell, text)
    return row


def normalized_test_cells(row):
    items = cells(row, 13)
    # L'ancien générateur plaçait les lignes des tableaux Markdown une colonne
    # trop à gauche. Recaler aussi leurs champs de suivi, sans en perdre le texte.
    if value(items[4]) in {"Haute", "Critique", "Moyenne", "Basse"}:
        if any(value(c) for c in items[12:]):
            raise ValueError("Colonne supplémentaire renseignée : vérifier la ligne avant de la décaler.")
        items = items[:3] + [ET.Element(q("table", "table-cell"))] + items[3:12]
    return items


def tracking(table):
    result = {}
    for row in table.findall("table:table-row", NS)[1:]:
        items = normalized_test_cells(row)
        test_id = value(items[0])
        if re.fullmatch(r"[A-Z]+-\d+", test_id):
            if test_id in result:
                raise ValueError(f"Identifiant dupliqué : {test_id}")
            result[test_id] = tuple(value(c) for c in items[6:13])
    return result


def main(source_path=ODS, output_path=None):
    output_path = output_path or source_path
    if output_path.resolve() == source_path.resolve() and source_path.with_name(f".~lock.{source_path.name}#").exists():
        raise SystemExit("Classeur ouvert : utilisez --output pour créer une copie sans écraser le fichier en cours d’édition.")
    with ZipFile(source_path) as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    raw = dict((info.filename, data) for info, data in entries)["content.xml"]
    namespaces = {}
    for _, pair in ET.iterparse(BytesIO(raw), events=["start-ns"]):
        namespaces[pair[0]] = pair[1]
        ET.register_namespace(*pair)
    document = ET.fromstring(raw)
    automatic_styles = document.find("office:automatic-styles", NS)
    if not any(s.get(q("style", "name")) == "RecetteBody" for s in automatic_styles):
        style = ET.SubElement(automatic_styles, q("style", "style"), {
            q("style", "name"): "RecetteBody", q("style", "family"): "table-cell"})
        ET.SubElement(style, q("style", "table-cell-properties"), {
            q("fo", "wrap-option"): "wrap", q("style", "vertical-align"): "top"})
        row_style = ET.SubElement(automatic_styles, q("style", "style"), {
            q("style", "name"): "RecetteRow", q("style", "family"): "table-row"})
        ET.SubElement(row_style, q("style", "table-row-properties"), {
            q("style", "use-optimal-row-height"): "true", q("style", "min-row-height"): "0.5cm"})
    tables = {t.get(q("table", "name")).replace("_", " "): t for t in document.findall(".//table:table", NS)}
    tests = tables["Tests de recette"]
    before = tracking(tests)
    markdown = (ROOT / "RECETTE_COMPLETE.md").read_text(encoding="utf-8")
    descriptions = {}
    references = {}
    for line in markdown.splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) == 3 and re.fullmatch(r"[A-Z]+-\d+", parts[0]):
            descriptions[parts[0]] = parts[1:]
            references[parts[0]] = "RECETTE_COMPLETE.md"
    extension = (ROOT / "TRANSFERTS_ET_STOCK.md").read_text(encoding="utf-8")
    extension_ids = []
    for line in extension.splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) == 3 and re.fullmatch(r"[A-Z]+-\d+", parts[0]):
            if parts[0] in extension_ids:
                raise ValueError(f"Identifiant dupliqué dans l’extension : {parts[0]}")
            descriptions[parts[0]] = parts[1:]
            references[parts[0]] = "TRANSFERTS_ET_STOCK.md"
            extension_ids.append(parts[0])

    for row in tests.findall("table:table-row", NS)[1:]:
        items = normalized_test_cells(row)
        test_id = value(items[0])
        if test_id not in before:
            continue
        if test_id in descriptions:
            action, expected = descriptions[test_id]
            set_value(items[2], action)
            set_value(items[3], f"{references[test_id]} — {test_id}")
            set_value(items[4], "Contrôles techniques réussis ; fichiers : " + expected if test_id.startswith("TEC-") else expected)
        elif test_id.startswith("TEC-"):
            # Les références techniques se trouvaient dans l'ancienne colonne Attendu.
            reference = value(items[4])
            if reference.endswith(".py"):
                set_value(items[3], reference)
                set_value(items[4], "Contrôles techniques réussis ; voir section 14.")
        if test_id == "HAB-02":
            set_value(items[2], "Responsables des CDF et des supports")
            set_value(items[4], "Affectations multiples persistantes ; comptes actifs ; aucun rôle ni habilitation supplémentaire pour ce mode.")
        for old in list(row):
            row.remove(old)
        row.extend(items)

    descriptions.update({
        "ADM-07": (
            "Après un cycle DA → BC, supprimer des comptes de test demandeur/valideur ; vérifier journal, preuves, commande et engagement. Tester candidat en attente, valideur nommé supprimé, nom recréé et refus hors superadministrateur.",
            "Traces et identifiants historiques conservés ; DA/BC et engagement maintenus ; candidat supprimé non éligible ; aucun remplacement implicite du valideur nommé ; journal en lecture seule."),
        "ADM-08": (
            "En fin de campagne, tester les suppressions de maintenance de rôles, référentiels, versions publiées et étapes ; vérifier les dépendances avant confirmation et les suppressions groupées ; essayer hors superadministrateur.",
            "Dépendances annoncées ; traces maintenance conservées ; suppression d’étape arrête le cycle, libère les réservations et remet la DA en correction ; journal non supprimable ; accès refusé hors superadministrateur."),
    })
    technical_ids = [test_id for test_id in descriptions if test_id.startswith("TEC-")]
    new_ids = ["ADM-07", "ADM-08"] + [f"RSP-{i:02}" for i in range(1, 16)] + extension_ids + technical_ids
    for test_id in new_ids:
        if test_id in before:
            continue
        action, expected = descriptions[test_id]
        section = "17. Responsables par CDF et par support" if test_id.startswith("RSP-") else "Administration — conservation des traces et maintenance"
        if test_id in extension_ids:
            section = {"WF": "Workflows manuels et automatiques", "TB": "Transferts budgétaires", "STK": "Gestion de stock", "SEC": "Sécurité transferts et stock"}[test_id.split("-")[0]]
        if test_id.startswith("TEC-"):
            section = "14. Vérifications techniques complémentaires"
            expected = "Contrôles techniques réussis ; fichiers : " + expected
        row = new_row([test_id, section, action,
                       f"{references.get(test_id, 'RECETTE_COMPLETE.md')} — {test_id}", expected, "Haute", "Non exécuté"] + [""] * 6)
        row_cells = row.findall("table:table-cell", NS)
        row_cells[5].set(q("table", "content-validation-name"), "val1")
        row_cells[6].set(q("table", "content-validation-name"), "val2")
        empty = next((r for r in tests.findall("table:table-row", NS)[1:] if not value(cells(r, 1)[0])), None)
        tests.insert(list(tests).index(empty) if empty is not None else len(tests), row)

    scenarios = tables["Scénarios métier"]
    scenario = next((r for r in scenarios.findall("table:table-row", NS) if value(cells(r, 1)[0]) == "S09"), None)
    if scenario is None:
        scenario = new_row(["S09", "Responsables par CDF et support", "RSP-01 à RSP-15", "Non exécuté", "", ""])
    else:
        scenarios.remove(scenario)
    empty = next((r for r in scenarios.findall("table:table-row", NS)[1:] if not value(cells(r, 1)[0])), None)
    scenarios.insert(list(scenarios).index(empty) if empty is not None else len(scenarios), scenario)
    for scenario_id, label, ids in [
        ("S10", "Workflows manuels et automatiques", "WF-12 à WF-19"),
        ("S11", "Transferts budgétaires", "TB-01 à TB-12 ; SEC-03 à SEC-05"),
        ("S12", "Gestion de stock", "STK-01 à STK-08 ; SEC-03 à SEC-05"),
    ]:
        if any(value(cells(r, 1)[0]) == scenario_id for r in scenarios.findall("table:table-row", NS)):
            continue
        empty = next((r for r in scenarios.findall("table:table-row", NS)[1:] if not value(cells(r, 1)[0])), None)
        row = new_row([scenario_id, label, ids, "Non exécuté", "", ""])
        scenarios.insert(list(scenarios).index(empty) if empty is not None else len(scenarios), row)
    mode = tables["Mode emploi"]
    excluded = tables.get("Hors périmètre")
    if excluded is not None:
        for row in excluded.findall("table:table-row", NS)[1:]:
            items = cells(row, 2)
            if "stock" in value(items[0]).lower():
                set_value(items[0], "Clôture annuelle, règles comptables, valorisation du stock et ventes")
                for child in list(row):
                    row.remove(child)
                row.extend(items)
    for row in mode.findall("table:table-row", NS):
        items = cells(row, 2)
        if value(items[0]) == "Référence":
            set_value(items[1], "RECETTE_COMPLETE.md et TRANSFERTS_ET_STOCK.md — périmètre du 09/11/2026")
            for child in list(row):
                row.remove(child)
            row.extend(items)
    if not any(value(cells(r, 1)[0]) == "Résultats conservés" for r in mode.findall("table:table-row", NS)):
        mode.append(new_row(["Résultats conservés", "Statuts et champs de suivi antérieurs préservés ; nouveaux tests non exécutés. Si une procédure change, dater le retest sans effacer la preuve historique."]))

    after = tracking(tests)
    assert all(after[test_id] == fields for test_id, fields in before.items()), "Un champ de suivi a changé"
    assert set(after) == set(before) | set(new_ids)
    counts = Counter(fields[0] for fields in after.values())
    dashboard = tables["Tableau de bord"]
    formulas = {
        "Total tests": 'COUNTA([$\'Tests de recette\'.A2:.A500])',
        "OK": 'COUNTIF([$\'Tests de recette\'.G2:.G500];"OK")',
        "KO": 'COUNTIF([$\'Tests de recette\'.G2:.G500];"KO")',
        "Bloqué": 'COUNTIF([$\'Tests de recette\'.G2:.G500];"Bloqué")',
        "Non exécuté": 'COUNTIF([$\'Tests de recette\'.G2:.G500];"Non exécuté")',
        "Taux exécuté": 'IFERROR((B3+B4)/B2;0)',
        "Taux réussite (exécutés)": 'IFERROR(B3/(B3+B4);0)',
        "Anomalies ouvertes": 'COUNTIFS([$Anomalies.A2:.A500];"<>";[$Anomalies.I2:.I500];"Ouverte")',
    }
    total = len(after)
    executed = counts["OK"] + counts["KO"]
    cached = {"Total tests": total, **counts, "Taux exécuté": executed / total,
              "Taux réussite (exécutés)": counts["OK"] / executed if executed else 0,
              "Anomalies ouvertes": sum(bool(value(cells(r, 9)[0])) and value(cells(r, 9)[8]) == "Ouverte"
                                       for r in tables["Anomalies"].findall("table:table-row", NS)[1:])}
    for row in dashboard.findall("table:table-row", NS)[1:]:
        items = cells(row, 2)
        label = value(items[0])
        if label in formulas:
            cell = items[1]
            set_value(cell, str(cached.get(label, 0)))
            cell.set(q("office", "value-type"), "float")
            cell.set(q("office", "value"), str(cached.get(label, 0)))
            cell.set(q("table", "formula"), "of:=" + formulas[label].replace("Tests de recette", tests.get(q("table", "name"))))
            for child in list(row):
                row.remove(child)
            row.extend(items)

    # LibreOffice conserve jusqu’à un million de lignes vides répétées. Leur
    # appliquer un style gonfle fortement l’export XLSX ; garder 500 lignes utiles.
    widths = {"Tests de recette": 13, "Scénarios métier": 6, "Anomalies": 12}
    for name, table in tables.items():
        position = 0
        for row in list(table.findall("table:table-row", NS)):
            items = cells(row, widths.get(name, 2))
            meaningful = any(value(cell) or cell.get(q("table", "formula")) for cell in items)
            repeat = int(row.get(q("table", "number-rows-repeated"), 1))
            if not meaningful:
                repeat = min(repeat, max(0, 500 - position))
                if not repeat:
                    table.remove(row)
                    continue
            if repeat == 1:
                row.attrib.pop(q("table", "number-rows-repeated"), None)
            else:
                row.set(q("table", "number-rows-repeated"), str(repeat))
            position += repeat
            for child in list(row):
                row.remove(child)
            row.extend(items)
        for row in table.findall("table:table-row", NS)[1:]:
            row.set(q("table", "style-name"), "RecetteRow")
            for cell in row.findall("table:table-cell", NS):
                if value(cell) and table is not dashboard:
                    cell.set(q("table", "style-name"), "RecetteBody")
    spreadsheet = document.find("office:body/office:spreadsheet", NS)
    ranges = spreadsheet.find("table:database-ranges", NS)
    if ranges is None:
        ranges = ET.SubElement(spreadsheet, q("table", "database-ranges"))
    existing_range = next((r for r in ranges if r.get(q("table", "name")) == "RecetteTests"), None)
    if existing_range is None:
        existing_range = ET.SubElement(ranges, q("table", "database-range"), {q("table", "name"): "RecetteTests"})
    test_sheet = tests.get(q("table", "name"))
    existing_range.set(q("table", "target-range-address"), f"'{test_sheet}'.A1:'{test_sheet}'.M{total + 1}")
    existing_range.set(q("table", "display-filter-buttons"), "true")
    existing_range.set(q("table", "contains-header"), "true")

    updated = ET.tostring(document, encoding="unicode")
    # Conserver aussi les namespaces utilisés uniquement dans les formules/valeurs.
    for prefix, uri in namespaces.items():
        declaration = f'xmlns:{prefix}=' if prefix else 'xmlns='
        if declaration not in updated.split(">", 1)[0]:
            updated = updated.replace(">", f' {declaration}"{uri}">', 1)
    temporary = output_path.with_suffix(".tmp.ods")
    with ZipFile(temporary, "w") as target:
        for info, data in entries:
            target.writestr(info, updated.encode("utf-8") if info.filename == "content.xml" else data)
    with ZipFile(temporary) as check:
        assert check.testzip() is None
        saved = ET.fromstring(check.read("content.xml"))
        saved_table = saved.find(".//table:table", NS)
        assert tracking(saved_table) == after
    temporary.replace(output_path)
    print(f"Classeur : {output_path}")
    print(f"{total} tests ; statuts conservés : {dict(counts)} ; {len(set(after) - set(before))} nouveaux tests.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ODS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    main(args.source, args.output)
