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
from itertools import permutations
from typing import Any, Iterable, Sequence

from .extract import BBox, Page

#: A diagram is eight ranks of eight squares.
SIDE = 8

#: A line that could be a rank: short, and carrying no digit. A diagram row
#: never carries one, and a book's own page numbers and move numbers are what
#: that keeps out. Everything else about the line is decided over the block:
#: eight lines of the same length, holding a position between them.
#:
#: The width is a range because a book frames its board. Sakaev prints eight
#: characters and nothing else; Quality Chess prints ten — a rank frame, the
#: eight squares, and the board's edge — in a font whose glyphs sit in the
#: private use area and mean nothing to anybody but itself.
_ROW = re.compile(r"[^\d\n]{8,14}$")

#: The widest frame a board is allowed to carry on either side.
_MAX_MARGIN = 6

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
    #: Where the diagram was printed, for a block that has no text of its own
    #: to be measured from — a board drawn as a picture, whose `start` and
    #: `end` are the single point in the text where it was met. `None` for a
    #: diagram set in a font, where the characters carry their own boxes.
    bbox: BBox | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "page": self.page,
            "start": self.start,
            "end": self.end,
            "rows": list(self.rows),
        }
        if self.bbox is not None:
            payload["bbox"] = self.bbox.to_json()
        return payload


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
        # A run holds lines of one width: the ranks of a board are printed to
        # the same measure, and a change of width ends it.
        if _ROW.fullmatch(line) and (not run or len(line) == len(run[0][0])):
            run.append((line, start, end))
            continue
        found.extend(_blocks_of(page.number, run))
        run = [(line, start, end)] if _ROW.fullmatch(line) else []
    return found


def _blocks_of(page: int, run: list[tuple[str, int, int]]) -> Iterable[Diagram]:
    """The diagrams inside one run of equal-width lines.

    A book may draw every row twice, the same characters over themselves; the
    second copy is the same rank, not the next one. That is decided over the
    whole run rather than line by line, because two ranks of a position can be
    identical in their own right — a font that prints every empty square the
    same way gives four identical rows in the opening position alone.
    """
    if len(run) >= 2 * SIDE and len(run) % (2 * SIDE) == 0:
        if all(run[i][0] == run[i + 1][0] for i in range(0, len(run), 2)):
            run = [(line, start, run[i * 2 + 1][2]) for i, (line, start, _) in enumerate(run[::2])]

    while len(run) >= SIDE:
        block, taken = _board_within(run)
        if block is None:
            return
        yield Diagram(page, taken[0][1], taken[-1][2], block)
        run = run[run.index(taken[-1]) + 1 :]


def _board_within(
    run: list[tuple[str, int, int]],
) -> tuple[tuple[str, ...] | None, list[tuple[str, int, int]]]:
    """The eight rows and eight columns of `run` that are the board itself.

    A book frames its board, above it and beside it: Quality Chess prints a row
    of edge glyphs, then the eight ranks, then another row. Which rows and
    columns are the board is not asked of the book — every window of eight by
    eight is tried, and the one whose characters are most spread out wins.

    Spread is what tells a square from a frame. A square's character comes back
    across the whole board — half of it is empty, and empty is one character
    per colour of square — while a frame glyph is drawn along one row or one
    column and nowhere else. Counting how often a character appears would not
    separate the two: a frame row repeats one glyph eight times over.
    """
    best: tuple[str, ...] | None = None
    best_lines: list[tuple[str, int, int]] = []
    best_score = 0
    width = len(run[0][0])
    for top in range(0, min(len(run) - SIDE, _MAX_MARGIN) + 1):
        lines = run[top : top + SIDE]
        for left in range(0, min(width - SIDE, _MAX_MARGIN) + 1):
            window = tuple(line[left : left + SIDE] for line, _, _ in lines)
            if len(set("".join(window))) > _MAX_GLYPHS:
                continue
            score = _spread(window)
            if score > best_score:
                best, best_lines, best_score = window, lines, score
    if best_score < _MIN_EMPTY:
        return None, []
    return best, best_lines


