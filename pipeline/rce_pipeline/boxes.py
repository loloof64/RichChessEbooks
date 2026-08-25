"""Step 3c — moving each token's box onto the ink it names.

A token's box is the union of the boxes the text layer gives its characters,
and on a scan those are the OCR's own. Tesseract writes invisible text in a
substitute font and lets the advances of that font place the characters inside
the word it read, so the boxes drift: on Boussole page 65 the layer spreads
`8.g5` over 22.4 points where the ink covers 17.8, and by the `g` it is half a
character out. The move's box then starts in the middle of the previous
character and ends in the white space after the move.

Nothing downstream reads a box for meaning, so none of this changes what the
pipeline makes of the book. What it changes is the one thing the archive is
for: the box **is** the tap zone, the rectangle the reader presses to open the
position, and a zone half a character out is the difference between opening a
move and opening the one beside it.

The correction is a word at a time. A word's ink is easy to find — it is the
run of dark columns between two white ones — and mapping the layer's word onto
it is one scale and one shift, applied to every token inside. Per word rather
than per line because that is the unit Tesseract boxes: within a word the
error grows character by character, and between words it starts again.
"""

from __future__ import annotations

from typing import Any, Iterable

from .extract import BBox, Page
from .tokenize import Token

#: Rendering scale. The ink only has to be found, not measured, so this is
#: half what `weight` needs.
ZOOM = 2.0

#: Grey below which a pixel is ink.
INK = 128

#: How far either side of the layer's word the ink is looked for, as a share
#: of the word's width. The error being corrected is a fraction of a character
#: and the search must not reach into the next word.
_MARGIN = 0.25

#: A column with less ink than this is white. One stray dark pixel is a speck
#: of the scan, not a letter.
_MIN_COLUMN = 1

#: The widest run of white, in points, that may stand inside one word. The
#: gaps between the letters of a word are a fraction of a point and the space
#: between two words is three, so this separates them — which it has to: the
#: search reaches past the word on both sides, and without it the tail of the
#: word before is taken for the start of this one and every box moves a
#: character to the left.
_MAX_GAP = 1.6

#: The ink found must look like the word the layer drew. The error being
#: corrected is a fifth of the width — Boussole's layer spreads `8.g5` over
#: 22.4 points where the ink covers 17.8, a scale of 0.79 — so a run half the
#: layer's width, or wider than the layer plus the margin the search was given,
#: is something else standing on the line: a rule, the frame of a diagram, the
#: word beside it. The box is then left exactly as the layer drew it.
_MIN_SCALE, _MAX_SCALE = 0.55, 1.35


def snap(pdf_path: str, pages: Iterable[Page], tokens: Iterable[Token],
         *, zoom: float = ZOOM) -> int:
    """Move every token's box onto the ink of the word it was read from.

    Returns how many boxes moved. The tokens are modified in place.
    """
    import numpy as np

    from .extract import fitz

    tokens = [t for t in tokens if t.bbox is not None]
    by_page: dict[int, list[Token]] = {}
    for token in tokens:
        by_page.setdefault(token.page, []).append(token)

    moved = 0
    doc = fitz.open(pdf_path)
    try:
        for page in pages:
            here = by_page.get(page.number)
            if not here:
                continue
            sheet = doc[page.number - 1]
            pixmap = sheet.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width
            )
            height = sheet.rect.height
            for start, end in _words(page):
                mapping = _ink_of(image, page, start, end, height, zoom)
                if mapping is None:
                    continue
                for token in here:
                    if token.start >= start and token.end <= end:
                        token.bbox = _remapped(token.bbox, *mapping)
                        moved += 1
        return moved
    finally:
        doc.close()


def _words(page: Page) -> list[tuple[int, int]]:
    """The runs of characters between whitespace, as index pairs."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for index, char in enumerate(page.chars):
        blank = char.char.isspace() or char.bbox.w <= 0 or char.bbox.h <= 0
        if blank:
            if start is not None:
                out.append((start, index))
                start = None
        elif start is None:
            start = index
    if start is not None:
        out.append((start, len(page.chars)))
    return out


def _ink_of(
    image: Any, page: Page, start: int, end: int, height: float, zoom: float
) -> tuple[float, float, float, float] | None:
    """This word's ink as `(layer_x0, layer_w, ink_x0, ink_w)`, or None.

    None wherever the ink cannot be told from the layer with confidence: no
    dark column at all, or a run so unlike the layer's word that it is
    something else — a rule, the edge of a diagram, the next word entirely.
    """
    import numpy as np

    boxes = [c.bbox for c in page.chars[start:end] if c.bbox.w > 0 and c.bbox.h > 0]
    if not boxes:
        return None
    layer_x0 = min(box.x for box in boxes)
    layer_x1 = max(box.x + box.w for box in boxes)
    top = height - max(box.y + box.h for box in boxes)
    bottom = height - min(box.y for box in boxes)
    if layer_x1 <= layer_x0:
        return None

    margin = (layer_x1 - layer_x0) * _MARGIN
    left = max(0, int((layer_x0 - margin) * zoom))
    right = min(image.shape[1], int((layer_x1 + margin) * zoom) + 1)
    band = image[
        max(0, int(top * zoom)) : min(image.shape[0], int(bottom * zoom) + 1),
        left:right,
    ]
    if band.size == 0:
        return None
    columns = (band < INK).sum(axis=0) >= _MIN_COLUMN
    # The run of ink the word's own middle stands in, and not whatever else
    # the margin caught: outwards from the centre, across the gaps a word
    # holds and never across the space beside it.
    middle = int(((layer_x0 + layer_x1) / 2) * zoom) - left
    middle = max(0, min(len(columns) - 1, middle))
    gap = max(1, int(_MAX_GAP * zoom))
    if not columns[middle]:
        near = np.flatnonzero(columns)
        if near.size == 0:
            return None
        middle = int(near[np.argmin(np.abs(near - middle))])
    first = last = middle
    while first > 0 and columns[max(0, first - gap) : first].any():
        first = int(np.flatnonzero(columns[max(0, first - gap) : first])[0]) + max(0, first - gap)
    while last < len(columns) - 1 and columns[last + 1 : last + 1 + gap].any():
        window = np.flatnonzero(columns[last + 1 : last + 1 + gap])
        last = last + 1 + int(window[-1])
    ink_x0 = left + first
    ink_x1 = left + last + 1
    ink_width = (ink_x1 - ink_x0) / zoom
    scale = ink_width / (layer_x1 - layer_x0)
    if not _MIN_SCALE <= scale <= _MAX_SCALE:
        return None
    return layer_x0, layer_x1 - layer_x0, ink_x0 / zoom, ink_width


def _remapped(
    box: BBox, layer_x0: float, layer_w: float, ink_x0: float, ink_w: float
) -> BBox:
    scale = ink_w / layer_w
    x = ink_x0 + (box.x - layer_x0) * scale
    return BBox(round(x, 2), box.y, round(box.w * scale, 2), box.h)
