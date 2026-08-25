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

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Container, Iterator, Sequence

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
#: on the boundary, and a frame the peeling missed sits just outside it — so
#: something has to come off, and what the books say is: barely a pixel.
#:
#: This was 0.10, a tenth of the square at each edge, and that tenth is where
#: the tallest pieces are. A knight stands 0.90 to 0.95 of a square high and a
#: white one is drawn as an outline, so clipping its crown leaves the outline
#: **open**: `binary_fill_holes` then fills nothing at all and the piece has no
#: body — SuperAttaquant's white knight had no cluster of its own, and nine of
#: its eleven boards could not be read. The two costs face opposite ways and
#: the band between them is narrow: at 0.02 SuperAttaquant decodes one board of
#: eleven, at 0.005 and 0.01 it decodes ten and Grivas reads all forty-five,
#: and at 0.00 the grid lines come in and Grivas loses 29 clean moves and
#: eleven of its boards. Measured 2026-08-25 over the whole corpus.
INSET = 0.01

#: Where a square's own paper is read off: high enough to be the paper and not
#: the ink standing on it, low enough not to be the scanner's noise.
_PAPER_PERCENTILE = 90.0

#: How much darker than its own paper a pixel has to be to be ink. Measured on
#: SuperAttaquant, whose paper runs at 0.85 and whose white pieces are drawn as
#: an outline that reaches only 0.60 at its faintest — above the 0.5 a white
#: page would put it under, which is why that book's queen came out darker than
#: its pawns and clustered with the black one. Sweeping it: 0.70 decodes seven
#: of its eleven boards, 0.85 decodes ten, 0.90 five. The hatch of a dark square
#: comes in with it, and the opening above is what takes that back out.
_INK_SHARE = 0.85

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
#:
#: Raised from 0.12 once `SCAN_DPI` made the clusters right: they are tight now
#: (the widest member of any of SuperAttaquant's thirteen sits at 0.085, where
#: the loosest used to sit at 0.092 with the piece in the wrong cluster), so a
#: stray absorbed goes into a cluster that means something. It buys that book a
#: board and a placed game. **0.20 is measured and worse** — three more boards
#: read and three clean moves lost, which is a stray landing in the wrong one of
#: thirteen right clusters.
STRAY_DISTANCE = 0.16

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

#: What a scanned page is rendered at to be searched for a board.
#:
#: This was 200, and 200 was **below what the books store**: SuperAttaquant
#: keeps its pages at 360 dpi and Boussole at 600, so rendering at 200
#: downsampled them — and what downsampling does to a printed halftone is
#: alias it. The screen SuperAttaquant prints its dark squares in is 2 pixels
#: of stroke and 4 of gap at 200, indistinguishable in width from the 3-pixel
#: outline of a white piece, and its phase shifts with wherever the square
#: happens to fall. That is what had the same piece signing as two things.
#: At 300 the screen comes out 3 and 6 against an outline of 3 to 4, and the
#: book's thirteen clusters land on the thirteen things a board carries: page
#: 198's board, typed out by eye, comes back a perfect bijection where at 200
#: its bishop was two clusters and its queens one. Costs a scan about twice
#: the pixels and the corpus about ninety seconds.
SCAN_DPI = 300

#: How dark a pixel of a scan has to be to be ink. Higher than the 0.5 a drawn
#: picture is read at: a scanned rule comes out grey, and SuperAttaquant's
#: frames are only found whole at 0.7.
SCAN_INK = 0.7

#: How far a scanned rule may drift as it crosses the page, as a share of the
#: page's shorter side. A page a degree out of true breaks every rule into
#: fragments; the ink is smeared this far along the rule's own axis before the
#: runs are measured. Measured on SuperAttaquant, 1312 pixels across at
#: `SCAN_DPI`: the top rule of a 413-pixel board runs 213 pixels unbroken, 392
#: at five pixels of smear, and its whole 413 at nine.
SKEW_TOLERANCE = 0.004

#: Most of a scanned page's shorter side a board may take up.
MAX_SCAN_SHARE = 0.7

#: How far from square a frame found on a scan may be. Looser than
#: `SQUARE_TOLERANCE`, which is applied to a board already located: here the
#: two rules are themselves a few pixels thick and drifting.
SCAN_SQUARE_TOLERANCE = 0.03

#: How much of a frame's height the rule down its side has to be found over.
RULE_OVERLAP = 0.7

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


