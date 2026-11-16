# Vérification de l'import XML fournisseur

Campagne du 16 novembre 2026 sur l'arbre de travail BF-ERP, incluant les modules
Ventes et Comptabilité déjà développés. Aucun push GitHub ni changement de base
PostgreSQL métier effectué.

## Résultats

| Vérification | Résultat |
| --- | --- |
| Première campagne ciblée SQLite | 21 tests réussis |
| Première campagne ciblée PostgreSQL | 24 tests réussis, aucun ignoré |
| Campagne complète SQLite | 397 tests, succès ; 29 cas propres à PostgreSQL ignorés |
| Campagne complète PostgreSQL 17.12 isolé | 397 tests réussis, aucun ignoré, 181,593 secondes |
| Vérification finale ciblée SQLite, identifiants Peppol stricts inclus | 22 tests réussis |
| Vérification finale ciblée PostgreSQL | 25 tests réussis, aucun ignoré, 22,782 secondes |
| Thème JavaScript existant | 4 tests réussis |
| Cohérence modèles/migrations | Aucun changement manquant |
| Contrôles Django, démonstration | Aucune anomalie |
| `git diff --check` | Réussi |
| Liste et formulaire d'import sur la démonstration | Réponses HTTP 200 |

Les campagnes se recouvrent et ne doivent pas être additionnées. Les erreurs
de générateur, disque et règles absentes des scénarios négatifs sont injectées
volontairement et vérifiées, pas des anomalies de campagne.

## Couverture des nouveaux tests

`accounting/test_supplier_xml.py` et `accounting/test_supplier_xml_postgresql.py` :

- Validation XSD, EN16931 et Peppol réelle sur un XML produit par le générateur UBL existant.
- Extraction fidèle des lignes, parties, totaux, échéance, banque et références.
- Préservation du TTC, du montant payé déclaré et du montant restant à payer.
- Fichier original identique aux octets déposés et empreinte SHA-256 correcte.
- Détection des doublons de fichier et des variantes portant le même numéro vendeur.
- Rapprochement fournisseur proposé, ambiguïté TVA et décision explicite.
- Refus d'un mauvais fournisseur, destinataire divergent ou non vérifiable.
- Comparaison des endpoints sans suppression de leur ponctuation.
- Refus d'approbation si XML invalide ou règles indisponibles.
- Facture ancienne conservée avec statut indisponible, sans falsifier sa date.
- Date mal formée conservée avec erreur d'extraction et validation invalide.
- Revalidation ajoutant un résultat sans écraser le précédent.
- Refus de XML mal formé, DTD/entités externes, type non pris en charge et dépassement de taille.
- Aucune récupération de liens externes de pièces jointes ni appel urllib pendant l'import testé.
- Absence d'écriture comptable automatique.
- Immutabilité des sources, revues terminées et validations, y compris par SQL direct.
- Rejet motivé et refus des modifications après décision.
- Fichier altéré : refus de téléchargement, revue et revalidation.
- Panne de stockage : aucune facture enregistrée en base.
- Formulaires HTTP, consultation, import et décision de revue.
- Permissions distinctes, lecteur sans téléchargement implicite, protection CSRF et mutations POST.
- Conservation du nom de réviseur après suppression de son compte utilisateur.
- Imports simultanés : un seul enregistrement et un seul fichier.
- Fichiers différents de même identité métier : un seul import accepté.
- Revues simultanées : une seule approbation et une seule progression de révision.

## Activation locale

Sauvegarde cohérente de SQLite avant migration :
`backups/before-supplier-xml-20261116-140051.sqlite3`.

Migrations additives appliquées à la démonstration :

- `accounting.0005_supplierinvoice_supplierinvoicevalidation` ;
- `accounting.0006_supplier_xml_history_guards`.

Aucune facture de test injectée dans la base de démonstration. Le nombre de
factures fournisseurs importées après activation est zéro. Les archives de tests
utilisent des répertoires temporaires dédiés sous `.qa/`, nettoyés après les tests.
Le serveur PostgreSQL de chaque campagne est local, isolé et arrêté en fin d'exécution.

## Limites de la vérification

Les tests utilisent des factures QA construites avec le générateur existant et
des variantes invalides contrôlées. Aucun XML réel fourni par l'utilisateur n'a
été testé pendant cette implémentation. Une recette avec les exports réels des
fournisseurs et une vérification visuelle du navigateur restent nécessaires.

Le périmètre couvre le dépôt manuel UBL Invoice/type 380. Avoirs, CII, SBDH, OCR,
remplacement/versionnement d'un XML déjà importé, connexion à un point d'accès,
imputation et comptabilisation automatiques ne sont pas développés.

Le contrôle réglementaire dépend des artefacts et périodes approuvés existants.
Les dates non couvertes restent indisponibles, jamais déclarées conformes.
Voir [IMPORT_XML_FOURNISSEURS.md](IMPORT_XML_FOURNISSEURS.md) pour la configuration,
le fonctionnement, les droits et les règles de revue.
