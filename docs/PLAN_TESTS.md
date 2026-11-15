# ERP — Plan de tests professionnel et cahier de recette

Référence : code BF-ERP du 14 novembre 2026, base Git `dc67883` et modifications
locales. Le classeur [PLAN_TESTS.xlsx](PLAN_TESTS.xlsx) reprend les cas avec
colonnes de suivi, procédures, attendus, preuves, anomalies et campagnes.
La [documentation fonctionnelle](DOCUMENTATION_FONCTIONNELLE.md) définit le
comportement du produit ; la [documentation technique](DOCUMENTATION_TECHNIQUE.md)
décrit le code, la base, les contrôles et mesures de performance.

## 1. Stratégie et niveaux de test

Le périmètre couvre authentification, sessions, rôles, responsables,
fournisseurs, référentiels, budgets, import/export, DA, validations,
délégations, commandes, transferts, stock, réceptions, journal et maintenance.

| Niveau | Finalité | Exécution |
| --- | --- | --- |
| Unitaire pur | Formats monétaires, normalisation des références/en-têtes et classification de réception | SimpleTestCase, sans accès DB |
| Intégration métier | Transactions, états, calculs, révisions, idempotence et audit | Tests Django avec base jetable |
| Intégration HTTP | Formulaires, routes, droits, CSRF, HTML/JSON/XLSX | Client Django, données de classe préparées automatiquement |
| Acceptation PostgreSQL | Verrous, concurrence, contraintes d'exclusion et guards SQL | Instance PostgreSQL de test dédiée |
| Recette fonctionnelle | Parcours précis par profil et non-régression visuelle | Navigateur réel, classeur renseigné manuellement |
| Bout en bout | Du budget à l'achat, la validation et la livraison, ou transfert avec effets croisés | Cas E2E sur jeu QA indépendant |
| Sécurité | Cloisonnement, méthode HTTP, CSRF, falsification, fichiers et journaux | Cas ciblés en environnement autorisé |
| Performance | Temps serveur, SQL, octets, mémoire puis charge concurrente cible | Script isolé et protocole PostgreSQL distinct |

Les tests d'intégration ne sont pas présentés comme des tests unitaires purs.
Un test de client Django ne prouve pas le comportement du JavaScript dans un
navigateur. Le fichier CJS de thème ne remplace pas une recette visuelle.

## 2. Préparation de l'environnement

1. Préparer une copie isolée du dépôt et une base QA neuve ou restaurable.
   Ne jamais lancer les cas de suppression/maintenance sur une base métier.
2. Relever commit, modifications locales, Python, Django, moteur/version DB,
   système, navigateur/version, fuseau et paramètres fonctionnels de session.
3. Installer les dépendances dans le venv et appliquer les migrations de
   cette seule instance QA. Vérifier `manage.py check`.
4. Créer les profils et données ci-dessous. Aucun mot de passe réel n'est
   requis dans les documents ; utiliser une valeur QA communiquée au testeur.
5. Configurer les courriels sur console ou boîte de test contrôlée. Aucun
   scénario ne doit envoyer à un fournisseur ou utilisateur réel.
6. Capturer le point de restauration et les soldes initiaux. Un cas ne doit
   pas hériter des consommations du précédent, sauf précondition explicite.

Exemples, uniquement depuis la copie QA :

```powershell
.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.venv\Scripts\python.exe manage.py createsuperuser --settings=config.demo_settings
.venv\Scripts\python.exe manage.py runserver --settings=config.demo_settings
```

Le script `demarrer-recette.cmd` utilise la base de démonstration du dépôt
où il est lancé. La commande `seed_purchase_demo` est un démarrage pratique,
mais son jeu ne remplace pas les profils et combinaisons du présent plan.

## 3. Jeu de données de référence

| Objet/profil | Configuration attendue |
| --- | --- |
| Année Y | Année locale Europe/Brussels du jour de recette |
| ADMIN | Compte QA actif superutilisateur ; pas utilisé pour simuler un profil restreint |
| DEMANDEUR / DEMANDEUR-B | Comptes actifs séparés, droit add_purchaserequest ; deuxième compte pour tests de propriété |
| CDF-A / CDF-B | Responsables de CDF distincts ; rôle financier de lecture uniquement si le cas exige le détail de DA |
| BUDGET | MANAGER_PERMISSIONS : add_annualenvelope, add_envelopeversion, change_envelopeversion, add_allocation, change_allocation, delete_allocation dans budgeting ; ajouter view_budget_balances et droits produits/transferts nécessaires au cas |
| FOURNISSEUR | view_supplier, add_supplier, change_supplier selon variante |
| STOCK | receiving.manage_stock et droits dépôt/lecture nécessaires ; pas de droits financiers d'achat |
| SUIVI | purchasing.monitor_purchases seul pour les contrôles de non-divulgation |
| LECTEUR | Seulement les permissions explicitement indiquées par le cas |
| CDF-A, CDF-B, CDF-C | Référentiels distincts ; CDF-C non alloué sauf instruction |
| F-QA, BI-A | Financement et produit budgétaire du jeu commun |
| QA-ARTICLE-A | Produit détaillé rattaché à BI-A |
| QA-FOU | Fournisseur de test, nom Société QA, TVA fictive |
| QA-SP1 / QA-SP2 | Supports ; appartenance et responsabilité séparées |
| QA-V1 | Version de Y ; allocation A/F-QA/BI-A = 1 000 ; destination B selon cas |
| QA-DEP-A / QA-DEP-B | Dépôts ; solde initial de QA-ARTICLE-A = 0 sauf précondition |

Créer les références depuis l'administration ou les écrans correspondants.
Attribuer les droits via rôles ou permissions individuelles ; reconnecter
l'utilisateur après changement pour éviter de tester une instance en cache.
Publier QA-V1 seulement pour les cas de réservation d'achat. Les cas d'import
en brouillon utilisent une version différente pour rester indépendants.

Oracle arithmétique : 2 × 100 HTVA à TVA 21 % = 200 HTVA + 42 TVA = 242 TVAC.
Sur allocation 1 000, réservation 242 → disponible 758. La validation finale
convertit la réserve en engagement, sans réduire encore le disponible.
Un transfert 100 d'A vers B donne A −100 à la soumission, B +100 seulement à
la fin du circuit. Un inventaire de 6 signifie stock final 6, pas ajout de 6.

## 4. Conduite d'une campagne

Dans le classeur, ouvrir Mode emploi, puis Recette manuelle. Filtrer domaine,
priorité et profil. Pour chaque cas, lire préconditions et données, réaliser
les étapes numérotées dans l'ordre et comparer chacun des attendus.

Statuts : **Non exécuté**, **OK**, **KO**, **Bloqué**, **NA**. Un cas non lancé
reste Non exécuté. Une infrastructure absente conduit à Bloqué, pas OK.
NA exige une justification de périmètre approuvée. Une preuve insuffisante
ne permet pas de déclarer un résultat positif.

Renseigner résultat observé, preuve, anomalie éventuelle, testeur, date et
build. Utiliser une campagne distincte pour un autre moteur, navigateur ou
correctif. Ne pas écraser le résultat d'origine lors du retest : ajouter une
exécution et relier le correctif à l'anomalie.

Preuves minimales : identifiant DA/transfert/version/réception, état avant et
après, soldes de la combinaison ou dépôt, réponse/messages et extrait de
journal utile. Expurger mots de passe, cookies, CSRF et données personnelles.

Priorités : P0 = sécurité, argent, atomicité, droits ou flux critique ;
P1 = comportement majeur, ergonomie et cas périphériques importants.
Sévérités d'anomalies : S0 = perte/corruption ou accès indu majeur ; S1 = flux
bloquant ou calcul faux ; S2 = dégradation avec contournement ; S3 = défaut
mineur de présentation. La priorité de correction dépend aussi de l'impact.

## 5. Critères d'entrée et de sortie

Entrée : version identifiée, environnement restaurable, migrations valides,
profils distincts, données connues et accès aux preuves. Une base non
maîtrisée ne convient pas aux tests de concurrence ni de maintenance.

Sortie proposée : tous les P0 de la campagne exécutés et conformes ; aucune
anomalie S0/S1 ouverte ; P1 restants explicitement acceptés ; intégration et
tests PostgreSQL applicables passés sur la cible ; flux E2E et navigateurs
retenus validés ; écarts et limites signés par le responsable de recette.
Ces critères ne signifient pas qu'une campagne manuelle a déjà été réalisée.

## 6. Commandes et résultats automatisés

```powershell
# Unités pures ajoutées : normalisation, formats et réception
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units receiving.test_progress_unit --settings=config.test_settings --noinput

# Suite complète, base éphémère
.venv\Scripts\python.exe manage.py test --settings=config.test_settings --noinput

# Acceptation réelle des verrous et contraintes
.venv\Scripts\python.exe manage.py test --settings=config.postgresql_test_settings --noinput

# Campagne avec résultats individuels JSON pour le classeur
.venv\Scripts\python.exe tools/executer_tests_documentes.py --output docs/resultats_tests.json

# Régénération des annexes et du classeur après une évolution du code
.venv\Scripts\python.exe tools/actualiser_documentation.py

# Mesures locales isolées, à interpréter selon la documentation technique
.venv\Scripts\python.exe tools/mesurer_performances.py --output docs/mesures_performances.json --repetitions 3
```

PostgreSQL : renseigner TEST_PG_DATABASE, TEST_PG_USER, TEST_PG_PASSWORD,
TEST_PG_HOST, TEST_PG_PORT avec des valeurs de test. Les tests ignorés sous
SQLite ne sont pas une acceptation des protections PostgreSQL.

Le classeur Tests automatisés contient la commande de chaque test, son
setUp, le code exact de son scénario et ses assertions. Le fichier
`resultats_tests.json` porte la date, le moteur, le commit et les verdicts
effectivement observés. Les résultats du classeur ne sont remplis qu'à partir
de cette exécution. Les cas manuels restent Non exécuté tant qu'un testeur
n'a pas renseigné ses preuves.

Les tests JavaScript `node --test tests/theme.test.cjs` requièrent Node.js.
Un contrôle de syntaxe V8 n'est pas l'exécution de cette suite. La popup,
l'impression, les protections contre perte de saisie et le comportement
multi-onglets nécessitent une recette navigateur indépendante.

## 7. Matrice de couverture et risques

| Domaine | Familles couvertes | Limite à surveiller |
| --- | --- | --- |
| AUTH/ACC/SEC | Connexion, inactivité, droits, CSRF, isolation, maintenance | Autorisations d'infrastructure et durcissement de production non certifiés |
| BUD/IMP | Versions, allocations, réserve, import et historique | Volumes maximum, nouvelle version et écritures concurrentes |
| DA/VAL/BC | Saisie, calcul, soumission, décisions, correction, numéro, document | Navigateur, impression, erreur réseau et changement de droits en cours |
| TRF | Séquentialité source/destination, lots, retours et annulations | Filtres, signature, solde destination déjà utilisé, atomicité du groupe |
| STK/REC | Idempotence, stock non négatif, livraison partielle et complète | Concurrence PostgreSQL, tokens et panne au milieu du lot |
| HIS | Historique daté, identités supprimées et rollback | Rétention, taille des captures et restitution ancienne |
| UI | Thèmes, clavier, menus, popup et format | Navigateurs/écrans réellement supportés à fixer avant campagne |
| PERF/E2E | Reproduction, contention et chaînes métier complètes | Mesures SQLite distinctes du débit et latence de production |

La liste automatisée constitue un inventaire exhaustif des tests Python
découverts à la génération, pas une preuve d'exhaustivité de tous les défauts
possibles. Compléter la recette exploratoire avec les volumes et données
propres à l'exploitation, notamment longues descriptions, accents, gros
référentiels et historiques sur plusieurs années.

## 8. Modèle de fiche d'anomalie

Identifiant, cas lié, build, environnement, profil/droits exacts, préconditions,
données, étapes minimales de reproduction, attendu, obtenu, fréquence,
impact/sévérité, captures/réponses/journal expurgés, contournement, responsable,
correctif, résultat de retest et tests de non-régression associés.

Pour une incohérence financière : noter allocation, réservations, engagements,
transferts, disponible et version/année avant/après. Pour stock : dépôt,
article, solde, token et livraison. Pour conflit : noter les deux révisions
et l'ordre des actions des onglets/utilisateurs.

Les catalogues ci-dessous sont générés. Maintenir leurs cas manuels dans
`tools/actualiser_documentation.py` puis régénérer pour conserver le même
contenu dans le Markdown et le classeur.

Les identifiants AUT sont dérivés du nom complet du test : l'ajout d'un autre
test ne renumérote pas les anomalies liées. Pour les cas manuels, conserver
l'ordre et les identifiants déjà utilisés dans une campagne ; ajouter les
nouveaux cas en fin de domaine ou gérer explicitement leur migration.

## 9. Requêtes techniques, rejeu et concurrence

Pour les cas « POST QA », utiliser les outils réseau du navigateur sur la
base jetable : capturer une requête légitime, conserver son URL, ses champs
et le jeton CSRF de la session QA, puis ne modifier que la donnée ciblée.
Ne pas exécuter un POST avec les cookies d'un compte administrateur pour
simuler un profil restreint. Nettoyer les captures avant de les joindre.

| Action | Contrat minimal à conserver lors du test |
| --- | --- |
| Soumettre DA | POST `/achats/<id>/soumettre/`, `expected_revision`, CSRF ; Accept application/json pour popup |
| Décision DA | POST `/achats/<id>/etapes/<step_id>/decision/`, `expected_revision`, `decision=approve/correct/reject/approve_all`, `reason` selon action, CSRF |
| Supprimer ligne | POST `/achats/<id>/lignes/<line_id>/supprimer/`, `expected_revision`, CSRF |
| Décision transfert | POST `/budget/transferts/<id>/`, `revision`, `step_id`, `action`, `reason`, CSRF |
| Action groupée | POST route groupe, snapshot signé original et action autorisée ; altérer un seul champ dans le cas de falsification |
| Mouvement/réception | Conserver token et données du premier envoi ; rejouer identique, puis avec une quantité différente dans un cas distinct |

Pour la concurrence, les commandes PostgreSQL du catalogue automatisé sont
préférables à deux clics approximativement simultanés : elles orchestrent les
transactions et vérifient les invariants. Une recette à deux navigateurs
complète ce contrôle, sans le remplacer. Ne pas donner un faux verdict OK si
le runner affiche skipped ou si la connexion PostgreSQL n'est pas disponible.




<!-- ANNEXES AUTO : tools/actualiser_documentation.py -->

## Catalogue des cas manuels et flux complets

179 cas documentés. Leur état initial est **Non exécuté** ; la présence d'un scénario n'est pas une preuve de réussite.


### Domaine AUTH — 10 cas


#### AUTH-001 — Connexion valide

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Compte actif QA créé.

Données : Identifiant et mot de passe QA.

Procédure :

1. Ouvrir /connexion/.
2. Saisir le compte QA.
3. Valider.

Résultats attendus :

- Accès authentifié.
- Aucun accès admin implicite.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-002 — Mot de passe incorrect

Priorité : P0. Acteur : ANONYME. Préconditions : Compte QA actif.

Données : Mot de passe faux.

Procédure :

1. Ouvrir la connexion.
2. Saisir le compte et un mot de passe faux.
3. Valider.

Résultats attendus :

- Message d'identification invalide.
- Aucune session authentifiée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-003 — Compte inconnu

Priorité : P0. Acteur : ANONYME. Préconditions : Aucun compte QA-inconnu.

Données : Identifiant QA-inconnu.

Procédure :

1. Essayer la connexion.
2. Ouvrir ensuite une DA connue.

Résultats attendus :

- Connexion refusée.
- DA non exposée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-004 — Compte désactivé

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Compte QA inactif.

Données : Bon mot de passe.

Procédure :

1. Essayer de se connecter.
2. Observer le message.

Résultats attendus :

- Message de compte désactivé si mot de passe correct.
- Pas de connexion.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-005 — Réactivation

Priorité : P0. Acteur : ADMIN. Préconditions : Compte QA désactivé.

Données : Même mot de passe.

Procédure :

1. Réactiver le compte dans l'administration.
2. Se connecter avec ce compte.

Résultats attendus :

- Connexion possible sans recréation des données.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-006 — Expiration par inactivité

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Session réglée à 1 minute sur base QA.

Données : Attente 70 secondes.

Procédure :

1. Ouvrir une DA.
2. Ne plus agir pendant 70 s.
3. Essayer une sauvegarde.

Résultats attendus :

- Retour connexion/expiration.
- Aucune mutation métier après expiration.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-007 — Le polling ne prolonge pas la session

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Délai QA de 1 minute.

Données : Onglet laissé ouvert.

Procédure :

1. Laisser les contrôles automatiques fonctionner.
2. Attendre 70 s.
3. Observer la redirection.

Résultats attendus :

- La session expire malgré les contrôles de statut.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-008 — Activité prolongeant le délai

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Délai QA de 1 minute.

Données : Actions à 40 puis 80 secondes.

Procédure :

1. Ouvrir une page protégée après 40 s.
2. Recommencer 40 s plus tard.

Résultats attendus :

- Session encore active grâce aux actions utilisateur.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-009 — Politique de session réservée

Priorité : P0. Acteur : LECTEUR. Préconditions : Compte sans statut superutilisateur.

Données : /configuration/session/.

Procédure :

1. Ouvrir directement l'URL.
2. Tenter aussi un POST QA.

Résultats attendus :

- Accès refusé.
- Politique inchangée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### AUTH-010 — Bornes du délai

Priorité : P0. Acteur : ADMIN. Préconditions : Formulaire de politique ouvert.

Données : 0 puis 10081 puis 1.

Procédure :

1. Soumettre chaque valeur.
2. Relire la politique.

Résultats attendus :

- 0 et 10081 refusés.
- 1 accepté et audité.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine ACC — 8 cas


#### ACC-001 — Droits via rôle ERP

Priorité : P0. Acteur : ADMIN. Préconditions : Compte sans permission individuelle.

Données : Rôle QA fournissant view_supplier.

Procédure :

1. Attribuer le rôle.
2. Reconnecter le compte.
3. Ouvrir Fournisseurs.

Résultats attendus :

- Consultation autorisée.
- Création toujours interdite sans add_supplier.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### ACC-002 — Retrait de rôle

Priorité : P0. Acteur : ADMIN. Préconditions : Utilisateur lecteur via rôle.

Données : Retrait du rôle QA.

Procédure :

1. Retirer le rôle.
2. Reconnecter le compte.
3. Accéder à l'URL fournisseur.

Résultats attendus :

- Accès retiré.
- Pas de droit résiduel après nouvelle session/instance.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### ACC-003 — Compte non staff responsable

Priorité : P0. Acteur : CDF-A. Préconditions : Compte applicatif non staff responsable CDF-A.

Données : DA sur CDF-A.

Procédure :

1. Ouvrir Mes validations.
2. Traiter sa ligne.
3. Essayer /admin/.

Résultats attendus :

- Validation métier possible.
- Administration non ouverte par l'affectation CDF.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### ACC-004 — Appartenance support sans responsabilité

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Membre QA-SP, non responsable CDF.

Données : DA sur CDF-A.

Procédure :

1. Saisir une DA avec QA-SP.
2. Tenter décision d'une DA d'autrui.

Résultats attendus :

- Support admis à la saisie.
- Aucun droit de validation acquis.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### ACC-005 — Affectation responsable CDF

Priorité : P0. Acteur : ADMIN. Préconditions : CDF-A sans responsable.

Données : Utilisateur actif CDF-A.

Procédure :

1. Ouvrir la configuration des responsables.
2. Rechercher identifiant partiel.
3. Affecter et enregistrer.

Résultats attendus :

- Utilisateur trouvé sans exigence de staff.
- Affectation persistée et accès aux nouvelles tâches.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### ACC-006 — Affectation inactive interdite

Priorité : P0. Acteur : ADMIN. Préconditions : Compte QA inactif non affecté.

Données : Utilisateur QA-inactif.

Procédure :

1. Chercher dans les choix.
2. Forger un POST d'affectation QA.

Résultats attendus :

- Compte non proposé comme nouveau responsable.
- POST invalide sans affectation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### ACC-007 — Changement de responsable en cours

Priorité : P0. Acteur : ADMIN. Préconditions : DA soumise affectée CDF-A.

Données : Remplacer par CDF-B.

Procédure :

1. Changer le responsable du CDF.
2. Rafraîchir les deux boîtes.
3. Tenter ancienne décision.

Résultats attendus :

- Nouveau responsable voit la tâche.
- Ancien responsable refusé côté serveur.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### ACC-008 — Consultation financière cloisonnée

Priorité : P0. Acteur : SUIVI. Préconditions : monitor_purchases seul.

Données : URL d'une DA d'autrui.

Procédure :

1. Consulter le suivi.
2. Accéder directement au détail financier.

Résultats attendus :

- Suivi opérationnel sans montants/fournisseur sensibles.
- Détail non autorisé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine UI — 9 cas


#### UI-001 — Menus par droits

Priorité : P1. Acteur : LECTEUR. Préconditions : Droit view_supplier uniquement.

Données : Compte sans budget/stock.

Procédure :

1. Se connecter.
2. Examiner les quatre rubriques.
3. Essayer leurs URL.

Résultats attendus :

- Achats/Fournisseurs visibles selon droits.
- Budget/stock protégés côté serveur.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### UI-002 — Bouton budget uniquement Achats

Priorité : P1. Acteur : ADMIN. Préconditions : Session active.

Données : Achats, Budget, Stocks, Configuration.

Procédure :

1. Ouvrir chaque rubrique.
2. Repérer le bouton €.

Résultats attendus :

- Bouton € présent dans Achats seulement.
- Pas de loupe globale équivalente ailleurs.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### UI-003 — Accès personnels globaux

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Session active.

Données : Bandeau supérieur.

Procédure :

1. Ouvrir Achats puis Mes validations puis Mes délégations.

Résultats attendus :

- Accès personnels dans le bandeau.
- Pas de doublons dans le menu Achats.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### UI-004 — Configuration sans anciens circuits

Priorité : P1. Acteur : ADMIN. Préconditions : Superutilisateur.

Données : /achats/configuration/.

Procédure :

1. Ouvrir Configuration.
2. Lire toutes les rubriques.

Résultats attendus :

- Rubrique Compatibilité des anciens circuits absente.
- Responsables et accès toujours présents.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### UI-005 — Thèmes et onglets

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Deux onglets même origine.

Données : Clair puis sombre.

Procédure :

1. Changer de thème.
2. Observer le deuxième onglet.
3. Ouvrir Vérifier un budget.

Résultats attendus :

- Choix synchronisé.
- Iframe lisible dans le thème choisi.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### UI-006 — Stockage navigateur indisponible

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Bloquer localStorage via outil navigateur QA.

Données : Mode privé/restreint.

Procédure :

1. Charger l'application.
2. Utiliser le bouton de thème.

Résultats attendus :

- Aucune erreur JS bloquante.
- Bascule utilisable sans persistance.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### UI-007 — Clavier et fenêtres

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA prête à soumettre avec erreur de budget.

Données : Tab, Entrée, Échap.

Procédure :

1. Accéder aux boutons au clavier.
2. Ouvrir l'erreur.
3. Fermer la fenêtre.

Résultats attendus :

- Focus visible et nom accessible.
- Fermeture possible sans perdre la DA.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### UI-008 — Actions de lignes alignées

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA brouillon de deux lignes.

Données : Fenêtre large puis mobile.

Procédure :

1. Observer Modifier/Supprimer.
2. Réduire la largeur.
3. Utiliser un bouton.

Résultats attendus :

- Boutons groupés et espacés.
- Pas d'action déclenchée sur la mauvaise ligne.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### UI-009 — Affichage numérique

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA avec TVA 21 et prix 1.2345.

Données : TVA 21,0000 en stockage.

Procédure :

1. Ouvrir la DA et le bon.

Résultats attendus :

- TVA affichée 21.
- Montants limités à deux décimales.
- Précision stockée non modifiée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine FOU — 6 cas


#### FOU-001 — Créer un fournisseur

Priorité : P1. Acteur : FOURNISSEUR. Préconditions : add_supplier.

Données : QA-FOU, Société QA, BE0123456789.

Procédure :

1. Ouvrir Achats/Fournisseurs.
2. Créer avec les trois champs.
3. Rechercher QA-FOU.

Résultats attendus :

- Une fiche créée.
- Code, nom et TVA retrouvés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### FOU-002 — TVA facultative

Priorité : P1. Acteur : FOURNISSEUR. Préconditions : add_supplier.

Données : QA-FOU-SANS-TVA.

Procédure :

1. Créer sans TVA.
2. Consulter la liste.

Résultats attendus :

- Création acceptée.
- Valeur absente lisible sans None ni erreur.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### FOU-003 — Code dupliqué

Priorité : P1. Acteur : FOURNISSEUR. Préconditions : QA-FOU existe.

Données : Même code, autre nom.

Procédure :

1. Créer un deuxième fournisseur QA-FOU.

Résultats attendus :

- Erreur de code unique.
- Une seule fiche QA-FOU et nom initial intact.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### FOU-004 — Recherche partielle

Priorité : P1. Acteur : FOURNISSEUR. Préconditions : Trois fournisseurs QA.

Données : Fragment du nom puis TVA.

Procédure :

1. Chercher successivement par code, nom et TVA.
2. Chercher une valeur absente.

Résultats attendus :

- Résultats conformes à chaque critère.
- Liste vide explicite en absence de résultat.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### FOU-005 — Modifier selon droits

Priorité : P1. Acteur : FOURNISSEUR. Préconditions : change_supplier.

Données : Nom Société QA modifiée.

Procédure :

1. Modifier QA-FOU.
2. Rechercher la nouvelle valeur.

Résultats attendus :

- Modification persistée.
- Code unique toujours protégé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### FOU-006 — Lecture sans écriture

Priorité : P1. Acteur : LECTEUR. Préconditions : view_supplier sans add/change.

Données : URL nouveau/modifier.

Procédure :

1. Consulter la liste.
2. Ouvrir création.
3. POST modification QA.

Résultats attendus :

- Liste accessible.
- Écritures refusées et fournisseur inchangé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine REF — 2 cas


#### REF-001 — BI et produit détaillé

Priorité : P1. Acteur : BUDGET. Préconditions : Droits produits nécessaires.

Données : QA-BI-A et QA-ARTICLE-A.

Procédure :

1. Créer le BI.
2. Créer l'article rattaché.
3. Sélectionner dans une DA.

Résultats attendus :

- Le BI de l'article est identifiable.
- Allocation fondée sur BI, pas sur code article.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REF-002 — Recherche BI dynamique

Priorité : P1. Acteur : BUDGET. Préconditions : Deux BI QA.

Données : Recherche partielle QA-BI.

Procédure :

1. Saisir sans soumettre.
2. Changer rapidement le texte.

Résultats attendus :

- Résultats actualisés sans page entière.
- Dernière saisie gagne sur requête lente.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine BUD — 20 cas


#### BUD-001 — Créer une version vide

Priorité : P1. Acteur : BUDGET. Préconditions : Gestion budgétaire autorisée.

Données : Année Y, QA-V1.

Procédure :

1. Créer QA-V1.
2. Enregistrer vide.
3. Réouvrir.

Résultats attendus :

- Brouillon conservé.
- Aucune publication automatique.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-002 — Nom de version déjà utilisé

Priorité : P1. Acteur : BUDGET. Préconditions : QA-V1 existe en Y.

Données : qa-v1 avec espaces périphériques.

Procédure :

1. Essayer une nouvelle version en Y.
2. Réessayer en Y+1.

Résultats attendus :

- Doublon normalisé en Y refusé.
- Année différente indépendante.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-003 — Ajouter une allocation

Priorité : P1. Acteur : BUDGET. Préconditions : QA-V1 brouillon.

Données : CDF-A/F-QA/BI-A = 1000.

Procédure :

1. Ouvrir Allocations.
2. Saisir la combinaison.
3. Enregistrer puis réouvrir.

Résultats attendus :

- Allocation 1000 persistée.
- Historique mentionne produit/CDF/financement/montant.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-004 — Doublon de combinaison

Priorité : P1. Acteur : BUDGET. Préconditions : Allocation CDF-A/F-QA/BI-A existante.

Données : Deuxième montant 500.

Procédure :

1. Ajouter la même combinaison.
2. Enregistrer.

Résultats attendus :

- Erreur explicite.
- Aucune deuxième allocation de la combinaison.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-005 — Montant négatif

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : Allocation -1.

Procédure :

1. Saisir -1.
2. Enregistrer.
3. Relire.

Résultats attendus :

- Refus de validation.
- Allocation précédente inchangée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-006 — Suppression annulable avant sauvegarde

Priorité : P1. Acteur : BUDGET. Préconditions : Deux allocations.

Données : Cocher suppression ligne 1.

Procédure :

1. Supprimer visuellement.
2. Annuler la suppression.
3. Enregistrer.

Résultats attendus :

- Ligne réaffichée.
- Valeur et choix conservés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-007 — Suppression enregistrée

Priorité : P1. Acteur : BUDGET. Préconditions : Allocation brouillon sans dépendance interdite.

Données : Supprimer ligne 1.

Procédure :

1. Cocher suppression.
2. Enregistrer.
3. Consulter l'historique.

Résultats attendus :

- Ligne retirée de la version.
- Suppression tracée sans effacement du journal.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-008 — Pagination allocations

Priorité : P1. Acteur : BUDGET. Préconditions : 30 allocations distinctes QA.

Données : Page 1 puis 2.

Procédure :

1. Ouvrir Allocations.
2. Passer page 2.
3. Modifier une ligne et sauvegarder.

Résultats attendus :

- 25 lignes maximum sur page 1.
- Page/filtre conservés.
- Autres allocations intactes.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-009 — Recherche sans perdre les saisies

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : Montant modifié non sauvegardé.

Procédure :

1. Modifier un montant.
2. Saisir un filtre.
3. Essayer page suivante.

Résultats attendus :

- Avertissement de sauvegarde.
- Saisie non remplacée silencieusement.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-010 — Publier version alimentée

Priorité : P1. Acteur : BUDGET. Préconditions : QA-V1 contient allocations.

Données : Bouton Publier.

Procédure :

1. Publier QA-V1.
2. Relire versions et disponibles.

Résultats attendus :

- QA-V1 active.
- Allocations en lecture seule par défaut.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-011 — Publication vide refusée

