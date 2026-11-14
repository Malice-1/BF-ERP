# Architecture et réalisation ERP — première analyse

**État actuel :** le parcours DA → commande est maintenant disponible pour recette. Ce document conserve l’analyse historique ; consulter [RECETTE_ACHATS.md](RECETTE_ACHATS.md) pour le fonctionnement livré et ses limites.

**Nettoyage du 12 novembre 2026 :** les services budgétaires historiques et le moteur
de règles mentionnés dans l’inventaire ci-dessous ont été retirés. Les applications
squelettes `accounting` et `documents` ont également été retirées. Le parcours actuel
utilise les validations fixes décrites dans [REGLES_VALIDATION.md](REGLES_VALIDATION.md).

Référence : `SPEC_ERP_CODEX_V0_1.md`, version 0.1 du 14 octobre 2026.
Pour une vue actuelle du produit construit, consulter [la synthèse de l’application](SYNTHESE_APPLICATION.md).
Ce document distingue propositions techniques, exigences validées et couverture réelle.
Décision complémentaire du demandeur : éviter les arrondis. Les calculs sont décimaux exacts sans quantification intermédiaire.

**Mise à jour après le lot 0b :** le document ci-dessous conserve l'inventaire initial et le plan cible. Les habilitations versionnées, fonctions ordonnées, affectations CDF et écrans de brouillons sont désormais implémentés. Consulter `LOT_0B.md` pour la couverture actuelle, les protections SQL et les limites restantes. Les mutations de demandes/lignes dans l'administration sont désormais désactivées au profit des services métier.

## 1. Inventaire du dépôt

| Domaine | Présent | Écart par rapport à la spécification |
|---|---|---|
| Identité | User Django personnalisé, Role, groupes/permissions Django | Pas de fonctions ordonnées, habilitations datées/versionnées/périmétrées, délégations |
| Fournisseurs | Fournisseur, contacts, adresses, migrations et administration | Référentiel minimal réutilisable ; référentiel détaillé à spécifier |
| Référentiels budget | CDF, financement, produit budgétaire, produit détaillé | Pas de responsables CDF datés |
| Budget | Budget avec année/actif ; BudgetLine avec allocation/engagé/consommé | Pas de versions annuelles ni réservations/engagements individualisés ; disponibilité incompatible BUD-006 |
| Achats | Demande, lignes, fournisseur et demandeur ; administration Django | Pas de soumission, règles, commande, document ou validations |
| Workflow | Initialement vide | Moteur, preuves, anomalies et affectations manquants |
| Réceptions, documents, comptabilité | Applications squelettes | Ne pas interpréter comme modules opérationnels |
| Interface | Administration Django uniquement | Pas de parcours métier par rôle ; vues applicatives vides |
| Tests | Initialement fichiers squelettes | Aucune recette métier ni concurrence existante |
| Configuration | Django 5.2.15, PostgreSQL, utilisateur personnalisé | Paramètres de développement ; exploitation à cadrer |

Constats sur le code historique :
- `approve_purchase_request` contournait toute validation par ligne et toute réservation ; remplacement par un refus explicite dans cet incrément.
- `commit_budget` modifie un objet en mémoire sans sauvegarde ni verrou ; le contrôle ligne par ligne ne protège pas une combinaison partagée. Ce service historique reste à remplacer, ne pas l'utiliser pour un flux métier.
- `Budget.save` désactive tous les autres budgets, sans portée annuelle et sans transaction commune garantie. À remplacer par une activation explicite verrouillée.
- `available_amount` soustrait engagé et consommé ; ce n'est pas la formule BUD-006. Une reprise des valeurs historiques doit être définie avant bascule.
- Pas de commande/document déjà présents à reprendre.
- `purchasing/admin.py` était déjà modifié localement avant intervention ; ces modifications ont été conservées.

## 2. Architecture proposée

Conserver un monolithe modulaire Django/PostgreSQL. Aucun besoin établi ne justifie des microservices ou une seconde application frontend à ce stade. Les premières interfaces métier peuvent utiliser vues/formulaires/templates Django, avec protections serveur identiques pour toute future API.

