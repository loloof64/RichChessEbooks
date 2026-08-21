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
from dataclasses import dataclass, field
from typing import Any, Iterable

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

#: The characters a SAN disambiguator can be: an origin file or an origin rank.
_DISAMBIGUATION_CHARS = frozenset("abcdefgh12345678")

#: Comments longer than this are truncated; a runaway match usually means the
#: tokeniser swallowed a whole page of prose.
_MAX_COMMENT_LENGTH = 600

_TRAILING_ANNOTATION = re.compile(r"[!?]+$")

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

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "initial_fen": self.initial_fen,
            "root_move_id": self.root_move_id,
            "page_start": self.page_start,
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
        them (`cascade`); and `ok` into `clean`, the moves no break stands
        above, and `below_break`. **`clean` is the figure to compare between
        two runs.**
        """
        by_id = {m.id: m for m in self.moves}

        def below_a_break(move: MoveNode) -> bool:
            parent = move.parent_id
            while parent is not None:
                if by_id[parent].status == "broken":
                    return True
                parent = by_id[parent].parent_id
            return False

        tally = dict(first_breaks=0, cascade=0, clean=0, below_break=0)
        for move in self.moves:
            tainted = below_a_break(move)
            if move.status == "broken":
                tally["cascade" if tainted else "first_breaks"] += 1
            elif move.status == "ok":
                tally["below_break" if tainted else "clean"] += 1
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


def _ply_of(number: int, is_black: bool) -> int:
    """The half-move a printed `12.` or `12...` announces. White's first is 0."""
    return 2 * (number - 1) + (1 if is_black else 0)


def _ply_awaited(board: chess.Board) -> int:
    """The half-move this position is waiting for."""
    return 2 * (board.fullmove_number - 1) + (0 if board.turn == chess.WHITE else 1)


