# BF-ERP

ERP interne de Bruxelles Formation. L’application Django couvre les achats, les budgets et transferts, les stocks et réceptions, les ventes, la comptabilité et les ressources humaines.

## Démarrer depuis un clone

Commande à exécuter dans PowerShell avec Python 3.14 disponible. Si le dépôt est déjà ouvert, commence à la création de l’environnement virtuel.

```powershell
git clone https://github.com/Malice-1/BF-ERP.git
cd BF-ERP
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py seed_purchase_demo --settings=config.demo_settings --password 'DemoBfErp!2026'
.\demarrer-recette.cmd
```

Ouvre [la page de connexion](http://127.0.0.1:8000/connexion/) et connecte-toi avec `demo.admin` et le mot de passe passé à la commande de génération. La commande crée aussi des profils de recette aux droits distincts. Sur une base de démonstration existante, leurs mots de passe sont conservés.

La démo utilise `db.demo.sqlite3` et écrit les courriels dans la console. Pour écouter sur le réseau de recette, lance `.\demarrer-recette.cmd <IPv4 locale>` avec l’adresse attribuée à cette machine. Depuis un autre système, utilise l’exécutable Python de l’environnement virtuel et `python manage.py runserver --settings=config.demo_settings`.

## Vérifier une modification

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings --noinput
```

Pour cibler un module, ajoute son nom à `manage.py test`, par exemple `manage.py test purchasing budgeting --settings=config.test_settings --noinput`. La suite locale utilise SQLite en mémoire. Pour les verrous, les accès concurrents et les contraintes propres au moteur, configure une instance de test PostgreSQL avec les variables `TEST_PG_*` puis utilise `config.postgresql_test_settings`. [Configuration PostgreSQL et exploitation](docs/DOCUMENTATION_TECHNIQUE.md#8-installation-tests-et-exploitation)

## Se repérer dans le dépôt

- [AGENTS.md](AGENTS.md) pour la carte du code, les règles métier et les consignes de vérification.
- [Documentation fonctionnelle](docs/DOCUMENTATION_FONCTIONNELLE.md) pour les parcours et les rôles.
- [Documentation technique](docs/DOCUMENTATION_TECHNIQUE.md) pour l’architecture, les données et l’exploitation.
- [Plan de tests](docs/PLAN_TESTS.md) pour les profils, les jeux de données et les scénarios de recette.