- `accounts` : fonctions de validation ordonnées, habilitations, délégations et politiques d'accès.
- `budgeting` : CDF/responsables, référentiels, budgets versionnés, allocations et écritures de réservation/engagement.
- `purchasing` : demandes/lignes, transitions, commandes/lignes, documents et futurs avenants.
- `workflow` : configurations versionnées, compilation des règles, instantanés, niveaux/étapes, preuves et audit.
- Applications notifications/exports à créer au lot concerné ; files durables et travailleurs à choisir selon infrastructure validée.
- `receiving` : seulement le périmètre nécessaire et spécifié au rapprochement ; `accounting` reste en attente.

Services de commande explicites avec acteur et révision attendue. Chaque commande contrôle permissions puis verrouille les agrégats concernés. Les lectures passent par des sélecteurs filtrés selon le droit opérationnel ou financier. Les modèles ne portent pas de transitions implicites dans `save`.

Transactions PostgreSQL : verrou demande, puis ressources dans ordre stable ; toutes les écritures et événements audit/outbox dans la même transaction. Verrouiller les combinaisons budgétaires stables et le budget annuel, pas seulement une allocation d'une version : un changement de version ne doit pas contourner le verrou de disponibilité. Verrou commun entre activation annuelle et réservation. Une contrainte unique assure une commande par demande et une conversion par réservation.

Notifications par outbox durable ; un échec d'envoi ne peut annuler la transaction métier. Réessais techniques distincts des politiques métier de relance d'export non validées. Pas de rappel lié à l'ancienneté.

Audit append-only via les services. En production, ajouter une protection de base de données contre UPDATE/DELETE des tables d'historique et des droits SQL adaptés ; les modèles Django seuls ne garantissent pas cette immutabilité.

## 3. Modèle relationnel cible

| Ensemble | Entités, cardinalités et invariants |
|---|---|
| Identité | User M:N Role ; ValidationFunction avec ordre global unique ; Authorization → User/fonction, version, validité, périmètre ; versions publiées immuables |
| Périmètre | Critères CDF/financement/catégorie/produit ; ET entre critères, OU entre valeurs ; une Authorization complète suffit à elle seule, jamais fusion de permissions partielles (HAB-002) |
| Organisation | CostCenter 1:N ManagerAssignment datées ; absence permise ; exclusion PostgreSQL des intervalles se chevauchant (ORG-001) |
| Délégations | Delegation délégant → délégué, intervalle global ; acteur réel et origine conservés dans la preuve ; remplacement administratif explicite et audité |
| Budget | AnnualBudget(year) 1:N BudgetVersion ; référence à une version active unique ; versions antérieures immuables |
| Imputation | BudgetCombination unique produit budgétaire × CDF × financement ; BudgetAllocation unique version × combinaison |
| Demande | PurchaseRequest → demandeur/fournisseur ; 1:N PurchaseRequestLine → produit détaillé/CDF/financement ; TVA explicite, état et révision |
| Configuration | WorkflowConfiguration 1:N versions ; Rule(mode exclusif/cumulatif, priorité, conditions) → prescriptions de fonctions/niveaux ; validation avant activation |
| Exécution | Demande 1:N SubmissionSnapshot ; snapshot 1:N LineSnapshot ; chaque ligne 1:N niveaux ; niveau 1:N étapes parallèles ; affectations et paramètres figés, même si référentiels changent |
| Preuves | ManualApprovalEvidence unique snapshot-ligne × utilisateur réel ; preuves HAB-003 par étape satisfaite : fonction, autorisation/version, périmètre, acteur, date et délégation ; auto-satisfaction référence la preuve manuelle |
| Budget ouvert | Reservation → snapshot-ligne/combinaison/version origine, montant TVAC, état ; Commitment → ligne commande/combinaison/version origine ; liens uniques de conversion, pas de double débit |
| Commande | Demande 0:1 PurchaseOrder ; commande 1:N lignes avec valeurs/imputations historiques ; document durable versionné lié à la commande |
| Administration | Anomaly avec clé de déduplication et cycle ouvert/clos ; réaffectation historisée, justification et contrôle d'habilitation |
| Événements | AuditEvent et OutboxEvent ; Notification → événement/destinataire ; NotificationDelivery par canal |
| Extensions validées | Regularization, Amendment, BudgetAdjustment ; Invoice/InvoiceLine/MatchingRun/ToleranceVersion ; ExportJob/ExportFile/RetentionVersion aux lots suivants |

