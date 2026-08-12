# `rce-pipeline`

Extracts chess moves — with the box each one occupies on its page — from a PDF chess
book, and packages them into a `.rce` archive for the Flutter reader.

v1 handles two notations: **figurine Unicode**, and **plain letters** in any of the
supported languages (`en`, `fr`, `de`, `es`, `it`, `nl`).

Both are read from the text layer. A third kind of book has no readable piece symbols in
that layer at all — a **scan**, whose OCR lands every symbol on an arbitrary character
(`♘`→`4)`, `♕`→`W`, `♗`→`2`), and a **figurine font**, whose layer holds the latin
letters the font draws pieces from. For those the symbols are read off the page images
by a trained classifier and written back in as figurines, after which the rest of the
pipeline is unchanged; see [Books whose symbols are only in the
image](#books-whose-symbols-are-only-in-the-image).

## Running it

The normal front end is [`../notebooks/rce_pipeline.ipynb`](../notebooks/rce_pipeline.ipynb)
in Google Colab. The notebook holds no logic: it installs the dependencies, calls this
package, and shows the results — including a rendered page with the extracted boxes
drawn on top, which is the only check that really tells you whether a clickable zone
will land on its move.

Locally, if you want it:

```bash
pip install -e .[dev]          # .[glyphs] alone for the recogniser without pytest
python -c "from rce_pipeline import run; print(run('book.pdf', output_path='book.rce').report())"
pytest
```

The recogniser's dependencies (`scikit-learn`, `scikit-image`, `numpy`, `pillow`) are an
extra rather than a requirement: a book with a usable text layer never loads them.

## The five steps

Each writes its artefact to `work_dir` before the next starts, so a step can be
changed and re-run without redoing the ones before it. On a 400-page book, extraction
dominates the runtime and is the one you least often need to repeat.

| Module | Does | Artefact |
| --- | --- | --- |
| `extract.py` | Text and per-**character** geometry, via PyMuPDF | `01_pages.json` |
| `scan.py` | Printed lines rebuilt from the layer's boxes, and their crops | — |
| `glyphs.py` | The piece symbols in those crops, written back into the pages | `01b_glyphs.json` |
| `notation.py` | Figurine Unicode, figurine font, or letters — and which language | `02_notation.json` |
| `tokenize.py` | Typed tokens (move, number, bracket, prose), each keeping its box | `03_tokens.json` |
| `parse.py` | Move tree, legality against `python-chess`, FEN reconstruction | `04_moves.json` |
| `package.py` | The `.rce` archive | `book.rce` |

Character granularity in step 1 is what lets a box cover the move alone: books glue
moves to their punctuation (`14.Nf3!,` `e4)`), and a word-level box would swallow it.

`scan.py` and `glyphs.py` sit beside step 1 rather than in the chain: they run only when
`run(glyph_model=...)` is given and the book needs them. They are described under [Books
whose symbols are only in the image](#books-whose-symbols-are-only-in-the-image).

## Books whose symbols are only in the image

Most of the target corpus is scanned. The reason a scan cannot simply be read is worth
recording, because it rules out the obvious fixes.

A scanned PDF carries an OCR text layer. Its **prose** is usually good. Its **moves**
are not, because they are set in bold and in a figurine font, and a general-purpose OCR
engine has no category for a knight glyph — it emits whatever latin character looked
closest. Observed in one French book:

| OCR text layer | Actually printed |
| --- | --- |
| `23.4)xf7! Exf7 24.We6` | `23.♘xf7! ♖xf7 24.♕e6` |
| `24.Axg6!? hxg6 25.\Wxg6+ Lh8 26.2x£7 @h7` | `24.♘xg6!? hxg6 25.♕xg6+ ♔h8 26.♗xf7 ♘h7` |
| `24...26 25.Web Sg7 26.Wxf7+ Gh6` | `24...g6 25.♕e6 ♔g7 26.♕xf7+ ♔h6` |

Two things this rules out. The substitution is not a stable cipher — the knight comes
out as `4)`, `A` and `@` on one page — so a fixed lookup table cannot work. And the
damage is not confined to piece symbols: in `24...26` for `g6` it is the *file letter*
that is wrong, and in `Web` for `We6` the *digit*. So repairing by edit distance cannot
work either, at any threshold that does not also invent moves.

What can work is not reading that layer at all: the OCR's character **boxes** are
usually placed correctly even when the characters are wrong, so they locate the move
tokens on the page. Crop those boxes from the page image at high resolution and
recognise them against the tiny alphabet chess notation actually uses — `a`–`h`,
`1`–`8`, `x`, `+`, `#`, `=`, `O`, `-`, and six piece shapes — with legality as the
final filter. A constrained recogniser over ~25 symbols is a far easier problem than
general OCR, and the piece glyphs are visually distinctive.

Both halves are built: `scan.py` locates the lines, `glyphs.py` reads the piece symbols
in them. What it does *not* do is re-read the squares — the measurements below are why.

A book set in a figurine **font** turns out to be the same problem and takes the same
fix. Its layer holds `tlJf3` where `♘f3` is printed, which is unreadable for exactly the
reason a scan's `4)xf7` is; the symbols are in the image and nowhere else. Such a book
used to be reported unparseable and now goes through the same recovery pass.

### Finding the printed lines

`scan.py` regroups the OCR layer's boxes into the lines the book printed, and renders
each one. A line is the unit because a recogniser needs the horizontal context — word
crops read far worse — and because it is what the boxes support: they are placed
right even where the characters under them are wrong.

```python
lines = scan.segment_lines(page)                 # every printed line
with scan.PageRenderer(pdf_path) as renderer:    # 360 dpi, grayscale
    for line in scan.notation_lines(lines):      # the ones carrying a move number
        renderer.crop(line)
```

Three things were wrong before they were measured, and each is a rule in the module:

- **Columns come first.** The gutter of the book this was written against is 7 points
  wide, half a line height, so any merge rule based on distance joins a line on the
  left to whatever sits beside it on the right. `split_columns` instead takes the
  vertical cut that the fewest boxes cross, which finds the gutter on all ten
  two-column pages of the sample and reports none on the single-column ones.
- **Consecutive line boxes overlap**, by two or three points, because OCR boxes are
  taller than their type. The overlap has to go to the line *above*: it is where
  descenders live, and a `g` cut down to its bowl reads as `a` — which turns `g6` into
  a square that was never printed. Splitting the overlap evenly, which looks fairer,
  cost 6 points of square recall.
- **Diagrams reach MuPDF as text.** A rank of a board arrives as a few narrow boxes
  strung across the width of the diagram, where a line of prose covers ~95% of its own
  width. Coverage separates the two. What survives the filter is never selected for
  re-reading anyway: it carries no move number.

On the 12-page sample this yields 622 lines, of which 249 carry notation. The line
boxes drawn back onto the page sit on the printed lines.

### Re-reading the squares: what the constrained Tesseract is worth

Now that the crops come from real segmentation, the recipe could be measured instead
of admired. Two pages, the 32 lines carrying moves, the 63 squares printed on them
read off the page by eye, and one number: how many of those squares a source
recovers, in order.

| Source | Squares recovered | Squares invented |
| --- | --- | --- |
| The scan's own OCR layer | 58 / 63 (92%) | 0 |
| Whitelist re-OCR of the crop, 360 dpi | 56 / 63 (89%) | 21 |
| Whitelist re-OCR, upscaled 2x | 58 / 63 (92%) | 21 |
| Whitelist re-OCR, upscaled 4x | 53 / 63 (84%) | 20 |

So the constrained re-OCR is not the fix it looked like. At its best it *ties* the
layer it was meant to replace, and pays for the tie with 21 squares that were never on
the page — because the whitelist has no way to say "this is a knight": every piece
glyph is forced into some letter and digit, and `♗c4` comes back carrying an extra
`a2`. It does rescue 2 of the 5 squares the embedded layer misses, which is worth
something, but not as a replacement — as a second opinion on a token already known to
be doubtful.

The earlier hand-made-crop result that made this look promising still reproduces,
and is still a single line: the one line where the embedded layer failed badly.

### Where the errors actually are

The useful part of that measurement is not the score, it is where the five failures
of the embedded layer sit. Every one of them is a square inside a move that begins
with a piece glyph — `♘xe4` arriving as `Axes`, `♕xe4` as `Wxed`, `♖f1` as `21` —
and not one is in a pawn move, a castling, or a square named in prose. The scanner's
own segmentation is thrown by the glyph and takes the character next to it down with
it.

That reframes the job. The squares are 92% right already and their errors are
localised: what has to be recognised is the piece glyphs, plus the two or three
characters beside each one. The whole-line re-OCR is attacking the 92% that was not
broken.

### Masking the glyphs before re-OCR: measured, does not work

The obvious repair — blank the piece glyphs so the whitelist stops inventing squares
out of them — was tried and made things worse: 84% → 73–76% recall, with the phantom
squares unchanged. Piece glyphs really are much wider than letters, but the width is
not measurable on this book at 360 dpi, because its bold type touches: whole runs like
`xe4` come out as one connected component, so a width threshold blanks real text. 115
components were masked on 32 lines, several times the number of glyphs printed on
them. Isolating a glyph needs the classifier, or a segmentation that survives touching
type — not a bounding box.

### The glyph classifier

The trained piece classifier lives outside this repository, at
`entrainement_ocr_echecs/6class/chess_glyphs_classifier.zip`. `glyphs.GlyphClassifier`
loads it from the zip, the unpacked directory or the pickle. Measured findings, so the
work is not redone:

- It is a `RandomForestClassifier` over **1767 features**: `skimage.hog` on the glyph
  resized to 32x32, `orientations=9`, `pixels_per_cell=(4,4)`, `cells_per_block=(2,2)`
  — 1764 values — followed by the crop's **aspect ratio, mean and standard deviation**.
  Nothing records this; it was recovered by matching feature counts, then confirmed by
  scoring the training glyphs back through the model. An earlier reading of this file
  called those last three unused, which is wrong and would have cost real accuracy:
  the aspect ratio alone carries 1.9% of the model's importance, its split thresholds
  land exactly between the classes' ratios (0.75 for `R`, 0.80 `B`, 0.86 `K`/`Q`, 0.91
  `N`), and feeding zeros instead drops the median confidence on the training glyphs
  from 0.999 to 0.965 — which matters, because confidence is the only thing separating
  a piece from a letter here.
- Its five classes are ordered `K, Q, R, B, N` — chess order, **not** alphabetical.
  Assuming alphabetical yields a clean permutation matrix and 0.1% accuracy, which
  looks like a broken model and is not one.
- On its own data it scores **99.9%**, and still 99.9% after deduplication. That number
  is an upper bound, not a generalisation estimate: the ~10,000 files per class hold
  only ~1,300 distinct images, and they are what it was trained on.
- It has **no "not a piece" class**, so every glyph handed to it comes back as a piece.
  Confidence separates them instead: on its own data, pieces score a median of 0.96 and
  ordinary letters 0.33, and a threshold of 0.5 keeps 100% of pieces while admitting
  0.1% of letters.
- On glyphs cut from a real scanned page it identified all four pieces in the test strip
  correctly (`Q K Q K`) with **no false positives among 22 letter and digit components**,
  but at lower confidence — 0.55 to 0.82 rather than 0.96. A threshold tuned on its
  training data would have dropped one of the four. Tune it per book.
- Piece glyphs are also far wider than letters at the same point size (41–44 px versus
  23 px at 360 dpi). That is an independent signal, free to compute, worth combining
  with the classifier's confidence.

`min_samples_split=5000` holds every tree to a median depth of 6 and 12 leaves. Given
the accuracy above, that is not currently hurting; it is worth knowing before anyone
concludes the model is more sophisticated than it is.

The classifier covers piece symbols only, which the measurements above suggest is
most of what is missing: the squares are 92% right in the layer already, and the ones
that are wrong are the ones standing next to a glyph.

### Reading the symbols off the page: what it is worth

`glyphs.py` cuts the ink of a rendered line into connected components, offers the ones
shaped like a piece to the classifier, and keeps what comes back confident enough.
Scored against the 54 symbols printed on two hand-read pages of the French scan:

| Confidence | Symbols recovered | Symbols invented |
| --- | --- | --- |
| 0.35 | 54 / 54 (100%) | 8 |
| 0.40 | 53 / 54 (98%) | 1 |
| **0.45** | **53 / 54 (98%)** | **0** |
| 0.50 | 48 / 54 (89%) | 0 |
| 0.60 | 41 / 54 (76%) | 0 |

0.45 is the knee, and is the default. The one symbol missed is a bishop scoring 0.38 —
bishops score lowest on this book, which is worth remembering when tuning another.
`scripts/eval_glyphs.py` reproduces the table (`--sweep`) against
`scripts/sample_truth.json`, the hand-read transcript of those two pages.

Two of the three gates are geometric, and they are doing most of the work. A candidate
must be **1.45 to 2.6 times the page's median component width** — the median component
is a letter, and a piece glyph is about twice one — and **no wider than 1.1 times its own
height**. That second one is the important one: bold notation touches at 360 dpi, so
`xe4` arrives as a single blob wide enough to pass for a symbol, and nothing else
distinguishes it. Without the aspect gate the same settings invent 8 pieces instead of
none. The reference width is taken over the whole page, not the line: `4.♘g5!!` is a
real line, and four characters cannot supply a median.

### Writing the symbols back: only as good as the layer's boxes

A recognised symbol has to replace the characters the scanner read under it, and that
depends on boxes this pipeline did not produce. Tesseract does not box characters
individually — it boxes a word and divides that box evenly among the characters it read
— so a symbol twice as wide as a letter overlaps its neighbour's box by half.

`glyphs.placement_score` measures the damage on any book, with no ground truth: what
share of the symbols written in ended up at the head of a move (`♘xe4`) rather than
beside one (`♘ZJg3`). It separates the two sample books cleanly:

| Book | Layer | Symbols | At the head of a move |
| --- | --- | --- | --- |
| French scan (`CommentDevenirSuperAttaquant`) | `GlyphLessFont`, tight boxes | 53 | 41 (77%) |
| `BoussoleSurEchiquier` | loose boxes, `tZJ` for `♘` | 105 | 48 (46%) |

The first reads `1.Dxe4! Acxe4 2.Hxe4! Axes` back as `1.♘xe4! ♘cxe4 2.♖xe4! ♘xes` —
every symbol at the head of its move, and the two remaining errors (`xes`, `xed`) the
scanner's own, in the squares. The second lands symbols one character off (`♘ZJg3`),
which no recogniser can fix: the boxes are wrong before the classifier is asked
anything. The score is printed in `run().report()` and flagged below 75%.

Two decisions inside that pass, both measured:

- **A character has to be 80% covered to be replaced.** At 50% the `x` of `♘xe4` is
  swallowed with the symbol and the move becomes `♘e4` — still legal, no longer the one
  printed, which is precisely the failure this pipeline refuses everywhere else. At 80%
  the same ambiguity costs a character instead (`♘g5` can come out `♘5`), the move is
  unreadable and the reader is asked.
- **Modelling the even division does not work.** Since the symbol's real width is
  measured, the word's remaining characters can be re-laid-out to predict which ones the
  symbol covers. Tried, and worse on both books: 77% → 68% and 46% → 12%. Tesseract's
  layout is evidently not the even division it appears to be, and the plain overlap rule
  beats a wrong model of it.

A book at 46% is not worth parsing from its layer. Reading those pages in full — squares
included — is the next thing to try, and the [re-OCR measurements](#re-reading-the-squares-what-the-constrained-tesseract-is-worth)
above say a whitelist Tesseract will not be how it is done.

### Settings for the constrained Tesseract

Should the whitelist pass come back as a second opinion on doubtful tokens, these are
the settings it was measured with, and they are not incidental:

- Alphabet restricted to `abcdefgh12345678xX+#=O-`, `--psm 7 --oem 1`, grayscale.
- **A whole line, not a word.** Word-by-word crops with tight padding returned garbage
  (`25.ee`, `e7`); Tesseract needs the horizontal context.
- **Not per character.** `--psm 10` on segmented components was far worse than either.
- **Upscaling is not free.** 2x helps, 4x hurts (92% → 84%), and `--psm 13` and `6`
  read the same as `7`.

## Two decisions worth knowing about

**Repairs are conservative.** When a move does not parse, it is compared against the
position's legal moves under an edit distance where scanner confusions (`0`/`O`,
`1`/`l`, `8`/`B`) cost half of an ordinary substitution — and only those get through.
Allowing one full substitution would repair far more moves, and would also turn `Qh9`
into `Qh5` and `Nc6` into `Nc3`: squares differ by a single character all the time, so
the pipeline would emit legal but wrong moves that silently corrupt every position
further down the line. A move that cannot be read from its shape is reported `broken`,
shown in red by the app, and settled by the user against the printed page.

**Moves need a number to be read.** Chess books are full of move-shaped text — figure
captions, "diagram b4", page references. `strict_numbering` (on by default) only reads
a move when a move number has just announced one, or when variation brackets make the
context unambiguous. Pass `strict_numbering=False` for a book that prints long
unnumbered sequences.

## Tests

`tests/test_parse.py` covers the move tree and the legality pass — variation branching,
comment attachment, castling written with zeros, repairs, and the ambiguity cases
(`Nd2` where both `Nbd2` and `Nfd2` are legal). It builds tokens directly rather than
going through a PDF, since that part of the job does not need a document.

`tests/test_glyphs.py` covers the half of the recovery pass that does not need the
model: which crops are offered to it, with a stub in its place, and how a recognised
symbol is written back into a page. Whether the model recognises a knight is measured by
`scripts/eval_glyphs.py`, not asserted — the numbers are in the tables above.

`tests/test_scan.py` covers line segmentation the same way, from boxes rather than
from a scan: the narrow gutter, fragments of one line, overlapping line boxes, diagram
debris, and which lines get selected for re-reading.

Extraction geometry is not unit-tested: no assertion is as convincing as the notebook's
step 7, which draws the boxes on the rendered page.
