"""Step 1c — reading the piece glyphs of a scanned page from the page image.

:mod:`rce_pipeline.scan` locates the printed lines of a scan and renders them.
This module reads the one thing in those lines that the OCR layer gets
uniformly wrong: the piece symbols. A general-purpose engine has no category
for a knight, so it emits whichever latin character looked closest (`♘` comes
back as `4)`, `A` or `@` on a single page), and the squares beside the symbol
are dragged down with it. Everything else in the layer — prose, move numbers,
most squares — is good enough to keep.

The recogniser is a `RandomForestClassifier` trained outside this repository
on cut-out piece glyphs, five classes and no "not a piece" class. Three things
follow from that and shape the whole module:

Geometry does the rejecting
    Since every crop handed to the classifier comes back as a piece, the crops
    have to be chosen before it sees them. A piece glyph is about twice as wide
    as a letter of the same type and nearly square; a letter is neither, and a
    run of touching bold letters — which is what `xe4` becomes at 360 dpi — is
    far wider than tall. Width relative to the page's own letters, plus aspect
    ratio, admits the glyphs and almost nothing else.

Confidence does the rest
    On its training data the model scores pieces at a median of 0.999 and
    ordinary letters at 0.33. On glyphs cut from a real scan the pieces drop to
    0.45–0.85, so the gap narrows but survives: see
    :data:`DEFAULT_MIN_CONFIDENCE` for what the threshold is worth, and expect
    to tune it for a book whose type is lighter or heavier than this one.

The result is written back as figurines
    :func:`repair_page` replaces the characters the OCR invented under a glyph
    with the Unicode piece it actually is, carrying the glyph's real box rather
    than the invented characters' boxes. The repaired page is an ordinary
    figurine page from then on: the rest of the pipeline needs no change, and
    the clickable zone the reader ends up with covers the printed symbol.
"""

from __future__ import annotations

import dataclasses
import io
import os
import pickle
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .extract import GLYPH_FONT, BBox, Char, Page
from .notation import FIGURINE_TO_LETTER
from .scan import (
    DEFAULT_DPI,
    LineImage,
    PageRenderer,
    notation_lines,
    segment_lines,
)

#: The classifier's classes, in the order it was trained with: chess order,
#: King to Knight, *not* alphabetical. Reading them as alphabetical yields a
#: clean permutation of the confusion matrix and 0.1% accuracy, which looks
#: like a broken model and is not one.
PIECES = ("K", "Q", "R", "B", "N")

#: What a recognised piece is written as. Unicode figurines rather than SAN
#: letters, because that is what a figurine book's text layer would have held
#: in the first place — the tokeniser already maps them, and a reader looking
#: at the repaired page sees the symbol that is printed.
FIGURINES = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘"}

#: Side of the square the classifier's features are computed on.
FEATURE_SIZE = 32

#: Length of the vector the model expects: 1764 HOG values plus three
#: measurements of the crop itself.
FEATURE_COUNT = 1767

#: Least confidence to accept a piece. Measured on two pages of a French
#: scanned book, against the 54 glyphs printed on them: 0.45 recovers 52 and
#: invents none, and every value up to 0.50 also invents none while recovering
#: fewer. Below 0.40 phantom pieces start appearing in prose. The margin is
#: narrower than the training data suggests — tune it per book, with
#: `scripts/eval_glyphs.py` if the book can be given a ground truth.
DEFAULT_MIN_CONFIDENCE = 0.45

#: Width of a candidate, as a multiple of the page's median component width —
#: which is a letter, since letters vastly outnumber everything else. Piece
#: glyphs measured 1.5 to 2.2 on the sample book; the upper bound leaves room
#: for a wider face while stopping well short of a two-letter run.
MIN_WIDTH_RATIO = 1.45
MAX_WIDTH_RATIO = 2.6

#: Widest a candidate may be relative to its own height. Piece glyphs are drawn
#: nearly square (0.9–1.0); two touching letters are 1.4 and up. This is the
#: single most useful filter of the three — without it the same settings invent
#: 8 pieces on the sample instead of none.
MAX_ASPECT = 1.1

