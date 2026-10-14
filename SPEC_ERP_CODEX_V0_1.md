# ERP intégré — Spécification fonctionnelle pour Codex

**Version :** 0.1 — 14 octobre 2026  
**Statut :** consolidation des décisions prises en conversation ; spécification évolutive.  
**Destinataire :** Codex / équipe de développement.  
**Contexte :** organisme de formation du secteur public belge ; remplacement d'outils fragmentés pour les achats, budgets, comptabilité, factures, stocks et ventes.

> **Consigne essentielle à Codex :** implémenter en priorité les règles **VALIDÉES** ci-dessous. Ne pas inventer de règles comptables, fiscales ou organisationnelles pour les domaines **À SPÉCIFIER**. Toute hypothèse doit être identifiée, isolée et facilement modifiable. Proposer un plan d'implémentation incrémental, des migrations, des tests et une interface adaptée aux rôles. Ne jamais assimiler les exemples chiffrés à des paramètres obligatoires.

## 1. Périmètre et statuts

- **VALIDÉ — périmètre fortement détaillé :** demandes d'achat, approbations par ligne, réservation/engagement budgétaire, versions de budgets, rapprochement des factures fournisseurs, habilitations, notifications et suivi des validations, exports.
- **PARTIELLEMENT DÉFINI :** réceptions, cycle fournisseur après validation de facture, corrections et régularisations.
- **À SPÉCIFIER :** comptabilité générale et analytique complète, paiements, stocks et inventaires, immobilisations, ventes et facturation clients, intégrations, migration, référentiels détaillés, reporting réglementaire, infrastructure.
- **HYPOTHÈSE NON VALIDÉE :** relance manuelle par le demandeur des exports différés en échec, avec contrôle des droits et audit. À ne pas traiter comme une décision métier définitive.

## 2. Modèle conceptuel minimal (à affiner)

Entités candidates : `User`, `Role`, `Authorization` (fonction, périmètre, dates, version), `Delegation`, `CostCenter` (CDF), `CostCenterManagerAssignment`, `FundingSource`, `BudgetProduct`, `AnnualBudget`, `BudgetVersion`, `BudgetAllocation`, `PurchaseRequest`, `PurchaseRequestLine`, `ApprovalWorkflowSnapshot`, `ApprovalLevel`, `ApprovalStep`, `ApprovalEvidence`, `PurchaseOrder`, `PurchaseOrderLine`, `Receipt`, `ReceiptLine`, `SupplierInvoice`, `SupplierInvoiceLine`, `CreditNote`, `BudgetReservation`, `BudgetCommitment`, `BudgetRegularization`, `PurchaseOrderAmendment`, `BudgetAdjustmentRequest`, `Notification`, `NotificationDelivery`, `AdministrativeAnomaly`, `ExportJob`, `ExportFile`, `AuditEvent`.

Prévoir identifiants stables, horodatages, références de versions, liens documentaires, contrôle de concurrence, traçabilité et opérations atomiques pour les transactions budgétaires et validations. Les relations exactes et les cardinalités non fixées restent à concevoir.

## 3. Demandes d'achat et approbations — exigences VALIDÉES

### Cycle de vie général

- Demande créée en **brouillon** ; lignes détaillées (produit, description, quantité, prix unitaire, TVA) ; chaque ligne possède son **CDF** et sa **source de financement** (ACH-001). La demande doit être validée avant émission ; une commande et son document sont créés uniquement après approbation complète.
- **BUD-001 :** soumission bloquée si budget insuffisant.
- **BUD-002 :** réservation budgétaire dès la soumission réussie.
- **ACH-003 :** rejet définitif = demande immuable et archivée ; pas de réouverture ni duplication ; libération des réservations ; nouvelle demande à créer manuellement.
- **ACH-004 :** annulation libre par le demandeur avant création de la commande ; libération des réservations, arrêt du workflow et conservation de l'historique.
- **ACH-005 :** après retour pour correction, seul le demandeur peut modifier ; aucune édition pendant la validation.
- **BUD-004 / ACH-006 / ACH-009 :** retour pour correction d'une seule ligne => arrêt de toute la demande, libération de **toutes** les réservations et invalidation fonctionnelle de toutes les approbations antérieures ; à la nouvelle soumission, contrôles et réservation atomiques de toutes les lignes, reconstruction intégrale du workflow selon les règles alors actives ; ancien historique conservé.

