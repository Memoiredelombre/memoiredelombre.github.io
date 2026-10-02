# Tests automatiques — Mémoire de l'Ombre

Ce dossier contient une suite de tests automatiques (Playwright) qui vérifie,
sans intervention humaine, que les parcours principaux de l'appli
fonctionnent toujours après une modification du code : navigation dans le
catalogue, connexion admin, gestion de la liste de souhaits.

Ils ne touchent jamais votre vraie base Supabase ni votre vrai bucket
Scaleway : un faux backend (`mock_stub.js`) est injecté dans une copie de
`index.html` pour simuler des données sans réseau.

## Fichiers

- `mock_stub.js` — faux Supabase / Leaflet / fetch, avec 30 objets et une
  liste de souhaits factices en mémoire.
- `build_preview.py` — construit `preview.html` (une copie de `index.html`
  avec le faux backend injecté juste après le script Leaflet). Ce fichier
  généré est ignoré par git, il n'a pas besoin d'être commité.
- `test_navigation.py` — mode invité, scroll infini du catalogue, ouverture
  d'une fiche, retour (bouton de l'appli + bouton "précédent" du
  navigateur) avec restauration de la position de scroll, absence des
  informations privées pour un invité.
- `test_admin.py` — connexion (bons/mauvais identifiants), apparition des
  informations privées une fois connecté, création et édition d'un objet
  via le formulaire, le select "Département" (liste fixe + saisie libre via
  "Autre"), déconnexion.
- `test_wishlist.py` — l'onglet Souhaits est masqué pour un invité et
  visible pour l'admin, ajout de souhaits, ouverture d'une fiche de
  souhait avec restauration du scroll, conversion d'un souhait en objet du
  catalogue ("Trouvé").
- `test_sources.py` — les sources d'une fiche objet (références, lien,
  document joint) : invisibles sur la fiche d'un objet qui n'en a pas,
  aucune gestion possible depuis la fiche elle-même (même en admin), ajout
  puis modification d'une source (avec lien + fichier joint, via le mock de
  la fonction serverless "photo-storage" — voir `__FAKE_BUCKET__` dans
  `mock_stub.js`) depuis le formulaire de modification de l'objet,
  affichage en lecture seule sur la fiche, puis suppression.

Chaque test vérifie aussi qu'aucune erreur JavaScript ne s'est produite
pendant le parcours qu'il joue.

## Lancer les tests

Il faut Python 3 et Playwright (`pip install playwright && playwright
install chromium`, une seule fois). Ensuite, depuis la racine du dépôt :

```
python3 tests/build_preview.py
python3 tests/test_navigation.py
python3 tests/test_admin.py
python3 tests/test_wishlist.py
python3 tests/test_sources.py
```

Chaque script affiche `[OK]` ou `[FAIL]` ligne par ligne, et se termine par
un résumé. Un script qui échoue s'arrête avec un code de sortie différent
de zéro (pratique pour l'intégrer plus tard à une vérification automatique
avant mise en ligne, par exemple une "GitHub Action").

## Pourquoi ce dossier existe

Avant, toute vérification après une modification se faisait à la main, en
rechargeant le site et en cliquant partout. Cette suite fait la même chose
en quelques secondes et de façon fiable — elle peut détecter une régression
introduite par erreur (par exemple si une future modification cassait à
nouveau la restauration du scroll) avant même de mettre le site en ligne.
