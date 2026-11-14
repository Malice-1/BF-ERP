# Audit du nettoyage — 14 novembre 2026

## Périmètre et état de départ

Audit des sources présentes au début de cette mission, y compris les fichiers
non suivis par Git. Les suppressions et modifications préexistantes restent
intactes et ne sont pas comptabilisées comme travail de cette mission.
291 fichiers texte recensés, dont 202 fichiers Python. Les sauvegardes,
classeurs, bases locales et documents de recette sont conservés.

Référence avant nettoyage : `manage.py test --settings=config.test_settings
--noinput` exécute 293 tests, sans échec, avec 11 tests ignorés.

## Cartographie des dépendances avant suppression

| Entrées | Dépendances et responsabilités |
| --- | --- |
| `manage.py`, ASGI, WSGI | Configuration Django, chargement des six applications métier et du framework |
| `config/urls.py`, `purchasing/urls.py` | Authentification, configuration, fournisseurs, achats, budgets, transferts, réceptions et administration |
| `accounts` | Utilisateurs, rôles, permissions, habilitations historiques, sessions, backend d'authentification et contrôles de suppression |
| `suppliers` | Fournisseurs, contacts et adresses ; utilisés par les DA et les documents figés |
| `purchasing.views`, `services`, `flow` | DA, lignes, réservation/engagement du budget, décisions, délégations, notifications et bons de commande |
| `budgeting`, `purchasing.budget_views` | Référentiels, responsables, versions, allocations, imports et historique budgétaire |
| `budgeting.transfer_views`, `transfers` | Création, correction, validations, traitements groupés et journal des transferts |
| `receiving` | Réceptions, dépôts, mouvements et soldes de stock ; dépend des commandes approuvées |
| `workflow.activity`, `budgeting.history` | Signaux connectés par `AppConfig.ready`, journal des opérations et captures budgétaires |
| Commandes de gestion | Initialisation d'historique, données de démonstration et traitement périodique des notifications |
| Templates et fichiers statiques | Rendu Django, inclusions, surcharges de l'administration, thème, recherche AJAX, imports, formulaires et impression |
| `config.excel`, `allocation_excel` | Import/export Excel via `openpyxl` ; garde les contrats existants |
| Migrations | Historique de schéma, permissions, données de migration et protections SQL PostgreSQL |

Le navigateur utilise du JavaScript natif et du CSS ; aucun React, Vue,
TypeScript, gestionnaire de paquets frontend ou build frontend n'est présent.
Les dépendances Python sont figées dans `requirements.txt`.

Les réexportations de modèles entre `budgeting`, `purchasing.models` et
`purchasing.flow_models` assurent leur découverte et les imports historiques.
Les appels différés dans les fonctions évitent aussi certains cycles d'import.

## Classement initial

### CERTAIN — nettoyage autorisé

- Calcul et contexte `validation_progress`, restes d'une barre de progression
  retirée de l'interface ; les tests vérifient encore artificiellement ce
  contexte. Remplacer ces assertions par le contrôle des étapes courantes.
- Contextes `can_view_version_history` et `events` de la fiche de transfert,
  absents du template et de ses inclusions. Le parcours et son journal restent
  accessibles par leurs propres vues.
- Contextes `form` et `transfers` de la création des transferts, remplacés par
  `header`, `destination`, `formset` et la page de suivi. Garder les formulaires
  de compatibilité POST et l'export des transferts.
- Réévaluation identique de l'éligibilité d'une étape de transfert après son
  filtrage ; la ligne retenue est déjà connue comme accessible.
- Imports non utilisés dans `config/test_excel.py` et
  `receiving/test_purchase_receipts.py`.
- Imports locaux répétés alors que la même fonction est déjà importée au
  niveau du module, sans raison de chargement différé.
- Entrées `.env` et `db.sqlite3` dupliquées dans `.gitignore`.
- Champ `revision` du dictionnaire privé des étapes de la boîte de validation,
  jamais lu par ses templates ni par l'export opérationnel.
- Surcharge vide `budget_check_button` de la fiche de version budgétaire :
  le template parent réserve déjà ce bouton à la rubrique Achats.

### PROBABLE — conservation

- Propriété historique `BudgetLine.available_amount`, peu référencée dans le
  dépôt ; elle peut être utilisée en administration ou depuis des scripts.
- Branches d'anciens circuits et habilitations : nécessaires aux soumissions
  déjà enregistrées ; leur retrait changerait le traitement des données.
- Modèles historiques et formulaires de compatibilité : une faible présence
  dans l'interface ne suffit pas à démontrer leur inutilité.

### INCERTAIN — conservation

- URLs de compatibilité et pages non proposées dans le menu : favoris,
  scripts ou clients externes possibles. Aucun endpoint n'est supprimé.
- Commandes, hooks Django, surcharges admin, signaux et variables CSS/classes
  dynamiques : chargement indirect confirmé ou possible.
- Migrations et appels à leurs fonctions historiques, notamment
  `request_number` : reconstruction de la base à préserver.
- Paquets transitifs et pilotes PostgreSQL : vérifier leurs métadonnées avant
  toute conclusion ; ne pas déduire leur inutilité des seuls imports métier.

## Méthode de preuve et contrôles

Inventaire avec `rg`, analyse AST et symboles Python, graphe des imports,
recherche des noms et attributs, résolution récursive des inclusions et de
l'héritage des templates, rapprochement des fichiers statiques et de leurs
sélecteurs avec HTML/JavaScript/Python. Les résultats automatiques sont des
candidats, examinés avec les conventions Django et les tests.

Le [rapport final](NETTOYAGE_RAPPORT_20261114.md) documente les modifications
effectuées, les commandes, les limites des outils disponibles et les métriques
mesurées par rapport à cet état de départ.
