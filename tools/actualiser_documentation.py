"""Generate the QA workbook and code/schema annexes from the current repository.

No business database is read or modified. Functional and technical prose before
the generated marker is maintained manually. Manual cases are versioned below.
"""
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_settings"

import django
django.setup()

from django.apps import apps
from django.test.runner import DiscoverRunner
from django.urls import get_resolver
from django.urls.resolvers import URLResolver
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

DOCS = ROOT / "docs"
MARKER = "<!-- ANNEXES AUTO : tools/actualiser_documentation.py -->"
APPS = ("accounts", "suppliers", "purchasing", "budgeting", "receiving", "workflow", "config")

# Domain | title | actor | state/precondition | exact data | ordered actions | expected observations
# '~' separates ordered actions and expected observations.
CASES = r"""
AUTH|Connexion valide|DEMANDEUR|Compte actif QA créé|Identifiant et mot de passe QA|Ouvrir /connexion/~Saisir le compte QA~Valider|Accès authentifié~Aucun accès admin implicite
AUTH|Mot de passe incorrect|ANONYME|Compte QA actif|Mot de passe faux|Ouvrir la connexion~Saisir le compte et un mot de passe faux~Valider|Message d'identification invalide~Aucune session authentifiée
AUTH|Compte inconnu|ANONYME|Aucun compte QA-inconnu|Identifiant QA-inconnu|Essayer la connexion~Ouvrir ensuite une DA connue|Connexion refusée~DA non exposée
AUTH|Compte désactivé|DEMANDEUR|Compte QA inactif|Bon mot de passe|Essayer de se connecter~Observer le message|Message de compte désactivé si mot de passe correct~Pas de connexion
AUTH|Réactivation|ADMIN|Compte QA désactivé|Même mot de passe|Réactiver le compte dans l'administration~Se connecter avec ce compte|Connexion possible sans recréation des données
AUTH|Expiration par inactivité|DEMANDEUR|Session réglée à 1 minute sur base QA|Attente 70 secondes|Ouvrir une DA~Ne plus agir pendant 70 s~Essayer une sauvegarde|Retour connexion/expiration~Aucune mutation métier après expiration
AUTH|Le polling ne prolonge pas la session|DEMANDEUR|Délai QA de 1 minute|Onglet laissé ouvert|Laisser les contrôles automatiques fonctionner~Attendre 70 s~Observer la redirection|La session expire malgré les contrôles de statut
AUTH|Activité prolongeant le délai|DEMANDEUR|Délai QA de 1 minute|Actions à 40 puis 80 secondes|Ouvrir une page protégée après 40 s~Recommencer 40 s plus tard|Session encore active grâce aux actions utilisateur
AUTH|Politique de session réservée|LECTEUR|Compte sans statut superutilisateur|/configuration/session/|Ouvrir directement l'URL~Tenter aussi un POST QA|Accès refusé~Politique inchangée
AUTH|Bornes du délai|ADMIN|Formulaire de politique ouvert|0 puis 10081 puis 1|Soumettre chaque valeur~Relire la politique|0 et 10081 refusés~1 accepté et audité
ACC|Droits via rôle ERP|ADMIN|Compte sans permission individuelle|Rôle QA fournissant view_supplier|Attribuer le rôle~Reconnecter le compte~Ouvrir Fournisseurs|Consultation autorisée~Création toujours interdite sans add_supplier
ACC|Retrait de rôle|ADMIN|Utilisateur lecteur via rôle|Retrait du rôle QA|Retirer le rôle~Reconnecter le compte~Accéder à l'URL fournisseur|Accès retiré~Pas de droit résiduel après nouvelle session/instance
ACC|Compte non staff responsable|CDF-A|Compte applicatif non staff responsable CDF-A|DA sur CDF-A|Ouvrir Mes validations~Traiter sa ligne~Essayer /admin/|Validation métier possible~Administration non ouverte par l'affectation CDF
ACC|Appartenance support sans responsabilité|DEMANDEUR|Membre QA-SP, non responsable CDF|DA sur CDF-A|Saisir une DA avec QA-SP~Tenter décision d'une DA d'autrui|Support admis à la saisie~Aucun droit de validation acquis
ACC|Affectation responsable CDF|ADMIN|CDF-A sans responsable|Utilisateur actif CDF-A|Ouvrir la configuration des responsables~Rechercher identifiant partiel~Affecter et enregistrer|Utilisateur trouvé sans exigence de staff~Affectation persistée et accès aux nouvelles tâches
ACC|Affectation inactive interdite|ADMIN|Compte QA inactif non affecté|Utilisateur QA-inactif|Chercher dans les choix~Forger un POST d'affectation QA|Compte non proposé comme nouveau responsable~POST invalide sans affectation
ACC|Changement de responsable en cours|ADMIN|DA soumise affectée CDF-A|Remplacer par CDF-B|Changer le responsable du CDF~Rafraîchir les deux boîtes~Tenter ancienne décision|Nouveau responsable voit la tâche~Ancien responsable refusé côté serveur
ACC|Consultation financière cloisonnée|SUIVI|monitor_purchases seul|URL d'une DA d'autrui|Consulter le suivi~Accéder directement au détail financier|Suivi opérationnel sans montants/fournisseur sensibles~Détail non autorisé
UI|Menus par droits|LECTEUR|Droit view_supplier uniquement|Compte sans budget/stock|Se connecter~Examiner les quatre rubriques~Essayer leurs URL|Achats/Fournisseurs visibles selon droits~Budget/stock protégés côté serveur
UI|Bouton budget uniquement Achats|ADMIN|Session active|Achats, Budget, Stocks, Configuration|Ouvrir chaque rubrique~Repérer le bouton €|Bouton € présent dans Achats seulement~Pas de loupe globale équivalente ailleurs
UI|Accès personnels globaux|DEMANDEUR|Session active|Bandeau supérieur|Ouvrir Achats puis Mes validations puis Mes délégations|Accès personnels dans le bandeau~Pas de doublons dans le menu Achats
UI|Configuration sans anciens circuits|ADMIN|Superutilisateur|/achats/configuration/|Ouvrir Configuration~Lire toutes les rubriques|Rubrique Compatibilité des anciens circuits absente~Responsables et accès toujours présents
UI|Thèmes et onglets|DEMANDEUR|Deux onglets même origine|Clair puis sombre|Changer de thème~Observer le deuxième onglet~Ouvrir Vérifier un budget|Choix synchronisé~Iframe lisible dans le thème choisi
UI|Stockage navigateur indisponible|DEMANDEUR|Bloquer localStorage via outil navigateur QA|Mode privé/restreint|Charger l'application~Utiliser le bouton de thème|Aucune erreur JS bloquante~Bascule utilisable sans persistance
UI|Clavier et fenêtres|DEMANDEUR|DA prête à soumettre avec erreur de budget|Tab, Entrée, Échap|Accéder aux boutons au clavier~Ouvrir l'erreur~Fermer la fenêtre|Focus visible et nom accessible~Fermeture possible sans perdre la DA
UI|Actions de lignes alignées|DEMANDEUR|DA brouillon de deux lignes|Fenêtre large puis mobile|Observer Modifier/Supprimer~Réduire la largeur~Utiliser un bouton|Boutons groupés et espacés~Pas d'action déclenchée sur la mauvaise ligne
UI|Affichage numérique|DEMANDEUR|DA avec TVA 21 et prix 1.2345|TVA 21,0000 en stockage|Ouvrir la DA et le bon|TVA affichée 21~Montants limités à deux décimales~Précision stockée non modifiée
FOU|Créer un fournisseur|FOURNISSEUR|add_supplier|QA-FOU, Société QA, BE0123456789|Ouvrir Achats/Fournisseurs~Créer avec les trois champs~Rechercher QA-FOU|Une fiche créée~Code, nom et TVA retrouvés
FOU|TVA facultative|FOURNISSEUR|add_supplier|QA-FOU-SANS-TVA|Créer sans TVA~Consulter la liste|Création acceptée~Valeur absente lisible sans None ni erreur
FOU|Code dupliqué|FOURNISSEUR|QA-FOU existe|Même code, autre nom|Créer un deuxième fournisseur QA-FOU|Erreur de code unique~Une seule fiche QA-FOU et nom initial intact
FOU|Recherche partielle|FOURNISSEUR|Trois fournisseurs QA|Fragment du nom puis TVA|Chercher successivement par code, nom et TVA~Chercher une valeur absente|Résultats conformes à chaque critère~Liste vide explicite en absence de résultat
FOU|Modifier selon droits|FOURNISSEUR|change_supplier|Nom Société QA modifiée|Modifier QA-FOU~Rechercher la nouvelle valeur|Modification persistée~Code unique toujours protégé
FOU|Lecture sans écriture|LECTEUR|view_supplier sans add/change|URL nouveau/modifier|Consulter la liste~Ouvrir création~POST modification QA|Liste accessible~Écritures refusées et fournisseur inchangé
REF|BI et produit détaillé|BUDGET|Droits produits nécessaires|QA-BI-A et QA-ARTICLE-A|Créer le BI~Créer l'article rattaché~Sélectionner dans une DA|Le BI de l'article est identifiable~Allocation fondée sur BI, pas sur code article
REF|Recherche BI dynamique|BUDGET|Deux BI QA|Recherche partielle QA-BI|Saisir sans soumettre~Changer rapidement le texte|Résultats actualisés sans page entière~Dernière saisie gagne sur requête lente
BUD|Créer une version vide|BUDGET|Gestion budgétaire autorisée|Année Y, QA-V1|Créer QA-V1~Enregistrer vide~Réouvrir|Brouillon conservé~Aucune publication automatique
BUD|Nom de version déjà utilisé|BUDGET|QA-V1 existe en Y|qa-v1 avec espaces périphériques|Essayer une nouvelle version en Y~Réessayer en Y+1|Doublon normalisé en Y refusé~Année différente indépendante
BUD|Ajouter une allocation|BUDGET|QA-V1 brouillon|CDF-A/F-QA/BI-A = 1000|Ouvrir Allocations~Saisir la combinaison~Enregistrer puis réouvrir|Allocation 1000 persistée~Historique mentionne produit/CDF/financement/montant
BUD|Doublon de combinaison|BUDGET|Allocation CDF-A/F-QA/BI-A existante|Deuxième montant 500|Ajouter la même combinaison~Enregistrer|Erreur explicite~Aucune deuxième allocation de la combinaison
BUD|Montant négatif|BUDGET|Version modifiable|Allocation -1|Saisir -1~Enregistrer~Relire|Refus de validation~Allocation précédente inchangée
BUD|Suppression annulable avant sauvegarde|BUDGET|Deux allocations|Cocher suppression ligne 1|Supprimer visuellement~Annuler la suppression~Enregistrer|Ligne réaffichée~Valeur et choix conservés
BUD|Suppression enregistrée|BUDGET|Allocation brouillon sans dépendance interdite|Supprimer ligne 1|Cocher suppression~Enregistrer~Consulter l'historique|Ligne retirée de la version~Suppression tracée sans effacement du journal
BUD|Pagination allocations|BUDGET|30 allocations distinctes QA|Page 1 puis 2|Ouvrir Allocations~Passer page 2~Modifier une ligne et sauvegarder|25 lignes maximum sur page 1~Page/filtre conservés~Autres allocations intactes
BUD|Recherche sans perdre les saisies|BUDGET|Version modifiable|Montant modifié non sauvegardé|Modifier un montant~Saisir un filtre~Essayer page suivante|Avertissement de sauvegarde~Saisie non remplacée silencieusement
BUD|Publier version alimentée|BUDGET|QA-V1 contient allocations|Bouton Publier|Publier QA-V1~Relire versions et disponibles|QA-V1 active~Allocations en lecture seule par défaut
BUD|Publication vide refusée|BUDGET|QA-V0 vide|Action publier|Essayer de publier|Erreur~Aucune version active vide créée
BUD|Remplacement de version|BUDGET|QA-V1 active et DA réservée de 242|QA-V2 allocation 2000|Créer et publier QA-V2~Consulter QA-V1 et QA-V2|V1 remplacée mais conservée~Réservations annuelles visibles, pas effacées
BUD|Déblocage publié par admin|ADMIN|Version publiée|Allocation 1000 vers 1200|Débloquer~Modifier~Enregistrer~Rebloquer|Publication et activité conservées~Nouveau montant effectif~Réservations inchangées
BUD|Gestionnaire non admin ne débloque pas|BUDGET|Version publiée|POST action unlock|Tenter l'URL/action de déblocage QA|Refus serveur~Aucun état modifié
BUD|Version bloquée|ADMIN|Version brouillon alimentée|Action lock|Bloquer~Tenter saisie allocation et import|Modification/import non autorisés~Données intactes
BUD|Supprimer brouillon admissible|BUDGET|Version vide non publiée sans transfert|QA-V-DELETE|Demander suppression~Confirmer~Relire la liste/historique|Version masquée de la sélection normale~Trace préservée
BUD|Suppression version utilisée refusée|BUDGET|Version publiée ou avec transfert|QA-V1|Demander suppression|Refus~Transferts, allocations et références conservés
BUD|Consultation ponctuelle par compte simple|DEMANDEUR|Session active sans view_budget_balances|CDF-A/F-QA/BI-A|Ouvrir €~Choisir version/combinaison~Vérifier|Disponible ponctuel affiché~Pas de droit ajouté au tableau global
BUD|Choix version ponctuelle|DEMANDEUR|V1 remplacée, V2 active, V3 brouillon|Même combinaison|Consulter successivement les trois versions|Solde calculé selon version choisie~Aucune activation par consultation
BUD|Combinaison sans allocation|DEMANDEUR|Combinaison CDF-C sans allocation|CDF-C/F-QA/BI-A|Vérifier son budget|Absence d'allocation signalée~Aucune création implicite
IMP|Bouton au niveau des allocations|BUDGET|Version brouillon modifiable|Barre d'actions de version|Ouvrir la version~Repérer Importer via Excel à côté Exporter~Cliquer|Accès à l'import de la bonne version~Bouton absent si modification interdite
IMP|Modèle Excel|BUDGET|Deux allocations QA existantes|Lien Télécharger le modèle|Télécharger~Ouvrir avec Excel/LibreOffice~Lire toutes les feuilles|Allocations et colonnes requises présentes~Références BI/CDF/financement disponibles
IMP|Import nominal|BUDGET|QA-V1 brouillon|Deux combinaisons nouvelles, 100 et 200|Compléter le modèle~Importer~Attendre résultat final~Relire les allocations|Deux créations~Total 300 pour les lignes importées~Aucune publication
IMP|Réimport idempotent|BUDGET|Import nominal déjà réussi|Même fichier 100/200|Réimporter le fichier~Lire compteurs et montants|Montants inchangés~Aucune addition ni doublon
IMP|Remplacement partiel|BUDGET|Allocations A=100 B=200 C=300|Fichier A=150 seulement|Importer~Relire A B C|A=150~B=200 et C=300 conservés
IMP|Code texte avec zéros initiaux|BUDGET|BI de code 0012|Code stocké en texte Excel|Importer 0012~Relire la combinaison|Le code 0012 n'est pas remplacé par 12
IMP|Extension invalide|BUDGET|Version modifiable|Fichier .csv renommé ou réel .xls|Choisir le fichier~Envoyer|Refus format/classeur~Aucune allocation modifiée
IMP|Fichier illisible|BUDGET|Version modifiable|Faux fichier .xlsx contenant du texte|Envoyer|Erreur lisible de lecture~Pas d'erreur serveur exposée ni mutation
IMP|Limite 5 Mio|BUDGET|Version modifiable|XLSX supérieur à 5*1024*1024 octets|Envoyer~Relire version|Refus de taille~État identique à avant
IMP|Limite décompressée|BUDGET|Base QA jetable|Archive XLSX dépassant 50 Mio décompressés|Envoyer un fichier de test maîtrisé|Rejet avant import~Pas de création partielle
IMP|Plus de 10000 lignes|BUDGET|10001 combinaisons valides dans fichier|10001 lignes hors en-tête|Importer|Limite explicite~Aucune modification
IMP|En-tête manquant ou répété|BUDGET|Version modifiable|Supprimer Code CDF puis dupliquer Code BI|Importer chaque variante séparément|Colonnes requises signalées~Version inchangée
IMP|Référence inconnue|BUDGET|Une ligne valide et une inconnue|Code BI QA-INCONNU|Importer le lot~Relire ligne valide initiale|Erreur avec localisation~Ligne valide non appliquée partiellement
IMP|Combinaison dupliquée dans fichier|BUDGET|Deux lignes identiques de dimensions|Montants 100 et 200|Importer|Refus doublon~Ni somme 300 ni écrasement silencieux
IMP|Montants invalides|BUDGET|Version modifiable|Texte abc, -1, NaN, précision excessive|Importer un fichier par valeur|Chaque valeur invalide refusée~Aucune écriture partielle
IMP|Formules Excel|BUDGET|Version modifiable|Montant =100+20 et cellule en erreur|Importer séparément les variantes|Demande de coller les valeurs~Aucun calcul de formule sur le serveur
IMP|Mauvaise année/version|BUDGET|Export de V1/Y|Cible V2 ou année Y+1|Réimporter l'export sur la mauvaise cible|Incohérence détectée~Cible inchangée
IMP|Import publié non débloqué|BUDGET|Version publiée|Fichier valide|Ouvrir l'import~Envoyer directement en QA|Import refusé~Pas de modification malgré fichier valide
IMP|Import publié débloqué admin|ADMIN|Version publiée, déblocage admin actif|Fichier A=150|Importer~Contrôler la version et historique|Import accepté pour admin~Écritures de DA conservées~Version toujours publiée
DA|Création et numéro annuel|DEMANDEUR|Fournisseur QA existant|Deux nouvelles DA en année Y|Créer les deux DA~Comparer références|DA-Y-NNNN uniques et croissantes~Aucune référence UUID nouvelle
DA|Fournisseur et support|DEMANDEUR|Membre QA-SP seulement|Fournisseur QA, support QA-SP|Créer DA avec QA-SP~Essayer support non membre par POST QA|Support membre accepté~Référence étrangère refusée
DA|Ligne calcul nominal|DEMANDEUR|DA brouillon|Qté 2, PU 100, TVA 21|Ajouter la ligne BI-A/CDF-A/F-QA~Relire totaux|HTVA 200, TVA 42, TVAC 242
DA|TVA explicitement nulle|DEMANDEUR|DA brouillon|Qté 1, PU 100, TVA 0|Ajouter une ligne~Relire|TVA 0 acceptée~TVAC 100
DA|TVA absente|DEMANDEUR|DA brouillon|Champ TVA vide|Envoyer l'ajout~Essayer soumission si ancienne ligne sans TVA|Erreur obligatoire~Absence jamais assimilée à zéro
DA|Précision conservée|DEMANDEUR|DA brouillon|Qté 1.2345, PU 3.3333, TVA 21|Enregistrer~Exporter/contrôler valeur calculée en test|Calcul décimal exact~Affichage arrondi sans modifier les données
DA|Quantité et prix invalides|DEMANDEUR|DA brouillon|Qté 0 puis négative, prix négatif|Envoyer chaque variante|Validation de champ refusée~Aucune ligne invalide ajoutée
DA|Modification de ligne|DEMANDEUR|Ligne brouillon TVAC 242|Qté 3 au lieu de 2|Modifier la ligne~Enregistrer~Relire totaux/historique|HTVA 300 et TVAC 363~Révision et audit augmentés
DA|Supprimer ligne sans page intermédiaire|DEMANDEUR|Deux lignes brouillon|Ligne 2|Cliquer Supprimer~Annuler confirmation~Recommencer et confirmer|Annulation conserve la ligne~Confirmation la retire sur retour à la DA
DA|Accès DA d'autrui|DEMANDEUR-B|DA de DEMANDEUR-A|Identifiant connu|Ouvrir détail~Tenter modification/annulation par POST QA|Accès refusé/404 selon vue~DA inchangée
DA|Révision périmée|DEMANDEUR|DA ouverte dans deux onglets|Même expected_revision|Modifier dans onglet 1~Envoyer l'ancienne action dans onglet 2|Conflit 409~Pas d'écrasement silencieux
DA|Soumission suffisante|DEMANDEUR|Allocation 1000, aucun autre mouvement|DA TVAC 242|Soumettre depuis la fiche~Fermer/recharger si besoin~Consulter disponible|DA en validation~Réservé 242 et disponible 758~Aucun double débit
DA|Insuffisance avec popup|DEMANDEUR|Disponible 100|DA TVAC 242|Soumettre~Observer et fermer la fenêtre|Erreur sur la DA sans navigation~100,00/242,00 au plus 2 décimales~Aucune réservation
DA|Insuffisance agrégée|DEMANDEUR|Disponible 1000|Deux lignes même combinaison TVAC 605 chacune|Soumettre~Consulter état/budget|Total 1210 refusé~Aucune des deux lignes réservée
DA|Combinaison absente dans lot|DEMANDEUR|Ligne 1 allouée, ligne 2 sans budget|Deux lignes sur CDF-A et CDF-C|Soumettre~Relire les deux écritures|Soumission refusée intégralement~Pas de réservation de ligne 1
DA|Pas de version active|DEMANDEUR|Année QA sans version active|DA valide|Soumettre|Message version active manquante~DA brouillon/correction et budget intact
DA|Annuler une DA en validation|DEMANDEUR|DA réservée de 242|Action annuler|Annuler avec confirmation~Consulter disponible|DA annulée~Réservation libérée, disponible revient à 1000
VAL|Lignes CDF parallèles|CDF-A et CDF-B|DA soumise, une ligne sur chaque CDF|Deux lignes TVAC 121 chacune|Ouvrir les deux boîtes~Valider ligne B avant A~Valider ensuite A|Les deux tâches sont accessibles indépendamment~Pas de commande après B seul~Commande après A et B
VAL|Même CDF deux décisions|CDF-A|DA soumise de deux lignes CDF-A|Deux lignes TVAC 121|Valider une ligne~Relire DA~Valider la deuxième|Deux décisions distinctes~DA commandée seulement après les deux
VAL|Bulles de la frise|ADMIN|DA soumise avec deux lignes ouvertes|Deux étapes CDF|Lire le parcours~Valider ligne 1 dans le tableau~Relire le parcours|Deux bulles vertes au départ puis une~Aucun bouton de validation dans la frise
VAL|Valider ligne par admin|ADMIN|DA en attente sans responsable|Droit decide_any_purchaserequest|Cliquer Valider sur la ligne~Confirmer~Lire audit|Étape approuvée par admin~Intervention administrateur identifiable
VAL|Valider tout au niveau DA|ADMIN|DA soumise de trois lignes|Action globale dans barre DA|Cliquer Valider tout le circuit~Lire portée puis confirmer|Toutes étapes restantes approuvées~Un bon unique et conversions sans double débit
VAL|Validation globale interdite au responsable|CDF-A|Compte sans droit admin dédié|DA de deux lignes|Observer les actions~Forger decision=approve_all en QA|Pas de bouton global autorisé~Requête refusée ou erreur de choix, aucune mutation
VAL|Retour pour correction|CDF-A|DA soumise de deux lignes|Motif Corriger la quantité|Demander correction avec motif~Relire DA/budget~Ouvrir le brouillon de correction|Toute DA en correction~Toutes réservations libérées~Anciennes décisions conservées
VAL|Motif obligatoire|ADMIN|DA en validation|Correction/rejet avec blanc|Ouvrir action~Tenter confirmer sans motif~Forger POST vide QA|Motif exigé navigateur et serveur~Aucun changement d'état
VAL|Correction et nouvelle soumission|DEMANDEUR|DA retournée en correction|Qté corrigée, TVAC 121|Modifier~Resoumettre~Ouvrir frise|Nouveau cycle indépendant~Anciennes approbations ne valident pas automatiquement la nouvelle DA
VAL|Rejet définitif|CDF-A|DA en validation|Motif Achat refusé|Rejeter~Tenter resoumission QA|DA rejetée, réservations libérées~Resoumission refusée
VAL|Responsable désactivé en cours|ADMIN|Étape pending affectée CDF-A|Désactivation de CDF-A|Désactiver le compte~Actualiser~Tenter décision avec ancienne session|Acteur inactif refusé~Étape à affecter ou droit bloqué selon état
VAL|Délégation d'achat|CDF-A|Principal responsable et délégué actif|Période incluant maintenant|Créer délégation~Se connecter délégué~Valider sa tâche|Autorité du principal vérifiée~Acteur réel et représenté conservés
VAL|Délégations invalides|CDF-A|Délégation A vers B active|Auto-délégation, chevauchement, chaîne B vers C|Créer chaque variante séparément|Chaque configuration interdite refusée~Aucune chaîne contournant les droits
BC|Données figées du bon|ADMIN|DA commandée|Modifier nom fournisseur et libellé article après commande|Modifier référentiels~Imprimer le bon|Le bon reprend les données figées approuvées~Pas de réécriture historique
BC|Impression directe|DEMANDEUR|DA commandée accessible|Bouton Imprimer|Cliquer une fois~Annuler la boîte système|Fenêtre d'impression ouverte sans page intermédiaire~DA reste affichée après annulation
BC|Lecture du bon interdite|DEMANDEUR-B|Bon d'une autre DA sans droit financier|URL /achats/id/commande/|Ouvrir URL et tentative iframe QA|Document non exposé~Aucune donnée du fournisseur/lignes
TRF|Source puis destination|CDF-A puis CDF-B|Budget source 1000, destination 0|Transfert 100|Soumettre~Essayer destination avant source~Valider source puis destination|Source disponible 900 dès soumission~Destination 0 puis 100 à la fin~Ordre imposé
TRF|Même responsable deux étapes|CDF-A|CDF-A et CDF-B gérés par même compte|Transfert 100|Approuver source~Relire~Approuver destination|Deux décisions nécessaires~Pas de réutilisation automatique de la première
TRF|Destination commune multisource|BUDGET|Sources A=1000 et C=1000|A donne 100 et C donne 200 vers B|Créer deux sources~Observer total~Soumettre|Destination total 300~Deux transactions dans un groupe et circuits propres
TRF|Suppression et ligne vide|BUDGET|Formulaire multisource|Une valide, une supprimée, une vide|Ajouter les trois~Supprimer l'une~Soumettre|Seule la source valide contribue au total et aux écritures
TRF|Au moins une source|BUDGET|Formulaire vide ou toutes lignes supprimées|Aucune ligne active|Soumettre|Erreur de minimum~Aucun transfert ni groupe parasite
TRF|Même combinaison interdite|BUDGET|Version modifiable|Source et destination identiques|Saisir les mêmes CDF/BI/financement~Soumettre|Erreur de combinaison~Aucune réservation
TRF|Supports indépendants|BUDGET|Supports QA-SP1/SP2 et droit création|Source SP1, destination SP2 puis vides|Créer transfert avec supports différents~Créer un autre sans supports|Supports conservés séparément~Absence facultative admise
TRF|Échec global insuffisant|BUDGET|Source A disponible 1000|Deux sources A de 600 et 600|Soumettre le groupe~Consulter disponible et liste|Les 1200 cumulés sont refusés~Aucune ligne créée/réservée
TRF|Version différente|BUDGET|V1 et V2 même année|Transfert de V1|Soumettre sur V1~Activer V2~Comparer soldes|Transfert reste dans V1~Pas de transfert automatique vers V2
TRF|Valider tout le circuit|ADMIN|Transaction en attente|Droit decide_any_budgettransfer|Ouvrir transaction~Valider tout le circuit~Confirmer|Toutes étapes restantes approuvées au nom admin~Destination créditée une fois
TRF|Validation groupée et filtres|ADMIN|Groupe de plusieurs lignes dont une masquée|Filtre limitant affichage|Filtrer~Lancer validation globale du groupe~Lire confirmation~Confirmer|Toutes les lignes du groupe concernées, y compris masquées~États et soldes cohérents
TRF|Instantané périmé|ADMIN|Liste ouverte deux fois|Une révision changée entre-temps|Agir dans onglet 1~Valider groupe depuis onglet 2|Refus de snapshot/révision~Aucun sous-ensemble validé accidentellement
TRF|Snapshot falsifié|ADMIN|Groupe en attente|Altérer la valeur snapshot dans outil QA|Envoyer action groupée|Signature refusée~Aucun changement sur le groupe
TRF|Refus avec motif|CDF-A|Transfert en attente|Motif Budget à revoir|Refuser avec motif~Relire source et historique|Réservation relâchée~Motif et acteur tracés
TRF|Retour global pour correction|ADMIN|Groupe pas entièrement approuvé|Motif Corriger sources|Retourner le groupe~Consulter Mes validations du créateur|Lignes renvoyées au créateur selon action~Motif visible~Budget libéré/inversé atomiquement
TRF|Corriger et resoumettre|BUDGET|Transfert retourné du créateur|Montant 100 vers 80|Modifier~Resoumettre~Ouvrir parcours|Nouveau cycle actif~Ancien cycle conservé~Réservation 80 uniquement
TRF|Annuler approuvé|ADMIN|Transfert 100 approuvé, destination disponible|Droit cancel_any_budgettransfer et motif|Annuler~Consulter les deux soldes~Répéter action QA|Retour des soldes une fois~Historique conservé~Pas de double inversion
TRF|Annulation destination consommée|ADMIN|Destination 100 reçus dont 90 réservés|Tentative reprise de 100|Demander annulation avec motif|Refus pour fonds indisponibles~Aucun débit partiel
TRF|Retour groupe accompli|ADMIN|Toutes les lignes approuvées|Action retour/refus global|Essayer le retour global~Comparer possibilité d'annulation|Retour simple refusé~Annulation soumise à droit propre et contrôles
TRF|Version bloquée après soumission|ADMIN|Transfert en attente|Blocage version puis approbation|Bloquer~Essayer approuver~Essayer refus autorisé|Approbation interdite selon règle de version~Refus possible et réservations libérées
TRF|Périmètre des listes|DEMANDEUR-B|Transferts d'autrui non liés à B|URL liste/version/détail connue|Ouvrir les URL~Exporter|Aucun élargissement par identifiant/filtre/export~Accès limité au périmètre
STK|Créer un dépôt|STOCK|Droit add_warehouse|QA-DEP-A, Dépôt QA|Créer~Réouvrir~Créer le même code|Dépôt enregistré~Doublon refusé
STK|Entrée de stock|STOCK|Solde initial 0|Entrée 10 QA-ARTICLE-A|Saisir dépôt/article/10/référence~Valider~Lire solde|Stock 10~Un mouvement et une trace
STK|Sortie de stock|STOCK|Stock 10|Sortie 3|Enregistrer sortie motivée~Lire solde|Stock 7~Delta -3
STK|Sortie insuffisante|STOCK|Stock 7|Sortie 8|Tenter sortie~Lire solde/journal|Refus~Solde 7 et aucun mouvement métier réussi
STK|Transfert de stock|STOCK|A=10, B=0|Transfert 4|Choisir B distinct et référence~Valider|A=6, B=4~Un mouvement atomique et motif
STK|Transfert même dépôt|STOCK|Stock disponible|Source A destination A|Tenter transfert|Refus~Aucun changement de stock
STK|Inventaire final|STOCK|Stock 10|Quantité comptée 6 puis 0|Enregistrer inventaire 6~Puis inventaire 0|Solde fixé à 6 puis 0~Deltas -4 puis -6, pas des sorties de 6 puis 0
STK|Quantités invalides|STOCK|Base QA|Valeurs négatives, NaN et zéro hors inventaire|Envoyer chaque variante via formulaire/service test|Refus sans mutation~Zéro accepté seulement dans l'inventaire
STK|Rejeu idempotent|STOCK|Premier mouvement token T réussi|Même token et payload|Rejouer le POST/service QA|Même opération logique~Pas de deuxième variation du solde
STK|Token avec payload différent|STOCK|Token T déjà utilisé|Quantité ou dépôt différent|Réutiliser T en modifiant la donnée|Conflit explicite~Premier mouvement inchangé
STK|Lecture sans gérer le stock|LECTEUR|view_stockbalance seul|URL mouvement POST|Lire les soldes~Tenter une écriture QA|Lecture possible~Écriture refusée
STK|Immutabilité d'un mouvement|ADMIN|Mouvement existant|save/delete et tentative SQL dans tests dédiés|Exécuter test immutabilité~Consulter historique|Édition ordinaire refusée selon couche~Correction par nouvelle opération distincte
REC|Réception partielle|STOCK|DA commandée de 10 unités, stock 0|Livraison QA-BL-1 de 4|Ouvrir Réceptions~Choisir dépôt et référence~Recevoir 4|Stock +4~Reçu 4, reste 6, Partiellement réceptionnée
REC|Compléter une réception|STOCK|Reçu 4 sur 10|Livraison QA-BL-2 de 6|Recevoir les 6 restants~Relire DA|Stock total 10~Reçu 10, reste 0, Réceptionnée
REC|Sur-réception|STOCK|Reste 6|Réception 7|Tenter réception~Consulter stock/réceptions|Refus~Aucun stock ni reçu augmenté
REC|DA non commandée|STOCK|DA brouillon/en validation|Livraison 1|Ouvrir URL réception~Tenter POST QA|Réception interdite~Aucun mouvement
REC|Ligne étrangère|STOCK|Deux DA commandées|Identifiant de ligne autre DA|Forger réception QA incluant ligne étrangère|Refus~Aucun reçu/mouvement partiel
REC|Réception vide ou sans référence|STOCK|DA commandée|Toutes quantités 0 puis référence vide|Soumettre chaque variante|Au moins une quantité positive et référence exigées
REC|Rejeu de livraison|STOCK|Réception token R réussie|Même R puis R avec quantité différente|Rejouer identique~Rejouer modifié|Identique non doublé~Modifié refusé
REC|Stock sans fuite financière|STOCK|manage_stock sans permission achats financière|DA commandée|Ouvrir réception et export opérationnel|Produit/quantités visibles~Pas de fournisseur/prix/totaux non autorisés
REC|Mouvement libre non assimilé à réception|STOCK|DA commandée non reçue|Entrée libre du même article|Enregistrer entrée libre~Lire progression DA|Stock augmente~DA toujours non réceptionnée
HIS|Historique daté|BUDGET|Allocation 100 puis 200 à deux dates|Date avant/puis après modification|Consulter chaque date et avant premier événement|États conformes aux dates~Pas de reconstruction erronée du présent dans le passé
HIS|Historique après remplacement version|BUDGET|V1 puis V2 publiées|Date et version V1|Ouvrir historique V1~Exporter|Version imposée dans vue dédiée~Événements de V2 non mélangés
HIS|Suppression utilisateur et identité|ADMIN|DA commandée approuvée par compte QA|Compte demandeur/approbateur jetable|Supprimer via maintenance avec aperçu~Relire bon et journal|Identité/snapshots historiques lisibles~Pas de commande perdue par détachement facultatif
HIS|Journal en lecture seule|ADMIN|Événements existants|ActivityLog ciblé|Ouvrir admin journal~Tenter service de suppression QA|Pas de mutation ordinaire~Service refuse de cibler le journal
HIS|Échec transaction sans journal fantôme|ADMIN|Opération de service forcée à échouer en test|Exception au dernier enregistrement|Exécuter test rollback dédié~Comparer budget, objets et journaux|Aucun événement de réussite ni objet partiel persisté
SEC|CSRF absent|DEMANDEUR|Session connectée, client QA enforce_csrf_checks|POST sans jeton|Tenter création/soumission sans CSRF|403~Aucune mutation ni réservation
SEC|GET non mutateur de commande|DEMANDEUR|DA brouillon|URL soumettre/annuler|Appeler GET sur action de confirmation~Relire DA|GET ne soumet/annule pas la DA~Seul POST exécute la commande
SEC|Injection HTML dans texte|DEMANDEUR|DA brouillon|Description <script>alert(1)</script>|Enregistrer~Ouvrir fiche, historique et export|Texte échappé~Aucun script exécuté
SEC|Formule dans export|ADMIN|Fournisseur/texte synthétique commençant =|Texte =1+1|Exporter XLSX~Inspecter cellule avec openpyxl|Cellule texte, pas une formule calculable
SEC|Anciennes routes configurables|ADMIN|Ancien éditeur retiré|GET puis POST /achats/regles-validation/|Ouvrir GET~Envoyer POST QA|GET redirige vers Configuration~POST 410 sans écriture
SEC|Maintenance sans superuser|LECTEUR|Droit delete_role sans superuser|Rôle jetable|Tenter suppression système/route QA|Refus malgré droit ordinaire~Pas de graphe supprimé
SEC|Aperçu dépendances maintenance|ADMIN|Version publiée avec dépendances sur base jetable|Objet parent à supprimer|Ouvrir suppression~Lire dépendances~Annuler|Graphe annoncé~Aucune suppression avant confirmation
SEC|Impression origine et accès|DEMANDEUR|Bon personnel|Iframe même origine puis origine externe QA|Charger document autorisé~Inspecter X-Frame-Options~Tester tiers|SAMEORIGIN~Autorisation document toujours appliquée
PERF|Reproduire mesures locales|TECH|Environnement Python isolé, dépendances installées|3 répétitions, allocations 10/100/1000|Exécuter tools/mesurer_performances.py avec output QA~Conserver JSON|Statut 200 des scénarios~SQL/temps/octet/mémoire renseignés~Aucune base métier touchée
PERF|Concurrence réservation DA|TECH|PostgreSQL test dédié|Deux DA dépassant budget ensemble|Exécuter .venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_t001_t002_concurrent_reservations_do_not_overspend --settings=config.postgresql_test_settings --noinput|Une seule réservation admissible~Disponible non surconsommé
PERF|Concurrence double décision|TECH|PostgreSQL test dédié|Deux décisions simultanées même DA|Exécuter .venv\Scripts\python.exe manage.py test purchasing.test_flow_postgresql.PostgreSQLPurchaseFlowTests.test_t005_simultaneous_manager_approval_creates_one_order --settings=config.postgresql_test_settings --noinput|Une seule commande~Pas de double engagement
PERF|Concurrence sorties stock|TECH|PostgreSQL test dédié|Deux sorties supérieures au total ensemble|Exécuter .venv\Scripts\python.exe manage.py test receiving.test_stock_postgresql.ConcurrentStockTests.test_concurrent_issues_cannot_overdraw_stock --settings=config.postgresql_test_settings --noinput|Stock jamais négatif~Une opération refusée si nécessaire
PERF|Charge et percentiles cible|TECH|PostgreSQL dédié et accord de charge|1/10/25/50 sessions, plusieurs centaines de requêtes|Mesurer après chauffe p50/p95/p99, CPU, SQL, erreurs et attentes|Rapport séparant lecture/écriture~Aucune incohérence métier~Seuils convenus, pas de SLA inventé
E2E|Achat nominal jusqu'à livraison complète|DEMANDEUR puis CDF-A puis STOCK|Jeu QA réinitialisé : allocation 1000 et stock 0|2 unités à 100 HTVA, TVA 21|Créer DA fournisseur QA~Ajouter ligne CDF-A/F-QA/BI-A~Soumettre~Vérifier disponible 758~Valider CDF-A~Imprimer~Réceptionner 1 unité BL-1~Réceptionner 1 unité BL-2~Relire budget et journal|Un bon unique~Engagé 242 et disponible 758~Stock 2, reçu 2, reste 0~Deux réceptions et traces cohérentes
E2E|Achat multilignes traité dans l'ordre inverse|DEMANDEUR puis CDF-B puis CDF-A|A=1000 et B=1000, stock 0|Ligne A TVAC 121 et B TVAC 242|Créer les deux lignes~Soumettre~Valider B d'abord~Vérifier absence de bon~Valider A~Recevoir séparément les lignes|Parallélisme des lignes confirmé~Commande unique après les deux décisions~Réserves converties sans nouvelle déduction
E2E|Correction complète d'une DA|DEMANDEUR puis CDF-A|Allocation 1000|DA initiale 242 puis corrigée 121|Créer et soumettre~Retourner pour correction avec motif~Vérifier disponible revenu 1000~Modifier quantité~Resoumettre~Valider nouveau cycle~Consulter anciens cycles|Deux soumissions conservées~Engagement final 121~Ancienne approbation non réutilisée~Motif visible
E2E|Insuffisance puis alimentation par import|DEMANDEUR puis ADMIN puis CDF-A|Allocation active 100 seulement|DA 242, import total 500|Soumettre et constater refus~Préparer fichier 500~Admin débloque la version publiée~Importer en admin~Rebloquer~Resoumettre DA~Valider|Refus initial sans réserve~Allocation finale 500~Engagé 242 et disponible 258~Trace import et décision
E2E|Rejet après une approbation partielle|DEMANDEUR puis CDF-A et CDF-B|Deux allocations 1000|Lignes 121 et 242|Soumettre deux lignes~Approuver A~Rejeter B avec motif~Comparer budget et états~Essayer resoumission|Aucune commande~Toutes réservations libérées~Historique approbation conservé mais DA terminale
E2E|Transfert puis achat sur destination|BUDGET puis CDF-A puis CDF-B puis DEMANDEUR|A=1000, B=0|Transfert 300, DA B=242|Soumettre transfert~Constater A=700 B=0~Valider source puis destination~Constater B=300~Créer/soumettre/valider DA sur B|Disponible B final 58~A reste 700~Transfert et DA ont des historiques distincts
E2E|Transfert groupé retourné corrigé|BUDGET puis ADMIN|A=1000 C=1000 destination B=0|Sources 100 et 200 puis correction 80|Soumettre deux sources~Retourner tout avec motif~Vérifier A=1000 C=1000 B=0~Corriger la première transaction à 80 et la resoumettre~Resoumettre aussi la seconde transaction retournée à 200~Valider les deux circuits~Consulter groupe et versions|Anciens cycles conservés~A=920, C=800, B=280~Pas de double solde
E2E|Annulation globale atomique impossible|ADMIN|Sources A=C=1000 ; transfert groupé 100 et 200 approuvé vers B puis DA réservant 250 sur B|B disponible 50 avant annulation ; A=900 C=800|Noter tous les soldes~Tenter annulation globale motivée des 300~Relire toutes les transactions et la réserve DA|Échec entier~A=900, C=800, B disponible 50~Réserve DA 250 conservée~Aucune première ligne inversée avant échec de la seconde
E2E|Remplacement responsable pendant validation|DEMANDEUR puis ADMIN puis CDF-B|DA affectée CDF-A|Responsable A remplacé par B|Soumettre~Changer affectation~Ouvrir deux boîtes~Tenter décision de A~Valider avec B|Ancien acteur refusé~Nouveau acteur enregistré~Bon et budget cohérents
E2E|Version remplacée avec DA en cours|BUDGET puis DEMANDEUR puis CDF-A|V1=1000 active|DA réservée 242 puis V2=2000|Soumettre sous V1~Publier V2~Consulter les deux versions~Valider DA~Imprimer le bon|Réservations annuelles conservées~DA référence sa soumission V1~Conversion sans double débit~V2 disponible annuel tient compte de 242
E2E|Réception rejouée après problème réseau|STOCK|DA commandée 10 unités, stock 0|Livraison 4 token R|Envoyer réception~Simuler perte de réponse après succès serveur~Rejouer même R~Recharger DA|Une seule réception~Stock 4, reste 6~Un nouvel envoi distinct sans même token n'est pas présenté comme garanti idempotent
E2E|Expiration pendant action métier|DEMANDEUR|Délai QA 1 minute, DA brouillon|DA TVAC 242 prête|Ouvrir la DA~Attendre expiration sans activité~Cliquer Soumettre~Se reconnecter~Relire état et disponible|Aucune soumission après expiration~Budget intact~Possibilité de reprendre après reconnexion
"""

