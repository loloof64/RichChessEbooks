"""Step 3b — the weight a move number is printed in, measured on the page.

A publisher who typesets the game score bold and the analysis around it plain
marks, character by character, the line a move belongs to.
:mod:`rce_pipeline.extract` reads that straight off the span for a book that
was typeset. For a scan there is nothing to read: its text layer is the OCR's
own — one subsetted face for the whole page, every character of it plain — and
the weight survives only in the ink. This measures it there.

What is measured is **stroke thickness**, which is scale-free: threshold the
token's box in a rendering of the page and erode the ink twice with a 3x3. A
bold stem keeps its core; a hairline disappears. One erosion does not separate
the two, two do — measured on Grivas, where the score's numbers keep 10 to 28
per cent of their ink and the analysis's keep 0 to 3.

Only the **move numbers** are measured, for two reasons. It is the number
whose meaning is in doubt, and it is the number that carries the signal: a
figurine is a dense drawing, so the moves printed with one overlap between the
weights while the numbers beside them do not.

The threshold is **learned per book and never chosen**. Two groups have to be
told apart and where they sit depends on the scan, so the split is taken where
it separates them best and then made to prove itself: the heavier group's floor
must stand clear of the lighter group's ceiling. On Grivas it stands at three
times it, with an empty band between. On Boussole the two touch — its numbers
run in one unbroken band from 0.00 to 0.25 — and nothing is read from it,
which is the right answer: that book marks its score in no way this can see.
"""

from __future__ import annotations

from typing import Any, Iterable

from .tokenize import Token

#: Rendering scale. At 4x a 9pt digit is about thirty pixels tall, which is
#: enough body for two erosions to have something left to measure.
ZOOM = 4.0

#: Grey below which a pixel is ink. A scan's paper sits well above this and its
#: type well below; the value is not delicate.
INK = 128

#: A box with less ink than this is not worth asking about — a stray box, or
#: one the extractor gave a token that printed nothing.
_MIN_DARK = 20

#: How far apart the two groups have to stand before the split is believed:
#: the heavier group's floor at twice the lighter group's ceiling. This is the
#: whole of the per-book decision, and it is a fact about the printing rather
#: than a number chosen to fit — Grivas clears it at 3.0, Boussole fails it at
#: 1.0, with its two groups touching.
_SEPARATION = 2.0

#: Percentile taken for each group's edge instead of its extreme value. One
#: token box overlapping a diagram is enough to make a group's extreme say
#: nothing about the group. A lighter group that erodes away to nothing at all
#: has a ceiling of zero, which is the cleanest separation there is and not a
#: division to guard against: only an empty heavier group refuses the split.
_EDGE = 2.5

#: Fewer numbers than this and there is no distribution to split.
_MIN_SAMPLES = 40


def mark(pdf_path: str, tokens: Iterable[Token], *, zoom: float = ZOOM) -> int:
    """Set `bold` on the move numbers a scan printed in its heavier weight.

    Returns how many were marked. Zero means the book does not mark its score
    in a way the ink can show, and every token is left as it was.

    Nothing here touches a book whose text layer already carries the weight:
    that reading is free and this one costs a rendering of every page.
    """
    tokens = list(tokens)
    numbers = [t for t in tokens if t.kind == "move_number" and t.bbox is not None]
    if len(numbers) < _MIN_SAMPLES:
        return 0
    thickness = _measure(pdf_path, numbers, zoom)
    measured = [(token, value) for token, value in zip(numbers, thickness) if value is not None]
    if len(measured) < _MIN_SAMPLES:
        return 0
    split = _split([value for _, value in measured])
    if split is None:
        return 0
    marked = 0
    for token, value in measured:
        if value > split:
            token.bold = True
            marked += 1
    return marked


def _measure(pdf_path: str, tokens: list[Token], zoom: float) -> list[float | None]:
    """Stroke thickness for each token's box, None where there is no ink.

    One page is held in memory at a time. A rendering at 4x is some tens of
    megabytes, and a book has hundreds of pages.
    """
    import numpy as np

    from .extract import fitz

    doc = fitz.open(pdf_path)
    try:
        # Filled by index rather than appended to: the tokens are walked a
        # page at a time, which is not the order they came in unless they
        # happened to be sorted.
        out: list[float | None] = [None] * len(tokens)
        for number in sorted({token.page for token in tokens}):
            page = doc[number - 1]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width
            )
            height = page.rect.height
            for at, token in enumerate(tokens):
                if token.page != number:
                    continue
                box = token.bbox
                assert box is not None
                # A BBox is in PDF points from the bottom of the page and the
                # rendering is indexed from the top.
                top = height - box.y - box.h
                cell = image[
                    max(0, int(top * zoom)) : int((top + box.h) * zoom),
                    max(0, int(box.x * zoom)) : int((box.x + box.w) * zoom),
                ]
                dark = cell < INK
                if dark.sum() < _MIN_DARK:
                    continue
                out[at] = float(_eroded(_eroded(dark)).sum()) / float(dark.sum())
        return out
    finally:
        doc.close()


def _eroded(mask: Any) -> Any:
    """A 3x3 binary erosion: a pixel survives only with all eight neighbours.

    Written out rather than taken from `scipy.ndimage` so that reading a book's
    weight needs nothing beyond numpy, which the pipeline already leans on.
    """
    import numpy as np

    rows, columns = mask.shape
    padded = np.pad(mask, 1, constant_values=False)
    out = np.ones_like(mask)
    for dy in range(3):
        for dx in range(3):
            out &= padded[dy : dy + rows, dx : dx + columns]
    return out


def _split(values: list[float]) -> float | None:
    """The thickness that separates the two weights, or None if there is one.

    The split maximising the separation between the two groups it makes, which
    is Otsu's on a list rather than a histogram; then the test that says
    whether there were two groups to begin with.
    """
    import numpy as np

    if len(values) < 2:
        return None
    ordered = np.sort(np.asarray(values, dtype=float))
    total = ordered.sum()
    running = np.cumsum(ordered)[:-1]
    counts = np.arange(1, len(ordered))
    below = running / counts
    above = (total - running) / (len(ordered) - counts)
    # Between-class variance, up to the constant factor that does not move the
    # maximum. Ties are left in: two equal values either side of a split make
    # the split unusable anyway, and the separation test below refuses it.
    score = counts * (len(ordered) - counts) * (above - below) ** 2
    at = int(np.argmax(score))
    split = float((ordered[at] + ordered[at + 1]) / 2)

    lighter, heavier = ordered[: at + 1], ordered[at + 1 :]
    ceiling = float(np.percentile(lighter, 100 - _EDGE))
    floor = float(np.percentile(heavier, _EDGE))
    if floor <= 0.0 or floor < _SEPARATION * ceiling:
        return None
    return split