def _spread(window: tuple[str, ...]) -> int:
    """How many of the sixty-four characters come back on another row *and* on
    another column — the squares, as opposed to the frame around them."""
    rows: dict[str, set[int]] = defaultdict(set)
    columns: dict[str, set[int]] = defaultdict(set)
    for r, row in enumerate(window):
        for c, char in enumerate(row):
            rows[char].add(r)
            columns[char].add(c)
    return sum(
        1
        for row in window
        for c, char in enumerate(row)
        if len(rows[char]) > 1 and len(columns[char]) > 1
    )


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


#: How far either side of where a diagram was met its position is looked for.
#: A parser reading a difficult book is a few plies out, not lost; and every
#: board offered is one more chance for a wrong one to be believed.
SEARCH_DEPTH = 12


def around(main_lines: dict[str, list[str]], check: dict[str, Any]) -> list[str]:
    """The positions this game's main line passes through near this diagram."""
    line = main_lines.get(check.get("game") or "", [])
    middle = check.get("index", 0)
    return line[max(0, middle - SEARCH_DEPTH) : middle + SEARCH_DEPTH + 1]


def learn(
    observations: Iterable[tuple[tuple[str, ...], Sequence[str]]],
    *,
    min_diagrams: int = 1,
) -> dict[str, str]:
    """The book's letters, from diagrams printed on positions it can reach.

    Each observation pairs a diagram's rows with **every board the line passed
    through** on its way there, most recent first. Offering the whole recent
    history rather than the board the parser stopped on is what makes this work
    on a book whose reading is poor: the parser is usually a few plies out
    rather than lost, and the position the diagram prints is one it walked past.

    Most observations are wrong, and that is the whole difficulty: a diagram is
    most useful exactly where the score had drifted, and a drifted board teaches
    the wrong letters. Voting character by character does not survive it — one
    book's sixteen observations left four letters standing out of twenty-three.
    So the observations vote **as wholes**: each proposes the table it implies,
    the table supported by the most other diagrams wins, and the letters are
    merged from those. A wrong board agrees with nothing, because two boards
    drift apart in their own directions while every correct one says the same.

    `min_diagrams` is how many diagrams must agree before a table is believed.
    One is enough when the board is known to be sound; ask for two when the
    history is being trawled, where a single coincidence is conceivable.

    The rows are read rank eight first, the order a diagram is printed in for
    a reader sitting behind White. No book in the corpus prints one the other
    way up, and a book that did would rotate the files too, so guessing at
    orientation here would be generality nothing has asked for.
    """
    prepared: list[tuple[tuple[str, ...], list[list[str]]]] = []
    for rows, board_fens in observations:
        boards = [squares for squares in map(_squares_of, board_fens) if squares]
        if boards and len(rows) == SIDE:
            prepared.append((tuple(rows), boards))

    best: dict[str, str] = {}
    best_support = 0
    for rows, boards in prepared:
        for squares in boards:
            table = _table_of(rows, squares)
            if table is None:
                continue
            agreed = [
                (other_rows, next((s for s in other_boards if _agrees(table, other_rows, s)), None))
                for other_rows, other_boards in prepared
            ]
            supporting = [(r, s) for r, s in agreed if s is not None]
            if len(supporting) <= best_support:
                continue
            merged: dict[str, str] = {}
            for other_rows, squares_of_other in supporting:
                merged.update(_table_of(other_rows, squares_of_other) or {})
            best, best_support = merged, len(supporting)
    if best_support < min_diagrams:
        return {}
    return _extend_by_case(best)


#: Where a font that carries no Unicode meaning of its own puts the ASCII it
#: was drawn against. `Chess-Merida` prints its pawn at U+F070, which is `p`.
_PRIVATE_USE = 0xF000


def _case_partner(char: str) -> str | None:
    """The same letter in the other case, private use area included.

    A diagram font names its two forms of a piece with one letter in two cases,
    and a font mapped into the private use area keeps the ASCII layout
    underneath — so the partner of U+F070 is U+F050, exactly as `p` and `P`.
    """
    code = ord(char)
    private = _PRIVATE_USE <= code <= _PRIVATE_USE + 0xFF
    base = chr(code - _PRIVATE_USE) if private else char
    if not base.isalpha():
        return None
    partner = base.swapcase()
    return chr(ord(partner) + _PRIVATE_USE) if private else partner


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
    partners = {char: _case_partner(char) for char in table}
    if any(
        table[partner] != piece
        for char, piece in table.items()
        if (partner := partners[char]) in table
    ):
        return table
    extended = dict(table)
    for char, piece in table.items():
        if partners[char] is not None:
            extended.setdefault(partners[char], piece)
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