Priorité : P1. Acteur : BUDGET. Préconditions : QA-V0 vide.

Données : Action publier.

Procédure :

1. Essayer de publier.

Résultats attendus :

- Erreur.
- Aucune version active vide créée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-012 — Remplacement de version

Priorité : P1. Acteur : BUDGET. Préconditions : QA-V1 active et DA réservée de 242.

Données : QA-V2 allocation 2000.

Procédure :

1. Créer et publier QA-V2.
2. Consulter QA-V1 et QA-V2.

Résultats attendus :

- V1 remplacée mais conservée.
- Réservations annuelles visibles, pas effacées.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-013 — Déblocage publié par admin

Priorité : P1. Acteur : ADMIN. Préconditions : Version publiée.

Données : Allocation 1000 vers 1200.

Procédure :

1. Débloquer.
2. Modifier.
3. Enregistrer.
4. Rebloquer.

Résultats attendus :

- Publication et activité conservées.
- Nouveau montant effectif.
- Réservations inchangées.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-014 — Gestionnaire non admin ne débloque pas

Priorité : P1. Acteur : BUDGET. Préconditions : Version publiée.

Données : POST action unlock.

Procédure :

1. Tenter l'URL/action de déblocage QA.

Résultats attendus :

- Refus serveur.
- Aucun état modifié.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-015 — Version bloquée

Priorité : P1. Acteur : ADMIN. Préconditions : Version brouillon alimentée.

Données : Action lock.

Procédure :

1. Bloquer.
2. Tenter saisie allocation et import.

Résultats attendus :

- Modification/import non autorisés.
- Données intactes.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-016 — Supprimer brouillon admissible

Priorité : P1. Acteur : BUDGET. Préconditions : Version vide non publiée sans transfert.

Données : QA-V-DELETE.

Procédure :

1. Demander suppression.
2. Confirmer.
3. Relire la liste/historique.

Résultats attendus :

- Version masquée de la sélection normale.
- Trace préservée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-017 — Suppression version utilisée refusée

Priorité : P1. Acteur : BUDGET. Préconditions : Version publiée ou avec transfert.

Données : QA-V1.

Procédure :

1. Demander suppression.

Résultats attendus :

- Refus.
- Transferts, allocations et références conservés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-018 — Consultation ponctuelle par compte simple

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Session active sans view_budget_balances.

Données : CDF-A/F-QA/BI-A.

Procédure :

1. Ouvrir €.
2. Choisir version/combinaison.
3. Vérifier.

Résultats attendus :

- Disponible ponctuel affiché.
- Pas de droit ajouté au tableau global.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-019 — Choix version ponctuelle

Priorité : P1. Acteur : DEMANDEUR. Préconditions : V1 remplacée, V2 active, V3 brouillon.

Données : Même combinaison.

Procédure :

1. Consulter successivement les trois versions.

Résultats attendus :

- Solde calculé selon version choisie.
- Aucune activation par consultation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BUD-020 — Combinaison sans allocation

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Combinaison CDF-C sans allocation.

Données : CDF-C/F-QA/BI-A.

Procédure :

1. Vérifier son budget.

Résultats attendus :

- Absence d'allocation signalée.
- Aucune création implicite.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine IMP — 19 cas


#### IMP-001 — Bouton au niveau des allocations

Priorité : P1. Acteur : BUDGET. Préconditions : Version brouillon modifiable.

Données : Barre d'actions de version.

Procédure :

1. Ouvrir la version.
2. Repérer Importer via Excel à côté Exporter.
3. Cliquer.

Résultats attendus :

- Accès à l'import de la bonne version.
- Bouton absent si modification interdite.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-002 — Modèle Excel

Priorité : P1. Acteur : BUDGET. Préconditions : Deux allocations QA existantes.

Données : Lien Télécharger le modèle.

Procédure :

1. Télécharger.
2. Ouvrir avec Excel/LibreOffice.
3. Lire toutes les feuilles.

Résultats attendus :

- Allocations et colonnes requises présentes.
- Références BI/CDF/financement disponibles.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-003 — Import nominal

Priorité : P1. Acteur : BUDGET. Préconditions : QA-V1 brouillon.

Données : Deux combinaisons nouvelles, 100 et 200.

Procédure :

1. Compléter le modèle.
2. Importer.
3. Attendre résultat final.
4. Relire les allocations.

Résultats attendus :

- Deux créations.
- Total 300 pour les lignes importées.
- Aucune publication.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-004 — Réimport idempotent

Priorité : P1. Acteur : BUDGET. Préconditions : Import nominal déjà réussi.

Données : Même fichier 100/200.

Procédure :

1. Réimporter le fichier.
2. Lire compteurs et montants.

Résultats attendus :

- Montants inchangés.
- Aucune addition ni doublon.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-005 — Remplacement partiel

Priorité : P1. Acteur : BUDGET. Préconditions : Allocations A=100 B=200 C=300.

Données : Fichier A=150 seulement.

Procédure :

1. Importer.
2. Relire A B C.

Résultats attendus :

- A=150.
- B=200 et C=300 conservés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-006 — Code texte avec zéros initiaux

Priorité : P1. Acteur : BUDGET. Préconditions : BI de code 0012.

Données : Code stocké en texte Excel.

Procédure :

1. Importer 0012.
2. Relire la combinaison.

Résultats attendus :

- Le code 0012 n'est pas remplacé par 12.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-007 — Extension invalide

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : Fichier .csv renommé ou réel .xls.

Procédure :

1. Choisir le fichier.
2. Envoyer.

Résultats attendus :

- Refus format/classeur.
- Aucune allocation modifiée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-008 — Fichier illisible

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : Faux fichier .xlsx contenant du texte.

Procédure :

1. Envoyer.

Résultats attendus :

- Erreur lisible de lecture.
- Pas d'erreur serveur exposée ni mutation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-009 — Limite 5 Mio

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : XLSX supérieur à 5*1024*1024 octets.

Procédure :

1. Envoyer.
2. Relire version.

Résultats attendus :

- Refus de taille.
- État identique à avant.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-010 — Limite décompressée

Priorité : P1. Acteur : BUDGET. Préconditions : Base QA jetable.

Données : Archive XLSX dépassant 50 Mio décompressés.

Procédure :

1. Envoyer un fichier de test maîtrisé.

Résultats attendus :

- Rejet avant import.
- Pas de création partielle.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-011 — Plus de 10000 lignes

Priorité : P1. Acteur : BUDGET. Préconditions : 10001 combinaisons valides dans fichier.

Données : 10001 lignes hors en-tête.

Procédure :

1. Importer.

Résultats attendus :

- Limite explicite.
- Aucune modification.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-012 — En-tête manquant ou répété

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : Supprimer Code CDF puis dupliquer Code BI.

Procédure :

1. Importer chaque variante séparément.

Résultats attendus :

- Colonnes requises signalées.
- Version inchangée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-013 — Référence inconnue

Priorité : P1. Acteur : BUDGET. Préconditions : Une ligne valide et une inconnue.

Données : Code BI QA-INCONNU.

Procédure :

1. Importer le lot.
2. Relire ligne valide initiale.

Résultats attendus :

- Erreur avec localisation.
- Ligne valide non appliquée partiellement.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-014 — Combinaison dupliquée dans fichier

Priorité : P1. Acteur : BUDGET. Préconditions : Deux lignes identiques de dimensions.

Données : Montants 100 et 200.

Procédure :

1. Importer.

Résultats attendus :

- Refus doublon.
- Ni somme 300 ni écrasement silencieux.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-015 — Montants invalides

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : Texte abc, -1, NaN, précision excessive.

Procédure :

1. Importer un fichier par valeur.

Résultats attendus :

- Chaque valeur invalide refusée.
- Aucune écriture partielle.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-016 — Formules Excel

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : Montant =100+20 et cellule en erreur.

Procédure :

1. Importer séparément les variantes.

Résultats attendus :

- Demande de coller les valeurs.
- Aucun calcul de formule sur le serveur.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-017 — Mauvaise année/version

Priorité : P1. Acteur : BUDGET. Préconditions : Export de V1/Y.

Données : Cible V2 ou année Y+1.

Procédure :

1. Réimporter l'export sur la mauvaise cible.

Résultats attendus :

- Incohérence détectée.
- Cible inchangée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-018 — Import publié non débloqué

Priorité : P1. Acteur : BUDGET. Préconditions : Version publiée.

Données : Fichier valide.

Procédure :

1. Ouvrir l'import.
2. Envoyer directement en QA.

Résultats attendus :

- Import refusé.
- Pas de modification malgré fichier valide.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### IMP-019 — Import publié débloqué admin

Priorité : P1. Acteur : ADMIN. Préconditions : Version publiée, déblocage admin actif.

Données : Fichier A=150.

Procédure :

1. Importer.
2. Contrôler la version et historique.

Résultats attendus :

- Import accepté pour admin.
- Écritures de DA conservées.
- Version toujours publiée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine DA — 17 cas


#### DA-001 — Création et numéro annuel

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Fournisseur QA existant.

Données : Deux nouvelles DA en année Y.

Procédure :

1. Créer les deux DA.
2. Comparer références.

Résultats attendus :

- DA-Y-NNNN uniques et croissantes.
- Aucune référence UUID nouvelle.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-002 — Fournisseur et support

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Membre QA-SP seulement.

Données : Fournisseur QA, support QA-SP.

Procédure :

1. Créer DA avec QA-SP.
2. Essayer support non membre par POST QA.

Résultats attendus :

- Support membre accepté.
- Référence étrangère refusée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-003 — Ligne calcul nominal

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA brouillon.

Données : Qté 2, PU 100, TVA 21.

Procédure :

1. Ajouter la ligne BI-A/CDF-A/F-QA.
2. Relire totaux.

Résultats attendus :

- HTVA 200, TVA 42, TVAC 242.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-004 — TVA explicitement nulle

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA brouillon.

Données : Qté 1, PU 100, TVA 0.

Procédure :

1. Ajouter une ligne.
2. Relire.

Résultats attendus :

- TVA 0 acceptée.
- TVAC 100.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-005 — TVA absente

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA brouillon.

Données : Champ TVA vide.

Procédure :

1. Envoyer l'ajout.
2. Essayer soumission si ancienne ligne sans TVA.

Résultats attendus :

- Erreur obligatoire.
- Absence jamais assimilée à zéro.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-006 — Précision conservée

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA brouillon.

Données : Qté 1.2345, PU 3.3333, TVA 21.

Procédure :

1. Enregistrer.
2. Exporter/contrôler valeur calculée en test.

Résultats attendus :

- Calcul décimal exact.
- Affichage arrondi sans modifier les données.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-007 — Quantité et prix invalides

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA brouillon.

Données : Qté 0 puis négative, prix négatif.

Procédure :

1. Envoyer chaque variante.

Résultats attendus :

- Validation de champ refusée.
- Aucune ligne invalide ajoutée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-008 — Modification de ligne

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Ligne brouillon TVAC 242.

Données : Qté 3 au lieu de 2.

Procédure :

1. Modifier la ligne.
2. Enregistrer.
3. Relire totaux/historique.

Résultats attendus :

- HTVA 300 et TVAC 363.
- Révision et audit augmentés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-009 — Supprimer ligne sans page intermédiaire

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Deux lignes brouillon.

Données : Ligne 2.

Procédure :

1. Cliquer Supprimer.
2. Annuler confirmation.
3. Recommencer et confirmer.

Résultats attendus :

- Annulation conserve la ligne.
- Confirmation la retire sur retour à la DA.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-010 — Accès DA d'autrui

Priorité : P1. Acteur : DEMANDEUR-B. Préconditions : DA de DEMANDEUR-A.

Données : Identifiant connu.

Procédure :

1. Ouvrir détail.
2. Tenter modification/annulation par POST QA.

Résultats attendus :

- Accès refusé/404 selon vue.
- DA inchangée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-011 — Révision périmée

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA ouverte dans deux onglets.

Données : Même expected_revision.

Procédure :

1. Modifier dans onglet 1.
2. Envoyer l'ancienne action dans onglet 2.

Résultats attendus :

- Conflit 409.
- Pas d'écrasement silencieux.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-012 — Soumission suffisante

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Allocation 1000, aucun autre mouvement.

Données : DA TVAC 242.

Procédure :

1. Soumettre depuis la fiche.
2. Fermer/recharger si besoin.
3. Consulter disponible.

Résultats attendus :

- DA en validation.
- Réservé 242 et disponible 758.
- Aucun double débit.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-013 — Insuffisance avec popup

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Disponible 100.

Données : DA TVAC 242.

Procédure :

1. Soumettre.
2. Observer et fermer la fenêtre.

Résultats attendus :

- Erreur sur la DA sans navigation.
- 100,00/242,00 au plus 2 décimales.
- Aucune réservation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-014 — Insuffisance agrégée

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Disponible 1000.

Données : Deux lignes même combinaison TVAC 605 chacune.

Procédure :

1. Soumettre.
2. Consulter état/budget.

Résultats attendus :

- Total 1210 refusé.
- Aucune des deux lignes réservée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-015 — Combinaison absente dans lot

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Ligne 1 allouée, ligne 2 sans budget.

Données : Deux lignes sur CDF-A et CDF-C.

Procédure :

1. Soumettre.
2. Relire les deux écritures.

Résultats attendus :

- Soumission refusée intégralement.
- Pas de réservation de ligne 1.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-016 — Pas de version active

Priorité : P1. Acteur : DEMANDEUR. Préconditions : Année QA sans version active.

Données : DA valide.

Procédure :

1. Soumettre.

Résultats attendus :

- Message version active manquante.
- DA brouillon/correction et budget intact.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### DA-017 — Annuler une DA en validation

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA réservée de 242.

Données : Action annuler.

Procédure :

1. Annuler avec confirmation.
2. Consulter disponible.

Résultats attendus :

- DA annulée.
- Réservation libérée, disponible revient à 1000.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine VAL — 13 cas


#### VAL-001 — Lignes CDF parallèles

Priorité : P0. Acteur : CDF-A et CDF-B. Préconditions : DA soumise, une ligne sur chaque CDF.

Données : Deux lignes TVAC 121 chacune.

Procédure :

1. Ouvrir les deux boîtes.
2. Valider ligne B avant A.
3. Valider ensuite A.

Résultats attendus :

- Les deux tâches sont accessibles indépendamment.
- Pas de commande après B seul.
- Commande après A et B.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-002 — Même CDF deux décisions

Priorité : P0. Acteur : CDF-A. Préconditions : DA soumise de deux lignes CDF-A.

Données : Deux lignes TVAC 121.

Procédure :

1. Valider une ligne.
2. Relire DA.
3. Valider la deuxième.

Résultats attendus :

- Deux décisions distinctes.
- DA commandée seulement après les deux.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-003 — Bulles de la frise

Priorité : P0. Acteur : ADMIN. Préconditions : DA soumise avec deux lignes ouvertes.

Données : Deux étapes CDF.

Procédure :

1. Lire le parcours.
2. Valider ligne 1 dans le tableau.
3. Relire le parcours.

Résultats attendus :

- Deux bulles vertes au départ puis une.
- Aucun bouton de validation dans la frise.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-004 — Valider ligne par admin

Priorité : P0. Acteur : ADMIN. Préconditions : DA en attente sans responsable.

Données : Droit decide_any_purchaserequest.

Procédure :

1. Cliquer Valider sur la ligne.
2. Confirmer.
3. Lire audit.

Résultats attendus :

- Étape approuvée par admin.
- Intervention administrateur identifiable.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-005 — Valider tout au niveau DA

Priorité : P0. Acteur : ADMIN. Préconditions : DA soumise de trois lignes.

Données : Action globale dans barre DA.

Procédure :

1. Cliquer Valider tout le circuit.
2. Lire portée puis confirmer.

Résultats attendus :

- Toutes étapes restantes approuvées.
- Un bon unique et conversions sans double débit.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-006 — Validation globale interdite au responsable

Priorité : P0. Acteur : CDF-A. Préconditions : Compte sans droit admin dédié.

Données : DA de deux lignes.

Procédure :

1. Observer les actions.
2. Forger decision=approve_all en QA.

Résultats attendus :

- Pas de bouton global autorisé.
- Requête refusée ou erreur de choix, aucune mutation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-007 — Retour pour correction

Priorité : P0. Acteur : CDF-A. Préconditions : DA soumise de deux lignes.

Données : Motif Corriger la quantité.

Procédure :

1. Demander correction avec motif.
2. Relire DA/budget.
3. Ouvrir le brouillon de correction.

Résultats attendus :

- Toute DA en correction.
- Toutes réservations libérées.
- Anciennes décisions conservées.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-008 — Motif obligatoire

Priorité : P0. Acteur : ADMIN. Préconditions : DA en validation.

Données : Correction/rejet avec blanc.

Procédure :

1. Ouvrir action.
2. Tenter confirmer sans motif.
3. Forger POST vide QA.

Résultats attendus :

- Motif exigé navigateur et serveur.
- Aucun changement d'état.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-009 — Correction et nouvelle soumission

Priorité : P0. Acteur : DEMANDEUR. Préconditions : DA retournée en correction.

Données : Qté corrigée, TVAC 121.

Procédure :

1. Modifier.
2. Resoumettre.
3. Ouvrir frise.

Résultats attendus :

- Nouveau cycle indépendant.
- Anciennes approbations ne valident pas automatiquement la nouvelle DA.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-010 — Rejet définitif

Priorité : P0. Acteur : CDF-A. Préconditions : DA en validation.

Données : Motif Achat refusé.

Procédure :

1. Rejeter.
2. Tenter resoumission QA.

Résultats attendus :

- DA rejetée, réservations libérées.
- Resoumission refusée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-011 — Responsable désactivé en cours

Priorité : P0. Acteur : ADMIN. Préconditions : Étape pending affectée CDF-A.

Données : Désactivation de CDF-A.

Procédure :

1. Désactiver le compte.
2. Actualiser.
3. Tenter décision avec ancienne session.

Résultats attendus :

- Acteur inactif refusé.
- Étape à affecter ou droit bloqué selon état.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-012 — Délégation d'achat

Priorité : P0. Acteur : CDF-A. Préconditions : Principal responsable et délégué actif.

Données : Période incluant maintenant.

Procédure :

1. Créer délégation.
2. Se connecter délégué.
3. Valider sa tâche.

Résultats attendus :

- Autorité du principal vérifiée.
- Acteur réel et représenté conservés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### VAL-013 — Délégations invalides

Priorité : P0. Acteur : CDF-A. Préconditions : Délégation A vers B active.

Données : Auto-délégation, chevauchement, chaîne B vers C.

Procédure :

1. Créer chaque variante séparément.

Résultats attendus :

- Chaque configuration interdite refusée.
- Aucune chaîne contournant les droits.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine BC — 3 cas


#### BC-001 — Données figées du bon

Priorité : P1. Acteur : ADMIN. Préconditions : DA commandée.

Données : Modifier nom fournisseur et libellé article après commande.

Procédure :

1. Modifier référentiels.
2. Imprimer le bon.

Résultats attendus :

- Le bon reprend les données figées approuvées.
- Pas de réécriture historique.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BC-002 — Impression directe

Priorité : P1. Acteur : DEMANDEUR. Préconditions : DA commandée accessible.

Données : Bouton Imprimer.

Procédure :

1. Cliquer une fois.
2. Annuler la boîte système.

Résultats attendus :

- Fenêtre d'impression ouverte sans page intermédiaire.
- DA reste affichée après annulation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### BC-003 — Lecture du bon interdite

Priorité : P1. Acteur : DEMANDEUR-B. Préconditions : Bon d'une autre DA sans droit financier.

Données : URL /achats/id/commande/.

Procédure :

1. Ouvrir URL et tentative iframe QA.

Résultats attendus :

- Document non exposé.
- Aucune donnée du fournisseur/lignes.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine TRF — 21 cas


#### TRF-001 — Source puis destination

Priorité : P1. Acteur : CDF-A puis CDF-B. Préconditions : Budget source 1000, destination 0.

Données : Transfert 100.

Procédure :

1. Soumettre.
2. Essayer destination avant source.
3. Valider source puis destination.

Résultats attendus :

- Source disponible 900 dès soumission.
- Destination 0 puis 100 à la fin.
- Ordre imposé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-002 — Même responsable deux étapes

Priorité : P1. Acteur : CDF-A. Préconditions : CDF-A et CDF-B gérés par même compte.

Données : Transfert 100.

Procédure :

1. Approuver source.
2. Relire.
3. Approuver destination.

Résultats attendus :

- Deux décisions nécessaires.
- Pas de réutilisation automatique de la première.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-003 — Destination commune multisource

Priorité : P1. Acteur : BUDGET. Préconditions : Sources A=1000 et C=1000.

Données : A donne 100 et C donne 200 vers B.

Procédure :

1. Créer deux sources.
2. Observer total.
3. Soumettre.

Résultats attendus :

- Destination total 300.
- Deux transactions dans un groupe et circuits propres.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-004 — Suppression et ligne vide

Priorité : P1. Acteur : BUDGET. Préconditions : Formulaire multisource.

Données : Une valide, une supprimée, une vide.

Procédure :

1. Ajouter les trois.
2. Supprimer l'une.
3. Soumettre.

Résultats attendus :

- Seule la source valide contribue au total et aux écritures.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-005 — Au moins une source

Priorité : P1. Acteur : BUDGET. Préconditions : Formulaire vide ou toutes lignes supprimées.

Données : Aucune ligne active.

Procédure :

1. Soumettre.

Résultats attendus :

- Erreur de minimum.
- Aucun transfert ni groupe parasite.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-006 — Même combinaison interdite

Priorité : P1. Acteur : BUDGET. Préconditions : Version modifiable.

Données : Source et destination identiques.

Procédure :

1. Saisir les mêmes CDF/BI/financement.
2. Soumettre.

Résultats attendus :

- Erreur de combinaison.
- Aucune réservation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-007 — Supports indépendants

Priorité : P1. Acteur : BUDGET. Préconditions : Supports QA-SP1/SP2 et droit création.

Données : Source SP1, destination SP2 puis vides.

Procédure :

1. Créer transfert avec supports différents.
2. Créer un autre sans supports.

Résultats attendus :

- Supports conservés séparément.
- Absence facultative admise.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-008 — Échec global insuffisant

Priorité : P0. Acteur : BUDGET. Préconditions : Source A disponible 1000.

Données : Deux sources A de 600 et 600.

Procédure :

1. Soumettre le groupe.
2. Consulter disponible et liste.

Résultats attendus :

- Les 1200 cumulés sont refusés.
- Aucune ligne créée/réservée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-009 — Version différente

Priorité : P1. Acteur : BUDGET. Préconditions : V1 et V2 même année.

Données : Transfert de V1.

Procédure :

1. Soumettre sur V1.
2. Activer V2.
3. Comparer soldes.

Résultats attendus :

- Transfert reste dans V1.
- Pas de transfert automatique vers V2.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-010 — Valider tout le circuit

Priorité : P1. Acteur : ADMIN. Préconditions : Transaction en attente.

Données : Droit decide_any_budgettransfer.

Procédure :

1. Ouvrir transaction.
2. Valider tout le circuit.
3. Confirmer.

Résultats attendus :

- Toutes étapes restantes approuvées au nom admin.
- Destination créditée une fois.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-011 — Validation groupée et filtres

Priorité : P1. Acteur : ADMIN. Préconditions : Groupe de plusieurs lignes dont une masquée.

Données : Filtre limitant affichage.

Procédure :

1. Filtrer.
2. Lancer validation globale du groupe.
3. Lire confirmation.
4. Confirmer.

Résultats attendus :

- Toutes les lignes du groupe concernées, y compris masquées.
- États et soldes cohérents.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-012 — Instantané périmé

Priorité : P1. Acteur : ADMIN. Préconditions : Liste ouverte deux fois.

Données : Une révision changée entre-temps.

Procédure :

1. Agir dans onglet 1.
2. Valider groupe depuis onglet 2.

Résultats attendus :

- Refus de snapshot/révision.
- Aucun sous-ensemble validé accidentellement.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-013 — Snapshot falsifié

Priorité : P1. Acteur : ADMIN. Préconditions : Groupe en attente.

Données : Altérer la valeur snapshot dans outil QA.

Procédure :

1. Envoyer action groupée.

Résultats attendus :

- Signature refusée.
- Aucun changement sur le groupe.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-014 — Refus avec motif

Priorité : P1. Acteur : CDF-A. Préconditions : Transfert en attente.

Données : Motif Budget à revoir.

Procédure :

1. Refuser avec motif.
2. Relire source et historique.

Résultats attendus :

- Réservation relâchée.
- Motif et acteur tracés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-015 — Retour global pour correction

Priorité : P1. Acteur : ADMIN. Préconditions : Groupe pas entièrement approuvé.

Données : Motif Corriger sources.

Procédure :

1. Retourner le groupe.
2. Consulter Mes validations du créateur.

Résultats attendus :

- Lignes renvoyées au créateur selon action.
- Motif visible.
- Budget libéré/inversé atomiquement.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-016 — Corriger et resoumettre

Priorité : P1. Acteur : BUDGET. Préconditions : Transfert retourné du créateur.

Données : Montant 100 vers 80.

Procédure :

1. Modifier.
2. Resoumettre.
3. Ouvrir parcours.

Résultats attendus :

- Nouveau cycle actif.
- Ancien cycle conservé.
- Réservation 80 uniquement.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-017 — Annuler approuvé

Priorité : P1. Acteur : ADMIN. Préconditions : Transfert 100 approuvé, destination disponible.

Données : Droit cancel_any_budgettransfer et motif.

Procédure :

1. Annuler.
2. Consulter les deux soldes.
3. Répéter action QA.

Résultats attendus :

- Retour des soldes une fois.
- Historique conservé.
- Pas de double inversion.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-018 — Annulation destination consommée

Priorité : P1. Acteur : ADMIN. Préconditions : Destination 100 reçus dont 90 réservés.

Données : Tentative reprise de 100.

Procédure :

1. Demander annulation avec motif.

Résultats attendus :

- Refus pour fonds indisponibles.
- Aucun débit partiel.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-019 — Retour groupe accompli

Priorité : P1. Acteur : ADMIN. Préconditions : Toutes les lignes approuvées.

Données : Action retour/refus global.

Procédure :

1. Essayer le retour global.
2. Comparer possibilité d'annulation.

Résultats attendus :

- Retour simple refusé.
- Annulation soumise à droit propre et contrôles.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-020 — Version bloquée après soumission

Priorité : P1. Acteur : ADMIN. Préconditions : Transfert en attente.

Données : Blocage version puis approbation.

Procédure :

1. Bloquer.
2. Essayer approuver.
3. Essayer refus autorisé.

Résultats attendus :

- Approbation interdite selon règle de version.
- Refus possible et réservations libérées.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### TRF-021 — Périmètre des listes

Priorité : P1. Acteur : DEMANDEUR-B. Préconditions : Transferts d'autrui non liés à B.

Données : URL liste/version/détail connue.

Procédure :

1. Ouvrir les URL.
2. Exporter.

Résultats attendus :

- Aucun élargissement par identifiant/filtre/export.
- Accès limité au périmètre.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine STK — 12 cas


#### STK-001 — Créer un dépôt

Priorité : P1. Acteur : STOCK. Préconditions : Droit add_warehouse.

Données : QA-DEP-A, Dépôt QA.

Procédure :

1. Créer.
2. Réouvrir.
3. Créer le même code.

Résultats attendus :

- Dépôt enregistré.
- Doublon refusé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-002 — Entrée de stock

Priorité : P1. Acteur : STOCK. Préconditions : Solde initial 0.

Données : Entrée 10 QA-ARTICLE-A.

Procédure :

1. Saisir dépôt/article/10/référence.
2. Valider.
3. Lire solde.

Résultats attendus :

- Stock 10.
- Un mouvement et une trace.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-003 — Sortie de stock

Priorité : P1. Acteur : STOCK. Préconditions : Stock 10.

Données : Sortie 3.

Procédure :

1. Enregistrer sortie motivée.
2. Lire solde.

Résultats attendus :

- Stock 7.
- Delta -3.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-004 — Sortie insuffisante

Priorité : P0. Acteur : STOCK. Préconditions : Stock 7.

Données : Sortie 8.

Procédure :

1. Tenter sortie.
2. Lire solde/journal.

Résultats attendus :

- Refus.
- Solde 7 et aucun mouvement métier réussi.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-005 — Transfert de stock

Priorité : P1. Acteur : STOCK. Préconditions : A=10, B=0.

Données : Transfert 4.

Procédure :

1. Choisir B distinct et référence.
2. Valider.

Résultats attendus :

- A=6, B=4.
- Un mouvement atomique et motif.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-006 — Transfert même dépôt

Priorité : P1. Acteur : STOCK. Préconditions : Stock disponible.

Données : Source A destination A.

Procédure :

1. Tenter transfert.

Résultats attendus :

- Refus.
- Aucun changement de stock.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-007 — Inventaire final

Priorité : P1. Acteur : STOCK. Préconditions : Stock 10.

Données : Quantité comptée 6 puis 0.

Procédure :

1. Enregistrer inventaire 6.
2. Puis inventaire 0.

Résultats attendus :

- Solde fixé à 6 puis 0.
- Deltas -4 puis -6, pas des sorties de 6 puis 0.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-008 — Quantités invalides

Priorité : P1. Acteur : STOCK. Préconditions : Base QA.

Données : Valeurs négatives, NaN et zéro hors inventaire.

Procédure :

1. Envoyer chaque variante via formulaire/service test.

Résultats attendus :

- Refus sans mutation.
- Zéro accepté seulement dans l'inventaire.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-009 — Rejeu idempotent

Priorité : P0. Acteur : STOCK. Préconditions : Premier mouvement token T réussi.

Données : Même token et payload.

Procédure :

1. Rejouer le POST/service QA.

Résultats attendus :

- Même opération logique.
- Pas de deuxième variation du solde.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-010 — Token avec payload différent

Priorité : P1. Acteur : STOCK. Préconditions : Token T déjà utilisé.

Données : Quantité ou dépôt différent.

Procédure :

1. Réutiliser T en modifiant la donnée.

Résultats attendus :

- Conflit explicite.
- Premier mouvement inchangé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-011 — Lecture sans gérer le stock

Priorité : P1. Acteur : LECTEUR. Préconditions : view_stockbalance seul.

Données : URL mouvement POST.

Procédure :

1. Lire les soldes.
2. Tenter une écriture QA.

Résultats attendus :

