# Transferts budgétaires, validations et stock

> Mise à jour : les nouveaux transferts utilisent un parcours fixe : responsable
> du CDF source, puis responsable du CDF destination. Aucune règle ni publication
> n’est nécessaire. Chaque étape exige une décision distincte. Les responsables
> se renseignent dans Configuration → Responsables des CDF et des supports.
> Une étape sans responsable actif reste « À affecter ». Les demandes d’achat
> exigent une validation par ligne, par le responsable du CDF de cette ligne.

Lot développé le 9 novembre 2026. Il complète les achats existants ; les réceptions
de commandes, la facturation et la comptabilité restent des lots distincts.

## Affectation des validations

Dans **Configuration → Responsables des CDF et des supports**, renseigner les
responsables de chaque CDF. Aucun circuit ni règle n’est à créer ou à publier.
Les transferts exigent deux décisions successives : CDF source, puis CDF
destination. Les demandes d’achat exigent une décision distincte pour chaque
ligne, par le responsable du CDF de cette ligne.

Les responsables doivent être actifs ; leurs affectations sont contrôlées à
chaque décision. Sans responsable actif, une étape reste **À affecter**, jamais
approuvée automatiquement. Les étapes déjà soumises gardent leur ancien parcours
et leurs décisions. Les délégations d’achat ne sont pas étendues aux transferts.
Voir [Validations](REGLES_VALIDATION.md) pour les détails et les cas de recette.

## Transferts budgétaires

Accès : **Budget → Transferts budgétaires** (`/budget/transferts/`).

Le demandeur choisit directement une **version budgétaire** dans le formulaire. Il n’y a plus
d’enveloppe à configurer ni d’autorisation nominative préalable ; le droit de création reste nécessaire.
L’année est déduite de la version choisie. Les versions bloquées ou supprimées ne peuvent pas recevoir
de nouveaux transferts. Les versions en brouillon et publiées restent sélectionnables si elles ne sont pas bloquées.
Les allocations doivent être suffisantes dans la version choisie. Les deux étapes de validation sont créées à la soumission.

Permissions à attribuer dans les rôles ERP :

| Permission | Usage |
|---|---|
| `budgeting.add_budgettransfer` | Créer, soumettre et annuler ses transferts |
| `budgeting.view_all_transfers` | Consulter tous les transferts |
| Permissions existantes de configuration des workflows/règles | Configurer et publier les circuits |

Les valideurs accèdent à leurs tâches par **Mes validations**, sans devoir posséder
les droits de création ou de lecture globale. Le compteur inclut les étapes de
transfert actuellement traitables. Pas d’envoi de courriel dédié aux transferts dans ce lot.

1. Créer un brouillon avec les combinaisons source/destination, un montant
   positif et une justification. Les deux combinaisons doivent être différentes.
2. Soumettre : le budget de la version choisie doit être suffisant ; un circuit applicable doit
   être publié. Le montant est réservé à la source, sans crédit à destination.
3. Valider les étapes dans l’ordre. À l’approbation finale, le crédit destination
   devient disponible. Le débit source n’est pas déduit une seconde fois.
4. Rejeter avec motif ou annuler comme demandeur avant approbation finale libère
   la réservation. Le demandeur ne peut pas annuler un transfert approuvé.
   Un utilisateur disposant du droit d’annulation globale peut l’annuler avec motif,
   si les fonds à destination restent disponibles. Pour corriger un brouillon, l’annuler puis le recréer.

### Suivi et annulation

**Budget → Suivi de tous les transferts** affiche toutes les demandes, avec filtres par année, version et état.
Le droit `budgeting.view_all_transfers` donne la consultation ; le droit
`budgeting.cancel_any_budgettransfer` permet aussi l’annulation des brouillons, demandes en validation
et transferts approuvés de tout demandeur. Le superadministrateur possède ces droits.
L’annulation exige un motif et conserve la demande et ses événements. L’action vérifie la révision,
verrouille l’enveloppe annuelle et refuse de reprendre des fonds déjà réservés ou engagés à destination.
Un transfert annulé ou rejeté ne peut pas être annulé une seconde fois.

### Historique des versions budgétaires

**Budget → Historique des versions budgétaires** permet de choisir une version, une date et une heure,
ou un événement de sa chronologie. Les états figés comprennent le statut de la version, les allocations,
réservations, engagements, soldes des transferts et disponibilités par CDF/financement/BI.
L’accès requiert la consultation des disponibilités, la consultation des versions ou les droits de gestion budgétaire.
Les changements d’allocations, publications, remplacements, mouvements d’achat et transferts sont enregistrés
dans leur transaction ; une opération annulée par rollback ne laisse aucun état historique.
Les suppressions de maintenance enregistrent aussi l’état des enveloppes restantes après opération.

