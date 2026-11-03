# Recette complète depuis une base vierge

État du périmètre : 3 novembre 2026. Ce document décrit les tests à réaliser ; il ne constitue pas un compte rendu de tests exécutés.

Classeur de suivi : [BF_ERP_Recette_Complete_Enrichie.xlsx](BF_ERP_Recette_Complete_Enrichie.xlsx), également disponible au format ODS. Les résultats déjà saisis sont conservés ; les nouveaux tests RSP-01 à RSP-15 et les tests ADM-07/08, absents de l’ancien classeur, commencent au statut **Non exécuté**. Un statut conservé reste le résultat de l’exécution antérieure : si la procédure a changé, consigner séparément le retest et sa date. ADM-07/08 se réalisent après le parcours nominal, sur des données de test dédiées, en respectant leurs précautions.

Présentation du produit : [Synthèse de l’application](SYNTHESE_APPLICATION.md).

## 1. Conditions de départ

- Base de recette dédiée, sans donnée métier, avec uniquement le compte administrateur actif, équipe et superutilisateur. Les permissions et tables techniques Django existent après migration.
- Utiliser le compte administrateur et son mot de passe existants. Les autres comptes ci-dessous sont à créer.
- Ne pas exécuter `seed_purchase_demo` : les données sont créées manuellement dans cette campagne. Ce document ne réinitialise aucune base.
- Démarrer avec `.\demarrer-recette.cmd`, puis ouvrir http://127.0.0.1:8000/connexion/. Le lanceur utilise `db.demo.sqlite3`, applique les migrations et ne charge pas de données de démonstration.
- Utiliser des sessions distinctes par profil ou se déconnecter entre les comptes.
- Les accès personnels **Mes validations** (cloche) et **Mes délégations** (remplacements) se trouvent en haut à droite, dans toutes les rubriques. Le badge de la cloche indique le nombre d’étapes actuellement traitables, y compris comme remplaçant ; il est actualisé au chargement des pages et absent lorsque le compteur est nul. Ces accès ne figurent plus dans le sous-menu Achats.
- Année budgétaire : année civile courante, soit 2026 pour cette campagne. Adapter si nécessaire : la soumission utilise l’année courante.
- Exécuter les sections 2 à 6 dans l’ordre. Ensuite, créer une DA neuve par variante et rétablir les droits/configurations après chaque essai.

Pour chaque test, noter : identifiant, testeur, compte, date, DA/version, résultat observé, preuve et statut **OK / KO / Bloqué / Non exécuté**. Un refus attendu est un succès du test.

## 2. Administrateur — comptes et rôles

### ADM-01 — Connexion initiale

1. Hors connexion, ouvrir une page métier : connexion exigée.
2. Essayer un mauvais mot de passe : refus.
3. Se connecter comme administrateur ; ouvrir Configuration et l’administration technique.
4. Vérifier les libellés français de l’accueil, des modèles, des champs, des filtres et des confirmations. Contrôler notamment Fonctions de validation, Habilitations, Fournisseurs, Bons de commande, Étapes de validation et Notifications de validation. Les actions du journal et les états d’envoi des courriels doivent également être affichés en français ; les codes techniques contenus dans les données d’audit restent des identifiants.
4. Vérifier l’absence d’autres comptes et de données métier ; consigner tout écart.

Attendu : accès administrateur opérationnel ; aucune donnée métier créée au simple démarrage.

### ADM-02 — Créer le rôle budgétiste

Dans **Configuration → Rôles ERP → Ajouter**, créer `BUDGETISTE`, libellé « Budgétiste », avec les permissions suivantes :

| Permission | Usage |
|---|---|
| `budgeting.add_annualenvelope` | Créer l’enveloppe annuelle |
| `budgeting.add_envelopeversion` | Créer une version |
| `budgeting.change_envelopeversion` | Modifier/publier un brouillon |
| `budgeting.add_allocation` | Ajouter des allocations |
| `budgeting.change_allocation` | Modifier des allocations |
| `budgeting.delete_allocation` | Supprimer des allocations du brouillon |
| `budgeting.add_budgetproduct` | Créer les BI |
| `purchasing.add_detailedproduct` | Créer les produits détaillés |
| `budgeting.view_budget_balances` | Consulter les disponibilités budgétaires |

Les six premières permissions sont toutes nécessaires à l’espace de gestion des versions. Les droits des enveloppes, versions, allocations et produits budgétaires figurent sous **Budgets**. Les quatre droits des **produits détaillés** (ajout, modification, consultation, suppression) figurent sous **Achats** (`purchasing`). Les libellés sont en français. Les anciennes entrées sont retirées des sélecteurs et les attributions existantes aux utilisateurs, rôles et groupes sont transférées. Les codes techniques restent utilisables dans cette documentation.

Attendu : rôle enregistré avec ses permissions ; code de rôle dupliqué refusé.

### ADM-03 — Créer le budgétiste

1. **Configuration → Comptes utilisateurs et droits individuels → Ajouter** : créer `rec.budget` avec un mot de passe de recette.
2. Attribuer `BUDGETISTE` dans **Rôles ERP**, enregistrer puis rouvrir la fiche.
3. Vérifier Actif coché, Équipe et Superutilisateur décochés, aucune permission individuelle.
4. Se connecter avec ce compte : pages budgétaires accessibles ; `/admin/` refusé.

Attendu : droits hérités du rôle sans statut équipe. Ce statut est nécessaire pour les écrans Django, pas pour les pages métier.

### ADM-04 — Créer les autres profils

Comme administrateur, créer les rôles et comptes suivants, actifs, sans statut équipe ni superutilisateur :

