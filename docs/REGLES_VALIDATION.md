# Validations des demandes d’achat et des transferts

Sur la fiche d’un transfert, chaque valideur voit uniquement sa validation actuellement accessible. Le lien « Parcours » ouvre une ligne du temps distincte : étapes du circuit, étape actuelle, auteurs et dates des validations, puis journal des événements et motifs de rejet ou d’annulation.

Le sous-menu Budget → Transferts regroupe « Créer un transfert » (formulaire de création uniquement, avec le droit de création) et « Liste des transferts » (consultation, filtres par année, version et état, parcours et actions). Les responsables CDF voient les transferts de leurs CDF et ceux qu’ils ont validés ; les demandeurs voient leurs transferts. Les utilisateurs disposant des droits de consultation budgétaire globale conservent la vue complète.

Le droit « Valider ou refuser tout transfert budgétaire » (`budgeting.decide_any_budgettransfer`) autorise une décision sur l’étape actuelle de tout transfert, même hors des CDF du valideur ou en l’absence de responsable affecté. Il donne accès à la liste complète et aux validations correspondantes. Les superutilisateurs disposent de ce droit automatiquement ; pour les autres comptes administrateurs, il faut l’attribuer directement ou via un groupe ou rôle. Les deux décisions restent successives, le motif de rejet reste obligatoire et les contrôles budgétaires restent applicables. L’auteur réel de chaque décision est conservé dans l’historique.

Le compteur de notifications et « Mes validations » affichent uniquement les étapes en attente réellement assignées à l’utilisateur. Le droit d’intervention global ne crée aucune notification personnelle ; l’administrateur peut toujours intervenir depuis la liste ou le parcours des transferts.

Le bouton « Valider tout le circuit », réservé au droit `budgeting.decide_any_budgettransfer`, valide en une seule action toutes les étapes restantes d’une transaction en cours. Une confirmation précède l’envoi. Chaque étape est validée au nom de l’administrateur et journalisée ; les décisions antérieures conservent leur auteur. L’action est atomique et conserve les contrôles de révision et de blocage de version. Elle ne valide pas les autres transactions du groupe.

Au niveau du transfert général, le bouton « Valider toutes les lignes » utilise le même droit d’administration pour terminer tous les circuits des lignes encore en validation, y compris celles masquées par un filtre. Il conserve les lignes déjà approuvées et leurs auteurs. La confirmation porte sur l’ensemble du transfert. Une ligne en brouillon, refusée ou annulée empêche cette action ; une modification depuis l’affichage exige de recharger la liste. L’opération entière est atomique : une erreur sur une ligne annule toutes les validations de cette action. Chaque étape validée conserve sa trace habituelle dans le workflow de sa transaction.

Le bouton global « Refuser le transfert global » demande un motif et renvoie toutes les lignes au demandeur au statut « À corriger ». Le demandeur les retrouve dans « Mes validations », avec une notification et le motif du retour. Il peut corriger et resoumettre chaque transaction en conservant ses numéros de transaction et de transfert général. Les étapes précédentes restent consultables ; une resoumission ouvre un nouveau cycle de deux validations. Le budget est de nouveau vérifié à cette occasion.

Un transfert global « Accompli » ne peut plus être refusé ni renvoyé au demandeur, y compris par un appel direct à l’action. Le bouton de refus disparaît. L’annulation reste possible avec le droit d’annulation globale, un motif et les contrôles habituels sur les fonds disponibles à destination.

Le bouton global « Annuler définitivement le transfert », réservé au droit d’annulation globale, demande un motif et annule toutes les lignes. Elles ne peuvent plus être corrigées, resoumises ou validées. Les anciennes décisions et leurs auteurs restent dans le workflow. Les deux actions globales sont atomiques et couvrent aussi les lignes masquées par les filtres. Si une ligne était déjà approuvée, ses fonds ne peuvent être retirés de la destination que s’ils sont encore disponibles ; sinon aucune ligne du transfert n’est modifiée.

Les lignes créées lors d’une même saisie partagent un identifiant de regroupement. La liste les présente dans une section commune avec leur nombre et leur montant total, tout en conservant les validations, le parcours et les actions de chaque ligne. La pagination porte sur les groupes pour ne pas séparer leurs lignes. Les filtres et les droits de consultation s’appliquent avant le calcul des totaux affichés. Les anciennes lignes sans lien de saisie connu restent indépendantes.

Chaque transfert général affiche un statut calculé sur toutes ses lignes, indépendamment des filtres : « Accompli » uniquement lorsque toutes sont approuvées, « En cours » tant qu’une ligne attend une validation, « Refusé » ou « Annulé » si toutes ses lignes ont cet état. Un résultat mêlant des lignes approuvées et des lignes refusées ou annulées est « Partiellement accompli ». Une annulation ultérieure met à jour le statut global.

Les schémas complets sont consultables depuis **Configuration → Schémas de
validation des DA et des transferts** (`/achats/configuration/schemas-validation/`).
Cette page est réservée aux administrateurs système et présente les étapes,
les décideurs, les effets budgétaires et les issues possibles.

Les validations suivent un parcours fixe. Il n’y a plus de règles conditionnelles,
de seuils, de versions de circuit à créer ni de publication à effectuer.

## Demandes d’achat : un responsable CDF par ligne

À la soumission, chaque ligne reçoit une seule étape de validation, affectée
aux responsables actifs du **CDF de cette ligne**.

