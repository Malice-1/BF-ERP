# Alimentation des budgets par Excel

Dans **Budget → Alimenter une version**, ouvrir la version souhaitée puis choisir **Alimenter cette version via Excel**.

Le lien **Télécharger le modèle Excel** fournit :

- une feuille **Allocations**, préremplie avec les allocations actuelles de cette version ;
- trois feuilles de référence contenant les codes des produits BI, CDF et financements.

La feuille Allocations doit comporter ces colonnes, une seule fois chacune :

| Code BI | Code CDF | Code financement | Montant TVAC |
| --- | --- | --- | --- |
| MAT-01 | CDF-01 | FONDS-01 | 1250,50 |

Les codes doivent déjà exister dans les référentiels. Les conserver comme texte, notamment lorsqu’ils commencent par zéro. Chaque combinaison BI, CDF et financement ne peut figurer qu’une fois. Les montants peuvent être des nombres Excel ou des textes décimaux à virgule ou point, positifs ou nuls. Les cellules vides, formules, erreurs Excel et montants négatifs sont refusés. Les lignes entièrement vides sont ignorées.

Le montant représente le **budget total** de la combinaison. L’import remplace le montant des combinaisons présentes, crée celles qui n’existent pas et conserve les autres allocations de la version. Il ne cumule pas les montants et ne supprime aucune ligne. Réimporter les mêmes données laisse les allocations inchangées. L’import n’active ni ne publie la version.

L’export Excel existant des allocations est également accepté. Si le fichier comporte les colonnes Année et Version, leur contenu doit correspondre à la version sélectionnée.

Le fichier doit être au format `.xlsx`, de 5 Mo maximum et de 10 000 lignes de données maximum. Toutes les lignes sont contrôlées avant l’écriture. Une erreur affiche un bandeau avec les numéros des lignes concernées et annule l’import entier. Une réussite indique le nombre d’allocations créées, modifiées et inchangées.

Pendant l’import, une barre indique la progression réelle de l’envoi du fichier, puis reste animée pendant la validation et l’enregistrement. Le bouton est désactivé pendant le traitement. Le résultat ou les erreurs apparaissent directement sur la page d’import, sans redirection automatique vers le formulaire d’édition des allocations, particulièrement volumineux pour les grands fichiers.

Les droits et les protections restent ceux de l’alimentation manuelle : droits de gestion budgétaire requis, version bloquée ou supprimée non modifiable, version publiée modifiable uniquement par le superutilisateur après déblocage administratif. L’import verrouille l’enveloppe et la version pendant l’enregistrement. Les réservations, engagements et transferts ne sont pas modifiés.

Les changements sont journalisés avec le fichier, l’utilisateur, la version, les combinaisons et les montants avant/après. Un état budgétaire final est enregistré pour chaque import ayant effectivement modifié les allocations.

## Consultation des allocations

La liste des versions affiche leur total TVAC. Sur la fiche d’une version, une recherche par code ou libellé du produit actualise le tableau au fil de la saisie, avec un indicateur de chargement. Le total de la version reste visible ; une recherche affiche aussi le total des allocations filtrées, sur l’ensemble des pages.

Les allocations sont affichées par pages de 25 lignes pour conserver un affichage fluide après un import volumineux. Les totaux portent sur les montants enregistrés. L’enregistrement et les suppressions s’appliquent aux lignes de la page affichée, en conservant les autres allocations. Les modifications non enregistrées bloquent la recherche et le changement de page jusqu’à leur enregistrement pour éviter de les perdre. L’export Excel contient toutes les allocations correspondant au filtre, indépendamment de la page affichée.

Les références des produits, CDF et financements sont transmises une seule fois par page. Les listes déroulantes sont complétées au moment de leur ouverture ; leur valeur courante reste affichée immédiatement. Cela évite de répéter des centaines d’options dans chaque ligne, sans modifier les validations côté serveur. Un lien permet d’activer les listes complètes lorsque JavaScript est désactivé.
