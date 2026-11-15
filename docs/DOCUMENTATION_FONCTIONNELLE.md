# ERP — Documentation fonctionnelle

Version documentaire : 14 novembre 2026. Référence : code du dépôt BF-ERP,
commit de base `dc67883` et modifications locales décrites ci-dessous.
Ce document décrit le produit effectivement implémenté, pas une cible future.

Documents associés : [plan de tests](PLAN_TESTS.md),
[classeur de recette](PLAN_TESTS.xlsx),
[documentation technique et performances](DOCUMENTATION_TECHNIQUE.md).

## 1. Finalité et périmètre

L'ERP couvre la préparation des demandes d'achat (DA), leur financement,
leur validation, l'émission du bon de commande, les réceptions et le stock.
Il fournit également les versions de budget, les allocations, les transferts
budgétaires, les référentiels, les droits d'accès et les historiques.

Il ne constitue pas, dans son état actuel, une comptabilité générale : pas de
plan comptable, facturation fournisseur, rapprochement bancaire ou paiement
implémenté par les anciens modules vides retirés. Un engagement budgétaire
n'est ni une facture ni un règlement. L'impression d'un bon n'envoie pas
automatiquement une commande au fournisseur.

L'interface utilise le français belge et le fuseau Europe/Brussels.
Les montants affichés sont exprimés en EUR. Le format d'affichage comporte
au plus deux décimales ; la précision de calcul et de stockage est conservée.

## 2. Vocabulaire et distinctions importantes

| Terme | Sens dans l'application |
| --- | --- |
| DA | Demande d'achat contenant un fournisseur et une ou plusieurs lignes |
| CDF | Centre auquel une ligne et son financement budgétaire sont rattachés |
| BI / produit budgétaire | Catégorie utilisée dans la combinaison budgétaire |
| Produit détaillé | Article opérationnel rattaché à un BI ; utilisé dans les DA et le stock |
| Financement | Référentiel entrant dans la combinaison CDF × financement × BI |
| Support | Appartenance du demandeur ou information facultative source/destination d'un transfert ; distinct du financement |
| Responsable CDF | Utilisateur actif affecté au CDF ; cette affectation permet la validation de ses lignes |
| Rôle ERP | Ensemble de permissions attribuées à un utilisateur ; ne remplace pas une affectation CDF |
| Version budgétaire | Jeu d'allocations d'une année ; peut être brouillon, active, remplacée, bloquée ou supprimée logiquement |
| Réservation | Budget indisponible pendant une validation de DA |
| Engagement | Réservation convertie après validation de toutes les lignes de la DA |
| Transfert en attente | Débit réservé à la source ; destination non créditée avant validation complète |
| Soumission | Cycle de validation figé d'une DA ; une correction entraîne une nouvelle soumission |
| Réception | Enregistrement physique d'une livraison liée à un bon de commande |

Les supports d'appartenance, les responsables de supports et les responsables
CDF sont trois notions différentes. L'appartenance à un support ne donne
aucun droit de validation par elle-même.

## 3. Profils et habilitations

Les profils ci-dessous sont des compositions recommandées de droits, pas des
rôles obligatoires codés en dur. Les droits individuels, groupes Django et
rôles ERP se cumulent. Un compte inactif ne peut pas agir.

| Profil | Accès et actions | Limites |
| --- | --- | --- |
| Demandeur | Créer et modifier ses brouillons/corrections, soumettre, consulter ses DA, annuler selon l'état | Ne modifie pas la DA d'autrui et ne devient pas valideur par sa seule qualité de demandeur |
| Responsable CDF | Retrouver les lignes affectées dans Mes validations et décider | Un autre CDF et une habilitation retirée ne doivent pas devenir accessibles |
| Gestionnaire budgétaire | Créer une version, alimenter, publier selon les permissions requises | Le droit de consulter un budget ne suffit pas à le modifier |
| Lecteur budget | Lire les versions et disponibilités autorisées | Pas de droit d'achat financier implicite |
| Gestionnaire fournisseurs | Consulter, créer et/ou modifier selon les trois permissions correspondantes | Consultation et écriture sont distinctes |
| Gestionnaire de stock | Enregistrer des mouvements et réceptions | Ne reçoit pas automatiquement les montants financiers des achats |
| Suivi opérationnel | Suivre l'état des demandes et étapes | Le suivi ne confère ni détail financier ni réaffectation |
| Administrateur métier des DA | Intervenir sur les validations avec `decide_any_purchaserequest` | L'accès global est un droit explicite, audité |
| Administrateur transferts | Décider ou annuler globalement avec les permissions dédiées | Décision et annulation globale sont deux droits différents |
| Administrateur système | Compte superutilisateur : administration, politique de session, blocages et maintenance | Les opérations de maintenance sont sensibles et historisées |

