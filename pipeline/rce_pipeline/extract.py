"""Step 1 — text and per-character geometry extraction from a PDF.

The output of this step is a *character stream* per page: one flat string plus,
for every character in it, the box it occupies on the page. Everything
downstream (tokenising, move detection) works on the string and asks this
module for the geometry of any slice it cares about.

Working at character granularity rather than word granularity matters here:
a move is often glued to its punctuation ("14.Nf3!," "e4)") and the clickable
zone should cover the move alone.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import warnings
from dataclasses import dataclass, field, asdict
from typing import Any, Iterator

try:  # PyMuPDF 1.24.3+ renamed the module; `fitz` still works but warns.
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz

# Fonts whose glyphs are chess pieces drawn from latin letters. Matched
# case-insensitively as a substring of the font name reported by MuPDF.
FIGURINE_FONT_HINTS = (
    "figurine",
    "chess",
    "diagram",
    "adiag",
    "linares",
    "informator",
)

#: Font name carried by characters that :mod:`rce_pipeline.glyphs` recovered
#: from the page image rather than read from the text layer. It is not a real
#: font; it lives here, beside the other font constants, so that the notation
#: detector can recognise a repaired page without importing the recogniser.
GLYPH_FONT = "rce-glyph"

#: Font name carried by characters read by Tesseract off a page that is a
#: picture. Not the `GlyphLessFont` of a scanner's layer on purpose: that one
#: says the pieces are drawn and need recovering, and these pages print letters.
OCR_FONT = "rce-ocr"

#: A page is a picture of a page when its text layer holds fewer characters
#: than this and one image covers at least a third of it. Fabrice's documents
#: split cleanly: their picture pages carry 0 to 24 characters (a title, a tab
#: label) under an image over half the page; their typed pages 450 and up.
_PICTURE_PAGE_TEXT = 50
_PICTURE_PAGE_COVER = 1 / 3

#: What Tesseract reads a picture page at. French and English cover the
#: library; a German book would need `deu` installed and added.
OCR_LANGUAGES = "fra+eng"
OCR_DPI = 300

#: MuPDF's "serifed" flag is bit 2 and its "bold" flag is bit 4; only the
#: second one is wanted here.
_BOLD_FLAG = 1 << 4


def _is_bold(span: dict) -> bool:
    """Whether a span is set in a bold face.

    Two readings, because neither alone covers the corpus: MuPDF's own flag,
    and the face's name. The flag is derived from the font descriptor and a
    subsetted face can arrive without it, while a name ending in `-Bold` is
    the publisher's own word for the same thing.
    """
    return bool(span.get("flags", 0) & _BOLD_FLAG) or "bold" in span.get("font", "").lower()


@dataclass(frozen=True)
class BBox:
    """A box in PDF user space, origin at the BOTTOM-LEFT of the page.

    MuPDF reports boxes with the origin at the top-left and y growing
    downwards; :meth:`from_mupdf` performs the flip once, here, so that no
    other module has to think about it.
    """

    x: float
    y: float
    w: float
    h: float

    @classmethod
    def from_mupdf(cls, rect: tuple[float, float, float, float], page_height: float) -> "BBox":
        x0, y0, x1, y1 = rect
        return cls(
            x=round(x0, 2),
            y=round(page_height - y1, 2),  # y1 is the lower edge in MuPDF space
            w=round(x1 - x0, 2),
            h=round(y1 - y0, 2),
        )

    def union(self, other: "BBox") -> "BBox":
        x0 = min(self.x, other.x)
        y0 = min(self.y, other.y)
        x1 = max(self.x + self.w, other.x + other.w)
        y1 = max(self.y + self.h, other.y + other.h)
        return BBox(round(x0, 2), round(y0, 2), round(x1 - x0, 2), round(y1 - y0, 2))

    def to_json(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class Char:
    """One character of the page stream, with where it was printed.

    `consumed` holds the characters this one replaced, when it did not come
    from the text layer: :mod:`rce_pipeline.glyphs` writes a figurine over the
    characters the scanner read under a piece symbol, and those characters are
    not only noise. A symbol is about twice as wide as a letter, so its box can
    cover the disambiguating letter printed next to it (`♘bd2` arriving as
    `♘d2`), and that letter is knowable here and nowhere later. `parse` uses it
    to tell a move whose disambiguator was destroyed from one that was never
    printed — two failures that look identical by the time the board is built.
    """

    char: str
    bbox: BBox
    font: str
    size: float
    consumed: str = ""
    #: Set in a heavier weight than the body text. A book that typesets its
    #: game score bold and its analysis plain says with the weight what it
    #: says nowhere else, and `parse` reads it as the line it belongs to.
    #: Always False for a scan, whose text layer is the OCR's and carries no
    #: weight at all — there the same fact lives in the pixels.
    bold: bool = False


@dataclass
class Page:
    number: int  # 1-based
    width: float
    height: float
    text: str
    chars: list[Char] = field(default_factory=list)

    def bbox_for(self, start: int, end: int) -> BBox | None:
        """Union of the boxes of ``text[start:end]``.

        Characters injected by the extractor to separate lines and blocks have
        no geometry and are skipped; a slice made only of those returns None.
        """
        boxes = [c.bbox for c in self.chars[start:end] if c.bbox.w > 0 and c.bbox.h > 0]
        if not boxes:
            return None
        result = boxes[0]
        for box in boxes[1:]:
            result = result.union(box)
        return result

    def to_json(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            # `consumed` is omitted where empty, which is every character of a
            # book that needed no glyph recovery: the artefact carries one
            # entry per character of the book and does not need the noise.
            "chars": [
                {
                    "char": c.char,
                    "bbox": c.bbox.to_json(),
                    "font": c.font,
                    "size": c.size,
                    **({"consumed": c.consumed} if c.consumed else {}),
                    **({"bold": True} if c.bold else {}),
                }
                for c in self.chars
            ],
        }


# Characters appended to keep the stream readable. They carry a degenerate box
# so that `bbox_for` ignores them, and they are never part of a move token.
_LINE_BREAK = "\n"
_BLOCK_BREAK = "\n\n"
_NO_GEOMETRY = BBox(0.0, 0.0, 0.0, 0.0)


def _filler(text: str) -> Iterator[Char]:
    for ch in text:
        yield Char(char=ch, bbox=_NO_GEOMETRY, font="", size=0.0)


def extract_pages(
    pdf_path: str,
    *,
    first_page: int = 1,
    last_page: int | None = None,
    sort_blocks: bool = False,
) -> list[Page]:
    """Read `pdf_path` and return one :class:`Page` per page in range.

    `sort_blocks` reorders blocks top-to-bottom then left-to-right. MuPDF's
    natural order follows the content stream, which is usually correct and
    handles two-column layouts that a naive geometric sort would interleave —
    so this stays off by default. Turn it on for documents whose text comes
    out visibly scrambled.
    """
    doc = fitz.open(pdf_path)
    try:
        last = doc.page_count if last_page is None else min(last_page, doc.page_count)
        indices = range(first_page - 1, last)
        furniture = _furniture(doc[index] for index in indices)
        pages: list[Page] = []
        for index in indices:
            pages.append(
                _extract_page(doc[index], index + 1, sort_blocks=sort_blocks, furniture=furniture)
            )
        return pages
    finally:
        doc.close()


def page_count(pdf_path: str) -> int:
    """Total pages in the document, regardless of the range being processed."""
    doc = fitz.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


#: How far into the page, from the top or the bottom, a running head or a
#: folio stands — as a share of its height. Sakaev's head ends at 5%, its
#: folio starts at 92%, and its text runs from 8% to 90%.
_MARGIN_BAND = 0.07

#: On how many pages a line must stand, where it stands, to be the page's
#: furniture and not the book's.
_FURNITURE_PAGES = 2


def _furniture_key(block: tuple | dict, height: float) -> tuple[str, int] | None:
    """What a running head or a folio is recognised by: its words, and where.

    Digits are left out, so a folio is every page's and so is a head carrying
    the page number. Only one line, and only in the margin: a line of the book
    never stands there.
    """
    x0, y0, x1, y1 = block["bbox"] if isinstance(block, dict) else block[:4]
    if height * _MARGIN_BAND < y0 and y1 < height * (1 - _MARGIN_BAND):
        return None
    text = block[4] if not isinstance(block, dict) else "\n".join(
        "".join(g["c"] for span in line.get("spans", []) for g in span.get("chars", []))
        for line in block.get("lines", [])
    )
    if text.strip().count("\n") > 0:
        return None
    return " ".join("".join(c for c in text if not c.isdigit()).split()), round(y0)


def _furniture(pages: Iterator["fitz.Page"]) -> set[tuple[str, int]]:
    """The running heads and folios of these pages.

    Sakaev prints its title and the page number at the head of every page, and
    the layer puts them first: "22.♖f3 | 72 The Complete Manual of Positional
    Chess | ♕xc5+" ended the line of play on page 72, and on nine pages more.
    """
    counts: dict[tuple[str, int], int] = {}
    for page in pages:
        seen = {
            key for block in page.get_text("blocks") if block[6] == 0
            if (key := _furniture_key(block, page.rect.height)) is not None
        }
        for key in seen:
            counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count >= _FURNITURE_PAGES}


def _extract_page(
    page: "fitz.Page", number: int, *, sort_blocks: bool,
    furniture: set[tuple[str, int]] = frozenset(),
) -> Page:
    # page.rect is the *rotated* (visible) box, and rawdict coordinates are
    # expressed in that same space, so rotated pages need no special handling.
    width, height = page.rect.width, page.rect.height

    if _is_picture_page(page):
        chars = _read_picture(page)
        if chars is not None:
            return Page(
                number=number,
                width=round(width, 2),
                height=round(height, 2),
                text="".join(c.char for c in chars),
                chars=chars,
            )

    raw = page.get_text("rawdict")
    blocks = [
        b for b in raw["blocks"] if b.get("type") == 0  # 0 = text
        and _furniture_key(b, height) not in furniture
    ]
    if sort_blocks:
        blocks.sort(key=lambda b: (round(b["bbox"][1], 1), round(b["bbox"][0], 1)))
    else:
        blocks = _reading_order(blocks, width)

    chars: list[Char] = []
    for block_index, block in enumerate(blocks):
        if block_index > 0:
            chars.extend(_filler(_BLOCK_BREAK))
        for line_index, line in enumerate(block.get("lines", [])):
            if line_index > 0:
                chars.extend(_filler(_LINE_BREAK))
            for span in line.get("spans", []):
                font = span.get("font", "")
                size = float(span.get("size", 0.0))
                bold = _is_bold(span)
                for glyph in span.get("chars", []):
                    chars.append(
                        Char(
                            char=glyph["c"],
                            bbox=BBox.from_mupdf(glyph["bbox"], height),
                            font=font,
                            size=size,
                            bold=bold,
                        )
                    )

    return Page(
        number=number,
        width=round(width, 2),
        height=round(height, 2),
        text="".join(c.char for c in chars),
        chars=chars,
    )


def _finish_the_column(blocks: list[dict], width: float) -> list[dict]:
    """Put back the right column the stream read in the middle of the left one.

    Grivas page 16 hands over the left column down to "relatively minimal",
    then the head of the right column (a new game), then "value. Indeed, 19
    ♗xa8?" on the very next line of the left one: the old game's moves were
    read inside the new one. Only that shape is undone -- the left column
    resuming within half a line of where it stopped, every block involved
    inside its own half of the page (Silman's single column breaks around a
    boxed aside). Sorting every page by column was measured twice and refused
    (Grivas page 27).
    """
    def right(block: dict) -> bool:
        return block["bbox"][0] >= width * 0.45

    def left(block: dict) -> bool:
        # Not a block starting in the right half, however narrow: the `w`
        # beside a right-column board ends inside the left half too.
        return block["bbox"][2] <= width * 0.55 and not right(block)

    def resumes(above: dict, below: dict) -> bool:
        lines = above.get("lines") or [above]
        line = lines[-1]["bbox"][3] - lines[-1]["bbox"][1]
        return -2 <= below["bbox"][1] - above["bbox"][3] <= line / 2

    order = list(blocks)
    for i in range(len(order)):
        if not left(order[i]):
            continue
        j = i + 1
        while j < len(order) and right(order[j]) and not left(order[j]):
            j += 1
        if j == i + 1 or j == len(order) or not left(order[j]) \
                or not resumes(order[i], order[j]):
            continue
        read_early, rest = order[i + 1:j], order[j:]
        k = next((n for n, block in enumerate(rest) if not left(block)), len(rest))
        order[i + 1:] = rest[:k] + read_early + rest[k:]
    return order


def _reading_order(blocks: list[dict], width: float) -> list[dict]:
    """The stream's blocks, with the two repairs of a two-column page applied.

    Cut first: Grivas page 38 welds the left column's foot ("32 ♘f3! (D)")
    to the right column's "10 0-0", after the whole right column was read.
    Only once cut is the foot a left block that `_finish_the_column` can see
    resuming the left column, and put back before the right one.
    """
    return _finish_the_column(_cut_at_the_gutter(blocks, width), width)


def _cut_at_the_gutter(blocks: list[dict], width: float) -> list[dict]:
    """Read the left column out before a right one the stream welded to it.

    Grivas page 27 hands over one block holding the left column down to
    "achieving a good position." *and* the right column's first four lines
    ("19...gxf6 20 ♕xf6 ♖g8"), before the left column's own continuation
    ("13 ♕e1 b6"): the game died on `gxf6` after `12...h6`. Only a block with
    two lines of text on each side of the gutter, one pair of them on the same
    row, is taken for two columns. It is cut there and its right half held
    back, with the right half of every block after it that keeps to the
    columns, until a block crosses the gutter or the page ends. Sorting every
    page by column was refused (see `_finish_the_column`).
    """
    def side(line: dict) -> str | None:
        if line["bbox"][2] <= width * 0.55:
            return "left"
        if line["bbox"][0] >= width * 0.45:
            return "right"
        return None

    def text(line: dict) -> str:
        return "".join(c["c"] for span in line["spans"] for c in span["chars"]).strip()

    def two_columns(lines: list[dict]) -> bool:
        left = [line for line in lines if side(line) == "left"]
        right = [line for line in lines if side(line) == "right"]
        # One line on the left is enough beside two on the right: Grivas
        # page 38's foot of the column is the one line "32 ♘f3! (D)".
        if sum(len(text(line)) > 3 for line in left) < 1 \
                or sum(len(text(line)) > 3 for line in right) < 2:
            return False
        return any(abs(a["bbox"][1] - b["bbox"][1]) < (a["bbox"][3] - a["bbox"][1]) / 2
                   for a in left for b in right)

    order: list[dict] = []
    held: list[dict] = []
    for block in blocks:
        lines = block.get("lines", [])
        if lines and all(side(line) for line in lines) and (held or two_columns(lines)):
            for column, into in (("left", order), ("right", held)):
                part = [line for line in lines if side(line) == column]
                if part:
                    into.append(dict(block, lines=part, bbox=(
                        min(line["bbox"][0] for line in part),
                        min(line["bbox"][1] for line in part),
                        max(line["bbox"][2] for line in part),
                        max(line["bbox"][3] for line in part),
                    )))
            continue
        order += held
        held = []
        order.append(block)
    return order + held


def _is_picture_page(page: "fitz.Page") -> bool:
    """Whether `page` is a picture of a page, with next to no text laid over it."""
    if len("".join(page.get_text().split())) >= _PICTURE_PAGE_TEXT:
        return False
    area = page.rect.width * page.rect.height
    return any(
        (x1 - x0) * (y1 - y0) >= _PICTURE_PAGE_COVER * area
        for x0, y0, x1, y1 in (info["bbox"] for info in page.get_image_info())
    )


def _read_picture(page: "fitz.Page") -> list[Char] | None:
    """The characters Tesseract reads on a picture page, or None without it.

    Tesseract is run on the rendering directly rather than through MuPDF's own
    OCR text page: its layout analysis keeps two columns apart, and MuPDF's
    regrouping of the lines it returns interleaves them line by line.

    A word's box is Tesseract's; each letter gets an equal share of its width.
    """
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        warnings.warn(
            f"page {page.number + 1} is a picture and tesseract is not installed: "
            "it is read as the few characters laid over it.",
            RuntimeWarning,
            stacklevel=3,
        )
        return None
    png = page.get_pixmap(dpi=OCR_DPI, colorspace=fitz.csGRAY).tobytes("png")
    tsv = subprocess.run(
        [tesseract, "stdin", "stdout", "-l", OCR_LANGUAGES, "--psm", "3", "tsv"],
        input=png, capture_output=True, check=True,
    ).stdout.decode("utf-8")

    scale = 72 / OCR_DPI
    height = page.rect.height
    chars: list[Char] = []
    previous: tuple[str, str, str] | None = None
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        word = (row.get("text") or "").strip()
        if row["level"] != "5" or not word:
            continue
        line = (row["block_num"], row["par_num"], row["line_num"])
        if previous is not None:
            joint = (
                _BLOCK_BREAK if line[0] != previous[0]
                else _LINE_BREAK if line != previous
                else " "
            )
            chars.extend(_filler(joint))
        previous = line
        left, top = int(row["left"]) * scale, int(row["top"]) * scale
        w, h = int(row["width"]) * scale, int(row["height"]) * scale
        step = w / len(word)
        for i, ch in enumerate(word):
            box = (left + i * step, top, left + (i + 1) * step, top + h)
            chars.append(
                Char(char=ch, bbox=BBox.from_mupdf(box, height), font=OCR_FONT, size=round(h, 1))
            )
    return chars


def font_inventory(pages: list[Page]) -> dict[str, int]:
    """Character count per font name, used by the notation detector."""
    counts: dict[str, int] = {}
    for page in pages:
        for char in page.chars:
            if char.font and not char.char.isspace():
                counts[char.font] = counts.get(char.font, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
