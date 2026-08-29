"""Steps 3b and 4 — build the move tree and validate it against the rules.

The tokeniser yields a flat sequence; this module gives it structure. Moves
become nodes linked by `parent_id`, parentheses open variations that branch
from the position *before* the move they replace, and prose attaches to the
move it follows.

Every move is played on a `python-chess` board as it is read. A move that does
not parse is not discarded straight away: it is compared against the legal
moves of the position under an edit distance that treats classic OCR
confusions (`0`/`O`, `1`/`l`, `8`/`B`) as near-free. That turns most scanning
noise into an `uncertain` move with a usable FEN, instead of a hole in the line.
"""

from __future__ import annotations

import re
import dataclasses
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import chess

from . import diagrams
from .extract import BBox
from .tokenize import Token

#: Character pairs a scanner routinely confuses. Substituting one for the
#: other costs half of a normal substitution.
_CONFUSABLE_PAIRS = frozenset(
    frozenset(pair)
    for pair in (
        ("0", "O"), ("0", "o"), ("O", "o"),
        ("1", "l"), ("1", "I"), ("l", "I"),
        ("8", "B"), ("5", "S"), ("2", "Z"),
        ("6", "b"), ("9", "g"),
    )
)

#: A repair is accepted below this total edit cost. One confusable swap costs
#: 0.5, so only look-alike substitutions get through.
#:
#: It is tempting to allow 1.0 and repair any single wrong character, which
#: catches far more. It is also how a scanning error becomes a legal but wrong
#: move: squares differ by one character all the time, so `Qh9` would silently
#: become `Qh5` and `Nc6` would become `Nc3`, corrupting every FEN further down
#: the line under nothing worse than an `uncertain` label. A move that cannot
#: be read from its shape alone is better reported as `broken`, where the app
#: shows it in red and the user settles it against the printed page.
_MAX_REPAIR_COST = 0.5

#: How far from the number it printed a citation's position may be looked for,
#: in plies, and in whole moves only. The two counts drift by a whole move at
#: a time: the parser's advances a ply for every move it managed to read, so
#: one move it could not read leaves it a move behind the book for the rest of
#: the game. One move of drift is what the corpus has — 69 citations re-placed
#: over six books, 36 of them on Markos. Four was measured and is worse
#: (Grivas 162 clean to 156, Tactics 102 to 99, against three more on Sakaev):
#: two moves of drift is rare, and the wider net only reaches citations that
#: were already standing where they belonged.
_CITATION_SPAN = 2

#: Confidence given to an ambiguity settled by a character the glyph pass
#: destroyed. Below the 0.75 of a look-alike repair on purpose: that repair
#: reads a character that is still on the page, this one leans on a character
#: that is gone, recovered from what a figurine was written over — which also
#: holds the scanner's guess at the symbol, and that guess can contain a file
#: letter by accident.
_CONSUMED_DISAMBIGUATION_CONFIDENCE = 0.6

#: Confidence given to a move whose piece symbol was never restored and which
#: only one piece could legally have made. Lower again than the two repairs
#: above: they both read something the page still carries, while this reads
#: nothing at all — the piece is named by the position, and the position is
#: only as good as every move that built it.
_LOST_SYMBOL_CONFIDENCE = 0.5

#: The pieces a lost symbol could have been. The pawn is deliberately absent:
#: the wreck on the page *is* a piece symbol, so reading the token as the pawn
#: move it spells is the very mistake that scored `Na6` as `a6`, ok, at full
#: confidence.
_LOST_SYMBOL_PIECES = ("K", "Q", "R", "B", "N")

#: A piece letter the glyph pass wrote back, standing inside the wreck around
#: it. Written against SAN letters: `parse` reads a translated token.
_RESTORED_PIECE = re.compile(r"[KQRBN]")

#: A piece, a digit where the file belongs, and the rank. No notation writes a
#: piece and two digits, so the first of them is the wreck of the file letter;
#: the rank is what survived. `tokenize` emits these so the reader gets a box
#: on the move whichever way it settles.
#:
#: The digit is optional because the file sometimes leaves no character at
#: all: `28.♔g1` arrives as `28.♔1`. That reads the same way — the piece and
#: the rank are what the page still says, and the board is asked for the
#: file — but it is a shape prose makes too, so `tokenize` only emits it
#: where a move number announces the move.
_FILE_READ_AS_A_DIGIT = re.compile(r"^([KQRBN])[1-8]?([1-8])$")

#: The characters a SAN disambiguator can be: an origin file or an origin rank.
_DISAMBIGUATION_CHARS = frozenset("abcdefgh12345678")

#: Comments longer than this are truncated; a runaway match usually means the
#: tokeniser swallowed a whole page of prose.
_MAX_COMMENT_LENGTH = 600

_TRAILING_ANNOTATION = re.compile(r"[!?]+$")

#: What a book's typography has to show before its weight is read as marking
#: the game score: both weights present among its move numbers, neither of
#: them a handful. A book setting everything in one weight — every scan, whose text
#: layer is the OCR's own and carries none — has nothing to say here, and one
#: where all but a few moves are bold is marking something else.
_MARKED_SHARE = 0.10
_MARKED_MINIMUM = 40


#: How far from the score's own count the number that opened an aside may
#: stand before the aside can no longer be that score. Zero is the ordinary
#: case — the number named the ply the game was waiting for — and one is the
#: game that has itself lost a move to a number the scan destroyed, which is
#: Boussole page 66. Beyond that a number is citing analysis of what is still
#: to come, and where such a citation ends says nothing about the game.
_ASIDE_REACH = 1


def weight_marks_the_line(tokens: Iterable[Token]) -> bool:
    """Whether this book sets its game score in a different weight from its analysis.

    Asked of the move numbers alone, because they are what the placement reads
    and what a scan's ink can be measured on: a figurine is a dense drawing,
    and the moves carrying one overlap between the weights.
    """
    weights = [token.bold for token in tokens if token.kind == "move_number"]
    if len(weights) < _MARKED_MINIMUM:
        return False
    bold = sum(weights)
    return min(bold, len(weights) - bold) >= _MARKED_SHARE * len(weights)


#: The check and mate marks. Stripped from both sides before a printed move is
#: compared to a legal one: the position decides them, not the reader, so a
#: book that prints `Nxc3` for `Nxc3+` has made no error to repair.
_CHECK_MARK = re.compile(r"[+#]+$")

#: A SAN piece move, with the disambiguation it may or may not carry. Only
#: piece moves reach the ambiguity path: a pawn move names its origin file
#: whenever it captures, and cannot be ambiguous otherwise.
_PIECE_MOVE = re.compile(
    r"^(?P<piece>[KQRBN])(?P<from_file>[a-h])?(?P<from_rank>[1-8])?x?"
    r"(?P<to>[a-h][1-8])[+#]?$"
)


@dataclass
class MoveNode:
    id: str
    game_id: str
    parent_id: str | None
    san: str
    uci: str | None
    fen: str | None
    ply: int
    page: int
    bbox: BBox
    variation_index: int
    comment: str | None = None
    confidence: float = 1.0
    status: str = "ok"
    repair: dict[str, str] | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "game_id": self.game_id,
            "parent_id": self.parent_id,
            "san": self.san,
            "uci": self.uci,
            "fen": self.fen,
            "ply": self.ply,
            "page": self.page,
            "bbox": self.bbox.to_json(),
            "variation_index": self.variation_index,
            "comment": self.comment,
            "confidence": round(self.confidence, 3),
            "status": self.status,
        }
        if self.repair is not None:
            payload["repair"] = self.repair
        return payload


@dataclass
class Game:
    id: str
    title: str | None
    initial_fen: str
    root_move_id: str | None
    page_start: int
    #: False when the book never printed where this game starts: a score
    #: resuming after a result, or a run of pages opening in mid-game with no
    #: diagram to seed it. `initial_fen` is then a placeholder, the moves are
    #: read for their boxes alone, and none of them is scored.
    position_known: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "initial_fen": self.initial_fen,
            "root_move_id": self.root_move_id,
            "page_start": self.page_start,
            "position_known": self.position_known,
        }


