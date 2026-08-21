"""The positions a book prints as pictures, read out of its text layer.

A publisher who sets diagrams with a **diagram font** writes the position as
eight lines of eight characters, one character per square, and the font draws a
square with its piece for each letter. That is text, not an image: it survives
extraction, and it can be read back to a position exactly.

Nothing here knows a font's letters in advance. The table is **learned from the
book itself**: wherever a game has been replayed to a diagram with no break
above it, the position is known, and laying it over the sixty-four characters
says what each letter means. The letters learned that way then read the
diagrams that have no game behind them — the ones a chapter opens on, which is
where the pipeline had nothing at all.

What a diagram gives is the placement of the pieces, and only that. Whose move
it is comes from the number printed under it (`8...` is Black's eighth), and
the castling rights are inferred from the placement — see `initial_fen`.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from .extract import Page

#: A diagram is eight ranks of eight squares.
SIDE = 8

#: The characters a diagram row may be made of, before anything is known about
#: which letter is which piece. Digits are excluded: a row of a chess diagram
#: never carries one, and the exclusion is what keeps ordinary short lines of
#: text out.
_ROW = re.compile(r"[A-Za-z.,_+*'|/\\-]{8}$")

#: A position has at least this many empty squares — thirty-two in the initial
#: position, more in every position that follows it. Two characters therefore
#: cover half the block, which no line of prose does.
_MIN_EMPTY = 24


@dataclass
class Diagram:
    """One block of eight rows, as printed, with its place in the page."""

    page: int
    start: int
    end: int
    rows: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {"page": self.page, "start": self.start, "end": self.end, "rows": list(self.rows)}


def find(pages: Iterable[Page]) -> list[Diagram]:
    """Every diagram block in `pages`, in reading order."""
    found: list[Diagram] = []
    for page in pages:
        found.extend(_find_in_page(page))
    return found


def _find_in_page(page: Page) -> list[Diagram]:
    from .tokenize import normalise

    text = normalise(page.text)
    found: list[Diagram] = []
    run: list[tuple[str, int, int]] = []
    for line, start, end in list(_lines(text)) + [("", len(text), len(text))]:
        if _ROW.fullmatch(line):
            run.append((line, start, end))
            continue
        found.extend(_blocks_of(page.number, run))
        run = []
    return found


def _blocks_of(page: int, run: list[tuple[str, int, int]]) -> Iterable[Diagram]:
    """The diagrams inside one run of eight-character lines.

    A book may draw every row twice, the same characters over themselves; the
    second copy is the same rank, not the next one. That is decided over the
    whole run rather than line by line, because two ranks of a position can be
    identical in their own right — a font that prints every empty square the
    same way gives four identical rows in the opening position alone.
    """
    if len(run) >= 2 * SIDE and len(run) % (2 * SIDE) == 0:
        if all(run[i][0] == run[i + 1][0] for i in range(0, len(run), 2)):
            run = [(line, start, run[i * 2 + 1][2]) for i, (line, start, _) in enumerate(run[::2])]
    for start in range(0, len(run) - SIDE + 1, SIDE):
        block = run[start : start + SIDE]
        rows = tuple(line for line, _, _ in block)
        if _looks_like_a_position(rows):
            yield Diagram(page, block[0][1], block[-1][2], rows)


def _lines(text: str) -> Iterable[tuple[str, int, int]]:
    """Each non-empty line of `text`, with its offsets in `text`."""
    for match in re.finditer(r"[^\n]*", text):
        stripped = match.group().strip()
        if not stripped:
            continue
        start = match.start() + (len(match.group()) - len(match.group().lstrip()))
        yield stripped, start, start + len(stripped)


#: Six pieces in two colours, each printed in a light and a dark form, plus the
#: two empty squares: twenty-six characters is everything a diagram font can
#: put on a board, and a block using more is not one.
_MAX_GLYPHS = 26


def _looks_like_a_position(rows: tuple[str, ...]) -> bool:
    counts = Counter("".join(rows))
    if len(counts) > _MAX_GLYPHS:
        return False
    return sum(n for _, n in counts.most_common(2)) >= _MIN_EMPTY


def learn(observations: Iterable[tuple[tuple[str, ...], str]]) -> dict[str, str]:
    """The book's letters, from diagrams whose position is already known.

    `observations` pairs a diagram's rows with the board FEN the game had
    reached there. **Most of them are wrong**, and that is the whole
    difficulty: a diagram is most useful exactly where the parser had drifted,
    and a drifted board teaches the wrong letters. Voting character by
    character does not survive it — one book's sixteen observations left four
    letters standing.

    So the observations vote as wholes instead. Each one proposes the table it
    implies on its own; the table supported by the most others wins, and the
    letters are then merged from that agreeing set. A wrong board agrees with
    nothing, because two boards drift apart in their own directions while every
    correct one says the same thing.

    The rows are read rank eight first, the order a diagram is printed in for
    a reader sitting behind White. No book in the corpus prints one the other
    way up, and a book that did would rotate the files too, so guessing at
    orientation here would be generality nothing has asked for.
    """
    prepared = []
    for rows, board_fen in observations:
        squares = _squares_of(board_fen)
        if squares is not None and len(rows) == SIDE:
            prepared.append((tuple(rows), squares))

    best: dict[str, str] = {}
    best_support = 0
    for table, _, _ in [(_table_of(rows, squares), rows, squares) for rows, squares in prepared]:
        if table is None:
            continue
        agreeing = [other for other in prepared if _agrees(table, *other)]
        if len(agreeing) <= best_support:
            continue
        merged: dict[str, str] = {}
        for rows, squares in agreeing:
            merged.update(_table_of(rows, squares) or {})
        best, best_support = merged, len(agreeing)
    return _extend_by_case(best)


def _extend_by_case(table: dict[str, str]) -> dict[str, str]:
    """The same letter in the other case, when the book has shown it means so.

    A diagram font prints each piece twice, once for a light square and once
    for a dark one, and the two forms are the same letter in the two cases.
    That is a fact about this book rather than an assumption about fonts: it is
    applied only when every pair already learned agrees on it. Two of Sakaev's
    twenty diagrams cannot be read without it — no game in those twelve pages
    reaches a position with a white queen on a dark square, so that form is
    never printed beside a board anyone knows.
    """
    pairs = [
        (char, table[char.swapcase()])
        for char in table
        if char.isalpha() and char.swapcase() in table
    ]
    if any(table[char] != piece for char, piece in pairs):
        return table
    extended = dict(table)
    for char, piece in table.items():
        if char.isalpha():
            extended.setdefault(char.swapcase(), piece)
    return extended


def _table_of(rows: tuple[str, ...], squares: list[str]) -> dict[str, str] | None:
    """The letters one diagram implies, or `None` if it contradicts itself."""
    table: dict[str, str] = {}
    for row, rank in zip(rows, squares):
        for char, piece in zip(row, rank):
            if table.setdefault(char, piece) != piece:
                return None
    return table


def _agrees(table: dict[str, str], rows: tuple[str, ...], squares: list[str]) -> bool:
    """Whether this diagram reads, under `table`, as the board it was seen on."""
    for row, rank in zip(rows, squares):
        for char, piece in zip(row, rank):
            if table.get(char, piece) != piece:
                return False
    return True


def _squares_of(board_fen: str) -> list[str] | None:
    """A board FEN as eight ranks of eight characters, `.` for an empty one."""
    ranks = board_fen.split("/")
    if len(ranks) != SIDE:
        return None
    out = []
    for rank in ranks:
        row = "".join("." * int(ch) if ch.isdigit() else ch for ch in rank)
        if len(row) != SIDE:
            return None
        out.append(row)
    return out


def decode(rows: tuple[str, ...], table: dict[str, str]) -> str | None:
    """The board FEN these rows print, or `None` if a character is unknown.

    Refusing on one unknown character is deliberate. A diagram is used to
    overrule the parser's own board, so a position guessed with a hole in it
    would be worse than no diagram at all.
    """
    ranks = []
    for row in rows:
        squares = ""
        for char in row:
            if char not in table:
                return None
            squares += table[char]
        ranks.append(re.sub(r"\.+", lambda m: str(len(m.group())), squares))
    return "/".join(ranks)


def initial_fen(board_fen: str, *, number: int, black_to_move: bool) -> str:
    """A complete FEN for a diagram, from the move number printed under it.

    Castling rights are inferred from the placement: a king still on its own
    square with a rook still on its corner is credited with the right. The book
    does not print the rights, and this is the reading that costs least — a
    game whose king has merely returned home is rare, while refusing every
    right would make the next legal castling illegal, which is not.
    """
    ranks = _squares_of(board_fen) or []
    rights = ""
    if len(ranks) == SIDE:
        white, black = ranks[7], ranks[0]
        if white[4] == "K":
            rights += "K" if white[7] == "R" else ""
            rights += "Q" if white[0] == "R" else ""
        if black[4] == "k":
            rights += "k" if black[7] == "r" else ""
            rights += "q" if black[0] == "r" else ""
    return f"{board_fen} {'b' if black_to_move else 'w'} {rights or '-'} - 0 {number}"