#: Ink blobs smaller than this are speckle, an accent, or the dot of an `i`.
MIN_COMPONENT_WIDTH = 3
MIN_COMPONENT_HEIGHT = 6

#: How much of a character's box a glyph must cover before that character is
#: taken to be part of the glyph and replaced by it.
#:
#: High, and deliberately so. Tesseract's OCR layer does not box characters
#: individually: it boxes a word and divides that box evenly among the
#: characters it read, so the boxes beside a piece symbol — which is twice as
#: wide as a letter — are all shifted, and a symbol overlaps its neighbour by
#: half. At 0.5 the `x` of `♘xe4` is swallowed with the symbol and the move
#: becomes `♘e4`: still legal, no longer the one in the book. At 0.8 the same
#: ambiguity costs a character instead (`♘g5` can come out `♘5`), the move is
#: unreadable, and the reader is asked. Losing a move beats inventing one.
MIN_CHAR_OVERLAP = 0.8

_FIGURINE_SET = frozenset(FIGURINES.values())

#: A symbol at the head of a move: `♘f3`, `♘bd2`, `♖1xe4`, `♗xc6`. Used to
#: check where the symbols landed, not to read them — the tokeniser does that.
_IN_MOVE = re.compile(r"[♔♕♖♗♘][a-h1-8]?x?[a-h][1-8]")


@dataclass(frozen=True)
class PieceGlyph:
    """One piece symbol found on the page image, and where it was printed."""

    piece: str  # K, Q, R, B or N
    confidence: float
    page: int
    #: The glyph's own box in PDF user space, from the ink rather than from the
    #: OCR layer's idea of where the characters were.
    bbox: BBox
    #: Width as a multiple of the page's median letter width, kept because it
    #: is an independent signal from the confidence and worth seeing together
    #: with it when a book needs tuning.
    width_ratio: float

    @property
    def figurine(self) -> str:
        return FIGURINES[self.piece]

    def to_json(self) -> dict[str, Any]:
        return {
            "piece": self.piece,
            "confidence": round(self.confidence, 3),
            "page": self.page,
            "bbox": self.bbox.to_json(),
            "width_ratio": round(self.width_ratio, 2),
        }


class GlyphClassifier:
    """The trained piece classifier, and the feature vector it expects.

    Nothing in the model records how its features were built; this is the
    recovered recipe, confirmed by scoring the training glyphs back through it.
    A crop becomes 1767 numbers: `skimage.hog` on the glyph resized to 32x32
    with `orientations=9`, `pixels_per_cell=(4, 4)`, `cells_per_block=(2, 2)`
    — 1764 of them — then the crop's aspect ratio, mean and standard deviation.

    Those last three are easy to mistake for padding, and are not. Feeding
    zeros in their place still classifies the training glyphs correctly, but
    drops the median confidence on them from 0.999 to 0.965 — and confidence is
    what tells a piece from a letter here, so the margin is the whole point.
    """

    def __init__(self, model: Any):
        expected = getattr(model, "n_features_in_", FEATURE_COUNT)
        if expected != FEATURE_COUNT:
            # Fail here rather than several hundred crops later inside the
            # model: a different count means the features were built some other
            # way, and this module's recipe would produce confident nonsense.
            raise ValueError(
                f"model expects {expected} features, this recipe produces {FEATURE_COUNT}"
            )
        self._model = model

    @classmethod
    def load(cls, path: str) -> "GlyphClassifier":
        """Load the classifier from its zip, its directory, or the pickle.

        The trained model ships as `chess_glyphs_classifier.zip`, holding
        `glyphs_results/classifier.pkl` beside the glyphs it was trained on.
        All three forms are accepted so a Colab session can point at the file
        it just uploaded without unpacking it first.
        """
        if os.path.isdir(path):
            return cls.load(os.path.join(path, "classifier.pkl"))
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                names = [n for n in archive.namelist() if n.endswith("classifier.pkl")]
                if not names:
                    raise ValueError(f"no classifier.pkl inside {path}")
                with archive.open(sorted(names, key=len)[0]) as handle:
                    return cls(pickle.load(handle))
        with open(path, "rb") as handle:
            return cls(pickle.load(handle))

    def classify(self, image: Any) -> tuple[str, float]:
        """Classify one grayscale crop as a piece, with its confidence."""
        return self.classify_many([image])[0]

    def classify_many(self, images: Sequence[Any]) -> list[tuple[str, float]]:
        """Classify crops in one call — the model is far faster in batches."""
        if not images:
            return []
        import numpy as np

        features = np.vstack([features_of(image) for image in images])
        probabilities = self._model.predict_proba(features)
        return [
            (PIECES[int(row.argmax())], float(row.max())) for row in probabilities
        ]