@dataclass
class ParseResult:
    games: list[Game] = field(default_factory=list)
    moves: list[MoveNode] = field(default_factory=list)
    #: Move-shaped tokens rejected before validation, kept for diagnostics.
    skipped: list[dict[str, Any]] = field(default_factory=list)
    #: One entry per move whose SAN named a piece and a square two pieces could
    #: legally reach. Diagnostics, not contract: it never reaches `moves.json`.
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    #: One entry per diagram met, and what it did: confirmed the board the
    #: parser had reached, corrected it, seeded a game that had no starting
    #: position, or could not be read. See `diagrams.py`.
    diagram_checks: list[dict[str, Any]] = field(default_factory=list)
    #: Moves a diagram below them proved wrong: they were legal, so nothing
    #: broke, but the position they left was not the one the book printed.
    contradicted: list[str] = field(default_factory=list)
    #: Moves standing on a main line whose count no longer matches the book's
    #: own numbering. Nothing is illegal there and no diagram need contradict
    #: them: the line simply lost a move it could not read, so it is a move
    #: behind the page, and every position it reaches after that is one the
    #: book never printed. See `break_diagnosis`.
    drifted: list[str] = field(default_factory=list)
    #: Every position each game's main line passed through, in order. Read by
    #: `diagrams.learn`, which looks for the printed position on both sides of
    #: where the diagram was met: a parser reading a difficult book is as often
    #: behind the page as ahead of it.
    main_lines: dict[str, list[str]] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "games": len(self.games),
            "moves": len(self.moves),
            "ok": sum(1 for m in self.moves if m.status == "ok"),
            "uncertain": sum(1 for m in self.moves if m.status == "uncertain"),
            "broken": sum(1 for m in self.moves if m.status == "broken"),
            "skipped": len(self.skipped),
            "ambiguous": len(self.ambiguities),
        }

    def ambiguity_diagnosis(self) -> dict[str, Any]:
        """Where the ambiguities of this book come from.

        A correctly typeset book read on a correct board should produce almost
        none. `python-chess` already excludes the moves of a pinned piece from
        `legal_moves`, so the usual reason a book omits a disambiguator — only
        one of the two pieces can legally go there — never reaches this path.
        When an ambiguity does appear, something upstream is wrong, and this
        counts which of the two candidates it is:

        - `downstream_of_repair`: an earlier move in the same line was accepted
          after a repair, so the board may not be the book's. The ambiguity is
          then evidence *against that repair*, and resolving it — by lookahead
          or otherwise — would launder a wrong position into a plausible one.
        - `clean_line`: no repair above it. The board is as good as this
          pipeline can make it, and the token itself is what lost the letter.

        `settled_from_consumed` counts those the glyph pass could answer, which
        are `clean_line` cases by construction. A book whose ambiguities are
        mostly `downstream_of_repair` is telling you `_MAX_REPAIR_COST` is too
        generous for it, not that it needs a cleverer disambiguator.
        """
        downstream = [a for a in self.ambiguities if a["upstream_repair_distance"] is not None]
        return {
            "total": len(self.ambiguities),
            "downstream_of_repair": len(downstream),
            "clean_line": len(self.ambiguities) - len(downstream),
            "settled_from_consumed": sum(
                1 for a in self.ambiguities if a["settled_by"] == "consumed"
            ),
            "nearest_repair_plies": sorted(a["upstream_repair_distance"] for a in downstream),
        }

    def break_diagnosis(self) -> dict[str, int]:
        """How much of this book's reading stands below a broken move.

        When a move finds no legal reading the line is left on the position
        before it, and the score goes on being read there. Everything under
        that point is played on a board the book never reached — including the
        moves that come out legal, which are then recorded `ok` at full
        confidence while naming a position that is not the book's. Counting
        them with the sound ones inflates the measurement, and the inflation
        grows with the length of the line rather than with the quality of the
        reading.

        So `broken` is split into the lines that actually died (`first_breaks`,
        one per line, the number worth working on) and what merely followed
        them (`cascade`); and `ok` into `clean`, the moves nothing stands
        against, `below_break`, `contradicted` — the moves a diagram further
        down proved wrong without any of them being illegal — and `drifted`.
        **`clean` is the figure to compare between two runs.**

        `drifted` is the same inflation one level up, and it took a corpus to
        see. A line that loses a move it cannot read goes on reading the moves
        below it, in order and legally, a move behind the page: `14 f4!` is
        played as White's thirteenth, every position after it is one the book
        never printed, and nothing marks it — no move is illegal, so there is
        no break, and a diagram only catches it where the book happens to
        print one. What does mark it is the book's own numbering, which the
        line stops agreeing with the moment the move is lost. Half of Grivas'
        `clean` stood on such a line, and four of SuperAttaquant's fourteen.
        """
        by_id = {m.id: m for m in self.moves}
        unscored = {game.id for game in self.games if not game.position_known}

        def below_a_break(move: MoveNode) -> bool:
            parent = move.parent_id
            while parent is not None:
                if by_id[parent].status == "broken":
                    return True
                parent = by_id[parent].parent_id
            return False

        contradicted = set(self.contradicted)
        drifted = set(self.drifted)
        tally = dict(
            first_breaks=0, cascade=0, clean=0, below_break=0, contradicted=0, drifted=0,
            unscored=sum(1 for m in self.moves if m.game_id in unscored),
        )
        for move in self.moves:
            if move.game_id in unscored:
                # Never played on a board the book printed: counting these
                # would say the pipeline failed where it was never asked.
                continue
            tainted = below_a_break(move)
            if move.status == "broken":
                tally["cascade" if tainted else "first_breaks"] += 1
            elif move.status == "ok":
                if tainted:
                    tally["below_break"] += 1
                elif move.id in contradicted:
                    # A diagram below this move printed a different position, so
                    # one of the moves between the last agreement and there is
                    # wrong. Legality never noticed — that is what makes this
                    # the second way `ok` lies, after the break cascade.
                    tally["contradicted"] += 1
                elif move.id in drifted:
                    # The book's numbering and this line's count have parted:
                    # a move was lost, so the board is behind the page and no
                    # position under here is the one that was printed.
                    tally["drifted"] += 1
                else:
                    tally["clean"] += 1
        return tally

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "games": [g.to_json() for g in self.games],
            "moves": [m.to_json() for m in self.moves],
        }


@dataclass
class _Level:
    """One depth of the variation stack."""

    board: chess.Board
    parent_id: str | None
    #: The move most recently played at this depth, and the position that
    #: preceded it. A `(` right after it branches from that position.
    last_move_id: str | None = None
    board_before_last: chess.Board | None = None
    parent_of_last: str | None = None
    moves_allowed: int = 0
    #: True when a `(` opened this level. Brackets are explicit and are trusted
    #: over the numbering heuristic below, which only guesses.
    from_bracket: bool = False
    #: The ply of the last number read into this level. An aside never goes
    #: backwards in its own numbering, so a number behind this one is not this
    #: aside carrying on.
    declared_at: int | None = None
    #: Position and parent before each half-move played at *this* depth,
    #: keyed by ply — the same record `main_history` keeps for the game, kept
    #: by an aside for itself. A book cites two alternative variations at one
    #: number, and the second names a ply the first has passed and the game
    #: has not reached.
    history: dict[int, tuple[chess.Board, str | None]] = field(default_factory=dict)
    #: True once a move at this depth could not be read: the board no longer
    #: follows the book, so what the same number still announces is read for
    #: its box and nothing else. Cleared by the next number, which is where
    #: the book itself starts the line again.
    board_lost: bool = False
    #: The move this level hung from when it opened, and the ply the number
    #: that opened it named. An aside the score turns out to have run into is
    #: taken back onto the game, and these two say which aside that can be:
    #: one that branched at the game's own tip, and whose number named the ply
    #: the game itself was waiting for.
    opened_at: str | None = None
    opened_ply: int | None = None
    #: Every position played at this depth, in order — what `main_lines` keeps
    #: for the game, kept by an aside for itself, so that an aside taken back
    #: brings its positions with it and the diagrams can still be read against
    #: the line.
    line: list[str] = field(default_factory=list)


#: The last word of a comment, when the comment really ends in one: letters
#: only, no digit, no capital after the first — and no `:` or `\` or `'`, the
#: marks `tokenize` reads as the wreck of a piece symbol. What this excludes is
#: the debris a broken font leaves in the middle of a line of play — `exdS`,
#: `iBxe4`, `18Rd2`, `:tel` — which the tokeniser can only emit as prose and
#: which is not a comment at all: the moves are still running beside it.
_PROSE_TAIL = re.compile(r"[A-Za-z][a-z]*[.,;:!?)\"\u201d\u00bb]*\s*$")


def _ends_in_a_word(text: str) -> bool:
    """Whether `text` reads as prose rather than as the wreck of a move."""
    tail = text.split()[-1] if text.split() else ""
    return bool(_PROSE_TAIL.match(tail))


#: One side of a game header: a capitalised name, or several of them, with the
#: initials a book puts in front of one — "Ki. Georgiev", "J.C. Fernandez",
#: "I. Zaitsev", three of SuperAttaquant's sixteen headings. Written without
#: `\w` on purpose — a scanner leaves private-use characters in the text, and
#: those must not read as letters.
_HEADER_NAME = r"(?:[A-Z]\.\s*){0,3}[A-Z][^\W\d_]*[a-z][^\W\d_]*\.?"

#: The header a book prints above a game: two sides joined by a dash, then
#: where it was played and the year. Anchored at the end of the text, because
#: what this is asked is whether the *next* thing on the page belongs to a new
#: game — a header in the middle of a paragraph is a citation, not a heading.
_GAME_HEADER = re.compile(
    rf"{_HEADER_NAME}(?:\s+{_HEADER_NAME})*"
    r"\s*[-\u2010-\u2015]\s*"
    rf"{_HEADER_NAME}(?:\s+{_HEADER_NAME})*"
    r"[^.!?]{0,70}?\b(?:1[89]\d\d|20\d\d)$"
)


def _ends_in_a_game_header(text: str) -> bool:
    """Whether this prose closes with the heading of a new game.

    "Dominik Csiba - Jan Markos / Banska Stiavnica 2011" is the book saying it
    has finished with the game it was on. The year is what makes the test
    safe: two names joined by a dash is also how a book cites a game in
    passing, and a citation carries no date at the end of the line.
    """
    return bool(_GAME_HEADER.search(re.sub(r"\W+$", "", text)))


#: The same heading at the head of the prose rather than at its end. A book
#: may print the board first and name the game under it — SuperAttaquant does
#: it every time, "Anderssen - Zukertort / Barmen, 1869" set below the
#: position the score opens from — and then the heading that says a new game
#: begins arrives *after* the board that begins it.
_GAME_HEADER_FIRST = re.compile(
    r"^\W*"
    rf"{_HEADER_NAME}(?:\s+{_HEADER_NAME})*"
    r"\s*[-\u2010-\u2015]\s*"
    rf"{_HEADER_NAME}(?:\s+{_HEADER_NAME})*"
    r"[^.!?]{0,70}?\b(?:1[89]\d\d|20\d\d)\b"
)


def _opens_on_a_game_header(text: str) -> bool:
    """Whether this prose *begins* with the heading of a new game."""
    return bool(_GAME_HEADER_FIRST.match(text))


