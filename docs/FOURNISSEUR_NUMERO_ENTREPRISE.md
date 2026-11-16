# Numéro d'entreprise du fournisseur et rapprochement XML

Modification du 16 novembre 2026.

## Utilisation

Dans **Achats → Fournisseurs → Créer/Modifier**, renseigner le champ facultatif
**Numéro d'entreprise**, séparément du numéro de TVA. Le champ figure également
dans l'administration et dans la liste/recherche des fournisseurs.

Pour une BCE belge, les saisies `0123.456.749`, `0123456749` et `BE0123456749`
sont enregistrées sous la même forme `0123456749`, sans perdre le zéro initial.
Il s'agit d'une normalisation de saisie, pas d'une vérification auprès du registre.
Aucune TVA n'est créée ou modifiée à partir du numéro d'entreprise et aucune
valeur n'est déduite automatiquement des anciennes fiches.

## Import XML

Le rapprochement utilise en priorité l'identifiant d'entreprise dans le vendeur :

- `AccountingSupplierParty/Party/PartyLegalEntity/CompanyID` ;
- `EndpointID` de schéma `0208`, qui représente une BCE belge ;
- `PartyIdentification/ID` de schéma `0208`.

Le schéma du CompanyID est conservé à l'extraction afin d'éviter de traiter
arbitrairement une autre catégorie d'identifiant comme une BCE lorsque le XML
fournit aussi une identification belge. Les identifiants de l'acheteur ne sont
pas utilisés pour retrouver le fournisseur.

Une correspondance unique associe la fiche fournisseur dès l'import. La facture
reste **À vérifier**, sans approbation ni écriture comptable automatique.

La recherche par TVA demeure disponible pour les fiches sans numéro d'entreprise.
Une fiche dont le numéro d'entreprise contredit le XML n'est pas sélectionnée par
simple concordance de TVA. Si plusieurs fiches partagent un même numéro, aucune
n'est choisie automatiquement : la sélection explicite reste nécessaire.

Lors de l'approbation :

- des identifiants d'entreprise contradictoires dans le XML bloquent la revue ;
- un numéro d'entreprise différent de celui de la fiche bloque l'approbation ;
- une TVA renseignée dans la fiche qui contredit celle du XML bloque l'approbation,
  même si le numéro d'entreprise correspond ;
- une TVA absente en fiche est admise si le numéro d'entreprise correspond ; elle
  n'est pas copiée ou inférée automatiquement ;
- les contrôles XML et destinataire existants restent exigés.

Le numéro d'entreprise retenu est figé dans le snapshot de revue. Une fiche remplie
après un premier import peut être retrouvée en revenant sur la facture. Pour les
anciennes extractions sans schémas/PartyIdentification, l'original archivé est relu
après contrôle de son empreinte, sans réécriture du snapshot historique.

Références de mapping vérifiées :

- https://docs.peppol.eu/poacc/billing/3.0/syntax/ubl-invoice/cac-AccountingSupplierParty/cac-Party/cac-PartyLegalEntity/cbc-CompanyID/
- https://docs.peppol.eu/poacc/billing/3.0/codelist/eas/

## Fichiers et migration

`suppliers/models.py`, `identifiers.py`, `forms.py`, `views.py`, `admin.py`,
template de liste ; `accounting/supplier_xml.py` et template de revue ; tests
dans `suppliers/tests.py` et `accounting/test_supplier_enterprise.py`.

Migration additive : `suppliers.0005_supplier_enterprise_number`. Champ indexé,
vide par défaut, sans contrainte d'unicité imposée aux fiches existantes.

Sauvegarde locale avant migration :
`backups/before-supplier-enterprise-20261116-145021.sqlite3`.
Migration appliquée uniquement à la démonstration ; aucune base PostgreSQL métier
modifiée et aucune donnée fournisseur fictive ajoutée.

## Vérifications

- Première campagne ciblée : 34 tests réussis sur SQLite.
- Campagne complète SQLite : 409 tests réussis, dont 29 cas spécifiques PostgreSQL ignorés.
- Campagne PostgreSQL complète : 409 tests réussis, aucun ignoré, 174,272 secondes.
- Contrôles Django et cohérence modèles/migrations réussis.

Couverture ajoutée : saisie et modification HTTP, formats BCE et recherche,
champ facultatif, association sans TVA, imports existants et anciens snapshots,
CompanyID avec schéma, endpoint/PartyIdentification `0208`, doublons de fiches,
divergence entreprise/TVA et contradiction interne du XML.