def features_of(image: Any) -> Any:
    """The 1767-value feature vector of one grayscale crop.

    `image` is a 2-D array of 8-bit grey levels, the crop tight around the ink
    — the model was trained on tight crops, and padding one changes its aspect
    ratio, which is a feature.
    """
    import numpy as np
    from skimage.feature import hog
    from skimage.transform import resize

    array = np.asarray(image, dtype=np.float64) / 255.0
    resized = resize(array, (FEATURE_SIZE, FEATURE_SIZE), anti_aliasing=True)
    descriptor = hog(
        resized,
        orientations=9,
        pixels_per_cell=(4, 4),
        cells_per_block=(2, 2),
        feature_vector=True,
    )
    height, width = array.shape
    return np.concatenate([descriptor, [width / height, array.mean(), array.std()]])


def find_glyphs(
    images: Sequence[LineImage],
    classifier: GlyphClassifier,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_width_ratio: float = MIN_WIDTH_RATIO,
    max_width_ratio: float = MAX_WIDTH_RATIO,
    max_aspect: float = MAX_ASPECT,
) -> list[PieceGlyph]:
    """Find the piece glyphs in a page's rendered lines.

    Give it every line of a page at once, not one at a time: the width a
    candidate is measured against is the median over all of them, and a short
    line — `4.♘g5!!` is a real one — has too few letters to supply its own.
    """
    decoded = [(image, _to_array(image.png)) for image in images]
    components = [_components(array) for _, array in decoded]

    reference = _median_width([box for line in components for box in line])
    if reference is None:
        return []

    glyphs: list[PieceGlyph] = []
    for (image, array), boxes in zip(decoded, components):
        candidates = [
            box
            for box in boxes
            if min_width_ratio <= box[2] / reference <= max_width_ratio
            and box[2] / box[3] <= max_aspect
        ]
        crops = [array[y : y + h, x : x + w] for x, y, w, h in candidates]
        for (x, y, w, h), (piece, confidence) in zip(
            candidates, classifier.classify_many(crops)
        ):
            if confidence < min_confidence:
                continue
            glyphs.append(
                PieceGlyph(
                    piece=piece,
                    confidence=confidence,
                    page=image.line.page,
                    bbox=image.to_pdf(x, y, w, h),
                    width_ratio=w / reference,
                )
            )
    return glyphs


def recover_pieces(
    pdf_path: str,
    pages: Sequence[Page],
    classifier: GlyphClassifier,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    dpi: int = DEFAULT_DPI,
) -> tuple[list[Page], list[PieceGlyph]]:
    """Read the piece symbols off the page images and write them into `pages`.

    The whole of the recovery pass, for a book whose text layer holds no
    readable piece symbols: a scan, whose OCR guessed at them, or a book set in
    a figurine *font*, whose layer holds the latin letters the font draws
    pieces from. Both are the same problem here — the symbols are only in the
    image — and both are fixed by the same pass.

    Only the lines carrying a move number are rendered, which is what keeps
    this affordable: on the sample book that is 249 lines out of 622.
    """
    found: list[PieceGlyph] = []
    with PageRenderer(pdf_path, dpi=dpi) as renderer:
        for page in pages:
            lines = notation_lines(segment_lines(page))
            images = [renderer.crop(line) for line in lines]
            found.extend(
                find_glyphs(images, classifier, min_confidence=min_confidence)
            )
    return repair_pages(pages, found), found


#: The move's own square, in file and rank.
_FILES = frozenset("abcdefgh")
_RANKS = frozenset("12345678")