Les contrôles serveur restent applicables même si une URL ou un identifiant
est connu. Cacher un bouton ne constitue pas la protection du service.
Les fonctions historiques par habilitations versionnées restent compatibles
avec les anciennes données ; leur rubrique a été retirée de Configuration.

## 4. Connexion, sessions et navigation

Connexion : `/connexion/`. Déconnexion : bouton du bandeau ; opération POST.
Une mauvaise identification conserve un message d'erreur. Un compte désactivé
peut recevoir un message spécifique quand son mot de passe est correct.

Le délai d'inactivité est de 120 minutes par défaut et configurable par
l'administrateur système entre 1 et 10 080 minutes. Une activité utilisateur
repousse l'expiration ; le contrôle périodique `/session/statut/` ne la
repousse pas. Le serveur refuse aussi un POST après expiration : conserver
un onglet ouvert ne garantit pas la validité de la session.

Les menus Stocks, Achats, Budget et Configuration apparaissent selon les
permissions. Mes validations et Mes délégations sont des accès personnels
globaux dans le bandeau. Ils ne sont plus proposés dans le menu Achats.
Le lien Suivi administrateur a été retiré du menu Achats ; son URL reste
protégée et compatible avec les droits existants.

Le bouton € « Vérifier un budget » est disponible dans la rubrique Achats.
Il ouvre une fenêtre de consultation, pas une écriture budgétaire. Le thème
clair/sombre peut être sélectionné ; le choix se synchronise entre onglets
et avec la fenêtre de consultation budgétaire.

## 5. Référentiels et configuration

### 5.1 Utilisateurs, rôles et responsables

Dans Configuration, gérer les comptes, rôles, permissions, CDF et supports.
L'accès à l'administration Django exige aussi le statut approprié ; un compte
applicatif actif n'est pas forcément un utilisateur d'administration.

La configuration des responsables permet d'affecter plusieurs utilisateurs
actifs à un CDF ou à un support. La recherche porte sur l'identifiant, le nom
et le prénom ; le choix administratif est paginé. Un utilisateur déjà affecté
puis devenu inactif peut rester visible pour retrait, sans être proposé pour
une nouvelle affectation active. L'affectation est contrôlée à nouveau au
moment de la décision, pas seulement lors de l'affichage initial.

### 5.2 Fournisseurs

Depuis Achats → Fournisseurs, consulter la liste et rechercher par code, nom
ou numéro de TVA. Créer un fournisseur avec code unique et nom ; la TVA est
facultative. Modifier avec le bouton de la ligne selon le droit de changement.
Une création avec un code existant doit être refusée sans doublon.

Les contacts et adresses existent dans le modèle et l'administration. La
page applicative simplifiée gère le fournisseur principal. Modifier le
référentiel après validation d'une DA ne réécrit pas le fournisseur figé du bon.

### 5.3 Produits et dépôts

Les BI sont les produits budgétaires. Les produits détaillés sont gérés depuis
Achats et rattachés à un BI. Les allocations ne sont pas portées par le
produit détaillé lui-même. Les dépôts sont créés/configurés dans Stocks,
avec code unique et libellé. Un droit de lecture de dépôt ne donne pas le
droit d'enregistrer des mouvements.

## 6. Gestion budgétaire

### 6.1 Création, alimentation et publication

1. Ouvrir Budget puis Créer une version.
2. Saisir l'année et un libellé distinct des autres versions de cette année.
3. Enregistrer le brouillon, même initialement vide.
4. Dans Allocations de la version, saisir les combinaisons BI/CDF/financement
   et leurs montants, ou utiliser l'import Excel.
5. Enregistrer et contrôler les totaux.
6. Publier et activer la version lorsque les contrôles sont satisfaits.

Le nom est unique dans l'année après les normalisations prévues par les
contrôles. Une combinaison ne doit pas être dupliquée dans une version.
Une publication vide ou un montant invalide doit être refusé. Une nouvelle
version active remplace la précédente sans effacer ses écritures ni son
historique. Les réservations/engagements de DA restent rattachés à l'enveloppe
annuelle ; les transferts sont isolés par version.

### 6.2 Modification, blocage et suppression

Une version publiée est normalement en lecture seule. L'administrateur
système peut débloquer les modifications ; elles prennent alors effet sur
la version publiée dès leur enregistrement, sans dépublier ni effacer les
réservations/engagements existants. Il peut rebloquer les modifications.