DATA = [
    ("Environnement", "Base QA jetable, même schéma que le moteur cible, aucun envoi courriel réel"),
    ("Y", "Année locale Europe/Brussels ; ne pas changer l'horloge de production"),
    ("ADMIN", "Superutilisateur actif QA ; usage de maintenance uniquement sur base jetable"),
    ("DEMANDEUR", "Compte actif avec purchasing.add_purchaserequest et fournisseur QA ; sans droits admin"),
    ("CDF-A / CDF-B", "Comptes actifs responsables uniquement de leur CDF ; accès financier distinct à ajouter si consultation DA nécessaire"),
    ("BUDGET", "Gestionnaire avec l'ensemble MANAGER_PERMISSIONS, lecture budget et création transferts pour les cas qui l'exigent"),
    ("FOURNISSEUR", "Compte actif avec view/add/change_supplier ; variantes de lecture seule définies par cas"),
    ("STOCK", "Compte actif avec receiving.manage_stock et les droits dépôt/lecture nécessaires ; sans droit financier d'achat"),
    ("SUIVI / LECTEUR", "Comptes aux seuls droits indiqués dans le cas ; jamais superutilisateurs"),
    ("TECH", "Opérateur sur environnement de test isolé et autorisé à créer sa base de tests"),
    ("Référentiels", "CDF-A, CDF-B, CDF-C ; F-QA ; BI-A ; article QA-ARTICLE-A rattaché à BI-A ; fournisseur QA-FOU"),
    ("Supports", "QA-SP1/QA-SP2 ; appartenance et responsabilité configurées séparément"),
    ("Budget de référence", "QA-V1 en Y ; allocation A/F-QA/BI-A=1000 ; B selon le cas ; C sans allocation sauf indication"),
    ("Stock de référence", "QA-DEP-A et QA-DEP-B ; article QA-ARTICLE-A ; solde 0 sauf précondition contraire"),
    ("Arithmétique", "2 × 100 HTVA à 21 % = 242 TVAC ; 1 × 100 à 21 % = 121 ; disponible 1000−242=758"),
    ("Réinitialisation", "Un cas = jeu initial indépendant. Recréer/restaurer la base QA ou nouveaux identifiants ; jamais supprimer des données réelles."),
]