@dataclass(frozen=True)
class Reading:
    """What a pass over a book's pictures found."""

    #: The boards, as blocks of invented characters, in reading order.
    diagrams: list[Diagram]
    #: The characters paired by silhouette: the same piece in its two colours.
    #: A drawing is the same drawing whichever colour it is filled with, so
    #: the shape half of two twins' signatures agrees to within a thousandth
    #: where the next nearest character is fifty times further off. Measured
    #: on Grivas against the table its own games taught: every pair right.
    twins: list[tuple[str, str]]
    #: The character an empty square came out as — the commonest of all, since
    #: a position is at least half empty.
    empty: str | None
    #: For each character no cluster explains, the believed characters it
    #: stands nearest, closest first. A stray is one square of one board and
    #: `diagrams.name_the_strays` reads it by taking the nearest of these that
    #: leaves a position anybody could have reached.
    neighbours: dict[str, list[str]] = field(default_factory=dict)


def find(
    pdf_path: str, pages: Sequence[Page], *, skip_pages: Container[int] = frozenset()
) -> list[Diagram]:
    """The diagrams of :func:`read`, for a caller that needs nothing else."""
    return read(pdf_path, pages, skip_pages=skip_pages).diagrams


def read(
    pdf_path: str, pages: Sequence[Page], *, skip_pages: Container[int] = frozenset()
) -> Reading:
    """Every diagram printed as a picture on `pages`, in reading order.

    The clustering is done over the whole book at once, and has to be: one
    board on its own says only that two of its squares differ, while thirty
    boards say that this shape is a rook, wherever it stands. A book drawing
    no boards costs one pass over its images and nothing else.

    `skip_pages` are the pages `diagrams.find` has already read. A diagram
    font **draws a framed board** when the page is rendered, so the search of
    the last resort finds it a second time and the parser meets one position
    twice — 45 diagrams on Markos where the book prints 25. A page is read one
    way or the other, never both.
    """
    boards = list(_boards(pdf_path, pages, skip_pages))
    if not boards:
        return Reading(diagrams=[], twins=[], empty=None)

    squares = [square for _, sqs in boards for square in sqs]
    labels = _cluster(squares)
    neighbours = _neighbours(squares, labels)
    found: list[Diagram] = []
    cursor = 0
    for page, bbox, offset in (meta for meta, _ in boards):
        chars = [chr(_FIRST_CHAR + label) for label in labels[cursor : cursor + SIDE * SIDE]]
        cursor += SIDE * SIDE
        rows = tuple("".join(chars[i * SIDE : (i + 1) * SIDE]) for i in range(SIDE))
        found.append(Board(page=page, rows=rows, bbox=bbox, offset=offset).as_diagram())
    found.sort(key=lambda d: (d.page, d.start))
    empty, twins = _twins(squares, labels)
    return Reading(diagrams=found, twins=twins, empty=empty, neighbours=neighbours)


def _neighbours(squares: Sequence[Any], labels: Sequence[int]) -> dict[str, list[str]]:
    """For each stray, the believed characters it stands nearest.

    A stray is a square no cluster explains, and one of them is enough for
    `diagrams.decode` to refuse a whole board — which on SuperAttaquant is
    seven boards of thirteen, each of them with exactly one such square. The
    distance says which piece it is most like and legality says which it can
    be; neither is enough on its own, and together they are.
    """
    import numpy as np

    counts = Counter(labels)
    believed = sorted(label for label, n in counts.items() if n >= MIN_SUPPORT)
    if not believed:
        return {}
    centroids = {
        label: np.asarray(
            [square for square, at in zip(squares, labels) if at == label]
        ).mean(axis=0)
        for label in believed
    }
    out: dict[str, list[str]] = {}
    for square, label in zip(squares, labels):
        if label in centroids or chr(_FIRST_CHAR + label) in out:
            continue
        ranked = sorted(
            believed,
            key=lambda other: float(np.abs(centroids[other] - square).mean()),
        )
        out[chr(_FIRST_CHAR + label)] = [chr(_FIRST_CHAR + other) for other in ranked]
    return out


def _twins(squares: Sequence[Any], labels: Sequence[int]) -> tuple[str | None, list[tuple[str, str]]]:
    """The empty square's character, and the characters paired by silhouette.

    A piece is the same drawing in both colours — only the fill changes — so
    the shape half of a signature says which two characters are one piece,
    and the shade half is what kept them apart in the first place.

    The pairing is a matching and not a poll of each character's own nearest:
    three characters can point in a chain, a to b and b to c, and asking for
    agreement then leaves all three unpaired. The closest pair of all is taken
    first, then the closest pair of what is left, until nothing is left —
    which on a book with twelve characters gives six pairs and no chain. An
    odd character out is left unpaired, and the boards it stands on are then
    read by nobody, which is the bargain `decode` already makes.
    """
    import numpy as np

    centres: dict[int, Any] = {}
    counts: Counter[int] = Counter(labels)
    for label, square in zip(labels, squares):
        centres[label] = centres.get(label, 0) + np.asarray(square, dtype=np.float64)
    for label in centres:
        centres[label] = centres[label] / counts[label]
    if not counts:
        return None, []

    empty = counts.most_common(1)[0][0]
    shape = {
        label: centre[: SIGNATURE_SIDE**2]
        for label, centre in centres.items()
        if label != empty and counts[label] >= MIN_SUPPORT
    }
    apart = sorted(
        (float(np.abs(shape[one] - shape[other]).mean()), one, other)
        for index, one in enumerate(sorted(shape))
        for other in sorted(shape)[index + 1 :]
    )
    taken: set[int] = set()
    twins: list[tuple[str, str]] = []
    for _distance, one, other in apart:
        if one in taken or other in taken:
            continue
        taken |= {one, other}
        twins.append((chr(_FIRST_CHAR + one), chr(_FIRST_CHAR + other)))
    return chr(_FIRST_CHAR + empty), twins


