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
    """One character of the page stream, with where it was printed."""

    char: str
    bbox: BBox
    font: str
    size: float


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
            "chars": [
                {"char": c.char, "bbox": c.bbox.to_json(), "font": c.font, "size": c.size}
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
        pages: list[Page] = []
        for index in range(first_page - 1, last):
            pages.append(_extract_page(doc[index], index + 1, sort_blocks=sort_blocks))
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


def _extract_page(page: "fitz.Page", number: int, *, sort_blocks: bool) -> Page:
    # page.rect is the *rotated* (visible) box, and rawdict coordinates are
    # expressed in that same space, so rotated pages need no special handling.
    width, height = page.rect.width, page.rect.height

    raw = page.get_text("rawdict")
    blocks = [b for b in raw["blocks"] if b.get("type") == 0]  # 0 = text
    if sort_blocks:
        blocks.sort(key=lambda b: (round(b["bbox"][1], 1), round(b["bbox"][0], 1)))

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
                for glyph in span.get("chars", []):
                    chars.append(
                        Char(
                            char=glyph["c"],
                            bbox=BBox.from_mupdf(glyph["bbox"], height),
                            font=font,
                            size=size,
                        )
                    )

    return Page(
        number=number,
        width=round(width, 2),
        height=round(height, 2),
        text="".join(c.char for c in chars),
        chars=chars,
    )


def font_inventory(pages: list[Page]) -> dict[str, int]:
    """Character count per font name, used by the notation detector."""
    counts: dict[str, int] = {}
    for page in pages:
        for char in page.chars:
            if char.font and not char.char.isspace():
                counts[char.font] = counts.get(char.font, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