def _a_game_is_named_under(tokens: Sequence[Token], at: int) -> bool:
    """Whether the prose at `at` — printed straight after a board — names a game.

    The board comes first and the heading under it, which is the other way
    round from the book `_ends_in_a_game_header` was written for. Only the very
    next token is asked: a heading standing anywhere else on the page belongs
    to some other board.
    """
    after = tokens[at] if at < len(tokens) else None
    return after is not None and after.kind == "text" and _opens_on_a_game_header(after.text)


def _ply_of(number: int, is_black: bool) -> int:
    """The half-move a printed `12.` or `12...` announces. White's first is 0."""
    return 2 * (number - 1) + (1 if is_black else 0)


#: A move number above which the book is not numbering a move. Games do run
#: past a hundred moves and are still numbered normally; what stands above this
#: is a page number the layer put in the score's way, or a move number a scan
#: welded something onto.
_NUMBER_CEILING = 120


def _plays(fen: str, text: str) -> bool:
    """Whether this move can be played on this position, annotations and all."""
    try:
        chess.Board(fen).push_san(_TRAILING_ANNOTATION.sub("", text.strip()))
    except ValueError:
        return False
    return True


def _the_line_after(tokens: Sequence[Token], at: int, most: int = 6) -> list[str]:
    """The run of moves printed after this point, as far as the score runs.

    Move numbers and the annotations that decorate a move are read across;
    prose, a bracket or a result end the run, because past one of those the
    moves are no longer this line's.
    """
    out: list[str] = []
    for token in tokens[at:]:
        if token.kind == "move":
            out.append(token.text)
            if len(out) == most:
                break
        elif token.kind not in ("annotation", "move_number"):
            break
    return out


#: How many of the moves printed after an eaten ply have to play, in order,
#: before the move that was eaten is believed. Two is not enough — a black move
#: to the fifth rank rarely stops White pushing a pawn — and the line runs on
#: past the break for as long as the book keeps printing it.
_EATEN_LOOKAHEAD = 3


def _move_of_the_eaten_ply(
    board: chess.Board, rank: int, line: Sequence[str]
) -> str | None:
    """The move the welded number destroyed, named by the board.

    All the number kept of it is the rank it ended on — the `5` of `f5` in
    `519`. That names a dozen legal moves and one of them is the book's, and
    what tells them apart is the score itself: it goes on, so the right move is
    the one the moves printed after it can be played from. One move of that is
    not enough (`18.exd5 ? 19.d6` — the pawn pushes whatever Black did), so the
    line is followed as far as the book prints it, and the move that carries it
    furthest wins.

    Where two carry it equally far the move is **not** put back. A wrong move
    here would be worse than a missing one: it is played, it is legal, and
    every position below it is one the book never printed — which is the way
    `clean` lies, and this pipeline counts that as the failure it is.
    """
    if len(line) < _EATEN_LOOKAHEAD:
        return None
    wanted = rank - 1
    best, carried = [], 0
    for move in board.legal_moves:
        if chess.square_rank(move.to_square) != wanted:
            continue
        after = board.copy(stack=False)
        after.push(move)
        reached = 0
        for text in line:
            try:
                after.push_san(_TRAILING_ANNOTATION.sub("", text.strip()))
            except ValueError:
                break
            reached += 1
        if reached > carried:
            best, carried = [move], reached
        elif reached == carried:
            best.append(move)
    if carried < _EATEN_LOOKAHEAD or len(best) != 1:
        return None
    return board.san(best[0])


def _number_stripped_of_a_lost_move(
    number: int, is_black: bool, board: chess.Board
) -> tuple[int | None, int | None]:
    """The number under a digit the scan welded to the front of it.

    "18.exd5 f5 19.d6!" comes off SuperAttaquant's page as `exd5` and then the
    move number **519** — the `f` gone and the `5` of Black's move standing in
    front of the number that follows it. Ten of that book's numbers are of this
    shape (`228`, `418`, `322`, `621`, `818`), and each one takes the rest of
    its game: the ply it names is nowhere and every move below is read on a
    board that has stopped following the page.

    What settles it is the game's own count, and nothing else may: Tactics'
    twelve pages each print their page number where the score can reach it —
    170 to 181 — and stripping *those* to 70 and 81 would move a line that was
    right. So the digits come off only where what is left is the ply the game
    is waiting for, or the one after it: the move the welding destroyed is the
    ply in between. Where that is what happened the rank the number kept comes
    back with it, and `_move_of_the_eaten_ply` asks the board which move it was.
    """
    text = str(number)
    awaited = _ply_awaited(board)
    for cut in range(1, len(text)):
        candidate = int(text[cut:] or 0)
        if not candidate:
            continue
        named = _ply_of(candidate, is_black)
        if named == awaited:
            return candidate, None
        if named == awaited + 1:
            eaten = int(text[cut - 1])
            return candidate, (eaten if 1 <= eaten <= 8 else None)
    return None, None


def _ply_awaited(board: chess.Board) -> int:
    """The half-move this position is waiting for."""
    return 2 * (board.fullmove_number - 1) + (0 if board.turn == chess.WHITE else 1)