def _boards(
    pdf_path: str, pages: Sequence[Page], skip_pages: Container[int]
) -> Iterator[tuple[tuple[int, BBox, int], list[Any]]]:
    """Each board picture on `pages`, with the signatures of its squares.

    Two ways in, tried in that order. A book that stores each board as its own
    image is read from the stored pixels, which are the best there are. A book
    that is a **scan** stores one image per page — the page — and the board has
    to be found inside it; that costs a rendering pass, so it is only done on a
    page whose own images gave nothing.
    """
    by_number = {page.number: page for page in pages}
    doc = fitz.open(pdf_path)
    try:
        for number, page in sorted(by_number.items()):
            if number in skip_pages:
                continue
            source = doc[number - 1]
            found = 0
            for rect, image in _candidate_images(doc, source):
                region = _board_region(image)
                if region is None:
                    continue
                squares = _signatures(image, region)
                if squares is None:
                    continue
                found += 1
                bbox = BBox.from_mupdf(tuple(rect), page.height)
                yield (number, bbox, _offset_for(page, bbox)), squares
            if found:
                continue
            for rect, image, region in _framed_boards(source):
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


def _framed_boards(page: Any) -> Iterator[tuple[Any, Any, tuple[int, int, int, int]]]:
    """The boards drawn on a scan of `page`, found by the frame around them.

    A scanned book stores the page and nothing else, so there is no picture to
    ask about: the board has to be found. What finds it is its frame — four
    rules, two across and two down, meeting in a square nothing else on a page
    of prose makes. The shading test in `_signatures` then has the last word,
    so a table or a boxed sidebar costs a crop and is dropped.

    **A scanned line is not straight.** Measured on SuperAttaquant, whose pages
    sit about a degree out of true: the longest unbroken run along the top rule
    of a board is 213 pixels of the 413 the board is wide, because the rule
    drifts a pixel or two down as it crosses. Smearing the ink a few pixels
    down its own axis before the runs are measured recovers the whole rule —
    213 becomes 392 at five pixels, 413 at nine. The same tilt leaves the grid
    inside a degree out, which is a seventh of a square at the far corner and
    what `INSET` is there to absorb.
    """
    import numpy as np

    pixmap = page.get_pixmap(dpi=SCAN_DPI, colorspace=fitz.csGRAY)
    image = (
        np.frombuffer(pixmap.samples, dtype=np.uint8)
        .reshape(pixmap.height, pixmap.width)
        .astype(np.float32)
        / 255.0
    )
    scale = 72.0 / SCAN_DPI
    smallest = int(MIN_WIDTH_PT / scale)
    largest = int(min(pixmap.width, pixmap.height) * MAX_SCAN_SHARE)
    if largest < smallest:
        return
    ink = image < SCAN_INK
    # How far a rule drifts depends on how far it runs, so the smear is taken
    # from the page and not from the smallest board looked for.
    smear = max(1, int(round(min(pixmap.width, pixmap.height) * SKEW_TOLERANCE)))
    across = _rules(ink, smear, smallest)
    down = _rules(ink.T, smear, smallest)

    for top, bottom, left, right in _squares_between(across, down, smallest, largest):
        crop = image[top:bottom, left:right]
        if crop.shape[0] < 8 * SIDE or crop.shape[1] < 8 * SIDE:
            continue
        rect = fitz.Rect(left * scale, top * scale, right * scale, bottom * scale)
        yield rect, crop, (0, crop.shape[0], 0, crop.shape[1])


