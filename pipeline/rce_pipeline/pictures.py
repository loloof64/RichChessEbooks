"""Step 1d — the positions a book prints as a picture, read from the picture.

:mod:`rce_pipeline.diagrams` reads the books that set a diagram in a **diagram
font**, where the position is already eight lines of eight characters in the
text layer. Four of the six books in the corpus do not: they draw the board as
an image, and to the text layer their diagrams are simply not there. This
module reads those, and hands back the very same :class:`diagrams.Diagram`
blocks, so that nothing downstream can tell where a position came from.

The whole point is that **no piece recogniser is involved**. A trained
classifier would have to know one drawing of a knight from another across
every publisher, and would be wrong exactly where a book is unusual. Instead
this module only ever says *these two squares carry the same thing*: it cuts
the board into sixty-four squares, reduces each to a signature, and clusters
the signatures over the whole book. A cluster is then an invented character,
and the board becomes eight rows of eight characters — the same shape as a
diagram font, learned the same way, by :func:`diagrams.learn`, from the
positions the book's own moves reach. What a cluster means is decided by the
game, never by what the square looks like.

Two things make the signature work, and both are measured rather than assumed:

The background is thrown away, not compared
    A publisher shades the dark squares — Grivas hatches them with diagonal
    strokes — and a hatch has a phase, so two empty dark squares are not the
    same bitmap at all. Comparing raw squares gave 189 clusters where 13 were
    wanted. So each square is reduced to the **body** standing on it: the ink,
    with its holes filled and thin structures opened away. The hatch is thin
    and open, so it goes; a piece is solid once filled, so it stays. An empty
    square then holds nothing at all, whatever its colour, and a piece looks
    the same on a light square as on a dark one — which is what makes one
    diagram teach both.

The body is centred before it is compared
    Two drawings of the same rook sit a few pixels apart in their squares, and
    at ten by ten that is a large difference. The body is cropped to its own
    bounding box and scaled, and its height, width and fill are carried
    separately. Without centring the same rook clustered twice.

Colour survives all of that because the shading inside the body is kept beside
the shape: a black knight fills its silhouette with ink, a white knight leaves
it white and draws an outline. Same silhouette, different signature.

**It takes resolution, and there is a book below it.** Grivas draws its boards
at 1200 pixels — 150 to a square — and its thirty boards give thirteen
clusters and not one stray: an empty square and the twelve pieces, every board
read. Tactics draws its at 190 pixels, 24 to a square, and does not come out:
a white piece there is an outline one pixel wide, which breaks, so the holes
do not fill and the opening takes the piece away with the hatch. Its boards
read some twenty strays and no position. Rendering the page at 150, 300 and
600 dpi was measured and makes it worse, because the picture is all the
publisher stored — the resolution is not there to be had. What that book needs
is a different way to name the clusters, not a better signature: see the
handoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Sequence

from .diagrams import SIDE, Diagram
from .extract import BBox, Page

try:  # PyMuPDF 1.24.3+ renamed the module; `fitz` still works but warns.
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz

#: Least width on the page, in points, for an image to be a diagram. A board
#: is printed at about a third of the page width — 145pt in Grivas, 150pt in
#: Tactics — and this is well below both while excluding rules, logos and the
#: publisher's ornaments.
MIN_WIDTH_PT = 60.0

#: How square a board has to be. A drawn board is square to within its frame
#: and its caption is a separate object, so the tolerance only covers the few
#: rows of pixels a publisher leaves around the edge (Tactics: 200 by 194).
MIN_ASPECT, MAX_ASPECT = 0.85, 1.18

#: Most of the page an image may cover before it is taken for a scan of the
#: page rather than something printed on it. Boussole and SuperAttaquant are
#: scans: one image per page, the page itself. Reading their diagrams means
#: finding the board inside that image, which this module does not do — see
#: the module docstring of `glyphs` for the rendering machinery it would use.
MAX_PAGE_SHARE = 0.5

#: A square's own side, as a share of which the body is opened. The strokes of
#: a hatch are a twentieth of a square wide and this is twice that, so they do
#: not survive; a piece is a third of a square wide at its narrowest.
OPENING_RATIO = 0.08

#: How far into a square the signature looks. The board's own grid lines sit
#: on the boundary, and a frame the peeling missed sits just outside it.
INSET = 0.10

#: Side of the grid each square is reduced to, twice over: once for the shape
#: of the body and once for the shading inside it.
SIGNATURE_SIDE = 10

#: How far apart two signatures may be and still be the same thing, as a mean
#: absolute difference per feature. Measured on Grivas' 30 boards: 0.02 splits
#: every piece into several clusters (136 of them), 0.06 gives 13 large ones —
#: an empty square and the twelve pieces — and 0.10 begins to merge a bishop
#: with a pawn.
MERGE_DISTANCE = 0.06

#: How many squares a cluster needs before it is believed to be a piece rather
#: than an accident of one board's alignment. Two, and not more, because
#: `MAX_KINDS` is what actually does the work here: over a short run of pages
#: a queen may stand on only three boards, and asking for four would drop
#: every board she stands on. Grivas is unchanged by the difference — its
#: thinnest real cluster holds 25 squares.
MIN_SUPPORT = 2

#: How many different things a board can carry: six pieces in two colours, and
#: an empty square. This is a fact about chess rather than a threshold, and it
#: is what the clustering is held to — the fourteenth cluster of a book is a
#: second reading of a piece already found, never a new one. Grivas produced
#: sixteen believed clusters where thirteen exist, and the three extra ones
#: were what left thirteen of its thirty boards unreadable.
MAX_KINDS = 13

#: How far a stray may be from a believed cluster and still be read as one.
#: Beyond it the square keeps a character of its own, which no diagram teaches
#: and `diagrams.decode` therefore refuses — the board is dropped rather than
#: guessed at, which is the same bargain the diagram font path makes.
STRAY_DISTANCE = 0.12

#: Where the invented characters start. The private use area is used because
#: the alternative — ordinary letters — would collide with a book that also
#: sets diagrams in a font, and because `diagrams._case_partner` leaves these
#: alone: two clusters are not two cases of one letter, and nothing should
#: extend one to the other.
_FIRST_CHAR = 0xE000

#: How far from square a located board may be, **as a share of one square**,
#: before the picture is taken to hold more than the board and dropped. A few
#: pixels between the two sides only means the cells are not quite square,
#: which costs nothing; a quarter of a square means the region is not the
#: board, and dividing it by eight would put every rank out. Measured: Grivas
#: sits at 0.06 of a square once the frame locates the board, Tactics — whose
#: whole board is 190 pixels — at 0.17, and the one picture that was genuinely
#: wrong, a speck of dirt above the frame taken for the board's edge, at 0.30.
#: Which part of such a picture is the board cannot be recovered from the
#: shading: a grid a third of a square out still has two thirds of every cell
#: in the right square, and a search over offsets measured on Grivas chose the
#: wrong one.
SQUARE_TOLERANCE = 0.25

#: How much of a line has to be ink before it is the board's frame rather than
#: something printed on the board. Measured over the Grivas images: a frame
#: line is 0.87 to 0.99 — it blurs across several columns, so it does not
#: always reach 1 — while the inkiest rank of a position is 0.44.
FRAME_INK = 0.5

#: A board's shading, measured to tell a board from any other square picture.
#: The two colours of square differ by this much, at least, in the mean of
#: what is left once the pieces are taken off.
MIN_SHADE_CONTRAST = 0.04


@dataclass(frozen=True)
class Board:
    """One diagram picture, as characters, with where it was printed."""

    page: int
    rows: tuple[str, ...]
    bbox: BBox
    #: Where in the page's text the diagram was met — see `_offset_for`.
    offset: int

    def as_diagram(self) -> Diagram:
        return Diagram(
            page=self.page,
            start=self.offset,
            end=self.offset,
            rows=self.rows,
            bbox=self.bbox,
        )


def available() -> bool:
    """Whether the arrays this step works on can be loaded.

    Reading a drawn board needs numpy and scipy, which the base install does
    not carry: a book whose diagrams are text is read without them, and one
    whose diagrams are pictures is simply read without its diagrams. Asked
    here rather than at import time so that `pipeline.run` can say which of
    the two happened instead of failing on a book it could still parse.
    """
    try:
        import numpy  # noqa: F401
        from scipy import ndimage  # noqa: F401
    except ImportError:
        return False
    return True


def find(pdf_path: str, pages: Sequence[Page]) -> list[Diagram]:
    """Every diagram printed as a picture on `pages`, in reading order.

    The clustering is done over the whole book at once, and has to be: one
    board on its own says only that two of its squares differ, while thirty
    boards say that this shape is a rook, wherever it stands. A book drawing
    no boards costs one pass over its images and nothing else.
    """
    boards = list(_boards(pdf_path, pages))
    if not boards:
        return []

    labels = _cluster([square for _, squares in boards for square in squares])
    found: list[Diagram] = []
    cursor = 0
    for page, bbox, offset in (meta for meta, _ in boards):
        chars = [chr(_FIRST_CHAR + label) for label in labels[cursor : cursor + SIDE * SIDE]]
        cursor += SIDE * SIDE
        rows = tuple("".join(chars[i * SIDE : (i + 1) * SIDE]) for i in range(SIDE))
        found.append(Board(page=page, rows=rows, bbox=bbox, offset=offset).as_diagram())
    found.sort(key=lambda d: (d.page, d.start))
    return found


def _boards(
    pdf_path: str, pages: Sequence[Page]
) -> Iterator[tuple[tuple[int, BBox, int], list[Any]]]:
    """Each board picture on `pages`, with the signatures of its squares."""
    by_number = {page.number: page for page in pages}
    doc = fitz.open(pdf_path)
    try:
        for number, page in sorted(by_number.items()):
            source = doc[number - 1]
            for rect, image in _candidate_images(doc, source):
                region = _board_region(image)
                if region is None:
                    continue
                squares = _signatures(image, region)
                if squares is None:
                    continue
                bbox = BBox.from_mupdf(tuple(rect), page.height)
                yield (number, bbox, _offset_for(page, bbox)), squares
    finally:
        doc.close()


def _candidate_images(doc: Any, page: Any) -> Iterator[tuple[Any, Any]]:
    """The images on `page` shaped like a board, as greyscale arrays.

    Shape is asked of the rectangle the image occupies on the page rather than
    of its pixels: a publisher may store a board at any resolution, and it is
    what the reader sees that is square.
    """
    import numpy as np

    page_area = page.rect.width * page.rect.height
    for xref, *_rest in page.get_images(full=True):
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        rect = rects[0]
        if rect.width < MIN_WIDTH_PT or rect.height <= 0:
            continue
        if not MIN_ASPECT <= rect.width / rect.height <= MAX_ASPECT:
            continue
        if page_area and rect.width * rect.height > MAX_PAGE_SHARE * page_area:
            continue
        try:
            pixmap = fitz.Pixmap(doc, xref)
        except Exception:  # pragma: no cover - a damaged or unsupported image
            continue
        if pixmap.alpha:
            pixmap = fitz.Pixmap(pixmap, 0)
        if pixmap.n > 1:
            pixmap = fitz.Pixmap(fitz.csGRAY, pixmap)
        if pixmap.width < 8 * SIDE or pixmap.height < 8 * SIDE:
            continue
        samples = np.frombuffer(pixmap.samples, dtype=np.uint8)
        yield rect, samples.reshape(pixmap.height, pixmap.width).astype(np.float32) / 255.0


def _board_region(image: Any) -> tuple[int, int, int, int] | None:
    """The board inside the picture: its ink, less the frame drawn around it.

    A publisher frames the board, and the frame is what a naive eighth of the
    picture would put inside the outer squares — where, filled and opened, it
    becomes a body of its own and gives every corner square a cluster nobody
    else shares. The frame is peeled off instead: a line of the frame is ink
    across the whole width, which no rank of a position ever is.
    """
    import numpy as np

    ink = image < 0.5
    # The frame, not the ink: a speck of dirt above the board is ink too, and
    # one such speck on a Grivas page put the whole grid a third of a square
    # out. A frame line runs the width of the picture and nothing printed on
    # the board does.
    rows = np.where(ink.mean(axis=1) > FRAME_INK)[0]
    cols = np.where(ink.mean(axis=0) > FRAME_INK)[0]
    if not len(rows) or not len(cols):
        # An unframed board: there is no line to measure from, so the ink
        # itself has to serve.
        rows = np.where(ink.any(axis=1))[0]
        cols = np.where(ink.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return None
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    left, right = int(cols[0]), int(cols[-1]) + 1
    while bottom - top > SIDE and ink[top, left:right].mean() > 0.5:
        top += 1
    while bottom - top > SIDE and ink[bottom - 1, left:right].mean() > 0.5:
        bottom -= 1
    while right - left > SIDE and ink[top:bottom, left].mean() > 0.5:
        left += 1
    while right - left > SIDE and ink[top:bottom, right - 1].mean() > 0.5:
        right -= 1
    if bottom - top < 8 * SIDE or right - left < 8 * SIDE:
        return None
    return _square_up((top, bottom, left, right))


def _square_up(region: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    """`region` if it is a board, `None` if it holds more than one.

    A board is square. A region that is not holds something else as well — a
    caption, a mark, a rule the peeling could not tell from the frame — and
    dividing it by eight would put every rank a fraction of a square out,
    which costs the whole position rather than the part that is wrong. The
    picture is dropped instead. See `SQUARE_TOLERANCE` for the search that was
    tried in its place and does not work.
    """
    top, bottom, left, right = region
    height, width = bottom - top, right - left
    if abs(height - width) > SQUARE_TOLERANCE * min(height, width) / SIDE:
        return None
    return region


def _signatures(image: Any, region: tuple[int, int, int, int]) -> list[Any] | None:
    """One signature per square, or `None` if this picture is not a board.

    What says it is a board is its own shading: the two colours of square
    differ, in the mean of what is left once the bodies standing on them are
    taken off. A picture with no such alternation is a photograph, a logo or a
    figure, and no position is read out of it.
    """
    import numpy as np
    from scipy import ndimage

    top, bottom, left, right = region
    height, width = bottom - top, right - left
    radius = max(1, int(round(min(height, width) / SIDE * OPENING_RATIO)))
    element = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=bool)

    squares: list[Any] = []
    grounds: tuple[list[float], list[float]] = ([], [])
    for rank in range(SIDE):
        for file in range(SIDE):
            y0 = int(round(top + height * (rank + INSET) / SIDE))
            y1 = int(round(top + height * (rank + 1 - INSET) / SIDE))
            x0 = int(round(left + width * (file + INSET) / SIDE))
            x1 = int(round(left + width * (file + 1 - INSET) / SIDE))
            cell = image[y0:y1, x0:x1]
            if cell.size == 0:
                return None
            body = ndimage.binary_opening(
                ndimage.binary_fill_holes(cell < 0.5), structure=element
            )
            squares.append(_signature(cell, body))
            ground = cell[~body]
            grounds[(rank + file) % 2].append(float(ground.mean()) if ground.size else 1.0)

    light = sum(grounds[0]) / len(grounds[0])
    dark = sum(grounds[1]) / len(grounds[1])
    if abs(light - dark) < MIN_SHADE_CONTRAST:
        return None
    return squares


def _signature(cell: Any, body: Any) -> Any:
    """One square as a vector: the shape of its body, and the shade inside it.

    An empty square answers with zeroes — the same zeroes whatever colour the
    square is, which is what lets one diagram teach both.
    """
    import numpy as np

    size = SIGNATURE_SIDE
    filled = np.where(body)
    if len(filled[0]) < 0.02 * body.size:
        return np.zeros(2 * size * size + 3, dtype=np.float32)
    y0, y1 = int(filled[0].min()), int(filled[0].max()) + 1
    x0, x1 = int(filled[1].min()), int(filled[1].max()) + 1
    shape = body[y0:y1, x0:x1]
    shade = np.where(shape, cell[y0:y1, x0:x1], 1.0)
    measures = [
        (y1 - y0) / cell.shape[0],
        (x1 - x0) / cell.shape[1],
        float(shape.mean()),
    ]
    return np.concatenate(
        [_pool(shape.astype(np.float32), size).ravel(), _pool(shade, size).ravel(), measures]
    ).astype(np.float32)


def _pool(array: Any, size: int) -> Any:
    """`array` averaged down to `size` by `size`, by area.

    By area, and not by whole pixels. A board drawn small — Tactics prints its
    at 190 pixels, so a square is 23.75 of them and a piece some 19 — divides
    into bins of one and two pixels, and then a piece sitting half a pixel
    over lands its ink in different bins and clusters on its own. Weighting
    each pixel by how much of the bin it covers makes the reduction continuous
    in the position of the body, which is the whole reason it is being taken.
    """
    import numpy as np

    return _weights(array.shape[0], size) @ array @ _weights(array.shape[1], size).T


def _weights(length: int, size: int) -> Any:
    """The `size` by `length` matrix that averages `length` values into `size`.

    Row `i` holds, for each input position, the share of output bin `i` that
    the position covers; the row sums to one.
    """
    import numpy as np

    edges = np.linspace(0.0, float(length), size + 1)
    lower = np.maximum(edges[:-1, None], np.arange(length)[None, :])
    upper = np.minimum(edges[1:, None], np.arange(1, length + 1)[None, :])
    overlap = np.clip(upper - lower, 0.0, None)
    return (overlap / overlap.sum(axis=1, keepdims=True)).astype(np.float32)


def _cluster(squares: Sequence[Any]) -> list[int]:
    """A label per square: the same label means the same thing on the board.

    Greedy, single pass, nearest centroid — the clusters are far apart and
    there is nothing here for a cleverer algorithm to earn. What it does need
    is a second thought about the strays: a square whose alignment was a pixel
    out lands in a cluster of its own, and one such square is enough for
    `diagrams.decode` to refuse the whole board. So the clusters are held to
    the thirteen things a board can carry (`MAX_KINDS`) and everything else is
    dissolved, its squares read as the nearest believed one — unless they are
    too far from any, in which case each keeps a character nothing will ever
    teach and its board is dropped.
    """
    import numpy as np

    centroids: list[Any] = []
    counts: list[int] = []
    labels: list[int] = []
    for square in squares:
        nearest, distance = _nearest(centroids, square)
        if nearest is None or distance > MERGE_DISTANCE:
            centroids.append(np.array(square, dtype=np.float32))
            counts.append(1)
            labels.append(len(centroids) - 1)
            continue
        counts[nearest] += 1
        centroids[nearest] += (square - centroids[nearest]) / counts[nearest]
        labels.append(nearest)

    believed = sorted(
        (index for index, count in enumerate(counts) if count >= MIN_SUPPORT),
        key=lambda index: -counts[index],
    )[:MAX_KINDS]
    believed.sort()
    if not believed:
        return labels
    kept = {index: position for position, index in enumerate(believed)}
    next_label = len(believed)
    resolved: list[int] = []
    for square, label in zip(squares, labels):
        if label in kept:
            resolved.append(kept[label])
            continue
        nearest, distance = _nearest([centroids[index] for index in believed], square)
        if nearest is not None and distance <= STRAY_DISTANCE:
            resolved.append(nearest)
        else:
            resolved.append(next_label)
            next_label += 1
    return resolved


def _nearest(centroids: Sequence[Any], square: Any) -> tuple[int | None, float]:
    """The closest centroid to `square`, by mean absolute difference."""
    import numpy as np

    if not centroids:
        return None, float("inf")
    distances = np.abs(np.asarray(centroids) - square).mean(axis=1)
    nearest = int(distances.argmin())
    return nearest, float(distances[nearest])


def _offset_for(page: Page, bbox: BBox) -> int:
    """Where in the page's text a picture printed at `bbox` was met.

    A diagram token has to stand between the text above it and the text below
    it: the number printed under a board — `8...`, and nothing else — is what
    tells the parser whose move it is, so a board landing after that number
    seeds nothing. The offset is therefore the first character of the text
    beneath the picture, in the column the picture stands in, taken in the
    order the page's own content stream gives — which is the order that keeps
    two columns apart.
    """
    below = bbox.y  # the picture's lower edge, origin bottom-left
    for index, char in enumerate(page.chars):
        box = char.bbox
        if box.w <= 0 or box.h <= 0:
            continue
        if box.y + box.h > below:
            continue
        overlap = min(box.x + box.w, bbox.x + bbox.w) - max(box.x, bbox.x)
        if overlap > 0.5 * box.w:
            return _word_start(page, index)
    return len(page.text)


def _word_start(page: Page, index: int) -> int:
    """`index`, moved back to where the word it stands in begins.

    Which character of the line below sits lowest is a matter of a fraction of
    a point — in Grivas the `1` of a move number measured taller than its `4`,
    and the diagram landed between them, leaving the parser a `4` where the
    book printed `14`. A diagram is never printed inside a word, so the offset
    is snapped to the start of one.
    """
    while index > 0 and not page.text[index - 1].isspace():
        index -= 1
    return index
