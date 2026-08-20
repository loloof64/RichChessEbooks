"""Step 1b — the printed lines of a scanned page, and the crops to re-read them.

Only scans need this. On a digitally produced book the text layer is the
book, and :mod:`rce_pipeline.extract` is the whole of step 1. On a scan the
text layer is OCR output: its *character boxes* are placed on the printed
glyphs, but for chess notation the characters themselves are wrong (`♘`
arrives as `4)`, `A` or `@`; `g6` as `26`). The boxes are worth keeping and
the characters are not.

So this module throws away nothing and reads nothing: it regroups the boxes
into the lines the book actually printed, and hands back a high-resolution
crop of each one. Recognising what is inside the crop — constrained OCR for
the squares, a glyph classifier for the pieces — is the next step, and the
reason a *line* is the unit here: a whole line of context is what makes
Tesseract read `g6` as `g6` instead of `26`, and word-sized crops do not.

Three things stand between MuPDF's line list and a usable crop:

Columns
    Chess books are set in two columns, and the gutter is narrow — 7 points
    in the book this was written against, half a line height. A merge rule
    based on distance alone would join a line on the left to whatever sits
    beside it on the right whenever their baselines happen to agree.
    :func:`split_columns` finds the boundary by looking for the vertical cut
    that the fewest lines cross, which measures the gutter rather than
    guessing at it.

Fragments
    OCR splits one printed line into several boxes wherever it hesitates
    (`4...` and `g6 5.♕xh7+!! ♕xh7 6.♗f7# (1-0)` are two entries of the same
    line). Anything sharing a baseline inside one column is one line.

Diagrams
    A board renders as debris — rank labels, half-recognised piece glyphs —
    that MuPDF reports as text. It is recognisable by shape rather than by
    content: a handful of narrow boxes strung across a wide row, where a line
    of prose covers nearly all of its own width.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

try:  # PyMuPDF 1.24.3+ renamed the module; `fitz` still works but warns.
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz

from .extract import BBox, Page

#: Resolution to render a crop at. The scans this targets hold about 5 pixels
#: per point (≈360 dpi), so this asks the renderer for what the scan already
#: has; going higher only interpolates, which Tesseract sometimes likes and
#: never learns from.
DEFAULT_DPI = 360

#: Points of white kept around a crop. Tesseract reads a line noticeably worse
#: when the glyphs touch the edge of the image, and the OCR boxes are tight.
DEFAULT_PADDING = 2.0

#: A line shorter than this was not printed as body text. It is bleed-through
#: from the facing page, or speckle the scanner resolved into a character.
MIN_LINE_HEIGHT = 6.0

#: Fraction of its own width a line's boxes must cover to be text rather than
#: diagram debris. Prose covers ~0.95 (the gaps are word spaces); a rank of a
#: chessboard covers ~0.35.
MIN_COVERAGE = 0.6

#: A move number, as it survives scanning: one to three digits and the dot or
#: ellipsis announcing whose move it is. The digits and the dot are the part
#: OCR gets right — the piece symbol beside them is the part it does not — so
#: this is the one reliable marker that a line carries notation.
#:
#: The letter in the lookbehind is what keeps a chess book's prose out: "sur
#: la case e4." ends in a digit and a dot too, and squares are named in prose
#: on nearly every line of the genre.
_MOVE_NUMBER = re.compile(r"(?<![A-Za-z\d])\d{1,3}\s*\.")

#: The same number as printed by Batsford, Gambit and Informator, which set
#: `12 Nb1` with no dot at all. `tokenize` learned this form; this did not, and
#: the two disagreeing cost more than either alone: a book that dots its
#: commentary (`8 ... Nc5`) but not its game score sent every comment through
#: glyph recovery and no line of play, so its symbols were restored exactly
#: where they did not matter. On Grivas that was 111 lines selected out of 572
#: instead of 170.
#:
#: A bare number counts only when a move follows it directly, as in `tokenize`,
#: but the piece letters cannot be used here — the symbols are still broken at
#: this stage, which is the whole point of re-reading the line. The square is
#: the only part that survives, and the wreck of the symbol sits between the
#: two: `24 'it'g2`, `14 lt::Jxg5`, `17 i.xc5?`, `25 i.f3`. Skipping over it is
#: what separates a line of play from prose here — a square counter cannot,
#: because the same wreck welds itself to the square and hides it.
#:
#: The error is deliberately taken on the permissive side: a prose line wrongly
#: selected costs one crop, while a line of play wrongly dropped loses every
#: move on it. Measured over forty pages, this admits 85 further lines of
#: Grivas and not one of the other three books.
#:
#: One form escapes it and no rule keyed on the number can catch it: `ll ll:\f3`,
#: where the number itself printed as letters.
_DOTLESS_MOVE_NUMBER = re.compile(
    r"(?<![A-Za-z\d])\d{1,3}\s+(?:[Oo0]-[Oo0]|\S{0,5}?x?[a-h][1-8](?![A-Za-z\d]))"
)


@dataclass(frozen=True)
class Line:
    """One line as the book printed it, rebuilt from the OCR layer's boxes.

    `text` is what the OCR layer claims the line says, which for the moves is
    wrong by construction — it is kept for locating lines, not for reading
    them. `spans` are the ranges of :attr:`Page.text` it was rebuilt from, in
    reading order, so the geometry of any part of it stays reachable through
    :meth:`Page.bbox_for`.
    """

    page: int
    bbox: BBox
    text: str
    spans: tuple[tuple[int, int], ...]
    column: int
    coverage: float

    @property
    def has_notation(self) -> bool:
        """True when a move number appears on the line, dotted or not."""
        return (
            _MOVE_NUMBER.search(self.text) is not None
            or _DOTLESS_MOVE_NUMBER.search(self.text) is not None
        )

    def to_json(self) -> dict[str, object]:
        return {
            "page": self.page,
            "bbox": self.bbox.to_json(),
            "text": self.text,
            "spans": [list(s) for s in self.spans],
            "column": self.column,
            "coverage": round(self.coverage, 3),
            "has_notation": self.has_notation,
        }


@dataclass(frozen=True)
class LineImage:
    """A rendered crop of one line, and the way back to page coordinates.

    Whatever recognises the crop reports boxes in its pixels; those boxes are
    what the reader turns into tap zones, so they have to come home to PDF
    user space. :meth:`to_pdf` is that trip, and it is the only place the
    top-left/bottom-left flip is done for crops.
    """

    line: Line
    png: bytes
    width: int
    height: int
    #: Pixels per PDF point.
    scale: float
    #: PDF-space box actually rendered, padding included.
    clip: BBox

    def to_pdf(self, x: float, y: float, w: float, h: float) -> BBox:
        """Convert a box in crop pixels (origin top-left) to a page BBox."""
        return BBox(
            x=round(self.clip.x + x / self.scale, 2),
            # The crop's top edge is the high-y edge of the clip in PDF space.
            y=round(self.clip.y + self.clip.h - (y + h) / self.scale, 2),
            w=round(w / self.scale, 2),
            h=round(h / self.scale, 2),
        )


def segment_lines(
    page: Page,
    *,
    min_height: float = MIN_LINE_HEIGHT,
    min_coverage: float = MIN_COVERAGE,
) -> list[Line]:
    """Rebuild the printed lines of `page` from its OCR-layer boxes."""
    fragments = list(_fragments(page))
    fragments = [f for f in fragments if f.bbox.h >= min_height and f.text.strip()]
    if not fragments:
        return []

    boundaries = split_columns([f.bbox for f in fragments], page.width)
    lines: list[Line] = []
    for column, group in _by_column(fragments, boundaries):
        for merged in _merge_rows(group):
            line = _build_line(page.number, merged, column)
            if line.coverage >= min_coverage:
                lines.append(line)

    # Reading order: column by column, top to bottom. PDF y grows upwards, so
    # the topmost line is the one with the largest y.
    lines.sort(key=lambda l: (l.column, -(l.bbox.y + l.bbox.h)))
    return _separate(lines)


def notation_lines(lines: list[Line], *, context: int = 1) -> list[Line]:
    """The lines worth re-reading, in the order `lines` came in.

    A line announcing a move number carries notation. So does the line under
    it, often enough to matter: a sequence broken by the line break puts its
    first move at the start of the next line with nothing to announce it, and
    that move is exactly as unreadable as the ones above. `context` extends
    the selection that far down the same column.
    """
    keep: set[int] = set()
    for index, line in enumerate(lines):
        if not line.has_notation:
            continue
        keep.add(index)
        for offset in range(1, context + 1):
            follower = index + offset
            if follower < len(lines) and lines[follower].column == line.column:
                keep.add(follower)
    return [line for index, line in enumerate(lines) if index in keep]


def split_columns(boxes: list[BBox], page_width: float) -> list[float]:
    """Column boundaries of a page, as x positions, or `[]` for one column.

    The boundary is the vertical cut crossed by the fewest boxes. On a
    two-column page that is the gutter and almost nothing crosses it — a
    running head, at worst. On a single-column page every line of text crosses
    every candidate cut, so the minimum stays high and no split is reported.
    """
    if len(boxes) < 8:
        return []

    best_x: float | None = None
    best_score: tuple[int, float] | None = None
    for x in range(int(0.25 * page_width), int(0.75 * page_width)):
        crossing = sum(1 for b in boxes if b.x < x < b.x + b.w)
        # Ties go to the cut nearest the middle of the page, which is where a
        # gutter is, and where a run of empty margin is not.
        score = (crossing, abs(x - page_width / 2))
        if best_score is None or score < best_score:
            best_score, best_x = score, float(x)

    assert best_x is not None and best_score is not None
    crossing = best_score[0]
    left = sum(1 for b in boxes if b.x + b.w <= best_x)
    right = sum(1 for b in boxes if b.x >= best_x)
    total = len(boxes)

    # Three crossings is a running head, a footer and a caption; a genuine
    # single-column page overshoots that many times over. Both sides have to
    # hold a real share of the page, or this is a wide margin, not a gutter.
    if crossing > max(3, 0.05 * total):
        return []
    if left < 0.2 * total or right < 0.2 * total:
        return []
    return [best_x]


class PageRenderer:
    """Renders line crops from the source PDF.

    Holds the document open: a book has thousands of lines and reopening the
    file for each one dominates the runtime.
    """

    def __init__(self, pdf_path: str, *, dpi: int = DEFAULT_DPI):
        self._doc = fitz.open(pdf_path)
        self.dpi = dpi
        self.scale = dpi / 72.0

    def __enter__(self) -> "PageRenderer":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._doc.close()

    def crop(self, line: Line, *, padding: float = DEFAULT_PADDING) -> LineImage:
        """Render `line` as a grayscale PNG.

        Grayscale rather than bitonal: the crop feeds a recogniser, and
        thresholding a scan of small bold type closes the counters of `e` and
        `a` — better left to whatever reads it, which can see the greys.

        `padding` is horizontal only. The line's own box already reaches above
        and below its type, and :func:`segment_lines` has trimmed it to stop
        where the neighbouring line begins; padding it vertically would put
        that neighbour back in the crop.
        """
        page = self._doc[line.page - 1]
        height = page.rect.height
        box = line.bbox
        left = max(0.0, box.x - padding)
        bottom = max(0.0, box.y)
        right = min(page.rect.width, box.x + box.w + padding)
        top = min(height, box.y + box.h)
        clip = BBox(round(left, 2), round(bottom, 2), round(right - left, 2), round(top - bottom, 2))

        # fitz clips in its own space: y counted downwards from the page top.
        rect = fitz.Rect(clip.x, height - (clip.y + clip.h), clip.x + clip.w, height - clip.y)
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(self.scale, self.scale),
            clip=rect,
            colorspace=fitz.csGRAY,
        )
        return LineImage(
            line=line,
            png=pixmap.tobytes("png"),
            width=pixmap.width,
            height=pixmap.height,
            scale=self.scale,
            clip=clip,
        )


def _separate(lines: list[Line]) -> list[Line]:
    """Trim consecutive boxes of a column until they stop overlapping.

    OCR boxes are taller than the type they cover, so on tightly set text the
    box of one line reaches into the line above by two or three points. Left
    alone, that slice of a neighbouring line lands in the crop and a
    single-line recogniser reads two.

    The overlap goes to the line above, all of it. It is where descenders
    live, and they are not decoration: `g` and `q` reduced to their bowls read
    as `a` and `o`, which on a chess page turns `g6` into a square that was
    never printed. The line below loses only white — its own type starts at
    its baseline, well inside what is left.
    """
    adjusted = list(lines)
    for index in range(len(adjusted) - 1):
        upper, lower = adjusted[index], adjusted[index + 1]
        if upper.column != lower.column:
            continue
        overlap = (lower.bbox.y + lower.bbox.h) - upper.bbox.y
        if overlap <= 0:
            continue
        box = lower.bbox
        adjusted[index + 1] = Line(
            page=lower.page,
            bbox=BBox(box.x, box.y, box.w, round(box.h - overlap, 2)),
            text=lower.text,
            spans=lower.spans,
            column=lower.column,
            coverage=lower.coverage,
        )
    return adjusted


@dataclass
class _Fragment:
    start: int
    end: int
    text: str
    bbox: BBox


def _fragments(page: Page) -> Iterator[_Fragment]:
    """The OCR layer's own lines, as ranges of the page's character stream.

    :mod:`rce_pipeline.extract` separates them with newlines and carries no
    other structure, which is all this needs: the fragment boundaries are
    exactly where the extractor put a break.
    """
    start = 0
    for index, char in enumerate(page.text + "\n"):
        if char != "\n":
            continue
        if index > start:
            bbox = page.bbox_for(start, index)
            if bbox is not None:
                yield _Fragment(start, index, page.text[start:index], bbox)
        start = index + 1


def _by_column(
    fragments: list[_Fragment], boundaries: list[float]
) -> Iterator[tuple[int, list[_Fragment]]]:
    """Group fragments by column, in left-to-right order.

    A fragment straddling a boundary — a running head, a centred caption —
    belongs to no column and is given one of its own, so it stays a line and
    never merges with anything beside it.
    """
    if not boundaries:
        yield 0, fragments
        return

    columns: dict[int, list[_Fragment]] = {}
    straddlers: list[_Fragment] = []
    for fragment in fragments:
        box = fragment.bbox
        if any(box.x < b < box.x + box.w for b in boundaries):
            straddlers.append(fragment)
            continue
        index = sum(1 for b in boundaries if box.x >= b)
        columns.setdefault(index, []).append(fragment)

    for index in sorted(columns):
        yield index, columns[index]
    for fragment in straddlers:
        yield -1, [fragment]


def _merge_rows(fragments: list[_Fragment]) -> Iterator[list[_Fragment]]:
    """Group fragments of one column into printed lines.

    Two fragments are the same line when their boxes overlap vertically by
    most of the shorter one's height. Inside a column that is enough — the
    only thing that could be beside a line and not part of it is another
    column, and columns have already been separated.
    """
    ordered = sorted(fragments, key=lambda f: (-(f.bbox.y + f.bbox.h), f.bbox.x))
    row: list[_Fragment] = []
    for fragment in ordered:
        if row and _same_row(row, fragment):
            row.append(fragment)
            continue
        if row:
            yield sorted(row, key=lambda f: f.bbox.x)
        row = [fragment]
    if row:
        yield sorted(row, key=lambda f: f.bbox.x)


def _same_row(row: list[_Fragment], candidate: _Fragment) -> bool:
    box = candidate.bbox
    for fragment in row:
        other = fragment.bbox
        overlap = min(box.y + box.h, other.y + other.h) - max(box.y, other.y)
        if overlap >= 0.5 * min(box.h, other.h):
            return True
    return False


def _build_line(page_number: int, fragments: list[_Fragment], column: int) -> Line:
    bbox = fragments[0].bbox
    for fragment in fragments[1:]:
        bbox = bbox.union(fragment.bbox)
    inked = _covered_width([(f.bbox.x, f.bbox.x + f.bbox.w) for f in fragments])
    return Line(
        page=page_number,
        bbox=bbox,
        # One space per join: the fragment boundary is a gap the OCR engine
        # hesitated at, and it is a word break far more often than not.
        text=" ".join(f.text.strip() for f in fragments),
        spans=tuple((f.start, f.end) for f in fragments),
        column=column,
        coverage=inked / bbox.w if bbox.w else 0.0,
    )


def _covered_width(intervals: list[tuple[float, float]]) -> float:
    """Total width the intervals cover, counting an overlap once.

    OCR fragments of one line do overlap — the engine reports a word twice
    under two readings — and summing their widths would report a line as
    denser than the page is wide.
    """
    total = 0.0
    high = float("-inf")
    for start, end in sorted(intervals):
        if end <= high:
            continue
        total += end - max(start, high)
        high = end
    return total