def manual_cases():
    counts = Counter()
    cases = []
    for line in CASES.strip().splitlines():
        parts = line.split("|")
        if len(parts) != 7:
            raise ValueError((len(parts), line))
        domain, title, actor, pre, data, steps, expected = parts
        counts[domain] += 1
        cases.append(dict(id=f"{domain}-{counts[domain]:03d}", domain=domain, title=title,
                          actor=actor, pre=pre, data=data, steps=steps.split("~"),
                          expected=expected.split("~"),
                          priority="P0" if domain in {"AUTH", "ACC", "VAL", "SEC", "E2E"} or any(x in title.casefold() for x in ("insuff", "atom", "concurr", "rejeu")) else "P1"))
    return cases


def automated_cases():
    suite = DiscoverRunner(verbosity=0).build_suite()
    def walk(group):
        for item in group:
            if hasattr(item, "_testMethodName"):
                yield item
            else:
                yield from walk(item)
    result = []
    for case in walk(suite):
        method = getattr(case.__class__, case._testMethodName)
        source = textwrap.dedent(inspect.getsource(method))
        tree = ast.parse(source)
        assertions = [ast.get_source_segment(source, n).strip() for n in ast.walk(tree)
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                      and n.func.attr.startswith("assert")]
        setup = textwrap.dedent(inspect.getsource(case.__class__.setUp))
        path = Path(inspect.getsourcefile(method)).relative_to(ROOT).as_posix()
        stable_id = "AUT-" + hashlib.sha256(case.id().encode("utf-8")).hexdigest()[:10].upper()
        result.append(dict(id=stable_id, name=case.id(), path=path,
                           line=inspect.getsourcelines(method)[1], source=source,
                           setup=setup, assertions=assertions,
                           kind="Acceptation PostgreSQL" if "postgresql" in case.id()
                           else "Unitaire pur sans DB" if "_unit" in case.id() or "_units" in case.id()
                           else "Intégration Django / service / HTTP",
                           command=f".venv\\Scripts\\python.exe manage.py test {case.id()} --settings="
                           + ("config.postgresql_test_settings" if "postgresql" in case.id() else "config.test_settings") + " --noinput"))
    return result


