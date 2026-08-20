"""Step 3a — turn page character streams into a stream of typed tokens.

Every token keeps the page and box it came from, because the box is what the
Flutter app turns into a clickable zone. Normalisation is deliberately
character-for-character (figurines to letters, dashes and the multiplication
sign to ASCII) so that an offset into the normalised text still indexes the
same character in :class:`~rce_pipeline.extract.Page.chars`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator

from .extract import BBox, Page
from .notation import FIGURINE_TO_LETTER, SAN_PIECE_LETTERS

#: One-to-one replacements applied before tokenising. Every key and value is a
#: single character: the mapping must not shift offsets.
_CHARACTER_FIXES = {
    **FIGURINE_TO_LETTER,
    "–": "-",  # en dash
    "—": "-",  # em dash
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen
    "−": "-",  # minus sign
    "×": "x",  # multiplication sign, a common OCR reading of "x"
    # The Grivas book prints the `...` that announces a black move as three
    # bullets in a 2.8pt font. Left alone, `15 .••` tokenises as `15 .` — a
    # white move — and every ply of the line after it lands on the wrong side.
    # No other book in the corpus contains a single bullet, so this costs
    # them nothing.
    "•": ".",
    " ": " ",  # non-breaking space
    "’": "'",
}

_TOKEN_TEMPLATE = r"""
      (?P<var_open>\()
    | (?P<var_close>\))
    | (?P<result>1-0|0-1|1/2-1/2|1/2|\*)
    | (?P<move_number>
          # A space inside the number: subset fonts break `18` into `1 8`, and
          # the leading digit then carries no dot, so `1 8 ...` was read as
          # black's eighth instead of black's eighteenth. Only a plain space,
          # never a newline, so a number ending one line cannot swallow the
          # digit opening the next.
          \d(?:[ ]?\d){{0,2}}
          (?:
              # The usual form, and the `12...` that announces a black move.
              \s*\.(?:\s*\.\s*\.)?
              # Batsford, Gambit and Informator print `12 Nb1` with no dot at
              # all. Accepting a bare number would make a move number of every
              # figure in the prose, so it only counts when a move follows it
              # directly — which is exactly where a number can do no harm.
            | (?=\s+(?:O-O|0-0|[{pieces}][a-h1-8x]|[a-h][1-8x]))
          )
      )
    | (?P<move>
          # A move must not begin inside the wreckage of a piece symbol. This
          # book's fonts break one into `ll:\c3`, `i.g7`, `'ii'e8`; refusing
          # only alphanumerics let those through as the pawn moves `c3`, `g7`
          # and `e8` — legal, confidently wrong, scored `ok`, and putting a
          # false position under every move after them. A dot still opens a
          # move in `1.e4` and `13...Nb4`, so only a dot carrying a letter is
          # refused, never one carrying a digit or another dot.
          (?<![A-Za-z0-9:\\'])
          (?<![A-Za-z]\.)
          (?:
              (?:O-O-O|O-O|0-0-0|0-0)
            | [{pieces}]?[a-h]?[1-8]?x?[a-h][1-8](?:\s*=\s*[{pieces}])?
          )
          [+#]?
          (?![A-Za-z0-9])
      )
    | (?P<annotation>[!?]{{1,2}}|[±∓⩲⩱∞⟳→↑↓⇆=]|\+[-=]|-\+)
    """


def _build_token_re(piece_letters: str) -> re.Pattern[str]:
    """Compile the token pattern for one alphabet of piece letters.

    Only the book's own letters go in. Accepting every language's at once
    would look tolerant and be worse: `T` is a Rook in French and nothing in
    English, `B` is a Bishop in English and nothing in French, so a permissive
    class turns a misread letter into a different, legal move.
    """
    return re.compile(
        _TOKEN_TEMPLATE.format(pieces=re.escape(piece_letters)), re.VERBOSE
    )

#: Prose shorter than this, or made only of punctuation, is dropped rather than
#: attached to a move as a comment.
_MIN_COMMENT_LENGTH = 3


@dataclass
class Token:
    kind: str  # move | move_number | var_open | var_close | result | annotation | text
    text: str  # normalised
    raw: str  # exactly as printed, before normalisation
    page: int  # 1-based
    start: int  # offset into the page's character stream
    end: int
    bbox: BBox | None
    #: Characters destroyed inside this token's span by the glyph recovery
    #: pass, in printed order. Empty for every token of a book that did not
    #: need it. Only collected for moves — it exists so that `parse` can tell a
    #: disambiguating letter that was eaten from one that was never printed.
    consumed: str = ""

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "text": self.text,
            "raw": self.raw,
            "page": self.page,
            "bbox": self.bbox.to_json() if self.bbox else None,
        }
        if self.consumed:
            payload["consumed"] = self.consumed
        return payload


def normalise(text: str) -> str:
    """Apply the one-to-one character fixes. Length is preserved."""
    return "".join(_CHARACTER_FIXES.get(ch, ch) for ch in text)


def tokenize_pages(
    pages: list[Page], *, piece_letters: str = SAN_PIECE_LETTERS
) -> list[Token]:
    """Tokenise every page in order, concatenating the results.

    `piece_letters` is the book's own alphabet of piece initials, in the order
    King, Queen, Rook, Bishop, Knight — `RDTFC` for a French book, `KDTLS` for
    a German one. Figurine books keep the default, because :func:`normalise`
    has already turned their symbols into SAN letters.

    Move tokens come out translated to SAN letters; prose is left exactly as
    printed. Applying the translation to the whole page instead would be much
    simpler and would also shred every comment in the book — in French, `R`,
    `D`, `T`, `F` and `C` start a great many ordinary words.

    Pages are tokenised independently, so a move split across a page break is
    lost. That is rare in practice — publishers avoid breaking a move in two —
    and detecting it reliably would require reflowing the whole book.
    """
    token_re = _build_token_re(piece_letters)
    to_san = str.maketrans(piece_letters, SAN_PIECE_LETTERS)

    tokens: list[Token] = []
    for page in pages:
        tokens.extend(_tokenize_page(page, token_re, to_san))
    return tokens


def _tokenize_page(
    page: Page, token_re: re.Pattern[str], to_san: dict[int, int]
) -> Iterator[Token]:
    text = normalise(page.text)
    cursor = 0

    for match in token_re.finditer(text):
        if match.start() > cursor:
            prose = _make_text_token(page, text, cursor, match.start())
            if prose is not None:
                yield prose

        kind = match.lastgroup
        assert kind is not None
        start, end = match.span()
        # Move numbers and promotions may carry internal spaces ("14 ." or
        # "e8 = Q"); squeeze them so downstream code sees canonical text.
        text_out = match.group() if kind == "annotation" else re.sub(r"\s+", "", match.group())
        consumed = ""
        if kind == "move":
            text_out = text_out.translate(to_san)
            consumed = "".join(c.consumed for c in page.chars[start:end])
        yield Token(
            kind=kind,
            text=text_out,
            raw=page.text[start:end],
            page=page.number,
            start=start,
            end=end,
            bbox=page.bbox_for(start, end),
            consumed=consumed,
        )
        cursor = end

    if cursor < len(text):
        prose = _make_text_token(page, text, cursor, len(text))
        if prose is not None:
            yield prose


def _make_text_token(page: Page, text: str, start: int, end: int) -> Token | None:
    collapsed = re.sub(r"\s+", " ", text[start:end]).strip()
    if len(collapsed) < _MIN_COMMENT_LENGTH:
        return None
    if not any(ch.isalnum() for ch in collapsed):
        return None
    return Token(
        kind="text",
        text=collapsed,
        raw=page.text[start:end],
        page=page.number,
        start=start,
        end=end,
        bbox=page.bbox_for(start, end),
    )
