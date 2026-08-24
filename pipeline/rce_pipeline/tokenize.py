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
          #
          # The lookbehind is what keeps the tolerance from reaching into the
          # move before. `Nf6 6 Nc3`, with the knight's symbol unrecovered so
          # that no token covers `f6`, offered the `6` of the square and the
          # `6` of the number as one: move 66, which threw the line a hundred
          # plies forward and lost the game from its fifth move.
          (?<![A-Za-z\d])
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
          (?:
              (?:O-O-O|O-O|0-0-0|0-0)
              # A space between the square's file and its rank: the same
              # subset font that breaks `18` into `1 8` breaks `Rac1` into
              # `Rac 1`, and the move is then never read. Only where the token
              # begins at a word boundary — otherwise the tail of an ordinary
              # word swallows the number that follows it ("the move 6.Bg5"
              # reads as `e 6`), and the citation the number announced is lost
              # with it.
            | (?<![A-Za-z])[{pieces}]?[a-h]?[1-8]?x?[a-h][ ][{ranks}]
            | [{pieces}]?[a-h]?[1-8]?x?[a-h][{ranks}](?:\s*=\s*[{pieces}])?
          )
          [+#]?
          # Never an apostrophe: with `l` read as a rank, the French elision
          # `de l'échiquier` is shaped exactly like `Re1` and every article in
          # the book becomes a move. 27 of them over two scans, and not one
          # real move in the corpus is followed by one.
          (?![A-Za-z0-9'])
      )
    | (?P<annotation>[!?]{{1,2}}|[±∓⩲⩱∞⟳→↑↓⇆=]|\+[-=]|-\+)
    """


#: Letters a scanner leaves where a destination rank belongs. `5` read as `S`
#: is the whole of it in this corpus — 40 of them over twelve pages of
#: Boussole, 32 on Grivas, 13 on SuperAttaquant — and it does not cost one
#: move but a line: the token matches nothing, the move is never read, the
#: side to play is wrong from there, and the line dies a few plies later on a
#: castling that is suddenly illegal. That is why `O-O` keeps appearing as the
#: dying move in an audit and is never itself the fault.
#:
#: The move is emitted **as printed** — `dS`, not `d5`. `parse` already treats
#: `5`/`S` as a near-free substitution, so the position is what decides what
#: was on the page, and a token no legal move comes within half an edit of
#: stays `broken`. Nothing here guesses.
#:
#: Only `S`. Adding `l` and `I` for rank 1 was measured and costs more than it
#: brings, and a letter the book uses for a piece is dropped whatever it is: a
#: German `S` is a Knight, and reading it as a rank would turn one of its moves
#: into another.
_LOOKALIKE_RANKS = "SlI"


def _build_token_re(piece_letters: str) -> re.Pattern[str]:
    """Compile the token pattern for one alphabet of piece letters.

    Only the book's own letters go in. Accepting every language's at once
    would look tolerant and be worse: `T` is a Rook in French and nothing in
    English, `B` is a Bishop in English and nothing in French, so a permissive
    class turns a misread letter into a different, legal move.
    """
    ranks = "1-8" + "".join(
        letter for letter in _LOOKALIKE_RANKS if letter not in piece_letters
    )
    return re.compile(
        _TOKEN_TEMPLATE.format(pieces=re.escape(piece_letters), ranks=ranks),
        re.VERBOSE,
    )

#: What a piece symbol leaves behind when the glyph pass fails to restore it:
#: `i.g7`, `ll:\\c3`, `'ii'e8`, `.l:txg6`. A move read from the square onwards
#: is then a legal pawn move, scored `ok` at full confidence, with a position
#: the book never reached under everything after it.
#:
#: The run is bounded and must not cross a space. What makes it wreckage
#: rather than ordinary punctuation is the mark inside it: `:`, `\\`, `'`, `<`,
#: `>`, or a lone dot carrying a letter. The angles are what a broken king
#: leaves — `♔fi>h1` read as a pawn move to h1, `<♔f3` as one to f3. A dot carrying a digit or another dot is how
#: `1.e4` and `13...Nb4` are printed, and those open a move as they always
#: did — including when a book's OCR runs the word before into the ellipsis
#: and prints `jouer...e5`, where the dot does carry a letter and still opens
#: nothing but an ordinary black move.
_WRECK_RUN = re.compile(r"[A-Za-z.:\\'|/<>]{1,5}$")
_WRECK_MARK = re.compile(r"[:\\'<>]|(?<=[A-Za-z])\.(?!\.)|(?<=[a-z])[A-Z]")


#: A move that already says which piece moved, castling included. Written
#: against SAN letters because `text_out` is translated by then.
_NAMES_A_PIECE = re.compile(r"[KQRBN]|O-O")


def _wreck_before(text: str, start: int) -> str:
    """The remains of a piece symbol printed just before `start`, if any."""
    run = _WRECK_RUN.search(text, 0, start)
    if run is None:
        return ""
    found = run.group()
    return found if _WRECK_MARK.search(found) else ""


#: Prose shorter than this, or made only of punctuation, is dropped rather than
#: attached to a move as a comment.
_MIN_COMMENT_LENGTH = 3


@dataclass
class Token:
    kind: str  # move | move_number | var_open | var_close | result | annotation | text | diagram
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
    #: The remains of a piece symbol printed immediately before this move and
    #: never restored, as in `i.g7`. Its presence says the book named a piece
    #: here, so `parse` must not read the token as the pawn move it spells.
    lost_symbol: str = ""
    #: Printed in a heavier weight than the body text. Books that typeset the
    #: game score bold and the analysis around it plain mark, character by
    #: character, the one thing `parse` otherwise has to guess: which line a
    #: move belongs to.
    bold: bool = False

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
        if self.lost_symbol:
            payload["lost_symbol"] = self.lost_symbol
        if self.bold:
            payload["bold"] = True
        return payload


def normalise(text: str) -> str:
    """Apply the one-to-one character fixes. Length is preserved."""
    return "".join(_CHARACTER_FIXES.get(ch, ch) for ch in text)


def tokenize_pages(
    pages: list[Page],
    *,
    piece_letters: str = SAN_PIECE_LETTERS,
    diagrams: list[Any] | None = None,
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

    `diagrams` are the blocks `diagrams.find` located: each one becomes a
    single `diagram` token and its rows are read as nothing else. Without that,
    a diagram set in a diagram font arrives here as eight lines of letters and
    is tokenised as prose — which is what it looked like until the font was
    understood.
    """
    token_re = _build_token_re(piece_letters)
    to_san = str.maketrans(piece_letters, SAN_PIECE_LETTERS)
    blocks: dict[int, list[Any]] = {}
    for diagram in diagrams or ():
        blocks.setdefault(diagram.page, []).append(diagram)

    tokens: list[Token] = []
    for page in pages:
        tokens.extend(_tokenize_page(page, token_re, to_san, blocks.get(page.number, [])))
    return tokens


def _tokenize_page(
    page: Page,
    token_re: re.Pattern[str],
    to_san: dict[int, int],
    diagrams: list[Any],
) -> list[Token]:
    """The page's tokens, the diagram blocks standing whole between them."""
    text = normalise(page.text)
    tokens: list[Token] = []
    cursor = 0
    for diagram in sorted(diagrams, key=lambda d: d.start):
        tokens.extend(_tokenize_span(page, text, token_re, to_san, cursor, diagram.start))
        tokens.append(
            Token(
                kind="diagram",
                text="/".join(diagram.rows),
                raw=page.text[diagram.start : diagram.end],
                page=page.number,
                start=diagram.start,
                end=diagram.end,
                bbox=diagram.bbox or page.bbox_for(diagram.start, diagram.end),
            )
        )
        cursor = diagram.end
    tokens.extend(_tokenize_span(page, text, token_re, to_san, cursor, len(text)))
    return _free_a_number_a_board_stranded(tokens, page, text)


def _tokenize_span(
    page: Page,
    text: str,
    token_re: re.Pattern[str],
    to_san: dict[int, int],
    lo: int,
    hi: int,
) -> Iterator[Token]:
    cursor = lo

    for match in token_re.finditer(text, lo, hi):
        kind = match.lastgroup
        assert kind is not None
        start, end = match.span()
        # Move numbers and promotions may carry internal spaces ("14 ." or
        # "e8 = Q"); squeeze them so downstream code sees canonical text.
        text_out = match.group() if kind == "annotation" else re.sub(r"\s+", "", match.group())
        consumed = lost_symbol = ""
        if kind == "move":
            text_out = text_out.translate(to_san)
            consumed = "".join(c.consumed for c in page.chars[start:end])
            # Only a move that names no piece can have lost one. A word run
            # into the ellipsis before a move — `jouer...Bxf5`, which the OCR
            # of one book prints without the space — otherwise flags a move
            # that spells its bishop out, and asking the board for a second
            # piece in front of it can only fail.
            if not _NAMES_A_PIECE.match(text_out):
                lost_symbol = _wreck_before(text, start)
            # A move may begin after the remains of a symbol, and nowhere else
            # that a word is already running. The pattern used to refuse both
            # with one lookbehind, which also refused `liJf6` — a knight whose
            # wreck ends on a letter — and losing black's fifth move made
            # white's sixth illegal and killed the game from there.
            if not lost_symbol and start and text[start - 1].isalnum():
                continue
            # The wreck is the piece as the book printed it, so the token
            # starts there: the reader's tap zone has to cover the symbol, not
            # just the square beside it. Taken off the token's start before
            # the prose above is closed, so the two do not both claim it.
            start -= len(lost_symbol)

        if start > cursor:
            prose = _make_text_token(page, text, cursor, start)
            if prose is not None:
                yield prose

        yield Token(
            kind=kind,
            text=text_out,
            raw=page.text[start:end],
            page=page.number,
            start=start,
            end=end,
            bbox=page.bbox_for(start, end),
            consumed=consumed,
            lost_symbol=lost_symbol,
            bold=_weight_of(page, start, end),
        )
        cursor = end

    if cursor < hi:
        prose = _make_text_token(page, text, cursor, hi)
        if prose is not None:
            yield prose


#: A bare move number ending a run of prose. Believed only where a diagram
#: stands between it and the move it announces.
_STRANDED_NUMBER = re.compile(r"(?<![A-Za-z\d])(\d{1,3})\s*$")

#: The same number printed as letters — `ll ... ♗d6` for `11 ... ♗d6`, the
#: `l`/`1` confusion this corpus already repairs in a destination rank. On its
#: own a letter is a letter; what makes this one a number is the ellipsis it
#: carries, which announces a black move and can follow nothing else.
_STRANDED_AS_LETTERS = re.compile(r"(?<![A-Za-z\d])([lI]{1,3})(\s*\.\s*\.\s*\.)\s*$")


def _free_a_number_a_board_stranded(
    tokens: list[Token], page: Page, text: str
) -> list[Token]:
    """Give back the move number a diagram separated from its move.

    A book prints the diagram of a position between the number of the move
    that reaches it and the move itself — Grivas p.17 reads `... w 7`, then a
    drawn board, then `♗d2 b4`. A drawn board occupies no characters, so the
    prose before it simply ends on a bare figure, and a bare figure is exactly
    what `_TOKEN_TEMPLATE` refuses: with neither a dot nor a move behind it,
    every page number and every year in the book would be a move number.

    Read as prose, the number is lost and the move after the board arrives
    with nothing announcing it. `parse` places it as a citation — into a
    variation — so the main line never records where it stands, and the moves
    that resume it a few lines later are played on the variation instead,
    where they are illegal. Twenty-eight of Grivas' broken moves descend from
    this one `7`.

    All three have to stand together — prose ending in a bare number, a
    diagram, a move — because that is the only shape in which the figure can
    be believed. Anywhere else it stays what it reads as.
    """
    out: list[Token] = []
    for at, token in enumerate(tokens):
        found, reading = _a_stranded_number(tokens, at)
        if found is None or reading is None:
            out.append(token)
            continue
        start = token.start + found.start(1)
        end = token.start + found.end(found.lastindex or 1)
        prose = _make_text_token(page, text, token.start, start)
        if prose is not None:
            out.append(prose)
        out.append(
            Token(
                kind="move_number",
                text=reading,
                raw=page.text[start:end],
                page=token.page,
                start=start,
                end=end,
                bbox=page.bbox_for(start, end),
                bold=_weight_of(page, start, end),
            )
        )
    return out


def _a_stranded_number(tokens: list[Token], at: int) -> tuple[re.Match[str] | None, str | None]:
    """The number this run of prose ends on, and how to read it, or nothing.

    Two shapes, and each is believed only in the company that makes it a
    number rather than a figure or a letter.
    """
    token = tokens[at]
    if token.kind != "text" or at + 1 >= len(tokens):
        return None, None
    after = tokens[at + 1]
    if after.kind == "diagram":
        # A board between the number and its move, and a move after the board.
        if at + 2 >= len(tokens) or tokens[at + 2].kind != "move":
            return None, None
        found = _STRANDED_NUMBER.search(token.raw)
        return found, found.group(1) if found else None
    if after.kind == "move":
        # The number itself printed as letters, with the ellipsis that says it
        # is one. `11` opening a page is the case in this corpus: the scanner
        # reads `ll` and the running head swallows it.
        found = _STRANDED_AS_LETTERS.search(token.raw)
        if found is None:
            return None, None
        return found, found.group(1).translate(_LETTERS_TO_DIGITS) + "..."
    return None, None


#: What a scanner leaves of the digit `1` when it prints a move number.
_LETTERS_TO_DIGITS = str.maketrans("lI", "11")


def _weight_of(page: Page, start: int, end: int) -> bool:
    """Whether the token as a whole is set bold.

    By majority of the characters that carry ink, not by any single one: a
    book that sets `12...` bold prints the ellipsis in the plain face it
    happens to have loaded, and a figurine can come from a face of its own
    with no weight to it.
    """
    marks = [c.bold for c in page.chars[start:end] if not c.char.isspace()]
    return bool(marks) and sum(marks) * 2 > len(marks)


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
