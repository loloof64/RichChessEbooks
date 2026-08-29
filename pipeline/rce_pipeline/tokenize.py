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
from typing import Any

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
      # `a)` and `b)` label the alternatives a book lists under one move —
      # "and now: a) 20...Qxe5 ... b) 20...dxe5" — and the label's bracket
      # closes nothing. Read as a variation close it pops the aside those
      # very lines belong to, and the whole list is played on the game's
      # board instead: two of Grivas page 21's lists, thirteen moves each.
      # A lone letter with a space in front of it is the label; a variation
      # ends in a digit, a check or an annotation, never in one letter.
    | (?P<var_close>(?<!\s[A-Za-z])\))
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
              # The usual form, and the `12...` that announces a black move
              # — which a scan prints with two dots as readily as three.
              # Nineteen of SuperAttaquant's black numbers lost a dot and
              # fifteen of Boussole's; read as white's, each one throws the
              # rest of its line a ply out of step with the page. A white
              # number is one dot and only one, so nothing else is at stake.
              # The two-dot form is tight, where the three-dot one tolerates
              # spaces: `9. .i.xg5` opens with a move number and the wreck of
              # a bishop, and a loose second dot eats the wreck.
              \s*\.(?:\s*\.\s*\.|\.)?
              # Batsford, Gambit and Informator print `12 Nb1` with no dot at
              # all. Accepting a bare number would make a move number of every
              # figure in the prose, so it only counts when a move follows it
              # directly — which is exactly where a number can do no harm.
              #
              # The pawn move behind it is read with this book's ranks, the
              # letters a scanner leaves among them included. Digits alone
              # cost the number in front of every such move: Grivas page 21
              # prints `19 e5!! dxe5` as `19 eS!! dxeS`, the number stayed in
              # the prose ending "...a slow but certain defeat.", and neither
              # move was read at all — no node, no box, nothing for the reader
              # to correct. A letter rank needs the move's own guard with it,
              # or `27 elle` announces a move; a capture cannot take it, the
              # captured square being spelled out behind the `x`.
            | (?=\s+(?:O-O|0-0|[{pieces}][a-h1-8x]
                        |[a-h]x|[a-h][{ranks}](?![A-Za-z0-9'])))
          )
      )
    | (?P<move>
          (?:
              (?:O-O-O|O-O|0-0-0|0-0)
              # The move written from square to square — `...b7-b5`, `♗f1-g2`
              # — which is how a book names a plan and how some name a move.
              # Read as two moves, the first of them is the piece standing
              # still, and it is illegal: 93 of Sakaev's moves died under one
              # `...b7-b5` in a sentence about the Caro-Kann.
            | (?<![A-Za-z])[{pieces}]?[a-h][1-8]-[a-h][{ranks}]
              # A space between the square's file and its rank: the same
              # subset font that breaks `18` into `1 8` breaks `Rac1` into
              # `Rac 1`, and the move is then never read. Only where the token
              # begins at a word boundary — otherwise the tail of an ordinary
              # word swallows the number that follows it ("the move 6.Bg5"
              # reads as `e 6`), and the citation the number announced is lost
              # with it.
              # And never where the word carries on from the line above:
              # `pour Ie cloua-\nge 6.♗g5` reads `ge 6` as a square, which
              # takes the number of the move behind it — the `6.♗g5` of the
              # comment on Boussole page 65, and the whole line after it.
            | (?<![A-Za-z])(?<!-\n)[{pieces}]?[a-h]?[1-8]?x?[a-h][ ][{ranks}](?!\.)
              # The piece a pawn promoted to. `=Q` is one way of writing it
              # and the figurine set straight after the square is the other:
              # SuperAttaquant prints `33.dxe8♕+`, `42.c8♕`, `29.exf8♕#`, and
              # with no `=` to find, none of those was a token at all — the
              # move vanished and the line went with it, twelve times over
              # twelve pages. Only on the promotion ranks, and only where no
              # square follows the piece: `16♗a2♗c7`, where a lost space runs
              # two moves together, would otherwise read as a pawn promoting
              # to a bishop on the second rank.
            | [{pieces}]?[a-h]?[1-8]?x?[a-h][{ranks}](?:\s*=\s*[{pieces}]|(?<=[18])[{pieces}](?![a-h]))?
              # A file the scanner read as a digit. No notation writes a piece
              # and two digits, so what stands where the file belongs is the
              # wreck of the file letter and nothing else — and this scan
              # wrecks it differently every time (`♗g5` as `♗25`, `♘d5` as
              # `♘45`, `♗f4` as `♗41`), so no substitution table reaches it.
              # The rank survives, `parse` asks the board which file, and the
              # move keeps the box the page gave it either way.
              #
              # A *bare* rank behind the symbol is a different case and is
              # `glyphs._file_the_symbol_swallowed`'s: there the letter is
              # still on the page, inside the ink the symbol covered.
            | (?<![A-Za-z\d])[{pieces}][1-8][{ranks}]
              # And the same move with the file gone altogether: `28.♔g1`
              # arrives as `28.♔1`, the letter having left no character at
              # all. A piece and a rank is a fragment of anything — it is the
              # shape a bare rank makes in prose — so it is read **only where
              # a move number stands in front of it**, where the page has
              # already said that a move is due and nothing else can be.
            | (?<![A-Za-z\d])[{pieces}][{ranks}]
          )
          [+#]?
          # Never an apostrophe: with `l` read as a rank, the French elision
          # `de l'échiquier` is shaped exactly like `Re1` and every article in
          # the book becomes a move. 27 of them over two scans, and not one
          # real move in the corpus is followed by one.
          #
          # Unless what runs into it is the next move. A restored symbol gives
          # back one character where the scan had three, and the space beside
          # it goes with them: Boussole page 65 prints `16 ♗a2 ♗c7` and the
          # layer has `16♗a2♗c7`, where neither move is read at all — White's
          # sixteenth and Black's are both lost, and the game is two plies
          # behind the page from there to the end. A piece letter with a
          # square behind it is a move and is nothing else; prose that begins
          # a word with a capital does not carry on with a file and a rank.
          (?:(?![A-Za-z0-9'])|(?=[{pieces}]x?[a-h][{ranks}]))
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

#: A rank standing at the head of a move that names no piece — `2b5`, `8h3+`,
#: `2xh7+`. SAN writes a rank only to say which of two pieces moved, so it can
#: never stand without the piece letter in front of it, and what is printed
#: there is a piece symbol the glyph pass failed to restore: this book's
#: scanner draws the bishop as `2` and the rook as `8`.
#:
#: `_WRECK_RUN` refuses digits on purpose — a digit in front of a square is
#: normally a move number — and this is the one place it cannot be one, since
#: the move it would announce has no piece to carry the rank. Twenty-three of
#: them on SuperAttaquant and not one on the five other books.
_WRECK_AS_A_RANK = re.compile(r"^[1-8](?=x?[a-h][1-8{ranks}])".format(
    ranks=_LOOKALIKE_RANKS
))


#: A piece and a rank and nothing else — `♔1`, `♗7`, `♖3` — the move whose
#: file letter came off the scan as no character at all. Written against SAN
#: letters: it is read from `text_out`, which is translated by then.
_A_PIECE_AND_A_RANK = re.compile(r"^[KQRBN][1-8][+#]?$")


def _announced_by_a_number(out: list["Token"], text: str, cursor: int, start: int) -> bool:
    """Whether a move number stands between `cursor` and `start`, and nothing else.

    The page says a move is due there, which is the whole licence for reading
    a token that would otherwise be a fragment of prose. The number is usually
    a token of its own by now; on a scan that lost the space beside a symbol
    it is still welded to what follows, and `_WELDED_NUMBER` finds it there.
    """
    if out and out[-1].kind == "move_number" and not text[out[-1].end : start].strip():
        return True
    return _WELDED_NUMBER.search(text, cursor, start) is not None


#: A move written from square to square, the long form of it: `b7-b5`,
#: `Bf1-g2`. Written against SAN letters because `text_out` is translated by
#: the time it is read.
_SQUARE_TO_SQUARE = re.compile(r"^([KQRBN]?)[a-h][1-8]-([a-h][1-8])$")

#: A move that already says which piece moved, castling included. Written
#: against SAN letters because `text_out` is translated by then.
_NAMES_A_PIECE = re.compile(r"[KQRBN]|O-O")


#: The ink a restored symbol leaves in front of the piece letter it became.
#: Short — one or two characters, where the wreck of a symbol nothing restored
#: runs to five — because what stands here is the remains of a glyph and not a
#: word: keeping it to two is what stops a French article welded to a square
#: from making a move of it.
_STUMP_RUN = re.compile(r"[A-Za-z.:\\'|/<>]{1,2}$")


def _wreck_before_a_named_piece(text: str, start: int) -> str:
    """The stump of a symbol standing in front of the letter it was read as.

    What marks it is the same thing that marks any wreck, read across the
    join: the case change into the piece letter (`lN`, `ltN`, `iQ`), or a mark
    no word carries. `text[start]` is that letter, so it is part of the test
    and never part of the answer.
    """
    run = _STUMP_RUN.search(text, 0, start)
    if run is None:
        return ""
    stump = run.group()
    return stump if _WRECK_MARK.search(stump + text[start]) else ""


def _wreck_before(text: str, start: int, spellings: dict[str, str]) -> str:
    """The remains of a piece symbol printed just before `start`, if any.

    What usually marks it is a mark no word carries — see `_WRECK_MARK`. But
    a scanner may read a symbol as one ordinary letter and nothing else:
    SuperAttaquant's queen comes out `W`, ninety times over, and `Wf3+` is
    then a token the pattern refuses outright because a word is running into
    it. The book has said what that letter is, in the ink under every symbol
    the glyph pass *did* restore, so the spelling table answers for the mark:
    a run the book has been seen spelling a piece is that piece's wreck.

    Only the spelled ending is given back, never the whole run; and the ink
    of a symbol begins where the word does, so a letter may not stand in
    front of it. Without that last clause the `n` this book spells its queen
    with is found inside "positional" and the word ends in a move to a1.

    A spelling of nothing but dots is refused whatever the book has been seen
    doing with it: a dot in front of a move is how every book in the corpus
    announces a black one, and reading `21 ...f5` as a bishop move costs the
    move and the number with it.
    """
    run = _WRECK_RUN.search(text, 0, start)
    if run is None:
        return ""
    found = run.group()
    if _WRECK_MARK.search(found):
        return found
    for cut in range(len(found)):
        spelled = found[cut:]
        if spelled.strip(".") and spelled in spellings and (
            cut == 0 or not found[cut - 1].isalpha()
        ):
            return spelled
    return ""


def _piece_spelled(wreck: str, spellings: dict[str, str]) -> str:
    """The piece this book spells that way, if it has been seen spelling it.

    The longest ending of the wreck the book has taught, because the wreck
    runs back over whatever stood before the symbol: `..ltJ` is the knight of
    `.ltJ` with a move number's dot in front of it.
    """
    for cut in range(len(wreck)):
        piece = spellings.get(wreck[cut:])
        if piece is not None:
            return piece
    return ""


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
    #: Which piece that wreck is, where the book's own spelling of its symbols
    #: says so — `glyphs.spellings`, learned from the symbols the glyph pass
    #: did restore. Empty when the book taught no spelling for this ink.
    lost_piece: str = ""
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
        if self.lost_piece:
            payload["lost_piece"] = self.lost_piece
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
    spellings: dict[str, str] | None = None,
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
        tokens.extend(_tokenize_page(
            page, token_re, to_san, blocks.get(page.number, []), spellings or {}
        ))
    return _drop_a_bracket_nothing_closes(tokens)


def _tokenize_page(
    page: Page,
    token_re: re.Pattern[str],
    to_san: dict[int, int],
    diagrams: list[Any],
    spellings: dict[str, str],
) -> list[Token]:
    """The page's tokens, the diagram blocks standing whole between them."""
    text = normalise(page.text)
    tokens: list[Token] = []
    cursor = 0
    for diagram in sorted(diagrams, key=lambda d: d.start):
        tokens.extend(_tokenize_span(
            page, text, token_re, to_san, cursor, diagram.start, spellings
        ))
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
    tokens.extend(_tokenize_span(
        page, text, token_re, to_san, cursor, len(text), spellings
    ))
    return _free_a_number_a_board_stranded(tokens, page, text)


def _drop_a_bracket_nothing_closes(tokens: list[Token]) -> list[Token]:
    """A parenthesis with no partner in the whole run was never printed.

    A scan invents them: Boussole page 65 opens one in the middle of the word
    "obliges" and nothing closes it, so everything below — the game's own
    score included — is read as one enormous variation. `parse` trusts a
    bracket over every rule it has, on the ground that the book was explicit
    there; that ground is gone when the book never wrote it. The two
    alternative variations at the top of that page's second column are read as
    two alternatives once it goes, which is what they are.

    Balanced over the **whole run** and not page by page, because a book
    really does open a variation on one page and close it on the next: doing
    this a page at a time takes three of Boussole's pages away entirely.

    Only the unmatched ones go. A bracket that is merely misplaced still says
    a variation is here somewhere.
    """
    opens: list[int] = []
    unmatched: set[int] = set()
    for index, token in enumerate(tokens):
        if token.kind == "var_open":
            opens.append(index)
        elif token.kind == "var_close":
            if opens:
                opens.pop()
            # An unmatched `)` is left alone: it closes nothing, and `parse`
            # already ignores one that arrives at the top of the stack.
        elif token.kind == "result":
            # A game is as far as a bracket ever reaches. Balancing the whole
            # book instead lets a stray `)` pages away pair with an invented
            # `(` and the invention survives; balancing a page at a time
            # breaks the variation a book opens on one page and closes on the
            # next, and costs Boussole three pages.
            unmatched.update(opens)
            opens.clear()
    # And an unmatched `(` only where it opens on prose. A variation begins
    # with a move or with the number announcing one, always; a bracket that
    # opens on a word is not one however the rest of the page balances, and
    # requiring both signs is what keeps three of Boussole's pages, where a
    # stray parenthesis stands in front of a line of play that is real.
    unmatched.update(
        index for index in opens
        if index + 1 >= len(tokens)
        or tokens[index + 1].kind not in ("move", "move_number")
    )
    if not unmatched:
        return tokens
    return [t for i, t in enumerate(tokens) if i not in unmatched]


def _tokenize_span(
    page: Page,
    text: str,
    token_re: re.Pattern[str],
    to_san: dict[int, int],
    lo: int,
    hi: int,
    spellings: dict[str, str],
) -> list[Token]:
    out: list[Token] = []
    cursor = lo

    for match in token_re.finditer(text, lo, hi):
        kind = match.lastgroup
        assert kind is not None
        start, end = match.span()
        # Move numbers and promotions may carry internal spaces ("14 ." or
        # "e8 = Q"); squeeze them so downstream code sees canonical text.
        text_out = match.group() if kind == "annotation" else re.sub(r"\s+", "", match.group())
        consumed = lost_symbol = ""
        number_at: int | None = None
        if kind == "move":
            text_out = text_out.translate(to_san)
            # A piece and a rank is a move only where a number announces one.
            if _A_PIECE_AND_A_RANK.match(text_out) and not _announced_by_a_number(
                out, text, cursor, start
            ):
                continue
            journey = _SQUARE_TO_SQUARE.match(text_out)
            if journey is not None:
                # Where the piece ends is the move; where it starts is where
                # it already stands. The token keeps the whole of it, so the
                # reader taps the journey the book drew.
                text_out = journey.group(1) + journey.group(2)
            consumed = "".join(c.consumed for c in page.chars[start:end])
            # Only a move that names no piece can have lost one. A word run
            # into the ellipsis before a move — `jouer...Bxf5`, which the OCR
            # of one book prints without the space — otherwise flags a move
            # that spells its bishop out, and asking the board for a second
            # piece in front of it can only fail.
            if not _NAMES_A_PIECE.match(text_out):
                lost_symbol = _wreck_before(text, start, spellings)
            # The symbol may also have been read as a character the move
            # pattern took in: a rank the move has no piece to carry. It is
            # answered below, once the wreck standing before it has had the
            # start of the token, because it needs none of it.
            rank_wreck = _WRECK_AS_A_RANK.match(text_out)
            if rank_wreck is not None:
                text_out = text_out[len(rank_wreck.group()) :]
            # A move may begin after the remains of a symbol, and nowhere else
            # that a word is already running. The pattern used to refuse both
            # with one lookbehind, which also refused `liJf6` — a knight whose
            # wreck ends on a letter — and losing black's fifth move made
            # white's sixth illegal and killed the game from there.
            if not lost_symbol and start and text[start - 1].isalnum():
                # Unless what runs into it is its own move number. A symbol
                # the glyph pass restores gives back one character where the
                # scan had three, and the space beside it goes with them:
                # `2.ltJf3` arrives as `2Nf3`, `22♖xf7` as `22Rxf7`. Neither
                # the number nor the move is then read, and the move that
                # would have resumed the score is exactly the one lost.
                welded = _WELDED_NUMBER.search(text, cursor, start)
                if welded is not None:
                    number_at = welded.start(1)
                else:
                    # Or the remains of the symbol it names. The glyph pass
                    # restores the piece letter and leaves the rest of the ink
                    # standing in front of it — `lNc3`, `ltNxe5`, `iQd8` — and
                    # a move that names its piece never looks for a wreck,
                    # since asking the board for a second piece in front of one
                    # can only fail. It is still the reader's tap zone, so the
                    # token takes it in without reading anything into it.
                    stump = _wreck_before_a_named_piece(text, start)
                    if not stump:
                        # Or the move before it, run into it by the same lost
                        # space: `16♗a2♗c7`. What stands behind is not a word
                        # but a move already read, so there is no word here to
                        # refuse. Black's sixteenth was dropped for want of
                        # this, and the game read two plies behind the page
                        # for the rest of Boussole page 65.
                        if not (out and out[-1].kind == "move" and out[-1].end == start):
                            continue
                    start -= len(stump)
            # The wreck is the piece as the book printed it, so the token
            # starts there: the reader's tap zone has to cover the symbol, not
            # just the square beside it. Taken off the token's start before
            # the prose above is closed, so the two do not both claim it.
            start -= len(lost_symbol)
            # A wreck can hold a mark the annotation branch has already taken
            # for a comment on the move: the knight of `lL!g4` is drawn with a
            # `!` in it. Nothing else can stand inside a wreck — no digit, no
            # bracket, no letter run the branches above match — so an
            # annotation is the only token to take back, and if anything else
            # is there the wreck is not believed at all.
            # Anything else it may not take, but what is left of it once that
            # token has its own back may still be a wreck: `9.i.xg5` runs
            # back over the move number's dot, gives it up, and the `i.` that
            # remains is the bishop the book printed.
            while lost_symbol and out and out[-1].end > start:
                if out[-1].kind == "annotation":
                    cursor = out.pop().start
                    continue
                start += len(lost_symbol)
                kept = text[out[-1].end : start]
                # A mark no word carries, or a run this book has been seen
                # spelling a piece with. Without the second, the queen
                # SuperAttaquant's scanner writes `W` was given back whole
                # every time it stood behind a move number — `21...Wb7` — and
                # `b7` was left to be read as a pawn move to the seventh rank.
                # The number in front is what makes the letter safe to believe
                # here: nothing else stands between the two.
                lost_symbol = kept if (
                    _WRECK_MARK.search(kept) or _piece_spelled(kept, spellings)
                ) else ""
                start -= len(lost_symbol)
                break
            # Last, because it is the only part of the wreck that stands
            # inside the token: the start needs no moving for it, and the
            # take-back above counts back from the start.
            if rank_wreck is not None:
                lost_symbol += rank_wreck.group()
            if number_at is None and lost_symbol:
                # The number announcing the move, which the wreck standing in
                # front of it hid. A bare number is a move number only where a
                # move follows it, and a wreck is not one: `16lilxd4` on
                # Grivas page 18 — with the space gone the way it goes beside
                # any symbol — left the `16` in the prose above, and the move
                # it announced played a ply early for the rest of the game.
                # The wreck is the licence: a figure, then this book's own
                # spelling of a piece, then a square, is a move being
                # announced, and prose has no such run in it.
                announcing = _NUMBER_BEFORE_A_WRECK.search(text, cursor, start)
                if announcing is not None:
                    number_at = announcing.start(1)

        if number_at is not None:
            # The number stands as its own token, so the move behind it is
            # announced exactly as a printed one would be.
            if number_at > cursor:
                prose = _make_text_token(page, text, cursor, number_at)
                if prose is not None:
                    out.append(prose)
            out.append(Token(
                kind="move_number",
                text=text[number_at:start],
                raw=page.text[number_at:start],
                page=page.number,
                start=number_at,
                end=start,
                bbox=page.bbox_for(number_at, start),
                bold=_weight_of(page, number_at, start),
            ))
            cursor = start

        if start > cursor:
            prose = _make_text_token(page, text, cursor, start)
            if prose is not None:
                out.append(prose)

        out.append(Token(
            kind=kind,
            text=text_out,
            raw=page.text[start:end],
            page=page.number,
            start=start,
            end=end,
            bbox=page.bbox_for(start, end),
            consumed=consumed,
            lost_symbol=lost_symbol,
            lost_piece=_piece_spelled(lost_symbol, spellings) if lost_symbol else "",
            bold=_weight_of(page, start, end),
        ))
        cursor = end

    if cursor < hi:
        prose = _make_text_token(page, text, cursor, hi)
        if prose is not None:
            out.append(prose)
    return out


#: A move number run into the move it announces. The separator is lost with
#: the symbol the glyph pass replaces: three characters of scan (`ltJ`) come
#: back as one (`N`), and the space or the dot in front of them goes too.
_WELDED_NUMBER = re.compile(r"(?<![A-Za-z\d])(\d{1,3})$")

#: A move number standing in front of the wreck of a piece symbol. Where the
#: glyph pass restored the symbol the number is welded to it and
#: `_WELDED_NUMBER` finds it; where it failed, the ink of the symbol is still
#: there, and the number may be flush against it (`16lilxd4`) or a space away
#: (`21 lilc6`). Neither reaches the bare-number branch of the token pattern,
#: which asks for a piece letter or a pawn move and is handed a wreck.
#:
#: Plain spaces only, never a newline: a figure ending a line would otherwise
#: announce whatever opens the next, which in two columns is not even the same
#: paragraph.
_NUMBER_BEFORE_A_WRECK = re.compile(r"(?<![A-Za-z\d])(\d{1,3})[ ]*$")

#: A bare move number ending a run of prose. Believed only where a diagram
#: stands between it and the move it announces.
_STRANDED_NUMBER = re.compile(r"(?<![A-Za-z\d])(\d{1,3})\s*$")

#: The same number printed as letters — `ll ... ♗d6` for `11 ... ♗d6`, the
#: `l`/`1` confusion this corpus already repairs in a destination rank. On its
#: own a letter is a letter; what makes this one a number is the ellipsis it
#: carries, which announces a black move and can follow nothing else.
#:
#: The digits and the letters mix, because the confusion is per character and
#: not per number: Grivas prints `10 ...♘xd4` as `lO ...` and `21 ...f5` as
#: `2l ...`, one character lost out of two either way. Refusing the mixed form
#: left both of those moves with no number to announce them, and the analysis
#: hanging off each was played on the game's own board.
_STRANDED_AS_LETTERS = re.compile(
    r"(?<![A-Za-z\d])([\dlIOo](?:[ ]?[\dlIOo]){0,2})(\s*\.\s*\.\s*\.)\s*$"
)


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
        # The space a subset font leaves between the two figures of a number
        # goes with it: `1 l ...` is the eleventh move printed in two pieces.
        digits = found.group(1).translate(_LETTERS_TO_DIGITS).replace(" ", "")
        if found.group(1).replace(" ", "").isdigit():
            # All digits already: whatever kept this from being read as a
            # number, it was not the scanner's alphabet, and reading it here
            # would take every figure in front of an ellipsis.
            return None, None
        if digits.startswith("0") or not 0 < int(digits) <= _LETTERS_CEILING:
            # `O ...` reads as move zero and `lOO ...` as move one hundred:
            # the first is no move at all, and neither is what the letters
            # were. A number a book prints has a move behind it.
            return None, None
        return found, digits + "..."
    return None, None


#: What a scanner leaves of a digit when it prints a move number.
_LETTERS_TO_DIGITS = str.maketrans("lIOo", "1100")

#: Above this a book is not numbering a move, so a run of letters that reads
#: as a bigger figure was never a number. Mirrors `parse._NUMBER_CEILING`.
_LETTERS_CEILING = 120


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