def parse_tokens(
    tokens: Iterable[Token],
    *,
    initial_fen: str = chess.STARTING_FEN,
    strict_numbering: bool = True,
    diagram_table: dict[str, str] | None = None,
) -> ParseResult:
    """Assemble `tokens` into games of move nodes.

    With `strict_numbering` (the default), a move is only read when a move
    number has recently announced one, or when a variation's parentheses make
    the context unambiguous. Chess books are full of stray tokens that look
    like moves — figure captions, "diagram b4", page references — and the
    numbering is what separates them from real notation. Turn it off for a
    document that prints long unnumbered sequences.
    """
    result = ParseResult()
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
    #: Whether the main line has been sound since the game began: a diagram is
    #: only allowed to teach the font from a board that can be believed.
    line_sound = True
    game: Game | None = None
    stack: list[_Level] = []
    #: Position and parent before each half-move of the game's main line,
    #: keyed by ply. A printed number that does not continue the line is
    #: branched from here, which gives the variation its true starting
    #: position rather than an approximation of one.
    main_history: dict[int, tuple[chess.Board, str | None]] = {}

    def start_game(page: int, from_diagram: str | None = None) -> None:
        nonlocal game, game_counter, stack, pending_title, line_sound
        game_counter += 1
        opening_fen = from_diagram or initial_fen
        game = Game(
            id=f"g{game_counter}",
            title=pending_title,
            initial_fen=opening_fen,
            root_move_id=None,
            page_start=page,
        )
        result.games.append(game)
        stack = [_Level(board=chess.Board(opening_fen), parent_id=None)]
        pending_title = None
        line_sound = True
        main_history.clear()

    def _place_by_number(declared: int) -> None:
        """Send what follows to the line the printed number actually belongs to.

        Books interleave analysis with the game score in plain prose, with no
        bracket, no bold and no indent to mark it — "Another promising
        continuation is 13...♘b6 14 g5", "Threatening 17...♘xc2". Read as the
        continuation, such a line is played on a position the book never
        reached and every move after it breaks.

        The number itself says so. `13...` announces Black's thirteenth, and a
        position knows which half-move it awaits; when the two disagree, this
        is not the continuation. That holds whichever way the number points —
        the examples above run backwards and forwards — which is why the
        direction of travel is the wrong thing to test.

        Brackets are explicit and are left alone: this only guesses, and only
        where the book gave nothing better.
        """
        if any(level.from_bracket for level in stack):
            return
        if declared == _ply_awaited(stack[-1].board):
            return
        if len(stack) > 1 and declared == _ply_awaited(stack[0].board):
            # The main line resumes. A prose variation has no closing bracket,
            # so its end is only ever visible as the game picking up again.
            del stack[1:]
            return
        if declared in main_history:
            board, parent = main_history[declared]
            # Replaces any prose variation in progress rather than nesting:
            # "15 Rhg1!? and 15 Qh3" are two alternatives to the same move, not
            # one inside the other.
            stack[1:] = [_Level(board=board.copy(), parent_id=parent)]

    for token in tokens:
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
            continue

        if token.kind == "diagram":
            rows = tuple(token.text.split("/"))
            reached = stack[0].board.board_fen() if stack else None
            printed = diagrams.decode(rows, diagram_table) if diagram_table else None
            if printed is None:
                verdict = "unread" if diagram_table is None else "unreadable"
            elif not stack:
                verdict = "seeds"
            elif printed == reached:
                verdict = "confirms"
            else:
                verdict = "corrects"
            if verdict in ("seeds", "corrects"):
                pending_position = printed
            result.diagram_checks.append(
                {
                    "page": token.page,
                    "rows": list(rows),
                    # The board the parser had reached, kept whatever the
                    # verdict: this is what `diagrams.learn` reads back, and
                    # `sound` is what says it may.
                    "reached": reached,
                    "printed": printed,
                    "sound": bool(stack) and line_sound,
                    "verdict": verdict,
                }
            )
            continue

        if token.kind == "move_number":
            number = int(re.match(r"\d+", token.text).group())
            is_black_only = "..." in token.text
            if pending_position is not None:
                # The diagram gave the placement and this number gives the rest
                # of the position: whose move it is, and which move it is.
                seeded = diagrams.initial_fen(
                    pending_position, number=number, black_to_move=is_black_only
                )
                pending_position = None
                if game is None:
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
            if game is None or (number == 1 and not is_black_only and result.moves and not stack[1:]):
                start_game(token.page)
            if stack:
                _place_by_number(_ply_of(number, is_black_only))
                stack[-1].moves_allowed = 1 if is_black_only else 2
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
            game = None
            stack = []
            continue

        if token.kind != "move":
            continue

        # --- a move token ---
        if game is None or not stack:
            result.skipped.append({**token.to_json(), "reason": "no game in progress"})
            continue

        level = stack[-1]
        if strict_numbering and level.moves_allowed <= 0:
            result.skipped.append({**token.to_json(), "reason": "no move number in context"})
            continue
        if token.bbox is None:
            result.skipped.append({**token.to_json(), "reason": "no geometry"})
            continue

        board_before = level.board.copy()
        if len(stack) == 1:
            main_history.setdefault(
                _ply_awaited(board_before), (board_before.copy(), level.parent_id)
            )
        resolution = _resolve(
            board_before, token.text, token.consumed, token.lost_symbol
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

        result.moves.append(node)
        by_id[node.id] = node
        if game.root_move_id is None:
            game.root_move_id = node.id

        level.board_before_last = board_before
        level.parent_of_last = level.parent_id
        level.last_move_id = node.id
        level.parent_id = node.id
        level.moves_allowed -= 1

        if move is None:
            # The position is lost from here on: anything that follows would be
            # played on a board that no longer matches the book. Close the line.
            level.moves_allowed = 0
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
    board: chess.Board, raw: str, consumed: str = "", lost_symbol: str = ""
) -> _Resolution:
    """Read `raw` as a move in `board`, repairing it if needed.

    `consumed` is the characters the glyph pass destroyed inside this token,
    and is only ever consulted for an ambiguous move; see `_settle_ambiguity`.

    `lost_symbol` is the wreck of a piece symbol printed before the token and
    never restored. It changes what the token can mean rather than how well it
    is trusted, so it is answered first; see `_settle_lost_symbol`.
    """
    candidate = _TRAILING_ANNOTATION.sub("", raw.strip())
    # Castling printed with zeros is a typographic variant, not a scanning
    # error, so it is normalised silently and stays `ok`.
    plain = candidate.replace("0-0-0", "O-O-O").replace("0-0", "O-O")

    if lost_symbol:
        return _settle_lost_symbol(board, plain, raw, lost_symbol)

    try:
        move = board.parse_san(plain)
        return _Resolution(move, board.san(move), "ok", 1.0)
    except chess.AmbiguousMoveError:
        return _settle_ambiguity(board, plain, raw, consumed)
    except (ValueError, AssertionError):
        failure = "no legal reading in this position"

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


def _settle_lost_symbol(
    board: chess.Board, plain: str, raw: str, wreck: str
) -> _Resolution:
    """Name the piece from the position, when the page no longer names it.

    The book printed a piece and the glyph pass failed to restore it, so what
    is left spells a pawn move. Playing that is worse than losing the move:
    it is legal often enough to be accepted at full confidence, and every move
    after it is then played on a position the book never reached.

    The board can often answer. Of the five pieces, usually only one can reach
    the square at all — the bishop on `1 d4 Nf6 2 c4 g6 3 Nc3 i.g7`, where no
    knight, rook, queen or king has any move to g7. When two can, nothing on
    the page settles it, so the readings are handed on as `candidates` for the
    reader to pick between, which is what the ambiguity path exists for.
    """
    readings: list[tuple[chess.Move, str]] = []
    for piece in _LOST_SYMBOL_PIECES:
        try:
            move = board.parse_san(piece + plain)
        except (ValueError, AssertionError):
            continue
        readings.append((move, board.san(move)))

    sans = [san for _, san in readings]
    if len(readings) == 1:
        move, san = readings[0]
        return _Resolution(
            move,
            san,
            "uncertain",
            _LOST_SYMBOL_CONFIDENCE,
            {"raw": raw, "reason": f"read as {san}: '{wreck}' is the only piece that fits"},
            candidates=sans,
            settled_by="legality",
        )

    reason = (
        f"the piece printed as '{wreck}' was lost, and "
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
