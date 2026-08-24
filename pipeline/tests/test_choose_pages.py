"""The page range a book is measured on: whole games, not an arbitrary window."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from choose_pages import _continues_a_game, _whole_games  # noqa: E402

OPENS = "Smith - Jones, Ohrid 2001\n1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6\n"
CONTINUES = "24.Rd1 Rxd1 25.Qxd1 Qc7 26.h3 g6 27.Qd4\nand Black resigned.\n" + OPENS
PROSE = "The bishop pair is worth more here than the exchange.\n"


def _book(pages: dict[int, str], total: int = 40) -> list[str]:
    """A book of `total` pages, `pages` giving the ones that carry anything."""
    return [pages.get(i + 1, PROSE) for i in range(total)]


def test_a_page_opening_a_game_does_not_continue_one():
    assert not _continues_a_game(OPENS)


def test_a_page_whose_score_runs_above_its_first_game_continues_one():
    assert _continues_a_game(CONTINUES)


def test_a_cross_reference_is_not_a_tail():
    # "2.20) 2.22)" over a Boussole page opening a game: two numbers, no play.
    assert not _continues_a_game("2.20) 2.22) " + OPENS)


def test_the_first_page_moves_back_to_where_its_game_began():
    texts = _book({7: OPENS, 10: CONTINUES, 22: OPENS})
    assert _whole_games(texts, 10, 20) == (7, 21)


def test_a_page_that_opens_its_own_game_stays_put():
    texts = _book({7: OPENS, 10: OPENS, 22: OPENS})
    assert _whole_games(texts, 10, 20)[0] == 10


def test_the_last_page_moves_forward_to_the_end_of_its_game():
    texts = _book({10: OPENS, 23: OPENS})
    assert _whole_games(texts, 10, 20) == (10, 22)


def test_a_game_ending_exactly_on_the_last_page_is_not_grown():
    texts = _book({10: OPENS, 21: OPENS})
    assert _whole_games(texts, 10, 20) == (10, 20)


def test_a_book_that_never_opens_a_game_keeps_its_window():
    # A puzzle book: fragments from positions it never prints. There is no
    # boundary to snap to, and swallowing the chapter would not make one.
    texts = _book({10: CONTINUES.replace(OPENS, ""), 30: PROSE})
    assert _whole_games(texts, 10, 20) == (10, 20)


def test_neither_edge_reaches_further_than_the_budget():
    texts = _book({2: OPENS, 10: CONTINUES, 35: OPENS})
    assert _whole_games(texts, 10, 20, budget=6) == (10, 20)
