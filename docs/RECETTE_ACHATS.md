# Recette du flux d’achat — DA jusqu’au bon de commande

> Vue d’ensemble : [Synthèse de l’application](SYNTHESE_APPLICATION.md).
>
> Pour la campagne complète depuis une base vierge, suivre désormais
> [le plan de recette complet](RECETTE_COMPLETE.md) : création des comptes et
> rôles, référentiels, budget, circuit de validation et tests par profil.
> Le présent document conserve les anciennes indications de démonstration ;
> en cas de divergence, utiliser le nouveau plan.

> État local au 19 octobre 2026 : la base de recette a été vidée à la demande
> de l’utilisateur. Seul `demo.admin` est conservé, avec son mot de passe existant.
> Les référentiels, budgets, demandes et autres comptes sont à créer manuellement.
> La sauvegarde préalable est conservée dans `.venv/backups/`.
> Les comptes et exemples décrits ci-dessous concernent le jeu optionnel
> `seed_purchase_demo`, qui n’est plus chargé automatiquement au démarrage.

Pour créer les comptes de test : connexion avec `demo.admin`, puis
**Configuration → Utilisateurs → Ajouter**. Enregistrer le compte, puis attribuer
ses groupes ou ses permissions dans sa fiche. Le statut **Actif** permet la
connexion ; le statut **Équipe** n’est nécessaire que pour accéder à
l’administration Django. Les permissions peuvent aussi être réunies dans
**Configuration → Groupes**, puis attribuées aux utilisateurs via ces groupes.

## Navigation par onglets

Les groupes Django ont été retirés des interfaces de configuration et des fiches
utilisateurs. Pour regrouper les droits, utiliser désormais **Configuration →
Rôles ERP**, puis attribuer les rôles aux utilisateurs. Les mentions de groupes
dans les anciens parcours ci-dessous ne correspondent plus à l’interface actuelle.

### Validations par rôle ERP

1. Avec l’administrateur, ouvrir **Configuration → Rôles ERP** et créer un rôle
   (code et libellé), par exemple `VALID_ACHATS`.
2. Dans **Configuration → Comptes utilisateurs et droits individuels**, ouvrir
   un compte et lui attribuer ce rôle dans la rubrique **ERP → Roles**.
3. Ouvrir l’administration technique, **Configurations des validations**. Créer
   une configuration brouillon et une règle avec sa fonction, son niveau, ses
   critères éventuels et son **Rôle valideur**. Laisser utilisateur nommé et
   responsable CDF vides. Publier la configuration avec l’action d’activation.
4. À la soumission d’une DA, les membres actifs du rôle deviennent candidats.
   Ils traitent l’étape depuis **Achats → Mes validations** ; la première décision
   clôt l’étape. Ce mode n’exige pas une habilitation individuelle supplémentaire.

Le rôle est vérifié de nouveau à chaque décision, y compris lors d’une délégation.
Le retrait du rôle interdit donc de nouvelles décisions. Le rôle utilisé et
l’utilisateur représenté sont conservés dans la preuve. La liste des candidats
est figée à la soumission : attribuer un rôle à un nouveau membre ne réaffecte pas
les étapes existantes ; une réaffectation explicite par un administrateur habilité
permet de les lui confier. Un rôle sans membre laisse l’étape à affecter.
Les modes existants par habilitation individuelle et responsable CDF sont conservés.

Le lien **Achats → Toutes les demandes** exige la permission
`purchasing.view_all_purchase_requests` (« Consulter toutes les demandes d’achat »),
attribuable dans **Configuration → Comptes utilisateurs et droits individuels**
ou **Groupes et permissions**. Elle permet de consulter toutes les DA, leurs
détails (y compris les montants) et leurs bons de commande. Elle ne donne aucun
droit de modifier, annuler ou soumettre les demandes des autres utilisateurs.
**Mes demandes** reste limité aux demandes créées par le compte connecté.

- **Achats** : demandes, validations, délégations, suivi et **Produits détaillés**
  selon les permissions. Cette dernière page permet la création et la liste des produits détaillés, avec leur BI.
  Droit requis : `purchasing.add_detailedproduct`, attribuable directement ou par groupe.
- **Budget** : pages **Créer une version**, **Alimenter une version** (sélection de
  la version puis saisie des lignes), **Produits budgétaires**, et disponibilités.
  Chaque action conserve ses permissions existantes. La consultation via le
  bouton **Vérifier un budget** reste accessible aux utilisateurs connectés.
- **Configuration** : comptes et droits individuels, groupes et permissions,
  rôles ERP, habilitations, responsables CDF et administration technique. Les
  liens de gestion des comptes, groupes et rôles ouvrent les écrans Django
  existants ; ils nécessitent le statut équipe et les permissions correspondantes.