def parse_tokens(
    tokens: Iterable[Token],
    *,
    initial_fen: str = chess.STARTING_FEN,
    strict_numbering: bool = True,
    diagram_table: dict[str, str] | None = None,
    weighted: bool | None = None,
) -> ParseResult:
    """Assemble `tokens` into games of move nodes.

    With `strict_numbering` (the default), a move is only read when a move
    number has recently announced one, or when a variation's parentheses make
    the context unambiguous. Chess books are full of stray tokens that look
    like moves — figure captions, "diagram b4", page references — and the
    numbering is what separates them from real notation. Turn it off for a
    document that prints long unnumbered sequences.

    `weighted` says whether the book marks its game score with the weight of
    the type. It is read from the tokens themselves by default, which wants
    the whole book: the share of bold moves on any one page says more about
    that page than about the publisher.
    """
    result = ParseResult()
    tokens = list(tokens)
    #: Whether this book marks its game score with the weight of the type. It
    #: is a property of the whole book, not of a page: a page of pure score
    #: carries no plain move and a page of pure analysis no bold one.
    if weighted is None:
        weighted = weight_marks_the_line(tokens)
    #: Whether the moves carry a weight of their own, and not only the numbers.
    #: A typeset book gives both, free, from the span. A scan gives what
    #: `weight.mark` could measure, and that is the **numbers only**: a
    #: figurine is a dense drawing and the moves carrying one overlap between
    #: the weights, so nothing is read from them. Reading the rule below on a
    #: book like that makes analysis of the whole game score at a stroke —
    #: which is why both scans of the corpus refused their own ink until this
    #: was asked.
    moves_carry_the_weight = any(
        token.bold for token in tokens if token.kind == "move"
    )
    # Keyed by (game_id, parent_id): every game has its own root, so a bare
    # `None` parent would otherwise be shared across games and make the second
    # game's first move look like a variation of the first game's.
    child_counts: dict[tuple[str, str | None], int] = {}
    by_id: dict[str, MoveNode] = {}
    move_counter = 0
    game_counter = 0

    pending_title: str | None = None
    #: A position read from a diagram, waiting for the number printed under it
    #: to say whose move it is.
    pending_position: str | None = None
    #: Whether that diagram stood under the header of a new game, so the board
    #: it prints opens one rather than correcting the game still running.
    pending_opens_a_game = False
    #: Whether the prose last read closed with a game header. Cleared by the
    #: first move read after it: a heading announces what comes next, and once
    #: the score has started the announcement is spent.
    header_read = False
    #: Whether the main line has been sound since the game began: a diagram is
    #: only allowed to teach the font from a board that can be believed.
    line_sound = True
    #: The last main-line move a diagram agreed with. What follows it is what a
    #: later disagreement puts in doubt.
    agreed_at: str | None = None
    #: Whether the last thing read was a result. What follows one is commentary
    #: until a first move opens the next game.
    finished = False
    #: The game a result has just closed, and the line it closed on. A book
    #: often plays on past the result — "Black resigned due to 27...♔xe7
    #: 28 ♕f6+ ♔d7 29 ♕xc6+" — and those half-moves are the game's own, as
    #: Laurent put it, "comme si elle avait vraiment été jouée avant
    #: l'abandon". Read as a new game they have no starting position at all.
    over: tuple[Game, _Level, int | None] | None = None
    game: Game | None = None
    stack: list[_Level] = []
    #: Position and parent before each half-move of the game's main line,
    #: keyed by ply. A printed number that does not continue the line is
    #: branched from here, which gives the variation its true starting
    #: position rather than an approximation of one.
    main_history: dict[int, tuple[chess.Board, str | None]] = {}
    #: The position an aside offered just before the main line picked up
    #: again, and the move it hung from. A book cites two alternatives to the
    #: same move in one breath — "White can choose between 7 Na2 and 7 Nb1" —
    #: and the second one carries the number the main line is waiting for, so
    #: the aside is closed on it. Kept here so a move that turns out illegal
    #: in the main line can still be offered the board it was printed for.
    closed_aside: tuple[chess.Board, str | None] | None = None

    def start_game(page: int, from_diagram: str | None = None, position_known: bool = True) -> None:
        nonlocal game, game_counter, stack, pending_title, line_sound, agreed_at, finished
        nonlocal over
        game_counter += 1
        opening_fen = from_diagram or initial_fen
        game = Game(
            id=f"g{game_counter}",
            title=pending_title,
            initial_fen=opening_fen,
            root_move_id=None,
            page_start=page,
            position_known=position_known,
        )
        result.games.append(game)
        result.main_lines[game.id] = [chess.Board(opening_fen).board_fen()]
        stack = [_Level(board=chess.Board(opening_fen), parent_id=None)]
        asides.clear()
        pending_title = None
        line_sound = True
        agreed_at = None
        finished = False
        over = None
        main_history.clear()

    def _place_by_number(declared: int) -> None:
        """Send what follows to the line the printed number actually belongs to.

        Books interleave analysis with the game score in plain prose, with no
        bracket and no indent to mark it — "Another promising continuation is
        13...♘b6 14 g5", "Threatening 17...♘xc2". Read as the continuation,
        such a line is played on a position the book never reached and every
        move after it breaks.

        This is the reading for a book that gives nothing better. Where the
        publisher sets the score in its own weight, `_place_by_weight` reads
        that instead — which is every book of the corpus that was typeset
        rather than scanned.

        The number itself says so. `13...` announces Black's thirteenth, and a
        position knows which half-move it awaits; when the two disagree, this
        is not the continuation. That holds whichever way the number points —
        the examples above run backwards and forwards — which is why the
        direction of travel is the wrong thing to test.

        Brackets are explicit and are left alone: this only guesses, and only
        where the book gave nothing better.
        """
        # An aside catches the game up as soon as it has read as many plies as
        # the game has, and both are then waiting for the same number: "les
        # Blancs menacent 14.b4", one move on Boussole page 65, and `13...♗b6`
        # is what the game and the aside are both waiting for. What separates
        # them is the aside's own numbering, which never goes backwards — the
        # book cited White's fourteenth and is now printing Black's thirteenth.
        went_back = (
            stack[-1].declared_at is not None and declared < stack[-1].declared_at
        )
        # And where the aside lost the move its own number announced, the ply
        # after it is the aside carrying on and not the score picking up. The
        # test above is a board's disagreement with a number, and a move that
        # was never read makes that disagreement out of nothing: the aside
        # stands where its number left it, so the next ply is one away from it
        # whichever line the book is printing. SuperAttaquant page 198 cites
        # `21...♕b7 22.c6 ♖xa1!`, whose first move reaches the layer as a bare
        # `b7` — the queen's symbol destroyed and the move illegal. Its own
        # `22.` was the only evidence `resumes` had, the citation was played
        # as the game score, and the game's `22.♖xa8 ♕c6 23.♖fa1` was diverted
        # into an aside in its place; 54 moves died under that inversion.
        #
        # Only the ply straight after the aside's own number, which is the
        # citation continuing itself. Any wider and a score that really does
        # resume over a broken aside is held out of its own line: Boussole
        # loses two clean moves to the wider form and none to this one.
        lost_its_move = (
            stack[-1].declared_at is not None
            and _ply_awaited(stack[-1].board) == stack[-1].declared_at
            and declared == stack[-1].declared_at + 1
        )
        resumes = (
            len(stack) > 1
            and declared == _ply_awaited(stack[0].board)
            and (
                went_back
                or (declared != _ply_awaited(stack[-1].board) and not lost_its_move)
            )
        )
        if not resumes and declared == _ply_awaited(stack[-1].board):
            return
        nonlocal closed_aside
        closed_aside = None
        if resumes:
            # The main line resumes. A prose variation has no closing bracket,
            # so its end is only ever visible as the game picking up again.
            board_before = stack[-1].board_before_last
            closed_aside = (
                (board_before.copy(), stack[-1].parent_of_last)
                if board_before is not None
                and _ply_awaited(board_before) == declared
                else None
            )
            del stack[1:]
            return
        if any(level.from_bracket for level in stack):
            # Below a bracket the book was explicit, and the guessing above is
            # for where it gave nothing. Only the game picking up again is
            # believed there — a scan invents brackets, and one of them opened
            # in the middle of a Boussole comment holds the score of the game
            # hostage for the rest of the page.
            return
        if declared in main_history:
            board, parent = main_history[declared]
            # Replaces any prose variation in progress rather than nesting:
            # "15 Rhg1!? and 15 Qh3" are two alternatives to the same move, not
            # one inside the other.
            stack[1:] = [_Level(board=board.copy(), parent_id=parent)]

    def _open_the_bracket_on_the_right_side(declared: int) -> None:
        """A bracket branches before the move it follows — unless it says not.

        `(` opens a variation at the position *before* the move just played,
        which is what an alternative to that move needs. A bracket whose first
        number names the ply the game is waiting for is not an alternative to
        the move, but a continuation of it: "6...h6, and White is already
        obliged (7.♗xf6 ♕xf6 8.♘d5)". Branched a move too early it is played
        for the wrong colour, and the whole variation dies on its first move.

        Only before the bracket has read anything, and only where its own
        board cannot be what the number names.
        """
        if len(stack) < 2:
            return
        level, parent = stack[-1], stack[-2]
        if not level.from_bracket or level.last_move_id is not None:
            return
        if declared == _ply_awaited(level.board):
            return
        if declared != _ply_awaited(parent.board):
            return
        level.board = parent.board.copy()
        level.parent_id = parent.last_move_id or parent.parent_id

    def _take_the_score_back(declared: int) -> bool:
        """Take back an aside the score ran into when a mark went missing.

        A weight mark is a measurement, and a measurement misses. Where the
        score's own number came out plain — the ink of `17...` eroding away,
        the box of a number the OCR half-destroyed — `_place_by_weight` reads
        what follows as analysis and copies the game's board to play it on.
        The game then stands still while the book goes on, and every number
        below is answered on a position two, four, ten plies behind the page.
        One missed mark used to cost the rest of the page.

        The number now printed in the score's own weight is what says so, and
        says it exactly: it names a ply the game has not reached, and one of
        the asides opened since has. That aside is the score. It branched at
        the game's own tip and its number named the ply the game was waiting
        for, which is what separates it from a citation of analysis further
        on; where two of them could answer, the one whose number stood nearest
        the game's own count is taken, and a tie is refused rather than
        guessed.

        Nothing is replayed: the aside was a copy of the game's board and its
        moves already hang from the game's last move, so taking it back is
        taking its level for the game's own.
        """
        if declared == _ply_awaited(stack[0].board):
            return False
        tip, awaited = stack[0].parent_id, _ply_awaited(stack[0].board)
        found = [
            level
            for level in asides + stack[1:2]
            if level.last_move_id is not None
            and level.opened_at == tip
            and level.opened_ply is not None
            and _ply_awaited(level.board) == declared
        ]
        nearest = min((abs(level.opened_ply - awaited) for level in found), default=99)
        if nearest > _ASIDE_REACH:
            return False
        found = [level for level in found if abs(level.opened_ply - awaited) == nearest]
        if len(found) != 1:
            return False
        nonlocal closed_aside
        taken = found[0]
        main_history.update(taken.history)
        result.main_lines.setdefault(game.id, []).extend(taken.line)
        stack[0] = taken
        closed_aside = None
        del stack[1:]
        asides.clear()
        return True

    def _resume_the_score(declared: int) -> None:
        """End whatever analysis is open: a number in the score's own weight.

        Split out of `_place_by_weight` and called before the test for a new
        game, because a game only ever opens at the top of the stack. A book
        whose analysis runs to the foot of one page and whose next game opens
        the one after — which is every second page of a puzzle book — would
        otherwise never start it, and read a hundred pages as one game.
        """
        if len(stack) < 2 or any(level.from_bracket for level in stack):
            return
        nonlocal closed_aside
        if _take_the_score_back(declared):
            return
        # A prose variation has no closing bracket: the end of one is only
        # ever visible as the game picking up again.
        board_before = stack[-1].board_before_last
        closed_aside = (
            (board_before.copy(), stack[-1].parent_of_last)
            if board_before is not None and _ply_awaited(board_before) == declared
            else None
        )
        del stack[1:]

    def _place_by_weight(bold: bool, declared: int) -> None:
        """Send what follows to the line the book's own typesetting names.

        Where a publisher sets the game score bold and the analysis around it
        plain, the weight of the number is a fact where `_place_by_number` has
        only an inference — and it says the thing the arithmetic cannot see.
        "The main continuations are the classical 6...e6 and the trendy
        6...Nbd7", printed exactly where the game awaits Black's sixth, agrees
        with the position on every count and is not the continuation; the
        number that resumes the score after two pages of analysis disagrees
        with it and is.

        Brackets still win, as they do for the arithmetic: this reads what the
        book prints outside them.
        """
        if bold or any(level.from_bracket for level in stack):
            # A bold number has already had `_resume_the_score`, above.
            return
        nonlocal closed_aside
        if len(stack) > 1 and declared == _ply_awaited(stack[-1].board):
            # The variation in progress is waiting for exactly this number, so
            # this continues it. Without the test, an analysis two plies long
            # restarts at every number it prints — "3.Qh5+ Kg8 4.Ng5" branched
            # afresh at the `4`, from a board its own first move had left.
            return
        closed_aside = None
        # Analysis. It is printed beside the game and never on it, whatever
        # the number says; the number only says *where* beside. Where it names
        # a ply the score has played, the variation starts from the position
        # the book branched it at; where it names one the score has not
        # reached — analysis of a move still to come — there is no such
        # position, and the current one is the closest the book has printed.
        board, parent = main_history.get(declared) or (stack[0].board, stack[0].parent_id)
        # Kept rather than dropped: a mark the ink measurement missed sends the
        # score down here, and the number that resumes it says which of these
        # was the game. See `_take_the_score_back`.
        asides.extend(stack[1:])
        stack[1:] = [_Level(
            board=board.copy(), parent_id=parent, opened_at=parent, opened_ply=declared
        )]

    #: Asides `_place_by_weight` has opened since the score was last resumed.
    asides: list[_Level] = []
    last_declared: int | None = None
    last_licence = 2
    adrift: set[str] = set()
    #: The kind of the token before this one. A move printed hard against the
    #: move in front of it is read even where the licence is spent: what the
    #: licence keeps out is the commentary naming a square, and prose is what
    #: stands in front of that.
    last_kind: str | None = None
    at = 0
    while at < len(tokens):
        token = tokens[at]
        at += 1
        kind_before, last_kind = last_kind, token.kind
        if token.kind not in ("text", "diagram", "annotation"):
            # A heading announces the game printed under it, and the first
            # thing read from that game spends the announcement.
            header_read = False
        if token.kind == "text":
            level = stack[-1] if stack else None
            if level is not None and level.last_move_id is not None:
                # The last move of *this* depth, not the last one appended: a
                # comment after `)` belongs to the move before the variation.
                _append_comment(by_id[level.last_move_id], token.text)
            else:
                # Prose before any move: the best candidate for a game heading.
                pending_title = token.text[:120]
            if level is not None and _ends_in_a_word(token.text):
                # A number announces the moves printed *beside* it, and prose
                # ends what it announced. Commentary names squares constantly —
                # "the pawn at d5", "White intends e2-e3", "his bishop on g2" —
                # and every one of them is shaped exactly like a move. Read as
                # the reply the number was still waiting for, such a word is
                # played on the board and the line is lost from there on,
                # whether it turns out illegal (a break) or merely legal, which
                # is worse: a wrong position scored `ok`. The book reprints the
                # number when the score resumes after a comment, so nothing
                # real is lost by letting the licence expire here.
                level.moves_allowed = 0
            header_read = _ends_in_a_game_header(token.text)
            continue

        if token.kind == "diagram":
            rows = tuple(token.text.split("/"))
            names_a_game = _a_game_is_named_under(tokens, at)
            reached = stack[0].board.board_fen() if stack else None
            # Where in its game's main line this diagram was met. The
            # positions around that point are what `diagrams.learn` searches:
            # a diagram printed where the score had drifted is still a diagram
            # of a position the line passes through, a few plies either side.
            printed = diagrams.decode(rows, diagram_table) if diagram_table else None
            if printed is None:
                verdict = "unread" if diagram_table is None else "unreadable"
            elif not stack:
                verdict = "seeds"
            elif printed == reached:
                verdict = "confirms"
            elif header_read or names_a_game:
                # The book has printed the heading of another game beside this
                # board, so the board is that game's opening position and not a
                # correction to the line above it. Read as a correction it
                # condemns the moves it stands under: Markos page 89 prints the
                # diagram of Csiba - Markos below the score of Prusikin -
                # Petrik, and eight sound moves of the latter were blamed on
                # it. The heading may stand on either side — Markos prints it
                # above the board and SuperAttaquant under it.
                verdict = "seeds"
            else:
                verdict = "corrects"
            if verdict == "confirms":
                agreed_at = stack[0].parent_id
            if verdict == "corrects":
                # Everything played since the last agreement led away from the
                # position the book has just printed. None of it broke, so only
                # the diagram can say so.
                suspect = stack[0].parent_id
                while suspect is not None and suspect != agreed_at:
                    result.contradicted.append(suspect)
                    suspect = by_id[suspect].parent_id
                agreed_at = None
            if verdict in ("seeds", "corrects") and not any(
                level.from_bracket for level in stack
            ):
                # A diagram is a figure the text flows around, so it can fall
                # in the middle of a bracketed variation — and the position it
                # prints is the game's, not the variation's. Seeding on it
                # there would put the whole stack back on the main line while
                # the variation is still running: on Grivas page 20 a diagram
                # inside `(13...♘xg3` took the next page's `14 fxg3 ♗xe5 15
                # ♘xe5!!` onto the game, where 185 moves died. The diagram is
                # still read and still judged; it just does not move a line
                # nobody is on.
                pending_position = printed
                pending_opens_a_game = header_read or names_a_game
            result.diagram_checks.append(
                {
                    "page": token.page,
                    "rows": list(rows),
                    # The board the parser had reached, kept whatever the
                    # verdict: this is what `diagrams.learn` reads back, and
                    # `sound` is what says it may.
                    "reached": reached,
                    "game": game.id if game is not None else None,
                    "index": len(result.main_lines.get(game.id, [])) if game is not None else 0,
                    "printed": printed,
                    "sound": bool(stack) and line_sound,
                    "verdict": verdict,
                }
            )
            continue

        if token.kind == "move_number":
            number = int(re.match(r"\d+", token.text).group())
            # Two dots or three: a scan loses one as readily as it loses
            # anything, and only a black number carries more than one.
            is_black_only = token.text.count(".") > 1
            if number > _NUMBER_CEILING and stack:
                stripped, eaten = _number_stripped_of_a_lost_move(
                    number, is_black_only, stack[-1].board
                )
                if stripped is not None:
                    number = stripped
                    if eaten is not None and not stack[-1].board_lost:
                        # The digit the number kept is the rank of the move it
                        # destroyed, and the board says which move that was.
                        put_back = _move_of_the_eaten_ply(
                            stack[-1].board, eaten, _the_line_after(tokens, at)
                        )
                        if put_back is not None:
                            tokens.insert(at, dataclasses.replace(
                                token, kind="move", text=put_back, raw=token.text,
                                consumed="", lost_symbol="", lost_piece="",
                            ))
                            stack[-1].moves_allowed = max(stack[-1].moves_allowed, 1)
                            last_kind = "move_number"
            seeded = None
            opens_on_a_header = False
            if pending_position is not None:
                # The diagram gave the placement and this number gives the rest
                # of the position: whose move it is, and which move it is.
                seeded = diagrams.initial_fen(
                    pending_position, number=number, black_to_move=is_black_only
                )
                line = _the_line_after(tokens, at)
                if line and not _plays(seeded, line[0]):
                    # The number under a board says whose move it is, and a
                    # scan loses an ellipsis as readily as anything else: `24`
                    # for `24...`. Where the move printed after it cannot be
                    # played by the side the number named and can be played by
                    # the other, the board is believed over the number. Only
                    # there — the reading is already broken when this fires,
                    # so it can take nothing away. Two of SuperAttaquant's
                    # seeded games open on such a number.
                    other = diagrams.initial_fen(
                        pending_position, number=number, black_to_move=not is_black_only
                    )
                    if _plays(other, line[0]):
                        seeded, is_black_only = other, not is_black_only
                pending_position = None
                opens_on_a_header, pending_opens_a_game = pending_opens_a_game, False
                if not chess.Board(seeded).is_valid():
                    # The board decoded, and it is not a position: the side the
                    # number does *not* name stands in check, or a side holds
                    # pieces nobody could have. A board a book draws is read by
                    # clustering its squares, and where the clustering merges
                    # two pieces the table still decodes — into a board the
                    # book never printed. Seeding a game on one of those is
                    # worse than leaving the game unplaced: every move after it
                    # is illegal and the reader is shown a position that never
                    # existed. SuperAttaquant reads eleven boards over its
                    # twelve pages, decodes two, and both put a king in check.
                    seeded = None
            if seeded is not None:
                # Where the book put the pieces back is an agreement, whatever
                # the verdict that got it there: what follows is played on the
                # printed board, so a later disagreement is about that and
                # cannot reach above it. Without this the second correcting
                # diagram of a game blamed it back to its first move — the
                # eleven opening moves of Grivas-Siebrecht, `1 d4 d5 2 c4 c6`,
                # marked wrong by a board a page away, with the diagram beside
                # them confirming they were right.
                agreed_at = stack[0].parent_id if stack else None
                if game is None or not game.position_known or opens_on_a_header:
                    # A game the book never printed the start of is not a game
                    # this board belongs to. SuperAttaquant opens eleven of its
                    # fourteen examples in mid-score, each under a drawn board
                    # — and read as a correction to whatever was still running,
                    # the board reseeds a game that stays unscored to the end,
                    # taking its own example's moves with it.
                    start_game(token.page, from_diagram=seeded)
                else:
                    # The book has just said where the pieces are, so the line
                    # continues from there rather than from wherever the score
                    # had drifted to. The moves already read keep their place in
                    # the tree; what follows descends from the last of them.
                    stack[:] = [_Level(board=chess.Board(seeded), parent_id=stack[0].parent_id)]
                    main_history.clear()
                    line_sound = True
                stack[-1].moves_allowed = 1 if is_black_only else 2
                continue
            if game is None and over is not None and _ply_of(number, is_black_only) in (
                _ply_awaited(over[1].board),
                (over[2] + 1) if over[2] is not None else None,
            ):
                # The number carries on the numbering of the game the result
                # closed, so this is that game still: the moves the loser
                # resigned in the face of. Opened as a game of its own they
                # start from a position the book never printed and none of
                # them is scored at all.
                game, stack, over = over[0], [over[1]], None
            if weighted and token.bold and stack:
                _resume_the_score(_ply_of(number, is_black_only))
            opens_a_game = game is None or (
                number == 1 and not is_black_only and result.moves and not stack[1:]
            )
            if opens_a_game:
                # A game whose first move is not the first move: the book never
                # printed where it starts. That is analysis quoted after a
                # result — "Black resigned in view of 27...Rf6 28 d5" — or a run
                # of pages opening in mid-score. Played from the initial
                # position it becomes a game nobody played, breaking on its
                # first move and carrying every move after it down; and where a
                # wrong board makes a move legal, it is worse than broken.
                #
                # So the moves are read and none of them is scored. They keep
                # their page and their box, which is what the reader needs to
                # correct them, and `position_known` tells the app and the
                # measurement not to believe the rest.
                start_game(token.page, position_known=number == 1 and not is_black_only)
            if stack:
                last_declared = _ply_of(number, is_black_only)
                last_licence = 1 if is_black_only else 2
                _open_the_bracket_on_the_right_side(last_declared)
                if weighted:
                    _place_by_weight(token.bold, last_declared)
                else:
                    _place_by_number(last_declared)
                stack[-1].declared_at = last_declared
                if len(stack) == 1 and game is not None and game.position_known:
                    # Once the placement has had its say: a number that opened
                    # an aside was a citation, and says nothing about the main
                    # line. What is left is the main line disagreeing with the
                    # book about which move it is on, and it only ever does
                    # that by losing one. The line clears itself when a later
                    # number agrees again — a diagram reseeds it, or the book
                    # starts a fresh game.
                    if last_declared != _ply_awaited(stack[0].board):
                        adrift.add(game.id)
                    else:
                        adrift.discard(game.id)
                stack[-1].moves_allowed = last_licence
                # The book has printed a number, so it is starting the line
                # again: whatever follows is resolved against the board once
                # more, as it was before this level lost it.
                stack[-1].board_lost = False
            continue

        if token.kind == "var_open":
            if not stack:
                continue
            level = stack[-1]
            if level.board_before_last is None:
                # A parenthesis with no preceding move at this depth: ordinary
                # prose brackets, not a variation.
                continue
            stack.append(
                _Level(
                    board=level.board_before_last.copy(),
                    parent_id=level.parent_of_last,
                    moves_allowed=2,
                    from_bracket=True,
                )
            )
            continue

        if token.kind == "var_close":
            if len(stack) > 1:
                stack.pop()
            continue

        if token.kind == "result":
            over = (game, stack[0], last_declared) if game is not None and stack else None
            game = None
            finished = True
            stack = []
            continue

        if token.kind != "move":
            continue

        # --- a move token ---
        if game is None or not stack:
            result.skipped.append({**token.to_json(), "reason": "no game in progress"})
            continue

        level = stack[-1]
        if strict_numbering and level.moves_allowed <= 0 and kind_before != "move":
            # A number licenses the moves printed beside it, and a scan
            # destroys the numbers of the score as readily as anything else —
            # "par 1" for "par 18.", `8.` swallowed by the move in front of
            # it. The move that lost its number is still printed hard against
            # the move before it, and refused here it is dropped with its box,
            # so the reader cannot even correct it. What the licence is for is
            # the commentary naming a square, and prose stands in front of
            # that; `_ends_in_a_word` is what ends a licence.
            result.skipped.append({**token.to_json(), "reason": "no move number in context"})
            continue
        if token.bbox is None:
            result.skipped.append({**token.to_json(), "reason": "no geometry"})
            continue

        if (
            weighted
            and moves_carry_the_weight
            and not token.bold
            and len(stack) == 1
            and not any(other.from_bracket for other in stack)
        ):
            # A move in the analysis weight, standing on the main line with no
            # number of its own to place it: the typography says it is not the
            # score, and `_place_by_weight` never saw it. Sakaev page 37 reads
            # "the move ...b7-b5 will be least useful" — a move the game has
            # already played, illegal where it stands, and 93 moves under it.
            stack.append(
                _Level(
                    board=level.board.copy(),
                    parent_id=level.parent_id,
                    moves_allowed=level.moves_allowed,
                )
            )
            level = stack[-1]

        board_before = level.board.copy()
        if not level.board_lost:
            (main_history if len(stack) == 1 else level.history).setdefault(
                _ply_awaited(board_before), (board_before.copy(), level.parent_id)
            )
        if level.board_lost:
            # The move the number announced beside one it could not read.
            # `8 Na2 e6`: the knight is unreadable and `e6` is dropped for
            # want of a licence — 790 move tokens over the corpus, with no
            # node and no box, so the reader cannot even correct them. It is
            # read here and never scored: the board this level holds is the
            # one from before the break, and a move that happens to be legal
            # on it would be worse than a broken one.
            resolution = _Resolution(
                None,
                _TRAILING_ANNOTATION.sub("", token.text.strip()),
                "broken",
                0.0,
                {"raw": token.text, "reason": "read after a move the line could not"},
            )
        elif game.position_known:
            resolution = _resolve(
                board_before, token.text, token.consumed, token.lost_symbol,
                token.lost_piece,
            )
            if resolution.status == "broken":
                # Nothing to lose: the move is dead where it stands. The
                # number that announced it may still say where it belongs.
                # The line's own record as well as the game's, and the game's
                # wins where both answer. A book cites two alternative
                # variations in one breath — "7 ♗xf6 ♕xf6 8 ♘d5 ♕d8, puisque
                # 7 ♗h4? g5 8 ♗g3 ♗g4" — and the second's number is one the
                # first has passed and the game has not reached, so nothing
                # but the line itself knows the position it names.
                if not any(other.from_bracket for other in stack):
                    placed = _place_a_citation(
                        main_history if len(stack) == 1
                        else {**stack[-1].history, **main_history},
                        last_declared, last_licence, token, stack,
                    )
                    if placed is None:
                        placed = _place_beside_a_citation(
                            closed_aside, last_declared, last_licence, token, stack
                        )
                else:
                    placed = None
                if placed is not None:
                    level = stack[-1]
                    board_before = level.board.copy()
                    resolution = placed
        else:
            resolution = _Resolution(
                None,
                _TRAILING_ANNOTATION.sub("", token.text.strip()),
                "broken",
                0.0,
                {"raw": token.text, "reason": "the game's starting position was never printed"},
            )
        move = resolution.move

        move_counter += 1
        sibling_key = (game.id, level.parent_id)
        node = MoveNode(
            id=f"{game.id}-m{move_counter}",
            game_id=game.id,
            parent_id=level.parent_id,
            san=resolution.san,
            uci=move.uci() if move else None,
            fen=None,
            ply=board_before.ply() + 1,
            page=token.page,
            bbox=token.bbox,
            variation_index=child_counts.get(sibling_key, 0),
            confidence=resolution.confidence,
            status=resolution.status,
            repair=resolution.repair,
        )
        child_counts[sibling_key] = node.variation_index + 1

        if resolution.candidates:
            result.ambiguities.append(
                {
                    "move_id": node.id,
                    "page": token.page,
                    "raw": token.text,
                    "consumed": token.consumed,
                    "candidates": resolution.candidates,
                    "settled_by": resolution.settled_by,
                    # The distance, in plies, to the nearest move above this
                    # one that was accepted after a repair — the measurement
                    # that says whether the board can be trusted here at all.
                    "upstream_repair_distance": _upstream_repair_distance(
                        by_id, level.parent_id
                    ),
                }
            )

        if move is not None:
            level.board.push(move)
            node.fen = level.board.fen()
            # The level's own record, which an aside taken back onto the game
            # carries with it; `main_lines` is the game's, and only the game's.
            level.line.append(level.board.board_fen())
            if len(stack) == 1:
                result.main_lines.setdefault(game.id, []).append(level.board.board_fen())

        if game.id in adrift:
            result.drifted.append(node.id)
        result.moves.append(node)
        by_id[node.id] = node
        if game.root_move_id is None:
            game.root_move_id = node.id

        level.board_before_last = board_before
        level.parent_of_last = level.parent_id
        level.last_move_id = node.id
        level.parent_id = node.id
        level.moves_allowed -= 1

        if move is None and game.position_known:
            # The position is lost from here on: anything that follows would be
            # played on a board that no longer matches the book. The line is
            # not closed but emptied — what the number still announces is read
            # for its box, which is what the reader taps to correct it, and
            # none of it is played or scored.
            level.board_lost = True
            if len(stack) == 1:
                line_sound = False

    return result


