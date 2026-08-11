# Rich Chess Ebook (.rce) — contexte projet

Projet de programmation : OCR / extraction de livres d'échecs numériques (PDF, EPUB en v2)
et enrichissement avec des positions FEN cliquables, empaquetées dans une archive `.rce`.

## Architecture générale

Deux composants séparés, reliés par un contrat de données strict (voir schéma ci-dessous) :

1. **Pipeline Python** (prototypé en Google Colab, à terme un package pip installable) :
   extrait le texte et les coordonnées d'un PDF, détecte la notation (figurine / texte,
   langue), parse les coups + variantes + commentaires, reconstruit les FEN avec
   `python-chess`, empaquette le tout dans une archive `.rce`.
2. **App Flutter** : importe l'archive `.rce`, affiche le PDF avec un viewer exposant la
   matrice de transformation par page (`pdfrx` recommandé plutôt que
   `syncfusion_flutter_pdfviewer`), superpose des zones cliquables au-dessus des coups,
   ouvre un échiquier statique à l'appui, et permet de corriger les erreurs de liaison.

**Ne pas traiter PDF et EPUB avec le même modèle de coordonnées.** Le PDF a une
pagination fixe (page, x, y, largeur, hauteur en points PDF, origine en bas à gauche).
L'EPUB est reflowable : pas de coordonnées stables, ancrage nécessaire dans le DOM
(id de span ou CFI). Traiter l'EPUB comme une v2 distincte, pas une extension du même code.

## Format `.rce`

Une archive ZIP contenant :

- le fichier source (PDF, EPUB en v2) inchangé
- `moves.json` — généré par le pipeline, immuable
- `patches.json` — optionnel, écrit uniquement par l'app Flutter (corrections utilisateur)
- `manifest.json` — métadonnées : hash SHA-256 du fichier source, langue détectée,
  type de notation, version du schéma

## Schéma `moves.json` (à finaliser en étape 1 du développement)

Chaque coup est un nœud avec :

- `id` (identifiant unique du coup)
- `parent_id` (coup précédent, pour reconstruire les variantes en arbre)
- `san` (notation du coup)
- `fen` (position résultante)
- `page`, `bbox` (`x`, `y`, `w`, `h` en points PDF)
- `variation_index` (0 = ligne principale, >0 = variante)
- `comment` (texte associé, si présent et interprété comme cohérent)
- `confidence`, `status` (`ok` / `uncertain` / `broken`) — posés par l'étape de
  validation légale du pipeline

## Schéma `patches.json`

Correctifs superposés au fichier de base à la lecture (jamais d'édition directe de
`moves.json` — traçabilité et re-génération du pipeline sans perdre les corrections
manuelles). Types de correctifs :

- `san_edit` — coup retapé par l'utilisateur, revalidé par le moteur de règles côté
  Flutter (`dartchess` ou équivalent), FEN recalculée
- `bbox_edit` — zone cliquable redéfinie manuellement sur la page
- `fen_override` — saisie directe de la FEN (cas non rejouables : diagrammes sans
  coup, positions non standard)

Chaque correctif porte `move_id`, `type`, `source` (`user`/`auto`), `timestamp`.
Une correction doit se propager : rejouer automatiquement la chaîne de FEN depuis le
coup corrigé jusqu'au prochain conflit ou la fin de la ligne. Le hash du fichier
source dans `manifest.json` sert à détecter une incompatibilité si l'utilisateur
réimporte une autre édition du même livre.

## Pipeline Python — étapes

1. Extraction texte + bbox par mot (`PyMuPDF`/`fitz` ou `pdfplumber` ; couche texte
   déjà présente dans la majorité des PDF modernes — l'OCR (Tesseract) n'est utile
   que pour les scans, et donne des bbox moins fiables)
2. Détection de la notation : figurine Unicode (U+2654–265F, triviale) vs police
   figurine (glyphe rendu à partir d'une lettre latine — détectable via le nom de
   police par span) vs texte en toutes lettres (langue à détecter par fréquence des
   lettres initiales : `R D T F C` en français, `K D T L S` en allemand,
   `K Q R B N` en anglais). Proposer le résultat à l'utilisateur en confirmation,
   pas en question à froid.
3. Parsing des coups, variantes imbriquées, commentaires — gérer aussi les erreurs
   d'OCR fréquentes (`0`↔`O`, `l`↔`1`, `B`↔`8`, `x`↔`×`) comme candidats de correction
   automatique quand un coup est illégal
4. Validation légale coup par coup avec `python-chess`, reconstruction des FEN,
   marquage `confidence`/`status`
5. Empaquetage en `.rce`

Chaque étape écrit son artefact intermédiaire sur disque (`01_spans.json`,
`02_tokens.json`, etc.) pour permettre de relancer une étape sans tout refaire.

## Risques à valider en premier (spikes, avant tout développement en profondeur)

1. **Flutter** : le calcul de la zone cliquable au-dessus d'un mot, à partir de
   coordonnées PDF (points, origine bas-gauche), doit rester correct au zoom et
   au défilement.
2. **Python** : robustesse de la reconstruction FEN face aux erreurs d'OCR et à
   la désambiguïsation SAN (`Nbd2`, prises en passant, roque, promotion).

## Ordre de développement recommandé

1. Figer le schéma JSON ci-dessus (le contrat entre les deux composants)
2. Écrire un fixture manuel (8-10 coups, une page PDF réelle, valeurs saisies à la main)
3. Spike Flutter sur ce fixture (sans dépendre du pipeline Python)
4. Spike Python sur la même page, comparer la sortie au fixture
5. Brancher les deux, élargir la couverture, construire l'UI de correction

## Décisions déjà prises

- Format de sortie : JSON (pas de binaire — le gain de compression est nul une fois
  dans le ZIP, la débogabilité est bien plus importante)
- EPUB : reporté en v2, modèle de coordonnées incompatible avec le PDF
- Correction : se fait côté Flutter (pas de retour dans Colab), car l'utilisateur ne
  détecte une erreur qu'en lisant le livre dans l'app