Les groupes Django et les rôles ERP permettent d’attribuer des permissions à leurs membres.
Dans **Configuration → Rôles ERP**, choisir les **Permissions** du rôle, puis
affecter ce rôle aux utilisateurs dans leur fiche (rubrique **ERP**). Les droits
directs, ceux des groupes et ceux des rôles se cumulent. Le retrait du rôle ou
d’une de ses permissions est pris en compte à la requête suivante. Le statut
équipe reste requis pour l’administration Django.

## Démarrage immédiat sur ce poste

Depuis `D:\Projets\BF-ERP` :

```powershell
.\demarrer-recette.cmd
```

Le lanceur applique les migrations à **db.demo.sqlite3**, puis démarre le serveur.
Il ne recrée plus automatiquement les comptes et données de démonstration et ne
modifie pas la base PostgreSQL configurée dans `.env`.
Pour réinstaller volontairement le jeu de démonstration, exécuter
`.\.venv\Scripts\python.exe manage.py seed_purchase_demo --settings=config.demo_settings`.

Ouvrir <http://127.0.0.1:8000/connexion/>. Arrêter avec Ctrl+C.

L’environnement `.venv`, la base de démonstration, les référentiels et une DA brouillon de deux lignes ont été préparés sur ce poste. Ces fichiers locaux ne sont pas versionnés. Après un nouveau clonage, préparer l’environnement :

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
.\demarrer-recette.cmd
```

Équivalent si l’on veut lancer uniquement le serveur après préparation :

```powershell
.\.venv\Scripts\python.exe manage.py runserver --settings=config.demo_settings
```

## Comptes de démonstration

Le compte `demo.budget` permet de gérer les versions via **Gestion des budgets**,
avec le même mot de passe initial que les autres comptes. Relancer
la commande `seed_purchase_demo --settings=config.demo_settings` via `manage.py`
pour créer ce compte sans réinitialiser les données.

### Parcours gestionnaire budget

**Produits budgétaires** dans le menu permet de créer un BI avec un code unique
et un libellé. Ce menu et sa route exigent `budgeting.add_budgetproduct`, attribué
à `demo.budget`. Un produit créé devient disponible dans la saisie des allocations.

Pour attribuer ce droit à un autre compte : se connecter comme `demo.admin`,
ouvrir **Configuration → Utilisateurs**, choisir le compte, puis ajouter la
permission **Budgets | produit budgétaire (BI) | Ajouter : produit budgétaire (BI)** dans
**Permissions de l’utilisateur** et enregistrer. Le compte bénéficiaire n’a pas
besoin du statut équipe ni superutilisateur. Le droit peut aussi être accordé à un
groupe via **Configuration → Groupes**, puis hérité par ses membres. Retirer ce
droit supprime l’accès, à condition qu’aucun groupe ne l’accorde encore.
Les permissions de gestion des versions, décrites ci-dessous, s’attribuent de la
même manière. Les habilitations de validation des achats sont distinctes de ces droits.

1. Se connecter avec `demo.budget` et ouvrir **Gestion des budgets**.
2. Saisir l’année et le nom de la version, puis **Créer le brouillon**.
3. Saisir les lignes **BI / produit budgétaire – CDF – financement – montant TVAC**.
   Les référentiels sont ceux configurés dans l’application. Une combinaison ne peut
   apparaître qu’une fois dans une version ; les montants négatifs sont refusés.
4. **Enregistrer les lignes**. Les lignes existantes restent modifiables et peuvent
   être supprimées dans le brouillon ; trois lignes vides permettent de continuer la saisie.
5. Après enregistrement, cliquer **Publier et activer cette version**. La version
   devient immuable et remplace la version active de la même année. Saisir les
   allocations totales, et non des variations par rapport à la version précédente.
   Les réservations et engagements existants restent déduits du disponible.

Les droits requis sont `add_annualenvelope`, `add_envelopeversion`,
`change_envelopeversion`, `add_allocation`, `change_allocation`,
`delete_allocation` dans l’application `budgeting`. Le compte de démonstration
dispose aussi de `budgeting.view_budget_balances` pour consulter les disponibilités.
Il n’a pas besoin d’accès à l’administration Django.

Mot de passe initial commun : **TestAchats!2026**.

| Compte | Usage |
|---|---|
| `demo.demandeur` | Créer, compléter, soumettre, corriger ou annuler ses DA ; consulter ses commandes |
| `demo.cdf` | Approuver les lignes au niveau 1, responsable CDF |
| `demo.finance` | Approuver les lignes au niveau 2, Finance |
| `demo.admin` | Suivi, réaffectation, habilitations, référentiels, budgets et règles dans `/admin/` |
| `demo.suivi` | Suivi opérationnel uniquement, sans fournisseur, description commerciale, montant ni accès aux budgets |

Ces comptes sont destinés uniquement à la base locale de démonstration. `seed_purchase_demo` refuse de s’exécuter avec les paramètres habituels PostgreSQL. Réexécuter la commande ne réinitialise ni les mots de passe existants ni les DA traitées. Pour d’autres mots de passe initiaux, utiliser `--password` à la première création.

Les règles et montants préchargés sont des **données fictives de recette**, pas des décisions métier : budget annuel de 10 000 EUR TVAC, deux niveaux CDF puis Finance, TVA 21 % saisie dans les deux lignes du brouillon d’exemple.

## Parcours nominal

1. Se connecter comme `demo.demandeur`. Ouvrir la DA brouillon existante ou créer une nouvelle DA avec le fournisseur fictif. Ajouter des lignes en choisissant produit, CDF, financement, quantité, prix et taux TVA explicite.
2. Cliquer **Soumettre pour validation**, puis confirmer. Les deux lignes préchargées font au total 100 EUR HTVA et 121 EUR TVAC. Toute la DA est soumise et 121 EUR sont réservés.
3. Se déconnecter puis entrer comme `demo.cdf`. Ouvrir **Mes validations**. Le lien du numéro de DA donne accès aux détails grâce au droit financier distinct attribué à ce compte de recette. Cliquer **Traiter** puis **Approuver** pour chaque ligne.
4. Se connecter comme `demo.finance`. Les étapes du niveau 2 ne deviennent accessibles que lorsque le niveau 1 de leur ligne est terminé. Approuver chaque ligne.
5. Revenir comme demandeur. La DA est **Commandée**. Ouvrir **Ouvrir / imprimer le bon de commande** ; le navigateur permet l’impression ou l’enregistrement PDF.
6. Comme administrateur, ouvrir **Budgets et disponibilités**. Les 121 EUR sont engagés et ne sont plus réservés. Le disponible reste 9 879 EUR, sans deuxième déduction.

Le bon conserve les données du fournisseur et des lignes figées à la soumission. Modifier ultérieurement un libellé du référentiel ne réécrit pas ce document.

## Autres essais

| Essai | Manipulation | Attendu |
|---|---|---|
| Budget insuffisant | Nouvelle DA de 20 000 EUR HTVA sur la combinaison de démonstration | Erreur explicite ; brouillon conservé ; aucune réservation |
| Correction | Depuis une étape accessible, choisir retour pour correction et fournir un motif | Toute la DA revient au demandeur ; toutes les réservations sont libérées ; décisions précédentes conservées mais invalidées pour le nouveau cycle |
| Nouvelle soumission | Modifier/ajouter/supprimer une ligne après correction puis soumettre | Nouveau workflow selon les règles et habilitations courantes ; nouvel historique séparé |
| Rejet | Choisir rejet définitif avec motif | DA non modifiable et non resoumettable ; budget libéré |
| Annulation | Le demandeur annule une DA avant création de commande | Workflow arrêté ; réservations libérées |
| Habilitation retirée | Admin : désactiver par nouvelle version l’habilitation CDF avant sa décision | À l’actualisation des validations ou au passage du traitement périodique : étape bloquée, anomalie visible au suivi et notifications aux acteurs concernés ; aucune perte des réservations |
| Habilitation rétablie | Republier une version active pour l’utilisateur encore affecté | Étape débloquée ; aucune approbation implicite sans preuve manuelle antérieure |
| Réaffectation | Admin : **Suivi administrateur**, réaffecter une étape accessible avec justification | Utilisateur actif et habilité à la même fonction/périmètre exigé ; tâches mises à jour sans redémarrage |
| Délégation | Valideur : **Mes délégations**, période englobant maintenant et délégué actif | Délégation globale ; le délégué traite les étapes au nom du titulaire, avec preuve de l’acteur réel |
| Confidentialité | Connexion `demo.suivi` puis suivi ; essayer les URL de détails et budgets | Données opérationnelles seulement ; accès financier refusé côté serveur |

Les délégations en chaîne et les délégations sortantes chevauchantes sont refusées explicitement ; leur composition n’est pas inventée. Le changement de responsable CDF ne réaffecte pas les workflows déjà soumis.

## Interface administrateur

Menu **Configuration**, ou <http://127.0.0.1:8000/admin/> avec `demo.admin`.

- **Enveloppes budgétaires annuelles** : une enveloppe par année. La soumission utilise l’année civile courante, hypothèse technique isolée dans `submit_purchase` ; aucune règle de clôture annuelle n’est implémentée.
- **Versions budgétaires achats** : créer une version et ses allocations produit budgétaire × CDF × financement en TVAC ; enregistrer puis, dans la liste, sélectionner la version et l’action **Publier et activer**. Une seule version active par enveloppe. Les écritures ouvertes des versions précédentes restent déduites.
- **Configurations des validations** : créer une version et ses règles ; enregistrer puis sélectionner l’action **Valider et activer**. Configuration publiée immuable ; utiliser **Copier en nouvelle configuration brouillon** pour la modifier.
- Une règle précise sa fonction, son niveau, ses critères facultatifs, ses seuils HTVA sur le **total de la DA**, son mode cumulatif/exclusif et sa priorité. Le maximum HTVA est exclusif. Les niveaux suivent l’ordre global des fonctions. Les critères non financiers sont évalués par ligne.
- Affectation : utilisateur nommé, responsable CDF actif, ou ensemble des utilisateurs habilités à la fonction. La première approbation clôt l’étape ; être superutilisateur ne remplace pas une habilitation métier.
- **Habilitations** et **Responsables CDF** dans la navigation applicative publient les changements historisés. Les écrans d’administration des demandes, étapes, écritures et commandes sont en consultation.
- L’activation d’une version déficitaire est autorisée et le déficit apparaît au tableau budgétaire, y compris pour une combinaison retirée de la nouvelle version ; les nouvelles réservations y sont bloquées. Les réservations existantes peuvent être converties.

Les anciennes tables `budgeting.Budget`/`BudgetLine` restent présentes pour préserver les données historiques. Elles ne pilotent pas ce flux et leurs compteurs ne sont pas importés automatiquement. Pour la recette, utiliser les **Versions budgétaires achats**.

Permissions séparées : `purchasing.monitor_purchases`, `purchasing.reassign_approvals`, `purchasing.view_purchase_financial`. Le droit financier donne ici une lecture globale ; une restriction financière par périmètre reste à cadrer avant un déploiement réel. Les brouillons ne sont modifiables que par leur demandeur.

## Notifications

Les événements de validation produisent des notifications internes et une file de courriels durable. En démonstration, les courriels sont affichés en console. Une panne de courriel n’annule jamais une décision.

```powershell
.\.venv\Scripts\python.exe manage.py process_purchase_notifications --settings=config.demo_settings
```

Cette commande actualise aussi les états d’habilitation. Pour une actualisation sans visite des écrans, l’exécuter périodiquement via le planificateur. Les paramètres de tentatives et délais sont configurables. Aucun rappel n’est envoyé en fonction de l’ancienneté seule.

Les notifications devenues obsolètes sont retirées et ne sont pas expédiées. Le traitement ne garantit pas une livraison SMTP exactement une fois en cas d’arrêt entre envoi et confirmation en base. Après un échec permanent, `--recover` réexamine les messages encore pertinents : l’automatisation complète de la reprise NOT-003 et l’alerte dédiée à l’exploitation NOT-002 restent à compléter avant exploitation.

## Vérifications et périmètre

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py check --settings=config.demo_settings
```

