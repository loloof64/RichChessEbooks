"""Tests for the weight a scan prints its game score in.

The measurement itself needs a rendered page and is exercised on the corpus;
what is pinned down here is the arithmetic around it — the erosion that makes
thickness scale-free, and the split that has to refuse a book setting
everything in one weight as readily as it accepts one that does not.
"""

import numpy as np
import pytest

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
        # Boussole: a split can always be found, and it separates nothing.
        assert _split([0.02] * 30 + [0.03] * 30) is None

    def test_a_weight_that_erodes_away_entirely_is_the_cleanest_split(self):
        # Nothing left of the lighter group at all. The ceiling is zero, which
        # is a perfect separation and not a division to be guarded against.
        assert _split([0.0] * 30 + [0.2] * 30) == pytest.approx(0.1)

    def test_no_ink_anywhere_is_refused(self):
        assert _split([0.0] * 60) is None
