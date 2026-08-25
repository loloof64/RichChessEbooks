"""Tests for the piece-glyph recovery pass.

Two halves, tested differently. Writing a recognised symbol back into a page is
geometry over boxes, so those tests build pages by hand the way
`test_scan.py` does, and no classifier is involved. Finding the symbols needs
an image and the trained model, neither of which belongs in a repository; what
is tested there is the part that does not depend on the model — which crops are
offered to it at all — with a stub standing in for it.

What no test here covers is whether the model recognises a knight. That is
measured, not asserted: `scripts/eval_glyphs.py` scores it against a hand-read
page, and the numbers live in the README.
"""

import pytest

from rce_pipeline.extract import GLYPH_FONT, BBox, Char, Page
from rce_pipeline.glyphs import (
    GlyphClassifier,
    PieceGlyph,
    find_glyphs,
    placement_score,
    repair_page,
    spellings,
    unshift_symbols,
)
from rce_pipeline.tokenize import tokenize_pages

CHAR_WIDTH = 5.0
LINE_HEIGHT = 14.0


def page(text: str, *, x: float = 20.0, y: float = 100.0) -> Page:
    """A one-line page whose characters are laid out left to right.

    Every character gets the same box, which is what an OCR layer does: it
    boxes a word and divides that box evenly among the characters it read.
    """
    chars = [
        Char(char, BBox(x + offset * CHAR_WIDTH, y, CHAR_WIDTH, LINE_HEIGHT), "GlyphLessFont", 10.0)
        for offset, char in enumerate(text)
    ]
    return Page(number=1, width=472.0, height=624.0, text=text, chars=chars)


def glyph(piece: str, x: float, w: float, *, y: float = 100.0, confidence: float = 0.8) -> PieceGlyph:
    return PieceGlyph(
        piece=piece,
        confidence=confidence,
        page=1,
        bbox=BBox(x, y, w, LINE_HEIGHT),
        width_ratio=1.9,
    )


class TestRepair:
    def test_replaces_what_the_scanner_read_under_the_symbol(self):
        # "1.Dxe4" — the scanner read D where a knight is printed, and the
        # knight is twice as wide as a letter, so it covers two character boxes.
        repaired = repair_page(page("1.Dxe4"), [glyph("N", 30.0, 2 * CHAR_WIDTH)])

        assert repaired.text == "1.♘e4"

    def test_keeps_a_character_the_symbol_only_half_covers(self):
        # The same knight, one character to the left: it covers "D" entirely and
        # "x" by half. Half is not enough — losing the "x" turns a capture into
        # a quiet move that is just as legal and is not the one in the book.
        repaired = repair_page(page("1.Dxe4"), [glyph("N", 30.0, 1.5 * CHAR_WIDTH)])

        assert repaired.text == "1.♘xe4"

    def test_keeps_the_letter_it_covered_for_the_parser(self):
        # "1.♘bd2" scanned as "1.Dbd2": the symbol covers the scanner's `D`
        # and the `b` that says which knight. Writing the figurine destroys
        # both — and the `b` is the answer to the ambiguity that creates.
        repaired = repair_page(page("1.Dbd2"), [glyph("N", 30.0, 2 * CHAR_WIDTH)])

        assert repaired.text == "1.♘d2"
        assert next(c for c in repaired.chars if c.char == "♘").consumed == "Db"

    def test_the_covered_letter_reaches_the_move_token(self):
        # The offsets survive the rewrite: the token's span indexes the
        # repaired stream, not the one the scanner produced.
        repaired = repair_page(page("1.Dbd2"), [glyph("N", 30.0, 2 * CHAR_WIDTH)])

        move = next(t for t in tokenize_pages([repaired]) if t.kind == "move")
        assert move.text == "Nd2"
        assert move.consumed == "Db"

    def test_symbol_carries_its_own_box_and_font(self):
        repaired = repair_page(page("1.Dxe4"), [glyph("Q", 30.0, 2 * CHAR_WIDTH)])
        written = next(char for char in repaired.chars if char.char == "♕")

        assert written.font == GLYPH_FONT
        assert written.bbox == BBox(30.0, 100.0, 10.0, LINE_HEIGHT)

    def test_inserts_a_symbol_the_scanner_dropped(self):
        # "4... e8" for "4...♖e8" happens: the scanner read nothing where the
        # symbol is printed and closed the gap. There is nothing to replace, so
        # the symbol goes in before the first character printed after it.
        source = page("4...")
        second = page("e8", x=60.0)
        source.chars.extend(second.chars)
        source.text += second.text

        repaired = repair_page(source, [glyph("R", 45.0, 2 * CHAR_WIDTH)])

        assert repaired.text == "4...♖e8"

    def test_leaves_other_pages_alone(self):
        source = page("1.Dxe4")
        elsewhere = PieceGlyph("N", 0.9, 7, BBox(30.0, 100.0, 10.0, LINE_HEIGHT), 1.9)

        assert repair_page(source, [elsewhere]).text == "1.Dxe4"

    def test_applies_several_symbols_to_one_line(self):
        repaired = repair_page(
            page("1.Dxe4 Hxe4"),
            [glyph("N", 30.0, 2 * CHAR_WIDTH), glyph("R", 55.0, 2 * CHAR_WIDTH)],
        )

        assert repaired.text == "1.♘e4 ♖e4"