Les tests de concurrence et protections SQL nécessitent PostgreSQL. Des paramètres séparés existent dans `config.postgresql_test_settings`, avec variables `TEST_PG_DATABASE`, `TEST_PG_USER`, `TEST_PG_PASSWORD`, `TEST_PG_HOST`, `TEST_PG_PORT`. Ils créent une base `test_<nom>` et la suppriment après les tests. Ils ne doivent jamais pointer vers une base de production nommée comme base de tests.

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.postgresql_test_settings
```

Une instance PostgreSQL 18 temporaire a servi à vérifier 63 tests, y compris T-005 et les réservations concurrentes. Cette instance de vérification a été arrêtée après les tests ; pour les rejouer, fournir une instance PostgreSQL disponible avec les paramètres ci-dessus. SQLite sert à la recette manuelle sur un poste et ne démontre pas les garanties de concurrence PostgreSQL. Les triggers d’historique immuable sont installés uniquement sur PostgreSQL.

Couverture de cet incrément : flux ACH brouillon/soumission/validation par ligne/niveaux/correction/rejet/annulation/commande, seuils HTVA globaux, snapshots, déduplication, délégation simple, réaffectation ; BUD-001/002/003/005/006/007 et maintien des écritures à travers les versions ; HAB-001/002/003 et blocage/déblocage ; suivi opérationnel SUI-001/002. Tests explicites T-001 à T-008 dans le périmètre de ce flux et contrôle de confidentialité.

Ce livrable permet la **recette du parcours DA → commande**, pas la recette de toute la spécification ERP. Restent notamment les régularisations d’engagement, annulation de commande, avenants TVA, ajustements approuvés, alertes de déficit automatiques BUD-019/020/021, réceptions/factures, exports SUI-003 et suivants, archivage des notifications informatives, et durcissement d’exploitation. L’ERP n’est pas présenté comme prêt pour la production. Aucune règle de comptabilité, stock ou vente n’a été inventée.