### Calcul et exécution des workflows

- **ACH-002 / ACH-017 :** règles configurables selon montant, CDF, financement, catégorie, produit budgétaire et autres critères retenus ; évaluées à chaque soumission.
- **ACH-007/008 :** approbation **par ligne**, même lorsque plusieurs lignes partagent un CDF.
- **ACH-009 :** lignes évaluées en parallèle ; commande créée seulement lorsque **toutes** les lignes sont approuvées.
- **ACH-010 / ACH-024 :** niveaux de validation séquentiels ; étapes d'un même niveau parallèles.
- **ACH-011 :** étape attribuable à un utilisateur nommé ou à un rôle (éventuellement contextualisé par CDF/financement).
- **ACH-012 :** lorsque plusieurs personnes éligibles partagent un rôle, **la première approbation** valide l'étape ; fermer atomiquement les tâches concurrentes.
- **ACH-013 :** délégation temporaire par le valideur ; remplacement administratif pour absence ; audit.
- **ACH-014 :** délégation globale sur une période, non sélective par CDF/rôle.
- **ACH-015 :** auto-approbation autorisée lorsque l'utilisateur est habilité, y compris par délégation ; exception pour la régularisation budgétaire (BUD-009).
- **ACH-016 :** si aucun valideur éligible à une étape requise, soumission possible avec réservation ; étape en attente d'affectation administrative ; autres étapes peuvent avancer ; commande bloquée.
- **ACH-018 :** règles exclusives et cumulatives, priorités et métadonnées versionnées.
- **ACH-019/020 :** déduplication par utilisateur réel à l'échelle d'une ligne ; une seule approbation manuelle par personne et par ligne ; historique des rôles/étapes préservé.
- **ACH-021 :** fonctions de validation ordonnées globalement (CDF, IT, Finance, Direction, etc.).
- **ACH-022/023 :** une approbation manuelle antérieure d'un utilisateur peut satisfaire automatiquement ses étapes de niveaux ultérieurs lorsqu'elles deviennent accessibles et que l'utilisateur y est éligible ; une simple éligibilité antérieure ne suffit pas.
- **ACH-025 :** plusieurs étapes parallèles d'un même niveau éligibles pour un même utilisateur sont satisfaites atomiquement par une seule approbation manuelle, avec traçabilité.
- **ACH-026 :** configuration du workflow figée/versionnée à la soumission ; nouvelle soumission après correction = règles courantes.
- **ACH-027 :** absence de règle de workflow applicable à **une** ligne bloque toute soumission, sans réservation, brouillon conservé (à distinguer de l'absence de valideur ACH-016).
- **ACH-028 :** contrôle de cohérence avant activation d'une configuration ; activation refusée si incohérente ; version active conservée ; brouillons possibles ; audit.
- **ACH-029 :** conflits non résolus entre règles exclusives => soumission intégralement bloquée, sans réservation.
- **ACH-030/031 :** seuils financiers de validation calculés sur le **montant total HTVA de la demande**, toutes lignes confondues ; critères non financiers appréciés par ligne.
- **ACH-032 :** si responsable de CDF change après soumission, approbateur initial reste affecté ; pas de réaffectation automatique. Administrateur autorisé peut réaffecter explicitement une étape encore en attente avec justification et audit ; étapes déjà approuvées préservées. À la nouvelle soumission, règles et responsable actuels.
- **ACH-033 :** réaffectation administrative uniquement à un utilisateur actif et habilité à la même fonction et au périmètre applicable ; justification obligatoire ; contrôle de concurrence ; pas de redémarrage du workflow ; audit.

## 4. Budgets, versions, réservations et engagements — VALIDÉ

- Budget annuel comportant plusieurs versions, **une seule active**. Allocations par combinaison **produit budgétaire × CDF × source de financement**.
- **BUD-003 :** commande et demandes conservent leurs imputations et références budgétaires historiques malgré changement de version.
- **BUD-005 :** contrôle et réservation sur montants **TVAC**, par ligne puis agrégés par combinaison ; TVA éventuellement différente selon ligne ; transaction tout-ou-rien.
- **BUD-006 :** disponible = allocation active − engagements ouverts de commandes − réservations de demandes soumises ; éviter tout double comptage.
- **BUD-007 :** à la création de la commande, conversion **atomique et idempotente** de réservation en engagement, sans deuxième déduction de disponibilité ; transaction commune à la création de commande.
- **BUD-008 :** annulation de commande ne libère **jamais automatiquement** son engagement, même en absence de réception/facture ; régularisation distincte.
- **BUD-009 :** régularisation budgétaire demandée et approuvée par **deux personnes distinctes** ; libération uniquement après approbation et exécution ; exception à ACH-015 ; audit et concurrence.
- **BUD-010 :** régularisation totale ou partielle, par ligne/combinaison, plusieurs régularisations successives possibles, sans dépasser le montant libérable.
- **BUD-011 :** montant libérable tient compte des réceptions, factures, notes de crédit et obligations contractuelles restantes, **sans double comptage** ; les obligations non vérifiées ne sont pas automatiquement libérables ; réduction/annulation documentée requise.
- **BUD-012 :** correction de TVA sur commande émise met à jour référence fiscale/TVAC recalculé, mais **pas automatiquement** l'engagement initial ; diminution via régularisation BUD-009 à 011 ; augmentation via avenant BUD-013/014.
- **BUD-013 :** augmentation TVAC due à correction TVA => nouveau workflow d'approbation d'avenant selon règles courantes ; conserver approbations initiales ; seuils toujours sur HTVA total ; engagement initial inchangé jusqu'à validation complète.
- **BUD-014 :** à la soumission de l'avenant, réserver atomiquement les suppléments TVAC sur toutes combinaisons ; insuffisance => tout bloquer ; à approbation complète convertir en engagement ; rejet/retour => libérer suppléments.
- **BUD-015 :** si budget insuffisant pour avenant, rester en brouillon ; permettre demande liée d'ajustement budgétaire préremplie (commande, avenant, combinaison, manque) ; aucun supplément réservé avant ajustement effectif et nouvelle soumission.
- **BUD-016 :** ajustement budgétaire approuvé préparé comme **nouvelle version annuelle**, approuvée puis activée séparément ; activation atomique remplace l'unique version active ; versions précédentes immuables.
- **BUD-017 :** engagements et réservations encore ouverts pris en compte dans la disponibilité de la nouvelle version, tout en conservant référence à version d'origine ; aucun doublon ni modification rétroactive des commandes/workflows.
- **BUD-018 :** activation autorisée même si certaines combinaisons deviennent déficitaires ; déficit signalé ; **nouvelles réservations bloquées** pour ces combinaisons ; réservations/engagements existants préservés ; conversion réservation existante en engagement permise.
- **BUD-019 :** alertes automatiques et tableau de bord des déficits par combinaison ; pas de doublons ; montant actualisé ; clôture automatique quand disponibilité redevient >= 0 ; audit.
- **BUD-020 :** alertes de déficit envoyées **uniquement au responsable CDF actif** ; finance centrale peut consulter tableau mais ne reçoit pas d'alerte automatique ; notifier résolution au responsable CDF.
- **BUD-021 :** si aucun responsable CDF actif, anomalie d'affectation envoyée à l'administrateur fonctionnel **sans détail financier** ; déficit toujours visible dans tableau approprié et nouvelles réservations bloquées ; lors d'une nomination, clôturer anomalie et transmettre déficits encore ouverts.

## 5. Factures fournisseurs et TVA — VALIDÉ / périmètre partiel

- **FAC-001 :** rapprochement commande, réceptions, facture fournisseur, avoirs et factures antérieures ; écart non autorisé => **blocage de la facture entière** ; pas de validation partielle ni dérogation sur simple justification ; correction puis nouveau contrôle. Livraisons et facturations partielles admises dans les quantités restant facturables.
- **FAC-002 :** tolérances configurables par type d'écart, versionnées et auditées.
- **FAC-003 :** tolérances **globales identiques** pour toutes factures fournisseurs.
- **FAC-004 :** factures non encore validées peuvent être recontrôlées avec configuration actualisée ; factures validées non modifiées rétroactivement ; chaque contrôle historisé.
- **FAC-005 :** recontrôle automatique à la prochaine action de progression si données/configuration ont changé ; recontrôle manuel également possible ; jamais progresser avec contrôle périmé ; échec technique bloquant.
- **FAC-006 :** administrateur fonctionnel habilité peut modifier/activer directement les tolérances globales, sans deuxième approbateur ; version active unique, historique immuable, validation des valeurs.
- **FAC-007 :** tolérances **absolues**, jamais en pourcentage ; montants en EUR ; quantités dans leur unité ; valeurs non négatives.
- **FAC-008 :** tolérances monétaires **uniquement sur les totaux de facture**, pas par ligne ; contrôles non monétaires (notamment quantité) maintenus par ligne ; différences de prix unitaire non bloquantes séparément.
- **FAC-009 :** écarts positifs et négatifs entre lignes peuvent se compenser ; contrôler écart net absolu des totaux ; écarts de lignes visibles/audités ; contrôles non monétaires indépendants.
- **FAC-010 :** deux contrôles monétaires globaux distincts : `abs(total_HTVA_facture − HTVA_attendu) <= tolérance_HTVA` ET `abs(total_TVA_facture − TVA_attendue) <= tolérance_TVA`. Compensation à l'intérieur de HTVA ou TVA, **jamais entre HTVA et TVA** ; cohérence arithmétique TVAC vérifiée, **pas** de troisième tolérance monétaire TVAC.
- **FAC-011 :** taux de TVA différent entre commande et facture => **blocage total**, quelles que soient les tolérances ; correction de référence TVA par personne autorisée avec journalisation, puis recontrôle ; aucune modification silencieuse de l'engagement budgétaire.

**Non spécifié :** modalités exactes de comptabilisation, calendrier de paiement, rapprochement bancaire, conformité de facturation électronique et autres obligations réglementaires. Ne pas présumer de leur implémentation.

## 6. Organisation et habilitations — VALIDÉ

- **ORG-001 :** un CDF a **au plus un responsable actif** à un instant donné ; affectations datées sans chevauchement ; périodes sans responsable possibles ; historique et audit.
- **HAB-001 :** habilitations par fonction de validation et périmètre configurable (CDF, financement, catégorie, etc.), globales ou restreintes, datées et versionnées ; contrôlées à l'affectation, à la réaffectation et à l'exécution.
- **HAB-002 :** critères de périmètre restreints combinés par **ET** ; plusieurs valeurs d'un critère par **OU** ; une autorisation complète doit suffire à elle seule ; ne pas recomposer artificiellement des autorisations partielles.
- **HAB-003 :** chaque approbation manuelle stocke **référence et version de l'autorisation**, périmètre évalué, acteur, date, étape, ligne et fonction, atomiquement ; choix déterministe si plusieurs autorisations ; étapes auto-satisfaites liées à la preuve d'approbation manuelle et à l'éligibilité.
- **HAB-004 :** perte d'habilitation requise sur étape en attente => étape bloquée et anomalie administrative automatique ; utilisateur ne peut plus approuver/rejeter ; autres étapes parallèles continuent ; validations antérieures et réservations conservées ; déduplication.
- **HAB-005 :** restauration de l'habilitation avant réaffectation => déblocage et clôture automatique d'anomalie si utilisateur toujours assigné et actif ; aucune approbation automatique ; pas de retour automatique après réaffectation.
- **HAB-006 :** notifier administrateur fonctionnel **et** valideur affecté pour blocage/déblocage ; **pas** le demandeur ; statut consultable sans détails sensibles ; déduplication et audit.
- **HAB-007 :** réaffectation => notifier ancien et nouveau valideur, pas le demandeur ; confirmation à l'administrateur ; tâches mises à jour atomiquement ; audit.

## 7. Notifications — VALIDÉ

- **NOT-001 :** notifications d'événements de validation visés par HAB-006/007 en **interne ET par courriel** ; même identifiant événement, statuts de canal distincts, liens vers ERP authentifié, détails sensibles limités ; échec d'envoi ne remet pas en cause l'événement métier.
- **NOT-002 :** échec courriel => nouvelles tentatives automatiques suivant politique technique configurable (nombre, délais, erreurs transitoires/définitives), file durable, journalisation ; échec permanent => anomalie technique aux administrateurs d'exploitation, pas par défaut à l'administrateur fonctionnel.
- **NOT-003 :** rétablissement du service de courriel => reprise automatique des messages en échec permanent **encore pertinents**, sans confirmation manuelle ; obsolètes non envoyés ; pas de boucle infinie.
- **NOT-004 :** pertinence évaluée **par type de notification et état métier courant** lors du renvoi ; notification obsolète => `Non renvoyé — obsolète` ; impossibilité de vérifier => ne pas envoyer.
- **NOT-005 :** règles de pertinence codées dans le logiciel, non configurables par l'administrateur ; changements par nouvelle version logicielle ; évaluation selon règle logicielle active lors du renvoi ; paramètres techniques de retry restent configurables.
- **NOT-006 :** notifications internes devenues obsolètes **retirées automatiquement de la liste active**, mais création/retrait/motif conservés dans l'audit ; compteurs actifs/non lus mis à jour ; pas de réactivation automatique d'une notification retirée.
- **NOT-007 :** archivage manuel permis **seulement pour notifications informatives** ; impossible pour notification correspondant à une action encore à accomplir par le destinataire ; archivage propre au destinataire et audité ; pas d'effet sur tâche métier.
- **NOT-008 :** **aucun rappel ni escalade automatiques du seul fait de l'ancienneté** d'une tâche en attente ; pas de réaffectation automatique liée au temps ; anomalies d'habilitation ou d'affectation continuent à être traitées selon leurs propres règles.

## 8. Suivi global des validations — VALIDÉ

- **SUI-001 :** tableau de suivi global pour administrateurs fonctionnels habilités, étapes en attente de toutes demandes/lignes, y compris étapes parallèles ; afficher demande/ligne, fonction, niveau, état, responsable, date de mise en attente, ancienneté, anomalie ; distinguer étape non encore accessible d'étape réellement en attente ; filtres et tri ; consultation ≠ pouvoir de réaffectation.
- **SUI-002 :** visibilité administrative **opérationnelle seulement** ; montants, prix, imputations, informations financières/commerciales sensibles nécessitent habilitations métier distinctes ; contrôle côté serveur et sur écrans/détails/recherche/export/API ; droits de suivi, réaffectation et lecture financière séparés.
- **SUI-003 :** export autorisé des **seules données effectivement accessibles** à l'utilisateur ; vérification au moment de la génération ; colonnes non autorisées absentes du fichier ; audit de création d'export (demandeur, paramètres, filtres, format, lignes, résultat).
- **SUI-004 :** formats **XLSX, CSV UTF-8 et PDF** ; présentation adaptée au format, encodage/échappement corrects, prévention d'injection de formules tableur, date et périmètre d'export indiqués.
- **SUI-005 :** exporter **tous les résultats filtrés et autorisés**, quelle que soit la pagination affichée ; tri conservé si applicable ; instantané cohérent ; aucune troncature silencieuse ; erreur explicite si échec/limite.
- **SUI-006 :** petit export immédiat, volumineux différé selon seuils techniques configurables par format/charge ; états `En attente`, `En cours`, `Disponible`, `En échec`, `Expiré` (+ états ultérieurs ci-dessous) ; file durable, identifiant, suivi, contrôle des droits à génération **et téléchargement**, pas de fichier partiel disponible.
- **SUI-007 :** export différé disponible => notification **interne uniquement**, **pas de courriel**, informative et archivable, lien sécurisé authentifié ; notification obsolète lorsque fichier expiré/supprimé/inaccessible ; une notification par export ; téléchargement n'entraîne pas retrait à lui seul. Cette notification d'export n'est pas dans le périmètre des notifications de validation à deux canaux de NOT-001.
- **SUI-008 :** durée de disponibilité des fichiers configurable **globalement** par administrateur habilité, commune XLSX/CSV/PDF ; délai part de la mise à disposition ; expiration rend immédiatement fichier inaccessible, suppression automatique du stockage ; audit conservé ; échecs de suppression suivis techniquement.
- **SUI-009 :** modification de durée **non rétroactive** : date d'expiration figée lors de mise à disposition, avec version du paramètre ; fichiers déjà disponibles gardent date initiale ; exports en cours utilisent paramètre actif lorsqu'ils deviennent disponibles ; fichiers expirés non réactivables.
- **SUI-010 :** suppression anticipée du fichier **par son demandeur uniquement**, après confirmation ; seulement si `Disponible` ; rendre accès impossible immédiatement, supprimer stockage, conserver audit et date d'expiration prévue ; statut `Supprimé par le demandeur` ; notification devient obsolète.
- **SUI-011 :** **aucun audit fonctionnel des téléchargements individuels** : pas de compteur, première/dernière date, ni événements pour chaque téléchargement ; conserver audit des demandes, générations, mises à disposition, expirations, suppressions et annulations. Les contrôles de sécurité restent obligatoires ; les journaux techniques de sécurité restent distincts.
- **SUI-012 :** demandeur peut **annuler** un export différé `En attente` ou `En cours`, après confirmation ; annulation atomique, interruption dès que possible, suppression fichiers temporaires, **interdiction de publier après annulation**, état final `Annulé` et audit ; si déjà `Disponible`, utiliser SUI-010 ; pas de notification de disponibilité.

### Exports en échec — point NON VALIDÉ

Dernière question non tranchée : relance manuelle, nouvelle demande obligatoire ou retry automatique. **Hypothèse de travail seulement :** relance manuelle par le demandeur, avec nouvelle vérification des droits et historique des tentatives. Ne pas intégrer une politique de retry automatique comme exigence validée.

## 9. Contraintes de conception transversales

1. **Transactions atomiques :** soumission multi-lignes, réservations, conversion en engagements, approbation, affectation, réaffectation, modification de version active.
2. **Idempotence :** événements répétés, validations concurrentes, génération de commande, conversion budgétaire, notifications, annulation/export.
3. **Historique immuable :** versions de budget/workflow/habilitation, décisions, régularisations et modifications sensibles.
4. **Contrôle d'accès côté serveur :** ne jamais considérer une colonne cachée dans l'interface comme une protection suffisante.
5. **Montants :** arithmétique décimale exacte (pas de flottants binaires pour l'argent) ; HTVA/TVA/TVAC explicites ; gestion des arrondis à spécifier.
6. **Concurrence :** verrouillage/versionnement optimiste ou autre mécanisme assurant l'absence de double approbation, double réservation et dépassement budgétaire.
7. **Confidentialité :** anomalies d'organisation sans exposition de détails financiers aux administrateurs non habilités ; notifications et liens sans informations excessives.
8. **Tests automatisés :** scénarios positifs, blocages, retours pour correction, transitions de version budgétaire, seuils HTVA, contrôle TVA, permissions, concurrence, exports.
9. **Accessibilité et ergonomie :** statuts compréhensibles, erreurs explicites, navigation selon les rôles, traces consultables selon habilitations.
10. **Réglementation :** identifier explicitement les exigences légales belges applicables avant d'implémenter les modules fiscaux/comptables non définis.

## 10. Scénarios de recette prioritaires (à automatiser)

| ID | Scénario | Résultat attendu |
|---|---|---|
| T-001 | Demande 2 lignes, budget suffisant | Réservations TVAC atomiques sur toutes combinaisons ; workflow créé |
| T-002 | Une combinaison budgétaire insuffisante | Aucune réservation ; demande reste brouillon |
| T-003 | Une ligne renvoyée pour correction après approbations d'autres lignes | Toutes réservations libérées ; approbations antérieures invalidées fonctionnellement, historique conservé |
| T-004 | Tous niveaux/étapes approuvés | Commande unique ; réservations converties atomiquement en engagements, pas de double déduction |
| T-005 | Deux approbateurs du même rôle valident simultanément | Une seule transition métier ; autres tâches fermées ; aucune double approbation |
| T-006 | Même utilisateur éligible à plusieurs étapes/niveaux | Une seule approbation manuelle par ligne ; complétions automatiques correctement tracées |
| T-007 | Perte puis restauration d'habilitation avant réaffectation | Blocage/anomalie puis déblocage automatique, sans auto-approbation |
| T-008 | Activation d'une version budgétaire déficitaire | Activation permise ; déficit signalé ; nouvelles réservations bloquées ; engagements existants maintenus |
| T-009 | Commande annulée | Engagement conservé jusqu'à régularisation distincte validée par autre personne |
| T-010 | Facture avec écarts HTVA et TVA | Vérification séparée des deux tolérances absolues ; aucune tolérance TVAC supplémentaire |
| T-011 | Taux TVA facture ≠ commande | Facture entièrement bloquée même si écarts monétaires faibles |
| T-012 | Responsable CDF absent lors d'un déficit | Anomalie administrative sans données financières ; pas d'alerte de déficit à l'administrateur |
| T-013 | Export filtré sur 10 pages | Toutes lignes filtrées/autorisées exportées dans XLSX, CSV et PDF |
| T-014 | Admin de suivi sans droit financier exporte | Aucune donnée financière dans fichier ni réponse technique |
| T-015 | Changement de durée de conservation | Exports disponibles gardent échéance initiale ; futurs fichiers prennent nouveau paramètre |
| T-016 | Demandeur annule export en cours pendant fin de génération | Aucun fichier publié si annulation gagnante ; sinon état Disponible et suppression possible ; pas d'état incohérent |
| T-017 | Téléchargements répétés | Vérification d'accès à chaque fois ; aucun événement d'audit fonctionnel de téléchargement |
| T-018 | Notification d'action devenue obsolète | Retrait automatique de liste active ; historique conservé |

## 11. Plan de réalisation recommandé (PROPOSITION, pas décision validée)

**Lot 0 — Fondations :** référentiels minimaux, identité, rôles/habilitations, audit, configuration versionnée, schéma relationnel, migrations, jeux de tests.

**Lot 1 — Achats + validation :** demandes/lignes, moteur de règles, approbations, corrections, annulations, délégations, réaffectations.

**Lot 2 — Budget :** versions/allocations, réservations/engagements, régularisations, avenants TVA, déficits/alertes.

**Lot 3 — Réceptions + factures fournisseurs :** réception, rapprochement, tolérances, blocages, recontrôles.

**Lot 4 — Suivi :** notifications, tableau administrateur, exports et cycle de vie des fichiers.

**Lots suivants à cadrer :** comptabilité générale, paiements, stocks/inventaires, ventes, interfaces et reprise des données.

## 12. Travail demandé à Codex

1. Lire ce fichier comme **source de vérité fonctionnelle provisoire**.
2. Commencer par analyser le dépôt existant ; **ne pas supposer** un framework, un schéma de base de données ou une architecture non fournis.
3. Produire un inventaire des fonctionnalités présentes/manquantes et un plan d'implémentation par lots, avec dépendances et risques.
4. Proposer le modèle de données et les machines à états en respectant les exigences numérotées.
5. Identifier les ambiguïtés **réellement bloquantes** uniquement ; proposer des hypothèses pour les détails non critiques sans les faire passer pour validées.
6. Implémenter de façon incrémentale avec migrations, contrôles d'accès, tests unitaires/intégration/concurrence et documentation.
7. Pour chaque modification, indiquer les exigences couvertes (`ACH-...`, `BUD-...`, etc.), les tests correspondants et les écarts restant ouverts.
8. **Ne pas développer la comptabilité, les stocks ou les ventes sur des règles inventées** : préparer les interfaces et dépendances, puis attendre leur spécification.

---

### Traçabilité de cette consolidation

Ce document consolide les décisions de la conversation jusqu'à **SUI-012**, ainsi que les exigences antérieures `ACH`, `BUD`, `FAC`, `ORG`, `HAB`, `NOT` et `SUI`. Il n'est pas une validation juridique, fiscale ou comptable. Les exemples sont illustratifs et les propositions non validées sont signalées.