| Rôle | Permissions | Comptes |
|---|---|---|
| `DEMANDEUR` | `purchasing.add_purchaserequest` | `rec.demandeur`, `rec.autre` |
| `VALID_CDF` | `purchasing.view_purchase_financial` | `rec.cdf`, `rec.cdf2` |
| `VALID_FINANCE` | `purchasing.view_purchase_financial` | `rec.finance` |
| `SUIVI` | `purchasing.monitor_purchases` uniquement | `rec.suivi` |
| `LECTURE_DA` | `purchasing.view_all_purchase_requests` uniquement | `rec.lecture` |
| Aucun | Aucune | `rec.sansdroit`, `rec.delegue` |

Attendu : chaque compte se connecte et conserve ses rôles. Utiliser les rôles ERP : les groupes Django ne sont plus proposés dans l’interface.

Le droit financier permet ici une lecture globale, sans donner à lui seul le droit d’approuver. « Toutes les demandes » permet la lecture des DA et BC avec montants, mais pas du tableau budgétaire global.

L’onglet **Budget** est visible dès que le compte possède au moins une permission de la catégorie **Budgets** (`budgeting.*`), directement ou via ses rôles/groupes. Sans permission dans cette catégorie, l’onglet est masqué et son accueil refuse l’accès direct. Chaque action conserve ses propres contrôles : voir l’onglet ne donne pas tous les droits budgétaires. Vérifier l’apparition puis la disparition de l’onglet lors de l’attribution et du retrait du dernier droit de cette catégorie.

La même règle s’applique à **Achats** (`purchasing.*`) : le budgétiste sans droit de cette catégorie ne voit ni l’onglet ni son sous-menu. À la connexion, il est orienté vers Budget. **Configuration** exige un droit sur les comptes/accès, l’historique, les référentiels fournisseurs ou les paramètres de validation ; le statut équipe seul ne suffit pas. Sans droit de rubrique, le compte est orienté vers ses validations. Les deux icônes personnelles restent accessibles indépendamment des droits de rubrique. Tester également les droits hérités d’un rôle et le retrait du dernier droit.

**Les rôles `VALID_CDF` et `VALID_FINANCE` ne sont pas nécessaires pour valider en mode responsables CDF/support.** Dans ce tableau, ils servent uniquement à attribuer la permission de lecture financière aux comptes de recette ; leurs noms sont historiques. Ils peuvent être remplacés par un seul rôle de lecture financière ou par une permission individuelle. Les conserver ici permet de suivre les autres scénarios, notamment la variante de validation par rôle de la section 10, sans modifier les comptes déjà préparés.

L’éligibilité aux étapes CDF/support vient des affectations dans **Configuration → Responsables des CDF et des supports**. Les comptes `rec.cdf`, `rec.cdf2` et `rec.finance` restent utiles comme acteurs de test. Dans le circuit nominal CFG-01, Finance est encore un utilisateur nommé avec habilitation ; dans le circuit CDF → support de la section 17, il valide grâce à son affectation au support, sans rôle ni habilitation supplémentaire.

### ADM-05 — Retrait et cumul des droits

1. Retirer le rôle de rec.budget : gestion des versions refusée à la requête suivante. Rétablir.
2. Retirer la permission de création de BI du rôle : création refusée. Rétablir.
3. Accorder cette permission directement au compte puis la retirer du rôle : accès conservé par le droit direct. Revenir à la configuration initiale.
4. Dans la fiche de rec.sansdroit, **décocher Actif**, puis enregistrer. Se déconnecter et essayer de se reconnecter avec le bon mot de passe : connexion refusée avec le message **« Ce compte est désactivé. Contactez votre administrateur. »**. Avec un mauvais mot de passe, le message reste **« Identifiants de connexion incorrects. »**. Recocher Actif après le test et vérifier que la connexion fonctionne à nouveau. Retirer les rôles et permissions ne désactive pas le compte.

Attendu : droits directs et hérités cumulés ; retirer une source ne supprime pas les autres.

Un compte **actif**, même sans rôle ni permission, peut se connecter : il arrive sur **Mes validations**, avec les accès personnels aux validations et délégations, sans menu de rubrique. Cela ne lui donne aucun droit budgétaire. Une éventuelle affectation comme responsable CDF/support ou une délégation valide peut encore lui permettre de traiter des validations : ces affectations sont distinctes des rôles ERP. Pour tester l’interdiction de connexion au point 4, il faut désactiver le compte avec la case **Actif**.

### ADM-06 — Déconnexion après inactivité

1. Comme administrateur système (superutilisateur), ouvrir **Configuration → Déconnexion automatique** : valeur par défaut 120 minutes.
2. Pour le test, régler à 1 minute et enregistrer. Comme budgétiste, ouvrir une page, puis ne plus naviguer ni enregistrer pendant plus d’une minute.
3. Vérifier le retour automatique à la connexion dans un onglet ouvert (contrôle toutes les 15 secondes, également au retour sur l’onglet). Essayer une URL protégée et un enregistrement depuis un ancien formulaire : connexion exigée, aucune modification exécutée.
4. Se reconnecter et effectuer une navigation avant chaque minute écoulée : la session reste active. Les autres onglets partagent la même session.
5. Essayer le réglage comme budgétiste et comme compte équipe non superutilisateur : refus côté serveur. Essayer 0, une valeur négative ou plus de 10 080 minutes : refus.
6. Réduire la durée pendant qu’un autre compte est connecté : nouvelle limite appliquée à sa prochaine requête, sans nouvelle connexion préalable.
7. Rétablir **120 minutes** et vérifier la conservation du réglage après rechargement.

L’activité correspond aux requêtes utilisateur (navigation, enregistrement), pas aux mouvements de souris ni à une saisie non enregistrée. Le contrôle automatique de l’état de connexion ne prolonge pas la session. Les anciennes sessions sans suivi d’activité sont évaluées à partir de leur expiration initiale. Sans JavaScript ou pendant une suspension du navigateur, le refus côté serveur reste effectif dès la prochaine requête.

### ADM-07 — Supprimer un utilisateur en conservant les traces

