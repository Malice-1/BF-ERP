# Réception des demandes d’achat dans le stock

Le menu **Stocks → Réceptions des achats** permet de réceptionner les produits des demandes **validées et commandées**, disposant d’un bon de commande. Il utilise le droit existant `receiving.manage_stock`. Un lien « Réceptionner les produits » est également disponible sur la fiche d’une demande commandée pour les utilisateurs disposant de ce droit.

Choisir la demande, le dépôt de réception et la référence du bon de livraison ou un commentaire. Saisir les quantités effectivement livrées pour chaque ligne ; laisser zéro pour les produits non livrés. Chaque réception peut être partielle et les livraisons successives peuvent alimenter différents dépôts. Les produits sont ceux des lignes de la demande, et les quantités maximales sont celles du bon de commande validé.

L’enregistrement crée une réception liée au bon de commande et à la demande, ainsi qu’une entrée de stock par ligne livrée. Le mouvement conserve le lien avec la réception et la demande, visible dans l’historique et dans son export Excel. Le dépôt, l’auteur, la date et la référence sont conservés. La réception, ses lignes et les mouvements sont immuables.

Les listes des demandes et leurs fiches affichent le suivi physique séparément de leur statut de validation :

- **Non réceptionnée** : aucune quantité reçue pour la demande.
- **Partiellement réceptionnée** : une partie des produits a été reçue.
- **Réceptionnée** : toutes les quantités commandées ont été reçues.

La fiche présente également ce suivi par ligne, avec les quantités réceptionnées, le reste à recevoir et l’historique des réceptions. Les exports des demandes et de leurs lignes incluent ces informations. La réception ne change ni le statut « Commandée », ni les engagements budgétaires, ni les validations.

Les contrôles sont effectués côté serveur : droit de gestion du stock, demande commandée, appartenance des lignes à cette demande, quantités positives et plafond du reste à recevoir. Un double envoi identique ne crée aucune réception supplémentaire ; un envoi différent avec le même identifiant est refusé. L’opération est atomique : une erreur annule la réception entière, ses lignes, les mouvements de stock et la journalisation.

Une entrée manuelle, une sortie, un transfert entre dépôts ou un inventaire ne modifie pas les quantités déjà réceptionnées d’une demande. Le suivi physique décrit les livraisons reçues, indépendamment du stock encore disponible.

Les utilisateurs chargés du stock peuvent consulter les produits et quantités nécessaires à la réception sans obtenir accès aux prix ni aux écrans financiers des demandes. Les demandeurs conservent la consultation du suivi sur leurs demandes. La réception des marchandises déjà présentes dans le stock avant cette fonctionnalité n’est pas déduite automatiquement des anciennes entrées manuelles.

## Vérification fonctionnelle

1. Valider une demande de cinq unités pour obtenir un bon de commande.
2. Dans Stocks → Réceptions des achats, enregistrer deux unités dans un dépôt : le stock augmente de deux et la demande devient « Partiellement réceptionnée », avec trois unités restantes.
3. Tenter une réception de quatre unités : refus, sans nouvelle réception ni mouvement de stock.
4. Réceptionner les trois unités restantes : la demande devient « Réceptionnée ».
5. Vérifier les liens dans les mouvements de stock, l’historique sur la demande et les données exportées en Excel.
