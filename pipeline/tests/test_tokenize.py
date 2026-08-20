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

    def test_a_number_does_not_reach_into_the_word_before_it(self):
        # Tolerating a space inside the number let it start on any digit at
        # all, including one ending a word: `Nf6 6 Nc3`, with the knight's
        # symbol unrecovered so that nothing covered `f6`, offered the rank
        # digit and the move number as one — 66, a hundred plies forward, and
        # the game lost from its fifth move. The wreck is a move of its own
        # now, so the same reach is pinned here on the game header the book
        # prints above every score: the year and the first move read as 31.
        tokens = tokenize_pages([page_of("Kotronias-Grivas Athens 1993 1 e4 c5")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["1"]

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

    def test_a_move_inside_a_broken_symbol_is_marked_not_dropped(self):
        # `ll:\c3` is a knight this book's font broke apart. Read from `c3`
        # on it is a legal pawn move — scored ok at full confidence, with a
        # position the book never reached under every move after it. The token
        # is kept, because the board can often name the piece the page lost,
        # but it carries the wreck so that nothing reads it as a pawn move.
        tokens = tokenize_pages([page_of("3 ll:\\c3 i.g7 4 e4 'ii'e8")])
        moves = [t for t in tokens if t.kind == "move"]

        assert [t.text for t in moves] == ["c3", "g7", "e4", "e8"]
        assert [t.lost_symbol for t in moves] == ["ll:\\", "i.", "", "'ii'"]

    def test_a_word_run_into_an_ellipsis_is_not_a_broken_symbol(self):
        # One book's OCR drops the space and prints `jouer...e5`. The dot does
        # carry a letter, and it still announces nothing but an ordinary black
        # move — reading a lost piece into it would refuse the pawn move and
        # then find no piece able to reach the square.
        tokens = tokenize_pages([page_of("Il faut jouer...e5 et non 12 Bxf5")])
        moves = [t for t in tokens if t.kind == "move"]

        assert [(t.text, t.lost_symbol) for t in moves] == [("e5", ""), ("Bxf5", "")]

    def test_the_tap_zone_covers_the_symbol_and_not_only_the_square(self):
        # The wreck is the piece as the book printed it, so it belongs to the
        # move's span: the reader puts its tap zone there.
        tokens = tokenize_pages([page_of("3 i.g7")])
        move = next(t for t in tokens if t.kind == "move")

        assert move.raw == "i.g7"

    def test_a_dot_still_opens_a_move(self):
        # The refusal has to leave the two forms a dot legitimately precedes.
        tokens = tokenize_pages([page_of("1.e4 e5 2. Nf3 Nc6 13...Nb4")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "e4", "e5", "Nf3", "Nc6", "Nb4",
        ]