À exécuter après le parcours nominal, avec des comptes de test distincts des acteurs nécessaires à la suite de la campagne.

1. Créer un compte de test, lui faire créer une DA puis réaliser un cycle complet avec des valideurs de test. Noter les identifiants du compte, de la DA et du BC.
2. Comme superadministrateur, ouvrir **Configuration → Journal des actions par utilisateur** ; filtrer sur ce compte. Vérifier ses actions, leurs dates et détails ; tester le tri par utilisateur et date.
3. Dans les comptes utilisateurs, supprimer le demandeur avec confirmation. Vérifier que le compte a disparu mais que DA, BC et engagement existent encore.
4. Revenir au journal : le nom et l’identifiant d’origine restent consultables et filtrables. L’historique du détail de la DA garde le nom de l’acteur d’origine.
5. Supprimer un valideur ayant approuvé : la preuve et la commande subsistent. Sur une autre DA en attente, supprimer le candidat puis actualiser : étape à affecter, réservation conservée.
6. Tester un circuit avec valideur nommé supprimé : une nouvelle soumission ne doit pas attribuer automatiquement son étape aux autres utilisateurs habilités.
7. Recréer un compte portant le même nom : les traces restent distinguées par l’identifiant. Tester aussi la suppression de plusieurs comptes depuis la liste.
8. Comme compte équipe non superutilisateur, même avec `delete_user`, essayer la suppression et l’accès au journal : refus. Comme superadministrateur, vérifier que le journal n’offre ni modification ni suppression.

Les événements historiques non enregistrés avant cette évolution ne peuvent pas être reconstitués. Les traces existantes des événements métier et de l’administration sont reprises par la migration. La suppression d’utilisateur ne supprime aucune donnée de recette automatiquement lors de l’installation de cette évolution.

## 3. Référentiels

### ADM-08 — Suppression de maintenance dans les autres tables

À réaliser en fin de campagne, sur des données réservées à ces essais : les dépendances obligatoires figurant dans la confirmation seront également supprimées.

1. Comme superadministrateur, ouvrir **Configuration → Rôles ERP** : vérifier le lien **Supprimer** sur chaque ligne et l’action de suppression de la fiche.
2. Créer un rôle, l’attribuer à un utilisateur et le supprimer avec confirmation : rôle et appartenance retirés, utilisateur conservé, trace `maintenance.deleted` consultable dans le journal.
3. Répéter sur un fournisseur, un CDF, un financement, un BI et un produit détaillé de test. Vérifier d’abord le détail des dépendances affichées ; revenir en arrière ne doit rien supprimer.
4. Tester une version budgétaire publiée : les allocations et autres dépendances obligatoires sont détaillées ; après confirmation, elles sont supprimées et la référence de version active est détachée si nécessaire.
5. Tester les listes des règles, allocations, habilitations, responsables CDF, étapes, commandes et événements métier : lien de suppression disponible au superadministrateur, y compris sur les tables en lecture seule.
6. Supprimer une étape d’une DA en cours : cycle arrêté, réservations libérées, DA soumise revenue en correction ; aucune commande créée automatiquement. Corriger puis resoumettre reconstruit un cycle.
7. Supprimer un rôle utilisé par une règle : les anciens candidats ne peuvent pas approuver grâce à une habilitation de remplacement implicite ; la règle concernée n’est plus applicable sur une nouvelle soumission tant qu’elle n’est pas remplacée.
8. Sélectionner plusieurs rôles de test et utiliser la suppression groupée : vérifier la confirmation, la suppression et les traces de chaque enregistrement.
9. Comme utilisateur ordinaire, tenter l’URL de suppression d’une table en lecture seule : refus. Les permissions habituelles ne donnent pas accès au mode de maintenance.
10. Vérifier que **Journal des actions** ne propose aucun bouton de suppression et conserve les traces après les suppressions des autres tables.

En cas de données liées créées simultanément pendant l’opération, un échec de contrainte doit annuler la transaction plutôt que laisser des liens cassés. Les contrôles de concurrence et les protections PostgreSQL restent couverts par les tests techniques.

### REF-01 — Administrateur

Dans **Configuration → Administration et référentiels techniques**, créer :

| Type | Code | Données |
|---|---|---|
| CDF | `REC-CDF-A` | Centre A |
| CDF | `REC-CDF-B` | Centre B |
| Financement | `REC-FONDS` | Financement de recette |
| Financement | `REC-SANS-BUDGET` | Sans allocation |
| Fournisseur | `REC-FOURN` | Fournisseur fictif de recette |
| Fournisseur | `REC-FOURN-2` | Second fournisseur fictif |
| Fonction de validation | `REC-CDF` | Validation CDF, position 10 |
| Fonction de validation | `REC-FINANCE` | Validation Finance, position 20 |

Attendu : données disponibles dans les formulaires ; codes dupliqués refusés ; positions de fonctions uniques. Tester aussi ajout, modification et relecture d’un contact et d’une adresse fournisseur dans l’administration.

### REF-02 — Budgétiste

1. **Budget → Produits budgétaires** : créer `REC-BI` / Fournitures et `REC-BI-2` / Équipement.
2. **Achats → Produits détaillés** : créer `REC-PAPIER` / Papier A4 rattaché à REC-BI et `REC-EQUIPEMENT` rattaché à REC-BI-2.
3. Essayer un code dupliqué et des champs obligatoires vides.

Attendu : rattachement au BI visible ; données invalides refusées sans création partielle.

### REF-03 — Restrictions

Avec rec.demandeur et rec.sansdroit, essayer les URL de création de BI et produits détaillés : refus côté serveur. Avec rec.budget, essayer de créer une DA : refus avec son seul rôle.

## 4. Budgétiste — premier budget

Utiliser les **versions budgétaires achats**. Les anciennes tables Budget/BudgetLine ne pilotent pas ce flux ; leurs compteurs ne sont pas importés.