def _rules(ink: Any, smear: int, smallest: int) -> list[tuple[int, int, int, int]]:
    """The long straight rules of `ink`, as `(first, last, from, to)`.

    Rows here, and columns by handing in the transpose. `first` and `last` are
    the rows the rule is thick over; `from` and `to` are how far along it runs.
    """
    import numpy as np
    from scipy import ndimage

    smeared = ndimage.grey_dilation(ink.astype(np.uint8), size=(smear, 1)).astype(bool)
    rules: list[tuple[int, int, int, int]] = []
    run: list[tuple[int, int, int]] = []
    for index in range(smeared.shape[0] + 1):
        span = _longest_run(smeared[index]) if index < smeared.shape[0] else None
        if span is not None and span[1] - span[0] >= smallest:
            run.append((index, span[0], span[1]))
            continue
        if run:
            # The rule's own reach is the longest stretch any one of its rows
            # holds, not what all of them agree on: a rule drifting across a
            # tilted page has each row starting a pixel later than the last,
            # and what they agree on is the part in the middle.
            widest = max(run, key=lambda r: r[2] - r[1])
            rules.append((run[0][0], run[-1][0], widest[1], widest[2]))
            run = []
    return rules


def _longest_run(row: Any) -> tuple[int, int] | None:
    """Where the longest unbroken stretch of ink on this line begins and ends."""
    import numpy as np

    edges = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0]))))
    if not len(edges):
        return None
    starts, ends = edges[0::2], edges[1::2]
    longest = int(np.argmax(ends - starts))
    return int(starts[longest]), int(ends[longest])


def _squares_between(
    across: list[tuple[int, int, int, int]],
    down: list[tuple[int, int, int, int]],
    smallest: int,
    largest: int,
) -> Iterator[tuple[int, int, int, int]]:
    """The square boxes two rules across and two rules down enclose.

    What is yielded is the **inside** of the box: a frame left in the crop
    becomes a body of its own in the corner squares, and the corner squares are
    where a rook usually stands.
    """
    for i, upper in enumerate(across):
        for lower in across[i + 1 :]:
            if not smallest <= lower[0] - upper[1] <= largest:
                continue
            begins, ends = max(upper[2], lower[2]), min(upper[3], lower[3])
            if ends - begins < smallest:
                continue
            left = _rule_at(down, begins, upper[0], lower[1], smallest)
            right = _rule_at(down, ends, upper[0], lower[1], smallest)
            if left is None or right is None:
                continue
            # Squareness is asked of the **inside** of the frame, and only
            # once all four rules are known. Comparing the gap between two
            # rules against the length they run over is comparing an inside
            # with an outside, and the difference is two rules thick — which
            # on a rendered scan is enough to fail a board that is square.
            top, bottom, x0, x1 = upper[1] + 1, lower[0], left[1] + 1, right[0]
            height, width = bottom - top, x1 - x0
            if min(height, width) < smallest:
                continue
            if abs(height - width) > SCAN_SQUARE_TOLERANCE * min(height, width):
                continue
            yield top, bottom, x0, x1


def _rule_at(
    rules: list[tuple[int, int, int, int]], where: int, first: int, last: int, smallest: int
) -> tuple[int, int, int, int] | None:
    """The rule covering `where` and running most of `first`..`last`.

    Covering, rather than centred on: a rule is several pixels thick before
    the smear widens it further, and `where` is the end of another rule's
    reach — the outer corner of the frame, not the middle of its side.

    Most of the length, and not all of it: the side of a frame is measured
    from the row that holds its longest stretch of ink, and on a tilted page
    that row is not the one reaching furthest at both ends. Asking for the
    whole height found the frames of SuperAttaquant and paired none of them.
    """
    tolerance = max(4.0, smallest * SCAN_SQUARE_TOLERANCE)
    wanted = (last - first) * RULE_OVERLAP
    for rule in rules:
        if not rule[0] - tolerance <= where <= rule[1] + tolerance:
            continue
        if min(rule[3], last) - max(rule[2], first) >= wanted:
            return rule
    return None


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
                ndimage.binary_fill_holes(cell < _ink_below(cell)), structure=element
            )
            squares.append(_signature(cell, body))
            ground = cell[~body]
            grounds[(rank + file) % 2].append(float(ground.mean()) if ground.size else 1.0)

    light = sum(grounds[0]) / len(grounds[0])
    dark = sum(grounds[1]) / len(grounds[1])
    if abs(light - dark) < MIN_SHADE_CONTRAST:
        return None
    return squares


def _ink_below(cell: Any) -> float:
    """The grey this square's ink is darker than, from the square's own paper.

    A fixed threshold reads a book that was typeset, whose paper is white by
    construction. A scan's is not: SuperAttaquant's runs at 0.85 and drifts
    across the page with the lamp, and the outline of a white piece there sits
    between 0.46 and 0.60 — above a threshold of 0.5, so the outline never
    closes, `binary_fill_holes` fills nothing, and the piece has no body at
    all. Its queen came out darker than a black pawn and clustered with the
    black queen; nine of its eleven boards could not be read.

    So the threshold is taken from the square: the paper is what most of a
    square is, and ink is what stands well below it. The ninetieth percentile
    rather than the maximum, because a scan's brightest pixels are noise.
    """
    import numpy as np

    return float(np.percentile(cell, _PAPER_PERCENTILE)) * _INK_SHARE


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
