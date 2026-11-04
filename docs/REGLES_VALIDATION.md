# Règles de validation

Accès : **Configuration → Workflows et validations → Règles de validation**.
Le même accès figure dans l’administration Django.

## Créer les règles d’une demande d’achat

1. Créer une version brouillon et ouvrir cette version.
2. Choisir **Ajouter une règle**, puis donner un nom à la validation.
3. Dans **Si…**, choisir **ET** (toutes les conditions) ou **OU** (au moins une),
   puis ajouter les informations à comparer et leurs valeurs.
4. Dans **Alors…**, choisir les responsables du CDF, ceux du support de la DA,
   un rôle ERP ou un utilisateur nommé.
5. Préciser l’ordre : un même ordre signifie des étapes parallèles sur la ligne ;
   un ordre supérieur attend les étapes précédentes de cette ligne.
6. Enregistrer, puis ajouter les autres règles. Une règle sans condition exige
   de cocher explicitement **Toujours appliquer à toutes les lignes**.
7. Utiliser les liens de simulation en bas de la version pour tester une DA
   accessible. Corriger les conditions ou les affectations selon le résultat.
8. Choisir **Publier et activer cette version**. Les nouvelles soumissions
   utilisent cette version ; les soumissions existantes conservent leurs étapes.

Exemple : montant de la ligne TVAC **supérieur ou égal à 5 000** ET CDF
**égal à Atelier** → validation par le rôle Direction, ordre 2.
Une autre règle peut demander les responsables CDF à l’ordre 1.

## Informations et montants

Champs disponibles : montant HTVA ou TVAC de la **ligne**, quantité, CDF,
financement, produit budgétaire, support choisi sur la **DA**, montant total
HTVA ou TVAC de la **DA**. Le support est indépendant du financement.

Les comparaisons numériques utilisent des décimales exactes : égal, différent,
supérieur, supérieur ou égal, inférieur, inférieur ou égal. Les référentiels
se choisissent dans une liste, avec égal ou différent. Une information manquante
ne satisfait pas une condition, même « différent de ».

Toutes les règles correspondantes se cumulent, sans priorité exclusive. Chaque
ligne doit correspondre à au moins une règle, sinon la soumission est refusée
sans réservation. Les ordres s’appliquent par ligne, pas comme une barrière
globale entre toutes les lignes de la DA.

Les responsables et les membres des rôles doivent être actifs. Un utilisateur
nommé dans le nouvel éditeur valide directement cette étape. Les fonctions et
leurs habilitations appartiennent uniquement à l’ancien système : elles ne sont
plus proposées dans l’éditeur courant. Une approbation par l’un des candidats
suffit pour une étape. Comme dans le circuit existant, une décision peut couvrir
une autre étape où le même utilisateur est éligible : cette étape conserve le
lien vers la décision servant de preuve.

## Simulation et traçabilité

Dans la fiche d’une DA, **Simuler les validations** évalue la version active.
Dans une version de règles, les liens de simulation évaluent ce brouillon ou
cette version précise. Le résultat donne les règles correspondantes par ligne,
leurs conditions, leur ordre et les valideurs actuellement éligibles.

La simulation ne réserve aucun budget et ne crée ni soumission, ni étape, ni
notification. Elle ne garantit pas la disponibilité budgétaire ; les contrôles
sont refaits lors de la soumission. Les remplaçants éventuels sont gérés ensuite
par les délégations existantes, et ne remplacent pas les titulaires affichés.

À la soumission, chaque étape mémorise la règle, les conditions, les valeurs
évaluées et le mode d’affectation. Une version publiée et ses règles ne sont
plus modifiables. Copier une version produit un nouveau brouillon.

## Anciennes configurations et extensions

Les configurations historiques restent utilisables avec leur comportement
initial. **Copier en nouveau brouillon** convertit leurs critères de montant
total, CDF, financement et BI en conditions lisibles. La conversion automatique
des circuits contenant des règles exclusives est refusée : créer dans ce cas
une nouvelle version cumulative. Aucune activation n’est automatique.

Les anciennes fonctions restent conservées dans la base pour les règles et
les preuves existantes, mais leur écran est retiré de l’administration. Les
habilitations sont rangées dans **Compatibilité des anciens circuits**. Lorsqu’une
copie contient une règle affectée uniquement à une fonction, remplacer ce mode
par un rôle, un utilisateur ou des responsables avant de publier. Le moteur
continue à traiter les soumissions et les versions historiques existantes.

L’évaluateur commun est dans `workflow/rules.py` ; il ne connaît ni les modèles
d’achat, ni les réservations. Un type d’opération déclare ses champs typés et
fournit ses valeurs. L’adaptateur DA se trouve dans `purchasing/rule_adapter.py`.
La version conserve le type d’opération et l’unicité de sa version active.

Pour les futurs transferts, ajouter un adaptateur (montant, CDF source,
destination, etc.), son cycle de validation et ses contrôles transactionnels.
Les transferts ne sont pas proposés tant que ce module n’existe pas. Le moteur
accepte aussi des groupes ET/OU imbriqués ; l’éditeur actuel propose un groupe
ET ou OU par règle, avec plusieurs règles cumulables.

## Recette du nouvel éditeur

| Cas | Attendu |
|---|---|
| Ligne 100 € HTVA dans une DA de deux lignes identiques ; seuil ligne 150 €, puis seuil total 150 € | Seule la condition sur le total correspond |
| Montant TVAC exactement au seuil, puis juste en dessous | Comparaison supérieure ou égale respecte la frontière |
| Conditions CDF ET montant, puis CDF OU support | Toutes les conditions sont nécessaires en ET ; une suffit en OU |
| Deux règles correspondantes au même ordre, puis une règle à l’ordre suivant | Deux étapes parallèles ; l’ordre suivant attend leur validation |
| Aucun responsable ou aucun membre actif du rôle | Simulation indique l’absence de candidat ; aucune approbation silencieuse |
| Simulation d’un brouillon | Aucune réservation, étape ou notification créée |
| Modification d’une version publiée | Refus ; copie en brouillon possible |
| Compte sans permission de configuration, ou simulation de la DA d’un tiers sans droit de lecture financière ni droit de lecture global | Accès refusé |
| Règle sans condition et option « Toujours » décochée | Enregistrement refusé |
| Règle sans correspondance pour une ligne | Soumission refusée sans réservation partielle |