def _file_the_symbol_swallowed(page: Page, start: int, end: int) -> Char | None:
    """The file letter a glyph's box reached past its own ink to take.

    A symbol is twice a letter's width and `_covered_range` divides a word's
    box evenly, so the range can end one character late: SuperAttaquant prints
    `20.♗b5!!` and the pass writes `20.♗5!!` — not a move at all, and the game
    died on it with sixty-two moves under it.

    What says so with certainty is what follows the symbol: a bare rank. A
    move goes to a square and names both halves of it, so a piece with a lone
    rank behind it has lost the file, and the last letter of the ink the
    symbol covered is that file. Where a whole square follows, the range may
    still have swallowed a *disambiguating* letter (`♘bd2` -> `♘d2`) and
    nothing on the page can tell — the reading is a move either way.
    """
    if end <= start or page.chars[end - 1].char not in _FILES:
        return None
    after = page.chars[end : end + 2]
    if not after or after[0].char not in _RANKS:
        return None
    if len(after) > 1 and after[1].char in _FILES:
        return None
    return page.chars[end - 1]


def repair_page(page: Page, glyphs: Iterable[PieceGlyph]) -> Page:
    """Write the recognised glyphs into a copy of `page`.

    Each glyph replaces the characters printed under it — whatever the scanner
    made of the symbol, which is one character or two — with the figurine, and
    that figurine carries the glyph's own box. Where the scanner dropped the
    symbol entirely (`4...♖e8` arriving as `4...e8`, which happens) the
    figurine is inserted at the position it was printed in.

    The returned page has a different character stream from the one that went
    in, so anything holding offsets into the old one — the :class:`Line` spans
    of a previous :func:`~rce_pipeline.scan.segment_lines` pass, in particular
    — no longer applies to it. Segment first, repair after.
    """
    edits: list[tuple[int, int, list[Char]]] = []
    for glyph in glyphs:
        if glyph.page != page.number:
            continue
        start, end = _covered_range(page, glyph.bbox)
        # A symbol is twice a letter's width, so the range can reach one
        # character too far and take the move's own file with it. Where it
        # did, the letter is put back and is no longer part of the ink.
        swallowed = _file_the_symbol_swallowed(page, start, end)
        ink = page.chars[start : end - 1 if swallowed else end]
        edits.append(
            (
                start,
                end,
                [
                    Char(
                        char=glyph.figurine,
                        bbox=glyph.bbox,
                        font=GLYPH_FONT,
                        size=round(glyph.bbox.h, 2),
                        # What the figurine covers is mostly the scanner's
                        # guess at the symbol, which is worthless — but the
                        # range can also swallow the disambiguating letter
                        # beside it (`♘bd2` -> `♘d2`), which nothing here can
                        # see. Kept because this is the last place it exists.
                        consumed="".join(c.char for c in ink),
                        # A recovered symbol is set in whatever weight the
                        # characters it covers were.
                        bold=any(c.bold for c in ink),
                    ),
                ]
                + ([swallowed] if swallowed else []),
            )
        )

    chars = list(page.chars)
    # Applied right to left so that an earlier edit's indices stay valid.
    for start, end, written in sorted(edits, key=lambda edit: -edit[0]):
        chars[start:end] = written

    return Page(
        number=page.number,
        width=page.width,
        height=page.height,
        text="".join(char.char for char in chars),
        chars=chars,
    )


#: How many times a spelling must have been seen before it is believed, and
#: how much of that vote the winning piece must hold. A book's OCR spells a
#: symbol the same way over and over — Boussole prints `ltJ` for a knight 60
#: times and never anything else — so what these keep out is the run of ink
#: that happens to look like two different pieces on two occasions.
_MIN_SPELLINGS = 3
_SPELLING_MAJORITY = 0.8