Une version bloquée ne reçoit pas de nouvelles allocations ni d'import.
Pour les transferts, certaines décisions d'approbation sont aussi refusées
quand la version n'est plus modifiable, alors que le rejet peut rester possible.
Ne pas confondre ce comportement avec la conversion d'une DA déjà réservée.

La suppression ordinaire concerne un brouillon admissible et conserve une
trace historique. Elle est refusée pour les états ou dépendances protégés,
notamment les versions déjà publiées ou utilisées par des transferts.
La suppression de maintenance système est une procédure différente.

### 6.3 Disponible et déficits

Pour une combinaison CDF/financement/BI, le principe est :

`Disponible = allocation de la version − réservations annuelles de DA
− engagements annuels de DA + solde des transferts de la version`.

La réservation d'un transfert diminue sa source dès la soumission ; la
destination n'augmente qu'après approbation complète. Une destination peut
apparaître dans les disponibilités même sans allocation initiale.

Un disponible négatif est signalé. Les nouvelles réservations insuffisantes
sont bloquées. Les DA déjà réservées ne sont pas déduites une seconde fois
quand elles deviennent des engagements. Consulter une version brouillon ou
remplacée ne l'active pas.

La vérification ponctuelle d'un budget est accessible à un utilisateur
authentifié, même sans accès au tableau global des budgets. C'est une
caractéristique actuelle à prendre en compte dans la politique d'accès.

### 6.4 Import et export Excel

L'import se trouve dans la barre d'actions des Allocations de la version,
à côté de l'export, lorsque la version est modifiable pour l'utilisateur.
Le modèle téléchargeable contient les allocations existantes et des feuilles
de référence BI, CDF et financements.

| Règle | Valeur |
| --- | --- |
| Format | `.xlsx` |
| Taille du fichier | Au plus 5 Mio |
| Taille décompressée | Au plus 50 Mio |
| Volume | Au plus 10 000 lignes de données |
| Colonnes obligatoires | Code BI, Code CDF, Code financement, Montant TVAC |
| Feuille | Allocations si présente ; sinon première feuille |
| Formules et cellules en erreur | Refusées ; coller les valeurs |
| Combinaison répétée | Refusée dans un même import |
| Code inconnu ou montant invalide | Refus de l'ensemble de l'import |
| Réimport | Remplacement du montant total ; jamais une addition répétée |
| Allocation absente du fichier | Conservée |
| Année/version présentes dans un export réimporté | Doivent correspondre à la version cible |

Conserver les codes en texte pour préserver les zéros initiaux. L'import est
transactionnel : une ligne invalide ne doit laisser aucune modification
partielle. Une progression d'envoi ne signifie pas encore que l'import
serveur est terminé. Attendre le résultat final et le journal de l'opération.

## 7. Demandes d'achat

### 7.1 Création et saisie

Depuis Achats, créer une DA, choisir le fournisseur et éventuellement un
support d'appartenance. Le numéro des nouvelles DA suit le format
`DA-AAAA-NNNN`, avec compteur annuel. Les anciennes références restent
inchangées ; les numéros consommés ne sont pas réutilisés après suppression.

Ajouter chaque ligne : produit détaillé, description, quantité, prix unitaire
HTVA, taux de TVA explicite, CDF et financement. Le BI découle du produit
détaillé. Une TVA à 0 est valide, une TVA absente n'est pas assimilée à zéro.
Les quantités/prix et limites de précision sont validés par les formulaires
et modèles. Les montants sont calculés en décimales, sans conversion métier
en nombres flottants.

Exemple : 2 unités à 100 EUR HTVA, TVA 21 % → HTVA 200 EUR, TVA 42 EUR,
TVAC 242 EUR. L'affichage peut être arrondi à deux décimales sans modifier
les valeurs conservées par le calcul.

Les boutons Modifier/Supprimer d'une ligne sont côte à côte. La suppression
se confirme sur place. Le bouton de modification fournisseur/support a été
retiré de la fiche ; la route historique reste protégée.

### 7.2 Soumission et contrôle budgétaire

Cliquer Soumettre dans la fiche. L'application contrôle toutes les lignes,
la version active de l'année courante, chaque combinaison et les montants
agrégés par combinaison. L'agrégation évite que deux lignes prises isolément
consomment ensemble plus que le disponible.

Si un contrôle échoue, aucune réservation partielle n'est effectuée. L'erreur
s'affiche dans une fenêtre sur la DA, avec montants lisibles. Fermer la
fenêtre permet de corriger la saisie. Une erreur réseau doit inciter à
recharger la DA pour vérifier son état avant de soumettre à nouveau.