La migration initialise un état daté pour les enveloppes existantes. Aucun état antérieur n’est inventé.
La commande idempotente `initialize_budget_history` permet de relancer cette initialisation si nécessaire.
Les modifications directes par SQL ou scripts utilisant des mises à jour en masse hors des services applicatifs
ne sont pas historisées automatiquement. Il n’existe pas de version spéciale de transferts.

Les transferts sont attachés à une version et n’affectent pas les autres versions, même pour la même année.
La création d’une autre version ou son activation ne déplace pas les transferts existants.
Depuis le détail d’une version, **Historique des transferts de cette version** donne les demandes et leur
chronologie (création, soumission, validations, rejet, annulation), avec un export Excel dédié.
Les utilisateurs sans droit de lecture budgétaire globale ne voient que leurs propres transferts.
Les événements sont aussi présents dans l’historique budgétaire daté de la version concernée ;
les événements spécifiques à une autre version n’y sont pas mélangés.
Les anciennes captures historiques sont conservées telles qu’enregistrées. La migration rattache les anciens
transferts à l’ancienne version active, ou à l’unique version de l’année ; si ce rattachement est ambigu,
elle exige une décision explicite au lieu d’affecter arbitrairement une version.

## Stock

Accès : **Stocks** (`/stocks/`).

L’accueil reprend les zones d’action de Budget : **Configuration des dépôts**, **Mouvements de stock**
et **Consulter les stocks**, selon les droits de l’utilisateur. Les formulaires et tableaux sont sur les
pages dédiées `/stocks/depots/`, `/stocks/mouvements/` et `/stocks/quantites/`.

| Permission | Usage |
|---|---|
| `receiving.view_stockbalance` | Consulter les quantités et l’historique |
| `receiving.manage_stock` | Consulter et enregistrer les mouvements/inventaires |
| `receiving.add_warehouse` | Créer les dépôts depuis la page stock, avec un des droits d’accès ci-dessus |

Les articles sont les produits détaillés existants. Conserver une seule unité de
référence par produit ; les quantités acceptent quatre décimales. Pas de conversion
d’unités, de valorisation, de lots/séries ou de raccord automatique aux commandes.

- **Entrée** : augmente la quantité du dépôt.
- **Sortie** : diminue la quantité ; stock négatif refusé.
- **Transfert** : débite le dépôt source et crédite le dépôt destination atomiquement.
- **Inventaire** : saisir la quantité réellement comptée, y compris zéro. Le mouvement
  conserve la quantité comptée et l’écart avec le stock au moment de l’enregistrement.

Chaque mouvement exige une justification ou référence. Il conserve sa date et son
auteur et n’est pas modifiable via les services métier. Corriger par un nouveau
mouvement justifié. Le formulaire déduplique une double soumission ; réutiliser
son identifiant avec un contenu différent est refusé. L’écran affiche les 200
derniers mouvements ; les précédents restent conservés en base et dans l’audit.

## Recette du lot

### Préparation des comptes et des données

Exécuter cette campagne après la préparation de la recette complète, sur des
données dédiées. La réussite des tests automatisés ne passe pas les scénarios
de recette manuelle à OK dans le classeur.

1. Créer `rec.transfert` avec `budgeting.add_budgettransfer` et
   `rec.lecturetransfert` avec `budgeting.view_all_transfers`, via deux rôles ERP.
2. Créer `rec.stock` avec `receiving.manage_stock` et `receiving.add_warehouse`,
   puis `rec.lecturestock` avec `receiving.view_stockbalance`. Tous ces comptes
   sont actifs, sans statut équipe ni superutilisateur.
3. Réutiliser `rec.cdf`, `rec.finance` et `rec.sansdroit`. Affecter `rec.cdf` au
   CDF source dédié. Pour la variante support, attribuer le support à
   `rec.transfert` et affecter `rec.finance` comme responsable de ce support.
4. Créer `REC-TB-A`, `REC-TB-B`, le financement `REC-TB-F` et le BI `REC-TB-BI`.
   Dans une nouvelle version de l’année courante, conserver les allocations
   existantes, ajouter 100 EUR sur A/F/BI, sans allocation B/F/BI, puis publier.
   Aucun achat ni transfert antérieur ne doit utiliser ces combinaisons.
5. Publier un workflow de transferts inconditionnel : responsables du CDF source,
   ordre 1. Créer une nouvelle version pour chaque variante de circuit.
6. Comme `rec.stock`, créer `REC-DEPOT-A` et `REC-DEPOT-B`. Utiliser le produit
   détaillé dédié `REC-STK-P`, créé par un compte ayant
   `purchasing.add_detailedproduct`, avec une unité de référence fixe.
7. Relever soldes, états et identifiants avant chaque test. Utiliser une demande
   distincte par variante de rejet/annulation. Exécuter TB-04 et TB-07 après TB-03.
   Pour les autres variantes, rétablir 100 EUR disponibles à la source par des
   opérations justifiées sur ces seules données de test. Ne pas vider la base.

Pour WF-13/14/15, créer une DA neuve par essai avec une allocation suffisante.
STK-01 part de quantités nulles ; STK-03 suit STK-01. Pour les refus de transfert
de stock, vérifier également que le dépôt destination n’a pas changé.