def spellings(pages: Sequence[Page]) -> dict[str, str]:
    """How this book's scanner spells each piece, from the symbols it restored.

    Every symbol written back over the page covers the ink the OCR made of it,
    and that ink is kept on the character (`Char.consumed`). So the book has
    already been made to spell each of its pieces several hundred times over,
    with the answer beside it: `ltJ` is a knight, `i.` a bishop, `:` a rook,
    `<it` a king, `'ii` a queen — the whole table Boussole needs, learned from
    the book itself and with no legality asked anywhere.

    That is worth having because the same spellings turn up where the glyph
    pass **failed**: a symbol it could not restore leaves exactly this ink
    standing in front of the square, and the parser was left asking the board
    which of the five pieces could reach it. Two can, often enough, and the
    move dies with the rest of the line under it.

    Keyed by the ink as :func:`~rce_pipeline.tokenize.normalise` leaves it,
    because that is the alphabet the wreck is read in.
    """
    from .tokenize import normalise

    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for page in pages:
        for char in page.chars:
            piece = FIGURINE_TO_LETTER.get(char.char)
            if piece is not None and char.consumed:
                votes[normalise(char.consumed)][piece] += 1
    table = {}
    for ink, counts in votes.items():
        piece, said = counts.most_common(1)[0]
        total = sum(counts.values())
        if total >= _MIN_SPELLINGS and said >= _SPELLING_MAJORITY * total:
            table[ink] = piece
    return table


#: What a symbol may be found standing over when it landed too far right: the
#: characters of the move beside it, never the ink of another symbol.
_MOVE_CHARS = frozenset("abcdefgh12345678x")

#: How much of the move may stand between the symbol's ink and the symbol: a
#: file, or a file and a rank. More than that and the run before is not this
#: symbol's ink but something else entirely.
_MAX_BETWEEN = 2


def unshift_symbols(page: Page, spellings: dict[str, str]) -> Page:
    """Put back a symbol that was written one group to the right of its ink.

    Tesseract does not box characters: it boxes a word and divides that box
    evenly among the characters it read. A layer that read three characters
    where a symbol is printed — `ltJ` for a knight — therefore puts the boxes
    half a letter out, and `_covered_range` picks the wrong one. The symbol is
    written over the **square** instead of over its own remains: Boussole page
    65 prints `12.♗xd5 ♘a5?` and the layer comes out `12.i.♗d5 ltJ♘5?`, with
    the bishop standing on the `x` it destroyed and the knight on the `a`.

    Neither move is then read at all — `♘5` is not a square — and on that page
    it costs Black's twelfth, after which the line is a half-move behind the
    book for the rest of the game.

    What makes it recoverable is that **a piece symbol is never printed twice
    in a row**: ink shaped like a symbol immediately before a symbol *is* that
    symbol's ink. `spellings` says which ink, in this book, and it must name
    the piece the classifier read — the classifier and the book's own habit
    agreeing is what licenses the repair, and it is why the run is taken as
    the longest **taught** spelling rather than as everything that looks like
    wreckage: `.i.g♗` is the bishop of `.i.` with the file `g` behind it, and
    swallowing that `g` would lose the square instead of saving it.

    The symbol keeps its own box, which is the measured ink; what it ate is
    given back with the box of the ink it was found on.
    """
    if not spellings:
        return page
    from .tokenize import normalise

    text = normalise(page.text)
    edits: list[tuple[int, int, list[Char]]] = []
    for index, char in enumerate(page.chars):
        piece = FIGURINE_TO_LETTER.get(char.char)
        if piece is None or not char.consumed:
            continue
        if not set(char.consumed) <= _MOVE_CHARS:
            continue
        found = _ink_before(text, index, piece, spellings)
        if found is None:
            continue
        start, between = found
        given_back = [
            Char(char=ch, bbox=page.chars[start].bbox, font=page.chars[start].font,
                 size=page.chars[start].size, bold=char.bold)
            for ch in char.consumed
        ]
        edits.append((
            start,
            index + 1,
            [dataclasses.replace(char, consumed=text[start:index])]
            + list(page.chars[index - between : index])
            + given_back,
        ))

    if not edits:
        return page
    chars = list(page.chars)
    for start, end, replacement in reversed(edits):
        chars[start:end] = replacement
    return Page(
        number=page.number,
        width=page.width,
        height=page.height,
        text="".join(char.char for char in chars),
        chars=chars,
    )


