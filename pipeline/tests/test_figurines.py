"""Tests for piece symbols printed as characters of a figurine font."""

import chess

from rce_pipeline import figurines
from rce_pipeline.extract import BBox, Char, Page

BODY = "AGaramondPro-Regular"
FIG = "SPAriesFig-Bold"


def page_of(text: str, figurine_chars: str = "") -> Page:
    chars = [
        Char(
            char=ch,
            bbox=BBox(72.0 + i * 6, 640.0, 6.0, 10.0),
            font=FIG if ch in figurine_chars else BODY,
            size=10.5,
        )
        for i, ch in enumerate(text)
    ]
    return Page(number=1, width=595.0, height=842.0, text=text, chars=chars)


class TestFinding:
    def test_a_symbol_is_found_by_where_it_stands(self):
        page = page_of(
            "1.d4 ¤f6 2.c4 e6 3.¤c3 ¥b4 4.e3 0-0 5.¥d3 d5 6.¤f3 c5 7.0-0 ¤c6 "
        "8.a3 ¥xc3 9.bxc3 dxc4 10.¥xc4 £c7 11.¥d3 e5 12.£c2 ¦e8 13.¤h4 e4",
            "¤¥£¦",
        )

        assert set(figurines.candidates([page])) >= {"¤", "¥"}

    def test_a_character_of_the_prose_font_is_not_one(self):
        # The same character, printed in the font the book's text is set in.
        page = page_of("1.d4 ¤f6 2.c4 e6 3.¤c3 ¥b4 4.e3 0-0 5.¥d3 d5 6.¤f3 c5 7.0-0 ¤c6 "
        "8.a3 ¥xc3 9.bxc3 dxc4 10.¥xc4 £c7 11.¥d3 e5 12.£c2 ¦e8 13.¤h4 e4")

        assert figurines.candidates([page]) == []

    def test_a_unicode_figurine_is_left_to_the_pipeline_that_reads_it(self):
        page = page_of(
            "1.d4 ♘f6 2.c4 e6 3.♘c3 ♗b4 4.e3 0-0 5.♗d3 d5 6.♘f3 c5 7.0-0 ♘c6",
            "♘♗",
        )

        assert figurines.candidates([page]) == []

    def test_a_symbol_printed_twice_is_not_worth_settling(self):
        page = page_of("1.d4 ¤f6 2.c4 ¤c6", "¤")

        assert figurines.candidates([page]) == []


class TestSettling:
    def test_the_board_decides_which_symbol_is_which_piece(self):
        page = page_of(
            "1.d4 ¤f6 2.c4 e6 3.¤c3 ¥b4 4.e3 0-0 5.¥d3 d5 6.¤f3 c5 7.0-0 ¤c6 "
        "8.a3 ¥xc3 9.bxc3 dxc4 10.¥xc4 £c7 11.¥d3 e5 12.£c2 ¦e8 13.¤h4 e4",
            "¤¥£¦",
        )

        settled = figurines.settle([page], ["¤", "¥"])

        assert settled == {"¤": "♞", "¥": "♝"}

    def test_a_book_with_no_symbols_is_left_alone(self):
        page = page_of("1.d4 d5 2.c4 e6 3.Nc3 Nf6")

        assert figurines.settle([page], []) == {}


class TestRewriting:
    def test_the_symbol_takes_the_figurine_place_and_keeps_its_box(self):
        page = page_of("1.d4 ¤f6", "¤")
        before = page.chars[5].bbox

        rewritten = figurines.rewrite([page], {"¤": "♞"})[0]

        assert rewritten.text == "1.d4 ♞f6"
        assert rewritten.chars[5].char == "♞"
        assert rewritten.chars[5].bbox == before
