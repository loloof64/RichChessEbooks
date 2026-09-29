"""What the measurement counts: a window's own pages, read with what stands before them."""
from __future__ import annotations

import sys
from pathlib import Path

import chess

from rce_pipeline.extract import BBox
from rce_pipeline.parse import parse_tokens
from rce_pipeline.tokenize import Token

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from measure import figures  # noqa: E402


def tok(kind: str, text: str, page: int) -> Token:
    return Token(kind=kind, text=text, raw=text, page=page, start=0, end=len(text),
                 bbox=BBox(72.0, 640.0, 18.0, 10.0))


def rows_of(board: chess.Board) -> str:
    """A board as the eight rows a diagram token carries."""
    return "/".join(
        "".join(
            piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
            for file in range(8)
        )
        for rank in range(7, -1, -1)
    )


def test_what_the_boards_said_is_counted_too():
    # `clean` only ever loses moves to a board that is read: a correction marks
    # the moves above it contradicted, and a book whose boards stay unread
    # keeps those same wrong moves clean. So the measure also reports what the
    # boards said — how many confirmed their line, how many moves they caught.
    board = chess.Board()
    for san in ("e4", "e5", "Nf3"):
        board.push_san(san)
    confirmed = rows_of(board)
    printed = board.copy()
    for san in ("Nc6", "Bb5"):
        printed.push_san(san)
    table = {char: char for rows in (confirmed, rows_of(printed)) for char in rows if char != "/"}
    parsed = parse_tokens([
        tok("move_number", "1.", 1), tok("move", "e4", 1), tok("move", "e5", 1),
        tok("move_number", "2.", 1), tok("move", "Nf3", 1),
        tok("diagram", confirmed, 1),
        tok("move_number", "2...", 1), tok("move", "Nc6", 1),
        tok("move_number", "3.", 1), tok("move", "Bc4", 1),
        tok("diagram", rows_of(printed), 1),
    ], diagram_table=table)

    counted = figures(parsed, first=1, last=1)
    assert (counted["confirms"], counted["contradicted"]) == (1, 2)


def test_only_the_window_is_counted_and_the_lead_still_places_its_game():
    # The game opens on page 1, the lead; page 2 is the window. Run alone, its
    # moves would be in a game nobody placed — read with the lead, they are
    # clean, and the lead's own moves are not counted.
    parsed = parse_tokens([
        tok("move_number", "1.", 1), tok("move", "e4", 1), tok("move", "e5", 1),
        tok("move_number", "2.", 2), tok("move", "Nf3", 2), tok("move", "Nc6", 2),
        tok("move_number", "3.", 2), tok("move", "Bb5", 2),
    ])

    counted = figures(parsed, first=2, last=2)
    assert {key: counted[key] for key in ("moves", "ok", "uncertain", "broken", "unplaced", "clean")} == {
        "moves": 3, "ok": 3, "uncertain": 0, "broken": 0, "unplaced": 0, "clean": 3,
    }
