# Module Ventes — SPEC-VENTES-001 v1.1

Implémentation du 16 novembre 2026. Application Django `sales`, intégrée aux
templates et permissions de BF-ERP. Aucun appel au réseau Peppol n'est effectué.

## Mise en service

Les dépendances `reportlab`, `lxml` et `saxonche` sont fixées dans
`requirements.txt`. Le moteur XSLT Saxon/C exécute les règles Schematron XSLT 2.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
```

Le module est accessible à `/ventes/`. Un utilisateur ayant uniquement des droits
Ventes est orienté vers cette rubrique depuis l'accueil Achats. Un superutilisateur
actif dispose des droits ; les autres utilisateurs doivent recevoir les permissions
Ventes via leurs rôles ERP ou droits individuels.

Avant de facturer :

1. Ouvrir **Ventes → Émetteur**, saisir l'identité légale, l'adresse, les identifiants
   fiscaux et l'IBAN. Ne pas utiliser de coordonnées de démonstration en production.
2. Créer un client actif, compléter son adresse et choisir explicitement son format
   de facturation. Aucun format n'est imposé silencieusement aux nouveaux clients.
3. Pour XML, renseigner les identifiants électroniques et schémas EAS du client
   et de l'émetteur, et une référence acheteur ou de commande fournie par le client.
   Le numéro interne de commande n'est pas présenté comme une référence acheteur.
   Un identifiant syntaxiquement valide ne prouve pas l'inscription
   effective d'un destinataire au réseau : cette V1 ne consulte pas d'annuaire Peppol.
4. Créer une commande avec au moins une ligne, enregistrer le brouillon, confirmer,
   puis générer la facture complète.

Les contrôles ne déterminent pas automatiquement le régime fiscal d'une formation
ou l'assujettissement légal d'une opération. Ces choix doivent être confirmés par
le service compétent. L'ERP exige une catégorie et un taux explicites, ainsi qu'un
motif pour exonération, autoliquidation ou hors champ.

## Choix de V1

- Devise : EUR. Quantités et prix à quatre décimales, remises en montant HT à deux
  décimales. Les montants monétaires sont calculés avec `Decimal`, arrondi commercial.
- HT arrondi par ligne ; TVA calculée par catégorie/taux/motif. La répartition
  cumulative des arrondis sur les lignes conserve l'égalité avec les totaux.
- Catalogue de formations indépendant du stock ; une description libre est également
  possible. La sélection d'une formation préremplit description et unité.
- Séries annuelles : `CV-AAAA-NNNN` et `FV-AAAA-NNNN`. Compteurs verrouillés et
  références uniques en base. La séquence n'est jamais recalculée par comptage.
- Une facture complète par commande, garantie par `OneToOneField` en base.
- Les commandes confirmées ne se modifient plus librement. Une commande facturée
  ne s'annule pas. Les données commerciales/fiscales d'une facture sont figées.
- Paiements manuels positifs, avec référence, date et jeton d'idempotence. Les
  trop-perçus et dates futures sont refusés. Une correction crée une neutralisation
  distincte ; elle ne supprime pas le paiement. Le statut est recalculé.
- Les droits portent sur l'ensemble des dossiers Ventes. Aucun cloisonnement par
  CDF/support n'est présumé. Les dimensions sont analytiques et facultatives.
- Avoirs, acomptes, facturation partielle et comptabilité générale restent exclus.

## Modèles et services

`sales/models.py` contient : `Customer`, `TrainingService`, `IssuerConfiguration`,
`SalesSequence`, `SalesOrder`, `SalesOrderLine`, `SalesInvoice`, `SalesInvoiceLine`,
`InvoiceDocument`, `InvoiceValidationRun`, `InvoicePayment`, `PaymentReversal`,
`SalesEvent`.

`sales/services.py` centralise les permissions, validations, révisions, transitions,
numérotation, émission et paiements. `sales/documents.py` produit les PDF et XML,
valide les XML et archive les fichiers. Les vues utilisent ces services ; les
actions de mutation sont exclusivement POST avec protection CSRF.

L'administration Django présente les données en lecture seule. Les opérations
passent par les écrans métier pour préserver les validations et l'audit.

## Émission et reprise documentaire

La préparation et la validation du document ont lieu avant validation de la
transaction d'émission. Un XML invalide ou une erreur de génération à ce stade
ne crée pas de facture et ne consomme pas définitivement de numéro. Les refus
documentaires sont journalisés sur la commande.

Une fois la transaction validée, la facture, ses lignes, ses instantanés et son
numéro existent définitivement. La commande passe à `INVOICED`. L'archivage passe
la facture à `ISSUED`, ou conserve `DOCUMENT_ERROR` avec un événement d'échec.
Une interruption du processus entre les deux étapes laisse également une facture
en erreur documentaire, récupérable par **Régénérer le document**.

La régénération produit une nouvelle version documentaire de la même facture,
sans consulter les valeurs actualisées du client ou de l'émetteur. Les fichiers
et résultats de validation précédents restent conservés.

Le statut documentaire est indépendant du paiement. `DOCUMENT_ERROR` désigne une
facture déjà émise dont le document demande une reprise, pas une facture supprimable.
Les états `DRAFT` et `CANCELLED_BEFORE_ISSUE` sont réservés à une éventuelle
préparation persistée ultérieure ; le flux actuel prépare en mémoire.

## Validation XML hors ligne

Les artefacts officiels sont versionnés dans `sales/validation_rules/` :

- XSD UBL 2.1 définitifs OASIS et leurs dépendances ;
- Schematron EN 16931 et Peppol, incluant les règles nationales qu'ils contiennent ;
- sources et compilateur Schematron, feuilles XSLT compilées ;
- manifeste des URL, empreintes SHA-256, version et intervalle de validité approuvé.

Le manifeste référence le commit OpenPeppol
`38d693d71d28d813781323a6ca97324edcc4d239` et les règles publiées pour la version
3.0.21. Source officielle : <https://docs.peppol.eu/poacc/billing/3.0/release-notes/>.
Ces règles sont obligatoires à partir du 17 août 2026.

**Une revue conservatrice est fixée au 1er décembre 2026.** Cette date est une
limite locale de vérification, pas une date officielle de remplacement. Au-delà,
une émission XML sera bloquée tant que l'applicabilité du jeu de règles n'aura pas
été revue. Ne pas étendre cette période automatiquement ni remplacer les artefacts
sans campagne de validation. Les factures antérieures sont revalidées selon leur
date d'émission ; conserver les jeux applicables lors d'une évolution du mécanisme.

L'absence d'artefact, une empreinte incorrecte, une date non couverte ou un moteur
indisponible donnent `UNAVAILABLE`, jamais `VALID`. Une erreur XSD ou assertion
fatale donne `INVALID`. Les avertissements sont conservés mais ne remplacent pas
les contrôles obligatoires. Les erreurs sont détaillées dans l'historique de
validation. DTD et entités externes sont interdites ; aucun accès réseau n'est
nécessaire pour générer ou valider une facture.

`tools/install_sales_rules.py` permet une réinstallation explicite des artefacts
officiels. Ce script n'est jamais appelé par une requête de facturation. Une mise
à jour réglementaire exige de mettre à jour les sources épinglées, l'intervalle,
les tests et le manifeste ensemble.

Le statut conforme couvre les validations techniques intégrées. Il ne constitue
ni une preuve de transmission, ni une qualification fiscale de l'opération.

## Documents privés et historique

Le stockage est `private_documents/sales/`, configurable par `SALES_DOCUMENT_ROOT`,
hors `STATIC_URL` et de toute exposition média. Ne pas configurer de desserte HTTP
directe de ce répertoire. Les téléchargements passent par une vue authentifiée,
le droit `download_salesinvoice`, le rattachement du document à la facture et un
contrôle SHA-256. Les réponses interdisent la mise en cache partagée et le sniffing.

Sauvegarder la base et ce répertoire ensemble. Les empreintes détectent une
altération des fichiers ; elles ne constituent pas un archivage probant certifié.
La durée de conservation et la politique de sauvegarde restent à définir par
l'organisation. En cas d'échec DB après écriture d'un fichier, un fichier orphelin
peut subsister ; ne pas le supprimer automatiquement sans rapprochement préalable.

`SalesEvent` conserve les opérations métier et l'identité de l'acteur. Le journal
générique `workflow.ActivityLog` reçoit aussi les actions. Les paiements, corrections,
documents et validations sont des enregistrements ajoutés à l'historique.

## Permissions

Réutilisation du backend des rôles ERP. Droits CRUD usuels pour clients, formations
et brouillons, puis droits distincts :

- `configure_customer_billing` ;
- `confirm_salesorder`, `cancel_salesorder` ;
- `issue_salesinvoice`, `view_salesinvoice`, `download_salesinvoice` ;
- `regenerate_salesinvoice` pour régénération et revalidation ;
- `record_invoicepayment` pour enregistrement et neutralisation ;
- `view_salesreport` pour le suivi analytique ;
- `change_issuerconfiguration` pour l'émetteur.

Les champs de format/conditions/identification Peppol ne sont pas modifiables par
un simple éditeur client dépourvu du droit de configuration de facturation.
La visibilité d'un lien ne dispense jamais du contrôle côté serveur.

## Budget et stock

Le suivi distingue trois mesures indépendantes :

| Indicateur | Date de filtre | Base |
| --- | --- | --- |
| Commandes confirmées, y compris déjà facturées | Date de commande | HT |
| Factures émises, même en erreur documentaire | Date d'émission | HT |
| Paiements non neutralisés | Date de paiement | TTC |

Les deux premières mesures peuvent être filtrées et regroupées par CDF,
financement, produit budgétaire et support. Les données figées des lignes de
facture conservent également le libellé historique des dimensions.

Les paiements sont présentés globalement par période/client. Aucune répartition
par dimension n'est inventée pour un paiement partiel d'une facture multi-imputation.
L'interface signale cette limite. Une règle d'allocation des paiements et de
reconnaissance du chiffre d'affaires doit être validée avant extension.

Aucune écriture n'est ajoutée aux réservations/engagements d'achat. Aucun appel
aux services de mouvement, réservation ou réception de stock n'est effectué.

## Migrations et fichiers partagés

Deux migrations consolidées :

1. `sales/0001_initial.py` : tables, permissions, relations et contraintes.
2. `sales/0002_history_guards.py` : protections PostgreSQL des factures, lignes,
   commandes confirmées et historiques. Réversible pour un retour de schéma QA.

Les protections de modèle et de QuerySet s'appliquent également en démonstration
SQLite. Les triggers et garanties de verrouillage PostgreSQL sont propres à ce
moteur ; SQLite n'est pas une preuve des garanties de concurrence en production.

Adaptations partagées : configuration/routes, navigation et fil d'Ariane,
orientation de l'accueil pour les utilisateurs Ventes, libellés de permissions,
dépendances et exclusions Git des documents et de `.qa/`. Le délai de connexion
des paramètres de test PostgreSQL est borné à cinq secondes.

## Vérifications

```powershell
.venv\Scripts\python.exe manage.py test --settings=config.test_settings --noinput
.venv\Scripts\python.exe manage.py test sales --settings=config.postgresql_test_settings --noinput
node --test tests/theme.test.cjs
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
```

Pour une instance PostgreSQL Windows de test isolée, le script
`tools/run_postgresql_acceptance.py --download` télécharge explicitement les
binaires officiels EDB dans `.qa/postgres/`, initialise un cluster de test local,
écoute uniquement sur `127.0.0.1` et arrête le serveur en fin de campagne. Aucun
service Windows n'est installé. L'authentification locale `trust` de ce cluster
est réservée aux données de test, sans données métier.

Relancer sans téléchargement :

```powershell
.venv\Scripts\python.exe tools/run_postgresql_acceptance.py sales
.venv\Scripts\python.exe tools/run_postgresql_acceptance.py accounts budgeting purchasing receiving suppliers workflow sales config
```

Les résultats de la campagne sont conservés dans `.qa/postgres/acceptance.log`.
La recette navigateur reste distincte des tests HTTP Django.
