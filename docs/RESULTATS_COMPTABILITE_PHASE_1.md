# Vérifications — comptabilité phase 1

16 novembre 2026. Arbre de travail local BF-ERP, base Git
`c0ed8e981b15a60c7bdb9f2d388f4d4d7114c4a7`, identique au HEAD GitHub consulté.
Les modifications Ventes et connexion préexistantes sont incluses dans les tests.

## Campagnes exécutées

| Vérification | Résultat |
| --- | --- |
| Première campagne ciblée comptabilité, SQLite | 18 tests réussis |
| Première campagne ciblée comptabilité, PostgreSQL | 27 tests réussis, aucun ignoré |
| Campagne ciblée enrichie, PostgreSQL | 30 tests réussis, aucun ignoré |
| Première campagne globale, SQLite | 371 tests, succès ; 26 tests PostgreSQL ignorés |
| Première campagne globale, PostgreSQL 17.12 isolé | 371 tests réussis, aucun ignoré |
| Campagne finale globale, SQLite | 373 tests, succès ; 26 tests PostgreSQL ignorés |
| Campagne finale globale, PostgreSQL 17.12 isolé | 373 tests réussis, aucun ignoré, 201,844 secondes |
| Thème JavaScript | 4 tests réussis |
| Syntaxe de `accounting/static/accounting/ledger.js` | Vérification Node réussie |
| `manage.py check`, démonstration | Aucune anomalie |
| `makemigrations --check --dry-run`, tests | Aucun changement manquant |
| `git diff --check` | Réussi |
| Huit écrans comptables, démonstration | Réponses HTTP 200 |

Ces campagnes se recouvrent ; ne pas additionner leurs nombres de tests.
Les avertissements de panne de générateur, de disque plein et de règles XML absentes
des tests Ventes sont des injections volontaires, pas des échecs de cette campagne.

## Cas comptables couverts

Le module contient 32 tests : 23 tests métier/HTTP et 9 tests PostgreSQL spécifiques.

- Brouillons équilibrés/déséquilibrés, absence de numéro définitif avant validation.
- Rejet des montants négatifs, non finis, à précision excessive, des lignes nulles
  ou portant simultanément un débit et un crédit.
- Équilibre des lignes réelles au posting, y compris attaque SQL avec faux totaux.
- Référence justificative, comptes d'imputation et tiers du type requis.
- Approbation du plan, révocation sur modification et revue de l'identité légale.
- Exercices/périodes sans chevauchement ; refus hors période et dans une période fermée.
- Révisions périmées, saisies idempotentes et conflit de contenu sur une même clé.
- Numérotation chronologique, allocation concurrente de la première séquence.
- Validation simultanée d'une même écriture sans doublon de numéro ou d'événement.
- Fermeture d'une période concurrente avec une validation.
- Contrepassation exacte, historique conservé, idempotence et concurrence.
- Contrepassation dans l'exercice suivant et sur compte historique désactivé.
- Snapshots de comptes/tiers et structure des comptes utilisés protégée.
- Immutabilité ORM et SQL des écritures, lignes, compteurs et événements.
- Import du plan atomique, idempotent, avec référence et SHA-256.
- Saisie, modification et validation via formulaires HTTP réels du client Django.
- Droits séparés, absence de droits, CSRF et refus des mutations GET.
- Conservation du nom historique du validateur après suppression de son utilisateur.
- Refus préalable des suppressions de maintenance touchant la comptabilité.
- Absence d'effet automatique sur factures Ventes, mouvements de stock et engagements budgétaires.

## Activation de la démonstration

- Sauvegarde SQLite cohérente avant modification :
  `backups/before-accounting-20261116-123214.sqlite3`.
- Quatre migrations additives appliquées avec `config.demo_settings` :
  `0001_initial`, `0002_ledger_guards`,
  `0003_accountingprofile_approved_issuer_snapshot`, `0004_entity_approval_guard`.
- Aucune migration destructive exécutée ; aucune base PostgreSQL métier modifiée.
- Aucun compte, journal, exercice ou mouvement de test créé dans la base de démonstration.
- Vérification après activation : `Account`, `Journal`, `JournalEntry`, `FiscalYear`
  et `AccountingProfile` contiennent zéro enregistrement.
- Écrans contrôlés : accueil, cadre, comptes, import du plan, journaux, exercices,
  liste et formulaire de nouvelle écriture.
- Les clusters PostgreSQL de test sont arrêtés automatiquement par le script ;
  aucun service Windows ajouté. Les artefacts QA restent sous `.qa/`, exclus de Git.

## Livrables et limites

- Diagnostic : `AUDIT_COMPTABILITE_PHASE_0.md`.
- Architecture, configuration, services, permissions et migrations : `COMPTABILITE_PHASE_1.md`.
- Recette manuelle : `RECETTE_COMPTABILITE_PHASE_1.md`.
- Code et tests : `accounting/` ; adaptations d'intégration détaillées dans la documentation.

Le plan public réel n'a pas été fourni ni validé réglementairement. Il doit être
saisi/importé puis approuvé par l'organisation avant la première validation métier.
Le logiciel ne prétend pas certifier cette approbation ou remplacer l'expert compétent.

La recette visuelle dans un navigateur, les essais de charge, les procédures de
sauvegarde/restauration de production et la validation réglementaire restent à faire.
Les phases 2 à 8 sont volontairement non commencées et attendent la validation
de la phase 1 par l'utilisateur.
