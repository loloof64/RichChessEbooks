"""What the measurement counts: a window's own pages, read with what stands before them."""
from __future__ import annotations

import sys
from pathlib import Path

from rce_pipeline.extract import BBox
from rce_pipeline.parse import parse_tokens
from rce_pipeline.tokenize import Token

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from measure import figures  # noqa: E402


def tok(kind: str, text: str, page: int) -> Token:
    return Token(kind=kind, text=text, raw=text, page=page, start=0, end=len(text),
                 bbox=BBox(72.0, 640.0, 18.0, 10.0))


def test_only_the_window_is_counted_and_the_lead_still_places_its_game():
    # The game opens on page 1, the lead; page 2 is the window. Run alone, its
    # moves would be in a game nobody placed — read with the lead, they are
    # clean, and the lead's own moves are not counted.
    parsed = parse_tokens([
        tok("move_number", "1.", 1), tok("move", "e4", 1), tok("move", "e5", 1),
        tok("move_number", "2.", 2), tok("move", "Nf3", 2), tok("move", "Nc6", 2),
        tok("move_number", "3.", 2), tok("move", "Bb5", 2),
    ])

    assert figures(parsed, first=2, last=2) == {
        "moves": 3, "ok": 3, "uncertain": 0, "broken": 0, "unplaced": 0, "clean": 3,
    }