Après succès : DA En validation, nouvelle soumission et données figées,
réservation du total TVAC de chaque ligne et étapes CDF correspondantes.

### 7.3 Validation des lignes et rôle de l'administrateur

Chaque ligne est validable par un responsable actif de son CDF. Les lignes
d'une même DA peuvent être traitées en parallèle et dans un ordre différent.
Deux lignes du même CDF exigent deux décisions distinctes. Il n'existe pas
d'étape finance supplémentaire dans les nouvelles DA.

Le parcours est une frise de consultation. La petite bulle verte indique
une validation actuellement ouverte. Plusieurs bulles vertes sont normales
si plusieurs lignes attendent leur responsable. Les boutons sont dans les
lignes de la DA, pas dans la frise.

L'administrateur disposant du droit dédié peut valider une ligne, même sans
affectation de responsable, ou utiliser Valider tout le circuit au niveau
des actions de la DA. Une confirmation précise que toutes les validations
restantes sont concernées. L'intervention est enregistrée au nom de l'acteur.

Un retour pour correction ou un rejet porte sur toute la demande, avec motif
obligatoire, et libère toutes ses réservations. Une correction est modifiable
et resoumissible ; les anciennes décisions restent visibles sans valoir pour
le nouveau cycle. Un rejet est terminal.

### 7.4 États de la DA

| État technique | Libellé / effet | Suite possible |
| --- | --- | --- |
| DRAFT | Brouillon, aucune réservation | Saisie, soumission ou annulation |
| SUBMITTED | En validation, budget réservé | Approbations, correction, rejet, annulation autorisée |
| CORRECTION | À corriger, réservations libérées | Modification puis nouvelle soumission |
| REJECTED | Rejet définitif | Consultation de l'historique |
| CANCELLED | Annulée | Consultation |
| ORDERED | Commandée ; toutes les lignes approuvées | Bon de commande et réceptions |

### 7.5 Bon de commande et réception

Toutes les lignes approuvées produisent un bon unique. Les réservations
deviennent des engagements ; le disponible n'est pas déduit une seconde fois.
Le document utilise les données fournisseur et lignes figées à la soumission.
Le bouton d'impression lance l'impression depuis la DA, sans page
intermédiaire. Le navigateur peut enregistrer en PDF selon ses capacités.

Le suivi des réceptions distingue Non réceptionnée, Partiellement réceptionnée
et Réceptionnée. Il s'agit d'un axe indépendant de l'état d'approbation.

## 8. Transferts budgétaires

### 8.1 Création et destination commune

Dans Budget → Transferts, choisir une version, saisir une ou plusieurs lignes
sources et une destination commune. Les supports source/destination sont
facultatifs et indépendants. Chaque ligne comporte son montant positif et sa
justification. Les lignes supprimées/vides sont ignorées selon les contrôles
du formset ; au moins une ligne valide reste obligatoire. Maximum : 100 lignes
dans une soumission de formulaire.

La combinaison source et destination doit être différente. Le montant total
de destination est la somme des sources valides. La création groupée est
atomique : budget insuffisant sur une source ou erreur sur une ligne annule
toutes les écritures de la soumission.

### 8.2 Circuit et effets

Pour chaque transaction, le responsable CDF source approuve d'abord ; le
responsable CDF destination intervient ensuite. Le même responsable aux deux
extrémités doit prendre deux décisions. Les affectations actuelles sont
réévaluées. Une ancienne règle automatique ne contourne pas ce circuit fixe.

À la soumission : source diminuée, destination inchangée. À la validation
finale : destination augmentée, source déjà débitée. Le remplacement de la
version active ne déplace pas le transfert dans une autre version.

Les états sont Brouillon, En attente, Approuvé, Retourné, Rejeté et Annulé,
selon l'opération. Un retour au demandeur permet correction/resoumission et
conserve l'historique des cycles. Le rejet/annulation et la correction ne
doivent pas être confondus : leurs issues et permissions sont différentes.

### 8.3 Actions globales et historique

La liste regroupe les transactions par transfert et affiche le total, l'état
global et les lignes. L'administrateur autorisé peut valider toutes les
lignes ou fermer un groupe avec justification. Les opérations globales
concernent aussi les lignes masquées par les filtres. Elles utilisent un
instantané signé des révisions pour refuser un écran devenu périmé.

Un transfert entièrement accompli ne peut plus être simplement retourné ;
l'annulation administrative nécessite son droit propre. Reprendre des fonds
à une destination déjà consommée/réservée est refusé si le disponible ne
permet pas le mouvement inverse. Une opération groupée échouée doit laisser
le groupe entier dans son état antérieur.

