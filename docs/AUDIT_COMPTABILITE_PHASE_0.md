# Comptabilité belge — diagnostic préalable et plan de phase 1

16 novembre 2026. Périmètre autorisé : diagnostic puis phase 1 uniquement.

## Référence du dépôt et méthode

`git ls-remote origin HEAD` a interrogé directement
https://github.com/Malice-1/BF-ERP.git :
`c0ed8e981b15a60c7bdb9f2d388f4d4d7114c4a7`. Le HEAD local est identique.
Les objets Git de ce commit ont été inspectés (`git show`), puis comparés au
code présent dans l'espace de travail. Les modifications locales antérieures,
notamment `sales/`, sont conservées et intégrées à l'analyse. Elles ne sont pas
présentées comme déjà publiées sur GitHub. Aucun push ni remplacement de l'arbre
de travail n'est nécessaire à cette mission.

La spécification détaillée « fournie précédemment » pour toute la comptabilité
n'est pas présente dans cette conversation. Le périmètre appliqué est donc la
mission fournie, limitée à sa phase 1 ; les règles fiscales non documentées ne
sont pas inventées.

## Architecture réelle

| Sujet | Constat / fichiers |
| --- | --- |
| Backend / ORM | Python, Django 5.2.15, ORM Django ; `requirements.txt`, `config/settings.py` |
| Base cible | PostgreSQL/psycopg ; SQLite pour démonstration et tests rapides |
| Frontend | Templates Django, CSS et JavaScript locaux, sans SPA ; `purchasing/templates/purchasing/base.html`, `purchasing/static/` |
| Applications | `accounts`, `suppliers`, `purchasing`, `budgeting`, `receiving`, `workflow`, et application locale `sales` |
| Identité de l'entité | `sales.IssuerConfiguration`, singleton avec identité légale et Peppol ; pas de modèle multi-sociétés |
| Clients / fournisseurs | `sales.Customer` et `suppliers.Supplier` ; ne pas les dupliquer dans la comptabilité |
| Achats | DA, bons de commande, réceptions ; pas de facture fournisseur comptable ni OCR |
| Ventes / paiements | `sales.SalesInvoice`, lignes et instantanés immuables ; `InvoicePayment`, `PaymentReversal` |
| Documents | Archives privées PDF/XML, SHA-256, validations UBL/EN16931/Peppol ; `sales/documents.py` |
| Permissions | Utilisateur personnalisé, groupes et rôles ERP via `accounts/backends.py` |
| Audit | `workflow.ActivityLog`, services explicites et instantanés d'acteur ; événements d'achat spécialisés non réutilisables tels quels |
| Intégrité | Transactions, verrous PostgreSQL, révisions optimistes et triggers d'historique ; exemples dans `sales/` et `purchasing/` |
| Budget | Écritures de réservation/engagement d'achat, pas un grand livre en partie double ; `purchasing/flow_models.py` |
| Tests | Django TestCase/TransactionTestCase, SQLite et PostgreSQL portable isolé ; `tools/run_postgresql_acceptance.py` |

Le mot `accounting` figure déjà dans les libellés d'applications ; aucune
application, table ou logique de comptabilité générale correspondante n'existe.

## Cadre réglementaire vérifié

Les sources CNC distinguent le PCMN des entreprises de celui des associations
et fondations. Un organisme public peut relever d'un cadre spécifique : le nom
« Bruxelles Formation » ne permet pas de choisir automatiquement un régime.
L'utilisateur a confirmé pendant l'audit un plan spécifique à un organisme public.
Ce cadre est retenu par défaut ; le plan réel n'a pas été fourni. La
comptabilisation reste bloquée jusqu'à revue et approbation de ce plan par une
personne habilitée. Les PCMN entreprises/associations demeurent des références
comparatives, sans peuplement ni activation automatique.

Sources officielles consultées :

- Entreprises : https://www.cnc-cbn.be/fr/node/1653 et https://www.cnc-cbn.be/fr/node/1670
- Associations/fondations : https://www.cnc-cbn.be/fr/node/1657 et https://www.cnc-cbn.be/fr/node/1672
- Continuité, irréversibilité et inaltérabilité : https://www.cnc-cbn.be/fr/node/1641
- Conservation informatique : https://www.cnc-cbn.be/fr/avis/conservation-des-livres-et-pieces-justificatives-en-cas-de-tenue-de-comptabilite-informatisee

Les annexes sont des références datées à faire vérifier et adapter, pas une
certification de conformité de l'entité. Aucun calcul de TVA ou schéma Intervat
n'est développé dans cette phase. Une correction d'écriture validée se fera par
contrepassation, sans modification de l'original.

