# Import des factures fournisseurs XML Peppol

Extension du 16 novembre 2026, demandée après livraison de la phase 1 comptable.
Accès : **Comptabilité → Factures fournisseurs → Importer un XML Peppol**,
`/comptabilite/factures-fournisseurs/`.

## Périmètre

Import manuel d'un fichier à la fois, extraction structurée sans OCR, validation
technique complète, rapprochement fournisseur proposé, revue métier explicite,
rejet motivé, revalidation et téléchargement sécurisé de l'original.

Formats acceptés : facture UBL `Invoice` déclarant Peppol BIS Billing 3.0, type 380.
L'import refuse les XML mal formés, DTD/entités externes, autres racines/profils,
avoirs `CreditNote`, autres types de factures et enveloppes SBDH. Pour une enveloppe,
fournir le document Invoice exporté par le système émetteur. Les fichiers CII,
PDF/ZIP et la réception automatique sur le réseau Peppol ne sont pas implémentés.

L'interface ne prétend pas avoir reçu le document d'un point d'accès Peppol :
il s'agit d'un dépôt manuel d'un fichier au format Peppol. La conformité du fichier
ne constitue pas une preuve d'authenticité de son émetteur ou de réalisation du service.

## Parcours

1. Déposer un XML, limité à 5 Mo par défaut.
2. Lire le statut de validation et les erreurs éventuelles.
3. Vérifier émetteur, destinataire, références, dates, lignes, remises/frais,
   ventilation fiscale, totaux et montant à payer.
4. Confirmer le fournisseur retrouvé par numéro d'entreprise en priorité, puis
   à défaut proposé par TVA, ou sélectionner manuellement
   la bonne fiche. Aucun fournisseur, contact, adresse ou compte bancaire n'est créé
   ou modifié automatiquement.
5. Approuver avec justification, ou rejeter avec un motif. Une revue terminée est
   immuable ; l'original reste archivé dans les deux cas.

Créer une fiche fournisseur manquante dans le module Fournisseurs avec les droits
existants, puis revenir sur la facture. Plusieurs fiches partageant une TVA ou un numéro d'entreprise donnent
plusieurs candidats ; aucune n'est sélectionnée arbitrairement.

L'approbation exige :

- une validation complète réussie, selon le dernier résultat enregistré ;
- un fichier archivé dont l'empreinte est correcte ;
- un fournisseur existant sans contradiction avec les identifiants du vendeur :
  numéro d'entreprise et TVA ; une TVA absente en fiche est admise si le numéro
  d'entreprise correspond, sans copier ni déduire automatiquement de TVA ;
- l'entité destinataire configurée et liée au cadre comptable ;
- au moins un identifiant destinataire vérifiable et aucun conflit parmi les identifiants
  comparables : TVA, identité légale, endpoint/schéma Peppol ; le nom seul ne suffit pas ;
- une justification et un droit de revue distinct.

Configurer l'entité via **Ventes → Émetteur**, puis la sélectionner dans
**Comptabilité → Cadre et approbation**. La réception/revue ne demande pas d'inventer
un plan comptable ni de l'approuver prématurément : elle ne comptabilise aucune écriture.

Le numéro d'entreprise se saisit dans la fiche fournisseur, séparément de la TVA.
Les formats BCE `0123.456.749`, `0123456749` et `BE0123456749` sont normalisés en
`0123456749`, en conservant le zéro initial. Le champ reste facultatif pour les
fiches existantes ; aucune migration ne le déduit d'une TVA.

Le rapprochement lit `PartyLegalEntity/CompanyID` et son schéma ; pour une BCE belge,
il exploite aussi `EndpointID` ou `PartyIdentification/ID` de schéma `0208`. Une
correspondance unique sur ce numéro associe le fournisseur à l'import, sans terminer
la revue. Une ambiguïté n'est pas résolue arbitrairement ; des identifiants XML
contradictoires ou une contradiction avec la fiche bloquent l'approbation.
Le rapprochement TVA demeure un recours pour les anciennes fiches dépourvues de numéro.

Les imports antérieurs peuvent retrouver les nouveaux identifiants depuis leur XML
original vérifié, sans modifier l'extraction historique figée. Aucun régime fiscal
n'est déduit du nom ou du numéro d'entreprise.

