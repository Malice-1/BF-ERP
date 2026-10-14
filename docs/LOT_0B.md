# Lot 0b — habilitations et interface des brouillons

## Fonctionnalités

- `/connexion/` : authentification Django ; `/achats/` : demandes du seul utilisateur connecté.
- Création brouillon, fournisseur modifiable, ajout/modification/suppression des lignes, annulation après écran de confirmation. Chaque mutation appelle un service transactionnel avec révision attendue et audit. Aucune édition de demande soumise ou terminale.
- Montants HTVA/TVA/TVAC calculés exactement, sans arrondi ; aucun taux n'est supposé pour les lignes historiques.
- `/habilitations/` : création et nouvelle version d'habilitation, validité temporelle, activation/désactivation, périmètres CDF/financement/produit budgétaire. Une sélection vide signifie global pour ce critère. ET entre critères, OU entre valeurs ; aucune fusion de permissions partielles. Sélection déterministe par identifiant d'habilitation.
- `/responsables-cdf/` : affectations datées, clôture explicite et conservation de l'historique. Intervalles `[début, fin)` ; absence de responsable possible. Clôturer une affectation ouverte avant de créer son remplacement.
- Fonctions ordonnées configurables dans l'administration Django ; aucun ordre métier préchargé comme décision validée.
- Les demandes/lignes et historiques d'habilitation/affectation sont consultables sans mutation dans l'administration. Les modifications locales préexistantes de `purchasing/admin.py` sont conservées, avec durcissement des permissions de mutation.

## Accès et exigences

| Exigence | Couverture |
|---|---|
| ACH-001 | Brouillon/lignes, produit, quantité, prix, TVA, CDF/financement ; soumission/commande à venir |
| ACH-003/005 | Aucune édition par les services pour demandes soumises ou terminales ; demandeur actif seulement |
| ACH-004 | Annulation brouillon/correction ; soumission et libération de réservations pas encore disponibles |
| ACH-021 | Ordre global unique des fonctions |
| HAB-001/002 | Versions, validité, périmètres et vérification d'éligibilité ; raccordement à affectation/exécution du workflow à venir |
| HAB-003 | Référence/version retournées par le sélecteur ; preuves d'approbation à venir |
| ORG-001 | Historique, non-chevauchement sous verrou et exclusion PostgreSQL, périodes vides possibles |
| Transversal | CSRF, contrôles serveur, audit atomique, révision optimiste, calcul Decimal |

La gestion des habilitations nécessite `accounts.manage_authorizations`. La gestion des responsables nécessite `budgeting.manage_cost_center_managers`. Ces droits se donnent aux utilisateurs/groupes dans l'administration Django. Ils ne confèrent pas de lecture financière d'autres demandes. L'accès direct aux brouillons reste réservé à leur propriétaire.

Les fonctions se configurent via les permissions Django standards sur ValidationFunction. Les versions d'habilitation sont publiées via les services/écrans dédiés, et non modifiées directement. Désactiver crée une nouvelle version ; l'ancienne reste intacte. Le service refuse une publication fondée sur une version périmée.

## Migrations et démarrage

Nouvelles migrations : accounts 0002/0003, budgeting 0008/0009, workflow 0002, en plus des migrations du premier incrément. Aucune donnée utilisateur, aucun rôle ni seuil métier créés automatiquement.

Avant utilisation sur la base configurée :
```
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```
Ouvrir `/connexion/`, puis `/achats/`. Les fournisseurs et référentiels nécessaires aux lignes doivent déjà exister ; ils se gèrent dans l'administration.

La migration PostgreSQL budgeting 0009 installe `btree_gist`, puis une contrainte d'exclusion des intervalles. Le compte exécutant les migrations doit pouvoir installer cette extension, ou l'exploitant doit l'installer au préalable. accounts 0003 installe un trigger qui interdit UPDATE/DELETE des versions d'habilitation, y compris via QuerySet. Ces migrations SQL sont ignorées sur SQLite, qui reste uniquement un environnement de tests unitaires.

## Vérification

```
.venv\Scripts\python.exe manage.py test --settings=config.test_settings
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.venv\Scripts\python.exe manage.py check --settings=config.test_settings
```

26 tests unitaires/intégration couvrent périmètres, validité, versionnement, droits, conflits de révision, création/modification/suppression et annulation, CSRF, isolation des demandes et calculs exacts.

Trois tests PostgreSQL complémentaires couvrent l'exclusion SQL, deux affectations concurrentes et l'immutabilité SQL des versions. Ils sont ignorés avec les paramètres SQLite. Ils doivent passer sur une base PostgreSQL de tests avant mise en service :
```
.venv\Scripts\python.exe manage.py test accounts.test_postgresql budgeting.test_postgresql
```
Cette commande utilise la configuration PostgreSQL habituelle et crée une base de tests ; elle nécessite le droit approprié. La base configurée n'a pas été modifiée ni utilisée pour cette vérification pendant le présent lot.

## Limites et prochaine étape

Pas encore de délégations, moteur de règles, preuves d'approbation, notifications d'habilitation, réservations ni commandes. La soumission n'est pas exposée. Les catégories ne sont pas un référentiel défini dans le dépôt ; elles ne sont pas acceptées comme critère avant leur cadrage.

Les périodes saisies dans les écrans de configuration sont explicitement en UTC, selon le paramétrage Django existant. Le passage à une saisie locale Europe/Brussels peut être ajouté sans changer les dates stockées.

L'audit applicatif trace les versions d'habilitation, affectations et mutations de brouillon. L'audit des modifications de fonctions utilise le journal natif Django admin. La protection SQL append-only de l'audit global reste à faire. Le serveur Django actuel reste une configuration de développement.

Prochain lot : budgets annuels/versionnés et réservations TVAC exactes, puis configuration et exécution du workflow, avec soumission atomique de toutes les lignes.