def name_the_strays(
    table: dict[str, str],
    boards: Sequence[Sequence[str]],
    neighbours: dict[str, list[str]],
) -> dict[str, str]:
    """The same table, with the squares no cluster explained read off the board.

    A stray is one square of one board — SuperAttaquant has seven of them over
    thirteen boards — and one is enough for :func:`decode` to refuse the whole
    board, which is the difference between a game the reader can play through
    and a game with no position under any of its moves.

    Two things know what such a square is and neither is enough alone. The
    **distance** says which of the believed characters its picture is most
    like, and it is the picture that went wrong, so its first answer is not
    always right. **Legality** says which pieces can stand there at all, and on
    six of those seven boards it leaves nine or eleven of the thirteen
    standing — though on the seventh it leaves exactly one, a white king, which
    is the piece a board cannot do without. Asked in that order — the nearest
    character that leaves a position anybody could have reached — they answer
    together.

    **A board's strays are named together**, because legality is a property of
    the whole position: with a second square still unexplained the board cannot
    be decoded at all, so no reading of the first one can ever stand. Two of
    SuperAttaquant's boards carry two strays each, and named one at a time they
    were refused however plain each of them was — 39 moves of one game with no
    position under any of them. The joint readings are tried nearest first, by
    the sum of the two distances.

    A stray that no character can make legal keeps its own, and its board is
    refused as before: a board guessed at is worse than a board dropped.
    """
    named = dict(table)
    for stray in neighbours:
        if stray in named:
            continue
        rows = next((b for b in boards if any(stray in row for row in b)), None)
        if rows is None:
            continue
        unknown = sorted({char for row in rows for char in row} - set(named))
        settled = _settle_strays(rows, named, unknown, neighbours)
        if settled is not None:
            named.update(settled)
    return named


#: How many squares of one board may be read off it at once. Beyond this the
#: board is not one the cluster nearly explained but one it did not read, and
#: the combinations to try grow with it.
_MAX_STRAYS = 3

#: How many joint readings of a board's strays are tried before it is given up
#: on. Reached only by a board with three of them and a long ranking.
_MAX_TRIALS = 500


def _settle_strays(
    rows: Sequence[str],
    named: dict[str, str],
    unknown: Sequence[str],
    neighbours: dict[str, list[str]],
) -> dict[str, str] | None:
    """What the unexplained squares of one board are, or nothing.

    The candidates for each are the believed characters it stands nearest, in
    that order and one per kind — two characters of the same kind are the same
    reading of the board, and trying both only doubles the work.
    """
    from itertools import product

    if not unknown or len(unknown) > _MAX_STRAYS:
        return None
    ranked = []
    for stray in unknown:
        kinds: list[str] = []
        for other in neighbours.get(stray, ()):
            kind = named.get(other)
            if kind is not None and kind not in kinds:
                kinds.append(kind)
        if not kinds:
            return None
        ranked.append(list(enumerate(kinds)))
    tried = 0
    for combination in sorted(product(*ranked), key=lambda c: sum(at for at, _ in c)):
        tried += 1
        if tried > _MAX_TRIALS:
            return None
        reading = {stray: kind for stray, (_, kind) in zip(unknown, combination)}
        if _stands(rows, {**named, **reading}):
            return reading
    return None


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


#: The six kinds of piece, in the order a table is written for them.
KINDS = "kqrbnp"

#: How many pieces of a kind a side may hold, counting promotions: one queen
#: and two of everything else to begin with, and eight pawns that can each
#: become any of them.
_AT_MOST = {"k": 1, "q": 9, "r": 10, "b": 10, "n": 10, "p": 8}

#: How many pawns a side begins with, and so how many promotions it can have
#: made: a board holding three rooks and eight pawns never happened.
_PAWNS = 8


