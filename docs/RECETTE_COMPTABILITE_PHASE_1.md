# Recette — comptabilité phase 1

Utiliser une instance QA et un plan de test sans valeur réglementaire. Le plan réel
de l'organisme public et son approbation sont nécessaires pour la mise en service.

## Profils

- Administrateur de configuration : comptes, cadre, journaux, exercices/périodes.
- Responsable autorisé à approuver le plan et à valider/contre-passer les écritures.
- Agent de saisie : ajout/modification de brouillons et consultation, sans validation.
- Lecteur : consultation seulement.
- Utilisateur sans droit Comptabilité.

Les droits peuvent être combinés pour une recette technique. La séparation effective
des fonctions doit être définie par l'organisation pour la production.

## Parcours de recette

| Cas | Action | Résultat attendu |
| --- | --- | --- |
| C01 — cadre public | Ouvrir le module sans configuration | Cadre public affiché, aucune règle fiscale ni plan d'entreprise injecté |
| C02 — plan | Saisir ou importer des comptes du plan QA | Codes, libellés, regroupements et tiers requis conservés |
| C03 — import répété | Soumettre deux fois le même CSV et sa référence | Une seule trace de fichier importé, aucun compte doublonné |
| C04 — import invalide | Mettre une ligne valide puis un indicateur postable invalide | Lot entièrement annulé, erreur visible |
| C05 — approbation | Essayer de valider une écriture sans plan approuvé | Refus, aucun numéro définitif consommé |
| C06 — revue | Renseigner entité, référence et motif ; approuver avec le responsable | Acteur, date et révision conservés |
| C07 — exercices | Créer deux exercices aux dates chevauchantes | Second exercice refusé |
| C08 — périodes | Créer une période hors exercice ou chevauchante | Refus |
| C09 — journaux | Créer journaux Achats/Ventes/financier/OD | Types distincts, codes uniques, pas d'automatisme déclenché |
| C10 — brouillon | Saisir deux lignes déséquilibrées | Brouillon enregistré sans numéro définitif |
| C11 — équilibre | Tenter de valider ce brouillon | Refus, état brouillon conservé |
| C12 — lignes | Saisir un montant négatif, trois décimales, deux côtés positifs ou une ligne nulle | Refus serveur |
| C13 — tiers | Omettre le fournisseur d'un compte qui le requiert | Refus |
| C14 — validation | Équilibrer, renseigner la pièce et valider | Numéro définitif, débit=crédit>0, acteur/date et snapshots visibles |
| C15 — répétition | Répéter la même demande de validation | Même écriture et numéro, aucun événement de validation doublonné |
| C16 — modification | Essayer de modifier une écriture validée | Refus applicatif et SQL ; aucun bouton de modification proposé |
| C17 — pièce ancienne | Poster une date comptable antérieure à la dernière date du journal/exercice | Refus ; la date de pièce peut être conservée avec une date comptable autorisée |
| C18 — période fermée | Fermer une période puis tenter une validation | Refus sans mutation ; réouverture exige droit et motif |
| C19 — contrepassation | Contre-passer avec motif et période ouverte | Nouvelle écriture inverse, lien réciproque, original conservé |
| C20 — exercice suivant | Fermer la période initiale et contre-passer dans une période du nouvel exercice | Nouvelle séquence de l'exercice, pas de réouverture silencieuse de l'ancien |
| C21 — compte historique | Désactiver un compte déjà utilisé et refaire approuver le plan | Nouvelle saisie refusée sur ce compte ; contrepassation exacte possible |
| C22 — snapshots | Modifier le libellé d'un compte ou le nom d'un tiers | Données historiques de l'écriture inchangées |
| C23 — identité légale | Modifier l'identité de l'émetteur avant une validation | Revue exigée ; réaffectation du grand livre à une autre identité légale refusée |
| C24 — maintenance | Tenter de supprimer un fournisseur lié au grand livre | Refus avant toute suppression ou détachement |
| C25 — droits | Saisie avec l'agent, validation avec l'agent puis le responsable | Agent refusé à la validation, responsable autorisé |
| C26 — utilisateur absent | Supprimer un utilisateur ayant validé une écriture | Nom historique conservé, identifiants facultatifs détachés |
| C27 — CSRF/méthode | Appeler une action en GET ou POST sans CSRF | Refus HTTP 405 ou 403 |
| C28 — concurrence | Lancer les tests PostgreSQL de validation, numérotation, clés de saisie, fermeture et contrepassation | Invariants préservés, aucun doublon ni écriture déséquilibrée |
| C29 — régression | Vérifier Achats, Stocks, Budget et Ventes | Flux inchangés ; aucune écriture comptable automatique de phase ultérieure |
| C30 — interface | Navigation clavier, thèmes clair/sombre, largeur mobile, ajout/suppression de lignes et erreurs | Rendu lisible et formulaires accessibles |

## Vérifications automatisées

`accounting/tests.py` couvre les règles métier, les formulaires HTTP, droits, CSRF,
snapshots, contrepassations et interactions avec la maintenance. Les tests SQL
d'immuabilité sont exécutés sur SQLite et PostgreSQL.

`accounting/test_postgresql.py` couvre les garanties de base cible : courses de
validation, création du compteur initial, saisies idempotentes, contrepassations,
fermeture de période concurrente, équilibre réel par SQL, chevauchements et audit.

La recette visuelle C30 et la revue du plan réel par les responsables restent à
effectuer. Les tests HTTP ne sont pas une preuve de rendu dans un navigateur réel.