def _append_comment(node: MoveNode, text: str) -> None:
    merged = text if node.comment is None else f"{node.comment} {text}"
    node.comment = merged[:_MAX_COMMENT_LENGTH]


@dataclass
class _Resolution:
    """What `_resolve` made of one move token."""

    move: chess.Move | None
    san: str
    status: str
    confidence: float
    repair: dict[str, str] | None = None
    #: The legal readings, when the token failed for being ambiguous rather
    #: than illegal. Empty otherwise, and empty is what marks the difference.
    candidates: list[str] = field(default_factory=list)
    #: What settled the ambiguity, when something did.
    settled_by: str | None = None


def _resolve(
    board: chess.Board,
    raw: str,
    consumed: str = "",
    lost_symbol: str = "",
    lost_piece: str = "",
) -> _Resolution:
    """Read `raw` as a move in `board`, repairing it if needed.

    `consumed` is the characters the glyph pass destroyed inside this token,
    and is only ever consulted for an ambiguous move; see `_settle_ambiguity`.

    `lost_symbol` is the wreck of a piece symbol printed before the token and
    never restored, and `lost_piece` the piece the book's own spelling of its
    symbols makes of that wreck. They change what the token can mean rather
    than how well it is trusted, so they are answered first; see
    `_settle_lost_symbol`.
    """
    candidate = _TRAILING_ANNOTATION.sub("", raw.strip())
    # Castling printed with zeros is a typographic variant, not a scanning
    # error, so it is normalised silently and stays `ok`.
    plain = candidate.replace("0-0-0", "O-O-O").replace("0-0", "O-O")

    if lost_symbol:
        return _settle_lost_symbol(board, plain, raw, lost_symbol, lost_piece)

    if plain.startswith("x"):
        # A capture whose piece left no character at all — not even a wreck
        # for the glyph pass to hand over. No SAN begins with a capture: a
        # pawn names the file it captures from, so `xc3+` is a piece move and
        # nothing else. The board is asked which piece, exactly as it is for a
        # wreck.
        return _settle_lost_symbol(board, plain, raw, "")

    lost_file = _FILE_READ_AS_A_DIGIT.match(_CHECK_MARK.sub("", plain))
    if lost_file:
        return _settle_lost_file(board, plain, raw, lost_file)

    try:
        move = board.parse_san(plain)
        return _Resolution(move, board.san(move), "ok", 1.0)
    except chess.AmbiguousMoveError:
        return _settle_ambiguity(board, plain, raw, consumed)
    except (ValueError, AssertionError):
        failure = "no legal reading in this position"

    settled = _drop_a_false_disambiguator(board, plain, raw)
    if settled is not None:
        return settled

    best_cost = _MAX_REPAIR_COST + 1.0
    best: list[tuple[chess.Move, str]] = []
    # The check mark is not part of what the reader wrote down: `python-chess`
    # derives it from the position, and a book may print `Nxc3` where the SAN
    # is `Nxc3+`. Comparing them literally charges a full insertion for it, so
    # every checking move lands at 1.5 and no repair is ever affordable —
    # which is why four books in a row reported not one `uncertain` move.
    bare = _CHECK_MARK.sub("", plain)
    for legal in board.legal_moves:
        legal_san = board.san(legal)
        cost = _confusable_distance(bare, _CHECK_MARK.sub("", legal_san))
        if cost < best_cost:
            best_cost, best = cost, [(legal, legal_san)]
        elif cost == best_cost:
            best.append((legal, legal_san))

    if best_cost > _MAX_REPAIR_COST or not best:
        return _Resolution(None, plain, "broken", 0.0, {"raw": raw, "reason": failure})

    if len(best) > 1:
        # Two legal moves are equally plausible readings. Choosing one at
        # random would hide the problem; leave it for the user to settle.
        options = ", ".join(san for _, san in best[:4])
        return _Resolution(
            None, plain, "broken", 0.0,
            {"raw": raw, "reason": f"ambiguous between {options}"},
        )

    move, legal_san = best[0]
    return _Resolution(
        move,
        legal_san,
        "uncertain",
        max(0.0, 1.0 - best_cost / 2.0),
        {"raw": raw, "reason": f"read as {legal_san} (edit cost {best_cost:g})"},
    )