class TestSpellings:
    """How this book's scanner spells each piece, from the symbols restored.

    Every symbol written back over a page keeps the ink it covered, so a book
    that needed the glyph pass has spelled its own pieces several hundred
    times over with the answer beside each one. The same spellings stand where
    the pass failed, which is where the parser was left asking the board.
    """

    def repaired(self, *inks: tuple[str, str]) -> list[Page]:
        """One page per (ink, piece), the symbol written over the ink."""
        return [
            repair_page(page(f"1.{ink}e4"), [glyph(piece, 30.0, len(ink) * CHAR_WIDTH)])
            for ink, piece in inks
        ]

    def test_the_ink_under_a_symbol_is_how_the_book_spells_it(self):
        # Boussole prints `ltJ` where a knight stands, sixty times over.
        assert spellings(self.repaired(*[("ltJ", "N")] * 3)) == {"ltJ": "N"}

    def test_a_spelling_seen_twice_is_not_believed(self):
        # Two occurrences are a coincidence away from being one.
        assert spellings(self.repaired(*[("ltJ", "N")] * 2)) == {}

    def test_a_spelling_the_book_uses_for_two_pieces_is_dropped(self):
        # Grivas spells 11 queens and 10 kings `'ili`. Nothing there names a
        # piece, and guessing the majority would name one in nine wrongly.
        seen = [("'ili", "Q")] * 3 + [("'ili", "K")] * 3
        assert spellings(self.repaired(*seen)) == {}

    def test_the_odd_misreading_does_not_unseat_a_spelling(self):
        seen = [("ltJ", "N")] * 9 + [("ltJ", "B")]
        assert spellings(self.repaired(*seen)) == {"ltJ": "N"}

    def test_the_ink_is_keyed_as_the_tokeniser_reads_it(self):
        # `normalise` is what the wreck will have been through by the time it
        # is looked up, and it is not the identity: the Grivas book's `...`
        # is three bullets.
        assert spellings(self.repaired(*[("\u2022i.", "B")] * 3)) == {".i.": "B"}