| ID | Action | Attendu |
|---|---|---|
| BUD-01 | Budget → Créer une version : année 2026, nom REC-V1 | Brouillon créé |
| BUD-02 | Alimenter une version : REC-BI / A / REC-FONDS = 10 000 € ; REC-BI / B / REC-FONDS = 2 000 € ; enregistrer | Deux allocations TVAC |
| BUD-03 | Modifier une ligne ; ajouter/enregistrer/supprimer une allocation temporaire sur REC-BI-2 ; rétablir BUD-02 | Édition possible en brouillon |
| BUD-04 | Doublon BI/CDF/financement puis montant négatif | Erreurs, aucune allocation invalide |
| BUD-05 | Créer une version temporaire vide et publier | Publication refusée |
| BUD-06 | Revenir à REC-V1, enregistrer puis Publier et activer | Active ; disponible A = 10 000 €, B = 2 000 € |
| BUD-07 | Modifier une allocation publiée | Refus : immuable |
| BUD-08 | Vérifier un budget : REC-V1, REC-BI, A, REC-FONDS puis REC-SANS-BUDGET | Disponible 10 000 € ; absence d’allocation signalée pour l’autre combinaison |

Ne pas publier d’autre version avant la fin du parcours nominal.

## 5. Administrateur — habilitations et circuit

### HAB-01 — Habilitations

Dans **Configuration → Habilitations de validation**, créer des habilitations activées, début dans le passé, fin vide. Dates en heure de Bruxelles.

| Utilisateur | Fonction | CDF | Financement | BI |
|---|---|---|---|---|
| rec.cdf | REC-CDF | A | REC-FONDS | REC-BI |
| rec.cdf2 | REC-CDF | A et B | REC-FONDS | REC-BI |
| rec.finance | REC-FINANCE | A et B | REC-FONDS | REC-BI |

Attendu : version courante visible ; fin antérieure ou égale au début refusée. Critères combinés par ET, valeurs d’un même critère par OU ; un critère vide ne le restreint pas.

### HAB-02 — Responsables des CDF et des supports

**Configuration → Responsables des CDF et des supports** : sélectionner rec.cdf pour A et rec.cdf2 pour B, puis enregistrer chaque fiche. Pour REC-FONDS, sélectionner rec.finance. Rouvrir la page pour vérifier la persistance.

Attendu : plusieurs responsables actifs peuvent être sélectionnés sur une même fiche ; une sélection vide est autorisée. Les comptes inactifs ne sont pas proposés. Ce nouvel écran ne gère pas de périodes : les contrôles historiques de dates restent couverts séparément par les tests techniques. L’affectation donne le droit de valider les étapes correspondantes sans rôle ni habilitation de fonction supplémentaire ; elle n’attribue pas de permission de lecture financière globale.

### CFG-01 — Circuit nominal

Dans l’administration, créer une **Configuration des validations** REC-CIRCUIT-V1 avec deux règles :

| Champ | Règle CDF | Règle Finance |
|---|---|---|
| Fonction | REC-CDF | REC-FINANCE |
| Niveau | 1 | 2 |
| Mode / priorité | Cumulative / 0 | Cumulative / 0 |
| Minimum / maximum HTVA | 0 / vide | 0 / vide |
| Critères CDF/financement/BI | Vides | Vides |
| Responsable CDF | Coché | Décoché |
| Responsables du support | Décoché | Décoché |
| Utilisateur nommé | Vide | rec.finance |
| Rôle valideur | Vide | Vide |

Enregistrer, revenir dans la liste, sélectionner la configuration et l’action **Valider et activer la configuration sélectionnée**.

Attendu : publiée, active et immuable. Niveau 1 : responsable configuré du CDF de la ligne, sans habilitation supplémentaire ; niveau 2 : Finance nommé et habilité. Le statut superutilisateur ne remplace pas une éligibilité métier. Le parcours CDF → support est testé dans la section 17.

## 6. Parcours nominal par profil

### ACH-01 — Demandeur : créer et compléter

Avec rec.demandeur : **Achats → Mes demandes → Nouvelle demande**, fournisseur REC-FOURN. Noter **DA-NOMINALE = …**, puis ajouter :

| Produit | Description | Quantité | Prix HTVA | TVA | CDF | Financement |
|---|---|---:|---:|---:|---|---|
| REC-PAPIER | Ramettes A4 | 10 | 5 € | 21 % | A | REC-FONDS |
| REC-PAPIER | Papier ateliers | 2 | 25 € | 21 % | A | REC-FONDS |

Attendu : brouillon du demandeur ; BI déduit du produit ; 100 € HTVA + 21 € TVA = 121 € TVAC ; aucune réservation. Tester modification fournisseur, modification ligne et ajout/suppression ligne temporaire, puis revenir aux données ci-dessus. Vérifier l’historique.

### ACH-02 — Demandeur : soumettre

Cliquer **Soumettre pour validation** puis confirmer.

Attendu : toute la DA soumise et non modifiable ; A réservé = 121 €, engagé = 0 €, disponible = **9 879 €** ; aucun BC. Rafraîchir/répéter ne double pas la réservation.

### ACH-03 — Autres profils : visibilité

| Profil | Action | Attendu |
|---|---|---|
| rec.autre | Mes demandes puis URL de DA-NOMINALE | Absente de sa liste ; détail refusé |
| rec.finance | Traiter niveau 2 avant niveau 1 | Refus |
| rec.suivi | Suivi administrateur ; filtres numéro/état | Étapes et acteurs, sans fournisseur, description commerciale ou montant |
| rec.lecture | Toutes les demandes ; détail | Lecture avec montants ; aucune modification pour autrui |
| rec.sansdroit | URL création DA, suivi, gestion budgets, configuration | Refus côté serveur |

### ACH-04 — CDF : approuver

