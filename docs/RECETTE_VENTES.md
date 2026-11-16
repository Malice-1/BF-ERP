# Recette du module Ventes

Utiliser une base QA, un compte superutilisateur puis un compte dépourvu de droits
Ventes. Ne pas saisir de coordonnées réelles dans un scénario de test.

| Cas | Procédure | Attendu |
| --- | --- | --- |
| CA-001 | Créer un client actif et une commande avec deux formations | Brouillon, numéro CV unique, HT/TVA/TTC corrects |
| CA-002 | Confirmer ; tenter de modifier la commande | État confirmé ; modification bloquée côté serveur |
| CA-003 | Configurer l'émetteur et le format PDF ; facturer | Une facture FV, deux lignes figées, PDF téléchargeable |
| CA-004 | Configurer des identifiants Peppol de test valides ; facturer en XML | XML UBL, validation XSD/EN16931/Peppol effective, version et date visibles |
| CA-005 | Effacer un identifiant Peppol ou une adresse obligatoire | Émission bloquée avec champs manquants ; aucune facture créée |
| CA-006 | Répéter la facturation d'une même commande | Aucune seconde facture |
| CA-007 | Exécuter le test PostgreSQL simultané | Une émission réussie, une demande refusée, un seul numéro/fichier |
| CA-008 | Modifier le client et l'émetteur après facturation ; régénérer | Anciennes coordonnées et format conservés |
| CA-009 | Confirmer puis facturer des formations | Aucun mouvement de stock supplémentaire |
| CA-010 | Consulter facture, commande et historique | Références, montants, fichiers, validations et opérations retrouvables |
| CA-011 | Essayer une émission avec le compte sans droit | Refus HTTP 403 et refus du service métier |
| CA-012 | Générer un XML valide | Aucune transmission ni mention d'envoi Peppol |
| CA-013 | Exécuter les campagnes existantes | Régressions Achats, Budget, Stocks, sessions et thème absentes |

Cas complémentaires :

- Quantité nulle, prix négatif, remise excessive, régime fiscal incohérent : refus.
- Catalogue : sélectionner une formation et vérifier description/unité préremplies.
- Ajouter et supprimer des lignes ; vérifier l'estimation puis les montants serveur.
- Plusieurs très petites lignes : somme des TVA de ligne égale à la ventilation.
- Révision périmée dans un second onglet : refus sans perte de données enregistrées.
- Commande annulée : confirmation et facturation impossibles.
- Erreur de stockage simulée : numéro conservé, `DOCUMENT_ERROR`, reprise possible.
- Règles XML absentes, expirées ou altérées : validation indisponible, émission bloquée.
- XML structurellement valide avec total falsifié : erreur Schematron détaillée.
- Paiement partiel puis solde : états partiellement payée puis payée.
- Répétition d'un paiement avec le même jeton : aucun doublon.
- Neutralisation justifiée : historique conservé et solde recalculé.
- Document altéré : téléchargement bloqué ; document d'une autre facture : 404.
- Utilisateur éditeur client sans configuration de facturation : champs protégés.
- Formulaire soumis sans CSRF : refus.
- Suivi : dates de commande, facture et paiement filtrées indépendamment ; aucune
  variation des écritures budgétaires de dépense.
- Interface en thèmes clair/sombre, largeur mobile, navigation clavier et erreurs.

Les tests automatisés sont dans `sales/tests.py` et `sales/test_postgresql.py`.
La recette visuelle doit être renseignée par le testeur ; un test HTTP réussi
ne constitue pas une validation du rendu dans tous les navigateurs.