#: A move naming its piece, a letter or digit, and then its square: `Nbd2` as
#: the book prints it, and `B1g3` as a broken symbol leaves it.
_DISAMBIGUATED = re.compile(r"^([KQRBN])([a-h1-8])(x?[a-h][1-8](?:=[QRBN])?)$")


def _drop_a_false_disambiguator(
    board: chess.Board, plain: str, raw: str
) -> _Resolution | None:
    """Read `B1g3` as `Bg3` — when, and only when, nothing else could be meant.

    A figurine the page half destroyed leaves a character welded inside the
    move: `♗1g3`, `♘bd4`, `♕fh4+`. Between a piece letter and a square, such a
    character is exactly where a disambiguator goes, so the move is read as one
    and is illegal, and on Grivas that one shape carries three hundred moves
    down with it.

    Removing a character is a full edit and `_MAX_REPAIR_COST` refuses it on
    purpose — allowing any single deletion is how `Qh9` becomes `Qh5`. This is
    narrower in two ways that matter: only the character between the piece and
    its square is removed, never one of the square's own; and the reading is
    accepted only if the board leaves **one** move it can be. A disambiguator
    the book really printed is there because two pieces reach the square, so
    dropping it raises `AmbiguousMoveError` and this returns nothing.

    `uncertain` at 0.5, like every move the board settled rather than the page.
    """
    match = _DISAMBIGUATED.match(_CHECK_MARK.sub("", plain))
    if match is None:
        return None
    piece, dropped, square = match.groups()
    try:
        move = board.parse_san(piece + square)
    except (ValueError, AssertionError, chess.AmbiguousMoveError):
        return None
    san = board.san(move)
    return _Resolution(
        move,
        san,
        "uncertain",
        0.5,
        {
            "raw": raw,
            "reason": f"read as {san}: {dropped!r} between the piece and the square is "
            "the wreck of the symbol, not a disambiguator",
        },
    )