def _ink_before(
    text: str, index: int, piece: str, spellings: dict[str, str]
) -> tuple[int, int] | None:
    """Where this symbol's own ink begins, and how much of the move follows it.

    Returns `None` unless the book has been seen spelling **this** piece that
    way. Longest spelling first, and only the move's own characters may stand
    between it and the symbol.
    """
    for between in range(_MAX_BETWEEN + 1):
        end = index - between
        if between and text[end] not in _MOVE_CHARS:
            break
        for length in range(min(end, _MAX_SPELLING), 0, -1):
            if spellings.get(text[end - length : end]) != piece:
                continue
            start = end - length
            # A spelling is learned from the boxes the layer drew, and those
            # run over the space and the move number's dot beside the symbol
            # — the book spells its knight `ltJ`, ` ltJ` and `.ltJ` all at
            # once. Only the ink may be taken away: swallowing the dot of
            # `12.` welds the number to the move and loses both.
            while start < end and (
                text[start] == " "
                or (text[start] == "." and start and text[start - 1].isdigit())
            ):
                start += 1
            if start < end:
                return start, between
    return None


#: The longest ink a spelling is looked for in. `_WRECK_RUN` in `tokenize`
#: bounds the same thing from the other side.
_MAX_SPELLING = 5


def placement_score(pages: Sequence[Page]) -> tuple[int, int]:
    """How many written-in symbols landed inside a move, out of how many.

    Recognising a symbol is one problem and knowing which characters it was
    printed over is another, and the second one is only as good as the text
    layer's boxes. Tesseract does not box characters individually — it divides
    a word's box evenly among the characters it read — so a layer that read the
    right number of characters puts a symbol within half a letter of where it
    belongs, and a layer that read `tZJg3` for `♘g3` does not.

    This is the cheap check that tells those apart on any book, with no ground
    truth: a symbol that landed correctly is followed by the square its move
    goes to. Around 90% on a well-boxed layer. A low score means the symbols
    were found and then written into the wrong place, which is worth knowing
    before the moves are parsed — the pieces are right and the text they were
    spliced into is not.
    """
    placed = total = 0
    for page in pages:
        text = page.text
        for index, char in enumerate(text):
            if char not in _FIGURINE_SET:
                continue
            total += 1
            if _IN_MOVE.match(text, index):
                placed += 1
    return placed, total


def repair_pages(pages: Sequence[Page], glyphs: Iterable[PieceGlyph]) -> list[Page]:
    """:func:`repair_page` over a whole book."""
    by_page: dict[int, list[PieceGlyph]] = {}
    for glyph in glyphs:
        by_page.setdefault(glyph.page, []).append(glyph)
    return [repair_page(page, by_page.get(page.number, [])) for page in pages]


def _covered_range(page: Page, box: BBox) -> tuple[int, int]:
    """The characters of `page` a glyph box was printed over.

    Returns a half-open range of indices into `page.chars`, empty (start ==
    end) when the scanner read nothing there — the insertion point, in that
    case, is where the symbol belongs in reading order.
    """
    covered = [
        index
        for index, char in enumerate(page.chars)
        if _rows_overlap(char.bbox, box) and _mostly_inside(char.bbox, box)
    ]
    if covered:
        # A range, not a set: the characters under one glyph are consecutive in
        # the stream, and splicing needs both ends anyway.
        return covered[0], _swallow_leftovers(page, covered[-1] + 1)

    on_row = [
        index
        for index, char in enumerate(page.chars)
        if _rows_overlap(char.bbox, box)
    ]
    # Before the first character that starts no earlier than the symbol does.
    # Its left edge rather than its middle: a symbol is wider than a letter, so
    # its middle can fall past the start of the letter that follows it.
    for index in on_row:
        if page.chars[index].bbox.x >= box.x:
            return index, index
    if on_row:
        return on_row[-1] + 1, on_row[-1] + 1
    return len(page.chars), len(page.chars)


#: Characters that can follow a piece symbol inside a move: the files and ranks,
#: the capture and check marks, promotion, and the castling forms. A `b` or a
#: `d` here is a disambiguating letter, which is why this is a whitelist of what
#: to keep rather than a blacklist of what to drop.
_MOVE_BODY = frozenset("abcdefgh12345678xX+#=-Oo0")