## Données extraites

- Numéro fournisseur, date d'émission, échéance éventuelle, devise, profil et références.
- Identité/adresse/TVA/identifiants électroniques du vendeur et de l'acheteur.
- Lignes : identifiant, descriptions, quantité/unité, prix et quantité de base,
  montant HT de ligne, catégorie et taux de TVA, remises/frais.
- Remises/frais globaux et ventilation TVA avec motifs/codes d'exonération.
- Totaux HT, TVA, TTC, montant payé déclaré, arrondi et montant exigible.
- Conditions et moyens de paiement, compte et communication déclarés, bénéficiaire distinct éventuel.
- Présence de pièces jointes et références externes, sans téléchargement ni extraction.

Les montants comptables sont stockés en `Decimal`, sans recalcul fiscal ni conversion
de devise. Les valeurs détaillées du XML restent dans l'extraction figée et l'original.
Le TTC et le montant à payer restent distincts, notamment lorsqu'un acompte est
déclaré. Cette déclaration ne crée pas un paiement reçu dans BF-ERP.

Les devises et montants négatifs admis par le profil XML ne sont pas convertis ou
transformés en écritures. Le grand livre de phase 1 reste limité à EUR ; un import
ne contourne pas cette limite.

## Validation et dates

Réutilisation de `sales.documents.validate_xml` et des artefacts locaux existants :
XSD UBL 2.1, Schematron EN16931 et Peppol incluant leurs règles nationales.
Le code ne recrée pas un validateur réduit ni des règles fiscales supposées.

La sélection des règles respecte la date d'émission et leur manifeste. Le jeu
actuellement installé couvre les dates du 17 août au 30 novembre 2026 inclus ;
le 1er décembre est une échéance locale conservatrice de revue, pas une expiration
officielle Peppol. Voir `MODULE_VENTES.md` et `sales/validation_rules/manifest.json`.

- `VALID` : les contrôles requis exécutés ont réussi ; les avertissements restent consultables.
- `INVALID` : contrôle de structure, assertion fatale ou extraction de montants/dates requises en échec.
- `UNAVAILABLE` : règles absentes, moteur indisponible ou date non couverte. Ce statut
  ne signifie ni conformité ni nécessairement non-conformité du document.

Une facture ancienne peut être archivée et consultée mais ne peut pas être
approuvée tant que les règles correspondant à sa date ne permettent pas sa validation.
Ne pas étendre artificiellement la période d'un manifeste pour contourner ce contrôle.

L'action **Revalider** ajoute un résultat avec version et date, sans écraser le
précédent ni modifier la revue historique. Le statut XML courant et la décision
de revue sont affichés séparément. Une nouvelle erreur de validation ne doit pas
être interprétée comme une nouvelle approbation ou une autorisation de paiement.

Source de mapping vérifiée :
https://docs.peppol.eu/poacc/billing/3.0/syntax/ubl-invoice/

## Doublons, concurrence et intégrité

Deux contrôles indépendants :

1. SHA-256 du fichier : mêmes octets → même import, sans second fichier ni facture.
2. Identité vendeur + numéro de facture : autre fichier pour le même numéro vendeur
   → refus, même si seules la mise en forme ou les coordonnées de paiement ont changé.

L'identité est fondée sur la TVA, puis à défaut l'endpoint/schéma, puis l'identifiant
légal/pays. Sans identité exploitable, seul le contrôle de fichier est possible ;
un document Peppol valide doit néanmoins satisfaire ses règles d'identification.
Le changement de fichier d'une facture déjà importée n'est pas un mécanisme de
correction : aucune version n'est écrasée. Le remplacement/versionnement de pièces
fournisseurs est hors de cette extension ; la situation doit être examinée explicitement.

Les contraintes uniques en base et le verrou du profil comptable sérialisent les
imports concurrents. Deux revues simultanées ne peuvent pas approuver deux fois
la facture. La révision du formulaire évite l'écrasement d'une décision récente.