## Modèle de phase 1

Nouvelle application `accounting`, nécessaire car aucune table existante ne peut
représenter correctement les invariants d'un grand livre :

- `AccountingProfile` : singleton, lien vers l'émetteur existant, EUR, cadre,
  justification de revue et identité/date d'approbation ; aucune duplication d'identité.
- `Account` : code, libellé, regroupement/postable, actif et exigences de tiers.
  Références PCMN importées explicitement, sans remplacer un plan existant.
- `FiscalYear`, `AccountingPeriod` : bornes et verrous ; absence de chevauchement,
  dates d'écriture contrôlées ; fermeture administrative des périodes seulement,
  clôture annuelle et reports de soldes réservés à la phase 7.
- `Journal` : achats, ventes, financier ou OD ; code unique et activité.
- `EntrySequence` : compteur par journal/exercice avec attribution atomique au posting.
- `JournalEntry`, `JournalEntryLine` : brouillon révisable, numéro définitif à la
  validation, débit/crédit en Decimal EUR, date comptable/date de pièce,
  référence justificative obligatoire à la validation, comptes et tiers existants.
- `AccountingEvent` : historique append-only avec acteur et données de transition.

Fondations de futures intégrations : origine typée, identifiant externe et clé
d'idempotence ; référence facultative à une facture Ventes et à son document déjà
archivé. Ces liens ne déclenchent aucune comptabilisation automatique en phase 1.
Ils prépareront les phases 2/3/6 sans second catalogue de factures/documents.

Contraintes SQL : codes uniques, montants non négatifs, un seul côté positif par
ligne, numéros et origines uniques, périodes valides. PostgreSQL : protections des
écritures validées, des lignes et de l'audit, équilibre contrôlé à la transition,
verrouillage cohérent des parents et prévention des chevauchements. Les procédures
doivent demeurer applicables via ORM et HTTP ; SQLite ne prouve pas les verrous.

## Composants et services de phase 1

Frontend : rubrique Comptabilité, tableau de bord, configuration et validation
du profil, consultation/paramétrage/import du PCMN, journaux, exercices/périodes,
liste/recherche des écritures, saisie multiligne, validation, contrepassation,
historique. Réutilisation du gabarit, styles, thème et composants de formulaire.

Backend : services de paramétrage audités, import de référence PCMN idempotent,
sauvegarde transactionnelle des brouillons, contrôle d'équilibre, validation avec
numérotation et snapshots, contrepassation liée et idempotente, fermeture et
réouverture motivées des périodes. Les droits de consultation, saisie, validation,
contrepassation et verrouillage sont distincts.

## Plan incrémental de phase 1

1. Ajouter modèles et migrations additives, sans peuplement automatique de données
   métier ni modification des tables Ventes/Achats.
2. Ajouter les références PCMN traçables et services de configuration.
3. Implémenter brouillons, validation, idempotence, numérotation et contrepassation.
4. Ajouter protections SQL et tests d'attaque des écritures validées.
5. Intégrer écrans, navigation et droits sans changer les flux Achats/Ventes.
6. Vérifier tests métier/HTTP, concurrence PostgreSQL, régressions et migrations.
7. Sauvegarder puis activer uniquement les migrations additives dans la démonstration,
   documenter les résultats, laisser la phase 2 en attente de validation utilisateur.

## Dépendances et risques

Aucune nouvelle bibliothèque nécessaire en phase 1 : Django, Decimal, lxml et
openpyxl sont présents. Les téléchargements officiels ne sont effectués qu'en
préparation explicite d'un référentiel, jamais pendant un posting.

Les moteurs OCR, parseurs CODA/CAMT, formats Intervat et accès Peppol seront évalués
dans leurs phases respectives ; aucun fournisseur externe ni accès réseau de
facturation n'est introduit ici.

Risques : mauvais cadre comptable pour un organisme public ; concurrence entre
posting et fermeture d'une période ; contournement de l'ORM par SQL ; perte de
traçabilité si un libellé de compte/tiers change ; duplication d'une origine lors
des futures intégrations ; régression des permissions/navigation ; confusion avec
les écritures budgétaires. Réponses : profil approuvé, verrouillage déterministe,
triggers, snapshots, clés uniques et campagnes isolées des modules existants.

La phase 1 est un socle technique. La validation réglementaire de l'entité et des
procédures, la politique d'archivage et les phases ultérieures sont nécessaires
avant une mise en production comptable.