def safe(value):
    return str(value).replace("|", "&#124;").replace("\n", " ")


def technical_annex():
    text = [MARKER]
    performance_path = DOCS / "mesures_performances.json"
    if performance_path.exists():
        measurements = json.loads(performance_path.read_text(encoding="utf-8"))
        text += ["\n## Résultats de performance mesurés\n",
                 f"Mesure horodatée : `{measurements['measured_at']}`. Python `{measurements['python']}`, Django `{measurements['django']}`, `{measurements['platform']}`. Moteur : {measurements['database']}.\n",
                 "| Scénario | Volume | Médiane ms | Min–max ms | SQL min–max | Réponse octets | Pic Python Mio |\n| --- | ---: | ---: | --- | --- | ---: | ---: |"]
        for item in measurements["results"]:
            text.append(f"| {item['scenario']} | {item['volume']} | {item['median_ms']} | {item['min_ms']}–{item['max_ms']} | {item['sql_min']}–{item['sql_max']} | {item['response_bytes']} | {item['python_peak_bytes']/1024/1024:.2f} |")
        text += ["\nInterprétation : la page des disponibilités passe de 111 requêtes SQL pour 10 combinaisons à 921 pour 100 puis 9 021 pour 1 000, soit `9 × N + 21` sur ce jeu. Le coût des requêtes par combinaison est donc démontré. La page d'allocations paginée reste à 23 requêtes pour 10/100/1 000 allocations ; le détail d'une DA brouillon reste à 26 requêtes pour 1/10/50 lignes, mais temps et réponse croissent avec le contenu. Ces résultats ne couvrent pas les frises actives ni de nombreux transferts en attente.\n",
                 "Priorité proposée : préagrégation du tableau des disponibilités et recette d'équivalence des soldes, puis mesure des rafraîchissements de tâches et des captures historiques sur PostgreSQL. Le scénario à 1 000 combinaisons est un signal de risque de latence ; aucune extrapolation de débit de production n'est légitime à partir de ces trois répétitions instrumentées.\n"]
    text += ["\n## Annexe A — Dictionnaire des données exhaustif\n",
            "Extraction des modèles métier enregistrés par Django. Les tables auth, sessions, admin et contenttypes sont fournies par Django ; leurs migrations restent requises. `null` concerne SQL ; `blank` concerne la validation de saisie. Les tables M2M automatiques ne sont pas de nouveaux modèles métier.\n"]
    models = [m for m in apps.get_models() if m._meta.app_label in APPS]
    text.append(f"{len(models)} modèles métier enregistrés, dont {sum(m._meta.proxy for m in models)} proxies ; {len({m._meta.db_table for m in models})} tables concrètes métier distinctes, hors tables M2M automatiques.\n")
    for model in models:
        meta = model._meta
        text += [f"\n### {meta.label}\n", f"Table : `{meta.db_table}`. Proxy : {'oui' if meta.proxy else 'non'}. Ordre : `{meta.ordering}`.\n",
                 "| Champ | Libellé | Type / format | Null | Vide | Relation / suppression | Unicité / index | Défaut / validateurs |\n| --- | --- | --- | --- | --- | --- | --- | --- |"]
        choices = []
        for field in meta.get_fields():
            if field.auto_created and not field.concrete:
                continue
            dimensions = [f"{key}={getattr(field,key)}" for key in ("max_length", "max_digits", "decimal_places") if getattr(field, key, None) is not None]
            relation = ""
            if field.is_relation:
                relation = field.remote_field.model._meta.label
                delete = getattr(field.remote_field, "on_delete", None)
                if delete:
                    relation += " / " + delete.__name__
            flags = [label for yes, label in ((field.primary_key,"PK"), (field.unique,"UNIQUE"), (getattr(field,"db_index",False),"INDEX")) if yes]
            validations = []
            if field.has_default():
                default = field.default
                validations.append("défaut=" + (getattr(default, "__module__", "") + "." + getattr(default, "__name__", type(default).__name__) if callable(default) else repr(default)))
            for validator in field.validators:
                limit = getattr(validator, "limit_value", None)
                validations.append(type(validator).__name__ + (f"({limit})" if limit is not None and not callable(limit) else ""))
            text.append("| " + " | ".join(map(safe, (field.name, field.verbose_name, field.__class__.__name__+" "+", ".join(dimensions), field.null, field.blank, relation, ", ".join(flags), "; ".join(validations)))) + " |")
            if field.choices:
                choices.append(f"\nValeurs de `{field.name}` : " + "; ".join(f"`{a}` = {b}" for a,b in field.choices) + ".\n")
        text += choices
        if meta.constraints:
            text += ["\nContraintes :"] + ["- `"+safe(c)+"`" for c in meta.constraints]
        if meta.indexes:
            text += ["\nIndex déclarés :"]+["- `"+safe(i)+"`" for i in meta.indexes]
        if meta.permissions:
            text += ["\nPermissions métier :"]+[f"- `{meta.app_label}.{code}` : {label}" for code,label in meta.permissions]
        m2m = [f for f in meta.many_to_many if f.remote_field.through._meta.auto_created]
        if m2m:
            text += ["\nTables de liaison automatiques :"]+[f"- `{f.remote_field.through._meta.db_table}` pour `{f.name}`." for f in m2m]
    text += ["\n## Annexe B — Routes applicatives\n", "L'administration possède ses routes générées par Django ; elle n'est pas développée ici route par route. Les décorateurs extraits ne résument pas tous les contrôles conditionnels du corps de vue ; lire aussi le code référencé.\n", "| URL | Nom Django | Vue | Décorateurs et méthode |\n| --- | --- | --- | --- |"]
    def walk(patterns, prefix="", namespace=""):
        for pattern in patterns:
            path = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                if path != "admin/":
                    walk(pattern.url_patterns,path,namespace+(pattern.namespace+":" if pattern.namespace else ""))
            else:
                cb=pattern.callback
                try:
                    original = inspect.unwrap(cb)
                    node = ast.parse(textwrap.dedent(inspect.getsource(original))).body[0]
                    decorators = "; ".join(ast.unparse(d) for d in getattr(node, "decorator_list", []))
                except (OSError, TypeError, SyntaxError):
                    decorators = "Vue Django native ; consulter sa configuration"
                text.append(f"| `/{path}` | `{namespace}{pattern.name or ''}` | `{cb.__module__}.{cb.__name__}` | {safe(decorators)} |")
    walk(get_resolver().url_patterns)
    text += ["\n## Annexe C — Index du code et des symboles\n", "Les signatures et corps font autorité dans les fichiers indiqués. Cette liste inclut les hooks et chargements indirects, sans supposer qu'un symbole non importé directement est mort.\n"]
    for root in APPS:
        for path in sorted((ROOT/root).rglob("*.py")):
            if "migrations" in path.parts or path.name.startswith("test"):
                continue
            source=path.read_text(encoding="utf-8-sig")
            tree=ast.parse(source)
            symbols=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
            if not symbols:
                continue
            relative=path.relative_to(ROOT).as_posix()
            text.append(f"\n### `{relative}`\n")
            for symbol in symbols:
                description=ast.get_docstring(symbol) or ""
                methods=", ".join(n.name for n in symbol.body if isinstance(n,ast.FunctionDef)) if isinstance(symbol,ast.ClassDef) else ""
                text.append(f"- [{symbol.name}](../{relative}#L{symbol.lineno}) — {'classe' if isinstance(symbol,ast.ClassDef) else 'fonction'}, ligne {symbol.lineno}. {description}" + (f" Méthodes : `{methods}`." if methods else ""))
    text += ["\n## Annexe D — Migrations et protections de schéma\n",
             "Toutes les migrations sont conservées. Cette liste résume leurs opérations déclarées ; pour les détails SQL et les conditions de moteur, consulter la source. Les fonctions RunPython qui installent des triggers/contraintes ne sont pas une modification des seuls modèles Python.\n",
             "| Migration | Dépendances déclarées | Opérations / fonctions |\n| --- | --- | --- |"]
    for root in APPS:
        for path in sorted((ROOT/root/"migrations").glob("*.py")):
            if path.name=="__init__.py":
                continue
            tree=ast.parse(path.read_text(encoding="utf-8-sig"))
            dependencies=[];operations=[]
            for node in ast.walk(tree):
                if isinstance(node,ast.Assign):
                    names=[n.id for n in node.targets if isinstance(n,ast.Name)]
                    if "dependencies" in names:
                        dependencies.append(ast.unparse(node.value))
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=="migrations":
                    labels=[f"{k.arg}={ast.unparse(k.value)}" for k in node.keywords if k.arg in ("model_name","name")]
                    if node.func.attr=="RunPython" and node.args:
                        labels.append(ast.unparse(node.args[0]))
                    operations.append(node.func.attr+(" ("+", ".join(labels)+")" if labels else ""))
            relative=path.relative_to(ROOT).as_posix()
            text.append(f"| [{path.stem}](../{relative}) | {safe('; '.join(dependencies))} | {safe('; '.join(operations))} |")
    text += ["\n## Annexe E — Contrôles d'exploitation à compléter avant production\n",
             "| Sujet | Contrôle et preuve attendue |\n| --- | --- |",
             "| Secrets et settings | Clé et identifiants hors dépôt, DEBUG désactivé, hôtes explicitement limités ; ne pas publier leur valeur dans les preuves |",
             "| DB PostgreSQL | Migrations appliquées, contraintes/triggers vérifiés, tests de concurrence exécutés, sauvegarde/restauration testée |",
             "| Transport/session | TLS, cookies Secure/HttpOnly/SameSite, proxy correctement déclaré, expiration et déconnexion testées sur configuration cible |",
             "| Serveur/statique | Serveur WSGI/ASGI de cible et gestion des fichiers statiques choisis par l'exploitation ; runserver réservé au local |",
             "| Courriels | Backend réellement choisi, timeouts et reprise documentés, ordonnanceur installé, monitoring de la file et tests d'obsolescence |",
             "| Observabilité | Identifiant de requête/corrélation si retenu, journaux sans secrets, taux d'erreur/latence, saturation et taille des historiques |",
             "| Reprise | RPO/RTO convenus, procédure de restauration et reprise de notifications, absence de rejeu contradictoire des réceptions |",
             "| Qualification | Navigateurs cibles, campagne P0/P1 signée, écarts acceptés et résultats PostgreSQL joints |"]
    return "\n".join(text)+"\n"


