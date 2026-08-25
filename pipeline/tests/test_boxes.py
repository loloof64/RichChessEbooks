"""Tests for moving a scan's tap zones onto the ink they name.

The rendering itself is exercised on the corpus; what is pinned down here is
what the rendering is read with — which run of ink belongs to this word, and
where a token's box lands once it is found.
"""

import numpy as np

from rce_pipeline.boxes import _ink_of, _remapped, _words
from rce_pipeline.extract import BBox, Char, Page

CHAR_WIDTH = 6.0
LINE_TOP, LINE_HEIGHT = 100.0, 12.0
PAGE_HEIGHT = 400.0


def page_of(text: str, *, x: float = 20.0) -> Page:
    """A one-line page, one box per character, laid out left to right.

    Boxes are in PDF points from the bottom of the page, as `extract` gives
    them; a space carries a box like any other character.
    """
    chars = [
        Char(
            char=ch,
            bbox=BBox(x + index * CHAR_WIDTH, PAGE_HEIGHT - LINE_TOP - LINE_HEIGHT,
                      CHAR_WIDTH, LINE_HEIGHT),
            font="GlyphLessFont",
            size=10.0,
        )
        for index, ch in enumerate(text)
    ]
    return Page(number=1, width=595.0, height=PAGE_HEIGHT, text=text, chars=chars)


def sheet(*runs: tuple[float, float], zoom: float = 2.0) -> np.ndarray:
    """A rendering, white but for dark columns over each `(x0, x1)` in points."""
    image = np.full((int(PAGE_HEIGHT * zoom), int(600 * zoom)), 255, dtype=np.uint8)
    for x0, x1 in runs:
        image[
            int(LINE_TOP * zoom) : int((LINE_TOP + LINE_HEIGHT) * zoom),
            int(x0 * zoom) : int(x1 * zoom),
        ] = 0
    return image


class TestWords:
    def test_a_word_is_what_stands_between_two_spaces(self):
        assert _words(page_of("8.g5 hxg5")) == [(0, 4), (5, 9)]

    def test_a_character_with_no_geometry_ends_a_word(self):
        # The line and block breaks `extract` puts in the stream carry a
        # degenerate box and belong to no word.
        page = page_of("e4\nd5")
        page.chars[2].bbox = BBox(0.0, 0.0, 0.0, 0.0)

        assert _words(page) == [(0, 2), (3, 5)]


class TestTheInkOfAWord:
    """The layer spreads `8.g5` over 24 points where the ink covers 18."""

    def test_the_ink_is_found_where_the_layer_says_the_word_is(self):
        page = page_of("8.g5")
        found = _ink_of(sheet((20.0, 38.0)), page, 0, 4, PAGE_HEIGHT, 2.0)

        assert found is not None
        layer_x0, layer_w, ink_x0, ink_w = found
        assert (layer_x0, layer_w) == (20.0, 24.0)
        assert (ink_x0, ink_w) == (20.0, 18.0)

    def test_the_word_before_is_not_this_word(self):
        # The search reaches past the layer's word on both sides, and the ink
        # of the word before sits inside that reach. Without the gap test
        # every box on the page moves a character to the left.
        page = page_of("8.g5")
        found = _ink_of(sheet((10.0, 16.0), (22.0, 40.0)), page, 0, 4, PAGE_HEIGHT, 2.0)

        assert found is not None
        assert found[2] == 22.0

    def test_a_gap_inside_the_word_is_crossed(self):
        page = page_of("8.g5")
        found = _ink_of(
            sheet((20.0, 26.0), (27.0, 38.0)), page, 0, 4, PAGE_HEIGHT, 2.0
        )

        assert found is not None
        assert (found[2], found[3]) == (20.0, 18.0)

    def test_a_word_with_no_ink_at_all_is_left_alone(self):
        page = page_of("8.g5")

        assert _ink_of(sheet(), page, 0, 4, PAGE_HEIGHT, 2.0) is None

    def test_ink_nothing_like_the_layer_s_word_is_refused(self):
        # A rule, or the edge of a diagram, running under the whole line.
        page = page_of("8.g5")

        assert _ink_of(sheet((0.0, 200.0)), page, 0, 4, PAGE_HEIGHT, 2.0) is None


class TestRemapped:
    def test_a_box_keeps_its_place_within_the_word(self):
        # `g5` is the second half of `8.g5`, and stays the second half of it.
        box = BBox(32.0, 288.0, 12.0, 12.0)

        moved = _remapped(box, 20.0, 24.0, 20.0, 18.0)

        assert (moved.x, moved.w) == (29.0, 9.0)

    def test_the_height_is_the_layer_s(self):
        box = BBox(32.0, 288.0, 12.0, 12.0)

        moved = _remapped(box, 20.0, 24.0, 20.0, 18.0)

        assert (moved.y, moved.h) == (288.0, 12.0)