def _piece_named_by(wreck: str) -> str | None:
    """The piece a wreck spells for itself, when the glyph pass restored it.

    `Q\'e5+`, `K>d2`, `Rf.f7+` on Grivas: the symbol *was* read and its letter
    written back, and only the ink left standing around it kept the move from
    beginning on the letter. So the token carries its piece after all — and a
    letter the page says is worth more than any of the five the board offers.
    One letter, or the wreck names nothing: two mean the run has reached past
    the symbol into whatever stood before it.
    """
    letters = set(_RESTORED_PIECE.findall(wreck))
    return letters.pop() if len(letters) == 1 else None


def _readings_of(
    board: chess.Board, plain: str, pieces: Sequence[str]
) -> list[tuple[chess.Move, str]]:
    """The legal moves `plain` spells in `board`, one per piece that fits."""
    readings: list[tuple[chess.Move, str]] = []
    for piece in pieces:
        try:
            move = board.parse_san(piece + plain)
        except (ValueError, AssertionError):
            continue
        san = board.san(move)
        if "x" in plain and "x" not in san:
            # `python-chess` reads a capture that captures nothing as the
            # quiet move it spells, so `xh7` comes back as `Rh7` on an empty
            # square. The book printed a capture; a piece that merely walks
            # there is not what it printed.
            continue
        readings.append((move, san))
    return readings


def _settle_lost_file(
    board: chess.Board, plain: str, raw: str, shape: re.Match[str]
) -> _Resolution:
    """Name the file from the position, when the scanner read it as a digit.

    SuperAttaquant prints `20.♗g5+ f6` and its layer carries `20.♗25+ f6`: the
    file letter came off the scan as a digit and the rank survived beside it.
    Nothing on the page can put the letter back — the same book reads `♘d5` as
    `♘45` and `♗f4` as `♗41`, so the digit is not a look-alike of anything and
    no substitution table reaches it.

    The board can. The piece is printed and the rank is printed, and a piece
    with one legal move to a rank has named its own square. Where two of them
    reach it the readings are handed on as `candidates`, exactly as an
    ambiguity is: a wrong move here is played, is legal, and puts every move
    below it on a position the book never printed.

    Eight of these over the corpus and every one on this scan; each stood at
    the head of a game and three of them were the book's largest breaks.
    """
    piece, rank = shape.group(1), int(shape.group(2)) - 1
    # The check mark is the third thing the page still says, and it is worth
    # as much as the other two: `38.♗g6+` came off as `♗26+`, and the only
    # bishop move to rank 6 was a capture that gives no check. Read without
    # the mark it is legal, is played, and is not the book's move.
    checks = plain.endswith(("+", "#"))
    readings = [
        (move, san)
        for move, san in ((move, board.san(move)) for move in board.legal_moves)
        if san.startswith(piece)
        and chess.square_rank(move.to_square) == rank
        and san.endswith(("+", "#")) == checks
    ]
    if len(readings) != 1:
        return _Resolution(
            None, plain, "broken", 0.0,
            {
                "raw": raw,
                "reason": "the file is a digit and "
                + (
                    f"{len(readings)} of the {piece} reach rank {rank + 1}"
                    if readings
                    else f"no {piece} reaches rank {rank + 1}"
                ),
            },
            candidates=[san for _, san in readings],
        )
    move, san = readings[0]
    return _Resolution(
        move, san, "uncertain", _LOST_SYMBOL_CONFIDENCE,
        {
            "raw": raw,
            "reason": f"read as {san}: the file came off the scan as a digit, "
            f"and only one {piece} reaches rank {rank + 1}",
        },
        candidates=[san],
        settled_by="legality",
    )


def _settle_lost_symbol(
    board: chess.Board, plain: str, raw: str, wreck: str, spelled: str = ""
) -> _Resolution:
    """Name the piece from the position, when the page no longer names it.

    The book printed a piece and the glyph pass failed to restore it, so what
    is left spells a pawn move — or, where the symbol left no character at
    all, a capture with nothing in front of it (`xc3+`). Playing that is worse than losing the move:
    it is legal often enough to be accepted at full confidence, and every move
    after it is then played on a position the book never reached.

    Two things are asked before the board, and both are the page rather than
    the position. The wreck sometimes answers for itself, the glyph pass
    having restored the letter with only the ink around it keeping the move
    from starting there (`_piece_named_by`). And the book has spelled its
    pieces for us several hundred times over, in the ink under every symbol
    that pass *did* restore: `glyphs.spellings` learns that table and
    `tokenize` reads this wreck off it.

    The board can often answer. Of the five pieces, usually only one can reach
    the square at all — the bishop on `1 d4 Nf6 2 c4 g6 3 Nc3 i.g7`, where no
    knight, rook, queen or king has any move to g7. When two can, nothing on
    the page settles it, so the readings are handed on as `candidates` for the
    reader to pick between, which is what the ambiguity path exists for.
    """
    named = _piece_named_by(wreck) or spelled
    readings = _readings_of(board, plain, (named,) if named else _LOST_SYMBOL_PIECES)
    if named and not readings:
        # The page and the board do not meet. Either the symbol was misread
        # or the line is already somewhere the book never was, and neither is
        # answered here: the other four pieces are asked, exactly as they were
        # before the page was looked at.
        fallback = _readings_of(board, plain, _LOST_SYMBOL_PIECES)
        if fallback:
            named, readings = None, fallback
    pieces = (named,) if named else _LOST_SYMBOL_PIECES

    if not readings:
        # The square may be wrecked as well as the symbol — `♘e5` printed
        # `tL!eS`, where the scanner reads the rank as a letter. Nothing
        # spells a legal move then, so the same near-free substitutions the
        # repair path allows are tried here, against the legal moves that name
        # a piece: the piece is known to have been printed, and the square is
        # read from the board like everything else in this function.
        bare = _CHECK_MARK.sub("", plain)
        best_cost, repaired = _MAX_REPAIR_COST + 1.0, []
        for legal in board.legal_moves:
            legal_san = board.san(legal)
            if legal_san[0] not in pieces:
                continue
            cost = _confusable_distance(bare, _CHECK_MARK.sub("", legal_san[1:]))
            if cost < best_cost:
                best_cost, repaired = cost, [(legal, legal_san)]
            elif cost == best_cost:
                repaired.append((legal, legal_san))
        if best_cost <= _MAX_REPAIR_COST and len(repaired) == 1:
            readings = repaired

    sans = [san for _, san in readings]
    if len(readings) == 1:
        move, san = readings[0]
        return _Resolution(
            move,
            san,
            "uncertain",
            _LOST_SYMBOL_CONFIDENCE,
            {
                "raw": raw,
                "reason": f"read as {san}: "
                + (
                    f"the {named} inside '{wreck}' names the piece"
                    if _piece_named_by(wreck)
                    else f"the book spells its {named} '{wreck}'"
                    if named
                    else (f"'{wreck}'" if wreck else "the lost piece")
                    + " is the only piece that fits"
                ),
            },
            candidates=sans,
            settled_by=(
                "the letter left in the wreck"
                if _piece_named_by(wreck)
                else "the book's own spelling" if named else "legality"
            ),
        )

    printed = f"the piece printed as '{wreck}'" if wreck else "the piece"
    reason = (
        f"{printed} was lost, and "
        + (f"could be {', '.join(sans[:4])}" if sans else "no piece reaches this square")
    )
    return _Resolution(None, plain, "broken", 0.0, {"raw": raw, "reason": reason},
                       candidates=sans)


