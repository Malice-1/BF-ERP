# Comptabilité — phase 1 : moteur et plan d'un organisme public

Implémentation du 16 novembre 2026, consécutive au diagnostic
[AUDIT_COMPTABILITE_PHASE_0.md](AUDIT_COMPTABILITE_PHASE_0.md).
Le cadre « plan spécifique à un organisme public » a été confirmé par l'utilisateur.

## Périmètre livré

Espace `/comptabilite/`, plan de comptes configurable/importable, journaux Achats,
Ventes, financiers et OD, exercices et périodes, écritures en partie double,
brouillons, validation définitive, contrepassation, audit et permissions séparées.

Le livrable de phase 1 ne couvre pas l'OCR, l'import de factures fournisseurs,
comptabilisation automatique de ventes/paiements, avoirs, imports CODA/CAMT,
rapprochement, calcul de TVA/Intervat, transmission Peppol, clôture annuelle,
report de soldes, reporting statutaire, immobilisations ou ventilation analytique.

Une extension ultérieure, demandée explicitement, ajoute l'import manuel des factures
fournisseurs XML : voir [IMPORT_XML_FOURNISSEURS.md](IMPORT_XML_FOURNISSEURS.md).
Elle ne comptabilise pas automatiquement les factures ni ne réalise les autres phases.

Les journaux portent les types nécessaires aux phases suivantes ; leur création
ne déclenche aucun automatisme fiscal. Les écritures budgétaires restent distinctes
du grand livre comptable. Aucune réservation ou consommation de budget/stock n'est
créée par une écriture de phase 1.

## Cadre public et validation réelle

Le dépôt ne contient pas le plan propre à l'organisme public et aucune annexe
spécifique à cette entité n'a été fournie. Aucun plan privé ni taux/régime fiscal
n'est donc inventé ou activé automatiquement.

Le moteur est utilisable pour préparer des brouillons ; la validation exige :

1. Une identité légale existante, via `sales.IssuerConfiguration`.
2. Le cadre public, la référence officielle du plan applicable et la justification
   de sa revue dans **Comptabilité → Cadre et approbation**.
3. Un plan réel saisi ou importé, avec au moins deux comptes d'imputation actifs.
4. L'approbation explicite par un utilisateur habilité, sur la révision courante.

Cette approbation interne enregistre l'acteur, la date et le motif ; elle ne
remplace pas une validation réglementaire réelle par les personnes compétentes.
Les plans PCMN entreprises/associations figurent comme cadres possibles, sans
peuplement automatique. Leurs règles ne sont pas appliquées par défaut au public.

Toute modification d'un compte ou du cadre retire l'approbation. Une identité
d'émetteur modifiée bloque le posting jusqu'à nouvelle revue. Après un premier
posting, l'identité légale du grand livre ne peut pas être réaffectée à une autre
entité. Les libellés historiques de chaque écriture restent figés.

Références vérifiées pendant l'audit :