rec.cdf : **Mes validations → Traiter → Approuver** pour chaque ligne ; actualiser entre décisions.

Attendu : Finance accessible ligne par ligne ; une seule ligne approuvée ne commande pas la DA. Réservé 121 €, disponible 9 879 €. Auteur, responsable représenté, source CDF et périmètre de la décision conservés.

### ACH-05 — Finance, demandeur et budgétiste

1. rec.finance approuve chaque ligne.
2. Demandeur : ouvrir le BC ; imprimer ou enregistrer en PDF via le navigateur.
3. Budgétiste : vérifier Budgets et disponibilités. Lecteur : ouvrir le BC.

Attendu : DA commandée ; un seul BC numéroté de 121 € ; A réservé = **0 €**, engagé = **121 €**, disponible = **9 879 €**. Aucune deuxième déduction. DA commandée non modifiable ; annulation du BC hors périmètre.

### ACH-06 — Administrateur : document figé

Modifier le nom fournisseur et le libellé produit après commande, rouvrir le BC puis rétablir les libellés.

Attendu : le BC conserve les données figées à la soumission.

## 7. Demandeur et valideurs — erreurs et sorties

Nouvelle DA par test. Relever le disponible D avant chaque essai : toute libération complète doit rendre D. Le BC nominal reste engagé.

| ID | Actions | Attendu |
|---|---|---|
| ERR-01 | Soumettre sans ligne | Refus sans réservation |
| ERR-02 | TVA vide puis explicite 0 % | Vide refusé ; 0 % accepté |
| ERR-03 | Quantité nulle/négative, prix négatif, champ requis vide | Refus sans effet partiel |
| ERR-04 | Deux lignes sur A de chacune 60 % de D TVAC ; soumettre | Refus sur cumul ; aucune réservation |
| ERR-05 | Une ligne budgétée et une REC-SANS-BUDGET | Échec global ; aucune réservation partielle |
| ERR-06 | DA A de 20 000 € HTVA à 21 % | Budget insuffisant ; brouillon conservé |
| ERR-07 | Deux onglets sur le même brouillon ; enregistrer A puis B sans recharger | Conflit ; modification récente non écrasée |
| COR-01 | DA soumise 121 € ; correction sans motif puis avec motif | Motif exigé ; toute la DA en correction ; 121 € libérés ; ancien cycle arrêté et conservé |
| COR-02 | Modifier/ajouter/supprimer des lignes après correction puis resoumettre | Nouveau cycle selon règles/habilitations courantes ; réservation nouveau total ; historique conservé |
| REJ-01 | Rejet sans motif puis avec motif | Motif exigé ; rejet définitif, budget libéré ; ni édition ni resoumission |
| ANN-01 | Annuler un brouillon puis réessayer | Annulation sans double effet |
| ANN-02 | Annuler après soumission avant BC | Étapes arrêtées, budget libéré ; pas de BC ultérieur |
| SEC-01 | Autre demandeur/lecteur : modifier, annuler ou soumettre la DA d’autrui par URL | Refus ; données et budget inchangés |

Terminer ou annuler COR-02 pour éviter une réservation oubliée.

## 8. Administrateur — habilitations et réaffectation

Pour HAB-03 à HAB-05 et REA-01/02, copier le circuit nominal en brouillon, décocher « Responsable CDF » au niveau 1, laisser rôle et utilisateur nommé vides, puis publier : ce circuit teste les habilitations de fonction. HAB-06 peut être testé dans les deux modes. Pour HAB-07, réactiver une copie du circuit nominal en mode responsable CDF. Utiliser des DA A neuves et rétablir les droits après chaque test.

| ID | Actions | Attendu |
|---|---|---|
| HAB-03 | Après soumission, publier une version désactivée de l’habilitation CDF ; actualiser les validations | Étape bloquée, anomalie au suivi, décision refusée ; réservation conservée |
| HAB-04 | Republier une version active et valide | Déblocage sans approbation implicite sans preuve ; anciennes versions conservées |
| HAB-05 | Retirer A du périmètre ou placer les dates hors période courante | Décision hors périmètre/période refusée |
| HAB-06 | Désactiver le compte valideur après soumission | Compte inutilisable pour décider ; réservation conservée |
| REA-01 | Suivi administrateur : réaffecter une étape accessible à rec.cdf2 avec motif | Acteur actif/habilité au périmètre ; tâches mises à jour sans nouveau cycle ni réservation |
| REA-02 | Réaffecter sans motif, à un non-habilité ou comme rec.suivi | Refus ; affectation conservée. Le suivi ne donne pas `purchasing.reassign_approvals` |
| HAB-07 | Sur une DA en mode responsable CDF, remplacer rec.cdf par rec.cdf2 sur A ; actualiser Mes validations ; soumettre une autre DA | Étapes non approuvées existantes et nouvelles affectées à rec.cdf2 ; ancien responsable refusé ; décisions déjà approuvées conservées |

Compléter les bornes de dates et périmètres par les tests techniques : deux habilitations partielles ne doivent pas être fusionnées pour couvrir artificiellement une ligne.

## 9. Valideur et délégué — délégations

Créer une nouvelle DA A soumise sous le circuit nominal. Ouvrir **Mes délégations** avec l’icône de remplacement en haut à droite : cet accès personnel reste disponible depuis Achats, Budget et Configuration, même sans droit d’achat.

| ID | Actions | Attendu |
|---|---|---|
| DEL-01 | rec.cdf : Mes délégations, rec.delegue, période englobant maintenant | Délégation globale ; étapes du titulaire accessibles au délégué |
| DEL-02 | rec.delegue approuve une ligne | Décision au nom du titulaire ; acteur réel conservé ; affectation CDF actuelle du titulaire contrôlée |
| DEL-03 | Sur une autre DA en mode responsable CDF, retirer le titulaire des responsables du CDF ; actualiser ; essayer comme délégué | Refus ; pas de contournement du retrait. En mode habilitation, répéter en désactivant l’habilitation du titulaire |
| DEL-04 | Délégation vers soi, dates inversées, périodes sortantes chevauchantes, chaîne CDF → délégué → autre | Configurations invalides refusées ; aucune chaîne composée implicitement |
| DEL-05 | Sur un titulaire de test disponible, délégation future ou terminée ; essayer hors période | Aucun droit transmis hors période |

