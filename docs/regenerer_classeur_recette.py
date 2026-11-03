"""Actualise le classeur ODS en conservant les résultats, avant export Excel."""
from copy import deepcopy
from collections import Counter
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

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


def main():
    with ZipFile(ODS) as source:
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
    tables = {t.get(q("table", "name")): t for t in document.findall(".//table:table", NS)}
    tests = tables["Tests de recette"]
    before = tracking(tests)
    markdown = (ROOT / "RECETTE_COMPLETE.md").read_text(encoding="utf-8")
    descriptions = {}
    for line in markdown.splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) == 3 and re.fullmatch(r"[A-Z]+-\d+", parts[0]):
            descriptions[parts[0]] = parts[1:]

    for row in tests.findall("table:table-row", NS)[1:]:
        items = normalized_test_cells(row)
        test_id = value(items[0])
        if test_id not in before:
            continue
        if test_id in descriptions:
            action, expected = descriptions[test_id]
            set_value(items[2], action)
            set_value(items[3], f"RECETTE_COMPLETE.md — {test_id}")
            set_value(items[4], expected)
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
    new_ids = ["ADM-07", "ADM-08"] + [f"RSP-{i:02}" for i in range(1, 16)]
    for test_id in new_ids:
        if test_id in before:
            continue
        action, expected = descriptions[test_id]
        section = "17. Responsables par CDF et par support" if test_id.startswith("RSP-") else "Administration — conservation des traces et maintenance"
        row = new_row([test_id, section, action,
                       f"RECETTE_COMPLETE.md — {test_id}", expected, "Haute", "Non exécuté"] + [""] * 6)
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
    mode = tables["Mode emploi"]
    for row in mode.findall("table:table-row", NS):
        items = cells(row, 2)
        if value(items[0]) == "Référence":
            set_value(items[1], "RECETTE_COMPLETE.md du 03/11/2026 ; section 17 ajoutée")
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
            cell.set(q("table", "formula"), "of:=" + formulas[label])
            for child in list(row):
                row.remove(child)
            row.extend(items)

    for table in tables.values():
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
    existing_range.set(q("table", "target-range-address"), f"'Tests de recette'.A1:'Tests de recette'.M{total + 1}")
    existing_range.set(q("table", "display-filter-buttons"), "true")
    existing_range.set(q("table", "contains-header"), "true")

    updated = ET.tostring(document, encoding="unicode")
    # Conserver aussi les namespaces utilisés uniquement dans les formules/valeurs.
    for prefix, uri in namespaces.items():
        declaration = f'xmlns:{prefix}=' if prefix else 'xmlns='
        if declaration not in updated.split(">", 1)[0]:
            updated = updated.replace(">", f' {declaration}"{uri}">', 1)
    temporary = ODS.with_suffix(".tmp.ods")
    with ZipFile(temporary, "w") as target:
        for info, data in entries:
            target.writestr(info, updated.encode("utf-8") if info.filename == "content.xml" else data)
    with ZipFile(temporary) as check:
        assert check.testzip() is None
        saved = ET.fromstring(check.read("content.xml"))
        saved_table = saved.find(".//table:table", NS)
        assert tracking(saved_table) == after
    temporary.replace(ODS)
    print(f"{total} tests ; statuts conservés : {dict(counts)} ; {len(set(after) - set(before))} nouveaux tests.")


if __name__ == "__main__":
    main()