### Scénarios à consigner

| ID | Actions | Attendu |
|---|---|---|
| WF-12 | Publier un circuit de chaque opération | Deux versions actives indépendantes |
| WF-13 | Manuel ordre 1, automatique ordre 2 | L’automatique attend la décision du niveau 1 |
| WF-14 | Deux étapes pour le même acteur ; désactiver la réutilisation au niveau 2 | Nouvelle décision exigée au niveau 2 |
| WF-15 | Circuit entièrement automatique sur une DA | Une seule commande, engagement unique, preuve système |
| WF-16 | Automatique sous 100 EUR, manuelle dès 100 ; tester 99,99, 100 et 100,01 | Bonne règle aux bornes, aucune absence de règle |
| WF-17 | Soumettre sous V1, publier V2 avec d’autres options puis soumettre à nouveau | Première demande sous V1 inchangée ; nouvelle sous V2 ; version publiée immuable |
| WF-18 | Étape manuelle sans candidat puis ajout d’un responsable CDF actif | À affecter puis en attente, jamais approuvée implicitement |
| WF-19 | Même acteur à deux étapes, réutilisation activée ; approuver la première | Étape suivante liée à la preuve manuelle, sans double déduction |
| TB-01 | Source 100 EUR ; soumettre un transfert de 60 EUR | Source disponible 40, destination 0 |
| TB-02 | Pendant TB-01, soumettre un autre transfert de 60 ou un achat de 50 EUR | Refus sans écriture partielle |
| TB-03 | Approuver TB-01 | Source 40, destination 60, total conservé |
| TB-04 | Rejouer la même décision depuis un ancien onglet | Refus sans crédit doublé |
| TB-05 | Rejeter avec motif ou annuler un transfert en attente | Source libérée, aucun crédit destination |
| TB-06 | Retirer tous les responsables CDF, soumettre puis en réaffecter un | Étape à affecter, puis traitable ; montant réservé conservé |
| TB-07 | Publier une nouvelle version avec allocation source de 200 après TB-03 | Nouvelle version : source 200, destination 0. Version d’origine : source 40, destination 60 ; son transfert et son historique sont conservés |
| TB-08 | Soumettre sans workflow actif ou sans règle correspondante | Refus ; brouillon conservé ; aucune réservation ni étape partielle |
| TB-09 | Montant nul/négatif, source égale à destination ou justification vide | Refus ; aucune réservation |
| TB-10 | Circuit entièrement automatique ; soumettre 20 EUR sur une source à 100 | Approuvé immédiatement ; source 80, destination 20 ; preuve système datée |
| TB-11 | Circuit support ; essayer sans support, sans appartenance puis avec un support autorisé | Refus avant réservation puis responsable du support choisi éligible |
| TB-12 | Deux étapes parallèles avec deux acteurs ; approuver une seule puis l’autre | Aucun crédit destination avant toutes les validations |
| STK-01 | Entrée 10, sortie 2, transfert 3 vers B | A = 5, B = 3 |
| STK-02 | Sortir ou transférer plus que le disponible | Refus, quantités et historique inchangés |
| STK-03 | Inventaire A = 4 puis A = 0 | Écarts -1 puis -4 conservés |
| STK-04 | Envoyer deux fois le même formulaire d’entrée | Une seule entrée |
| STK-05 | Entrée 2,5000 puis sortie 0,1250 ; essayer une quantité négative ou plus de quatre décimales | Solde 2,3750 ; précision invalide refusée sans mouvement |
| STK-06 | Transfert vers le même dépôt, sans destination ou destination sur une entrée simple | Refus sans écriture ni variation des quantités |
| STK-07 | Enregistrer une correction distincte et justifiée ; consulter historique et journal | Mouvement initial conservé ; correction datée et attribuée |
| STK-08 | Réenvoyer le même identifiant de formulaire avec une quantité différente | Refus sans second mouvement ; quantité initiale conservée |
| SEC-03 | Sans droits : ouvrir les URL, envoyer les formulaires, viser une étape future | Refus côté serveur |
| SEC-04 | Lecture seule : consulter puis envoyer directement un formulaire de création ou mouvement | Consultation autorisée ; écriture refusée ; aucune donnée changée |
| SEC-05 | Autre demandeur : soumettre/annuler le transfert d’autrui ; responsable CDF retiré : décider | Refus côté serveur ; demande et réservations conservées |

Vérifications techniques :

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py check --settings=config.demo_settings
```

Les tests concurrents `budgeting/test_transfers_postgresql.py` et
`receiving/test_stock_postgresql.py` nécessitent la configuration PostgreSQL dédiée
décrite dans la recette complète. Les verrous utilisent l’enveloppe annuelle commune
aux achats/transferts et les dépôts de stock dans l’ordre de leurs identifiants.
SQLite ne vérifie pas ces garanties de concurrence.