def settle(
    boards: Sequence[Sequence[str]],
    twins: Sequence[tuple[str, str]],
    empty: str,
) -> list[dict[str, str]]:
    """Every table the positions themselves allow, the likeliest first.

    :func:`learn` names a character from a position the book's own moves
    reach. A book whose moves never reach a diagram — a book of puzzles, or one
    whose pages open in mid-score, which is the very thing a diagram would fix
    — gives it nothing to learn from. This asks the boards instead, the way
    :func:`figurines.settle` asks the board which character is which piece.

    What makes it tractable is that the characters come **in twins**: the same
    piece in the two colours, which `pictures` finds by their silhouette (the
    drawing is the same; only the fill differs). Six twins onto six kinds of
    piece is 720 arrangements rather than the 479 million of twelve characters
    onto twelve pieces, and each arrangement is then either way round.

    Which way round is left to the boards and, after them, to the moves: a
    position with the colours exchanged is still a legal position, so nothing
    static can tell one from the other. What is assumed is only that the book
    draws its two colours the same way throughout, which is a statement about
    a printing press and not about chess.

    The tables come back ordered by how many of the boards they leave legal,
    and there will usually be several at the top — swapping a knight for a
    bishop leaves every position legal. The caller breaks the tie by reading
    the book with each of them.
    """
    positions = [rows for rows in boards]
    ranked: list[tuple[int, dict[str, str]]] = []
    for order in permutations(KINDS):
        for flipped in (False, True):
            table = {empty: "."}
            for (first, second), kind in zip(twins, order):
                white, black = (second, first) if flipped else (first, second)
                table[white] = kind.upper()
                table[black] = kind
            ranked.append((sum(_stands(rows, table) for rows in positions), table))
    if not ranked:
        return []
    best = max(score for score, _ in ranked)
    if best == 0:
        # Not one board came out a position anybody could have reached, under
        # any arrangement — which on a book whose boards are read cleanly does
        # not happen, and on one whose boards each carry a character no twin
        # covers is all it can say. A table nothing supports is not a table.
        return []
    standing = [table for score, table in ranked if score == best]
    seen = Counter(char for rows in positions for row in rows for char in row)
    return sorted(standing, key=lambda table: _how_many_of_each(table, seen, len(positions)))


#: How many of a piece a middlegame board carries, on average. Rooks are the
#: pieces a game keeps longest and bishops the ones it spends, and that is the
#: whole of what this is for: legality cannot tell a rook from a bishop — swap
#: them and every position is still a position — and neither can the moves,
#: where the book prints too few of them to reach one. What can is the count.
#: On SuperAttaquant's thirteen boards the two characters this names rooks
#: stand on every board, 25 and 23 times; the two it names bishops stand on ten
#: and eleven, 14 and 16 times. The right table and the one with the rooks and
#: bishops exchanged read the book equally well — 13 clean moves each — and
#: this is what separates them.
_HOW_MANY = {"k": 1.0, "q": 0.7, "r": 1.8, "b": 1.2, "n": 1.2, "p": 6.5}


def _how_many_of_each(table: dict[str, str], seen: Counter, boards: int) -> float:
    """How far this table's pieces stand from the number a board carries."""
    held = Counter()
    for char, kind in table.items():
        if kind != ".":
            held[kind.lower()] += seen.get(char, 0)
    return sum(
        abs(held[kind] / max(boards, 1) / 2 - expected)
        for kind, expected in _HOW_MANY.items()
    )


def _stands(rows: Sequence[str], table: dict[str, str]) -> bool:
    """Whether these rows, read with `table`, are a position that can happen.

    A board that cannot be read at all — a character no twin covers — counts
    against no table in particular, since every table is missing the same
    character; it simply says nothing.
    """
    import chess

    board_fen = decode(tuple(rows), table)
    if board_fen is None:
        return False
    counts = Counter(board_fen)
    for side in (str.upper, str.lower):
        held = {kind: counts.get(side(kind), 0) for kind in KINDS}
        if any(held[kind] > _AT_MOST[kind] for kind in KINDS):
            return False
        # Every piece beyond the ones a side begins with came from a pawn, and
        # it had only eight. `python-chess` does not check this and it is what
        # separates a character read as a rook from the same one read as a
        # pawn: eight rooks is a position nobody ever reached.
        promoted = sum(max(0, held[kind] - (1 if kind == "q" else 2)) for kind in "qrbn")
        if promoted + held["p"] > _PAWNS:
            return False
    return any(
        chess.Board(f"{board_fen} {colour} - - 0 1").is_valid() for colour in ("w", "b")
    )