def make_workbook(manual, automated, results):
    book=Workbook(); info=book.active; info.title="Mode emploi"
    info.append(["Plan de tests ERP", "14 novembre 2026"])
    for row in [("Cas manuels",len(manual)),("Tests automatisés",len(automated)),("Statuts manuels","Non exécuté, OK, KO, Bloqué, NA"),("Priorité","P0 critique ; P1 majeur"),("Règle","Ne pas confondre attendus et résultats réellement observés"),("Référence","Lire PLAN_TESTS.md et le jeu de données avant exécution"),("Lecture des longues cellules","Agrandir la hauteur de ligne ou ouvrir la cellule pour voir la procédure/code intégral"),("Dernière campagne auto",results.get("finished_at","Non exécutée")),("Mesures","La campagne de charge et les tests PostgreSQL ne sont pas réputés passés en SQLite")]:info.append(row)
    for row in DATA:info.append(row)
    sheet=book.create_sheet("Recette manuelle")
    sheet.append(["ID","Domaine","Priorité","Objectif","Profil","Préconditions","Données","Procédure ordonnée","Résultats attendus","Statut","Résultat observé","Preuve","Anomalie","Testeur","Date","Build"])
    for case in manual:
        sheet.append([case["id"],case["domain"],case["priority"],case["title"],case["actor"],case["pre"],case["data"],"\n".join(f"{i}. {v}" for i,v in enumerate(case["steps"],1)),"\n".join(f"{i}. {v}" for i,v in enumerate(case["expected"],1)),"Non exécuté"])
    validation=DataValidation(type="list",formula1='"Non exécuté,OK,KO,Bloqué,NA"',allow_blank=False)
    validation.errorTitle="Statut inconnu";validation.error="Choisir une valeur de la liste.";validation.showErrorMessage=True
    sheet.add_data_validation(validation);validation.add(f"J2:J{sheet.max_row}")
    auto=book.create_sheet("Tests automatisés")
    auto.append(["ID","Type","Test exact / objectif contractuel","Commande individuelle","Préconditions / setUp","Procédure exécutée (code réel)","Assertions / attendus exacts","Statut réellement exécuté","Motif / résultat","Fichier","Ligne"])
    executed={x["test"]:x for x in results.get("tests",[])}
    for test in automated:
        item=executed.get(test["name"],{})
        auto.append([test["id"],test["kind"],test["name"],test["command"],test["setup"],test["source"],"\n".join(test["assertions"]),item.get("status","Non exécuté"),item.get("reason",""),test["path"],test["line"]])
    for ws,column in ((sheet,"J"),(auto,"H")):
        for status,color in (("OK","DCFCE7"),("KO","FEE2E2"),("Erreur","FEE2E2"),("Bloqué","FEF3C7"),("Ignoré","FEF3C7"),("Non exécuté","E2E8F0")):
            ws.conditional_formatting.add(f"{column}2:{column}{ws.max_row}",CellIsRule(operator="equal",formula=[f'"{status}"'],fill=PatternFill("solid",fgColor=color)))
    trace=book.create_sheet("Couverture")
    trace.append(["Domaine","Cas manuels","Responsable recette","Validation"])
    for domain,count in Counter(c["domain"] for c in manual).items():trace.append([domain,count,"À désigner","Non exécuté"])
    runs=book.create_sheet("Exécutions")
    runs.append(["Campagne","Build/commit","Environnement","Moteur DB/version","Navigateur","Début","Fin","Testeur","Périmètre","Verdict","Lien preuves"])
    defects=book.create_sheet("Anomalies")
    defects.append(["ID","Test lié","Titre","Sévérité S0-S3","Préconditions","Étapes","Attendu","Obtenu","Preuve","Build","Statut","Correctif","Retest"])
    dashboard=book.create_sheet("Synthèse")
    dashboard.append(["Indicateur","Valeur"])
    dashboard.append(["Manuels total",len(manual)])
    for status in ("Non exécuté","OK","KO","Bloqué","NA"):
        dashboard.append(["Manuels "+status,f'=COUNTIF(\'Recette manuelle\'!J2:J{sheet.max_row},"{status}")'])
    dashboard.append(["Automatisés / dernière campagne",results.get("summary",{}).get("total","Non exécuté")])
    dashboard.append(["Succès automatisés",results.get("summary",{}).get("passed","Non exécuté")])
    dashboard.append(["Ignorés automatisés",results.get("summary",{}).get("skipped","Non exécuté")])
    dashboard.append(["Échecs / erreurs",results.get("summary",{}).get("failed",0)+results.get("summary",{}).get("errors",0)])
    for ws in book:
        ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="173F63")
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment=Alignment(vertical="top",wrap_text=True)
                if isinstance(cell.value,str) and cell.value.startswith(("=","+","-","@")) and ws.title!="Synthèse":cell.data_type="s"
        for col in ws.columns:
            letter=col[0].column_letter
            width=18 if col[0].value in ("ID","Statut","Priorité","Domaine","Ligne") else 48
            ws.column_dimensions[letter].width=width
        if ws.title=="Tests automatisés":
            for col in ("E","F","G"):ws.column_dimensions[col].width=70
        for i in range(2,ws.max_row+1):ws.row_dimensions[i].height=100 if ws.title in ("Recette manuelle","Tests automatisés") else 34
    book.save(DOCS/"PLAN_TESTS.xlsx")