#: How many leftover characters may be swallowed after one figurine. Four
#: covers the longest mapping seen: Grivas spells its king `'ili>` and its
#: knight `tt::l`, five characters of which the glyph's own box holds one, and
#: at three the last of them survived to stand in front of the square — `♔>xf7`,
#: `♘lxg3`, neither of which is a move. Beyond four the symbol was probably
#: placed in prose, where eating words would be worse than leaving the move
#: unreadable; a fifth is never taken on any book of the corpus, so this bound
#: is the run these mappings actually reach and not a margin over it.
_MAX_LEFTOVERS = 4


def _swallow_leftovers(page: Page, end: int) -> int:
    """Extend a glyph's range over the leftovers of a broken font mapping.

    One printed figurine can arrive in the text layer as several characters —
    `liJ` for a knight, `i..` for a bishop, `'itt` for a king — and only the
    first of them is usually inside the glyph's own box, so replacing that box
    alone leaves `NiJxc3+` where `Nxc3+` was printed. That matches no move
    pattern at all, which is worse than a wrong move: it yields no token, so
    the move vanishes instead of being reported broken.

    Geometry cannot separate those leftovers from the square that follows,
    since they are all the same size and on the same row. What separates them
    is that a leftover cannot belong to a move. Only characters outside
    :data:`_MOVE_BODY` are taken, so a square, a rank or a disambiguating
    letter is never eaten — `♘bd2` keeps its `b`.
    """
    limit = min(end + _MAX_LEFTOVERS, len(page.chars))
    while end < limit:
        char = page.chars[end].char
        # A space ends the run: leftovers are always flush against the symbol,
        # and crossing a space would join the figurine to the next word.
        if char.isspace() or char in _MOVE_BODY:
            break
        end += 1
    return end


def _rows_overlap(char_box: BBox, glyph_box: BBox) -> bool:
    if char_box.h <= 0 or char_box.w <= 0:
        return False
    overlap = min(char_box.y + char_box.h, glyph_box.y + glyph_box.h) - max(
        char_box.y, glyph_box.y
    )
    return overlap >= 0.5 * min(char_box.h, glyph_box.h)


def _mostly_inside(char_box: BBox, glyph_box: BBox) -> bool:
    overlap = min(char_box.x + char_box.w, glyph_box.x + glyph_box.w) - max(
        char_box.x, glyph_box.x
    )
    return overlap >= MIN_CHAR_OVERLAP * char_box.w


def _to_array(png: bytes) -> Any:
    import numpy as np
    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        return np.asarray(image.convert("L"), dtype="uint8")


def _components(array: Any) -> list[tuple[int, int, int, int]]:
    """Ink blobs of one line crop, as `(x, y, w, h)` in crop pixels.

    Otsu against the crop rather than a fixed level: a scan's paper is grey,
    and how grey varies down the page. Blobs are what the bold type of chess
    notation gives — its letters touch, so a blob is often a run of them and
    only geometry can say which blobs are worth classifying.
    """
    from skimage.filters import threshold_otsu
    from skimage.measure import label, regionprops

    # `<=`, not `<`: skimage's convention is that what is *above* the threshold
    # is the foreground, and on an image with only two levels — which a
    # synthetic crop is, and a hard-thresholded scan can be — Otsu returns the
    # darker one, so `<` selects nothing at all.
    ink = array <= threshold_otsu(array)
    boxes: list[tuple[int, int, int, int]] = []
    for region in regionprops(label(ink)):
        y0, x0, y1, x1 = region.bbox
        if x1 - x0 < MIN_COMPONENT_WIDTH or y1 - y0 < MIN_COMPONENT_HEIGHT:
            continue
        boxes.append((x0, y0, x1 - x0, y1 - y0))
    boxes.sort()
    return boxes


def _median_width(boxes: Sequence[tuple[int, int, int, int]]) -> float | None:
    if not boxes:
        return None
    widths = sorted(box[2] for box in boxes)
    middle = len(widths) // 2
    if len(widths) % 2:
        return float(widths[middle])
    return (widths[middle - 1] + widths[middle]) / 2
