# Conventions graphiques de BF ERP

Les pistes 1 (institutionnelle) et 5 (nocturne) partagent la même structure :
navigation latérale, en-tête personnel et espace de travail sur fond neutre.
Sur petit écran, la navigation devient horizontale au-dessus du contenu.

- Police : Segoe UI, puis les polices système. Corps 14 px ; titre principal 30 px.
- Clair : fond `#F3F6FA`, panneaux blancs, texte `#18364D`, action `#164675`.
- Sombre : fond `#102335`, panneaux `#172E43`, texte `#ECF3F9`, action `#89C5ED`.
- Navigation : bleu `#163F6B` en clair, bleu nuit `#0B1B2B` en sombre.
- Cartes : angles de 10 px ; boutons et champs : angles de 6 px.
- Statuts : toujours un libellé lisible, avec une couleur complémentaire.
- Les couleurs du logo sont des accents d’identité ; éviter de les multiplier
  dans les actions métier. Le nom et les accents sont actuellement composés
  en HTML/CSS ; ils ne constituent pas le fichier officiel du logo.

Le bouton clair/sombre est disponible sur la connexion, les pages métier et
l’administration. Sans préférence enregistrée, le thème suit le système.
Le choix est enregistré dans `localStorage` sous `bf-erp-theme`, pour ce
navigateur et cette origine ; il est partagé entre les onglets et la fenêtre
de consultation du budget. Il ne dépend pas du compte utilisateur.
L’impression utilise des fonds clairs.

Pour les nouveaux écrans métier, étendre `purchasing/base.html`, utiliser les
variables de `purchasing/static/purchasing/erp.css` et éviter les couleurs en
ligne. La fenêtre de budget charge le même CSS et le même script de thème.
L’administration conserve ses composants Django avec les couleurs définies
dans `admin-theme.css` et les surcharges de `templates/admin/`.

Vérification du comportement du sélecteur : `node --test tests/theme.test.cjs`.