class TestUnshiftSymbols:
    """A symbol written one group to the right of its own ink.

    Tesseract boxes a word and divides that box evenly among the characters it
    read, so a layer that read `ltJ` where a knight is printed puts the boxes
    half a letter out and the symbol lands on the **square** instead. Boussole
    page 65 prints `12.♗xd5 ♘a5?` and the layer comes out `12.i.♗d5 ltJ♘5?`:
    neither move is a move any more, and the game reads a half-move behind the
    book from there to the end of the page.
    """

    def shifted(self, text: str, piece: str, at: int, spellings_: dict) -> str:
        """`text` with `piece` written over the character at `at`."""
        page_ = page(text)
        repaired = repair_page(
            page_, [glyph(piece, 20.0 + at * CHAR_WIDTH, CHAR_WIDTH)]
        )
        return unshift_symbols(repaired, spellings_).text

    def test_the_symbol_goes_back_onto_its_own_ink(self):
        # `12.i.Bd5` for `12.♗xd5`: the bishop landed on the `x` it destroyed.
        assert self.shifted("12.i.xd5", "B", 5, {"i.": "B"}) == "12.♗xd5"

    def test_what_stands_between_the_ink_and_the_symbol_is_the_move(self):
        # `8.i.g♗` for `8.♗g2`: the symbol landed on the rank, and the file
        # stands between it and its ink. Swallowing that `g` would lose the
        # square instead of saving it.
        assert self.shifted("8.i.g2", "B", 5, {"i.": "B"}) == "8.♗g2"

    def test_a_spelling_naming_another_piece_is_not_this_symbol_s_ink(self):
        assert self.shifted("12.i.xd5", "N", 5, {"i.": "B"}) == "12.i.♘d5"

    def test_ink_the_book_never_taught_is_left_alone(self):
        assert self.shifted("12.i.xd5", "B", 5, {"ltJ": "N"}) == "12.i.♗d5"

    def test_the_move_number_keeps_its_dot(self):
        # The book spells its bishop `.i.` as well as `i.`, because the boxes
        # it was learned from ran over the number's dot. Taking that dot away
        # welds the number to the move and loses both.
        assert self.shifted("12.i.xd5", "B", 5, {".i.": "B", "i.": "B"}) == "12.♗xd5"

    def test_a_symbol_that_ate_no_move_is_left_where_it_is(self):
        # It covered the tail of its own ink, which is not the move and is not
        # worth moving anything for.
        assert self.shifted("12.<it>f7", "K", 5, {"<it": "K"}) == "12.<i♔f7"


class TestBrokenFontLeftovers:
    """One printed figurine arriving as several characters.

    A figurine font whose subset is embedded under a generated name maps its
    knight to `liJ` and its bishop to `i..`, and only the first of those sits
    inside the glyph's own box. Replacing that alone left `NiJxc3+` where
    `Nxc3+` was printed, which matches no move pattern — so the move produced
    no token at all and vanished rather than being reported broken.
    """

    def test_the_rest_of_a_multi_character_mapping_is_taken(self):
        repaired = repair_page(page("19 liJd4"), [glyph("N", 20.0 + 3 * CHAR_WIDTH, CHAR_WIDTH)])

        assert repaired.text == "19 \u2658d4"

    def test_a_disambiguating_letter_is_never_eaten(self):
        # `b` can belong to a move, so it survives where `iJ` does not. This is
        # the whole reason the rule is a whitelist of move characters.
        repaired = repair_page(page("liJbd2"), [glyph("N", 20.0, CHAR_WIDTH)])

        assert repaired.text == "\u2658bd2"

    def test_a_single_character_mapping_is_untouched(self):
        repaired = repair_page(page("25 nd7"), [glyph("Q", 20.0 + 3 * CHAR_WIDTH, CHAR_WIDTH)])

        assert repaired.text == "25 \u2655d7"

    def test_leftovers_stop_at_a_space(self):
        # Crossing one would join the figurine to the next word.
        repaired = repair_page(page("l a6"), [glyph("R", 20.0, CHAR_WIDTH)])

        assert repaired.text == "\u2656 a6"