Les clés existantes BigAutoField sont conservées. Les identifiants d'objets sont stables ; références d'affichage non séquentielles pour les demandes dans le premier incrément (proposition technique, sans valeur comptable). Les snapshots doivent copier les libellés et valeurs utiles en plus des références pour ne pas dépendre de référentiels modifiables.

Argent : Decimal uniquement. Quantité et prix actuels ont chacun deux décimales, taux TVA quatre ; le produit HTVA peut avoir quatre décimales et TVA/TVAC dix. Avant réservation, élargir le stockage budgétaire (proposition DecimalField 24,10) et borner tailles des agrégats ; ne pas quantifier à deux décimales. L'éventuel traitement des montants de facture déjà exprimés en centimes relève du rapprochement ultérieur, sans modifier silencieusement les engagements.

## 4. Machines à états

Demande :
`DRAFT → SUBMITTED → ORDERED`.
`SUBMITTED → CORRECTION → SUBMITTED` : invalider fonctionnellement l'ancien snapshot, libérer toutes les réservations ; reconstruire complètement avec configuration courante.
`SUBMITTED → REJECTED` : archive définitive, aucune réouverture/duplication.
`DRAFT/CORRECTION/SUBMITTED → CANCELLED` par demandeur avant commande ; libération des réservations et arrêt du workflow.
Aucune modification de ligne pendant SUBMITTED ni dans un état terminal.

Étape : `NOT_ACCESSIBLE → PENDING / WAITING_ASSIGNMENT / BLOCKED_AUTHORIZATION → APPROVED` (manuelle ou automatique avec preuve). Les niveaux sont séquentiels ; étapes d'un niveau parallèles ; lignes parallèles. Une absence d'affectation n'arrête pas les autres étapes accessibles mais empêche la commande. Perte/restauration d'habilitation : blocage/déblocage, pas d'approbation implicite.

Snapshot : actif, terminé ou invalidé ; décisions anciennes restent stockées. Une approbation réelle peut satisfaire plusieurs étapes du niveau courant puis les étapes ultérieures devenues accessibles, avec contrôle d'éligibilité courant pour chacune. L'éligibilité seule n'est jamais une preuve.

Réservation : ouverte → convertie ou libérée. Engagement : ouvert, partiellement régularisé, totalement régularisé. Annuler une commande n'en libère pas l'engagement (BUD-008).

Configuration : brouillon → validée/active → remplacée ; activation incohérente refusée sans changer la version active.

## 5. Lots et critères de sortie

| Lot | Travail | Dépendances / recette |
|---|---|---|
| 0a livré | Brouillons via services, identifiant, TVA exacte, révision, audit, tests isolés | Couverture partielle ACH-001/003/004/005 et contraintes transversales |
| 0b | Habilitations versionnées, périmètres, fonctions ordonnées, responsables CDF, délégations, contraintes SQL, interface brouillons protégée | HAB-001/002/003, ORG-001 ; tests permissions et bornes temporelles |
| 1a | Budgets annuels/versionnés, combinaisons, allocations, réservations, disponibilité multi-version ; activation et signalement déficits | Nécessaire à la soumission ; T-001/002/008/012 ; migration contrôlée des anciens compteurs |
| 1b | Configuration règles et activation cohérente ; snapshots, niveaux/étapes ; soumission tout-ou-rien | ACH-016/018/026–031 ; absence de règle bloque sans réservation ; absence de valideur réserve et attend |
| 1c | Approbation par ligne, preuves, déduplication acteur réel, correction/rejet/annulation ; commande/document et conversion atomique | ACH-007–025, BUD-007 ; T-003/004/005/006 sous PostgreSQL |
| 1d | Réaffectations, perte/restauration d'habilitation, anomalies, outbox et notifications associées | ACH-032/033, HAB-004–007, NOT-001–008 ; T-007/018 |
| 2 | Régularisations à deux personnes, avenants TVA, ajustements, déficits et alertes complets | BUD-008–021 ; T-009 ; calcul libérable dépend des obligations/réceptions/factures |
| 3 | Réceptions nécessaires au rapprochement, factures/avoirs, tolérances globales versionnées et recontrôles | FAC-001–011 ; T-010/011 ; rester dans le périmètre spécifié |
| 4 | Suivi opérationnel, droits financiers séparés, exports CSV/XLSX/PDF et cycle de vie durable | SUI-001–012 ; T-013–018 ; aucune politique de relance d'export inventée |