- [PCMN entreprises, CNC](https://www.cnc-cbn.be/fr/node/1670)
- [PCMN associations/fondations, CNC](https://www.cnc-cbn.be/fr/node/1672)
- [Tenue et conservation des livres, CNC](https://www.cnc-cbn.be/fr/node/1641)
- [Conservation informatique, CNC](https://www.cnc-cbn.be/fr/avis/conservation-des-livres-et-pieces-justificatives-en-cas-de-tenue-de-comptabilite-informatisee)

Ces références ne déterminent pas à elles seules le cadre de l'organisme public.
La durée de conservation et les formalités propres à l'entité doivent être
validées avant production. Aucun délai légal n'est codé par supposition.

## Première utilisation

1. Configurer l'identité légale dans **Ventes → Émetteur**, si elle est absente.
   La comptabilité réutilise cet enregistrement ; elle ne crée pas une société parallèle.
2. Configurer le cadre public et la référence du plan.
3. Saisir/importer les comptes et faire approuver le plan adapté.
4. Créer un exercice sans chevauchement avec les exercices existants.
5. Créer des périodes non chevauchantes comprises dans cet exercice. Les périodes
   peuvent être mensuelles, trimestrielles ou annuelles : aucun rythme n'est présumé.
6. Créer les journaux nécessaires, avec codes distincts.
7. Saisir un brouillon comprenant au moins deux lignes. Le brouillon peut être
   déséquilibré pendant sa préparation.
8. Renseigner la pièce justificative et valider séparément. Le système attribue
   alors le numéro définitif, fige les données et enregistre l'acteur.

Le bouton **Fermer** d'une période bloque les nouvelles écritures et modifications
de brouillons dans cette période. Une réouverture exige un droit distinct et un
motif. Ce mécanisme n'effectue pas la clôture annuelle comptable de phase 7.

## Import du plan de comptes

Import explicite d'un CSV UTF-8, séparé par `;`, limité à 2 Mo et 10 000 lignes.
Le modèle vierge est téléchargeable depuis l'écran d'import. En-têtes exacts :

```csv
code;label;postable;party_requirement
```

- `code` : 1 à 12 chiffres ; les zéros initiaux sont conservés.
- `label` : libellé réel du plan applicable.
- `postable` : `1` pour une imputation, `0` pour un regroupement.
- `party_requirement` : `NONE`, `CUSTOMER` ou `SUPPLIER`, suivant le paramétrage validé.

Aucun compte d'exemple n'est présenté comme une règle du plan public. Les codes,
classements et exigences de tiers sont fournis par l'organisation.

Un import identique, de même empreinte et référence, est idempotent. Un compte
déjà existant avec des paramètres incompatibles provoque un refus ; il n'est pas
écrasé. Une erreur annule tout le lot. L'import conserve SHA-256, référence,
date et nombre de lignes dans le profil, et retire son approbation.

Un compte utilisé ne peut pas changer de code, de type d'imputation ou de type
de tiers. Son libellé peut être corrigé et il peut être désactivé, avec audit et
nouvelle approbation. Une contrepassation exacte peut utiliser un compte historique
désactivé ; une nouvelle saisie ordinaire ne le peut pas.

## Invariants du moteur

- Devise de phase 1 : EUR, montants `Decimal`, deux décimales. Aucun arrondi silencieux
  d'une troisième décimale ; valeurs négatives, NaN et infinis refusés.
- Une ligne comporte un débit strictement positif et un crédit nul, ou l'inverse.
- Chaque écriture contient de 2 à 200 lignes.
- Validation uniquement si débit total = crédit total > 0, calculé sur les lignes
  réelles, jamais sur les seuls totaux fournis par un formulaire.
- Comptes d'imputation actifs, tiers du type requis et journal actif obligatoires.
- Période/exercice ouverts et date comptable comprise dans la période.
- Une référence de pièce justificative est requise à la validation. L'import et
  l'archivage d'une nouvelle pièce relèvent de la phase 2 ; aucune archive n'est simulée.
- Révision optimiste pour refuser l'écrasement d'un brouillon modifié dans un autre onglet.
- Numéro attribué au posting, dans la transaction de l'écriture, par journal et
  exercice : `CODEJOURNAL-CODEEXERCICE-000001`. Pas de numéro définitif en brouillon.
- Ordre chronologique dans chaque journal/exercice. Une pièce ancienne peut garder
  sa date documentaire avec une date comptable autorisée ; aucune insertion rétroactive
  silencieuse avant la dernière date comptable de la série.
- Jeton UUID unique de saisie ; une répétition identique retrouve la même écriture.
  Une réutilisation avec un autre contenu est refusée.
- Origines externes typées et identifiants uniques sont prévus pour les intégrations
  futures, sans traitement automatique en phase 1.

Les snapshots figent identité/cadre/plan, journal, exercice/période, comptes et tiers.
Changer un fournisseur ou un libellé de compte ne réécrit pas une écriture validée.

## Contrepassation

Une écriture validée ne se modifie ni ne se supprime, y compris depuis l'admin.
L'action **Contrepasser** exige une période ouverte, une date non antérieure à
l'origine, un motif et le droit distinct correspondant.

Elle crée une nouvelle écriture validée, exactement inverse, dans le même journal,
avec référence à l'original et conservation de ses snapshots. La période de
destination peut appartenir à l'exercice suivant si la période initiale est fermée.
Une contrainte unique interdit une seconde contrepassation de l'original ; une
répétition identique avec le même jeton est idempotente. Une contrepassation n'est
pas elle-même contre-passée automatiquement dans cette V1.

L'original reste `POSTED` et visible ; le lien de contrepassation est affiché dans
les deux sens. Aucun état « supprimé » ne masque l'écriture initiale.

## Intégrité et concurrence

Les services prennent d'abord un verrou sur le profil comptable, puis sur les
références, périodes, écritures et compteurs concernés. Le verrou global du profil
privilégie une sérialisation simple et sûre en phase 1. Il pourra devenir un point
de contention à mesurer avant une montée en charge ; ne pas le retirer sans
nouvelle démonstration des invariants.

PostgreSQL complète les validations applicatives par des triggers : équilibre réel
au posting, ligne immuable, entité approuvée courante, compteurs monotones,
contrepassation exacte, absence de chevauchement des dates et protection de l'audit.
La validation et la fermeture d'une période ne peuvent pas se croiser sans contrôle.
Les écritures validées ne peuvent plus recevoir de lignes, même par SQL direct.

SQLite conserve les contraintes de ligne et protections d'immuabilité de base ;
ses tests ne prouvent pas les garanties de verrouillage de PostgreSQL. L'équilibre
complet et l'applicabilité sont validés par les services sur les deux moteurs et
défendus aussi au niveau PostgreSQL pour la cible de production.

La suppression d'un utilisateur peut détacher ses identifiants facultatifs tout
en conservant ses noms historiques. La suppression de maintenance de BF-ERP refuse
désormais de supprimer des données comptables ou de détacher des références métier
utilisées par celles-ci. Ce refus précède toute mutation, avec HTTP 403 dans l'admin.

Ces protections ne remplacent pas une séparation des rôles PostgreSQL, les
sauvegardes et la protection des supports. Un administrateur de base capable de
supprimer les triggers ou les tables reste hors du modèle d'autorisation applicatif.

## Permissions et audit

Backend existant des rôles ERP, groupes et permissions Django. Toutes les mutations
sont POST + CSRF et appellent des services qui vérifient également les droits.

| Action | Droits |
| --- | --- |
| Consulter | Permissions `view_*` des modèles concernés |
| Configurer le cadre | `change_accountingprofile` |
| Approuver le cadre/plan | `approve_accountingprofile` |
| Plan | `add_account`, `change_account`, `import_account` |
| Journaux | `add_journal`, `change_journal` |
| Exercices/périodes | `add_fiscalyear`, `add_accountingperiod` |
| Brouillons | `add_journalentry`, `change_journalentry` |
| Valider | `post_journalentry` |
| Contrepasser | `reverse_journalentry` |
| Fermer / rouvrir une période | `lock_accountingperiod` / `reopen_accountingperiod` |

La visibilité d'un lien n'est pas une autorisation serveur. Un utilisateur ayant
uniquement des droits Comptabilité est orienté vers cette rubrique depuis l'accueil.
Les droits portent sur l'entité unique de BF-ERP ; aucun cloisonnement multi-sociétés
n'est simulé. Les modèles sont exposés en lecture seule dans l'administration.

`AccountingEvent` conserve les opérations et l'acteur avec un lien vers l'écriture.
Les mêmes opérations alimentent `workflow.ActivityLog`. Les événements de configuration
restent accessibles dans ce journal général ; chaque écriture dispose de son historique.

## Architecture et migrations

Fichiers créés sous `accounting/` : modèles, services, formulaires, vues, routes,
admin en lecture seule, templates, CSS/JS et modèle CSV, tests SQLite/HTTP et PostgreSQL.

Modèles : `AccountingProfile`, `Account`, `FiscalYear`, `AccountingPeriod`, `Journal`,
`EntrySequence`, `JournalEntry`, `JournalEntryLine`, `AccountingEvent`. L'identité,
clients, fournisseurs et documents de factures sont réutilisés via clés étrangères.
Les liens facultatifs `source_invoice`/`source_document` préparent les phases 3/6.

Migrations uniquement additives :

1. `0001_initial` : schéma, droits, contraintes et relations vers les tables existantes.
2. `0002_ledger_guards` : protections SQL sur les tables comptables nouvelles.
3. `0003_accountingprofile_approved_issuer_snapshot` : identité revue dans le profil.
4. `0004_entity_approval_guard` : contrôle PostgreSQL de l'identité lors du posting.

Aucune table ni donnée métier existante n'est supprimée. Aucun plan réel, exercice,
journal ou écriture fictive n'est injecté dans la démonstration. Aucun peuplement
fiscal automatique n'est réalisé par les migrations.

Fichiers existants adaptés : `config/settings.py`, `config/urls.py`, navigation,
fil d'Ariane et accueil dans `purchasing/`, libellés des droits et protection de
maintenance dans `accounts/`. Les changements Ventes antérieurs restent conservés.

Aucune dépendance externe supplémentaire pour cette phase.

## Vérifications et activation

```powershell
.venv\Scripts\python.exe manage.py test accounting --settings=config.test_settings --noinput
.venv\Scripts\python.exe tools/run_postgresql_acceptance.py accounting
.venv\Scripts\python.exe tools/run_postgresql_acceptance.py accounts budgeting purchasing receiving suppliers workflow sales config accounting
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
node --check accounting/static/accounting/ledger.js
node --test tests/theme.test.cjs
```

Pour la démonstration, sauvegarder SQLite de façon cohérente avant :

```powershell
.venv\Scripts\python.exe manage.py migrate accounting --settings=config.demo_settings --noinput
```

Les tests PostgreSQL utilisent le cluster isolé déjà disponible sous `.qa/`, limité
à `127.0.0.1`, puis arrêté par le script. Aucune migration de base métier PostgreSQL
n'est effectuée par cette campagne. Les résultats réels sont consignés séparément
dans `RESULTATS_COMPTABILITE_PHASE_1.md`.

Une recette visuelle et une revue par les responsables comptables restent distinctes
des tests HTTP automatisés. Le passage à la phase 2 demande la validation de la phase 1.
