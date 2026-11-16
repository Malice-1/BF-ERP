# Résultats de vérification — Ventes

Campagne du 16 novembre 2026, sur l'arbre de travail local. Les modifications de
connexion déjà présentes au début de cette demande sont incluses dans la
non-régression ; elles ne sont pas des fonctionnalités du module Ventes.

| Vérification | Résultat |
| --- | --- |
| Campagne globale Django, SQLite en mémoire | 340 tests, succès ; 17 tests spécifiques PostgreSQL ignorés |
| Campagne globale Django, PostgreSQL portable 17.12 isolé | 340 tests, tous réussis, aucun ignoré |
| Vérification finale ciblée Ventes après ajustement des références XML, PostgreSQL | 33 tests, tous réussis, aucun ignoré |
| Vérification ciblée XML après cet ajustement, SQLite | 7 tests, tous réussis |
| Thème JavaScript existant | 4 tests réussis |
| Syntaxe JavaScript des commandes | `node --check` réussi |
| Cohérence modèles/migrations | `makemigrations --check --dry-run` : aucun changement manquant |
| Contrôles Django, configuration de démonstration | Aucune anomalie |
| Contrôle des différences Git | `git diff --check` réussi |
| Écrans clients, commandes, création de commande, factures, formations, émetteur, suivi | Réponses HTTP 200 avec les données et droits de la démonstration |

La campagne globale et la dernière campagne ciblée sont deux exécutions
distinctes : leurs nombres de tests ne doivent pas être additionnés.

## Garanties effectivement éprouvées

- Commande multi-lignes, validations serveur, arrondis cohérents et révision périmée.
- Confirmation, annulation autorisée et protection des commandes confirmées.
- Une seule facture pour deux demandes d'émission simultanées sur PostgreSQL.
- Initialisation concurrente de la première séquence de commande sans doublon.
- Unicité de facture au niveau SQL, distincte des contrôles applicatifs.
- Rejet de modifications fiscales par SQL direct sur PostgreSQL.
- PDF généré, archivé et téléchargé avec contrôle d'intégrité.
- XML validé par les XSD UBL, les Schematron EN16931 et Peppol réels.
- Catégories S, Z, E, AE et O ; absence de référence acheteur/commande traitée sans
  inventer une référence client à partir du numéro interne.
- Rejet des XML invalides et indisponibilité explicite des règles manquantes ou
  hors période. Refus des DTD.
- Aucune utilisation de `urllib.request.urlopen` lors du parcours XML testé.
- Erreur de préparation avant émission : aucune facture ni numéro définitif.
- Erreur d'archivage après émission : facture conservée, reprise possible.
- Instantanés indépendants des modifications ultérieures du client et de l'émetteur.
- Paiements partiels, solde, correction tracée, idempotence et concurrence sans
  dépassement du montant dû.
- Permissions HTTP et métier, CSRF, rattachement document/facture, document altéré.
- Absence de mouvements de stock créés par les ventes de formations.

Les messages de panne de générateur, disque plein et règles absentes apparaissant
dans les journaux de tests sont des injections volontaires vérifiées par les tests.

## Corrections de préparation de tests existants

La première campagne PostgreSQL a révélé deux tests existants qui forçaient
`locked_at` par mise à jour SQL sur une version budgétaire publiée. Les protections
existantes interdisaient cette préparation.

- `purchasing/test_allocation_excel.py` utilise désormais `lock_envelope` pour
  refermer les modifications d'une version publiée précédemment déverrouillée.
- `budgeting/test_transfers.py` crée une version brouillon puis la verrouille par
  le service métier pour tester le refus de validation sur version verrouillée.

Ces corrections ne modifient pas les services de budget ou d'achat. Les campagnes
SQLite et PostgreSQL ont ensuite réussi.

## Activation locale

- Sauvegarde cohérente de SQLite avant migration :
  `backups/before-sales-20261116-120127.sqlite3`.
- `sales.0001_initial` et `sales.0002_history_guards` appliquées avec
  `config.demo_settings`.
- Aucune migration appliquée à une base PostgreSQL métier.
- Les clusters PostgreSQL de test ont été arrêtés après les campagnes ; aucun
  service Windows installé. Binaires et données de test restent sous `.qa/`,
  exclus de Git, pour permettre de reproduire les vérifications.
- Aucune fiche émetteur ou client fictive injectée dans la base de démonstration.

## Limites de la vérification

Les réponses HTTP et formulaires ont été testés, mais aucune recette visuelle
complète dans un navigateur ni aucun test de charge n'a été réalisé. Le cahier
`RECETTE_VENTES.md` décrit les parcours manuels restants.

Les données légales de l'émetteur, les régimes fiscaux réellement applicables,
la conservation documentaire et l'allocation budgétaire des paiements partiels
restent à confirmer par l'organisation. Le jeu de règles XML exige une revue
d'applicabilité avant le 1er décembre 2026, comme expliqué dans `MODULE_VENTES.md`.
