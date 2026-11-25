# Travailler sur BF-ERP

Lis le [README](README.md) pour démarrer depuis un clone. Utilise la [documentation fonctionnelle](docs/DOCUMENTATION_FONCTIONNELLE.md) pour comprendre le parcours concerné et le [plan de tests](docs/PLAN_TESTS.md) pour retrouver ses scénarios. Les services, migrations et tests versionnés décrivent le comportement implémenté.

## Où intervenir

| Domaine | Points d’entrée |
| --- | --- |
| Achats et validations | `purchasing/services.py` pour les demandes et leurs lignes, `purchasing/flow.py` pour la soumission, les décisions et les bons, `purchasing/flow_views.py` pour les écrans de validation. |
| Budget | `purchasing/flow_models.py` et `purchasing/budget_views.py` pour les enveloppes, versions et allocations. `purchasing/budget_analysis.py` et `purchasing/budget_pilot_views.py` pour les tableaux de bord. `budgeting/history.py` et `budgeting/transfers.py` pour les états datés et les transferts. |
| Comptabilité et ventes | `accounting/services.py` pour les écritures, `accounting/purchase_posting.py` et `accounting/sales_posting.py` pour les imputations, `accounting/fixed_assets.py` pour les immobilisations. `sales/` pour les commandes, factures et paiements clients. |
| Référentiels, stock et accès | `suppliers/` et `hr/` pour leurs référentiels. `receiving/services.py` et `receiving/purchases.py` pour le stock et les réceptions. `accounts/` pour les droits et habilitations. `workflow/` pour les journaux. |
| Interface et exports | `purchasing/templates/purchasing/base.html`, `navigation.html` dans le même dossier et `purchasing/context_processors.py` pour la structure commune. `config/excel.py` pour les exports XLSX. |

## Règles métier à préserver

- **Achats.** Une validation ordinaire porte sur la ligne choisie. La validation globale est réservée au droit correspondant et doit être explicite. Le retour pour correction et le rejet portent sur la demande entière. Le bon de commande se crée lorsque le circuit est terminé.
- **Budget.** Les montants d’achats sont suivis en TVAC. Le disponible tient compte des allocations, des réservations, des engagements et des mouvements de transfert applicables. Réutilise les calculs du domaine, y compris pour les tableaux et les exports. L’historique est fondé sur les états enregistrés.
- **Accès.** Vérifie les permissions dans les vues et services et conserve le périmètre utilisateur sur les requêtes et les exports. Un lien masqué dans le menu ne remplace pas ce contrôle. Utilise les libellés de permissions français dans `accounts/permission_labels.py` pour les nouveaux modèles.
- **Écritures et audit.** Passe par les services métier pour conserver les contrôles de révision, les transactions et le journal des actions. Les imputations d’achats et de ventes ont chacune leur paramétrage dans **Groupes comptes**. Les amortissements du registre des immobilisations sont calculés pour le suivi, puis comptabilisés manuellement dans **Écritures**.

## Développement et vérification

- Utilise `config.demo_settings` pour la démo et des jeux de données fictifs. Garde les bases locales, fichiers `.env`, identifiants et documents réels hors des commits. Vérifie le réglage de base avant d’exécuter une commande qui écrit des données.
- Lance les commandes du README avec `config.test_settings` pour les tests isolés. Pour un changement de verrouillage, de concurrence ou de contrainte propre à PostgreSQL, vérifie aussi le scénario avec `config.postgresql_test_settings`.
- Quand un modèle change, versionne sa migration et exécute `makemigrations --check --dry-run`. Pour une règle métier modifiée, mets à jour les tests concernés et les documents qui décrivent cette règle.
- Note dans le compte rendu les commandes réellement exécutées, les vérifications restantes et les décisions métier qui doivent survivre à la conversation.
