"""Tests for turning a page's characters into tokens.

What matters here is which spans become moves and move numbers, since the
parser refuses a move that no number announced and a whole column of a book
can be lost to that alone.
"""

from rce_pipeline.extract import BBox, Char, Page
from rce_pipeline.parse import parse_tokens
from rce_pipeline.tokenize import tokenize_pages


def page_of(text: str) -> Page:
    chars = [
        Char(char=ch, bbox=BBox(float(i), 700.0, 1.0, 10.0), font="Serif", size=10.0)
        for i, ch in enumerate(text)
    ]
    return Page(number=1, width=595.0, height=842.0, text=text, chars=chars)


class TestMoveNumbers:
    def test_a_dot_is_not_required_to_announce_a_move(self):
        # Batsford, Gambit and Informator print `12 Nb1`, and so does the
        # Grivas book. Requiring the dot left every move of it unannounced, so
        # `strict_numbering` refused the lot: a page whose left column opened
        # `1 e4 c5 2 Nf3` produced no game at all, losing even the pawn moves
        # that need no piece symbol.
        tokens = tokenize_pages([page_of("12 Nb1 Nd7 13 Bd2 Nb4 14 Na4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["12", "13", "14"]
        assert [m.san for m in parse_tokens(tokens).moves] == ["Nb1", "Bd2", "Na4"]

    def test_an_opening_score_with_no_dots_starts_a_game(self):
        tokens = tokenize_pages([page_of("1 e4 c5 2 Nf3 Nc6 3 d4 cxd4 4 Nxd4")])

        assert [m.san for m in parse_tokens(tokens).moves] == [
            "e4", "c5", "Nf3", "Nc6", "d4", "cxd4", "Nxd4",
        ]

    def test_figures_in_prose_are_not_move_numbers(self):
        # Which is why a bare number counts only when a move follows it
        # directly: this sentence would otherwise announce four of them, and
        # every book is full of such sentences.
        text = "He won 12 games and lost 3 in 1997 at the age of 24 years."

        tokens = tokenize_pages([page_of(text)])

        assert [t for t in tokens if t.kind == "move_number"] == []

    def test_the_dotted_forms_still_work(self):
        tokens = tokenize_pages([page_of("1.e4 e5 2. Nf3 Nc6 13...Nb4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == [
            "1.", "2.", "13...",
        ]

    def test_a_number_the_font_broke_in_two_is_read_whole(self):
        # A subset font emits `18` as `1 8`, with a real space between the
        # digits. The leading `1` then carries no dot and announces nothing,
        # so the number was read as 8 — ten moves early, which the variation
        # detector reads as a branch rather than the continuation.
        tokens = tokenize_pages([page_of("1 7 Bd2 Nb4 1 8 Na4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["17", "18"]

    def test_a_number_does_not_swallow_the_digit_below_it(self):
        # Only a plain space joins two digits. A line ending on a number sits
        # next to the first digit of the line under it, and joining across
        # that break would invent a number neither line printed.
        tokens = tokenize_pages([page_of("Bd2 Nb4 17\n8 Na4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["8"]

    def test_an_ellipsis_printed_as_bullets_still_announces_black(self):
        # The Grivas book sets `...` as three 2.8pt bullets. Read as the
        # single dot that survives, `15 .••` announces a white move, and the
        # black move that follows is played for white.
        tokens = tokenize_pages([page_of("15 .•• Nb4 16 h4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["15...", "16"]


class TestBrokenTypography:
    def test_a_bulleted_ellipsis_keeps_the_line_on_the_right_side(self):
        # `.••` is the damaging form: the leading dot is a real one, so the
        # number was recognised — as white's third, which rewinds the line to
        # before the move just played and opens a variation on it. Three bare
        # bullets are merely unrecognised, which costs nothing here.
        tokens = tokenize_pages(
            [page_of("1 e4 e5 2 Nf3 Nc6 3 Bb5 3 .•• a6 4 Ba4")]
        )

        moves = parse_tokens(tokens).moves

        # The status and the line matter as much as the reading here: a broken
        # move keeps its san, so comparing san alone would pass either way.
        assert [m.san for m in moves] == [
            "e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4",
        ]
        assert {m.status for m in moves} == {"ok"}
        assert {m.variation_index for m in moves} == {0}

    def test_a_move_does_not_start_inside_a_broken_symbol(self):
        # `ll:\c3` is a knight this book's font broke apart. Read from `c3`
        # on, it is a legal pawn move: scored ok at full confidence, and every
        # move after it played on a position the book never reached. Refusing
        # it lowers the ok count and raises what the count is worth.
        tokens = tokenize_pages([page_of("3 ll:\\c3 i.g7 4 e4 'ii'e8")])

        assert [t.text for t in tokens if t.kind == "move"] == ["e4"]

    def test_a_dot_still_opens_a_move(self):
        # The refusal has to leave the two forms a dot legitimately precedes.
        tokens = tokenize_pages([page_of("1.e4 e5 2. Nf3 Nc6 13...Nb4")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "e4", "e5", "Nf3", "Nc6", "Nb4",
        ]