def _settle_ambiguity(
    board: chess.Board, plain: str, raw: str, consumed: str
) -> _Resolution:
    """Handle a move naming a piece and a square two of them can reach.

    The edit-distance repair is deliberately not tried here. It is built for a
    token whose characters are wrong, and this token's are not: the piece and
    the destination are legal, only the origin is unsaid. Letting it run would
    answer a question nobody asked, and could return some *other* legal move
    that happens to look alike.

    The one thing that can answer, when it is there, is a character the glyph
    pass destroyed. A figurine is written over the characters the scanner read
    under a piece symbol, and — being twice a letter wide — sometimes over the
    disambiguating letter beside it. If exactly one of the legal readings
    starts on a file or rank named in what was destroyed, that is the move the
    book printed. If none do, or if two do, the answer is not on the page and
    the move is `broken`: the user settles it against the print.
    """
    candidates = _ambiguous_candidates(board, plain)
    sans = [board.san(move) for move in candidates]

    hints = {ch for ch in consumed if ch in _DISAMBIGUATION_CHARS}
    matched = [
        (move, san)
        for move, san in zip(candidates, sans)
        if _origin_hints(move.from_square) & hints
    ]
    if len(matched) == 1:
        move, san = matched[0]
        return _Resolution(
            move,
            san,
            "uncertain",
            _CONSUMED_DISAMBIGUATION_CONFIDENCE,
            {"raw": raw, "reason": f"read as {san}: '{consumed}' was under the figurine"},
            candidates=sans,
            settled_by="consumed",
        )

    options = ", ".join(sans[:4]) or "no legal reading"
    return _Resolution(
        None,
        plain,
        "broken",
        0.0,
        {"raw": raw, "reason": f"ambiguous: the disambiguating letter is missing ({options})"},
        candidates=sans,
    )


def _ambiguous_candidates(board: chess.Board, san: str) -> list[chess.Move]:
    """The legal moves `san` could name, when it names more than one.

    Built from the piece and the destination rather than by comparing SAN
    strings, so a token that already carries part of its disambiguation
    (`Raa4`, two rooks on the a-file) narrows the set instead of missing it.
    Whether the token spells the capture is not used: books drop the `x`, and
    a wider set only makes the caller more cautious.
    """
    parts = _PIECE_MOVE.match(san)
    if parts is None:
        return []

    piece_type = chess.PIECE_SYMBOLS.index(parts["piece"].lower())
    to_square = chess.parse_square(parts["to"])
    from_file = parts["from_file"]
    from_rank = parts["from_rank"]

    candidates = []
    for legal in board.legal_moves:
        if legal.to_square != to_square:
            continue
        if board.piece_type_at(legal.from_square) != piece_type:
            continue
        if from_file and chess.square_file(legal.from_square) != chess.FILE_NAMES.index(from_file):
            continue
        if from_rank and chess.square_rank(legal.from_square) != chess.RANK_NAMES.index(from_rank):
            continue
        candidates.append(legal)
    return candidates


def _origin_hints(square: int) -> set[str]:
    """The two characters that could disambiguate a move leaving `square`."""
    return {
        chess.FILE_NAMES[chess.square_file(square)],
        chess.RANK_NAMES[chess.square_rank(square)],
    }


def _place_a_citation(
    history: dict[int, tuple[chess.Board, str | None]],
    declared: int | None,
    licence: int,
    token: Token,
    stack: list[_Level],
) -> _Resolution | None:
    """Re-place a move the line cannot play on the position its number names.

    Books cite an earlier move in the middle of a sentence, with no bracket
    and no indent — "Theory also suggests 4 ...g6 here", "and 7 Ba4 (Zhang
    Zhong-Grivas, Elista OL)". `_place_by_number` is what diverts those, and
    it works by arithmetic, which fails exactly when it is needed most: the
    parser's ply count drifts from the book's by a move for every move it
    could not read, so on a badly scanned game no number matches any position
    and every citation is played as the continuation. It is illegal there,
    and it takes the rest of the page down with it — 113 moves under one on
    Grivas, 96 under another.

    The board still knows. Among the positions the main line passed within a
    ply or two of the number, one may make this move legal, and a citation
    that only one position can play is a citation that says where it belongs.

    Two things keep this honest. Only a move already `broken` is offered it,
    so nothing that stands can be taken away; and where more than one position
    can play the move, only the number's own is taken — a move two boards can
    both play says nothing about where it was printed.
    """
    if declared is None or declared == _ply_awaited(stack[-1].board):
        # The number says this move *is* the continuation. Then it is broken
        # for a reason no other board can mend — an illegal move, a
        # disambiguation the scanner dropped — and offering it one is how
        # `2 Nc6` becomes a legal Black move a ply earlier, which is the one
        # thing `_MAX_REPAIR_COST` exists to prevent.
        return None
    found: list[tuple[int, chess.Board, str | None, _Resolution]] = []
    # Whole moves only: an odd offset lands the citation on a board where the
    # other side is to play, and a move read for the wrong colour is a wrong
    # move however legal it comes out.
    for offset in range(-_CITATION_SPAN, _CITATION_SPAN + 1, 2):
        entry = history.get(declared + offset)
        if entry is None:
            continue
        board, parent = entry
        trial = _resolve(board, token.text, token.consumed, token.lost_symbol, token.lost_piece)
        if trial.status != "broken":
            found.append((offset, board, parent, trial))
    exact = [item for item in found if item[0] == 0]
    chosen = exact[0] if exact else (found[0] if len(found) == 1 else None)
    if chosen is None:
        return None
    _offset, board, parent, trial = chosen
    # Replaces any aside in progress rather than nesting, as `_place_by_number`
    # does, and carries the licence the number gave: a citation announced by
    # `5...` is one move and one by `5.` is two.
    stack[1:] = [_Level(board=board.copy(), parent_id=parent, moves_allowed=licence,
                        declared_at=declared)]
    return trial


def _place_beside_a_citation(
    closed_aside: tuple[chess.Board, str | None] | None,
    declared: int | None,
    licence: int,
    token: Token,
    stack: list[_Level],
) -> _Resolution | None:
    """Read a move as the second of two alternatives the book cited together.

    "White can choose between 7 Na2 and 7 Nb1", "Other moves would meet the
    same fate: 17...Nc5? 18 Be4 a6; 17...Qb8 18 Bb5!". Both alternatives carry
    the same number, and that number is the one the main line is waiting for,
    so the second one closes the aside the first one opened and is played as
    the continuation — where it is illegal, since the two are alternatives to
    the *same* move and only one of them is the game.

    `_place_a_citation` cannot help here: its own guard reads the number as
    saying "this is the continuation", which is exactly what it says. What
    knows better is the aside that was closed a moment ago, still standing at
    the position this number named. Offering that board keeps the main line
    intact: only a move already broken is offered it, and the resumption the
    number announced still happens — a move the game really does continue with
    is legal in the main line and never gets this far.
    """
    if closed_aside is None or declared is None:
        return None
    board, parent = closed_aside
    if _ply_awaited(board) != declared:
        return None
    trial = _resolve(board, token.text, token.consumed, token.lost_symbol, token.lost_piece)
    if trial.status == "broken":
        return None
    stack[1:] = [_Level(board=board.copy(), parent_id=parent, moves_allowed=licence,
                        declared_at=declared)]
    return trial


def _upstream_repair_distance(
    by_id: dict[str, MoveNode], parent_id: str | None
) -> int | None:
    """Plies back to the nearest ancestor accepted after a repair, if any.

    Walks through a variation into the line it branched from, which is right:
    the position really does descend from there.
    """
    distance = 1
    node_id = parent_id
    while node_id is not None:
        node = by_id.get(node_id)
        if node is None:
            return None
        if node.status == "uncertain":
            return distance
        node_id = node.parent_id
        distance += 1
    return None


def _confusable_distance(a: str, b: str) -> float:
    """Levenshtein distance where OCR-confusable substitutions cost 0.5."""
    previous = [float(i) for i in range(len(b) + 1)]
    for i, ch_a in enumerate(a, start=1):
        current = [float(i)]
        for j, ch_b in enumerate(b, start=1):
            if ch_a == ch_b:
                substitution = previous[j - 1]
            else:
                penalty = 0.5 if frozenset((ch_a, ch_b)) in _CONFUSABLE_PAIRS else 1.0
                substitution = previous[j - 1] + penalty
            current.append(min(previous[j] + 1.0, current[j - 1] + 1.0, substitution))
        previous = current
    return previous[-1]