Chaque lot fournit migrations additives, contrôles serveur, interface adaptée, tests et traçabilité exigences. Les lots 1c/1d ne sont pas publiables comme module complet sans notifications et anomalies obligatoires.

## 6. Migrations et validation

1. Migrations actuelles additives : révision/horodatage, numéro par défaut, choix d'états, TVA nullable pour préserver les lignes historiques, AuditEvent.
2. Recenser valeurs historiques d'états et TVA avant toute contrainte supplémentaire ; pas de taux fiscal supposé. Les nouveaux services exigent un taux explicite.
3. Ajouter structures cibles budget/workflow sans écraser les tables existantes ; décider la reprise des compteurs engagés/consommés avec leurs pièces justificatives. Ne pas fabriquer un historique de réservations.
4. Import contrôlé, comparaison des soldes, puis bascule vers les services ; retirer anciens chemins de mutation une fois remplacés.
5. PostgreSQL : tests TransactionTestCase avec connexions indépendantes et synchronisation pour réservation concurrente, premier approbateur gagnant, commande unique, réaffectation et activation de version.
6. Tests de confidentialité sur sélecteurs, écrans, exports et réponses API ; séparer vue opérationnelle et vue financière.

Commandes de vérification du premier incrément :
```
.venv\Scripts\python.exe manage.py test --settings=config.test_settings
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.venv\Scripts\python.exe manage.py check --settings=config.test_settings
```
Les tests SQLite isolés ne valident pas les verrous PostgreSQL. Les migrations n'ont pas été appliquées à la base configurée. Après revue/sauvegarde selon l'environnement : `manage.py migrate` sur la base cible.

## 7. Couverture et limites de l'incrément livré

- ACH-001 partiel : création brouillon/lignes avec CDF, financement, TVA ; montants exacts ; pas de soumission ni commande.
- ACH-003/005 partiel : refus de modification par les services pour état rejeté/terminal/en validation ; seul demandeur actif admis. Le cycle de rejet/correction complet reste à réaliser.
- ACH-004 partiel : annulation idempotente du brouillon et d'une demande en correction ; annulation en validation attend le service de libération de réservations.
- Audit transactionnel : création, ajout de ligne, annulation ; révision et acteur. Pas encore d'audit global immuable protégé en SQL.
- L'ancien raccourci d'approbation refuse toute action : aucune fausse approbation ne peut être obtenue par ce service.
- Administration Django historique et accès ORM direct ne passent pas par ces services : ils ne constituent pas une interface métier conforme ; durcissement à réaliser avant exposition à des utilisateurs. Aucun écran métier ou API nouveau n'est publié dans cet incrément.
- Modification/suppression de lignes et fournisseur via commandes métier restent à réaliser au lot 0b.
- Aucun développement de comptabilité, paiements, stocks ou ventes.

## 8. Décisions et questions

Aucun choix restant ne bloque les fondations livrées. La consigne « éviter les arrondis » est appliquée aux calculs ; le stockage précis des réservations sera élargi avant leur activation.

À résoudre au lot concerné, sans bloquer le socle :
- Correspondance rôles existants/fonctions/périmètres et configurations réelles : données administratives à fournir avant usage opérationnel, aucun seuil d'exemple préchargé.
- Composition délégations multiples/en chaîne et conflits temporels : ne pas inventer une propagation illimitée ; obtenir décision avant activation de ces cas.
- Algorithme et pièces établissant les obligations contractuelles restantes (BUD-011) avant exécution des régularisations.
- Modalités des réceptions et avoirs nécessaires au rapprochement avant lot 3.
- Retry des exports en échec non validé ; aucune relance automatique ou manuelle implémentée par défaut.
- Infrastructure, courriel, stockage et reprise des données à cadrer avant mise en service.