Le délégué sans droit financier n’acquiert pas automatiquement l’accès aux détails et BC. Pour reprendre avec le titulaire, attendre la fin de période ou utiliser un autre valideur ; l’interface actuelle ne propose pas de parcours de révocation à tester ici.

## 10. Validation par rôle ERP

### ROL-01 — Préparation

1. Créer rec.role1 et rec.role2, actifs, rôle VALID_CDF, sans habilitation individuelle.
2. Copier le circuit nominal en brouillon REC-CIRCUIT-ROLES.
3. Au niveau 1, sélectionner VALID_CDF ; décocher responsable CDF et laisser utilisateur nommé vide. Garder Finance au niveau 2.
4. Publier puis soumettre une DA neuve.

Attendu : les membres actifs du rôle à la soumission sont candidats, même sans habilitation individuelle ; première approbation clôturant l’étape ; rôle et utilisateur représenté conservés dans la preuve.

| ID | Actions | Attendu |
|---|---|---|
| ROL-02 | Deux membres décident la même étape | Une seule décision ; aucun doublon |
| ROL-03 | Retirer le rôle d’un candidat avant décision | Refus, y compris via délégation ; les droits de lecture hérités peuvent aussi disparaître |
| ROL-04 | Ajouter un nouveau membre après soumission | Pas automatiquement candidat des étapes existantes ; candidat des nouvelles soumissions |
| ROL-05 | Réaffecter explicitement une étape accessible au nouveau membre actif | Possible si contrôles du mode rôle satisfaits ; traçabilité conservée |
| ROL-06 | Publier un circuit sur un rôle sans membre ; soumettre | Étape à affecter, réservation conservée ; ajouter un membre puis réaffecter explicitement |
| ROL-07 | Publier une règle combinant rôle et utilisateur nommé ou responsable CDF | Refus ; configuration active précédente conservée |

Rétablir les rôles et publier une copie du circuit nominal pour les essais suivants qui le nécessitent.

## 11. Administrateur — règles avancées

Utiliser des copies de configuration, des DA neuves et des acteurs éligibles. Noter la configuration active pour chaque essai.

| ID | Configuration / action | Attendu |
|---|---|---|
| CFG-02 | Nouvelle configuration publiée pendant une DA soumise | Une seule active ; nouvelles DA sur nouveau circuit ; ancien cycle conservé |
| CFG-03 | Règle minimum 100 €, maximum 110 € HTVA ; DA 99,99 / 100 / 109,99 / 110 € | Applicable seulement à 100 et 109,99 ; sans autre règle, refus sans réservation |
| CFG-04 | Même règle ; deux lignes de 50 € HTVA à 21 % | Seuil sur 100 € HTVA global, pas 50 € par ligne ni 121 € TVAC |
| CFG-05 | Règles filtrées CDF/financement/BI ; DA multilignes | Critères non financiers évalués par ligne |
| CFG-06 | Règles cumulatives puis exclusives de priorités différentes | Cumul respecté ; exclusives arbitrées par priorité, la plus grande gagnant |
| CFG-07 | Exclusives ambiguës de même priorité ou ordre fonctions/niveaux incohérent | Publication refusée sans remplacer la configuration active |
| CFG-08 | Même acteur habilité aux deux niveaux ; approbation manuelle au premier | Preuve réutilisée aux étapes éligibles de cette même ligne avec traçabilité |
| CFG-09 | Acteur seulement candidat au premier niveau, approuvé par un autre | Candidature seule insuffisante comme preuve au niveau suivant |
| CFG-10 | Deux étapes éligibles au même niveau pour même acteur et ligne | Une preuve manuelle réutilisée ; aucune double déduction |
| CFG-11 | Décider au niveau futur ou comme admin sans éligibilité métier | Refus sans contournement par URL |

## 12. Budgétiste — changements de version et déficit

Relever R (réservations) et E (engagements) réels avant chaque essai. Disponible = **allocation active − R − E**. Une nouvelle version contient des totaux, pas des variations.

| ID | Actions | Attendu |
|---|---|---|
| VER-01 | Garder une DA A réservée ; publier REC-V2 même année, A = 12 000 €, B = 2 000 € | REC-V2 seule active ; écritures antérieures conservées ; disponible A = 12 000 − R − E |
| VER-02 | Modifier une version publiée active ou remplacée | Refus : historique immuable |
| VER-03 | Vérifier budget sur version active, remplacée puis brouillon | Allocation de la version choisie et écritures de son enveloppe annuelle ; aucune activation par consultation |
| VER-04 | Publier A inférieur à R + E | Activation autorisée, déficit visible ; nouvelles réservations refusées |
| VER-05 | Terminer une DA réservée avant déficit | Conversion en engagement autorisée sans deuxième déduction |
| VER-06 | Omettre A encore réservé/engagé d’une nouvelle version, conserver B | A reste visible avec allocation nulle et déficit ; nouvelles réservations refusées |
| VER-07 | Créer un budget d’autre année puis soumettre pendant l’année courante | Soumission toujours sur l’année courante |

Publier ensuite une version suffisamment dotée et rapprocher les soldes.

## 13. Confidentialité et notifications

### SEC-02 — Matrice par profil

Tester menus et URL directes ; un lien masqué seul ne suffit pas. Cette matrice suppose les rôles initiaux sans ajouts temporaires.

