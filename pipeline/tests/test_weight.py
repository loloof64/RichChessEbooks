"""Tests for the weight a scan prints its game score in.

The measurement itself needs a rendered page and is exercised on the corpus;
what is pinned down here is the arithmetic around it — the erosion that makes
thickness scale-free, and the split that has to refuse a book setting
everything in one weight as readily as it accepts one that does not.
"""

import numpy as np
import pytest

from rce_pipeline import weight
from rce_pipeline.weight import _eroded, _split


class TestErosion:
    def test_a_pixel_survives_only_with_all_eight_neighbours(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[1:4, 1:4] = True

        eroded = _eroded(mask)

        assert eroded.sum() == 1
        assert eroded[2, 2]

    def test_a_hairline_disappears(self):
        # One pixel wide, however long: nothing has a neighbour either side.
        mask = np.zeros((9, 3), dtype=bool)
        mask[:, 1] = True

        assert _eroded(mask).sum() == 0

    def test_a_stem_keeps_its_core(self):
        # Three pixels wide: the middle column survives, less its two ends.
        mask = np.zeros((9, 5), dtype=bool)
        mask[:, 1:4] = True

        assert _eroded(mask).sum() == 7

    def test_the_page_beyond_the_box_is_not_ink(self):
        # A block running to the edge erodes there, exactly as it would if the
        # box had been cropped a pixel wider.
        mask = np.ones((4, 4), dtype=bool)

        assert _eroded(mask).sum() == 4


class TestSplit:
    def test_two_weights_are_separated(self):
        # A hairline that all but vanishes, and a stem that keeps a quarter.
        values = [0.00, 0.01, 0.02, 0.01, 0.00] * 8 + [0.24, 0.27, 0.22, 0.26] * 10

        split = _split(values)

        assert split is not None
        assert 0.02 < split < 0.22

    def test_one_weight_throughout_is_refused(self):
        # Every scan whose publisher marked nothing: one unbroken band.
        assert _split([n / 200 for n in range(60)]) is None

    def test_two_groups_that_touch_are_refused(self):
        # A split can always be found; this one separates nothing.
        assert _split([0.02] * 30 + [0.03] * 30) is None

    def test_a_tail_of_bad_boxes_does_not_hide_two_weights(self):
        # Boussole, and the reason it was written down as marking its score in
        # no way the ink could show. Its two weights are plain to the eye and a
        # tenth of its boxes run over a neighbouring letter or a diagram's
        # edge, landing between the two groups. Read at the extremes those
        # strays fill the band; read at the quartiles the groups still stand
        # apart.
        strays = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
        assert _split([0.00] * 30 + strays + [0.20] * 30) is not None

    def test_a_weight_that_erodes_away_entirely_is_the_cleanest_split(self):
        # Nothing left of the lighter group at all. The ceiling is zero, which
        # is a perfect separation and not a division to be guarded against.
        assert _split([0.0] * 30 + [0.2] * 30) == pytest.approx(0.1)

    def test_no_ink_anywhere_is_refused(self):
        assert _split([0.0] * 60) is None

    def test_a_bold_number_at_the_heavier_group_s_foot_is_bold(self):
        # A scan's page 43: plain numbers at 0.00-0.02, bold ones from 0.09
        # up to 0.3, and `32...` at 0.089. Otsu's split, dragged up by the
        # heavier group's long tail, put it among the plain ones and the score
        # resumed on the wrong move. The two groups' edges say where the gap is.
        # Proportions as the book's 5818 numbers measure, a tenth of them.
        plain = [0.0] * 222 + [0.01] * 36 + [0.02] * 10 + [0.03] * 2
        bold = ([0.075] + [0.085] * 2 + [0.089] * 4 + [0.10] * 14 + [0.11] * 25
                + [0.12] * 31 + [0.13] * 25 + [0.14] * 19 + [0.15] * 13 + [0.16] * 20
                + [0.17] * 17 + [0.18] * 27 + [0.22] * 60 + [0.28] * 40)
        split = _split(plain + bold)

        assert split is not None and 0.02 < split < 0.089


def test_a_black_number_keeps_the_whole_of_its_digit():
    # `4 ... exf4` on Grivas page 28: the box runs over the spaced dots, and a
    # quarter of it for the `4` of `4...` cut the digit to two thirds. What
    # was left measured plain, and the game's own line was read as analysis.
    from rce_pipeline.extract import BBox
    from rce_pipeline.tokenize import Token

    number = Token(kind="move_number", text="4...", raw="4 ...", page=1, start=0, end=5,
                   bbox=BBox(236.0, 100.0, 12.2, 10.72))

    (cropped,) = weight._digits_of([number])

    assert cropped.bbox.w >= 4.5