La visibilité inclut les acteurs autorisés : créateur, responsables concernés,
approbateurs et lecteurs globaux selon leurs permissions. Filtrer une liste
ne doit pas élargir ce périmètre. Le parcours et le journal daté sont
consultables par transaction ; l'historique d'une version isole ses transferts.

## 9. Stock et réceptions

### 9.1 Mouvements

| Mouvement | Saisie | Effet |
| --- | --- | --- |
| Entrée | Quantité positive | Augmente le dépôt |
| Sortie | Quantité positive | Diminue le dépôt, sans stock négatif |
| Transfert | Dépôt destination différent | Débite source et crédite destination atomiquement |
| Inventaire | Quantité finale, zéro autorisé | Ajuste le solde à la quantité comptée ; delta historisé |

Le produit est un produit détaillé. La référence/justification est obligatoire.
Chaque opération possède un token d'idempotence : rejouer le même envoi ne
double pas le stock ; réutiliser son token avec des données différentes est
refusé. Un mouvement enregistré est immuable ; corriger par un mouvement
distinct motivé.

### 9.2 Réception d'achat

Ouvrir Stocks → Réceptions des achats ou le lien de réception d'une DA
commandée. Choisir le dépôt, la référence de livraison et les quantités reçues
par ligne. Une réception partielle est possible ; une quantité supérieure au
reste à recevoir est refusée. Une ligne d'une autre DA, une quantité négative,
une réception vide ou une DA non commandée sont refusées.

La réception et ses mouvements de stock sont enregistrés dans une seule
transaction. Un échec ne doit créer ni réception orpheline ni stock partiel.
Un utilisateur stock peut réceptionner sans obtenir le détail financier de
la DA. Un mouvement de stock indépendant ne vaut pas réception de commande.

## 10. Notifications, délégations et historiques

Mes validations regroupe les lignes et transferts accessibles et les retours
au demandeur. Le badge global tient compte des affectations actuelles. La
file de notifications des achats est durable : un échec d'envoi de courriel
n'annule pas la soumission. Une commande de gestion doit être planifiée pour
traiter cette file. Les notifications obsolètes ne sont plus envoyées.

Une délégation d'achat désigne un remplaçant et une période valide. Les
chevauchements et chaînes interdits sont refusés. La décision conserve
l'acteur réel et le représenté ; elle dépend aussi du droit actuel du
principal. Cette délégation n'est pas appliquée aux transferts.

Trois historiques sont complémentaires : événements de DA avec révision,
événements de configuration/transfert/stock et journal indépendant des
identités/objets. L'historique budgétaire conserve des états datés ; consulter
une date ne réécrit pas le passé. Les données d'identité enregistrées restent
lisibles après suppression d'un compte.

## 11. Exports, exploitation et maintenance

Les écrans proposent des exports Excel selon leurs droits et filtres.
Un export doit conserver la portée de l'écran et ne pas exposer de données
financières à un profil opérationnel. Les textes commençant par une formule
Excel sont exportés comme texte. L'impression est distincte d'un export XLSX.

Les suppressions ordinaires sont limitées par les dépendances et états.
L'administration système offre une maintenance avec aperçu des dépendances,
détachement des références facultatives et journal de suppression. Supprimer
une étape d'un cycle actif peut arrêter ce cycle, remettre la DA en correction
et libérer le budget. Le journal indépendant ne peut pas être supprimé par
ce service. Toute recette de maintenance se fait sur une base jetable.

## 12. Limites connues et assistance

- La démonstration SQLite n'est pas une preuve de robustesse concurrente
  PostgreSQL. Les tests dédiés doivent être rejoués sur le moteur cible.
- Certains GET de consultation actualisent les affectations/circuits et
  peuvent provoquer des écritures d'état. L'ouverture répétée d'écrans peut
  donc avoir un coût supérieur à une simple lecture.
- Les listes non paginées et les calculs de disponible peuvent coûter cher
  sur de gros volumes ; voir les mesures et priorités dans la doc technique.
- Aucun SLA, audit de sécurité complet, test navigateur exhaustif ou débit
  de production n'est certifié par cette documentation.
- En cas de conflit de révision, recharger puis vérifier l'état avant de
  recommencer. En cas d'import refusé, corriger le fichier entier avant envoi.
- Signaler une anomalie avec le numéro DA/transfert, le profil, les étapes,
  le résultat attendu/obtenu et les preuves ; ne jamais joindre de mot de passe.