def main():
    manual=manual_cases();automated=automated_cases()
    results_path=DOCS/"resultats_tests.json"
    results=json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else {}
    plan=DOCS/"PLAN_TESTS.md"
    prose=plan.read_text(encoding="utf-8").split(MARKER)[0]
    sections=[MARKER,"\n## Catalogue des cas manuels et flux complets\n",f"{len(manual)} cas documentés. Leur état initial est **Non exécuté** ; la présence d'un scénario n'est pas une preuve de réussite.\n"]
    for domain,count in Counter(c["domain"] for c in manual).items():
        sections.append(f"\n### Domaine {domain} — {count} cas\n")
        for c in (c for c in manual if c["domain"]==domain):
            sections += [f"\n#### {c['id']} — {c['title']}\n",f"Priorité : {c['priority']}. Acteur : {c['actor']}. Préconditions : {c['pre']}.\n",f"Données : {c['data']}.\n","Procédure :\n"]
            sections += [f"{i}. {step}." for i,step in enumerate(c["steps"],1)]
            sections += ["\nRésultats attendus :\n"]+[f"- {item}." for item in c["expected"]]
            sections += ["\nPreuves : statut, identifiant de l'objet et capture/réponse ou extrait de journal expurgé. Après le cas : relever les soldes/états modifiés, puis rétablir le jeu QA indépendant décrit en préambule.\n"]
    sections += ["\n## Catalogue automatisé exhaustif\n",f"{len(automated)} tests réellement découverts par Django. Chaque commande sélectionne un test précis ; son setUp et son scénario sont reproduits dans le classeur. Les assertions ci-dessous sont les conditions réellement codées, et non des résultats supposés.\n"]
    for test in automated:
        sections += [f"\n### {test['id']} — `{test['name']}`\n",f"Type : {test['kind']}. Source : [{test['path']}:{test['line']}](../{test['path']}#L{test['line']}).\n", "Préconditions : dépendances installées ; base de tests créée par Django ; setUp de la classe exécuté automatiquement. La procédure exacte et les données sont dans le classeur et le corps du test référencé. Ne pas préparer ces données dans une base métier.\n",f"```powershell\n{test['command']}\n```\n","Attendus contractuels :\n"]
        sections += [f"- `{safe(value)}`" for value in test["assertions"]] or ["- Lire le contexte assertRaises et le scénario exact dans le classeur ; le runner doit signaler OK, sans exception non attendue."]
    plan.write_text(prose+"\n"+"\n".join(sections),encoding="utf-8")
    tech=DOCS/"DOCUMENTATION_TECHNIQUE.md"
    source=tech.read_text(encoding="utf-8").split(MARKER)[0]
    tech.write_text(source+"\n"+technical_annex(),encoding="utf-8")
    make_workbook(manual,automated,results)
    print(json.dumps({"manual":len(manual),"automated":len(automated),"generated_at":datetime.now(timezone.utc).isoformat()}))


if __name__=="__main__":
    main()