- Lecture possible.
- Écriture refusée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### STK-012 — Immutabilité d'un mouvement

Priorité : P1. Acteur : ADMIN. Préconditions : Mouvement existant.

Données : save/delete et tentative SQL dans tests dédiés.

Procédure :

1. Exécuter test immutabilité.
2. Consulter historique.

Résultats attendus :

- Édition ordinaire refusée selon couche.
- Correction par nouvelle opération distincte.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine REC — 9 cas


#### REC-001 — Réception partielle

Priorité : P1. Acteur : STOCK. Préconditions : DA commandée de 10 unités, stock 0.

Données : Livraison QA-BL-1 de 4.

Procédure :

1. Ouvrir Réceptions.
2. Choisir dépôt et référence.
3. Recevoir 4.

Résultats attendus :

- Stock +4.
- Reçu 4, reste 6, Partiellement réceptionnée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REC-002 — Compléter une réception

Priorité : P1. Acteur : STOCK. Préconditions : Reçu 4 sur 10.

Données : Livraison QA-BL-2 de 6.

Procédure :

1. Recevoir les 6 restants.
2. Relire DA.

Résultats attendus :

- Stock total 10.
- Reçu 10, reste 0, Réceptionnée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REC-003 — Sur-réception

Priorité : P1. Acteur : STOCK. Préconditions : Reste 6.

Données : Réception 7.

Procédure :

1. Tenter réception.
2. Consulter stock/réceptions.

Résultats attendus :

- Refus.
- Aucun stock ni reçu augmenté.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REC-004 — DA non commandée

Priorité : P1. Acteur : STOCK. Préconditions : DA brouillon/en validation.

Données : Livraison 1.

Procédure :

1. Ouvrir URL réception.
2. Tenter POST QA.

Résultats attendus :

- Réception interdite.
- Aucun mouvement.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REC-005 — Ligne étrangère

Priorité : P1. Acteur : STOCK. Préconditions : Deux DA commandées.

Données : Identifiant de ligne autre DA.

Procédure :

1. Forger réception QA incluant ligne étrangère.

Résultats attendus :

- Refus.
- Aucun reçu/mouvement partiel.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REC-006 — Réception vide ou sans référence

Priorité : P1. Acteur : STOCK. Préconditions : DA commandée.

Données : Toutes quantités 0 puis référence vide.

Procédure :

1. Soumettre chaque variante.

Résultats attendus :

- Au moins une quantité positive et référence exigées.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REC-007 — Rejeu de livraison

Priorité : P0. Acteur : STOCK. Préconditions : Réception token R réussie.

Données : Même R puis R avec quantité différente.

Procédure :

1. Rejouer identique.
2. Rejouer modifié.

Résultats attendus :

- Identique non doublé.
- Modifié refusé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REC-008 — Stock sans fuite financière

Priorité : P1. Acteur : STOCK. Préconditions : manage_stock sans permission achats financière.

Données : DA commandée.

Procédure :

1. Ouvrir réception et export opérationnel.

Résultats attendus :

- Produit/quantités visibles.
- Pas de fournisseur/prix/totaux non autorisés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### REC-009 — Mouvement libre non assimilé à réception

Priorité : P1. Acteur : STOCK. Préconditions : DA commandée non reçue.

Données : Entrée libre du même article.

Procédure :

1. Enregistrer entrée libre.
2. Lire progression DA.

Résultats attendus :

- Stock augmente.
- DA toujours non réceptionnée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine HIS — 5 cas


#### HIS-001 — Historique daté

Priorité : P1. Acteur : BUDGET. Préconditions : Allocation 100 puis 200 à deux dates.

Données : Date avant/puis après modification.

Procédure :

1. Consulter chaque date et avant premier événement.

Résultats attendus :

- États conformes aux dates.
- Pas de reconstruction erronée du présent dans le passé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### HIS-002 — Historique après remplacement version

Priorité : P1. Acteur : BUDGET. Préconditions : V1 puis V2 publiées.

Données : Date et version V1.

Procédure :

1. Ouvrir historique V1.
2. Exporter.

Résultats attendus :

- Version imposée dans vue dédiée.
- Événements de V2 non mélangés.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### HIS-003 — Suppression utilisateur et identité

Priorité : P1. Acteur : ADMIN. Préconditions : DA commandée approuvée par compte QA.

Données : Compte demandeur/approbateur jetable.

Procédure :

1. Supprimer via maintenance avec aperçu.
2. Relire bon et journal.

Résultats attendus :

- Identité/snapshots historiques lisibles.
- Pas de commande perdue par détachement facultatif.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### HIS-004 — Journal en lecture seule

Priorité : P1. Acteur : ADMIN. Préconditions : Événements existants.

Données : ActivityLog ciblé.

Procédure :

1. Ouvrir admin journal.
2. Tenter service de suppression QA.

Résultats attendus :

- Pas de mutation ordinaire.
- Service refuse de cibler le journal.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### HIS-005 — Échec transaction sans journal fantôme

Priorité : P1. Acteur : ADMIN. Préconditions : Opération de service forcée à échouer en test.

Données : Exception au dernier enregistrement.

Procédure :

1. Exécuter test rollback dédié.
2. Comparer budget, objets et journaux.

Résultats attendus :

- Aucun événement de réussite ni objet partiel persisté.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine SEC — 8 cas


#### SEC-001 — CSRF absent

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Session connectée, client QA enforce_csrf_checks.

Données : POST sans jeton.

Procédure :

1. Tenter création/soumission sans CSRF.

Résultats attendus :

- 403.
- Aucune mutation ni réservation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### SEC-002 — GET non mutateur de commande

Priorité : P0. Acteur : DEMANDEUR. Préconditions : DA brouillon.

Données : URL soumettre/annuler.

Procédure :

1. Appeler GET sur action de confirmation.
2. Relire DA.

Résultats attendus :

- GET ne soumet/annule pas la DA.
- Seul POST exécute la commande.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### SEC-003 — Injection HTML dans texte

Priorité : P0. Acteur : DEMANDEUR. Préconditions : DA brouillon.

Données : Description <script>alert(1)</script>.

Procédure :

1. Enregistrer.
2. Ouvrir fiche, historique et export.

Résultats attendus :

- Texte échappé.
- Aucun script exécuté.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### SEC-004 — Formule dans export

Priorité : P0. Acteur : ADMIN. Préconditions : Fournisseur/texte synthétique commençant =.

Données : Texte =1+1.

Procédure :

1. Exporter XLSX.
2. Inspecter cellule avec openpyxl.

Résultats attendus :

- Cellule texte, pas une formule calculable.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### SEC-005 — Anciennes routes configurables

Priorité : P0. Acteur : ADMIN. Préconditions : Ancien éditeur retiré.

Données : GET puis POST /achats/regles-validation/.

Procédure :

1. Ouvrir GET.
2. Envoyer POST QA.

Résultats attendus :

- GET redirige vers Configuration.
- POST 410 sans écriture.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### SEC-006 — Maintenance sans superuser

Priorité : P0. Acteur : LECTEUR. Préconditions : Droit delete_role sans superuser.

Données : Rôle jetable.

Procédure :

1. Tenter suppression système/route QA.

Résultats attendus :

- Refus malgré droit ordinaire.
- Pas de graphe supprimé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### SEC-007 — Aperçu dépendances maintenance

Priorité : P0. Acteur : ADMIN. Préconditions : Version publiée avec dépendances sur base jetable.

Données : Objet parent à supprimer.

Procédure :

1. Ouvrir suppression.
2. Lire dépendances.
3. Annuler.

Résultats attendus :

- Graphe annoncé.
- Aucune suppression avant confirmation.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### SEC-008 — Impression origine et accès

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Bon personnel.

Données : Iframe même origine puis origine externe QA.

Procédure :

1. Charger document autorisé.
2. Inspecter X-Frame-Options.
3. Tester tiers.

Résultats attendus :

- SAMEORIGIN.
- Autorisation document toujours appliquée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine PERF — 5 cas


#### PERF-001 — Reproduire mesures locales

Priorité : P1. Acteur : TECH. Préconditions : Environnement Python isolé, dépendances installées.

Données : 3 répétitions, allocations 10/100/1000.

Procédure :

1. Exécuter tools/mesurer_performances.py avec output QA.
2. Conserver JSON.

Résultats attendus :

- Statut 200 des scénarios.
- SQL/temps/octet/mémoire renseignés.
- Aucune base métier touchée.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### PERF-002 — Concurrence réservation DA

Priorité : P0. Acteur : TECH. Préconditions : PostgreSQL test dédié.

Données : Deux DA dépassant budget ensemble.

Procédure :

1. Exécuter .venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_t001_t002_concurrent_reservations_do_not_overspend --settings=config.postgresql_test_settings --noinput.

Résultats attendus :

- Une seule réservation admissible.
- Disponible non surconsommé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### PERF-003 — Concurrence double décision

Priorité : P0. Acteur : TECH. Préconditions : PostgreSQL test dédié.

Données : Deux décisions simultanées même DA.

Procédure :

1. Exécuter .venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_t005_simultaneous_manager_approval_creates_one_order --settings=config.postgresql_test_settings --noinput.

Résultats attendus :

- Une seule commande.
- Pas de double engagement.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### PERF-004 — Concurrence sorties stock

Priorité : P0. Acteur : TECH. Préconditions : PostgreSQL test dédié.

Données : Deux sorties supérieures au total ensemble.

Procédure :

1. Exécuter .venv\Scripts\python.exe manage.py test receiving.test_stock_postgresql.ConcurrentStockTests.test_concurrent_issues_cannot_overdraw_stock --settings=config.postgresql_test_settings --noinput.

Résultats attendus :

- Stock jamais négatif.
- Une opération refusée si nécessaire.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### PERF-005 — Charge et percentiles cible

Priorité : P1. Acteur : TECH. Préconditions : PostgreSQL dédié et accord de charge.

Données : 1/10/25/50 sessions, plusieurs centaines de requêtes.

Procédure :

1. Mesurer après chauffe p50/p95/p99, CPU, SQL, erreurs et attentes.

Résultats attendus :

- Rapport séparant lecture/écriture.
- Aucune incohérence métier.
- Seuils convenus, pas de SLA inventé.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


### Domaine E2E — 12 cas


#### E2E-001 — Achat nominal jusqu'à livraison complète

Priorité : P0. Acteur : DEMANDEUR puis CDF-A puis STOCK. Préconditions : Jeu QA réinitialisé : allocation 1000 et stock 0.

Données : 2 unités à 100 HTVA, TVA 21.

Procédure :

1. Créer DA fournisseur QA.
2. Ajouter ligne CDF-A/F-QA/BI-A.
3. Soumettre.
4. Vérifier disponible 758.
5. Valider CDF-A.
6. Imprimer.
7. Réceptionner 1 unité BL-1.
8. Réceptionner 1 unité BL-2.
9. Relire budget et journal.

Résultats attendus :

- Un bon unique.
- Engagé 242 et disponible 758.
- Stock 2, reçu 2, reste 0.
- Deux réceptions et traces cohérentes.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-002 — Achat multilignes traité dans l'ordre inverse

Priorité : P0. Acteur : DEMANDEUR puis CDF-B puis CDF-A. Préconditions : A=1000 et B=1000, stock 0.

Données : Ligne A TVAC 121 et B TVAC 242.

Procédure :

1. Créer les deux lignes.
2. Soumettre.
3. Valider B d'abord.
4. Vérifier absence de bon.
5. Valider A.
6. Recevoir séparément les lignes.

Résultats attendus :

- Parallélisme des lignes confirmé.
- Commande unique après les deux décisions.
- Réserves converties sans nouvelle déduction.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-003 — Correction complète d'une DA

Priorité : P0. Acteur : DEMANDEUR puis CDF-A. Préconditions : Allocation 1000.

Données : DA initiale 242 puis corrigée 121.

Procédure :

1. Créer et soumettre.
2. Retourner pour correction avec motif.
3. Vérifier disponible revenu 1000.
4. Modifier quantité.
5. Resoumettre.
6. Valider nouveau cycle.
7. Consulter anciens cycles.

Résultats attendus :

- Deux soumissions conservées.
- Engagement final 121.
- Ancienne approbation non réutilisée.
- Motif visible.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-004 — Insuffisance puis alimentation par import

Priorité : P0. Acteur : DEMANDEUR puis ADMIN puis CDF-A. Préconditions : Allocation active 100 seulement.

Données : DA 242, import total 500.

Procédure :

1. Soumettre et constater refus.
2. Préparer fichier 500.
3. Admin débloque la version publiée.
4. Importer en admin.
5. Rebloquer.
6. Resoumettre DA.
7. Valider.

Résultats attendus :

- Refus initial sans réserve.
- Allocation finale 500.
- Engagé 242 et disponible 258.
- Trace import et décision.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-005 — Rejet après une approbation partielle

Priorité : P0. Acteur : DEMANDEUR puis CDF-A et CDF-B. Préconditions : Deux allocations 1000.

Données : Lignes 121 et 242.

Procédure :

1. Soumettre deux lignes.
2. Approuver A.
3. Rejeter B avec motif.
4. Comparer budget et états.
5. Essayer resoumission.

Résultats attendus :

- Aucune commande.
- Toutes réservations libérées.
- Historique approbation conservé mais DA terminale.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-006 — Transfert puis achat sur destination

Priorité : P0. Acteur : BUDGET puis CDF-A puis CDF-B puis DEMANDEUR. Préconditions : A=1000, B=0.

Données : Transfert 300, DA B=242.

Procédure :

1. Soumettre transfert.
2. Constater A=700 B=0.
3. Valider source puis destination.
4. Constater B=300.
5. Créer/soumettre/valider DA sur B.

Résultats attendus :

- Disponible B final 58.
- A reste 700.
- Transfert et DA ont des historiques distincts.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-007 — Transfert groupé retourné corrigé

Priorité : P0. Acteur : BUDGET puis ADMIN. Préconditions : A=1000 C=1000 destination B=0.

Données : Sources 100 et 200 puis correction 80.

Procédure :

1. Soumettre deux sources.
2. Retourner tout avec motif.
3. Vérifier A=1000 C=1000 B=0.
4. Corriger la première transaction à 80 et la resoumettre.
5. Resoumettre aussi la seconde transaction retournée à 200.
6. Valider les deux circuits.
7. Consulter groupe et versions.

Résultats attendus :

- Anciens cycles conservés.
- A=920, C=800, B=280.
- Pas de double solde.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-008 — Annulation globale atomique impossible

Priorité : P0. Acteur : ADMIN. Préconditions : Sources A=C=1000 ; transfert groupé 100 et 200 approuvé vers B puis DA réservant 250 sur B.

Données : B disponible 50 avant annulation ; A=900 C=800.

Procédure :

1. Noter tous les soldes.
2. Tenter annulation globale motivée des 300.
3. Relire toutes les transactions et la réserve DA.

Résultats attendus :

- Échec entier.
- A=900, C=800, B disponible 50.
- Réserve DA 250 conservée.
- Aucune première ligne inversée avant échec de la seconde.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-009 — Remplacement responsable pendant validation

Priorité : P0. Acteur : DEMANDEUR puis ADMIN puis CDF-B. Préconditions : DA affectée CDF-A.

Données : Responsable A remplacé par B.

Procédure :

1. Soumettre.
2. Changer affectation.
3. Ouvrir deux boîtes.
4. Tenter décision de A.
5. Valider avec B.

Résultats attendus :

- Ancien acteur refusé.
- Nouveau acteur enregistré.
- Bon et budget cohérents.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-010 — Version remplacée avec DA en cours

Priorité : P0. Acteur : BUDGET puis DEMANDEUR puis CDF-A. Préconditions : V1=1000 active.

Données : DA réservée 242 puis V2=2000.

Procédure :

1. Soumettre sous V1.
2. Publier V2.
3. Consulter les deux versions.
4. Valider DA.
5. Imprimer le bon.

Résultats attendus :

- Réservations annuelles conservées.
- DA référence sa soumission V1.
- Conversion sans double débit.
- V2 disponible annuel tient compte de 242.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-011 — Réception rejouée après problème réseau

Priorité : P0. Acteur : STOCK. Préconditions : DA commandée 10 unités, stock 0.

Données : Livraison 4 token R.

Procédure :

1. Envoyer réception.
2. Simuler perte de réponse après succès serveur.
3. Rejouer même R.
4. Recharger DA.

Résultats attendus :

- Une seule réception.
- Stock 4, reste 6.
- Un nouvel envoi distinct sans même token n'est pas présenté comme garanti idempotent.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


#### E2E-012 — Expiration pendant action métier

Priorité : P0. Acteur : DEMANDEUR. Préconditions : Délai QA 1 minute, DA brouillon.

Données : DA TVAC 242 prête.

Procédure :

1. Ouvrir la DA.
2. Attendre expiration sans activité.
3. Cliquer Soumettre.
4. Se reconnecter.
5. Relire état et disponible.

Résultats attendus :

- Aucune soumission après expiration.
- Budget intact.
- Possibilité de reprendre après reconnexion.

Preuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.


## Catalogue automatisé exhaustif

306 tests réellement découverts par Django. Chaque commande sélectionne un test précis ; son setUp et son scénario sont reproduits dans le classeur. Les assertions ci-dessous sont les conditions réellement codées, et non des résultats supposés.


### AUT-BC9DD3D172 — `accounts.test_admin_deletion.SystemDeletionTests.test_all_registered_business_tables_have_superuser_delete`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:57](../accounts/test_admin_deletion.py#L57).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_all_registered_business_tables_have_superuser_delete --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(model_admin.has_delete_permission(request), model._meta.label)`
- `self.assertIn("system_delete_link", model_admin.get_list_display(request))`
- `self.assertFalse(model_admin.has_delete_permission(request))`

### AUT-F0F4D6990B — `accounts.test_admin_deletion.SystemDeletionTests.test_bulk_role_deletion_and_no_bypass_for_non_superuser`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:70](../accounts/test_admin_deletion.py#L70).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_bulk_role_deletion_and_no_bypass_for_non_superuser --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertFalse(Role.objects.exists())`
- `self.assertRaises(PermissionDenied)`

### AUT-321342FA8A — `accounts.test_admin_deletion.SystemDeletionTests.test_deleting_a_step_stops_cycle_and_releases_remaining_budget`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:86](../accounts/test_admin_deletion.py#L86).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_deleting_a_step_stops_cycle_and_releases_remaining_budget --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(self.client.get(url), "libérer ses réservations")`
- `self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 302)`
- `self.assertEqual(self.purchase.status, "CORRECTION")`
- `self.assertFalse(Submission.objects.get().active)`
- `self.assertEqual(BudgetEntry.objects.get().state, "released")`
- `self.assertFalse(PurchaseOrder.objects.exists())`

### AUT-522026C278 — `accounts.test_admin_deletion.SystemDeletionTests.test_deleting_used_role_does_not_broaden_rule_or_approval`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:100](../accounts/test_admin_deletion.py#L100).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_deleting_used_role_does_not_broaden_rule_or_approval --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(step.candidates.exists())`
- `self.assertIsNone(flow.authority(self.first, step))`
- `self.assertEqual(new_step.manager_source, "cdf")`
- `self.assertTrue(rule.named_user_reference.startswith("[référence supprimée:"))`

### AUT-A682778D8E — `accounts.test_admin_deletion.SystemDeletionTests.test_each_populated_business_table_can_be_deleted_without_orphans`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:129](../accounts/test_admin_deletion.py#L129).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_each_populated_business_table_can_be_deleted_without_orphans --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(model._base_manager.filter(pk=obj.pk).exists())`

### AUT-6C0735CAEF — `accounts.test_admin_deletion.SystemDeletionTests.test_journal_cannot_be_targeted_by_service`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:81](../accounts/test_admin_deletion.py#L81).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_journal_cannot_be_targeted_by_service --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(PermissionDenied)`

### AUT-62B9894EF7 — `accounts.test_admin_deletion.SystemDeletionTests.test_postgres_history_guards_remain_enabled_outside_deletion`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:150](../accounts/test_admin_deletion.py#L150).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_postgres_history_guards_remain_enabled_outside_deletion --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(DatabaseError)`
- `self.assertRaises(DatabaseError)`

### AUT-104347A9C3 — `accounts.test_admin_deletion.SystemDeletionTests.test_published_budget_deletion_previews_required_dependents`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:40](../accounts/test_admin_deletion.py#L40).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_published_budget_deletion_previews_required_dependents --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Supprimer")`
- `self.assertEqual(response.context["protected"], [])`
- `self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 302)`
- `self.assertFalse(EnvelopeVersion.objects.filter(pk=self.version.pk).exists())`
- `self.assertFalse(Allocation.objects.exists())`
- `self.assertFalse(PurchaseOrder.objects.exists())`
- `self.assertFalse(BudgetEntry.objects.exists())`
- `self.assertIsNone(self.envelope.active_version_id)`
- `self.assertTrue(ActivityLog.objects.filter(action="maintenance.deleted", object_type="purchasing.purchaseorder").exists())`

### AUT-FF13BDFB43 — `accounts.test_admin_deletion.SystemDeletionTests.test_role_has_visible_delete_link_and_members_survive`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_deletion.py:23](../accounts/test_admin_deletion.py#L23).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_deletion.SystemDeletionTests.test_role_has_visible_delete_link_and_members_survive --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(self.client.get(reverse("admin:accounts_role_changelist")), url)`
- `self.assertContains(self.client.get(url), "Suppression de maintenance")`
- `self.assertEqual(ActivityLog.objects.count(), before)`
- `self.assertEqual(response.status_code, 302)`
- `self.assertFalse(Role.objects.filter(pk=role.pk).exists())`
- `self.assertTrue(get_user_model().objects.filter(pk=self.other.pk).exists())`
- `self.assertFalse(self.other.roles.exists())`
- `self.assertTrue(ActivityLog.objects.filter(action="maintenance.deleted",                     object_type="accounts.role", actor_identifier=str(self.admin.pk)).exists())`

### AUT-C8D754074E — `accounts.test_admin_french.FrenchAdministrationTests.test_index_and_creation_forms_are_french`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_french.py:16](../accounts/test_admin_french.py#L16).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_french.FrenchAdministrationTests.test_index_and_creation_forms_are_french --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(admin.site.is_registered(ValidationFunction))`
- `self.assertContains(response, label)`
- `self.assertNotContains(response, english)`
- `self.assertContains(response, label)`

### AUT-E90E3964DF — `accounts.test_admin_french.FrenchAdministrationTests.test_readonly_fields_states_and_object_names_are_french`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_french.py:27](../accounts/test_admin_french.py#L27).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_french.FrenchAdministrationTests.test_readonly_fields_states_and_object_names_are_french --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "État d’envoi du courriel")`
- `self.assertContains(response, "En attente")`
- `self.assertContains(response, "Création")`
- `self.assertNotIn(" object ", str(model(pk=1)))`

### AUT-929666D613 — `accounts.test_admin_french.FrenchAdministrationTests.test_registered_business_fields_have_explicit_labels`

