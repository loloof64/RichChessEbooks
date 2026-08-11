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

#: Comments longer than this are truncated; a runaway match usually means the
#: tokeniser swallowed a whole page of prose.
_MAX_COMMENT_LENGTH = 600

_TRAILING_ANNOTATION = re.compile(r"[!?]+$")


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

    def counts(self) -> dict[str, int]:
        return {
            "games": len(self.games),
            "moves": len(self.moves),
            "ok": sum(1 for m in self.moves if m.status == "ok"),
            "uncertain": sum(1 for m in self.moves if m.status == "uncertain"),
            "broken": sum(1 for m in self.moves if m.status == "broken"),
            "skipped": len(self.skipped),
        }

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


def parse_tokens(
    tokens: Iterable[Token],
    *,
    initial_fen: str = chess.STARTING_FEN,
    strict_numbering: bool = True,
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
    game: Game | None = None
    stack: list[_Level] = []

    def start_game(page: int) -> None:
        nonlocal game, game_counter, stack, pending_title
        game_counter += 1
        game = Game(
            id=f"g{game_counter}",
            title=pending_title,
            initial_fen=initial_fen,
            root_move_id=None,
            page_start=page,
        )
        result.games.append(game)
        stack = [_Level(board=chess.Board(initial_fen), parent_id=None)]
        pending_title = None

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
            continue

        if token.kind == "move_number":
            number = int(re.match(r"\d+", token.text).group())
            is_black_only = "..." in token.text
            if game is None or (number == 1 and not is_black_only and result.moves and not stack[1:]):
                start_game(token.page)
            if stack:
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
        move, san, status, confidence, repair = _resolve(board_before, token.text)

        move_counter += 1
        sibling_key = (game.id, level.parent_id)
        node = MoveNode(
            id=f"{game.id}-m{move_counter}",
            game_id=game.id,
            parent_id=level.parent_id,
            san=san,
            uci=move.uci() if move else None,
            fen=None,
            ply=board_before.ply() + 1,
            page=token.page,
            bbox=token.bbox,
            variation_index=child_counts.get(sibling_key, 0),
            confidence=confidence,
            status=status,
            repair=repair,
        )
        child_counts[sibling_key] = node.variation_index + 1

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

    return result


def _append_comment(node: MoveNode, text: str) -> None:
    merged = text if node.comment is None else f"{node.comment} {text}"
    node.comment = merged[:_MAX_COMMENT_LENGTH]


def _resolve(
    board: chess.Board, raw: str
) -> tuple[chess.Move | None, str, str, float, dict[str, str] | None]:
    """Read `raw` as a move in `board`, repairing it if needed.

    Returns the move (None when unreadable), the SAN to record, the status,
    a confidence in [0, 1], and — when a repair was applied — what it changed.
    """
    candidate = _TRAILING_ANNOTATION.sub("", raw.strip())
    # Castling printed with zeros is a typographic variant, not a scanning
    # error, so it is normalised silently and stays `ok`.
    plain = candidate.replace("0-0-0", "O-O-O").replace("0-0", "O-O")

    try:
        move = board.parse_san(plain)
        return move, board.san(move), "ok", 1.0, None
    except chess.AmbiguousMoveError:
        # The move names a piece and a destination two pieces can reach: the
        # book printed a disambiguation letter (Nbd2) that did not survive
        # extraction. Worth telling apart from an outright illegal move,
        # because it is the easiest kind for the user to settle.
        failure = "ambiguous: the disambiguating letter is missing"
    except (ValueError, AssertionError):
        failure = "no legal reading in this position"

    best_cost = _MAX_REPAIR_COST + 1.0
    best: list[tuple[chess.Move, str]] = []
    for legal in board.legal_moves:
        legal_san = board.san(legal)
        cost = _confusable_distance(plain, legal_san)
        if cost < best_cost:
            best_cost, best = cost, [(legal, legal_san)]
        elif cost == best_cost:
            best.append((legal, legal_san))

    if best_cost > _MAX_REPAIR_COST or not best:
        return None, plain, "broken", 0.0, {"raw": raw, "reason": failure}

    if len(best) > 1:
        # Two legal moves are equally plausible readings. Choosing one at
        # random would hide the problem; leave it for the user to settle.
        options = ", ".join(san for _, san in best[:4])
        return None, plain, "broken", 0.0, {"raw": raw, "reason": f"ambiguous between {options}"}

    move, legal_san = best[0]
    return (
        move,
        legal_san,
        "uncertain",
        max(0.0, 1.0 - best_cost / 2.0),
        {"raw": raw, "reason": f"read as {legal_san} (edit cost {best_cost:g})"},
    )


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