- Les lignes peuvent être validées indépendamment, dans n’importe quel ordre.
- Un responsable d’un autre CDF ne peut pas approuver la ligne.
- Si plusieurs responsables actifs gèrent un CDF, la décision de l’un d’eux suffit.
- Chaque ligne exige sa propre décision, même si plusieurs lignes ont le même CDF.
- Le support demandeur et le financement ne créent aucune validation supplémentaire.
- Sans responsable actif, la ligne reste **À affecter**. Les autres lignes peuvent
  être validées, mais la demande ne peut pas être terminée.

Exemple : une DA contient une ligne du CDF A et une ligne du CDF B. Le responsable
du CDF A voit et valide la première ; celui du CDF B voit et valide la deuxième.
Le bon de commande est créé uniquement lorsque les deux lignes sont approuvées.

Le budget TVAC de toutes les lignes est réservé lors de la soumission. Les
réservations deviennent des engagements après l’approbation de toutes les lignes.
Un rejet ou un retour pour correction porte sur toute la demande et libère ses
réservations. Une nouvelle soumission crée de nouvelles étapes de validation.

## Transferts : CDF source, puis CDF destination

Chaque nouveau transfert suit deux étapes successives :

1. Validation par un responsable actif du **CDF source**.
2. Validation par un responsable actif du **CDF destination**.

La deuxième étape reste inaccessible tant que la première n’est pas approuvée.
Deux décisions distinctes sont nécessaires, même si la même personne gère les
deux CDF. Un transfert entre deux combinaisons budgétaires du même CDF conserve
également les deux étapes.

Le montant est réservé à la source lors de la soumission. La destination n’est
créditée qu’après les deux validations. Sans responsable actif, l’étape reste
**À affecter** ; aucune validation automatique n’est effectuée.

## Affecter les responsables

Dans **Configuration → Responsables des CDF et des supports**, sélectionner un
CDF et ses responsables. Le droit `budgeting.manage_cost_center_managers` est
nécessaire pour modifier ces affectations.

Les responsables doivent avoir un compte actif. Aucune fonction, habilitation ou
règle de validation n’est nécessaire pour les nouveaux parcours. Un administrateur
ne peut pas approuver une ligne ou un transfert uniquement parce qu’il est
administrateur : il doit être responsable du CDF concerné.

Les affectations sont revérifiées avant chaque décision. Un responsable retiré
perd son accès à la validation ; un nouveau responsable retrouve les étapes
en attente dans **Mes validations**. Les délégations existantes restent prises
en charge pour les demandes d’achat.

## Historique et anciens circuits

Les étapes déjà enregistrées conservent leurs affectations et leurs décisions.
Les anciennes configurations sont conservées en base pour l’historique, mais
elles ne sont plus utilisées pour les nouvelles soumissions. L’éditeur, la
simulation et l’administration des circuits configurables sont retirés.

Les règles budgétaires, le suivi des transferts par version et les possibilités
d’annulation restent décrits dans [Transferts et stock](TRANSFERTS_ET_STOCK.md).

## Modification administrative d’une version budgétaire

Dans **Budget → Alimenter une version**, ouvrir la version puis utiliser
**Débloquer pour modification**. Cette action est réservée à l’administrateur
système, y compris pour une version publiée. Les gestionnaires ordinaires
conservent un accès en lecture seule aux versions publiées, même débloquées.

Après modification, cliquer sur **Enregistrer les lignes**, puis sur **Bloquer
les modifications** pour revenir en lecture seule. La version conserve sa date
de publication et reste active si elle l’était déjà. Les modifications prennent
effet immédiatement à l’enregistrement ; les réservations et engagements
existants ne sont pas effacés. Les états datés antérieurs restent consultables.

Une version brouillon bloquée peut également être débloquée par l’administrateur.
Une version supprimée ne peut pas être débloquée. Le reblocage des modifications
d’une version publiée ne suspend pas les achats et transferts en cours.

## Vérifications de recette

| Cas | Résultat attendu |
|---|---|
| DA avec deux lignes de CDF différents | Chaque responsable valide uniquement sa ligne |
| Deux lignes du même CDF | Deux décisions manuelles, une par ligne |
| Une seule ligne approuvée sur deux | Demande toujours en validation ; aucun bon de commande |
| Toutes les lignes approuvées | Bon de commande unique ; réservations converties en engagements |
| Ligne sans responsable actif | Étape « À affecter », jamais approuvée automatiquement |
| Responsable remplacé après soumission | Ancien responsable refusé, nouveau responsable autorisé |
| Transfert : destination avant source | Validation refusée |
| Transfert : même responsable pour les deux CDF | Deux décisions successives obligatoires |
| Ancienne règle automatique encore présente | Aucun effet sur une nouvelle soumission |


Les nouveaux transferts sont soumis directement depuis le formulaire de creation. Creation, journalisation et soumission sont atomiques : si le controle budgetaire refuse la soumission, le formulaire conserve la saisie sans creer de brouillon ni reserver de montant. Les anciens brouillons restent consultables et peuvent encore etre soumis depuis leur fiche.

La saisie des transferts utilise un tableau de 1 a 100 lignes, avec version et destination communes. Chaque ligne source conserve ses CDF, produit, financement, support optionnel, montant, justification et deux validations successives. La destination est saisie une seule fois (CDF, produit, financement et support optionnel). Son montant non editable est calcule comme la somme des sources actives ; il ne constitue pas une valeur financiere acceptee depuis le navigateur. Les lignes vides ou retirees sont ignorees. Le lot entier est atomique, y compris si plusieurs lignes debitent la meme combinaison source : le disponible tient compte des lignes precedentes du lot.
