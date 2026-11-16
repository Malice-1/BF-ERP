"""Download official validation artifacts, compile Schematron and record provenance.

Run explicitly when updating rules; invoice generation never accesses the network.
"""
import hashlib
import json
import re
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1] / "sales" / "validation_rules"
SOURCES = {}


def download(url, relative):
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    data = urllib.request.urlopen(url, timeout=60).read()
    target.write_bytes(data)
    SOURCES[relative] = {"url": url, "sha256": hashlib.sha256(data).hexdigest()}
    return target


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    base = "https://docs.oasis-open.org/ubl/os-UBL-2.1/"
    pending = ["xsd/maindoc/UBL-Invoice-2.1.xsd"]
    seen = set()
    while pending:
        relative = pending.pop()
        if relative in seen:
            continue
        seen.add(relative)
        target = download(urljoin(base, relative), relative)
        for location in re.findall(r'schemaLocation="([^"]+)"', target.read_text(encoding="utf-8")):
            url = urljoin(urljoin(base, relative), location)
            if not url.startswith(base):
                raise RuntimeError(f"Unexpected schema dependency: {url}")
            pending.append(url.removeprefix(base))
    peppol = "https://raw.githubusercontent.com/OpenPEPPOL/peppol-bis-invoice-3/38d693d71d28d813781323a6ca97324edcc4d239/"
    for filename in ("CEN-EN16931-UBL.sch", "PEPPOL-EN16931-UBL.sch"):
        download(peppol + "rules/sch/" + filename, filename)
    skeleton = "https://raw.githubusercontent.com/Schematron/schematron/master/trunk/schematron/code/"
    for filename in ("iso_dsdl_include.xsl", "iso_abstract_expand.xsl", "iso_svrl_for_xslt2.xsl", "iso_schematron_skeleton_for_saxon.xsl"):
        download(skeleton + filename, "compiler/" + filename)
    from saxonche import PySaxonProcessor
    with PySaxonProcessor(license=False) as proc:
        xslt = proc.new_xslt30_processor()
        for filename in ("CEN-EN16931-UBL", "PEPPOL-EN16931-UBL"):
            node = proc.parse_xml(xml_file_name=str(ROOT / (filename + ".sch")))
            for stylesheet in ("iso_dsdl_include.xsl", "iso_abstract_expand.xsl", "iso_svrl_for_xslt2.xsl"):
                executable = xslt.compile_stylesheet(stylesheet_file=str(ROOT / "compiler" / stylesheet))
                node = executable.transform_to_value(xdm_node=node).item_at(0)
            target = ROOT / (filename + ".xsl")
            target.write_text(str(node), encoding="utf-8")
            SOURCES[target.name] = {"generated_from": filename + ".sch",
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    manifest = {"version": "OpenPeppol-38d693d71d28-UBL2.1", "downloaded_at": date.today().isoformat(),
        "valid_from": "2026-08-17", "valid_until": "2026-12-01", "files": SOURCES,
        "note": "3.0.21 mandatory from 2026-08-17. Conservative review deadline 2026-12-01; not an official end date. Review official releases before extending."}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Validation artifacts installed: {len(SOURCES)} files")


if __name__ == "__main__":
    main()