Les données originales/extraites, les revues terminées et les validations sont
protégées contre la réécriture et la suppression. Des triggers SQLite/PostgreSQL
complètent les protections ORM. Les noms historiques des réviseurs restent conservés
lorsqu'un utilisateur est supprimé.

## Archives et sécurité

Stockage privé `private_documents/supplier_invoices/`, configurable par
`SUPPLIER_DOCUMENT_ROOT`. Le nom envoyé ne détermine jamais le chemin de stockage.
Ne pas exposer ce répertoire via un serveur statique/média.

Téléchargement authentifié avec permission dédiée, empreinte vérifiée, réponse en
pièce jointe XML, `Cache-Control: private, no-store` et `X-Content-Type-Options: nosniff`.
Un fichier altéré/absent donne un refus HTTP 409. XML traité sans DTD, récupération
tolérante, accès réseau, exécution de pièces jointes ou téléchargement de leurs URLs.

Un XML UBL reconnu est conservé même si sa validation échoue. Un fichier illisible
ou d'un format non pris en charge est refusé avant création d'une facture.
Une panne de stockage annule l'import en base. Une panne de base après écriture
peut laisser un fichier orphelin ; le conserver pour rapprochement avant nettoyage.
Sauvegarder les archives et la base ensemble selon la politique de l'organisation.

## Droits et audit

- `view_supplierinvoice` : consulter les données extraites et validations.
- `import_supplierinvoice` : déposer les fichiers.
- `review_supplierinvoice` : approuver ou rejeter avec justification.
- `download_supplierinvoice` : télécharger les originaux.
- `revalidate_supplierinvoice` : relancer la validation.

Ces droits ne sont pas déduits les uns des autres. Mutations uniquement POST avec
CSRF, vérifications dans les vues et services. Les opérations alimentent
`AccountingEvent` et `workflow.ActivityLog` ; l'historique est consultable dans le détail.

## Architecture, migrations et limites

- Modèles `SupplierInvoice` et `SupplierInvoiceValidation` dans `accounting/models.py`.
  Pas de nouvelle table fournisseur, de catalogue bancaire parallèle ni de moteur documentaire séparé.
- Services/parser : `accounting/supplier_xml.py` ; vues/formulaires : `supplier_views.py`.
- Écrans et routes intégrés à Comptabilité, admin en lecture seule.
- Stockage/validation réutilisés via `sales/documents.py` ; ajout du helper générique
  `private_storage`, sans changement du comportement des factures Ventes.
- Migrations additives `0005_supplierinvoice_supplierinvoicevalidation` et
  `0006_supplier_xml_history_guards`. Aucune suppression ni migration destructive.
- Aucune nouvelle bibliothèque requise.

L'ajout ultérieur du numéro d'entreprise utilise la migration additive
`suppliers.0005_supplier_enterprise_number`. Le champ est indexé, sans unicité
imposée aux fiches : plusieurs codes fournisseurs pour une même entreprise restent
possibles et sont présentés comme une ambiguïté à résoudre explicitement.

**Aucune écriture comptable n'est créée par l'import ou la revue.** L'imputation
sur le plan public, la déductibilité TVA, les écritures d'autoliquidation,
les rapprochements avec commandes/réceptions et les paiements restent à valider
et développer séparément. Aucun email, appel réseau Peppol ou notification externe
n'est envoyé par cette extension.

## Vérifications

```powershell
.venv\Scripts\python.exe manage.py test accounting.test_supplier_xml --settings=config.test_settings --noinput
.venv\Scripts\python.exe tools/run_postgresql_acceptance.py accounting.test_supplier_xml accounting.test_supplier_xml_postgresql
.venv\Scripts\python.exe tools/run_postgresql_acceptance.py accounts budgeting purchasing receiving suppliers workflow sales config accounting
```

Les résultats effectifs et l'activation locale sont décrits dans
`RESULTATS_IMPORT_XML_FOURNISSEURS.md`.

Recette manuelle : importer un XML réel en QA ; vérifier les données et références,
le fournisseur et le destinataire ; revalider ; approuver/rejeter ; télécharger
l'original ; tester un doublon, un autre destinataire et un XML non conforme ;
vérifier les profils lecteur/importateur/réviseur et le rendu clair/sombre/mobile.
