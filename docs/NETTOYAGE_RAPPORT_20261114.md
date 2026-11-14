# Rapport de nettoyage — 14 novembre 2026

## A. Résumé du nettoyage

Le dépôt a été audité dans son ensemble avant suppression. La cartographie,
les points d'entrée et les niveaux de certitude sont décrits dans
[l'audit](AUDIT_NETTOYAGE_20261114.md).

Le précédent nettoyage documenté dans `NETTOYAGE.md` et les modifications de
la session étaient déjà présents. Ils ne sont pas attribués à cette mission.
Une copie textuelle de départ a servi à comparer les changements, y compris
dans les fichiers non suivis par Git. Les fins de ligne ne comptent pas comme
des changements fonctionnels.

| Mesure de cette mission | Résultat |
| --- | ---: |
| Fichiers entièrement supprimés | 0 |
| Fichiers existants modifiés | 10 |
| Documents ajoutés | 2 |
| Lignes retirées des fichiers existants | 37 |
| Lignes ajoutées dans les fichiers existants | 16 |
| Réduction nette hors nouveaux documents | 21 lignes |
| Dépendances retirées | 0 |
| Endpoints, modèles et migrations supprimés | 0 |

Répartition des dix fichiers modifiés : quatre fichiers backend, un template
frontend, quatre fichiers de tests et `.gitignore`. Aucun paquet, fichier
statique ou module entier restant n'a une inutilité suffisamment démontrée
pour justifier sa suppression.

## B. Éléments supprimés et simplifications

### Calculs et contextes abandonnés

- `purchasing/views.py` : retrait du calcul et du contexte de progression
  `validation_progress`. La barre avait déjà disparu de l'interface.
  Les étapes courantes, la frise et leurs permissions restent inchangées.
- `budgeting/transfer_views.py` : retrait de l'ancien formulaire unique et
  de la liste des transferts du contexte de création, qui affiche aujourd'hui
  le formulaire d'en-tête, la destination et le formset. L'export conserve sa
  sélection de données et ses droits.
- Même module : retrait de `can_view_version_history` et du contexte `events`
  de la fiche de transfert. Le lien du parcours, son journal et les exports
  historiques restent disponibles dans leurs vues respectives.
- Retrait d'une sélection initiale de ligne immédiatement remplacée par la
  boucle de traitement des lignes valides du formset.
- `purchasing/flow_views.py` : retrait de `revision` du dictionnaire privé
  des étapes opérationnelles. La protection des commandes par révision est
  conservée dans les formulaires et services.

### Traitements redondants

- Fiche de transfert : suppression du second calcul identique des droits
  d'une étape déjà filtrée comme accessible. La vérification serveur lors
  de la décision reste obligatoire et inchangée.
- Boîte de validation : lecture des noms des candidats depuis la relation
  déjà préchargée, au lieu de reconstruire un `values_list` qui ignore le
  cache de préchargement. Aucune mesure de temps n'a été effectuée.
- Suppression de deux imports locaux qui dupliquaient les imports de module.

### Frontend, tests et configuration

- Retrait de la surcharge vide du bouton de vérification du budget dans la
  fiche de version : le parent le réserve déjà à la rubrique Achats.
- Retrait de deux imports inutilisés dans les tests Excel et réceptions.
- Les tests d'interface vérifient les étapes réellement affichées et les
  formulaires actuels, plutôt que des contextes abandonnés. Aucun test n'est
  supprimé ni désactivé ; le nombre de tests est identique avant et après.
- Déduplication des règles `.env` et `db.sqlite3` de `.gitignore`.

## C. Éléments conservés

| Catégorie | Élément | Motif |
| --- | --- | --- |
| PROBABLE | `BudgetLine.available_amount` et données de budgets historiques | Utilisation hors interface ou par scripts non exclue ; modèle historique conservé |
| PROBABLE | Anciennes règles, habilitations, délégations et réutilisation de preuves | Traitement des soumissions historiques toujours possible |
| INCERTAIN | Éditeurs retirés et URLs non proposées dans les menus | Compatibilité GET/POST, favoris et appels externes possibles ; contrats HTTP conservés |
| INCERTAIN | Ancien format POST de création des transferts | Formulaires déjà ouverts et intégrations possibles |
| Utilisation confirmée | Réexportations de modèles, chargements locaux et hooks Django | Découverte des modèles, administration, signaux, widgets et commandes |
| Utilisation confirmée | Classes CSS dynamiques, états de frise et icônes SVG | États générés par Django et JavaScript ; toutes les variantes d'icônes ont des appelants |
| Utilisation confirmée | Neuf dépendances de `requirements.txt` | Django et ses dépendances, pilote PostgreSQL/binaire, dotenv et Excel ; métadonnées transitives vérifiées |
| Conservation requise | Migrations, sauvegardes, classeurs et documents de recette | Reconstruction des bases et conservation des données et références historiques |

Les surcharges de templates de l'administration ne sont pas des fichiers
orphelins : Django les charge par convention. Même règle pour `apps.py`,
`admin.py`, les commandes et les fonctions connectées aux signaux.

## D. Vérifications exécutées

Les commandes Python utilisent `.venv\Scripts\python.exe` depuis le dépôt.

| Commande ou contrôle | Résultat |
| --- | --- |
| `manage.py test --settings=config.test_settings --noinput` avant nettoyage | 293 tests : 282 réussis, 11 ignorés, aucun échec |
| `manage.py test purchasing.test_admin_decisions purchasing.test_ui_actions purchasing.tests budgeting.test_transfers budgeting.test_transfer_batch_returns config.test_excel --settings=config.test_settings --noinput` | Groupe 1 : 96 tests réussis |
| `manage.py test purchasing.test_flow purchasing.test_configuration purchasing.test_budget_workspace budgeting.test_transfers budgeting.test_transfer_batch_returns receiving.test_purchase_receipts config.test_excel --settings=config.test_settings --noinput` | Groupe 2 : 138 tests réussis |
| `manage.py test --settings=config.test_settings --noinput --verbosity=2` après nettoyage | 293 tests : 282 réussis, les mêmes 11 ignorés, aucun échec |
| `manage.py check --settings=config.test_settings` | Aucune anomalie |
| `manage.py check --settings=config.demo_settings` | Aucune anomalie |
| `manage.py makemigrations --check --dry-run --settings=config.test_settings` | Aucun changement détecté |
| `python -m compileall -q accounts budgeting config purchasing receiving suppliers workflow` | Succès |
| Analyse AST de ces sept répertoires | 199 fichiers Python analysés sans erreur |
| Chargement des templates avec `django.template.loader.get_template` | 57 templates compilés |
| Recherche des références `{% static %}` via les finders Django | Aucun fichier référencé manquant |
| Résolution récursive des URLs Django, administration comprise | 261 patterns chargés |
| Analyse des imports, usages et contextes après nettoyage | Aucun import inutilisé restant hors réexportations de modèles nécessaires ; contextes supprimés sans référence de production résiduelle |
| Compilation V8 avec `new Function` des huit scripts navigateur et du fichier de tests CJS | Neuf fichiers valides syntaxiquement |
| `python -m pip check` | Aucune dépendance cassée |
| `git -c core.safecrlf=false diff --check` | Aucune erreur d'espacement |

Les onze tests ignorés exigent PostgreSQL : verrous concurrents, contraintes
d'exclusion et protections SQL des historiques. La tentative de
`manage.py test purchasing.test_flow_postgresql
--settings=config.postgresql_test_settings --noinput` a été interrompue
pendant l'établissement de la connexion. Un contrôle de connexion séparé,
limité à trois secondes, confirme `connection timeout expired`.
Aucun résultat PostgreSQL n'est présenté comme réussi.

Ruff, Pyflakes, mypy et Node.js ne sont pas installés dans cet environnement.
L'analyse AST, les contrôles Django, la compilation Python et la vérification
syntaxique V8 ont été effectués ; ils ne remplacent pas un lint complet ni
une vérification de types. `node --test tests/theme.test.cjs` n'a pas été
exécuté. Aucun manifeste frontend ni build TypeScript/bundler n'existe dans
ce projet. Il n'y a donc pas de build frontend à valider ; côté backend,
les contrôles Django, templates, imports et compilation ont été validés.

## E. Risques résiduels et vérification manuelle

- Rejouer les onze tests d'acceptation sur une instance PostgreSQL de test
  joignable avant de conclure sur les contraintes et accès concurrents.
- Une recherche statique ne prouve pas l'absence de consommateurs externes :
  conserver les points d'entrée de compatibilité tant que leur abandon
  n'est pas confirmé.
- Un passage navigateur reste utile pour les rôles, les thèmes, l'impression,
  les recherches et les formulaires dynamiques. Aucun navigateur automatisé
  n'est disponible ici ; aucun gain visuel n'est revendiqué.
- Aucune modification de règle métier, de secret ou de donnée n'a été
  réalisée. Aucune migration n'a été appliquée pendant cette mission et
  aucun déploiement n'a été effectué.

## F. Bilan

Les restes certains ont été supprimés, sans déplacer le code dans des
archives. Les vues transportent moins de données abandonnées ; les tests
suivent les composants réellement affichés ; les vérifications redondantes
et deux imports locaux répétés ont disparu.

La nouvelle passe ne révèle pas d'autre suppression certaine de fichier,
de dépendance ou de module. Les exclusions motivées sont documentées au lieu
de retirer du code potentiellement nécessaire. Aucun gain de performance
chiffré n'est revendiqué.