| Profil | Accès autorisés à vérifier | Refus à vérifier |
|---|---|---|
| Administrateur | Configuration, référentiels, suivi, réaffectation, lecture globale | Décision sans éligibilité ; modification DA d’autrui |
| Budgétiste | Versions, BI, produits détaillés, disponibilités budgétaires | Admin Django, création DA, détails/BC d’autrui sans droit achats distinct, réaffectation |
| Demandeur | Ses DA, édition selon statut, ses BC | DA d’autrui, tableau financier global, configuration |
| CDF / Finance | Décisions éligibles, lecture financière globale des achats | Édition DA d’autrui, niveau futur, réaffectation, tableau budgétaire sans droit distinct |
| Suivi | Suivi opérationnel et filtres | Détails DA, BC, tableau financier global, réaffectation |
| Lecture DA | Toutes les demandes, détails et BC avec montants | Édition/soumission d’autrui, tableau financier global |
| Sans droit | Accueil, pages validations/délégations sans décision non autorisée | Création DA, gestion budgets, configuration, suivi |

**Particularité actuelle à tester :** tout utilisateur connecté peut utiliser **Vérifier un budget**, y compris Suivi et Sans droit. Le refus du tableau global ne signifie donc pas absence de toute information budgétaire ponctuelle.

### SUI-01 — Suivi opérationnel

rec.suivi : filtrer des DA en attente, bloquées et à affecter par numéro/état ; examiner l’écran et le contenu HTML.

Attendu : étapes, acteurs et états visibles, sans fournisseur, description commerciale ni montant. Le suivi seul ne permet ni décision ni réaffectation.

### NOT-01 — Notifications

1. Soumettre une DA : contrôler les notifications des acteurs concernés dans Mes validations.
2. Approuver : contrôler les tâches du niveau suivant.
3. Tester correction, rejet et blocage sur des DA distinctes.
   Vérifier aussi la cloche en haut à droite depuis les différentes rubriques : badge uniquement pour les étapes que le compte peut traiter maintenant, jamais pour un niveau futur ou une étape terminée. Contrôler son apparition après affectation ou délégation active, sa diminution après décision et sa disparition après retrait du droit ou du remplacement. Un compte sans tâche conserve l’icône sans badge. Tester les deux icônes au clavier et sur écran étroit ; elles doivent rester accessibles sans passer par Achats. Les anciennes URL restent utilisables.
4. Exécuter :

```powershell
.\.venv\Scripts\python.exe manage.py process_purchase_notifications --settings=config.demo_settings
```

Attendu : notifications pertinentes pour leurs destinataires ; courriels visibles en console de recette ; messages obsolètes non envoyés. La commande actualise aussi les habilitations. Simuler une panne d’envoi dans les tests techniques : elle ne doit pas annuler une décision.

Aucun rappel fondé sur la seule ancienneté. Après échec permanent, `--recover` réexamine les messages pertinents. Livraison SMTP exactement une fois non garantie en cas d’arrêt entre envoi et confirmation ; reprise automatique complète et alerte d’exploitation restent à compléter.

## 14. Vérifications techniques complémentaires

À exécuter par le responsable technique et à consigner. Aucune exécution n’est attestée ici.

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py check --settings=config.demo_settings
```

| ID | Contrôles | Tests existants |
|---|---|---|
| TEC-01 | Droits par rôle, cumul/retrait, compte inactif, libellés français de l’administration | accounts/test_role_permissions.py ; accounts/test_admin_french.py |
| TEC-02 | Habilitations, bornes de dates, périmètres ET/OU, modifications périmées | accounts/tests.py |
| TEC-03 | Responsables CDF, périodes, confidentialité | budgeting/tests.py |
| TEC-04 | Montants exacts, TVA, propriété, révisions, audit, connexion, CSRF | purchasing/tests.py |
| TEC-05 | Versions budgétaires, produits, permissions | purchasing/test_budget_workspace.py |
| TEC-06 | Flux, seuils, preuves, rôles, délégations, documents, notifications | purchasing/test_flow.py |
| TEC-07 | Concurrence, double soumission, décisions simultanées, verrou annuel, historique SQL | purchasing/test_flow_postgresql.py |
| TEC-08 | Habilitations immuables en SQL et affectations CDF concurrentes | accounts/test_postgresql.py ; budgeting/test_postgresql.py |

TEC-07/08 nécessitent PostgreSQL : SQLite ne démontre pas ces garanties. Configurer TEST_PG_DATABASE, TEST_PG_USER, TEST_PG_PASSWORD, TEST_PG_HOST, TEST_PG_PORT sur une instance dédiée. Django crée puis supprime une base de tests : ne jamais utiliser une base de production nommée comme base de tests.

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.postgresql_test_settings
```

Attendus : réservations concurrentes sans dépassement ; un seul BC et engagement après décisions simultanées ; aucune écriture doublée après double soumission ; verrou cohérent publication/réservation ; protections SQL contre la réécriture des historiques. Deux onglets ne remplacent pas ces tests.

## 15. Hors périmètre actuel

- Réceptions, factures, rapprochements comptables.
- Annulation de BC, régularisations d’engagement, avenants TVA, ajustements approuvés.
- Alertes automatiques de déficit BUD-019/020/021.
- Exports SUI-003 et suivants, archivage des notifications informatives.
- Clôture annuelle et règles comptables, de stock ou vente non implémentées.
- Restriction financière par périmètre ; finalisation des notifications et du durcissement d’exploitation.

Cette campagne couvre **DA → commande** et sa configuration ; elle ne vaut pas validation de toute la spécification ERP ni accord de mise en production.

## 16. Registre et clôture

Dupliquer une ligne pour chaque test et variante :

| ID / variante | Testeur / compte | Date | DA / BC / version | Statut | Observé / preuve / anomalie |
|---|---|---|---|---|---|
| ADM-01 | | | | Non exécuté | |
| … | | | | Non exécuté | |