Type : Intégration Django / service / HTTP. Source : [accounts/test_admin_french.py:39](../accounts/test_admin_french.py#L39).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_admin_french.FrenchAdministrationTests.test_registered_business_fields_have_explicit_labels --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertNotEqual(str(field.verbose_name), field.name.replace("_", " "))`

### AUT-278BFED102 — `accounts.test_login.LoginMessageTests.test_disabled_account_with_correct_password_has_specific_message`

Type : Intégration Django / service / HTTP. Source : [accounts/test_login.py:11](../accounts/test_login.py#L11).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_login.LoginMessageTests.test_disabled_account_with_correct_password_has_specific_message --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Ce compte est désactivé. Contactez votre administrateur.")`
- `self.assertEqual(response.context["form"].errors.as_data()["__all__"][0].code, "inactive")`
- `self.assertNotIn("_auth_user_id", self.client.session)`
- `self.assertEqual(self.client.session["login_failures"], 1)`
- `self.assertIsNone(authenticate(username=self.user.username, password="CorrectPassword!2026"))`

### AUT-8E4FEF07F6 — `accounts.test_login.LoginMessageTests.test_reactivated_account_can_login`

Type : Intégration Django / service / HTTP. Source : [accounts/test_login.py:27](../accounts/test_login.py#L27).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_login.LoginMessageTests.test_reactivated_account_can_login --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))`

### AUT-083611D5AC — `accounts.test_login.LoginMessageTests.test_wrong_password_or_unknown_user_keeps_invalid_credentials_message`

Type : Intégration Django / service / HTTP. Source : [accounts/test_login.py:20](../accounts/test_login.py#L20).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_login.LoginMessageTests.test_wrong_password_or_unknown_user_keeps_invalid_credentials_message --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Identifiants de connexion incorrects.")`
- `self.assertNotContains(response, "Ce compte est désactivé.")`
- `self.assertNotIn("_auth_user_id", self.client.session)`

### AUT-EC9439DE9C — `accounts.test_role_permissions.RolePermissionTests.test_permissions_combine_with_standard_grants_and_inactive_denied`

Type : Intégration Django / service / HTTP. Source : [accounts/test_role_permissions.py:26](../accounts/test_role_permissions.py#L26).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_role_permissions.RolePermissionTests.test_permissions_combine_with_standard_grants_and_inactive_denied --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(user.has_perm(f"budgeting.{permissions[0].codename}"))`
- `self.assertTrue(user.has_perm(f"budgeting.{permission.codename}"))`

### AUT-E5248A2B33 — `accounts.test_role_permissions.RolePermissionTests.test_role_grant_and_revocation_on_protected_page`

Type : Intégration Django / service / HTTP. Source : [accounts/test_role_permissions.py:9](../accounts/test_role_permissions.py#L9).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_role_permissions.RolePermissionTests.test_role_grant_and_revocation_on_protected_page --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.get(url).status_code, 200)`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.get(url).status_code, 200)`
- `self.assertEqual(self.client.get(url).status_code, 403)`

### AUT-CE6BFBE403 — `accounts.test_sessions.IdleSessionTests.test_activity_slides_timeout_but_poll_does_not`

Type : Intégration Django / service / HTTP. Source : [accounts/test_sessions.py:29](../accounts/test_sessions.py#L29).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_sessions.IdleSessionTests.test_activity_slides_timeout_but_poll_does_not --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(response.json()["authenticated"])`
- `self.assertEqual(self.client.session["last_activity_at"], previous)`
- `self.assertGreater(self.client.session["last_activity_at"], previous)`

### AUT-ADFE666D5D — `accounts.test_sessions.IdleSessionTests.test_default_expiry_blocks_post_before_view`

Type : Intégration Django / service / HTTP. Source : [accounts/test_sessions.py:22](../accounts/test_sessions.py#L22).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_sessions.IdleSessionTests.test_default_expiry_blocks_post_before_view --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertIn(reverse("login"), response.url)`
- `self.assertNotIn("_auth_user_id", self.client.session)`

### AUT-FB9352D3D7 — `accounts.test_sessions.IdleSessionTests.test_expiry_also_protects_admin`

Type : Intégration Django / service / HTTP. Source : [accounts/test_sessions.py:69](../accounts/test_sessions.py#L69).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_sessions.IdleSessionTests.test_expiry_also_protects_admin --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertNotIn("_auth_user_id", self.client.session)`

### AUT-F16D8244A2 — `accounts.test_sessions.IdleSessionTests.test_login_initializes_activity`

Type : Intégration Django / service / HTTP. Source : [accounts/test_sessions.py:48](../accounts/test_sessions.py#L48).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_sessions.IdleSessionTests.test_login_initializes_activity --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIn("last_activity_at", self.client.session)`

### AUT-13CB717210 — `accounts.test_sessions.IdleSessionTests.test_new_policy_applies_to_existing_sessions`

Type : Intégration Django / service / HTTP. Source : [accounts/test_sessions.py:38](../accounts/test_sessions.py#L38).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_sessions.IdleSessionTests.test_new_policy_applies_to_existing_sessions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(self.client.get(reverse("session_status")).json()["authenticated"])`

### AUT-8CF2F7003D — `accounts.test_sessions.IdleSessionTests.test_old_session_without_timestamp_expires`

Type : Intégration Django / service / HTTP. Source : [accounts/test_sessions.py:43](../accounts/test_sessions.py#L43).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_sessions.IdleSessionTests.test_old_session_without_timestamp_expires --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(self.client.get(reverse("session_status")).json()["authenticated"])`

### AUT-248D593896 — `accounts.test_sessions.IdleSessionTests.test_policy_superuser_only_validated_and_audited`

Type : Intégration Django / service / HTTP. Source : [accounts/test_sessions.py:53](../accounts/test_sessions.py#L53).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_sessions.IdleSessionTests.test_policy_superuser_only_validated_and_audited --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.post(url, {"idle_timeout_minutes": 1}).status_code, 403)`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.post(url, {"idle_timeout_minutes": 30}).status_code, 302)`
- `self.assertEqual(SessionPolicy.timeout_seconds(), 1800)`
- `self.assertEqual(ConfigurationAuditEvent.objects.get().payload, {"idle_timeout_minutes": 30})`
- `self.assertEqual(response.status_code, 200)`
- `self.assertFalse(SessionPolicy.objects.exists())`

### AUT-783425964D — `accounts.tests.AuthorizationTests.test_configuration_pages_are_permission_protected`

Type : Intégration Django / service / HTTP. Source : [accounts/tests.py:82](../accounts/tests.py#L82).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.tests.AuthorizationTests.test_configuration_pages_are_permission_protected --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get("/habilitations/").status_code, 403)`
- `self.assertEqual(self.client.get("/habilitations/").status_code, 200)`
- `self.assertEqual(self.client.get("/habilitations/nouvelle/").status_code, 200)`
- `self.assertEqual(self.client.get(f"/habilitations/{version.authorization_id}/version/").status_code, 200)`

### AUT-A5C3AF623D — `accounts.tests.AuthorizationTests.test_deterministic_selection`

Type : Intégration Django / service / HTTP. Source : [accounts/tests.py:77](../accounts/tests.py#L77).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.tests.AuthorizationTests.test_deterministic_selection --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.eligible({}), first)`

### AUT-95A58458DF — `accounts.tests.AuthorizationTests.test_hab001_date_bounds_and_inactive_user`

Type : Intégration Django / service / HTTP. Source : [accounts/tests.py:44](../accounts/tests.py#L44).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.tests.AuthorizationTests.test_hab001_date_bounds_and_inactive_user --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIsNotNone(self.eligible({}))`
- `self.assertIsNone(self.eligible({}, self.now - timedelta(seconds=1)))`
- `self.assertIsNone(self.eligible({}, end))`
- `self.assertIsNone(self.eligible({}))`

### AUT-F8729ABB12 — `accounts.tests.AuthorizationTests.test_hab002_and_between_criteria_or_between_values`

Type : Intégration Django / service / HTTP. Source : [accounts/tests.py:33](../accounts/tests.py#L33).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.tests.AuthorizationTests.test_hab002_and_between_criteria_or_between_values --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.eligible({"cost_center": self.other.pk, "funding": self.funding.pk}), version)`
- `self.assertIsNone(self.eligible({"cost_center": self.other.pk}))`
- `self.assertIsNone(self.eligible({"cost_center": 999, "funding": self.funding.pk}))`

### AUT-D2F7AFE0DF — `accounts.tests.AuthorizationTests.test_hab002_does_not_combine_partial_authorizations`

Type : Intégration Django / service / HTTP. Source : [accounts/tests.py:39](../accounts/tests.py#L39).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.tests.AuthorizationTests.test_hab002_does_not_combine_partial_authorizations --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIsNone(self.eligible({"cost_center": self.cdf.pk, "funding": 999}))`

### AUT-C522F70F0E — `accounts.tests.AuthorizationTests.test_new_version_preserves_old_and_checks_revision`

Type : Intégration Django / service / HTTP. Source : [accounts/tests.py:53](../accounts/tests.py#L53).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.tests.AuthorizationTests.test_new_version_preserves_old_and_checks_revision --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(old.enabled)`
- `self.assertEqual(new.version, 2)`
- `self.assertIsNone(self.eligible({}))`
- `self.assertEqual(AuthorizationVersion.objects.count(), 2)`
- `self.assertEqual(ConfigurationAuditEvent.objects.count(), 2)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-F76723C780 — `accounts.tests.AuthorizationTests.test_permission_and_invalid_scope_leave_no_records`

Type : Intégration Django / service / HTTP. Source : [accounts/tests.py:69](../accounts/tests.py#L69).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.tests.AuthorizationTests.test_permission_and_invalid_scope_leave_no_records --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(AuthorizationVersion.objects.count(), 0)`
- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(ValidationError)`

### AUT-9481C21396 — `budgeting.test_admin_managers.CostCenterAdminManagersTests.test_change_cdf_permission_alone_cannot_change_managers`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_admin_managers.py:98](../budgeting/test_admin_managers.py#L98).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_admin_managers.CostCenterAdminManagersTests.test_change_cdf_permission_alone_cannot_change_managers --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertNotIn("managers", response.context["adminform"].form.fields)`
- `self.assertEqual(self.client.post(self.url, self.payload([self.admin.pk])).status_code, 302)`
- `self.assertEqual(list(self.cdf.managers.all()), [self.user])`
- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(list(self.cdf.managers.all()), [self.admin])`

### AUT-2EBF3B6F47 — `budgeting.test_admin_managers.CostCenterAdminManagersTests.test_choices_include_active_application_users_without_staff_status`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_admin_managers.py:30](../budgeting/test_admin_managers.py#L30).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_admin_managers.CostCenterAdminManagersTests.test_choices_include_active_application_users_without_staff_status --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIn(self.user, field.queryset)`
- `self.assertNotIn(self.inactive, field.queryset)`
- `self.assertContains(response, 'class="admin-autocomplete"')`
- `self.assertContains(response, 'data-minimum-input-length="0"')`
- `self.assertContains(response, reverse("admin:budgeting_costcenter_manager_choices"))`

### AUT-A68CCAE78D — `budgeting.test_admin_managers.CostCenterAdminManagersTests.test_create_and_update_responsables_from_cdf_form`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_admin_managers.py:71](../budgeting/test_admin_managers.py#L71).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_admin_managers.CostCenterAdminManagersTests.test_create_and_update_responsables_from_cdf_form --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(list(CostCenter.objects.get(code="NEW").managers.all()), [self.user])`
- `self.assertEqual(response.status_code, 302)`
- `self.assertSetEqual(set(self.cdf.managers.all()), {self.user, self.admin})`
- `self.assertContains(self.client.get(reverse("admin:budgeting_costcenter_changelist")), "Alex Martin")`
- `self.assertEqual(self.client.post(self.url, self.payload([])).status_code, 302)`
- `self.assertFalse(self.cdf.managers.exists())`

### AUT-29B3B61726 — `budgeting.test_admin_managers.CostCenterAdminManagersTests.test_dropdown_is_paginated_and_permission_protected`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_admin_managers.py:52](../budgeting/test_admin_managers.py#L52).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_admin_managers.CostCenterAdminManagersTests.test_dropdown_is_paginated_and_permission_protected --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(len(first["results"]), 20)`
- `self.assertTrue(first["pagination"]["more"])`
- `self.assertFalse(second["pagination"]["more"])`
- `self.assertFalse({r["id"] for r in first["results"]} & {r["id"] for r in second["results"]})`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.get(url).status_code, 200)`
- `self.assertEqual(self.client.get(url).status_code, 302)`

### AUT-59A5CE9DD6 — `budgeting.test_admin_managers.CostCenterAdminManagersTests.test_dropdown_loads_active_users_and_searches_partial_names_and_identifiers`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_admin_managers.py:39](../budgeting/test_admin_managers.py#L39).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_admin_managers.CostCenterAdminManagersTests.test_dropdown_loads_active_users_and_searches_partial_names_and_identifiers --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertIn(str(self.user.pk), ids)`
- `self.assertNotIn(str(self.inactive.pk), ids)`
- `self.assertEqual(self.client.get(url, {"term": "inconnu"}).json()["results"], [])`
- `self.assertEqual(data["results"], [{"id": str(self.user.pk), "text": "Alex Martin (responsable)"}])`

### AUT-2EDB5C5720 — `budgeting.test_admin_managers.CostCenterAdminManagersTests.test_existing_inactive_assignment_is_preserved_and_can_be_removed`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_admin_managers.py:89](../budgeting/test_admin_managers.py#L89).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_admin_managers.CostCenterAdminManagersTests.test_existing_inactive_assignment_is_preserved_and_can_be_removed --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "inactif — compte inactif")`
- `self.assertEqual(self.client.post(self.url, self.payload([self.inactive.pk])).status_code, 302)`
- `self.assertIn(self.inactive, self.cdf.managers.all())`
- `self.assertEqual(self.client.post(self.url, self.payload([])).status_code, 302)`
- `self.assertFalse(self.cdf.managers.exists())`

### AUT-B59786E22F — `budgeting.test_admin_managers.CostCenterAdminManagersTests.test_inactive_user_cannot_be_newly_assigned`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_admin_managers.py:83](../budgeting/test_admin_managers.py#L83).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_admin_managers.CostCenterAdminManagersTests.test_inactive_user_cannot_be_newly_assigned --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertIn("managers", response.context["adminform"].form.errors)`
- `self.assertFalse(self.cdf.managers.exists())`

### AUT-2975AAABF6 — `budgeting.test_admin_managers.CostCenterAdminManagersTests.test_old_dated_assignment_urls_redirect_without_writing`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_admin_managers.py:10](../budgeting/test_admin_managers.py#L10).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_admin_managers.CostCenterAdminManagersTests.test_old_dated_assignment_urls_redirect_without_writing --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(CostCenterManagerAssignment.objects.exists())`
- `self.assertRedirects(self.client.get(url), reverse("entity_managers"))`
- `self.assertEqual(self.client.post(url, {}).status_code, 410)`

### AUT-C6A76CA5D2 — `budgeting.test_history.BudgetHistoryTests.test_allocation_changes_publication_and_replacement_are_frozen`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:157](../budgeting/test_history.py#L157).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_allocation_changes_publication_and_replacement_are_frozen --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(after.state["versions"][str(self.budget.pk)]["status"], "Publiée remplacée")`
- `self.assertEqual(after.state["versions"][str(replacement.pk)]["status"], "Active")`
- `self.assertEqual(before.state["versions"][str(self.budget.pk)]["status"], "Active")`
- `self.assertRaises(ValidationError)`

### AUT-3A08E6F618 — `budgeting.test_history.BudgetHistoryTests.test_allocation_history_records_product_amount_cdf_and_funding`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:27](../budgeting/test_history.py#L27).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_allocation_history_records_product_amount_cdf_and_funding --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(added.state["change"]["kind"], "added")`
- `self.assertIn("Produit ajouté", added.reason)`
- `self.assertIn("1.234,50", added.reason)`
- `self.assertIn(str(self.product), added.reason)`
- `self.assertIn(str(self.source), added.reason)`
- `self.assertIn(self.funding.code, added.reason)`
- `self.assertEqual(removed.state["change"]["kind"], "removed")`
- `self.assertEqual(removed.state["change"]["amount"], "1234.50")`
- `self.assertContains(response, "Produit ajouté")`
- `self.assertContains(response, "Produit supprimé")`
- `self.assertNotContains(response, "TVAC")`

### AUT-52DA247FD2 — `budgeting.test_history.BudgetHistoryTests.test_cancel_approved_is_audited_and_restores_balances_once`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:91](../budgeting/test_history.py#L91).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_cancel_approved_is_audited_and_restores_balances_once --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(Decimal(self.source_row(before)["available"]), 40)`
- `self.assertEqual(self.balance(self.source), 100)`
- `self.assertEqual(self.balance(self.target), 0)`
- `self.assertEqual(after.actor, "admin")`
- `self.assertIn("Correction de saisie", after.reason)`
- `self.assertEqual(Decimal(self.source_row(after)["available"]), 100)`
- `self.assertEqual(Decimal(self.source_row(before)["available"]), 40)`
- `self.assertRaises(PermissionDenied)`

### AUT-418052853B — `budgeting.test_history.BudgetHistoryTests.test_cancel_approved_refused_if_destination_is_reserved`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:107](../budgeting/test_history.py#L107).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_cancel_approved_refused_if_destination_is_reserved --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(transfer.status, "approved")`
- `self.assertEqual(BudgetHistoryEvent.objects.count(), count)`
- `self.assertRaises(ValidationError)`

### AUT-BBD4F6BFF1 — `budgeting.test_history.BudgetHistoryTests.test_cancellation_permission_and_reason_are_required`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:120](../budgeting/test_history.py#L120).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_cancellation_permission_and_reason_are_required --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("transfer_monitor")).status_code, 200)`
- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(transfer.status, "cancelled")`
- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(ValidationError)`

### AUT-69C0809B9E — `budgeting.test_history.BudgetHistoryTests.test_generic_legacy_allocation_label_is_explained_without_rewriting_it`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:48](../budgeting/test_history.py#L48).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_generic_legacy_allocation_label_is_explained_without_rewriting_it --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIn("Produit ajouté : BI-1", after.display_reason)`
- `self.assertIn("10.000,00", after.display_reason)`
- `self.assertIn("CDF-A", after.display_reason)`
- `self.assertIn("F-1", after.display_reason)`
- `self.assertEqual(after.reason, "Allocation TVAC · 42")`

### AUT-176EB598D8 — `budgeting.test_history.BudgetHistoryTests.test_history_at_date_and_before_first_record`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:143](../budgeting/test_history.py#L143).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_history_at_date_and_before_first_record --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.context["selected"].pk, before.pk)`
- `self.assertEqual(Decimal(self.source_row(response.context["selected"])["available"]), 100)`
- `self.assertIsNone(response.context["state"])`
- `self.assertEqual(self.client.get(reverse("purchasing:budget_history")).status_code, 403)`

### AUT-DB2206F122 — `budgeting.test_history.BudgetHistoryTests.test_history_export_actions_are_attached_to_their_sections`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:16](../budgeting/test_history.py#L16).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_history_export_actions_are_attached_to_their_sections --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIn('section=state', state_zone)`
- `self.assertNotIn('section=timeline', state_zone)`
- `self.assertIn('section=timeline', timeline_zone)`
- `self.assertNotIn('section=state', timeline_zone)`

### AUT-9C4F9852D3 — `budgeting.test_history.BudgetHistoryTests.test_history_rolls_back_with_budget_transaction`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:172](../budgeting/test_history.py#L172).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_history_rolls_back_with_budget_transaction --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(BudgetHistoryEvent.objects.count(), count)`
- `self.assertRaises(RuntimeError)`

### AUT-3D87D52191 — `budgeting.test_history.BudgetHistoryTests.test_monitor_filters_and_permissions`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:136](../budgeting/test_history.py#L136).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_monitor_filters_and_permissions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("transfer_monitor")).status_code, 200)`
- `self.assertContains(self.client.get(reverse("transfer_monitor")), f'aria-label="Voir le workflow de la transaction {self.transfer.pk}"')`
- `self.assertNotContains(self.client.get(reverse("transfer_monitor"), {"status": "approved"}), f'aria-label="Voir le workflow de la transaction {self.transfer.pk}"')`

### AUT-D8D8DDB5F0 — `budgeting.test_history.BudgetHistoryTests.test_version_history_is_fixed_and_only_date_remains_selectable`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_history.py:61](../budgeting/test_history.py#L61).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_history.BudgetHistoryTests.test_version_history_is_fixed_and_only_date_remains_selectable --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.context["version"].pk, self.budget.pk)`
- `self.assertTrue(response.context["form"].fields["version"].widget.is_hidden)`
- `self.assertContains(response, 'name="at"')`
- `self.assertContains(response, reverse("purchasing:budget_version", args=[self.budget.pk]))`
- `self.assertTrue(all(str(self.budget.pk) in event.state["versions"] for event in response.context["timeline"]))`
- `self.assertEqual(invalid.context["version"].pk, self.budget.pk)`
- `self.assertIn("at", invalid.context["form"].errors)`
- `self.assertFalse(self.client.get(reverse("purchasing:budget_history")).context["form"].fields["version"].widget.is_hidden)`
- `self.assertEqual(self.client.get(url).status_code, 403)`

### AUT-8A102C2ABA — `budgeting.test_permissions.BudgetPermissionTests.test_budget_balance_reading_does_not_require_purchase_financial_access`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_permissions.py:183](../budgeting/test_permissions.py#L183).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_permissions.BudgetPermissionTests.test_budget_balance_reading_does_not_require_purchase_financial_access --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("purchasing:budgets")).status_code, 200)`
- `self.assertFalse(get_user_model().objects.get(pk=user.pk).has_perm("purchasing.view_purchase_financial"))`
- `self.assertEqual(self.client.get(reverse("purchasing:budgets")).status_code, 403)`

### AUT-8705258D27 — `budgeting.test_permissions.BudgetPermissionTests.test_budget_navigation_follows_actual_permissions_including_roles`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_permissions.py:63](../budgeting/test_permissions.py#L63).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_permissions.BudgetPermissionTests.test_budget_navigation_follows_actual_permissions_including_roles --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(home).status_code, 403)`
- `self.assertEqual(self.client.get(home).status_code, 403)`
- `self.assertContains(self.client.get(home), f'href="{home}"')`
- `self.assertEqual(self.client.get(reverse("purchasing:budget_versions")).status_code, 403)`
- `self.assertEqual(self.client.get(reverse("purchasing:budgets")).status_code, 403)`
- `self.assertEqual(self.client.get(home).status_code, 403)`
- `self.assertContains(self.client.get(home), f'href="{home}"')`

### AUT-C28D7016BB — `budgeting.test_permissions.BudgetPermissionTests.test_budget_permissions_have_one_namespace_and_french_labels`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_permissions.py:125](../budgeting/test_permissions.py#L125).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_permissions.BudgetPermissionTests.test_budget_permissions_have_one_namespace_and_french_labels --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(Permission.objects.filter(content_type__app_label="budgeting",                                              content_type__model__in=["budget", "budgetline"]).exists())`
- `self.assertFalse(row.name.startswith("Can "))`
- `self.assertEqual(app, "budgeting")`
- `self.assertTrue(row.name.startswith(("Ajouter :", "Modifier :", "Supprimer :")))`
- `self.assertFalse(Permission.objects.filter(content_type__app_label="purchasing", codename=code).exists())`

### AUT-A3733D030F — `budgeting.test_permissions.BudgetPermissionTests.test_detailed_product_grants_move_to_purchases_without_duplicate_or_data_loss`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_permissions.py:92](../budgeting/test_permissions.py#L92).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_permissions.BudgetPermissionTests.test_detailed_product_grants_move_to_purchases_without_duplicate_or_data_loss --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(Permission.objects.filter(content_type=old_ct).exists())`
- `self.assertEqual(Permission.objects.get(codename="add_budgetproduct").content_type.app_label, "budgeting")`
- `self.assertEqual(detail.budget_product_id, product.pk)`
- `self.assertEqual(self.client.get(reverse("purchasing:detailed_products")).status_code, 200)`
- `self.assertEqual(self.client.get(reverse("purchasing:detailed_products")).status_code, 403)`
- `self.assertIn(new, user.user_permissions.all())`
- `self.assertIn(new, group.permissions.all())`
- `self.assertIn(new, role.permissions.all())`

### AUT-BB25BB8641 — `budgeting.test_permissions.BudgetPermissionTests.test_permission_choices_are_in_french_for_role_and_user`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_permissions.py:172](../budgeting/test_permissions.py#L172).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_permissions.BudgetPermissionTests.test_permission_choices_are_in_french_for_role_and_user --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Budgets &#124; version budgétaire &#124; Ajouter : version budgétaire")`
- `self.assertNotContains(response, "Can add")`
- `self.assertNotContains(response, "Can change")`
- `self.assertNotContains(response, "Can delete")`

### AUT-3E59AD121E — `budgeting.test_permissions.BudgetPermissionTests.test_purchase_reader_cannot_access_budget_navigation_or_urls`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_permissions.py:52](../budgeting/test_permissions.py#L52).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_permissions.BudgetPermissionTests.test_purchase_reader_cannot_access_budget_navigation_or_urls --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertNotContains(response, f'href="{reverse("purchasing:budget_home")}"')`
- `self.assertEqual(self.client.get(reverse(f"purchasing:{name}")).status_code, 403)`

### AUT-1641EF366A — `budgeting.test_permissions.BudgetPermissionTests.test_section_menus_follow_categories_and_survive_last_permission_removal`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_permissions.py:19](../budgeting/test_permissions.py#L19).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_permissions.BudgetPermissionTests.test_section_menus_follow_categories_and_survive_last_permission_removal --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(self.client.get(urls["purchases"]), reverse("my_validations"))`
- `self.assertEqual(self.client.get(urls["configuration"]).status_code, 403)`
- `self.assertContains(response, 'id="my-validations"')`
- `self.assertContains(response, 'id="my-delegations"')`
- `self.assertNotContains(response, f'href="{url}"')`
- `self.assertContains(response, f'href="{url}"')`
- `self.assertNotContains(response, f'href="{url}"')`

### AUT-57C3111F55 — `budgeting.test_permissions.BudgetPermissionTests.test_transfer_preserves_individual_group_role_and_legacy_grants`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_permissions.py:139](../budgeting/test_permissions.py#L139).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_permissions.BudgetPermissionTests.test_transfer_preserves_individual_group_role_and_legacy_grants --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIn(replacement, user.user_permissions.all())`
- `self.assertIn(replacement, group.permissions.all())`
- `self.assertIn(replacement, role.permissions.all())`
- `self.assertFalse(Permission.objects.filter(pk=old.pk).exists())`
- `self.assertTrue(user.has_perm("budgeting.add_allocation"))`
- `self.assertTrue(user.has_perm("budgeting.view_budget_balances"))`
- `self.assertTrue(user.has_perm("purchasing.view_purchase_financial"))`
- `self.assertFalse(Permission.objects.filter(content_type__app_label="purchasing", codename="change_envelopeversion").exists())`
- `self.assertFalse(Permission.objects.filter(content_type__model="budgetline").exists())`

### AUT-4576D653FE — `budgeting.test_supports.SupportConfigurationTests.test_shared_manager_configuration_edits_support_not_funding`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_supports.py:36](../budgeting/test_supports.py#L36).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_supports.SupportConfigurationTests.test_shared_manager_configuration_edits_support_not_funding --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(list(self.support.managers.all()), [self.user])`
- `self.assertFalse(self.funding.managers.exists())`

### AUT-E8C983C92A — `budgeting.test_supports.SupportConfigurationTests.test_support_managers_are_independent_from_funding_and_membership`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_supports.py:16](../budgeting/test_supports.py#L16).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_supports.SupportConfigurationTests.test_support_managers_are_independent_from_funding_and_membership --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(list(self.support.managers.all()), [self.user])`
- `self.assertFalse(self.funding.managers.exists())`
- `self.assertFalse(self.user.supports.exists())`
- `self.assertEqual(data["results"], [{"id": str(self.user.pk), "text": "Alex Martin (membre)"}])`

### AUT-431540D03F — `budgeting.test_supports.SupportConfigurationTests.test_user_fiche_records_multiple_supports_without_manager_rights`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_supports.py:26](../budgeting/test_supports.py#L26).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_supports.SupportConfigurationTests.test_user_fiche_records_multiple_supports_without_manager_rights --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertSetEqual(set(self.user.supports.all()), {self.support, other})`
- `self.assertFalse(self.user.managed_supports.exists())`

### AUT-9A3676BC3C — `budgeting.test_transfer_batch_returns.BatchReturnTests.test_completed_batch_cannot_be_refused_but_can_be_cancelled_with_permission`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfer_batch_returns.py:27](../budgeting/test_transfer_batch_returns.py#L27).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfer_batch_returns.BatchReturnTests.test_completed_batch_cannot_be_refused_but_can_be_cancelled_with_permission --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(group["status_label"], "Accompli")`
- `self.assertFalse(group["can_return_all"])`
- `self.assertTrue(group["can_cancel_all"])`
- `self.assertContains(response, "Un transfert accompli ne peut plus être refusé")`
- `self.assertFalse(BudgetTransfer.objects.filter(batch_id=batch.key).exclude(status="approved").exists())`
- `self.assertFalse(BudgetTransfer.objects.filter(batch_id=batch.key).exclude(status="cancelled").exists())`
- `self.assertEqual(self.balance(self.source), 100)`
- `self.assertEqual(self.balance(self.target), 0)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(PermissionDenied)`

### AUT-03734D6E41 — `budgeting.test_transfer_batch_returns.BatchReturnTests.test_correction_cannot_exceed_budget_or_be_submitted_by_someone_else`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfer_batch_returns.py:160](../budgeting/test_transfer_batch_returns.py#L160).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfer_batch_returns.BatchReturnTests.test_correction_cannot_exceed_budget_or_be_submitted_by_someone_else --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("transfer_correct", args=[line.pk])).status_code, 404)`
- `self.assertContains(response, "Budget source insuffisant")`
- `self.assertEqual(line.status, "returned")`
- `self.assertEqual(line.amount, Decimal("10"))`

### AUT-E99F24A350 — `budgeting.test_transfer_batch_returns.BatchReturnTests.test_failed_reversal_rolls_back_the_entire_global_action`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfer_batch_returns.py:141](../budgeting/test_transfer_batch_returns.py#L141).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfer_batch_returns.BatchReturnTests.test_failed_reversal_rolls_back_the_entire_global_action --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(self.target), 35)`
- `self.assertRaises(ValidationError)`
- `self.assertEqual(line.status, "approved")`
- `self.assertTrue(line.steps.filter(active=True).exists())`

### AUT-7FD6050FF9 — `budgeting.test_transfer_batch_returns.BatchReturnTests.test_global_cancellation_is_permanent_and_has_no_more_actions`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfer_batch_returns.py:108](../budgeting/test_transfer_batch_returns.py#L108).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfer_batch_returns.BatchReturnTests.test_global_cancellation_is_permanent_and_has_no_more_actions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("transfer_correct", args=[lines[0].pk])).status_code, 403)`
- `self.assertEqual(group["status_label"], "Annulé")`
- `self.assertFalse(group["can_return_all"] or group["can_cancel_all"] or group["can_approve_all"])`
- `self.assertEqual(line.status, "cancelled")`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-0432BD42DC — `budgeting.test_transfer_batch_returns.BatchReturnTests.test_global_close_requires_permission_reason_and_fresh_snapshot`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfer_batch_returns.py:130](../budgeting/test_transfer_batch_returns.py#L130).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfer_batch_returns.BatchReturnTests.test_global_close_requires_permission_reason_and_fresh_snapshot --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-A81B87E5EC — `budgeting.test_transfer_batch_returns.BatchReturnTests.test_global_refusal_returns_every_line_and_notifies_requester`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfer_batch_returns.py:56](../budgeting/test_transfer_batch_returns.py#L56).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfer_batch_returns.BatchReturnTests.test_global_refusal_returns_every_line_and_notifies_requester --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "renvoyée(s) au demandeur")`
- `self.assertEqual(self.balance(self.source), 100)`
- `self.assertEqual(self.balance(self.target), 0)`
- `self.assertEqual(len(response.context["returned_transfers"]), 3)`
- `self.assertEqual(response.context["pending_validation_count"], 3)`
- `self.assertContains(response, "Corriger les montants")`
- `self.assertEqual(line.status, "returned")`
- `self.assertEqual(line.return_reason, "Corriger les montants")`
- `self.assertFalse(line.steps.filter(active=True).exists())`

### AUT-03810DAEB6 — `budgeting.test_transfer_batch_returns.BatchReturnTests.test_requester_can_correct_and_resubmit_without_losing_previous_decisions`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfer_batch_returns.py:78](../budgeting/test_transfer_batch_returns.py#L78).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfer_batch_returns.BatchReturnTests.test_requester_can_correct_and_resubmit_without_losing_previous_decisions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertRedirects(response, reverse("transfer_detail", args=[line.pk]))`
- `self.assertEqual(line.status, "pending")`
- `self.assertEqual(line.amount, Decimal("15"))`
- `self.assertEqual(line.batch_id, lines[1].batch_id)`
- `self.assertEqual(list(line.steps.filter(active=False).values_list("pk", "approved_by_id", "approved_at")), previous)`
- `self.assertEqual(line.steps.filter(active=True).count(), 2)`
- `self.assertEqual(line.status, "approved")`
- `self.assertRaises(PermissionDenied)`

### AUT-9A5AFB9F8F — `budgeting.test_transfers.TransferTests.test_approval_after_version_lock_is_refused_and_rejection_remains_possible`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:454](../budgeting/test_transfers.py#L454).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_approval_after_version_lock_is_refused_and_rejection_remains_possible --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(transfer.status, "rejected")`
- `self.assertRaises(ValidationError)`

### AUT-38DB997922 — `budgeting.test_transfers.TransferTests.test_budget_selection_isolates_transfers_by_version`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:153](../budgeting/test_transfers.py#L153).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_budget_selection_isolates_transfers_by_version --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(row["available"], balance)`
- `self.assertEqual(row["transfers"], movements)`

### AUT-39EA1D531A — `budgeting.test_transfers.TransferTests.test_budget_table_includes_destination_without_allocation`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:145](../budgeting/test_transfers.py#L145).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_budget_table_includes_destination_without_allocation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(len(response.context["rows"]), 2)`
- `self.assertEqual(sum(row["available"] for row in response.context["rows"]), 100)`

### AUT-88D82BB3B7 — `budgeting.test_transfers.TransferTests.test_cancel_and_owner_permissions`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:118](../budgeting/test_transfers.py#L118).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_cancel_and_owner_permissions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(self.source), 100)`
- `self.assertRaises(PermissionDenied)`

### AUT-4E96B694A0 — `budgeting.test_transfers.TransferTests.test_common_destination_budget_failure_rolls_back_every_source`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:330](../budgeting/test_transfers.py#L330).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_common_destination_budget_failure_rolls_back_every_source --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.context["submission_errors"], ["Budget source insuffisant."])`
- `self.assertEqual(BudgetTransfer.objects.count(), 1)`
- `self.assertEqual(self.balance(self.source), 100)`

### AUT-CBF064BE91 — `budgeting.test_transfers.TransferTests.test_common_destination_ignores_deleted_and_blank_sources`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:320](../budgeting/test_transfers.py#L320).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_common_destination_ignores_deleted_and_blank_sources --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(BudgetTransfer.objects.count(), 2)`
- `self.assertEqual(self.balance(self.source), 80)`

### AUT-9003AD449E — `budgeting.test_transfers.TransferTests.test_configured_automatic_rule_cannot_bypass_fixed_http_validation`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:186](../budgeting/test_transfers.py#L186).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_configured_automatic_rule_cannot_bypass_fixed_http_validation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(transfer.status, "pending")`
- `self.assertEqual(transfer.revision, 1)`
- `self.assertEqual(transfer.steps.count(), 2)`
- `self.assertEqual(self.balance(self.target), 0)`

### AUT-142A181D05 — `budgeting.test_transfers.TransferTests.test_direct_submission_failure_preserves_form_without_creating_a_draft`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:244](../budgeting/test_transfers.py#L244).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_direct_submission_failure_preserves_form_without_creating_a_draft --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.context["submission_errors"], ["Budget source insuffisant."])`
- `self.assertContains(response, '<div class="login-error" role="alert">')`
- `self.assertContains(response, "Budget source insuffisant.", count=1)`
- `self.assertEqual(response.context["formset"][0]["amount"].value(), "101")`
- `self.assertEqual(BudgetTransfer.objects.count(), before)`
- `self.assertEqual(BudgetHistoryEvent.objects.count(), events)`
- `self.assertEqual(self.balance(self.source), 100)`

### AUT-58253FC50A — `budgeting.test_transfers.TransferTests.test_existing_transfer_cannot_switch_version`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:448](../budgeting/test_transfers.py#L448).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_existing_transfer_cannot_switch_version --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(ValidationError)`

### AUT-F49A3E136E — `budgeting.test_transfers.TransferTests.test_fixed_steps_without_any_configuration`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:50](../budgeting/test_transfers.py#L50).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_fixed_steps_without_any_configuration --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIsNone(transfer.workflow_id)`
- `self.assertFalse(WorkflowVersion.objects.exists())`
- `self.assertEqual(list(transfer.steps.values_list("level", "state")), [(1, "pending"), (2, "future")])`
- `self.assertTrue(transfer.steps.get(level=2).rule["destination_cdf_manager"])`
- `self.assertEqual(self.balance(self.target), 60)`
- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(PermissionDenied)`

### AUT-06D6A8859F — `budgeting.test_transfers.TransferTests.test_inbox_and_detail_authorization`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:134](../budgeting/test_transfers.py#L134).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_inbox_and_detail_authorization --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, reverse("transfer_detail", args=[self.transfer.pk]))`
- `self.assertEqual(response.context["pending_validation_count"], 1)`
- `self.assertEqual(self.client.get(reverse("transfer_detail", args=[self.transfer.pk])).status_code, 200)`
- `self.assertEqual(self.client.get(reverse("transfer_detail", args=[self.transfer.pk])).status_code, 403)`

### AUT-3527B3A2F2 — `budgeting.test_transfers.TransferTests.test_insufficient_budget_rolls_back_all_steps`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:99](../budgeting/test_transfers.py#L99).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_insufficient_budget_rolls_back_all_steps --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(other.steps.exists())`
- `self.assertEqual(other.status, "draft")`
- `self.assertRaises(ValidationError)`

### AUT-B693EDA0A9 — `budgeting.test_transfers.TransferTests.test_locked_and_deleted_versions_cannot_receive_transfers`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:227](../budgeting/test_transfers.py#L227).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_locked_and_deleted_versions_cannot_receive_transfers --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertIn("budget_version", response.context["header"].errors)`
- `self.assertRaises(ValidationError)`

### AUT-68E254CF70 — `budgeting.test_transfers.TransferTests.test_missing_manager_waits_then_follows_current_assignments`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:75](../budgeting/test_transfers.py#L75).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_missing_manager_waits_then_follows_current_assignments --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(transfer.steps.get(level=1).state, "unassigned")`
- `self.assertEqual(transfer.steps.get(level=2).state, "future")`
- `self.assertEqual(transfer.steps.get(level=1).state, "pending")`
- `self.assertContains(self.client.get(reverse("my_validations")), reverse("transfer_detail", args=[transfer.pk]))`

### AUT-8A38E04BDB — `budgeting.test_transfers.TransferTests.test_multiple_sources_feed_common_destination_with_individual_approvals`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:278](../budgeting/test_transfers.py#L278).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_multiple_sources_feed_common_destination_with_individual_approvals --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(sum(row.amount for row in rows), Decimal("60.30"))`
- `self.assertEqual([(row.source_cdf_id, row.destination_cdf_id) for row in rows],                      [(self.source.pk, self.target.pk), (other_source.pk, self.target.pk)])`
- `self.assertTrue(all(row.destination_support_id == data["destination_support"] for row in rows))`
- `self.assertEqual(self.balance(self.target), 0)`
- `self.assertEqual(self.balance(self.target), Decimal("25.10"))`
- `self.assertEqual(rows[1].status, "pending")`
- `self.assertEqual(self.balance(self.target), Decimal("60.30"))`

### AUT-AF7A546D06 — `budgeting.test_transfers.TransferTests.test_pending_transfer_prevents_purchase_overspend`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:165](../budgeting/test_transfers.py#L165).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_pending_transfer_prevents_purchase_overspend --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(BudgetEntry.objects.exists())`
- `self.assertRaises(PurchaseRequestError)`

### AUT-1B41895B71 — `budgeting.test_transfers.TransferTests.test_rejection_releases_reservation_and_requires_reason`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:108](../budgeting/test_transfers.py#L108).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_rejection_releases_reservation_and_requires_reason --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(self.source), 40)`
- `self.assertEqual(self.balance(self.source), 100)`
- `self.assertEqual(self.balance(self.target), 0)`
- `self.assertRaises(ValidationError)`

### AUT-11DDC9698A — `budgeting.test_transfers.TransferTests.test_reservation_then_balanced_posting_and_double_decision`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:87](../budgeting/test_transfers.py#L87).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_reservation_then_balanced_posting_and_double_decision --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(self.source), 40)`
- `self.assertEqual(self.balance(self.target), 0)`
- `self.assertEqual(self.balance(self.source), 40)`
- `self.assertEqual(self.balance(self.target), 60)`
- `self.assertEqual(self.balance(self.target), 60)`
- `self.assertRaises(ValidationError)`

### AUT-0A8C493047 — `budgeting.test_transfers.TransferTests.test_same_manager_requires_two_successive_decisions`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:63](../budgeting/test_transfers.py#L63).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_same_manager_requires_two_successive_decisions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(transfer.status, "pending")`
- `self.assertEqual(transfer.steps.get(level=2).state, "pending")`
- `self.assertEqual(transfer.status, "approved")`
- `self.assertFalse(transfer.steps.filter(evidence__isnull=False).exists())`

### AUT-E8CCB6988D — `budgeting.test_transfers.TransferTests.test_selected_version_determines_year_without_configuration`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:209](../budgeting/test_transfers.py#L209).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_selected_version_determines_year_without_configuration --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(TransferConfiguration.objects.exists())`
- `self.assertContains(response, 'name="budget_version"')`
- `self.assertEqual(self.client.post(reverse("transfer_list"), payload).status_code, 302)`
- `self.assertEqual(transfer.envelope_id, other.pk)`
- `self.assertEqual(transfer.budget_version_id, version.pk)`
- `self.assertEqual(transfer.status, "pending")`
- `self.assertEqual(available(version, self.source.pk, self.funding.pk, self.product.pk), 90)`
- `self.assertEqual(self.balance(self.source), 100)`

### AUT-E15F90473D — `budgeting.test_transfers.TransferTests.test_table_header_has_no_common_support_and_rejects_unknown_row_support`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:378](../budgeting/test_transfers.py#L378).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_table_header_has_no_common_support_and_rejects_unknown_row_support --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertNotIn("support", response.context["header"].fields)`
- `self.assertContains(response, 'name="lines-0-source_support"')`
- `self.assertContains(response, 'name="lines-0-destination_support"')`
- `self.assertEqual(response.status_code, 200)`
- `self.assertIn("destination_support", response.context["formset"].forms[0].errors)`
- `self.assertEqual(BudgetTransfer.objects.count(), 1)`

### AUT-B3F5CF2F7F — `budgeting.test_transfers.TransferTests.test_table_ignores_removed_and_empty_rows`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:401](../budgeting/test_transfers.py#L401).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_table_ignores_removed_and_empty_rows --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(BudgetTransfer.objects.count(), 2)`
- `self.assertEqual(self.balance(self.source), 80)`

### AUT-528AEA6204 — `budgeting.test_transfers.TransferTests.test_table_requires_at_least_one_valid_row`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:411](../budgeting/test_transfers.py#L411).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_table_requires_at_least_one_valid_row --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertTrue(response.context["formset"].non_form_errors())`
- `self.assertEqual(BudgetTransfer.objects.count(), 1)`

### AUT-FE29B232E0 — `budgeting.test_transfers.TransferTests.test_table_rolls_back_all_rows_when_combined_budget_is_insufficient`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:391](../budgeting/test_transfers.py#L391).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_table_rolls_back_all_rows_when_combined_budget_is_insufficient --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.context["submission_errors"], ["Budget source insuffisant."])`
- `self.assertEqual(BudgetTransfer.objects.count(), 1)`
- `self.assertEqual(BudgetHistoryEvent.objects.count(), events)`
- `self.assertEqual(self.balance(self.source), 100)`

### AUT-54BE5C5F9F — `budgeting.test_transfers.TransferTests.test_table_stores_distinct_supports_per_side_and_per_row`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:349](../budgeting/test_transfers.py#L349).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_table_stores_distinct_supports_per_side_and_per_row --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual([(t.source_support_id, t.destination_support_id) for t in rows],                      [(source.pk, destination.pk), (destination.pk, source.pk)])`
- `self.assertTrue(all(t.support_id is None and t.status == "pending" for t in rows))`
- `self.assertContains(response, '<th scope="row">Support</th>')`
- `self.assertContains(response, f"<td>{source}</td>", html=True)`
- `self.assertContains(response, f"<td>{destination}</td>", html=True)`
- `self.assertEqual(record["Support source"], str(source))`
- `self.assertEqual(record["Support destination"], str(destination))`

### AUT-718AF1802A — `budgeting.test_transfers.TransferTests.test_table_submits_each_row_with_its_own_validation`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:338](../budgeting/test_transfers.py#L338).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_table_submits_each_row_with_its_own_validation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(response, reverse("transfer_monitor"))`
- `self.assertEqual(rows.count(), 2)`
- `self.assertEqual(self.balance(self.source), 50)`
- `self.assertEqual(row.status, "pending")`
- `self.assertEqual(row.steps.count(), 2)`

### AUT-AF2C1A7902 — `budgeting.test_transfers.TransferTests.test_transfer_survives_budget_version_replacement`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:125](../budgeting/test_transfers.py#L125).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_transfer_survives_budget_version_replacement --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(available(new, self.source.pk, self.funding.pk, self.product.pk), 200)`
- `self.assertEqual(available(new, self.target.pk, self.funding.pk, self.product.pk), 0)`

### AUT-CC81E7F34B — `budgeting.test_transfers.TransferTests.test_transfer_without_source_or_destination_support_can_be_submitted`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:307](../budgeting/test_transfers.py#L307).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_transfer_without_source_or_destination_support_can_be_submitted --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(response, reverse("transfer_monitor"))`
- `self.assertEqual([row.amount for row in rows], [Decimal("25.10"), Decimal("35.20")])`
- `self.assertTrue(all(row.source_support_id is None and row.destination_support_id is None                         and row.status == "pending" for row in rows))`

### AUT-4B9C17C02B — `budgeting.test_transfers.TransferTests.test_version_history_enforces_owner_scope`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:437](../budgeting/test_transfers.py#L437).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_version_history_enforces_owner_scope --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual([t.pk for t in response.context["transfers"]], [self.transfer.pk])`
- `self.assertEqual(self.client.get(reverse("version_transfers", args=[self.budget.pk])).status_code, 403)`

### AUT-E25D23AD6E — `budgeting.test_transfers.TransferTests.test_version_history_isolated_from_other_versions`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:420](../budgeting/test_transfers.py#L420).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_version_history_isolated_from_other_versions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual([t.pk for t in response.context["transfers"]], [transfer.pk])`
- `self.assertTrue(response.context["events"].exists())`
- `self.assertTrue(any(str(transfer) in e.reason for e in response.context["timeline"]))`
- `self.assertFalse(any(str(transfer) in e.reason for e in response.context["timeline"]))`
- `self.assertEqual(Decimal(source["transfers"]), 0)`

### AUT-76D401A3EA — `budgeting.test_transfers.TransferTests.test_version_with_transfers_cannot_be_deleted`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:467](../budgeting/test_transfers.py#L467).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferTests.test_version_with_transfers_cannot_be_deleted --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(ValidationError)`

### AUT-E5703B9DE3 — `budgeting.test_transfers.TransferVisibilityTests.test_admin_can_approve_entire_remaining_workflow`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:542](../budgeting/test_transfers.py#L542).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_admin_can_approve_entire_remaining_workflow --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(self.client.get(reverse("transfer_timeline", args=[transfer.pk])),                         'value="approve_all"')`
- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(transfer.status, "approved")`
- `self.assertEqual(transfer.steps.filter(state="approved", approved_by=self.admin).count(), 2)`
- `self.assertEqual(ConfigurationAuditEvent.objects.filter(object_type="budget_transfer",         object_id=transfer.pk, action="transfer.approve", actor=self.admin,         payload__full_workflow=True).count(), 2)`

### AUT-2DA5D95380 — `budgeting.test_transfers.TransferVisibilityTests.test_batch_approval_is_forbidden_for_regular_manager`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:506](../budgeting/test_transfers.py#L506).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_batch_approval_is_forbidden_for_regular_manager --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.post(reverse("transfer_batch_approve", args=[group["number"]]),                      {"snapshot": group["snapshot"]}).status_code, 403)`

### AUT-C80C90C30E — `budgeting.test_transfers.TransferVisibilityTests.test_batch_approval_rejects_stale_snapshot_and_terminal_lines`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:528](../budgeting/test_transfers.py#L528).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_batch_approval_rejects_stale_snapshot_and_terminal_lines --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(lines[1].steps.filter(state="approved").exists())`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-545D8B3E92 — `budgeting.test_transfers.TransferVisibilityTests.test_batch_approval_rolls_back_all_lines_if_later_line_is_invalid`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:514](../budgeting/test_transfers.py#L514).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_batch_approval_rolls_back_all_lines_if_later_line_is_invalid --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(ValidationError)`
- `self.assertEqual(line.status, "pending")`
- `self.assertFalse(line.steps.filter(state="approved").exists())`

### AUT-DF782FF10F — `budgeting.test_transfers.TransferVisibilityTests.test_creation_page_only_contains_creation_form`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:658](../budgeting/test_transfers.py#L658).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_creation_page_only_contains_creation_form --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Créer un transfert")`
- `self.assertContains(response, 'id="transfer-lines-form"')`
- `self.assertContains(response, '<summary>Transferts</summary>')`
- `self.assertNotContains(response, "Demandes de transfert")`
- `self.assertNotContains(response, "Exporter les demandes de transfert")`

### AUT-AB24E86A92 — `budgeting.test_transfers.TransferVisibilityTests.test_filter_by_global_transfer_number`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:624](../budgeting/test_transfers.py#L624).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_filter_by_global_transfer_number --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(len(groups), 1)`
- `self.assertEqual(groups[0]["number"], number)`
- `self.assertEqual(len(groups[0]["lines"]), 3)`
- `self.assertEqual(response.context["number"], str(number))`
- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.context["page"].paginator.count, 0)`

### AUT-A9F721ADED — `budgeting.test_transfers.TransferVisibilityTests.test_full_workflow_preserves_previous_validator`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:558](../budgeting/test_transfers.py#L558).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_full_workflow_preserves_previous_validator --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(first.approved_by, self.reviewer)`
- `self.assertEqual(transfer.steps.get(level=2).approved_by, self.admin)`

### AUT-8F11988523 — `budgeting.test_transfers.TransferVisibilityTests.test_full_workflow_requires_global_permission_and_checks_revision_and_lock`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:567](../budgeting/test_transfers.py#L567).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_full_workflow_requires_global_permission_and_checks_revision_and_lock --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(transfer.steps.filter(state="approved").exists())`
- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-EF01244FCE — `budgeting.test_transfers.TransferVisibilityTests.test_global_batch_approval_validates_all_lines_and_workflows`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:488](../budgeting/test_transfers.py#L488).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_global_batch_approval_validates_all_lines_and_workflows --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(group["can_approve_all"])`
- `self.assertContains(response, "ligne(s) validée(s).")`
- `self.assertEqual(list(lines[0].steps.values_list("approved_by_id", "approved_at")), previous)`
- `self.assertContains(response, 'status-APPROVED">Accompli')`
- `self.assertEqual(line.status, "approved")`
- `self.assertEqual(line.steps.filter(state="approved").count(), 2)`

### AUT-E8FA16F067 — `budgeting.test_transfers.TransferVisibilityTests.test_global_decision_permission_works_outside_managed_cdf`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:704](../budgeting/test_transfers.py#L704).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_global_decision_permission_works_outside_managed_cdf --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(self.client.get(reverse("transfer_monitor")), f'aria-label="Voir le workflow de la transaction {transfer.pk}"')`
- `self.assertContains(self.client.get(reverse("transfer_monitor")), 'aria-label="Valider"')`
- `self.assertContains(self.client.get(reverse("transfer_monitor")), 'aria-label="Refuser"')`
- `self.assertContains(response, 'name="action" value="approve"')`
- `self.assertContains(response, 'name="action" value="reject"')`
- `self.assertEqual(response.context["actionable_step_ids"], [transfer.steps.get(level=1).pk])`
- `self.assertEqual(transfer.status, "approved")`
- `self.assertEqual(transfer.steps.filter(approved_by=actor).count(), 2)`
- `self.assertNotContains(response, 'name="action" value="approve"')`
- `self.assertEqual(response.status_code, 302)`

### AUT-24BD2A2D5F — `budgeting.test_transfers.TransferVisibilityTests.test_global_permission_does_not_assign_personal_notifications`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:676](../budgeting/test_transfers.py#L676).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_global_permission_does_not_assign_personal_notifications --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.context["transfer_tasks"], [])`
- `self.assertEqual(response.context["pending_validation_count"], 0)`
- `self.assertEqual(response.context["transfer_tasks"], [])`
- `self.assertEqual(response.context["pending_validation_count"], 0)`
- `self.assertContains(self.client.get(reverse("transfer_timeline", args=[transfer.pk])),                         'name="action" value="approve"')`
- `self.assertEqual([step.pk for step in response.context["transfer_tasks"]],                      [transfer.steps.get(level=2).pk])`
- `self.assertEqual(response.context["pending_validation_count"], 1)`

### AUT-4EB5A045CC — `budgeting.test_transfers.TransferVisibilityTests.test_global_status_handles_rejected_and_cancelled_lines`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:596](../budgeting/test_transfers.py#L596).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_global_status_handles_rejected_and_cancelled_lines --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(batch_status(["rejected"])[1], "Refusé")`
- `self.assertEqual(batch_status(["cancelled", "cancelled"])[1], "Annulé")`
- `self.assertEqual(batch_status(["approved", "rejected"])[1], "Partiellement accompli")`

### AUT-F8C709979B — `budgeting.test_transfers.TransferVisibilityTests.test_global_status_is_accomplished_only_after_all_lines_are_approved`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:578](../budgeting/test_transfers.py#L578).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_global_status_is_accomplished_only_after_all_lines_are_approved --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(list(response.context["page"])[0]["status_label"], "En cours")`
- `self.assertEqual(list(response.context["page"])[0]["status_label"], "En cours")`
- `self.assertEqual(list(response.context["page"])[0]["status_label"], "Accompli")`
- `self.assertContains(response, 'status-badge status-APPROVED">Accompli')`
- `self.assertEqual(list(response.context["page"])[0]["status_label"], "Partiellement accompli")`

### AUT-E021AD5746 — `budgeting.test_transfers.TransferVisibilityTests.test_global_validator_can_reject_unassigned_step`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:728](../budgeting/test_transfers.py#L728).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_global_validator_can_reject_unassigned_step --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.state, "unassigned")`
- `self.assertEqual(transfer.status, "rejected")`

### AUT-54EC3BBD78 — `budgeting.test_transfers.TransferVisibilityTests.test_group_totals_only_include_visible_and_filtered_lines`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:639](../budgeting/test_transfers.py#L639).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_group_totals_only_include_visible_and_filtered_lines --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(group["total"], Decimal("60"))`
- `self.assertEqual(group["line_count"], 1)`
- `self.assertEqual(group["total"], Decimal("60"))`
- `self.assertEqual(group["line_count"], 1)`

### AUT-D59BD0F960 — `budgeting.test_transfers.TransferVisibilityTests.test_multiple_lines_share_a_group_and_separate_submissions_do_not`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:602](../budgeting/test_transfers.py#L602).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_multiple_lines_share_a_group_and_separate_submissions_do_not --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.post(reverse("transfer_list"), self.batch_payload(["10", "20", "30"])).status_code, 302)`
- `self.assertEqual(len(batch_ids), 1)`
- `self.assertNotIn(self.transfer.batch_id, batch_ids)`
- `self.assertEqual(len(groups), 2)`
- `self.assertEqual(groups[0]["line_count"], 3)`
- `self.assertEqual(groups[0]["total"], Decimal("60"))`
- `self.assertEqual(len(groups[0]["lines"]), 3)`
- `self.assertContains(response, "3 lignes")`
- `self.assertEqual(groups[0]["number"], groups[1]["number"] + 1)`
- `self.assertContains(response, f'aria-label="Numéro unique du transfert global : {groups[0]["number"]}">{groups[0]["number"]}</h3>')`
- `self.assertContains(response, "Numéro de transaction")`
- `self.assertEqual(list(filtered.context["page"])[0]["number"], groups[0]["number"])`
- `self.assertContains(response, f'aria-label="Voir le workflow de la transaction {line.pk}"')`

### AUT-43AC03EB8A — `budgeting.test_transfers.TransferVisibilityTests.test_read_only_user_is_directed_to_transfer_list`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:667](../budgeting/test_transfers.py#L667).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_read_only_user_is_directed_to_transfer_list --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(self.client.get(reverse("transfer_list")), reverse("transfer_monitor"))`
- `self.assertContains(response, '<summary>Transferts</summary>')`
- `self.assertNotContains(response, "Créer un transfert")`

### AUT-8DC0FCA69D — `budgeting.test_transfers.TransferVisibilityTests.test_requester_cannot_decide_from_timeline`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:745](../budgeting/test_transfers.py#L745).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_requester_cannot_decide_from_timeline --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertNotContains(response, 'name="action" value="approve"')`
- `self.assertNotContains(response, 'name="action" value="reject"')`

### AUT-2F9BB30C1C — `budgeting.test_transfers.TransferVisibilityTests.test_reviewer_sees_only_current_validation_and_separate_timeline`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:752](../budgeting/test_transfers.py#L752).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_reviewer_sees_only_current_validation_and_separate_timeline --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(len(response.context["rows"]), 1)`
- `self.assertNotContains(response, "Responsable du CDF destination")`
- `self.assertContains(response, "Responsable du CDF destination")`
- `self.assertContains(response, 'aria-current="step"')`
- `self.assertContains(self.client.get(reverse("transfer_monitor")), f'aria-label="Voir le workflow de la transaction {transfer.pk}"')`

### AUT-10B91978BC — `budgeting.test_transfers.TransferVisibilityTests.test_staff_status_alone_does_not_allow_global_decision`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:738](../budgeting/test_transfers.py#L738).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_staff_status_alone_does_not_allow_global_decision --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(PermissionDenied)`

### AUT-92D73BF0AA — `budgeting.test_transfers.TransferVisibilityTests.test_unassigned_step_does_not_notify_global_validator`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:696](../budgeting/test_transfers.py#L696).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_unassigned_step_does_not_notify_global_validator --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.context["transfer_tasks"], [])`
- `self.assertEqual(response.context["pending_validation_count"], 0)`

### AUT-C47B28B445 — `budgeting.test_transfers.TransferVisibilityTests.test_unrelated_user_cannot_read_timeline_or_listed_transfer`

Type : Intégration Django / service / HTTP. Source : [budgeting/test_transfers.py:763](../budgeting/test_transfers.py#L763).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers.TransferVisibilityTests.test_unrelated_user_cannot_read_timeline_or_listed_transfer --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("transfer_timeline", args=[transfer.pk])).status_code, 404)`
- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.context["page"].paginator.count, 0)`

### AUT-64882F532C — `config.test_excel.ExcelExportTests.test_budget_export_contains_only_the_selected_version`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:30](../config/test_excel.py#L30).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_budget_export_contains_only_the_selected_version --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(len(rows), 2)`
- `self.assertEqual(rows[1][1], version.label)`
- `self.assertEqual(rows[1][5], 250)`

### AUT-437C778BC6 — `config.test_excel.ExcelExportTests.test_budget_product_export_follows_search`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:21](../config/test_excel.py#L21).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_budget_product_export_follows_search --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(list(workbook.active.values), [("Code", "Libellé"), ("MATCH-01", "Selected product")])`

### AUT-433A3D9B6F — `config.test_excel.ExcelExportTests.test_exports_are_valid_workbooks_and_preserve_number_types`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:50](../config/test_excel.py#L50).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_exports_are_valid_workbooks_and_preserve_number_types --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(workbook["Allocations"]["I2"].value, 100)`
- `self.assertEqual(workbook["Allocations"]["I2"].data_type, "n")`
- `self.assertIn("Version", workbook.sheetnames)`
- `self.assertGreaterEqual(workbook.active.max_row, 2)`
- `self.assertEqual(workbook.active.freeze_panes, "A2")`
- `self.assertTrue(workbook.active.auto_filter.ref)`

### AUT-98372D98E5 — `config.test_excel.ExcelExportTests.test_exports_enforce_view_permissions_and_monitor_has_no_financial_columns`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:154](../config/test_excel.py#L154).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_exports_enforce_view_permissions_and_monitor_has_no_financial_columns --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("purchasing:budget_version", args=[self.budget.pk]), {"export": "xlsx"}).status_code, 403)`
- `self.assertNotIn("Fournisseur", headers)`
- `self.assertNotIn("Montant TVAC", headers)`
- `self.assertEqual(self.client.get(reverse(name), {"export": "xlsx"}).status_code, 403, name)`

### AUT-BDC7977DAD — `config.test_excel.ExcelExportTests.test_history_exports_are_scoped_to_their_sections`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:112](../config/test_excel.py#L112).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_history_exports_are_scoped_to_their_sections --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(workbook.sheetnames, ["État budgétaire", "Contexte"])`
- `self.assertEqual(workbook["État budgétaire"]["H2"].value, 100)`
- `self.assertEqual(workbook.sheetnames, ["Chronologie", "Contexte"])`
- `self.assertGreater(workbook["Chronologie"].max_row, 1)`
- `self.assertGreaterEqual(workbook["Chronologie"].column_dimensions["A"].width, 26)`
- `self.assertEqual(workbook["Chronologie"]["A2"].number_format, "dd/mm/yyyy hh:mm:ss")`
- `self.assertEqual(workbook["Chronologie"]["A2"].data_type, "d")`

### AUT-919E99A50C — `config.test_excel.ExcelExportTests.test_history_exports_the_selected_past_state`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:98](../config/test_excel.py#L98).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_history_exports_the_selected_past_state --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(workbook["État budgétaire"]["H2"].value, 100)`
- `self.assertIn("Contexte", workbook.sheetnames)`
- `self.assertIn("Chronologie", workbook.sheetnames)`
- `self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")`
- `self.assertIn("Historique", workbook.sheetnames)`
- `self.assertEqual(workbook["Transferts"]["C2"].value, self.budget.label)`

### AUT-344F836C29 — `config.test_excel.ExcelExportTests.test_purchase_and_transfer_exports_do_not_expose_other_owners`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:129](../config/test_excel.py#L129).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_purchase_and_transfer_exports_do_not_expose_other_owners --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual([r[0] for r in rows[1:]], [own.number])`
- `self.assertEqual(workbook["Lignes"]["J2"].value, 20)`
- `self.assertIsNone(workbook["Lignes"]["K2"].value)`
- `self.assertEqual(self.client.get(reverse("purchasing:detail", args=[other.pk]), {"export": "xlsx"}).status_code, 404)`
- `self.assertEqual([r[0] for r in rows[1:]], [str(self.transfer)])`
- `self.assertEqual(self.client.get(reverse("purchasing:all_requests"), {"export": "xlsx"}).status_code, 403)`
- `self.assertEqual({r[0] for r in rows[1:]}, {own.number, other.number})`

### AUT-0553D0062E — `config.test_excel.ExcelExportTests.test_transfer_filters_export_all_matching_pages`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:83](../config/test_excel.py#L83).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_transfer_filters_export_all_matching_pages --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(len(rows), 53)`
- `self.assertNotIn(str(other), [row[0] for row in rows[1:]])`
- `self.assertTrue(all(row[1] == self.envelope.year for row in rows[1:]))`

### AUT-9A9DF75160 — `config.test_excel.ExcelExportTests.test_warehouse_text_cannot_become_a_formula`

Type : Intégration Django / service / HTTP. Source : [config/test_excel.py:65](../config/test_excel.py#L65).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test config.test_excel.ExcelExportTests.test_warehouse_text_cannot_become_a_formula --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(workbook.active["A2"].value, "=1+1")`
- `self.assertEqual(workbook.active["A2"].data_type, "s")`
- `self.assertEqual(workbook.active["B2"].value, warehouse.label)`
- `self.assertEqual(workbook.active["E2"].value, 12.3456)`
- `self.assertEqual(workbook.active["E2"].data_type, "n")`
- `self.assertEqual(self.workbook("stock_movements").active.max_row, 1)`
- `self.assertEqual(self.workbook("stock_movements").active.max_row, 202)`

### AUT-512A2CF831 — `purchasing.test_admin_decisions.AdminDecisionTests.test_actions_are_on_lines_and_da_but_not_timeline`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_admin_decisions.py:98](../purchasing/test_admin_decisions.py#L98).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_admin_decisions.AdminDecisionTests.test_actions_are_on_lines_and_da_but_not_timeline --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(sum(step.state == "approved" for step in response.context["steps"]), 0)`
- `self.assertEqual(sum(step.is_current for step in response.context["steps"]), 2)`
- `self.assertEqual(html.count('aria-current="step"'), 2)`
- `self.assertEqual(table.count('value="approve"'), 2)`
- `self.assertNotIn('value="approve_all"', table)`
- `self.assertEqual(html.count('value="approve_all"'), 1)`
- `self.assertNotIn('data-purchase-decision', timeline)`
- `self.assertEqual(result.status_code, 200)`
- `self.assertEqual(self.purchase.status, "SUBMITTED")`
- `self.assertEqual(steps.filter(state="approved").count(), 1)`
- `self.assertEqual(steps.filter(state="pending").count(), 1)`
- `self.assertEqual(sum(step.state == "approved" for step in response.context["steps"]), 1)`
- `self.assertEqual(sum(step.is_current for step in response.context["steps"]), 1)`
- `self.assertEqual(html.count('aria-current="step"'), 1)`
- `self.assertNotContains(response, 'class="purchase-validation-summary"')`
- `self.assertEqual(html.count('value="approve"'), 1)`
- `self.assertEqual(html.count('value="approve_all"'), 1)`

### AUT-EB1DE7E576 — `purchasing.test_admin_decisions.AdminDecisionTests.test_admin_can_approve_all_lines`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_admin_decisions.py:35](../purchasing/test_admin_decisions.py#L35).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_admin_decisions.AdminDecisionTests.test_admin_can_approve_all_lines --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.purchase.status, "ORDERED")`
- `self.assertEqual(steps.count(), 2)`
- `self.assertEqual(steps.filter(state="approved", approved_by=self.admin).count(), 2)`
- `self.assertEqual(BudgetEntry.objects.filter(snapshot__submission__purchase_request=self.purchase, state="committed").count(), 2)`

### AUT-9896DC4A23 — `purchasing.test_admin_decisions.AdminDecisionTests.test_admin_can_validate_unassigned_step_with_audit`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_admin_decisions.py:24](../purchasing/test_admin_decisions.py#L24).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_admin_decisions.AdminDecisionTests.test_admin_can_validate_unassigned_step_with_audit --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.approved_by, self.admin)`
- `self.assertTrue(step.evaluated_scope["admin_override"])`
- `self.assertTrue(self.purchase.audit_events.get(action="request.approve").payload["admin_override"])`
- `self.assertTrue(PurchaseOrder.objects.filter(purchase_request=self.purchase).exists())`
- `self.assertEqual(BudgetEntry.objects.get().state, "committed")`

### AUT-7611424871 — `purchasing.test_admin_decisions.AdminDecisionTests.test_admin_correction_requires_reason_and_releases_budget`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_admin_decisions.py:46](../purchasing/test_admin_decisions.py#L46).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_admin_decisions.AdminDecisionTests.test_admin_correction_requires_reason_and_releases_budget --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.purchase.status, "SUBMITTED")`
- `self.assertEqual(self.purchase.status, "CORRECTION")`
- `self.assertEqual(BudgetEntry.objects.get().state, "released")`
- `self.assertEqual(self.purchase.audit_events.get(action="request.correct").payload["reason"], "Corriger le montant")`
- `self.assertRaises(ValidationError)`

### AUT-ACBB56D77B — `purchasing.test_admin_decisions.AdminDecisionTests.test_admin_rejection_is_terminal`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_admin_decisions.py:58](../purchasing/test_admin_decisions.py#L58).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_admin_decisions.AdminDecisionTests.test_admin_rejection_is_terminal --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.purchase.status, "REJECTED")`
- `self.assertEqual(BudgetEntry.objects.get().state, "released")`
- `self.assertRaises(PurchaseRequestError)`

### AUT-6D66454C73 — `purchasing.test_admin_decisions.AdminDecisionTests.test_permission_allows_non_superuser_and_actions_on_timeline`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_admin_decisions.py:82](../purchasing/test_admin_decisions.py#L82).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_admin_decisions.AdminDecisionTests.test_permission_allows_non_superuser_and_actions_on_timeline --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(detail, 'data-purchase-decision')`
- `self.assertContains(detail, 'value="approve_all"')`
- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(step.approved_by, self.other)`
- `self.assertNotContains(self.client.get(reverse("purchasing:detail", args=[self.purchase.pk])), 'data-purchase-decision')`

### AUT-351CB9D802 — `purchasing.test_admin_decisions.AdminDecisionTests.test_regular_validator_cannot_approve_all`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_admin_decisions.py:67](../purchasing/test_admin_decisions.py#L67).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_admin_decisions.AdminDecisionTests.test_regular_validator_cannot_approve_all --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(PurchaseOrder.objects.exists())`
- `self.assertRaises(PermissionDenied)`

### AUT-F291DC9F65 — `purchasing.test_admin_decisions.AdminDecisionTests.test_stale_revision_cannot_validate`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_admin_decisions.py:73](../purchasing/test_admin_decisions.py#L73).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_admin_decisions.AdminDecisionTests.test_stale_revision_cannot_validate --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.state, "pending")`
- `self.assertRaises(PurchaseRequestConflict)`

### AUT-636E3E2681 — `purchasing.test_allocation_excel.AllocationExcelTests.test_async_errors_are_returned_to_the_import_page_without_changes`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:70](../purchasing/test_allocation_excel.py#L70).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_async_errors_are_returned_to_the_import_page_without_changes --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 400)`
- `self.assertFalse(response.json()["ok"])`
- `self.assertIn("Ligne 2", response.json()["errors"][0])`
- `self.assertFalse(version.allocations.exists())`
- `self.assertEqual(response.status_code, 400)`
- `self.assertTrue(response.json()["errors"])`

### AUT-C6F192BE21 — `purchasing.test_allocation_excel.AllocationExcelTests.test_async_import_reports_success_without_redirecting_to_large_form`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:57](../purchasing/test_allocation_excel.py#L57).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_async_import_reports_success_without_redirecting_to_large_form --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.json()["counts"], {"created": 1000, "updated": 0, "unchanged": 0})`
- `self.assertTrue(response.json()["ok"])`
- `self.assertNotIn("Location", response.headers)`
- `self.assertLess(len(response.content), 1000)`
- `self.assertEqual(version.allocations.count(), 1000)`

### AUT-CB39BB5485 — `purchasing.test_allocation_excel.AllocationExcelTests.test_current_export_can_be_imported_and_wrong_year_or_version_is_rejected`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:135](../purchasing/test_allocation_excel.py#L135).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_current_export_can_be_imported_and_wrong_year_or_version_is_rejected --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.post(url, {"file": SimpleUploadedFile("export.xlsx", exported.content)}).status_code, 302)`
- `self.assertEqual(version.allocations.get().amount, 10)`
- `self.assertContains(response, "Import impossible")`

### AUT-C3F30D3041 — `purchasing.test_allocation_excel.AllocationExcelTests.test_duplicate_combination_empty_file_invalid_headers_and_invalid_workbook`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:124](../purchasing/test_allocation_excel.py#L124).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_duplicate_combination_empty_file_invalid_headers_and_invalid_workbook --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(version.allocations.exists())`
- `self.assertContains(response, "Import impossible")`

### AUT-94D9ED5509 — `purchasing.test_allocation_excel.AllocationExcelTests.test_import_creates_updates_preserves_other_allocations_and_is_not_additive`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:83](../purchasing/test_allocation_excel.py#L83).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_import_creates_updates_preserves_other_allocations_and_is_not_additive --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(original.amount, Decimal("1234.56"))`
- `self.assertEqual(untouched.amount, 500)`
- `self.assertEqual(version.allocations.get(budget_product=new).amount, 70)`
- `self.assertEqual(version.allocations.count(), 3)`
- `self.assertIsNone(EnvelopeVersion.objects.get(pk=version.pk).published_at)`
- `self.assertEqual(ConfigurationAuditEvent.objects.filter(action="budget.allocations_import", object_id=version.pk).count(), 2)`
- `self.assertRedirects(response, reverse("purchasing:budget_version", args=[version.pk]))`

### AUT-40B91E46B9 — `purchasing.test_allocation_excel.AllocationExcelTests.test_import_rolls_back_previous_rows_when_a_save_fails`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:167](../purchasing/test_allocation_excel.py#L167).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_import_rolls_back_previous_rows_when_a_save_fails --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Erreur d’enregistrement")`
- `self.assertEqual(existing.amount, 5)`
- `self.assertEqual(version.allocations.count(), 1)`
- `self.assertFalse(ConfigurationAuditEvent.objects.filter(action="budget.allocations_import").exists())`

### AUT-EA7344E7E9 — `purchasing.test_allocation_excel.AllocationExcelTests.test_invalid_rows_abort_entire_file_with_row_numbers`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:103](../purchasing/test_allocation_excel.py#L103).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_invalid_rows_abort_entire_file_with_row_numbers --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Ligne 3")`
- `self.assertEqual(original.amount, 100)`
- `self.assertContains(response, "Ligne 2")`
- `self.assertContains(response, "Aucune modification enregistrée")`
- `self.assertEqual(original.amount, 100)`

### AUT-04D6C1002C — `purchasing.test_allocation_excel.AllocationExcelTests.test_permissions_and_published_version_rules_match_manual_editing`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:147](../purchasing/test_allocation_excel.py#L147).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_permissions_and_published_version_rules_match_manual_editing --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Import impossible")`
- `self.assertEqual(self.client.post(url, {"file": self.upload([["BI", "CDF", "F", 20]])}).status_code, 403)`
- `self.assertEqual(self.client.post(url, {"file": self.upload([["BI", "CDF", "F", 20]])}).status_code, 302)`
- `self.assertEqual(version.allocations.get().amount, 20)`
- `self.assertContains(self.client.post(url, {"file": self.upload([["BI", "CDF", "F", 30]])}), "Import impossible")`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.get(url, {"template": "xlsx"}).status_code, 403)`

### AUT-D399BB8FA4 — `purchasing.test_allocation_excel.AllocationExcelTests.test_template_can_be_downloaded_from_allocation_versions_page`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:47](../purchasing/test_allocation_excel.py#L47).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_template_can_be_downloaded_from_allocation_versions_page --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(self.client.get(url), 'aria-label="Télécharger le modèle Excel d’alimentation du budget"')`
- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(list(workbook["Allocations"].values), [tuple(HEADERS)])`
- `self.assertIn(("BI", "Budget"), list(workbook["Produits BI"].values))`

### AUT-19445FCD02 — `purchasing.test_allocation_excel.AllocationExcelTests.test_template_contains_current_allocations_and_reference_codes`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_excel.py:36](../purchasing/test_allocation_excel.py#L36).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_excel.AllocationExcelTests.test_template_contains_current_allocations_and_reference_codes --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(workbook.sheetnames, ["Allocations", "Produits BI", "CDF", "Financements"])`
- `self.assertEqual(list(workbook["Allocations"].values), [tuple(HEADERS), ("BI", "CDF", "F", 123)])`
- `self.assertEqual(workbook["Allocations"]["A2"].data_type, "s")`

### AUT-93FB8C7107 — `purchasing.test_allocation_search.AllocationSearchTests.test_complete_selects_remain_available_without_javascript`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_search.py:136](../purchasing/test_allocation_search.py#L136).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_search.AllocationSearchTests.test_complete_selects_remain_available_without_javascript --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.context["reference_choices"], {})`
- `self.assertEqual(len(response.context["formset"].forms[0].fields["budget_product"].choices), 3)`
- `self.assertIn("full_choices=1", response.context["form_action"])`

### AUT-1138AFFEC6 — `purchasing.test_allocation_search.AllocationSearchTests.test_filtered_edits_and_deletions_preserve_other_allocations`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_search.py:60](../purchasing/test_allocation_search.py#L60).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_search.AllocationSearchTests.test_filtered_edits_and_deletions_preserve_other_allocations --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(self.client.post(url, data), url)`
- `self.assertEqual(line.amount, 150)`
- `self.assertEqual(other.amount, 200)`
- `self.assertRedirects(self.client.post(url, data), url)`
- `self.assertFalse(Allocation.objects.filter(pk=line.pk).exists())`
- `self.assertTrue(Allocation.objects.filter(pk=other.pk).exists())`

### AUT-B42A691A85 — `purchasing.test_allocation_search.AllocationSearchTests.test_filtered_export_includes_all_matching_pages`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_search.py:79](../purchasing/test_allocation_search.py#L79).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_search.AllocationSearchTests.test_filtered_export_includes_all_matching_pages --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(len(rows), 36)`
- `self.assertEqual(sum(Decimal(str(row[-1])) for row in rows[1:]), 630)`

### AUT-62EE2F110D — `purchasing.test_allocation_search.AllocationSearchTests.test_large_reference_list_is_sent_once_and_response_stays_small`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_search.py:101](../purchasing/test_allocation_search.py#L101).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_search.AllocationSearchTests.test_large_reference_list_is_sent_once_and_response_stays_small --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertLess(len(response.content), 100000)`
- `self.assertEqual(len(response.context["reference_choices"]["budget_product"]), 502)`
- `self.assertEqual(response.content.count(b'id="allocation-reference-data"'), 1)`
- `self.assertLessEqual(len(form.fields["budget_product"].choices), 2)`

### AUT-D86496CAA8 — `purchasing.test_allocation_search.AllocationSearchTests.test_lightweight_selects_still_allow_changing_to_another_valid_product`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_search.py:117](../purchasing/test_allocation_search.py#L117).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_search.AllocationSearchTests.test_lightweight_selects_still_allow_changing_to_another_valid_product --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(self.client.post(url, data), url)`
- `self.assertEqual(line.budget_product_id, replacement.pk)`
- `self.assertEqual(line.amount, 150)`
- `self.assertTrue(response.context["formset"].forms[0].errors)`
- `self.assertEqual(line.budget_product_id, replacement.pk)`

### AUT-0934567BD4 — `purchasing.test_allocation_search.AllocationSearchTests.test_pagination_limits_edit_forms_and_totals_cover_all_pages`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_search.py:48](../purchasing/test_allocation_search.py#L48).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_search.AllocationSearchTests.test_pagination_limits_edit_forms_and_totals_cover_all_pages --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(first.context["formset"].initial_form_count(), 25)`
- `self.assertEqual(first.context["total"], 630)`
- `self.assertEqual(second.context["formset"].initial_form_count(), 10)`
- `self.assertEqual(second.context["filtered_total"], 630)`
- `self.assertFalse({line.pk for line in first.context["lines"]} & {line.pk for line in second.context["lines"]})`

### AUT-75266BB345 — `purchasing.test_allocation_search.AllocationSearchTests.test_published_read_only_allocations_have_the_same_search_and_totals`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_search.py:91](../purchasing/test_allocation_search.py#L91).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_search.AllocationSearchTests.test_published_read_only_allocations_have_the_same_search_and_totals --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(response.context["can_edit_allocations"])`
- `self.assertEqual(response.context["total"], 100)`
- `self.assertEqual(response.context["filtered_total"], 100)`
- `self.assertNotContains(response, 'id="budget-allocations"')`

### AUT-6121D8DA3D — `purchasing.test_allocation_search.AllocationSearchTests.test_search_by_product_code_or_label_returns_filtered_total_and_full_total`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_allocation_search.py:27](../purchasing/test_allocation_search.py#L27).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_allocation_search.AllocationSearchTests.test_search_by_product_code_or_label_returns_filtered_total_and_full_total --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.context["filtered_total"], 0)`
- `self.assertEqual(response.context["total"], 330)`
- `self.assertEqual(response.context["page"].paginator.count, 0)`
- `self.assertEqual(list(response.context["versions"])[0].allocation_total, 330)`
- `self.assertEqual(response.context["total"], 330)`
- `self.assertEqual(response.context["filtered_total"], 130)`
- `self.assertEqual(len(response.context["lines"]), 2)`
- `self.assertTemplateUsed(response, "purchasing/budget_allocations_results.html")`
- `self.assertNotContains(response, "<!doctype html>")`

### AUT-D76884F67E — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_access_control`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:288](../purchasing/test_budget_workspace.py#L288).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_access_control --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(self.index).status_code, 302)`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.post(url, {"action": "publish"}).status_code, 403)`

### AUT-229C7BCCD5 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_admin_unlocks_edits_and_relocks_published_allocations`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:63](../purchasing/test_budget_workspace.py#L63).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_admin_unlocks_edits_and_relocks_published_allocations --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.post(url, {"action": "unlock"}).status_code, 403)`
- `self.assertContains(self.client.get(url), "Débloquer pour modification")`
- `self.assertRedirects(self.client.post(url, {"action": "unlock"}), url)`
- `self.assertIsNotNone(version.editing_unlocked_at)`
- `self.assertEqual(version.published_at, publication)`
- `self.assertEqual(version.envelope.active_version_id, version.pk)`
- `self.assertContains(response, "Enregistrer les lignes")`
- `self.assertNotContains(response, "Publier et activer cette version")`
- `self.assertNotContains(self.client.get(url), "Enregistrer les lignes")`
- `self.assertEqual(self.client.post(url, payload).status_code, 403)`
- `self.assertRedirects(self.client.post(url, payload), url)`
- `self.assertEqual(version.allocations.get().amount, Decimal("1500"))`
- `self.assertEqual(Decimal(before.state["versions"][str(version.pk)]["rows"][0]["allocated"]), Decimal("1200"))`
- `self.assertRedirects(self.client.post(url, {"action": "lock"}), url)`
- `self.assertIsNone(version.editing_unlocked_at)`
- `self.assertIsNone(version.locked_at)`
- `self.assertEqual(version.published_at, publication)`
- `self.assertNotContains(self.client.get(url), "Enregistrer les lignes")`
- `self.assertEqual(version.allocations.get().amount, Decimal("1500"))`

### AUT-F29AF7DE09 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_allocation_input_displays_two_decimals_without_changing_stored_precision`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:27](../purchasing/test_budget_workspace.py#L27).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_allocation_input_displays_two_decimals_without_changing_stored_precision --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, 'value="1200.12"')`
- `self.assertNotContains(response, 'value="1200.1234567890"')`
- `self.assertEqual(allocation.amount, Decimal("1200.1234567890"))`

### AUT-825222734A — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_budget_manager_cannot_create_requests_without_permission`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:298](../purchasing/test_budget_workspace.py#L298).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_budget_manager_cannot_create_requests_without_permission --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(self.client.get(reverse("purchasing:list")), reverse("purchasing:budget_home"))`
- `self.assertNotContains(response, "Mes demandes")`
- `self.assertNotContains(response, "Créer une demande")`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.post(url, {}).status_code, 403)`
- `self.assertContains(self.client.get(reverse("purchasing:list")), "Mes demandes")`
- `self.assertEqual(self.client.get(url).status_code, 200)`

### AUT-2C470DA443 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_budget_product_search_matches_code_or_label`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:37](../purchasing/test_budget_workspace.py#L37).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_budget_product_search_matches_code_or_label --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(url).context["products"].count(), 3)`
- `self.assertEqual(list(response.context["products"]), expected)`
- `self.assertEqual(response.context["search"], search.strip())`

### AUT-0BC7CA0B15 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_create_fill_publish_and_replace`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:147](../purchasing/test_budget_workspace.py#L147).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_create_fill_publish_and_replace --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(self.client.post(url, self.line_data()), url)`
- `self.assertEqual(version.allocations.get().amount, Decimal("1200"))`
- `self.assertRedirects(self.client.post(url, {"action": "publish"}), url)`
- `self.assertIsNotNone(version.published_at)`
- `self.assertContains(self.client.get(url), "Version active")`
- `self.assertEqual(version.allocations.get().amount, Decimal("1200"))`
- `self.assertEqual(version.envelope.active_version_id, replacement.pk)`
- `self.assertEqual(version.allocations.get().amount, Decimal("1200"))`

### AUT-1639D27B5F — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_delete_draft_preserves_history_and_requires_confirmation`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:200](../purchasing/test_budget_workspace.py#L200).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_delete_draft_preserves_history_and_requires_confirmation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(delete_url).status_code, 403)`
- `self.assertContains(response, "Confirmer la suppression")`
- `self.assertIsNone(version.deleted_at)`
- `self.assertRedirects(self.client.post(delete_url), reverse("purchasing:allocation_versions"))`
- `self.assertIsNotNone(version.deleted_at)`
- `self.assertEqual(version.allocations.count(), 1)`
- `self.assertNotContains(self.client.get(reverse("purchasing:allocation_versions")), version.label)`
- `self.assertEqual(self.client.get(detail).status_code, 404)`
- `self.assertEqual(response.context["state"]["status"], "Supprimée")`
- `self.assertEqual(BudgetHistoryEvent.objects.latest("pk").actor, "admin_delete")`
- `self.assertEqual(self.client.post(delete_url).status_code, 404)`

### AUT-9EBCE41997 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_delete_empty_draft_and_refuse_published_or_locked_versions`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:224](../purchasing/test_budget_workspace.py#L224).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_delete_empty_draft_and_refuse_published_or_locked_versions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertIsNone(version.deleted_at)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-D86638F2CE — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_deleted_row_can_be_saved_with_only_its_hidden_fields`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:14](../purchasing/test_budget_workspace.py#L14).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_deleted_row_can_be_saved_with_only_its_hidden_fields --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(Allocation.objects.filter(pk=allocation.pk).exists())`
- `self.assertRedirects(self.client.post(url, payload), url)`
- `self.assertFalse(Allocation.objects.filter(pk=allocation.pk).exists())`

### AUT-87BD82853A — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_draft_unlock_and_deleted_version_refusal`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:106](../purchasing/test_budget_workspace.py#L106).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_draft_unlock_and_deleted_version_refusal --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(unlocked.allocations_editable)`
- `self.assertIsNone(unlocked.locked_at)`
- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(ValidationError)`

### AUT-2CAED236DA — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_empty_version_is_saved_and_can_be_reopened`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:178](../purchasing/test_budget_workspace.py#L178).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_empty_version_is_saved_and_can_be_reopened --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(version.allocations.exists())`
- `self.assertContains(self.client.get(reverse("purchasing:allocation_versions")), "À compléter")`
- `self.assertEqual(self.client.get(url).status_code, 200)`
- `self.assertRedirects(self.client.post(url, self.line_data()), url)`
- `self.assertEqual(version.allocations.get().amount, Decimal("1200"))`

### AUT-7A2DF13C98 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_invalid_duplicate_negative_and_empty_publication`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:166](../purchasing/test_budget_workspace.py#L166).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_invalid_duplicate_negative_and_empty_publication --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIsNone(version.published_at)`
- `self.assertEqual(response.status_code, 200)`
- `self.assertFalse(response.context["formset"].is_valid())`
- `self.assertFalse(Allocation.objects.exists())`

### AUT-D3CEDAD3AD — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_live_product_search_returns_only_results_and_filtered_export_link`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:48](../purchasing/test_budget_workspace.py#L48).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_live_product_search_returns_only_results_and_filtered_export_link --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(page, 'id="budget-product-search"')`
- `self.assertNotContains(page, 'aria-label="Rechercher les produits"')`
- `self.assertContains(response, "LIVE-01")`
- `self.assertNotContains(response, "<html")`
- `self.assertNotContains(response, 'name="csrfmiddlewaretoken"')`
- `self.assertContains(response, "q=LIVE")`
- `self.assertEqual(response.context["products"].count(), 2)`

### AUT-94E9698332 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_locked_version_rejects_allocation_and_version_writes`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:265](../purchasing/test_budget_workspace.py#L265).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_locked_version_rejects_allocation_and_version_writes --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(Allocation.objects.get(pk=allocation.pk).amount, Decimal("1200"))`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-719A7C49F0 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_only_superuser_can_lock_an_empty_version`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:245](../purchasing/test_budget_workspace.py#L245).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_only_superuser_can_lock_an_empty_version --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.post(url, {"action": "lock"}).status_code, 403)`
- `self.assertRedirects(self.client.post(url, {"action": "lock"}), url)`
- `self.assertIsNotNone(version.locked_at)`
- `self.assertFalse(version.allocations.exists())`
- `self.assertContains(self.client.get(url), "Version bloquée")`
- `self.assertContains(self.client.get(reverse("purchasing:allocation_versions")), "Bloquée")`
- `self.assertNotContains(self.client.get(url), "Enregistrer les lignes")`
- `self.assertFalse(version.allocations.exists())`
- `self.assertEqual(event.state["versions"][str(version.pk)]["status"], "Bloquée")`
- `self.assertEqual(event.actor, "admin_lock")`

### AUT-A736118FE5 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_product_permission_grant_group_and_revocation`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:338](../purchasing/test_budget_workspace.py#L338).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_product_permission_grant_group_and_revocation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.post(url, data).status_code, 403)`
- `self.assertContains(self.client.get(reverse("purchasing:budget_home")), url)`
- `self.assertRedirects(self.client.post(url, data), url)`
- `self.assertTrue(BudgetProduct.objects.filter(code="NEW-BI").exists())`
- `self.assertIn("code", response.context["form"].errors)`
- `self.assertEqual(BudgetProduct.objects.filter(code="NEW-BI").count(), 1)`
- `self.assertFalse(response.context["form"].is_valid())`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertNotContains(self.client.get(reverse("purchasing:budget_home")), url)`
- `self.assertEqual(self.client.get(url).status_code, 200)`
- `self.assertEqual(self.client.post(url, {"code": "DENIED", "label": "Denied"}).status_code, 403)`
- `self.assertFalse(BudgetProduct.objects.filter(code="DENIED").exists())`
- `self.assertEqual(self.client.get(url).status_code, 302)`

### AUT-99F01A0725 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_sections_and_detailed_product_permissions`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:314](../purchasing/test_budget_workspace.py#L314).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_sections_and_detailed_product_permissions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.post(url, {}).status_code, 403)`
- `self.assertContains(self.client.get(reverse("purchasing:list")), "Produits détaillés")`
- `self.assertRedirects(self.client.post(url, data), url)`
- `self.assertEqual(DetailedProduct.objects.get(code="DETAIL").budget_product, self.product)`
- `self.assertIn("code", self.client.post(url, data).context["form"].errors)`
- `self.assertContains(response, "Alimenter une version budgétaire")`
- `self.assertEqual(response.context["nav_section"], "budget")`
- `self.assertEqual(self.client.get(reverse("purchasing:configuration")).status_code, 403)`
- `self.assertContains(response, reverse("admin:accounts_user_changelist"))`
- `self.assertNotContains(response, "Groupes et permissions")`
- `self.assertEqual(response.context["nav_section"], "configuration")`

### AUT-6ACA97BAC1 — `purchasing.test_budget_workspace.BudgetWorkspaceTests.test_version_name_is_unique_within_the_year`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_budget_workspace.py:187](../purchasing/test_budget_workspace.py#L187).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_budget_workspace.BudgetWorkspaceTests.test_version_name_is_unique_within_the_year --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(EnvelopeVersion.objects.count(), 1)`
- `self.assertEqual(response.status_code, 302)`
- `self.assertEqual(response.status_code, 200)`
- `self.assertIn("label", response.context["form"].errors)`
- `self.assertRaises(IntegrityError)`

### AUT-898D886937 — `purchasing.test_configuration.ConfigurationGroupingTests.test_django_admin_groups_workflow_models_and_application_links`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_configuration.py:8](../purchasing/test_configuration.py#L8).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_configuration.ConfigurationGroupingTests.test_django_admin_groups_workflow_models_and_application_links --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertContains(response, "Responsables et validations")`
- `self.assertNotIn('id="workflow-settings-validationfunction"', html)`
- `self.assertNotIn(reverse("authorizations"), group)`
- `self.assertContains(response, "Responsables et validations")`
- `self.assertContains(response, reverse("entity_managers"))`
- `self.assertIn(reverse(name), group)`

### AUT-5F4BEE03B6 — `purchasing.test_configuration.ConfigurationGroupingTests.test_django_admin_workflow_group_preserves_permissions`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_configuration.py:25](../purchasing/test_configuration.py#L25).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_configuration.ConfigurationGroupingTests.test_django_admin_workflow_group_preserves_permissions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Responsables et validations")`
- `self.assertContains(response, reverse("admin:accounts_role_changelist"))`
- `self.assertNotContains(response, f'href="{reverse(name)}"')`

### AUT-585D66CFDC — `purchasing.test_configuration.ConfigurationGroupingTests.test_nonstaff_manager_only_sees_authorized_application_links`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_configuration.py:49](../purchasing/test_configuration.py#L49).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_configuration.ConfigurationGroupingTests.test_nonstaff_manager_only_sees_authorized_application_links --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(links, [reverse("entity_managers")])`
- `self.assertNotContains(response, "/admin/accounts/validationfunction/")`

### AUT-1E3339404F — `purchasing.test_configuration.ConfigurationGroupingTests.test_workflow_settings_are_grouped_with_direct_links`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_configuration.py:35](../purchasing/test_configuration.py#L35).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_configuration.ConfigurationGroupingTests.test_workflow_settings_are_grouped_with_direct_links --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual({link["url"] for link in workflow["links"]}, {         reverse("admin:accounts_role_changelist"),         reverse("admin:budgeting_costcenter_changelist"),         reverse("admin:budgeting_support_changelist"),         reverse("entity_managers"),     })`
- `self.assertContains(response, 'id="workflow-settings"')`

### AUT-E8FEEF2E6D — `purchasing.test_flow.PurchaseFlowTests.test_admin_budget_edit_preserves_reservations_and_live_order_flow`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:26](../purchasing/test_flow.py#L26).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_admin_budget_edit_preserves_reservations_and_live_order_flow --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(), Decimal("-71"))`
- `self.assertEqual(self.version.published_at, publication)`
- `self.assertIsNone(self.version.locked_at)`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertEqual(BudgetEntry.objects.get().state, "committed")`
- `self.assertEqual(self.balance(), Decimal("-71"))`
- `self.assertRaises(PurchaseRequestError)`

### AUT-819F175AD9 — `purchasing.test_flow.PurchaseFlowTests.test_admin_can_clone_and_publish_budget`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:588](../purchasing/test_flow.py#L588).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_admin_can_clone_and_publish_budget --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 302)`
- `self.assertIsNone(clone.published_at)`
- `self.assertEqual(response.status_code, 302)`
- `self.assertIsNotNone(clone.published_at)`

### AUT-750C450338 — `purchasing.test_flow.PurchaseFlowTests.test_all_requests_grant_revoke_and_read_only`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:225](../purchasing/test_flow.py#L225).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_all_requests_grant_revoke_and_read_only --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(url).status_code, 302)`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.get(detail).status_code, 404)`
- `self.assertContains(response, self.purchase.number)`
- `self.assertContains(response, self.owner.username)`
- `self.assertEqual(response.status_code, 200)`
- `self.assertFalse(response.context["editable"])`
- `self.assertFalse(response.context["can_cancel"])`
- `self.assertNotContains(self.client.get(reverse("purchasing:list")), self.purchase.number)`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.get(detail).status_code, 404)`
- `self.assertEqual(self.client.get(url).status_code, 200)`
- `self.assertEqual(self.client.post(reverse("purchasing:" + name, args=[self.purchase.pk]), {}).status_code, 404)`

### AUT-7F7C92A9AF — `purchasing.test_flow.PurchaseFlowTests.test_browser_submit_approve_and_role_pages`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:517](../purchasing/test_flow.py#L517).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_browser_submit_approve_and_role_pages --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(url).status_code, 200)`
- `self.assertFalse(Submission.objects.exists())`
- `self.assertEqual(self.client.post(url, {"expected_revision": self.purchase.revision}).status_code, 302)`
- `self.assertContains(inbox, "Traiter")`
- `self.assertEqual(self.client.post(url, {"expected_revision": self.purchase.revision, "decision": "approve"}).status_code, 302)`
- `self.assertEqual(self.client.get(url).status_code, 200, url)`

### AUT-28D3196582 — `purchasing.test_flow.PurchaseFlowTests.test_budget_check_displays_locked_version_as_locked`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:336](../purchasing/test_flow.py#L336).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_budget_check_displays_locked_version_as_locked --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, locked.label + " · Bloquée")`

### AUT-C3048BC2E3 — `purchasing.test_flow.PurchaseFlowTests.test_budget_check_excludes_deleted_versions_and_refuses_direct_selection`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:321](../purchasing/test_flow.py#L321).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_budget_check_excludes_deleted_versions_and_refuses_direct_selection --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertNotContains(response, deleted.label)`
- `self.assertContains(response, self.version.label)`
- `self.assertIn("no-store", response.headers["Cache-Control"])`
- `self.assertIn("version", response.context["form"].errors)`
- `self.assertIsNone(response.context["result"])`

### AUT-E10FAD5B47 — `purchasing.test_flow.PurchaseFlowTests.test_budget_check_requires_login_and_button_is_visible`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:313](../purchasing/test_flow.py#L313).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_budget_check_requires_login_and_button_is_visible --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("purchasing:budget_check")).status_code, 302)`
- `self.assertContains(response, 'id="budget-check-open"')`
- `self.assertContains(response, "Vérifier un budget")`
- `self.assertEqual(response.headers["X-Frame-Options"], "DENY")`

### AUT-99F5AD6A42 — `purchasing.test_flow.PurchaseFlowTests.test_budget_check_standard_user_sees_live_balance`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:209](../purchasing/test_flow.py#L209).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_budget_check_standard_user_sees_live_balance --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")`
- `self.assertEqual(response.context["result"]["available"], Decimal("1000"))`
- `self.assertEqual(response.context["result"]["available"], Decimal("879"))`
- `self.assertEqual(response.context["result"]["available"], Decimal("879"))`

### AUT-654A3A36F0 — `purchasing.test_flow.PurchaseFlowTests.test_budget_check_uses_selected_draft_or_replaced_version`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:268](../purchasing/test_flow.py#L268).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_budget_check_uses_selected_draft_or_replaced_version --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIn("version", response.context["form"].errors)`
- `self.assertIsNone(response.context["result"])`
- `self.assertEqual(response.context["result"]["available"], Decimal(expected))`
- `self.assertEqual(response.context["result"]["version"], version.label)`

### AUT-42A03C0574 — `purchasing.test_flow.PurchaseFlowTests.test_budget_check_validation_and_missing_allocation`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:252](../purchasing/test_flow.py#L252).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_budget_check_validation_and_missing_allocation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(response.context["result"]["allocated"])`
- `self.assertEqual(response.context["result"]["available"], Decimal("0"))`
- `self.assertIsNone(response.context["result"])`
- `self.assertIn("budget_product", response.context["form"].errors)`
- `self.assertContains(response, "Version budgétaire")`

### AUT-9404CD60E2 — `purchasing.test_flow.PurchaseFlowTests.test_budget_table_refuses_deleted_or_invalid_selection`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:301](../purchasing/test_flow.py#L301).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_budget_table_refuses_deleted_or_invalid_selection --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertNotContains(self.client.get(url), deleted.label)`
- `self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")`
- `self.assertIn("version", response.context["form"].errors)`
- `self.assertEqual(response.context["rows"], [])`

### AUT-8EE3293B22 — `purchasing.test_flow.PurchaseFlowTests.test_budget_table_selects_one_version_and_keeps_annual_reservations`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:284](../purchasing/test_flow.py#L284).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_budget_table_selects_one_version_and_keeps_annual_reservations --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(url).context["selected_version"].pk, replacement.pk)`
- `self.assertEqual(response.context["selected_version"].pk, version.pk)`
- `self.assertEqual(len(response.context["rows"]), 1)`
- `self.assertEqual(response.context["rows"][0]["available"], Decimal(amount))`
- `self.assertNotContains(response, "<th>Année / version</th>")`
- `self.assertContains(response, 'name="version"')`

### AUT-61336CB656 — `purchasing.test_flow.PurchaseFlowTests.test_configuration_and_budget_published_rows_cannot_be_changed`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:462](../purchasing/test_flow.py#L462).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_configuration_and_budget_published_rows_cannot_be_changed --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-4AD3B96DA5 — `purchasing.test_flow.PurchaseFlowTests.test_decision_requires_post_csrf_and_fresh_revision`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:534](../purchasing/test_flow.py#L534).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_decision_requires_post_csrf_and_fresh_revision --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(client.get(url).status_code, 200)`
- `self.assertEqual(step.state, "pending")`
- `self.assertEqual(client.post(url, {"expected_revision": purchase.revision, "decision": "approve"}).status_code, 403)`
- `self.assertRaises(PurchaseRequestConflict)`

### AUT-48C8D47C2C — `purchasing.test_flow.PurchaseFlowTests.test_delegation_chains_and_overlaps_are_rejected`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:486](../purchasing/test_flow.py#L486).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_delegation_chains_and_overlaps_are_rejected --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(ValidationError)`

### AUT-B97ABCB448 — `purchasing.test_flow.PurchaseFlowTests.test_demo_seed_is_repeatable_and_preserves_password_and_draft`

Type : Intégration Django / service / HTTP. Source : [.venv/Lib/site-packages/django/test/utils.py:573](../.venv/Lib/site-packages/django/test/utils.py#L573).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_demo_seed_is_repeatable_and_preserves_password_and_draft --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(user.check_password("TestAchats!2026"))`
- `self.assertEqual(purchase.lines.count(), 2)`
- `self.assertTrue(user.check_password("PersonalTestPassword"))`
- `self.assertEqual(PurchaseRequest.objects.filter(created_by=user).count(), 1)`

### AUT-FF18EF0BDD — `purchasing.test_flow.PurchaseFlowTests.test_demo_seed_refuses_usual_database`

Type : Intégration Django / service / HTTP. Source : [.venv/Lib/site-packages/django/test/utils.py:567](../.venv/Lib/site-packages/django/test/utils.py#L567).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_demo_seed_refuses_usual_database --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(CommandError)`

### AUT-F5DD93E3EF — `purchasing.test_flow.PurchaseFlowTests.test_document_uses_immutable_supplier_and_line_snapshot`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:494](../purchasing/test_flow.py#L494).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_document_uses_immutable_supplier_and_line_snapshot --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Supplier snapshot")`
- `self.assertNotContains(response, "Changed later")`
- `self.assertEqual(self.client.get(f"/achats/{self.purchase.pk}/commande/").status_code, 404)`

### AUT-8346318A0A — `purchasing.test_flow.PurchaseFlowTests.test_entity_managers_validate_without_roles_or_authorizations`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:102](../purchasing/test_flow.py#L102).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_entity_managers_validate_without_roles_or_authorizations --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.state, "pending")`
- `self.assertIsNone(step.function_id)`
- `self.assertIsNone(step.role_id)`
- `self.assertIsNone(flow.authority(self.first, step))`
- `self.assertIsNotNone(flow.authority(self.other, step))`
- `self.assertTrue(PurchaseOrder.objects.filter(purchase_request=self.purchase).exists())`
- `self.assertIsNone(step.authorization_id)`
- `self.assertEqual(step.evaluated_scope["manager_source"], "cdf")`

### AUT-428B7227DF — `purchasing.test_flow.PurchaseFlowTests.test_global_badge_uses_current_manager_and_delegation`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:67](../purchasing/test_flow.py#L67).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_global_badge_uses_current_manager_and_delegation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(flow.pending_validation_count(self.other), 0)`
- `self.assertEqual(flow.pending_validation_count(self.other), 1)`
- `self.assertEqual(flow.pending_validation_count(self.first), 1)`
- `self.assertEqual(flow.pending_validation_count(self.first), 0)`
- `self.assertEqual(flow.pending_validation_count(self.other), 0)`

### AUT-649D883B73 — `purchasing.test_flow.PurchaseFlowTests.test_global_delegation_uses_principal_authorization_and_real_actor`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:476](../purchasing/test_flow.py#L476).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_global_delegation_uses_principal_authorization_and_real_actor --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.approved_by, self.other)`
- `self.assertIsNone(step.authorization_id)`
- `self.assertEqual(step.evaluated_scope["represented_user"], self.first.pk)`

### AUT-FC02697CF5 — `purchasing.test_flow.PurchaseFlowTests.test_global_personal_icons_and_pending_badge`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:48](../purchasing/test_flow.py#L48).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_global_personal_icons_and_pending_badge --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.context["pending_validation_count"], 1)`
- `self.assertContains(response, 'id="validation-count"')`
- `self.assertContains(response, f'href="{reverse("my_validations")}"')`
- `self.assertContains(response, f'href="{reverse("my_delegations")}"')`
- `self.assertNotContains(response, f'href="{reverse("purchasing:inbox")}"')`
- `self.assertNotContains(response, f'href="{reverse("purchasing:delegations")}"')`
- `self.assertEqual(response.context["pending_validation_count"], 0)`
- `self.assertNotContains(response, 'id="validation-count"')`
- `self.assertEqual(response.context["pending_validation_count"], 0)`
- `self.assertEqual(flow.pending_validation_count(self.second), 0)`

### AUT-6EEB04A5A1 — `purchasing.test_flow.PurchaseFlowTests.test_mail_failure_does_not_undo_submission`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:559](../purchasing/test_flow.py#L559).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_mail_failure_does_not_undo_submission --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.purchase.status, "SUBMITTED")`
- `self.assertTrue(PurchaseNotice.objects.filter(email_state="failed").exists())`

### AUT-B692F6197D — `purchasing.test_flow.PurchaseFlowTests.test_manager_configuration_screen_permissions_and_save`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:132](../purchasing/test_flow.py#L132).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_manager_configuration_screen_permissions_and_save --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("entity_managers")).status_code, 403)`
- `self.assertContains(self.client.get(reverse("entity_managers")), self.cdf.code)`
- `self.assertRedirects(response, reverse("entity_managers"))`
- `self.assertEqual(list(self.support.managers.all()), [self.other])`

### AUT-65E807E701 — `purchasing.test_flow.PurchaseFlowTests.test_missing_manager_and_replacement_refresh_candidates`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:117](../purchasing/test_flow.py#L117).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_missing_manager_and_replacement_refresh_candidates --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.state, "unassigned")`
- `self.assertEqual(step.state, "pending")`
- `self.assertIsNone(flow.authority(self.other, step))`
- `self.assertIsNotNone(flow.authority(self.first, step))`
- `self.assertTrue(PurchaseNotice.objects.filter(step=step, recipient=self.first, active=True).exists())`

### AUT-885607E103 — `purchasing.test_flow.PurchaseFlowTests.test_no_eligible_approver_reserves_and_can_be_reassigned`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:438](../purchasing/test_flow.py#L438).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_no_eligible_approver_reserves_and_can_be_reassigned --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.state, "unassigned")`
- `self.assertEqual(self.balance(), 879)`
- `self.assertTrue(PurchaseOrder.objects.exists())`

### AUT-746F13035F — `purchasing.test_flow.PurchaseFlowTests.test_notification_delivery_and_obsolete_suppression`

Type : Intégration Django / service / HTTP. Source : [.venv/Lib/site-packages/django/test/utils.py:547](../.venv/Lib/site-packages/django/test/utils.py#L547).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_notification_delivery_and_obsolete_suppression --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(mail.outbox)`
- `self.assertEqual(len(mail.outbox), count)`
- `self.assertFalse(PurchaseNotice.objects.filter(active=True).exists())`

### AUT-19E4E64B4E — `purchasing.test_flow.PurchaseFlowTests.test_one_missing_combination_rolls_back_other_lines`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:374](../purchasing/test_flow.py#L374).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_one_missing_combination_rolls_back_other_lines --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(BudgetEntry.objects.exists())`
- `self.assertRaises(PurchaseRequestError)`

### AUT-32D63A6CF8 — `purchasing.test_flow.PurchaseFlowTests.test_operational_monitor_does_not_leak_financial_payload`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:506](../purchasing/test_flow.py#L506).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_operational_monitor_does_not_leak_financial_payload --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, self.purchase.number)`
- `self.assertNotContains(response, "Sensitive item")`
- `self.assertNotContains(response, self.supplier.name)`
- `self.assertEqual(self.client.get(f"/achats/{self.purchase.pk}/").status_code, 404)`
- `self.assertEqual(self.client.get("/achats/budgets/").status_code, 403)`

### AUT-7895F8BFD6 — `purchasing.test_flow.PurchaseFlowTests.test_personal_pages_are_global_and_do_not_select_purchases`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:80](../purchasing/test_flow.py#L80).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_personal_pages_are_global_and_do_not_select_purchases --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(response, reverse("my_delegations"))`
- `self.assertEqual(self.client.get(reverse(name)).status_code, 302)`
- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.context["nav_section"], "personal")`
- `self.assertContains(response, 'aria-label="Espace personnel"')`
- `self.assertContains(response, 'id="my-validations"')`
- `self.assertContains(response, 'id="my-delegations"')`

### AUT-ACDEF65045 — `purchasing.test_flow.PurchaseFlowTests.test_reassignment_requires_permission_reason_and_scope`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:452](../purchasing/test_flow.py#L452).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_reassignment_requires_permission_reason_and_scope --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(error)`

### AUT-6BE900BA09 — `purchasing.test_flow.PurchaseFlowTests.test_rejection_is_terminal_and_no_reservation_remains`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:400](../purchasing/test_flow.py#L400).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_rejection_is_terminal_and_no_reservation_remains --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(), 1000)`
- `self.assertRaises(PurchaseRequestError)`

### AUT-80CF346D1F — `purchasing.test_flow.PurchaseFlowTests.test_requester_can_cancel_submitted_without_order`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:407](../purchasing/test_flow.py#L407).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_requester_can_cancel_submitted_without_order --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(), 1000)`
- `self.assertFalse(Submission.objects.get().active)`
- `self.assertEqual(sum(Decimal(row["reserved"]) for row in rows), 0)`

### AUT-4DD0F552B9 — `purchasing.test_flow.PurchaseFlowTests.test_t001_t004_complete_flow_preserves_budget_and_creates_one_order`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:344](../purchasing/test_flow.py#L344).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_t001_t004_complete_flow_preserves_budget_and_creates_one_order --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(sum(Decimal(row["reserved"]) for row in reserved_rows), Decimal("121"))`
- `self.assertEqual(self.balance(), Decimal("879"))`
- `self.assertTrue(PurchaseOrder.objects.exists())`
- `self.assertEqual(self.balance(), Decimal("879"))`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertEqual(BudgetEntry.objects.get().state, "committed")`
- `self.assertEqual(sum(Decimal(row["committed"]) for row in committed_rows), Decimal("121"))`
- `self.assertEqual(sum(Decimal(row["reserved"]) for row in committed_rows), 0)`
- `self.assertEqual(self.purchase.status, "ORDERED")`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertRaises(PurchaseRequestError)`

### AUT-3C69663E33 — `purchasing.test_flow.PurchaseFlowTests.test_t002_combination_aggregate_shortage_rolls_back_all`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:365](../purchasing/test_flow.py#L365).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_t002_combination_aggregate_shortage_rolls_back_all --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(BudgetEntry.objects.exists())`
- `self.assertFalse(Submission.objects.exists())`
- `self.assertEqual(purchase.status, "DRAFT")`
- `self.assertRaises(PurchaseRequestError)`

### AUT-AC846B1485 — `purchasing.test_flow.PurchaseFlowTests.test_t003_correction_releases_every_line_and_preserves_history`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:383](../purchasing/test_flow.py#L383).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_t003_correction_releases_every_line_and_preserves_history --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(), Decimal("1000"))`
- `self.assertEqual(ApprovalStep.objects.filter(state="approved").count(), 1)`
- `self.assertFalse(old.active)`
- `self.assertEqual(old.lines.count(), 2)`
- `self.assertEqual(purchase.submissions.count(), 2)`
- `self.assertEqual(self.balance(), Decimal("879"))`

### AUT-5163ED98DB — `purchasing.test_flow.PurchaseFlowTests.test_t008_new_deficit_blocks_new_reservation_allows_existing_conversion`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:426](../purchasing/test_flow.py#L426).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_t008_new_deficit_blocks_new_reservation_allows_existing_conversion --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.balance(), -71)`
- `self.assertEqual(self.balance(), -71)`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertEqual(PurchaseOrder.objects.get().submission.budget_version_id, self.version.pk)`
- `self.assertRaises(PurchaseRequestError)`

### AUT-BE208FF20C — `purchasing.test_flow.PurchaseFlowTests.test_users_without_grant_cannot_approve`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_flow.py:417](../purchasing/test_flow.py#L417).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow.PurchaseFlowTests.test_users_without_grant_cannot_approve --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(PurchaseOrder.objects.exists())`
- `self.assertRaises(PermissionDenied)`

### AUT-96C1B34283 — `purchasing.test_request_numbers.PurchaseRequestNumberTests.test_legacy_reference_is_preserved`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_request_numbers.py:39](../purchasing/test_request_numbers.py#L39).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_request_numbers.PurchaseRequestNumberTests.test_legacy_reference_is_preserved --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(legacy.number, "DA-9D30A9A088B84D6FB3F1068FA1")`

### AUT-B408B8B0BD — `purchasing.test_request_numbers.PurchaseRequestNumberTests.test_numbers_are_not_reused_after_deletion`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_request_numbers.py:30](../purchasing/test_request_numbers.py#L30).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_request_numbers.PurchaseRequestNumberTests.test_numbers_are_not_reused_after_deletion --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.create().number, "DA-2026-0002")`

### AUT-AFF71E97D3 — `purchasing.test_request_numbers.PurchaseRequestNumberTests.test_numbers_increment_and_restart_each_year`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_request_numbers.py:17](../purchasing/test_request_numbers.py#L17).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_request_numbers.PurchaseRequestNumberTests.test_numbers_increment_and_restart_each_year --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(first.number, "DA-2026-0001")`
- `self.assertEqual(second.number, "DA-2026-0002")`
- `self.assertEqual(third.number, "DA-2027-0001")`
- `self.assertEqual(third.number, "DA-2027-0001")`

### AUT-30F287B50E — `purchasing.test_request_numbers.PurchaseRequestNumberTests.test_unsaved_instance_does_not_consume_number`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_request_numbers.py:35](../purchasing/test_request_numbers.py#L35).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_request_numbers.PurchaseRequestNumberTests.test_unsaved_instance_does_not_consume_number --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(PurchaseRequestSequence.objects.exists())`

### AUT-2FF2A48F15 — `purchasing.test_rules.FixedValidationTests.test_any_active_manager_of_the_line_cdf_can_validate`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:95](../purchasing/test_rules.py#L95).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_any_active_manager_of_the_line_cdf_can_validate --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertCountEqual(step.candidates.all(), [self.first, self.second])`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertIsNone(event.payload["authorization"])`
- `self.assertEqual(event.payload["represented_user"], self.second.pk)`

### AUT-4C67D771CE — `purchasing.test_rules.FixedValidationTests.test_each_line_goes_only_to_its_cdf_manager_and_all_must_approve`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:57](../purchasing/test_rules.py#L57).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_each_line_goes_only_to_its_cdf_manager_and_all_must_approve --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(WorkflowVersion.objects.exists())`
- `self.assertIsNone(Submission.objects.get().workflow_id)`
- `self.assertEqual(ApprovalStep.objects.count(), 2)`
- `self.assertEqual((first.state, second.state), ("pending", "pending"))`
- `self.assertEqual(flow.pending_validation_count(self.first), 1)`
- `self.assertEqual(flow.pending_validation_count(self.second), 1)`
- `self.assertFalse(PurchaseOrder.objects.exists())`
- `self.assertEqual(BudgetEntry.objects.filter(state="reserved").count(), 2)`
- `self.assertEqual(self.purchase.status, "ORDERED")`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertEqual(BudgetEntry.objects.filter(state="committed").count(), 2)`
- `self.assertRaises(PermissionDenied)`
- `self.assertEqual(flow.available(self.budget, cdf.pk, self.funding.pk, self.product.pk), Decimal(900))`

### AUT-0AA23304B2 — `purchasing.test_rules.FixedValidationTests.test_editor_and_admin_configuration_are_retired`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:186](../purchasing/test_rules.py#L186).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_editor_and_admin_configuration_are_retired --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(admin.site.is_registered(WorkflowVersion))`
- `self.assertFalse(admin.site.is_registered(ApprovalRule))`
- `self.assertFalse(WorkflowVersion.objects.exists())`
- `self.assertNotContains(self.client.get(reverse("purchasing:configuration")), "Si… alors…")`
- `self.assertRedirects(self.client.get(url), reverse("purchasing:configuration"))`
- `self.assertEqual(self.client.post(url, {}).status_code, 410)`

### AUT-C7BE102C28 — `purchasing.test_rules.FixedValidationTests.test_missing_manager_blocks_its_line_without_blocking_others`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:107](../purchasing/test_rules.py#L107).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_missing_manager_blocks_its_line_without_blocking_others --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(second.state, "unassigned")`
- `self.assertEqual(second.state, "unassigned")`
- `self.assertFalse(PurchaseOrder.objects.exists())`
- `self.assertEqual(flow.pending_validation_count(self.second), 1)`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`

### AUT-8864F21E2A — `purchasing.test_rules.FixedValidationTests.test_old_automatic_configuration_is_ignored_for_new_submissions`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:141](../purchasing/test_rules.py#L141).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_old_automatic_configuration_is_ignored_for_new_submissions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.manager_source, "cdf")`
- `self.assertFalse(step.rule_snapshot["automatic"])`
- `self.assertFalse(PurchaseOrder.objects.exists())`

### AUT-6A56177B99 — `purchasing.test_rules.FixedValidationTests.test_old_recorded_steps_are_not_rewritten`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:170](../purchasing/test_rules.py#L170).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_old_recorded_steps_are_not_rewritten --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.rule_snapshot["named_user_id"], self.second.pk)`
- `self.assertIsNone(flow.authority(self.first, step))`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`

### AUT-C40188B3CA — `purchasing.test_rules.FixedValidationTests.test_rejection_of_one_line_releases_the_whole_request`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:160](../purchasing/test_rules.py#L160).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_rejection_of_one_line_releases_the_whole_request --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(BudgetEntry.objects.filter(state="released").count(), 2)`
- `self.assertFalse(PurchaseOrder.objects.exists())`

### AUT-49B82E3B27 — `purchasing.test_rules.FixedValidationTests.test_request_page_explains_line_validation_without_rule_editor`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:198](../purchasing/test_rules.py#L198).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_request_page_explains_line_validation_without_rule_editor --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Chaque ligne est valid&eacute;e par le responsable de son CDF")`
- `self.assertNotContains(response, "Simuler les validations")`

### AUT-F292872794 — `purchasing.test_rules.FixedValidationTests.test_revoked_or_inactive_manager_cannot_validate`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:124](../purchasing/test_rules.py#L124).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_revoked_or_inactive_manager_cannot_validate --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(step.state, "unassigned")`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertRaises(PermissionDenied)`

### AUT-7DF4B8AE25 — `purchasing.test_rules.FixedValidationTests.test_same_cdf_still_requires_one_decision_per_line`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:82](../purchasing/test_rules.py#L82).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_same_cdf_still_requires_one_decision_per_line --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(steps[1].state, "pending")`
- `self.assertIsNone(steps[1].evidence_id)`
- `self.assertFalse(PurchaseOrder.objects.exists())`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`

### AUT-EE52F86196 — `purchasing.test_rules.FixedValidationTests.test_steps_follow_order_within_each_line`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:204](../purchasing/test_rules.py#L204).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_steps_follow_order_within_each_line --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(next_step.state, "future")`
- `self.assertEqual(next_step.state, "pending")`
- `self.assertEqual(steps[1].state, "pending")`
- `self.assertFalse(PurchaseOrder.objects.exists())`
- `self.assertTrue(PurchaseOrder.objects.exists())`
- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(PermissionDenied)`

### AUT-10A287DAC8 — `purchasing.test_rules.FixedValidationTests.test_support_is_not_required_and_does_not_add_validation`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_rules.py:152](../purchasing/test_rules.py#L152).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_rules.FixedValidationTests.test_support_is_not_required_and_does_not_add_validation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIsNone(self.purchase.support_id)`
- `self.assertEqual(ApprovalStep.objects.count(), 1)`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`

### AUT-63E797257A — `purchasing.test_ui_actions.SharedActionNavigationTests.test_nonfinancial_reviewer_returns_to_its_inbox`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_ui_actions.py:26](../purchasing/test_ui_actions.py#L26).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_ui_actions.SharedActionNavigationTests.test_nonfinancial_reviewer_returns_to_its_inbox --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, 'aria-label="Retour à mes validations"')`
- `self.assertNotContains(response, 'aria-label="Retour à la demande"')`
- `self.assertContains(response, 'name="csrfmiddlewaretoken"')`
- `self.assertContains(response, 'aria-label="Confirmer"')`

### AUT-F02DE2A142 — `purchasing.test_ui_actions.SharedActionNavigationTests.test_order_can_be_loaded_for_direct_print_with_access_controls`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_ui_actions.py:61](../purchasing/test_ui_actions.py#L61).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_ui_actions.SharedActionNavigationTests.test_order_can_be_loaded_for_direct_print_with_access_controls --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")`
- `self.assertContains(response, 'id="order-print-document"')`
- `self.assertContains(self.client.get(reverse("purchasing:detail", args=[purchase.pk])), 'data-print-order')`
- `self.assertEqual(self.client.get(url).status_code, 404)`

### AUT-C2E135933A — `purchasing.test_ui_actions.SharedActionNavigationTests.test_purchase_has_accessible_icons_and_actions_below_content`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_ui_actions.py:17](../purchasing/test_ui_actions.py#L17).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_ui_actions.SharedActionNavigationTests.test_purchase_has_accessible_icons_and_actions_below_content --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, 'aria-label="Ajouter une ligne"')`
- `self.assertContains(response, 'class="ui-icon ui-back"')`
- `self.assertNotContains(response, '&lt;svg')`
- `self.assertGreater(html.index('aria-label="Actions de la demande"'), html.index('Parcours de validation'))`

### AUT-59424953A7 — `purchasing.test_ui_actions.SharedActionNavigationTests.test_submit_returns_destination_after_success`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_ui_actions.py:51](../purchasing/test_ui_actions.py#L51).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_ui_actions.SharedActionNavigationTests.test_submit_returns_destination_after_success --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.json()["redirect"], reverse("purchasing:detail", args=[self.purchase.pk]))`
- `self.assertEqual(self.purchase.status, "SUBMITTED")`

### AUT-D3A5A59DBA — `purchasing.test_ui_actions.SharedActionNavigationTests.test_submit_returns_error_for_popup_without_changing_request`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_ui_actions.py:36](../purchasing/test_ui_actions.py#L36).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_ui_actions.SharedActionNavigationTests.test_submit_returns_error_for_popup_without_changing_request --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 409)`
- `self.assertEqual(response.json()["errors"], ["Budget insuffisant : disponible 42000,00 EUR."])`
- `self.assertEqual(self.purchase.revision, revision)`
- `self.assertContains(detail, 'id="purchase-error-dialog"')`
- `self.assertContains(detail, 'data-purchase-submit')`

### AUT-DD50C1E058 — `purchasing.test_validation_schemes.ValidationSchemesTests.test_admin_can_read_both_fixed_schemes_in_configuration`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_validation_schemes.py:15](../purchasing/test_validation_schemes.py#L15).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_validation_schemes.ValidationSchemesTests.test_admin_can_read_both_fixed_schemes_in_configuration --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.context["nav_section"], "configuration")`
- `self.assertContains(response, 'id="schema-da"')`
- `self.assertContains(response, 'id="schema-transfert"')`
- `self.assertContains(response, "Responsable du CDF source")`
- `self.assertContains(response, "Responsable du CDF destination")`
- `self.assertContains(response, "Retour pour correction")`
- `self.assertContains(response, "Annulation après approbation")`
- `self.assertContains(response, reverse("purchasing:configuration"))`
- `self.assertEqual(self.client.post(self.url).status_code, 405)`

### AUT-7978CFF0BA — `purchasing.test_validation_schemes.ValidationSchemesTests.test_non_admin_cannot_read_even_with_configuration_permissions`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_validation_schemes.py:34](../purchasing/test_validation_schemes.py#L34).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_validation_schemes.ValidationSchemesTests.test_non_admin_cannot_read_even_with_configuration_permissions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(self.url).status_code, 403)`
- `self.assertNotContains(self.client.get(reverse("purchasing:configuration")), self.url)`
- `self.assertEqual(self.client.get(self.url).status_code, 403)`

### AUT-DF7F4927DB — `purchasing.test_validation_schemes.ValidationSchemesTests.test_requires_login`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_validation_schemes.py:12](../purchasing/test_validation_schemes.py#L12).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_validation_schemes.ValidationSchemesTests.test_requires_login --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(self.client.get(self.url), reverse("login") + "?next=" + self.url)`

### AUT-AD4AB16FAF — `purchasing.test_validation_schemes.ValidationSchemesTests.test_scheme_link_is_only_in_admin_configuration`

Type : Intégration Django / service / HTTP. Source : [purchasing/test_validation_schemes.py:28](../purchasing/test_validation_schemes.py#L28).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_validation_schemes.ValidationSchemesTests.test_scheme_link_is_only_in_admin_configuration --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertNotContains(response, 'href="' + self.url + '"')`
- `self.assertContains(self.client.get(reverse("purchasing:configuration")), 'href="' + self.url + '"')`

### AUT-58346E7A2F — `purchasing.tests.PurchaseDraftTests.test_ach001_exact_amounts_without_rounding`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:39](../purchasing/tests.py#L39).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_ach001_exact_amounts_without_rounding --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(line.total_htva, Decimal("5.6211"))`
- `self.assertEqual(line.total_vat, Decimal("1.180431"))`
- `self.assertEqual(line.total_tvac, Decimal("6.801531"))`
- `self.assertEqual(AuditEvent.objects.count(), 2)`
- `self.assertEqual(self.request.status, PurchaseRequest.Status.DRAFT)`

### AUT-C58C8DE29E — `purchasing.tests.PurchaseDraftTests.test_ach003_ach005_terminal_and_submitted_requests_are_not_editable`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:74](../purchasing/tests.py#L74).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_ach003_ach005_terminal_and_submitted_requests_are_not_editable --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(PurchaseRequestError)`

### AUT-1F9B2B3333 — `purchasing.tests.PurchaseDraftTests.test_ach004_draft_cancellation_is_idempotent_and_audited`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:81](../purchasing/tests.py#L81).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_ach004_draft_cancellation_is_idempotent_and_audited --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(repeated.status, "CANCELLED")`
- `self.assertEqual(AuditEvent.objects.count(), 2)`
- `self.assertRaises(PurchaseRequestError)`

### AUT-092E15B1DB — `purchasing.tests.PurchaseDraftTests.test_ach005_only_requester_can_edit`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:47](../purchasing/tests.py#L47).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_ach005_only_requester_can_edit --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(self.request.lines.exists())`
- `self.assertEqual(AuditEvent.objects.count(), 1)`
- `self.assertRaises(PermissionDenied)`

### AUT-18A2F4E8A3 — `purchasing.tests.PurchaseDraftTests.test_authentication_and_csrf_required`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:139](../purchasing/tests.py#L139).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_authentication_and_csrf_required --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get("/achats/").status_code, 302)`
- `self.assertEqual(client.post(f"/achats/{self.request.pk}/annuler/", {"expected_revision": 1}).status_code, 403)`

### AUT-0CB9048047 — `purchasing.tests.PurchaseDraftTests.test_edit_post_cannot_change_owner_or_status`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:146](../purchasing/tests.py#L146).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_edit_post_cannot_change_owner_or_status --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(result.status_code, 302)`
- `self.assertEqual(self.request.created_by, self.owner)`
- `self.assertEqual(self.request.status, "DRAFT")`

### AUT-A79E19C6ED — `purchasing.tests.PurchaseDraftTests.test_explicit_zero_vat_is_allowed`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:71](../purchasing/tests.py#L71).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_explicit_zero_vat_is_allowed --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.add_line(vat_rate=Decimal("0")).total_vat, 0)`

### AUT-E407D25DAE — `purchasing.tests.PurchaseDraftTests.test_inactive_requester_is_denied`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:89](../purchasing/tests.py#L89).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_inactive_requester_is_denied --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(PermissionDenied)`

### AUT-4A73E12323 — `purchasing.tests.PurchaseDraftTests.test_interface_line_creation_edit_and_cancellation`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:121](../purchasing/tests.py#L121).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_interface_line_creation_edit_and_cancellation --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(result.status_code, 302)`
- `self.assertContains(detail, "6,80")`
- `self.assertNotContains(detail, "6,801531")`
- `self.assertEqual(stale.status_code, 409)`
- `self.assertEqual(self.request.lines.count(), 1)`
- `self.assertEqual(self.client.get(f"/achats/{self.request.pk}/annuler/").status_code, 200)`
- `self.assertEqual(self.request.status, "DRAFT")`
- `self.assertEqual(self.client.post(f"/achats/{self.request.pk}/annuler/", {"expected_revision": 2}).status_code, 302)`
- `self.assertNotContains(self.client.get(f"/achats/{self.request.pk}/"), "Ajouter une ligne")`

### AUT-ADCF12DF50 — `purchasing.tests.PurchaseDraftTests.test_line_edit_and_delete_are_audited`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:100](../purchasing/tests.py#L100).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_line_edit_and_delete_are_audited --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(edited.quantity, 2)`
- `self.assertFalse(self.request.lines.exists())`
- `self.assertEqual(event.action, "line.deleted")`
- `self.assertEqual(event.payload["quantity"], "2.00")`

### AUT-8BA2502CBF — `purchasing.tests.PurchaseDraftTests.test_numbers_are_generated_and_unique`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:95](../purchasing/tests.py#L95).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_numbers_are_generated_and_unique --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertNotEqual(other.number, self.request.number)`
- `self.assertRegex(other.number, r"^DA-\d{4}-\d{4,}$")`

### AUT-5F26FE4B0E — `purchasing.tests.PurchaseDraftTests.test_pages_are_private_even_when_ids_are_known`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:112](../purchasing/tests.py#L112).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_pages_are_private_even_when_ids_are_known --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(self.client.get("/achats/"), reverse("my_validations"))`
- `self.assertNotContains(self.client.get("/achats/", follow=True), self.request.number)`
- `self.assertEqual(self.client.get(path).status_code, 404)`
- `self.assertIn(self.client.post(path, {"expected_revision": 1}).status_code, (404, 405))`

### AUT-3E63CA402E — `purchasing.tests.PurchaseDraftTests.test_stale_revision_is_rejected_without_side_effects`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:53](../purchasing/tests.py#L53).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_stale_revision_is_rejected_without_side_effects --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.request.lines.count(), 1)`
- `self.assertEqual(AuditEvent.objects.count(), 2)`
- `self.assertRaises(PurchaseRequestConflict)`

### AUT-C7D68A3395 — `purchasing.tests.PurchaseDraftTests.test_validation_and_audit_rollback`

Type : Intégration Django / service / HTTP. Source : [purchasing/tests.py:60](../purchasing/tests.py#L60).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.tests.PurchaseDraftTests.test_validation_and_audit_rollback --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.request.revision, 1)`
- `self.assertFalse(self.request.lines.exists())`
- `self.assertEqual(AuditEvent.objects.count(), 1)`
- `self.assertRaises(ValidationError)`

### AUT-81BFF2D916 — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_cannot_receive_more_than_ordered_and_does_not_write_anything`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:63](../receiving/test_purchase_receipts.py#L63).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_cannot_receive_more_than_ordered_and_does_not_write_anything --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(PurchaseReceipt.objects.count(), 1)`
- `self.assertEqual(StockMovement.objects.count(), 1)`
- `self.assertEqual(StockBalance.objects.get().quantity, 4)`
- `self.assertRaises(ValidationError)`

### AUT-7534C93D85 — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_idempotency_and_conflicting_replay`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:71](../receiving/test_purchase_receipts.py#L71).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_idempotency_and_conflicting_replay --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.receive("5", token=token).pk, receipt.pk)`
- `self.assertEqual(StockBalance.objects.get().quantity, 5)`
- `self.assertEqual(PurchaseReceipt.objects.count(), 1)`
- `self.assertRaises(ValidationError)`

### AUT-72B6762C1D — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_immutable_receipt_and_receipt_line`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:151](../receiving/test_purchase_receipts.py#L151).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_immutable_receipt_and_receipt_line --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-2E9244F3B5 — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_partial_then_complete_receipt_updates_stock_and_purchase_progress`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:48](../receiving/test_purchase_receipts.py#L48).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_partial_then_complete_receipt_updates_stock_and_purchase_progress --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "none")`
- `self.assertEqual(first.lines.get().movement.quantity, 2)`
- `self.assertEqual(StockBalance.objects.get(warehouse=self.warehouse, product=self.detail).quantity, 2)`
- `self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "partial")`
- `self.assertEqual(self.line.received_quantity, 2)`
- `self.assertEqual(self.line.remaining_quantity, 3)`
- `self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "complete")`
- `self.assertEqual(self.purchase.audit_events.filter(action="stock.purchase_receipt").count(), 2)`
- `self.assertEqual(self.purchase.status, "ORDERED")`

### AUT-8258527B7C — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_permission_state_foreign_lines_zero_and_negative_quantities`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:80](../receiving/test_purchase_receipts.py#L80).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_permission_state_foreign_lines_zero_and_negative_quantities --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(PurchaseReceipt.objects.exists())`
- `self.assertFalse(StockMovement.objects.exists())`
- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-0325C37B6E — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_receipt_is_atomic_if_a_stock_write_fails`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:93](../receiving/test_purchase_receipts.py#L93).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_receipt_is_atomic_if_a_stock_write_fails --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(PurchaseReceipt.objects.exists())`
- `self.assertFalse(StockMovement.objects.exists())`
- `self.assertFalse(StockBalance.objects.exists())`
- `self.assertRaises(ValidationError)`

### AUT-249554826D — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_requester_sees_received_quantities_and_receipt_history`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:140](../receiving/test_purchase_receipts.py#L140).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_requester_sees_received_quantities_and_receipt_history --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, "Partiellement réceptionnée")`
- `self.assertContains(response, "Réceptions liées à la demande")`
- `self.assertEqual(response.context["lines"][0].received_quantity, 2)`
- `self.assertEqual(response.context["lines"][0].remaining_quantity, 3)`
- `self.assertContains(self.client.get(reverse("purchasing:list")), "Partiellement réceptionnée")`
- `self.assertEqual(self.client.get(reverse("purchase_receipts")).status_code, 403)`

### AUT-7BDB8EC89F — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_stock_operations_without_receipt_do_not_change_purchase_fulfilment`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:113](../receiving/test_purchase_receipts.py#L113).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_stock_operations_without_receipt_do_not_change_purchase_fulfilment --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "none")`
- `self.assertEqual(purchase_progress([self.purchase])[0].receipt_status, "complete")`

### AUT-48676ED123 — `receiving.test_purchase_receipts.PurchaseReceiptTests.test_stock_user_can_receive_without_financial_permissions`

Type : Intégration Django / service / HTTP. Source : [receiving/test_purchase_receipts.py:122](../receiving/test_purchase_receipts.py#L122).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_purchase_receipts.PurchaseReceiptTests.test_stock_user_can_receive_without_financial_permissions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, self.purchase.number)`
- `self.assertContains(response, "Reste à recevoir")`
- `self.assertNotContains(response, "Prix HTVA")`
- `self.assertContains(response, "Partiellement réceptionnée")`
- `self.assertEqual(PurchaseReceipt.objects.count(), 1)`
- `self.assertEqual(PurchaseReceipt.objects.count(), 1)`
- `self.assertContains(self.client.get(reverse("stock_movements")), self.purchase.number)`

### AUT-1599BB362C — `receiving.test_stock.StockTests.test_http_movement_form_round_trip`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:80](../receiving/test_stock.py#L80).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_http_movement_form_round_trip --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.post(reverse("stock_movements"), data).status_code, 302)`
- `self.assertEqual(self.client.post(reverse("stock_movements"), data).status_code, 302)`
- `self.assertEqual(self.quantity(self.source), Decimal("2.5"))`

### AUT-DFC582C291 — `receiving.test_stock.StockTests.test_idempotency_and_conflicting_replay`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:51](../receiving/test_stock.py#L51).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_idempotency_and_conflicting_replay --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.move(token=token).pk, first.pk)`
- `self.assertEqual(self.quantity(self.source), 10)`
- `self.assertRaises(ValidationError)`

### AUT-C8BBCA7B62 — `receiving.test_stock.StockTests.test_insufficient_transfer_is_atomic`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:43](../receiving/test_stock.py#L43).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_insufficient_transfer_is_atomic --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.quantity(self.source), 10)`
- `self.assertFalse(StockBalance.objects.filter(warehouse=self.target).exists())`
- `self.assertEqual(StockMovement.objects.count(), 1)`
- `self.assertRaises(ValidationError)`

### AUT-E0CBE45986 — `receiving.test_stock.StockTests.test_invalid_quantities_or_depot_pairs_leave_no_writes`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:73](../receiving/test_stock.py#L73).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_invalid_quantities_or_depot_pairs_leave_no_writes --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertFalse(StockMovement.objects.exists())`
- `self.assertFalse(StockBalance.objects.exists())`
- `self.assertRaises(ValidationError)`

### AUT-DFE3F8792E — `receiving.test_stock.StockTests.test_permissions_and_movement_immutability`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:59](../receiving/test_stock.py#L59).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_permissions_and_movement_immutability --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.client.get(reverse("stock")).status_code, 403)`
- `self.assertContains(self.client.get(reverse("stock")), "Configuration des dépôts")`
- `self.assertRaises(PermissionDenied)`
- `self.assertRaises(ValidationError)`
- `self.assertRaises(ValidationError)`

### AUT-D4F084E159 — `receiving.test_stock.StockTests.test_receipt_issue_transfer_inventory_and_history`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:31](../receiving/test_stock.py#L31).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_receipt_issue_transfer_inventory_and_history --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.quantity(self.source), 5)`
- `self.assertEqual(self.quantity(self.target), 3)`
- `self.assertEqual(adjustment.delta, -1)`
- `self.assertEqual(self.quantity(self.source), 0)`
- `self.assertEqual(StockMovement.objects.count(), 5)`

### AUT-9F7AD77110 — `receiving.test_stock.StockTests.test_warehouse_only_permissions_expose_stock_section`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:124](../receiving/test_stock.py#L124).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_warehouse_only_permissions_expose_stock_section --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 200)`
- `self.assertEqual(response.context["nav_section"], "stock")`
- `self.assertContains(response, reverse("warehouses"))`
- `self.assertNotContains(response, "Nouveau dépôt")`
- `self.assertEqual(self.client.post(reverse("warehouses"), {"code": "C", "label": "C"}).status_code, 403)`
- `self.assertEqual(self.client.post(reverse("warehouse_edit", args=[self.source.pk]),         {"code": "A", "label": "Modifié"}).status_code, 302)`
- `self.assertEqual(self.client.get(reverse("stock")).status_code, 200)`
- `self.assertEqual(self.client.get(reverse("stock_movements")).status_code, 403)`
- `self.assertEqual(self.client.get(reverse("stock_balances")).status_code, 403)`

### AUT-E861745BA9 — `receiving.test_stock.StockTests.test_warehouse_read_only_and_write_permissions`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:111](../receiving/test_stock.py#L111).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_warehouse_read_only_and_write_permissions --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, self.source.code)`
- `self.assertNotContains(response, "Nouveau dépôt")`
- `self.assertEqual(self.client.post(reverse("warehouses"), {"code": "C", "label": "C"}).status_code, 403)`
- `self.assertEqual(self.client.post(reverse("warehouse_edit", args=[self.source.pk]),         {"code": "A", "label": "Modifié"}).status_code, 403)`
- `self.assertEqual(self.source.label, "A")`

### AUT-75CC00F62F — `receiving.test_stock.StockTests.test_warehouse_tab_creation_and_configuration`

Type : Intégration Django / service / HTTP. Source : [receiving/test_stock.py:89](../receiving/test_stock.py#L89).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock.StockTests.test_warehouse_tab_creation_and_configuration --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(response, reverse("warehouses"))`
- `self.assertContains(response, reverse("stock_movements"))`
- `self.assertContains(response, reverse("stock_balances"))`
- `self.assertNotContains(response, "<table")`
- `self.assertNotIn("form", response.context)`
- `self.assertNotContains(response, "<summary>")`
- `self.assertEqual(self.client.post(reverse("warehouses"), {"code": "C", "label": "Central"}).status_code, 302)`
- `self.assertEqual(self.client.post(reverse("warehouse_edit", args=[warehouse.pk]),         {"code": "CENT", "label": "Central principal"}).status_code, 302)`
- `self.assertEqual(warehouse.label, "Central principal")`
- `self.assertEqual(response.status_code, 200)`
- `self.assertTrue(response.context["form"].errors)`
- `self.assertEqual(warehouse.code, "CENT")`

### AUT-1140521744 — `suppliers.tests.SupplierManagementTests.test_create_edit_search_and_unique_code`

Type : Intégration Django / service / HTTP. Source : [suppliers/tests.py:31](../suppliers/tests.py#L31).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test suppliers.tests.SupplierManagementTests.test_create_edit_search_and_unique_code --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertRedirects(response, listing)`
- `self.assertIn("code", response.context["form"].errors)`
- `self.assertRedirects(self.client.post(edit, {"code": "F01", "name": "Beta", "vat_number": "BE123"}), listing)`
- `self.assertEqual(supplier.name, "Beta")`
- `self.assertContains(self.client.get(listing, {"q": "BE123"}), "Beta")`
- `self.assertNotContains(self.client.get(listing, {"q": "unmatched"}), "Beta")`
- `self.assertContains(response, 'href="' + listing + '"')`
- `self.assertEqual(response.context["nav_section"], "purchases")`

### AUT-4053453C61 — `suppliers.tests.SupplierManagementTests.test_permissions_are_checked_on_each_action`

Type : Intégration Django / service / HTTP. Source : [suppliers/tests.py:17](../suppliers/tests.py#L17).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test suppliers.tests.SupplierManagementTests.test_permissions_are_checked_on_each_action --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertContains(self.client.get(listing), "Alpha")`
- `self.assertEqual(supplier.name, "Alpha")`
- `self.assertEqual(self.client.get(url).status_code, 403)`
- `self.assertEqual(self.client.post(url, {"code": "X", "name": "Changed"}).status_code, 403)`

### AUT-268DF094F0 — `workflow.test_activity.IndependentHistoryTests.test_admin_deletes_requester_and_approvers_without_losing_order_or_log`

Type : Intégration Django / service / HTTP. Source : [workflow/test_activity.py:22](../workflow/test_activity.py#L22).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test workflow.test_activity.IndependentHistoryTests.test_admin_deletes_requester_and_approvers_without_losing_order_or_log --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(existing_logs)`
- `self.assertFalse(get_user_model().objects.filter(pk=owner_id).exists())`
- `self.assertIsNone(self.purchase.created_by_id)`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertEqual(BudgetEntry.objects.get().state, "committed")`
- `self.assertTrue(existing_logs.issubset(set(ActivityLog.objects.values_list("pk", flat=True))))`
- `self.assertEqual(ActivityLog.objects.filter(actor_identifier=str(owner_id)).first().actor_username, "owner")`
- `self.assertFalse(ApprovalStep.objects.filter(approved_by_id=first_id).exists())`
- `self.assertEqual(response.status_code, 200)`
- `self.assertTrue(all(row.actor_identifier == str(owner_id) for row in response.context["cl"].queryset))`
- `self.assertEqual(response.status_code, 200)`
- `self.assertTrue(any(event.actor_display == "owner" for event in response.context["events"]))`
- `self.assertEqual(response.status_code, 302)`

### AUT-9EE2CFE230 — `workflow.test_activity.IndependentHistoryTests.test_deleted_manager_can_be_replaced_and_notifications_become_obsolete`

Type : Intégration Django / service / HTTP. Source : [workflow/test_activity.py:117](../workflow/test_activity.py#L117).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test workflow.test_activity.IndependentHistoryTests.test_deleted_manager_can_be_replaced_and_notifications_become_obsolete --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIsNone(assignment.user_id)`
- `self.assertEqual(flow.pending_validation_count(self.other), 1)`
- `self.assertFalse(PurchaseNotice.objects.filter(recipient__isnull=True, email_state="pending").exists())`

### AUT-44A428661B — `workflow.test_activity.IndependentHistoryTests.test_deleted_named_approver_never_broadens_rule`

Type : Intégration Django / service / HTTP. Source : [workflow/test_activity.py:48](../workflow/test_activity.py#L48).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test workflow.test_activity.IndependentHistoryTests.test_deleted_named_approver_never_broadens_rule --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertIsNone(rule.named_user_id)`
- `self.assertIn("first", rule.named_user_reference)`
- `self.assertEqual(step.state, "unassigned")`
- `self.assertFalse(step.candidates.exists())`
- `self.assertIn("first", rule.named_user_reference)`

### AUT-A55F030A02 — `workflow.test_activity.IndependentHistoryTests.test_deleted_publisher_and_pending_candidate_can_be_removed`

Type : Intégration Django / service / HTTP. Source : [workflow/test_activity.py:77](../workflow/test_activity.py#L77).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test workflow.test_activity.IndependentHistoryTests.test_deleted_publisher_and_pending_candidate_can_be_removed --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(ApprovalStep.objects.get(level=1).state, "unassigned")`

### AUT-06BDE0D5FD — `workflow.test_activity.IndependentHistoryTests.test_deleted_requester_does_not_break_pending_workflow`

Type : Intégration Django / service / HTTP. Source : [workflow/test_activity.py:71](../workflow/test_activity.py#L71).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test workflow.test_activity.IndependentHistoryTests.test_deleted_requester_does_not_break_pending_workflow --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(PurchaseOrder.objects.count(), 1)`

### AUT-74B5E5B496 — `workflow.test_activity.IndependentHistoryTests.test_failed_transaction_does_not_leave_phantom_log`

Type : Intégration Django / service / HTTP. Source : [workflow/test_activity.py:107](../workflow/test_activity.py#L107).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test workflow.test_activity.IndependentHistoryTests.test_failed_transaction_does_not_leave_phantom_log --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(ActivityLog.objects.count(), before)`

### AUT-872D0B7A47 — `workflow.test_activity.IndependentHistoryTests.test_journal_is_read_only_and_no_secrets_are_logged`

Type : Intégration Django / service / HTTP. Source : [workflow/test_activity.py:84](../workflow/test_activity.py#L84).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test workflow.test_activity.IndependentHistoryTests.test_journal_is_read_only_and_no_secrets_are_logged --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(logs.exists())`
- `self.assertNotIn('"password"', str(list(logs.values_list("details", flat=True))))`
- `self.assertEqual(self.client.get(reverse("admin:workflow_activitylog_changelist")).status_code, 302)`
- `self.assertRaises(DatabaseError)`
- `self.assertRaises(DatabaseError)`

### AUT-AE8605BA9C — `workflow.test_activity.IndependentHistoryTests.test_user_deletion_requires_superuser_even_with_standard_permission`

Type : Intégration Django / service / HTTP. Source : [workflow/test_activity.py:98](../workflow/test_activity.py#L98).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test workflow.test_activity.IndependentHistoryTests.test_user_deletion_requires_superuser_even_with_standard_permission --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(response.status_code, 403)`
- `self.assertTrue(get_user_model().objects.filter(pk=self.owner.pk).exists())`

### AUT-08D8CC46A5 — `accounts.test_postgresql.PostgreSQLAuthorizationTests.test_queryset_cannot_rewrite_version`

Type : Acceptation PostgreSQL. Source : [accounts/test_postgresql.py:13](../accounts/test_postgresql.py#L13).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_postgresql.PostgreSQLAuthorizationTests.test_queryset_cannot_rewrite_version --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertTrue(version.enabled)`
- `self.assertRaises(DatabaseError)`

### AUT-1C31A0B39F — `budgeting.test_postgresql.PostgreSQLManagerTests.test_database_rejects_overlap_even_without_service`

Type : Acceptation PostgreSQL. Source : [budgeting/test_postgresql.py:21](../budgeting/test_postgresql.py#L21).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_postgresql.PostgreSQLManagerTests.test_database_rejects_overlap_even_without_service --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(IntegrityError)`

### AUT-3F48B111B5 — `budgeting.test_transfers_postgresql.ConcurrentTransferTests.test_concurrent_transfers_cannot_overdraw_source`

Type : Acceptation PostgreSQL. Source : [budgeting/test_transfers_postgresql.py:33](../budgeting/test_transfers_postgresql.py#L33).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test budgeting.test_transfers_postgresql.ConcurrentTransferTests.test_concurrent_transfers_cannot_overdraw_source --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertCountEqual(self.parallel([lambda: submit(self.transfer.pk), lambda: submit(other.pk)]), ["ok", "blocked"])`
- `self.assertEqual(self.balance(self.source), 40)`

### AUT-074F2E99BD — `purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_activation_and_reservation_share_annual_lock`

Type : Acceptation PostgreSQL. Source : [purchasing/test_flow_postgresql.py:109](../purchasing/test_flow_postgresql.py#L109).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_activation_and_reservation_share_annual_lock --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertIn("activated", result)`
- `self.assertEqual(self.envelope.active_version_id, new.pk)`
- `self.assertEqual(balance, -500 if "submitted" in result else 100)`

### AUT-27FEC76C40 — `purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_published_allocation_sql_writes_follow_admin_edit_state`

Type : Acceptation PostgreSQL. Source : [purchasing/test_flow_postgresql.py:24](../purchasing/test_flow_postgresql.py#L24).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_published_allocation_sql_writes_follow_admin_edit_state --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.budget.allocations.get().amount, Decimal("900"))`
- `self.assertRaises(DatabaseError)`
- `self.assertRaises(DatabaseError)`
- `self.assertRaises(DatabaseError)`

### AUT-98B59B7F86 — `purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_same_request_double_submission_does_not_duplicate_ledger`

Type : Acceptation PostgreSQL. Source : [purchasing/test_flow_postgresql.py:128](../purchasing/test_flow_postgresql.py#L128).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_same_request_double_submission_does_not_duplicate_ledger --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertCountEqual(self.parallel([submit, submit]), ["submitted", "blocked"])`
- `self.assertEqual(Submission.objects.count(), 1)`
- `self.assertEqual(BudgetEntry.objects.count(), 1)`

### AUT-3E055E28C6 — `purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_sql_guards_protect_published_configuration_and_history`

Type : Acceptation PostgreSQL. Source : [purchasing/test_flow_postgresql.py:138](../purchasing/test_flow_postgresql.py#L138).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_sql_guards_protect_published_configuration_and_history --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertRaises(DatabaseError)`

### AUT-BECD30FB6B — `purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_t001_t002_concurrent_reservations_do_not_overspend`

Type : Acceptation PostgreSQL. Source : [purchasing/test_flow_postgresql.py:83](../purchasing/test_flow_postgresql.py#L83).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_t001_t002_concurrent_reservations_do_not_overspend --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertCountEqual(result, ["submitted", "blocked"])`
- `self.assertEqual(BudgetEntry.objects.filter(state="reserved").count(), 1)`
- `self.assertEqual(flow.available(self.budget, self.cdf.pk, self.funding.pk, self.product.pk), 400)`

### AUT-5F8B4C8A93 — `purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_t005_simultaneous_manager_approval_creates_one_order`

Type : Acceptation PostgreSQL. Source : [purchasing/test_flow_postgresql.py:94](../purchasing/test_flow_postgresql.py#L94).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_t005_simultaneous_manager_approval_creates_one_order --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertCountEqual(result, ["approved", "blocked"])`
- `self.assertEqual(PurchaseOrder.objects.count(), 1)`
- `self.assertEqual(BudgetEntry.objects.filter(state="committed").count(), 1)`
- `self.assertEqual(ApprovalStep.objects.filter(state="approved", evidence__isnull=True).count(), 1)`

### AUT-6A429C7908 — `purchasing.test_numeric_units.AmountDisplayUnitTests.test_grouping_and_decimal_separator`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:29](../purchasing/test_numeric_units.py#L29).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.AmountDisplayUnitTests.test_grouping_and_decimal_separator --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(amount(Decimal("1234567.89")), "1.234.567,89")`

### AUT-9237DF8F21 — `purchasing.test_numeric_units.AmountDisplayUnitTests.test_negative_value_is_formatted`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:37](../purchasing/test_numeric_units.py#L37).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.AmountDisplayUnitTests.test_negative_value_is_formatted --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(amount(Decimal("-42.125")), "-42,13")`

### AUT-F5FD811D21 — `purchasing.test_numeric_units.AmountDisplayUnitTests.test_rounds_display_without_changing_decimal_value`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:32](../purchasing/test_numeric_units.py#L32).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.AmountDisplayUnitTests.test_rounds_display_without_changing_decimal_value --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(amount(value), "1.200,13")`
- `self.assertEqual(value, Decimal("1200.125"))`

### AUT-B6B92C91DF — `purchasing.test_numeric_units.AmountDisplayUnitTests.test_zero_is_not_lost`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:40](../purchasing/test_numeric_units.py#L40).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.AmountDisplayUnitTests.test_zero_is_not_lost --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(amount(Decimal("0")), "0")`

### AUT-73F122A03E — `purchasing.test_numeric_units.ImportNormalizationUnitTests.test_code_preserves_leading_zeroes_in_text`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:17](../purchasing/test_numeric_units.py#L17).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.ImportNormalizationUnitTests.test_code_preserves_leading_zeroes_in_text --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(_code(" 0012 "), "0012")`

### AUT-6EAA18B041 — `purchasing.test_numeric_units.ImportNormalizationUnitTests.test_code_rejects_boolean_as_reference`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:20](../purchasing/test_numeric_units.py#L20).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.ImportNormalizationUnitTests.test_code_rejects_boolean_as_reference --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(_code(True), "")`
- `self.assertEqual(_code(False), "")`

### AUT-E7FDE5975C — `purchasing.test_numeric_units.ImportNormalizationUnitTests.test_header_handles_missing_value`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:14](../purchasing/test_numeric_units.py#L14).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.ImportNormalizationUnitTests.test_header_handles_missing_value --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(_header(None), "")`

### AUT-FFC1882652 — `purchasing.test_numeric_units.ImportNormalizationUnitTests.test_header_normalizes_accents_spacing_and_case`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:11](../purchasing/test_numeric_units.py#L11).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.ImportNormalizationUnitTests.test_header_normalizes_accents_spacing_and_case --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(_header("  Montánt   TVAC "), "MONTANT TVAC")`

### AUT-921BC8F618 — `purchasing.test_numeric_units.ImportNormalizationUnitTests.test_numeric_code_converts_integral_float_without_suffix`

Type : Unitaire pur sans DB. Source : [purchasing/test_numeric_units.py:24](../purchasing/test_numeric_units.py#L24).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test purchasing.test_numeric_units.ImportNormalizationUnitTests.test_numeric_code_converts_integral_float_without_suffix --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(_code(12.0), "12")`

### AUT-F4B1ECDA90 — `receiving.test_progress_unit.ReceiptProgressUnitTests.test_exact_receipt_is_complete`

Type : Unitaire pur sans DB. Source : [receiving/test_progress_unit.py:16](../receiving/test_progress_unit.py#L16).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_progress_unit.ReceiptProgressUnitTests.test_exact_receipt_is_complete --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(receipt_label(Decimal("10"), Decimal("10")), ("complete", "Réceptionnée"))`

### AUT-DDF52F5B30 — `receiving.test_progress_unit.ReceiptProgressUnitTests.test_no_receipt_is_distinct_from_completion`

Type : Unitaire pur sans DB. Source : [receiving/test_progress_unit.py:10](../receiving/test_progress_unit.py#L10).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_progress_unit.ReceiptProgressUnitTests.test_no_receipt_is_distinct_from_completion --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(receipt_label(Decimal("10"), Decimal("0")), ("none", "Non réceptionnée"))`

### AUT-DB3CC1119E — `receiving.test_progress_unit.ReceiptProgressUnitTests.test_partial_receipt_is_identified`

Type : Unitaire pur sans DB. Source : [receiving/test_progress_unit.py:13](../receiving/test_progress_unit.py#L13).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_progress_unit.ReceiptProgressUnitTests.test_partial_receipt_is_identified --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(receipt_label(Decimal("10"), Decimal("4")), ("partial", "Partiellement réceptionnée"))`

### AUT-E17B077640 — `receiving.test_progress_unit.ReceiptProgressUnitTests.test_zero_order_does_not_appear_complete`

Type : Unitaire pur sans DB. Source : [receiving/test_progress_unit.py:19](../receiving/test_progress_unit.py#L19).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_progress_unit.ReceiptProgressUnitTests.test_zero_order_does_not_appear_complete --settings=config.test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(receipt_label(Decimal("0"), Decimal("0")), ("none", "Non réceptionnée"))`

### AUT-C624269B0D — `receiving.test_stock_postgresql.ConcurrentStockTests.test_concurrent_issues_cannot_overdraw_stock`

Type : Acceptation PostgreSQL. Source : [receiving/test_stock_postgresql.py:20](../receiving/test_stock_postgresql.py#L20).

Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.

```powershell
.venv\Scripts\python.exe manage.py test receiving.test_stock_postgresql.ConcurrentStockTests.test_concurrent_issues_cannot_overdraw_stock --settings=config.postgresql_test_settings --noinput
```

Attendus contractuels :

- `self.assertEqual(self.quantity(self.source), 4)`
- `self.assertEqual(StockMovement.objects.count(), 2)`
- `self.assertCountEqual(list(executor.map(issue, range(2))), ["ok", "blocked"])`