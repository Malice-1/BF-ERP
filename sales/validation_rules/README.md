# Validation artifacts

Official OASIS UBL 2.1 schemas and OpenPeppol billing rules are retained for
offline, reproducible invoice validation. Copyright and licence notices remain
in the original files. These third-party artifacts must not be hand-edited.

`manifest.json` records source URLs, source/generated SHA-256 digests, rule
version, download date and the locally approved applicability interval.

Sources:

- https://docs.oasis-open.org/ubl/os-UBL-2.1/
- https://github.com/OpenPEPPOL/peppol-bis-invoice-3/tree/38d693d71d28d813781323a6ca97324edcc4d239
- https://github.com/Schematron/schematron/tree/master/trunk/schematron/code

The ISO Schematron compiler is used only by the explicit installation script.
At runtime, Saxon/C runs the compiled XSLT files. No network transmission is
performed during invoice generation or validation.

The local review deadline of 2026-12-01 is conservative and is not an official
Peppol expiry date. Updating applicability requires checking published official
releases and rerunning acceptance tests. See `docs/MODULE_VENTES.md`.