Pour une anomalie : reproduction, attendu, observé, message exact/capture et impact. Ne pas consigner les mots de passe.

Avant clôture :

- Chaque scénario applicable a un résultat et chaque blocage une explication.
- Allocations, réservations et engagements sont rapprochés ; chaque réservation restante est identifiée par DA.
- Anomalies ouvertes et réserves d’acceptation sont consignées.
- Circuit actif, budget actif et droits temporaires restant à retirer sont relevés.
- Bilan daté et validé par les responsables métier et technique.


## 17. Responsables par CDF et par support

Dans **Configuration → Responsables des CDF et des supports**, sélectionner un ou plusieurs utilisateurs actifs pour chaque CDF et support, puis enregistrer la fiche concernée.

Dans une nouvelle version du workflow, utiliser **Affecter au responsable CDF** ou **Affecter aux responsables du support** à la place du rôle valideur. Choisir un seul mode d’affectation par règle, puis publier la version. Les versions déjà publiées doivent être copiées en brouillon avant modification.

Préparation : conserver le circuit nominal, puis en publier une copie REC-CDF-SUPPORT avec deux règles cumulatives : REC-CDF au niveau 1 en mode responsable CDF ; REC-FINANCE au niveau 2 en mode responsables du support. Rôle et utilisateur nommé restent vides. Utiliser des responsables distincts entre niveaux pour vérifier la séquence. « Support » correspond au champ Financement de la ligne de DA. Créer REC-FONDS-2 et ses allocations sur A et B dans une nouvelle version budgétaire avant le test multiligne. Utiliser une DA neuve par variante, relever le disponible et annuler ou terminer les demandes de test après chaque essai.

| ID | Actions | Attendu |
|---|---|---|
| RSP-01 | Administrateur : attribuer rec.cdf à A, rec.cdf2 à B et rec.finance à REC-FONDS ; enregistrer chaque fiche ; rouvrir | Affectations persistantes et indépendantes entre CDF et supports |
| RSP-02 | Compte sans budgeting.manage_cost_center_managers : ouvrir puis envoyer directement un formulaire vers /configuration/responsables/ | GET et POST refusés ; aucune affectation modifiée |
| RSP-03 | Affecter deux utilisateurs actifs au même CDF puis au même support ; enregistrer ; désactiver un compte temporaire et tenter de le sélectionner | Sélection multiple acceptée ; compte inactif absent des choix et refusé à l’enregistrement |
| RSP-04 | Copier le circuit nominal ; configurer CDF niveau 1 et support niveau 2, sans rôle ni utilisateur nommé ; publier | Nouvelle version active, précédente conservée ; aucun changement des étapes déjà soumises sous l’ancienne version |
| RSP-05 | Retirer les rôles valideurs et habilitations de fonction aux responsables de test en conservant les droits de connexion ; soumettre une DA A / REC-FONDS | Responsable de A éligible au niveau 1 ; responsable du support non autorisé à décider au niveau 2 avant la validation CDF |
| RSP-06 | Approuver le niveau CDF ; actualiser Mes validations et notifications du responsable de REC-FONDS ; approuver le support | Tâche support accessible au bon niveau ; DA commandée après toutes les validations ; réservation convertie une seule fois en engagement |
| RSP-07 | Soumettre deux lignes A / REC-FONDS et B / REC-FONDS-2, avec responsables distincts pour chaque CDF et support | Chaque ligne est affectée à ses propres responsables ; un responsable étranger au CDF/support de la ligne ne peut pas décider |
| RSP-08 | Configurer deux responsables distincts sur A ; soumettre ; faire approuver l’étape par le premier puis tenter avec le second | Une seule approbation suffit pour cette étape ; seconde décision refusée sans double engagement |
| RSP-09 | Vider les responsables de A puis soumettre ; rétablir A, vider ceux du support, soumettre une autre DA et approuver le CDF | Au niveau accessible sans responsable : étape à affecter, signalement au suivi/administrateurs, budget réservé ; aucun BC prématuré |
| RSP-10 | Sur une étape à affecter, ajouter un responsable actif ; actualiser Mes validations | Étape en attente, nouveau responsable candidat et averti, décision possible sans nouvelle soumission ni nouvelle réservation |
| RSP-11 | Remplacer un responsable pendant une étape en attente ; actualiser puis essayer avec ancien et nouveau comptes | Nouveau responsable autorisé et averti ; ancien refusé, ancienne notification inactive ; historique et réservation conservés |
| RSP-12 | Désactiver le seul responsable avant décision ; actualiser ; réactiver puis actualiser | Compte inactif non éligible ; étape à affecter, pas de validation ; reprise possible après réactivation et actualisation |
| RSP-13 | Sur une DA neuve, déléguer du responsable CDF à rec.delegue ; décider comme délégué ; sur une autre DA retirer le titulaire des responsables et réessayer | Délégation valide utilisable avec traçabilité de l’acteur réel et du titulaire ; retrait de l’affectation interdit toute nouvelle décision déléguée |
| RSP-14 | Approuver le CDF puis changer ses responsables ; actualiser la DA et contrôler historique, montants et étape support | Décision CDF approuvée conservée ; aucune nouvelle réservation ; étape support suit ses propres responsables actuels |
| RSP-15 | Dans des brouillons séparés, combiner CDF et support, puis responsable et rôle, puis responsable et utilisateur nommé ; tenter de publier | Publication refusée pour chaque combinaison ; configuration active précédente inchangée |

Rétablir les affectations de HAB-02 et le circuit voulu après la campagne. Les tests de réutilisation d’une preuve par un même acteur aux deux niveaux restent décrits dans CFG-08/10 ; une telle preuve peut approuver automatiquement une autre étape éligible de la même ligne.

Les responsables CDF historiques dont la période est active sont repris par la migration. Les étapes des soumissions antérieures conservent leur mode historique ; les nouvelles soumissions suivent la version du workflow active.
