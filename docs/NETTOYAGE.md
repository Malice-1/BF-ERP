# Nettoyage de l’application — 12 novembre 2026

## Éléments retirés

53 fichiers devenus inutiles ont été supprimés, après vérification de leurs
imports, routes, références dans les templates et appels métier :

- Ancien éditeur de règles : formulaires, adaptateur, moteur de prédicats,
  cinq templates, JavaScript, CSS et tests propres au moteur retiré.
- Service de publication des anciens circuits. Les tests d’historique utilisent
  désormais un jeu de données enregistré, indépendant de cet ancien service.
- Ancien éditeur des affectations CDF datées, son template, ses formulaires,
  ses services, son sélecteur et les tests de cette fonctionnalité retirée.
- Anciens services de budget et de validation budgétaire, et raccourci
  d’approbation directe des demandes d’achat.
- Applications `accounting` et `documents`, qui ne contenaient aucun modèle
  métier ni migration. Elles ne sont plus dans `INSTALLED_APPS`.
- Modules de squelette vides : choix, constantes, sélecteurs, validateurs,
  vues, services, administrations et tests sans implémentation.
- Page statique de propositions graphiques devenue sans usage.
- Imports et branches de navigation propres aux anciennes règles et à leur
  simulation ; ancien paramètre de comptage réservé à cette simulation.

Le texte d’aide du support demandeur et la synthèse de l’application ont été
actualisés. Les anciennes recettes et notes manuelles sont identifiées comme
archives lorsqu’elles mentionnent des services ou écrans retirés.

## Éléments conservés volontairement

- Toutes les migrations, les tables et les données historiques : anciens
  budgets, circuits, règles, habilitations et affectations datées.
- Les contrôles nécessaires pour lire et traiter les validations déjà
  enregistrées, leurs décisions et leur journal.
- Les réexportations de modèles dans `purchasing.models`, nécessaires à Django
  et aux imports des autres modules ; elles ne sont pas des imports inutiles.
- Les anciens liens de règles et d’affectations : un GET redirige vers la
  configuration actuelle ; un POST renvoie 410, sans modifier les données.
- Les spécifications, archives de recette, classeurs et sauvegardes.
- Les points d’entrée chargés automatiquement par Django : configurations
  d’applications, administration, commandes et templates de surcharge.

Aucune table ni donnée métier n’a été supprimée par ce nettoyage.

## Vérifications

- Suite Django : **182 tests, 172 réussis, 10 ignorés car réservés à PostgreSQL**
  avec `manage.py test --settings=config.test_settings --noinput`.
- Les 40 templates conservés se compilent.
- `manage.py check --settings=config.demo_settings` : aucune anomalie.
- `makemigrations --check --dry-run` : aucun changement de schéma.
- `git diff --check` : aucune erreur d’espacement.
- Les tests JavaScript du thème n’ont pas pu être exécutés : Node.js n’est pas
  disponible dans cet environnement. Le script du thème n’a pas été modifié.