class TestPlacementScore:
    def test_counts_symbols_that_landed_inside_a_move(self):
        assert placement_score([page("1.♘xe4 ♖e8")]) == (2, 2)

    def test_reports_symbols_spliced_into_the_wrong_place(self):
        # What a loosely boxed layer produces: the symbol is right, the
        # characters it replaced were not the ones under it.
        assert placement_score([page("11...♘ZJg3 ♕'gS")]) == (0, 2)


class FakeModel:
    """Stands in for the trained forest: says knight, at a fixed confidence."""

    n_features_in_ = 1767

    def __init__(self, confidence: float = 0.9):
        self.confidence = confidence
        self.seen: list[tuple[int, int]] = []

    def predict_proba(self, features):
        import numpy as np

        rest = (1.0 - self.confidence) / 4
        return np.array([[rest, rest, rest, rest, self.confidence]] * len(features))


class TestCandidates:
    """Which ink the classifier is shown, which is where the rejecting happens."""

    def line_image(self, blobs, *, width=200, height=50):
        """A crop with black rectangles on white, as (x, y, w, h) in pixels."""
        np = pytest.importorskip("numpy")
        pytest.importorskip("skimage")
        Image = pytest.importorskip("PIL.Image")
        import io

        from rce_pipeline.scan import Line, LineImage

        array = np.full((height, width), 255, dtype="uint8")
        for x, y, w, h in blobs:
            array[y : y + h, x : x + w] = 0
        buffer = io.BytesIO()
        Image.fromarray(array).save(buffer, format="PNG")
        line = Line(
            page=1,
            bbox=BBox(20.0, 100.0, width / 5, height / 5),
            text="1.Dxe4",
            spans=((0, 6),),
            column=0,
            coverage=0.95,
        )
        return LineImage(
            line=line,
            png=buffer.getvalue(),
            width=width,
            height=height,
            scale=5.0,
            clip=BBox(20.0, 100.0, width / 5, height / 5),
        )

    def test_offers_the_wide_square_blob_and_not_the_letters(self):
        # Four letters 10 wide and one symbol 20 wide and 20 tall: the letters
        # are the majority, so they set the width everything is measured
        # against, and only the symbol is far enough above it.
        letters = [(x, 10, 10, 20) for x in (0, 20, 40, 60)]
        model = FakeModel()

        glyphs = find_glyphs([self.line_image(letters + [(100, 8, 20, 20)])], GlyphClassifier(model))

        assert [(g.piece, round(g.confidence, 2)) for g in glyphs] == [("N", 0.9)]

    def test_rejects_a_run_of_touching_letters(self):
        # `xe4` set in bold touches at 360 dpi and reaches the recogniser as one
        # blob. It is wide enough to look like a symbol and nothing like square.
        letters = [(x, 10, 10, 20) for x in (0, 20, 40, 60)]
        model = FakeModel()

        glyphs = find_glyphs([self.line_image(letters + [(100, 10, 32, 20)])], GlyphClassifier(model))

        assert glyphs == []

    def test_rejects_a_symbol_the_model_is_unsure_about(self):
        letters = [(x, 10, 10, 20) for x in (0, 20, 40, 60)]
        model = FakeModel(confidence=0.3)

        glyphs = find_glyphs([self.line_image(letters + [(100, 8, 20, 20)])], GlyphClassifier(model))

        assert glyphs == []

    def test_maps_the_symbol_back_to_page_coordinates(self):
        letters = [(x, 10, 10, 20) for x in (0, 20, 40, 60)]
        image = self.line_image(letters + [(100, 8, 20, 20)])

        found = find_glyphs([image], GlyphClassifier(FakeModel()))[0]

        # 5 pixels per point, crop origin at x=20, and the crop's top edge is
        # the high-y edge of the clip: y = 100 + 10 - (8 + 20) / 5.
        assert found.bbox == BBox(40.0, 104.4, 4.0, 4.0)


class TestModelGuard:
    def test_refuses_a_model_expecting_other_features(self):
        class Other:
            n_features_in_ = 900

        with pytest.raises(ValueError, match="900"):
            GlyphClassifier(Other())
