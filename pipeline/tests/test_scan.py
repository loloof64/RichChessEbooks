"""Tests for the line segmentation a scanned book needs.

These build pages directly rather than reading a PDF: the job under test is
turning a bag of OCR boxes back into the lines a book printed, and that is
geometry, not a document. The page rendering on the other side of the module
is checked by looking at the crops, which no assertion replaces.

The layouts here are the ones that were wrong before they were tested: a
narrow gutter between two columns, boxes of the same line reported
separately, and consecutive lines whose boxes overlap.
"""

import pytest

from rce_pipeline.extract import BBox, Char, Page
from rce_pipeline.scan import Line, notation_lines, segment_lines, split_columns

#: Body type in the book this was written against: 14 point lines, 5 point
#: characters, a 7 point gutter between two 205 point columns.
LINE_HEIGHT = 14.0
CHAR_WIDTH = 5.0


def page(*fragments: tuple[str, float, float], width: float = 472.0, height: float = 624.0) -> Page:
    """A page whose text is `fragments`, each given as (text, x, y).

    Fragments are laid out one character after another from their own origin,
    and separated in the character stream the way the extractor separates the
    lines it reads.
    """
    chars: list[Char] = []
    text_parts: list[str] = []
    for index, (text, x, y) in enumerate(fragments):
        if index:
            chars.append(Char("\n", BBox(0.0, 0.0, 0.0, 0.0), "", 0.0))
            text_parts.append("\n")
        for offset, char in enumerate(text):
            box = BBox(x + offset * CHAR_WIDTH, y, CHAR_WIDTH, LINE_HEIGHT)
            chars.append(Char(char, box, "GlyphLessFont", 10.0))
        text_parts.append(text)
    return Page(number=1, width=width, height=height, text="".join(text_parts), chars=chars)


def texts(lines: list[Line]) -> list[str]:
    return [line.text for line in lines]


class TestFragments:
    def test_joins_pieces_of_one_printed_line(self):
        lines = segment_lines(page(("4...", 36.0, 32.0), ("g6 5.Qxh7+", 59.0, 32.0)))

        assert texts(lines) == ["4... g6 5.Qxh7+"]

    def test_keeps_separate_lines_apart(self):
        lines = segment_lines(
            page(("premiere ligne dun paragraphe", 20.0, 60.0),
                 ("seconde ligne du paragraphe", 20.0, 46.0))
        )

        assert texts(lines) == [
            "premiere ligne dun paragraphe",
            "seconde ligne du paragraphe",
        ]

    def test_reads_a_line_left_to_right_whatever_the_order_of_the_boxes(self):
        lines = segment_lines(page(("sacrifie.", 120.0, 40.0), ("le materiel", 20.0, 40.0)))

        assert texts(lines) == ["le materiel sacrifie."]

    def test_orders_lines_down_the_page(self):
        lines = segment_lines(page(("basse", 20.0, 40.0), ("haute", 20.0, 300.0)))

        assert texts(lines) == ["haute", "basse"]


class TestColumns:
    #: Two columns, 7 points apart — the narrow gutter that a rule based on
    #: distance alone gets wrong.
    LEFT = 20.0
    RIGHT = 232.0

    def two_columns(self, *, aligned: bool) -> Page:
        fragments = []
        for index in range(10):
            y = 500.0 - index * LINE_HEIGHT
            fragments.append((f"ligne gauche numero {index}", self.LEFT, y))
            # `aligned` puts both columns on the same baselines, which is the
            # case a vertical-overlap rule cannot tell from one wide line.
            offset = 0.0 if aligned else LINE_HEIGHT / 2
            fragments.append((f"ligne droite numero {index}", self.RIGHT, y - offset))
        return page(*fragments)

    @pytest.mark.parametrize("aligned", [True, False])
    def test_never_joins_a_line_to_the_column_beside_it(self, aligned):
        lines = segment_lines(self.two_columns(aligned=aligned))

        assert len(lines) == 20
        assert all(line.text.count("ligne") == 1 for line in lines)

    def test_reads_one_column_before_the_next(self):
        lines = segment_lines(self.two_columns(aligned=True))

        assert all("gauche" in line.text for line in lines[:10])
        assert all("droite" in line.text for line in lines[10:])

    def test_finds_the_gutter(self):
        boxes = [BBox(20.0, y, 205.0, LINE_HEIGHT) for y in range(100, 300, 14)]
        boxes += [BBox(232.0, y, 205.0, LINE_HEIGHT) for y in range(100, 300, 14)]

        # Anywhere in the white between the two columns is a correct answer.
        assert split_columns(boxes, 472.0) == pytest.approx([232.0], abs=7.0)

    def test_reports_no_column_on_a_page_of_full_width_lines(self):
        boxes = [BBox(20.0, y, 420.0, LINE_HEIGHT) for y in range(100, 400, 14)]

        assert split_columns(boxes, 472.0) == []

    def test_leaves_a_running_head_out_of_both_columns(self):
        # The head straddles the gutter, so it belongs to no column and stays
        # a line of its own instead of joining whatever it overlaps.
        head = ("14. Preparez-vous au sacrifice", 168.0, 600.0)
        body = [(f"ligne {i}", x, 500.0 - i * LINE_HEIGHT)
                for i in range(8) for x in (20.0, 232.0)]
        lines = segment_lines(page(head, *body))

        assert "14. Preparez-vous au sacrifice" in texts(lines)
        assert len(lines) == 17


class TestOverlappingBoxes:
    def test_gives_the_overlap_to_the_line_above(self):
        # OCR boxes are taller than their type: these two overlap by 4 points.
        lines = segment_lines(page(("jouant g5,", 20.0, 100.0), ("le calcul", 20.0, 90.0)))

        upper, lower = lines
        # The line above keeps its box, descenders and all; the line below
        # starts where the one above stops.
        assert upper.bbox.y == 100.0
        assert upper.bbox.y + upper.bbox.h == 114.0
        assert lower.bbox.y + lower.bbox.h == 100.0

    def test_leaves_lines_that_do_not_overlap_alone(self):
        lines = segment_lines(page(("jouant g5,", 20.0, 100.0), ("le calcul", 20.0, 80.0)))

        assert [line.bbox.h for line in lines] == [LINE_HEIGHT, LINE_HEIGHT]


class TestDiagramDebris:
    def test_drops_a_row_of_a_chessboard(self):
        # A rank of a board reaches MuPDF as a few narrow boxes strung across
        # the width of the diagram: the rank labels and whatever the scanner
        # made of the pieces.
        lines = segment_lines(
            page(("8", 257.0, 300.0), ("eo", 287.0, 300.0), ("oe", 360.0, 300.0),
                 ("8", 412.0, 300.0), ("une ligne de texte ordinaire", 20.0, 200.0))
        )

        assert texts(lines) == ["une ligne de texte ordinaire"]

    def test_drops_bleed_through_from_the_facing_page(self):
        # Half-height ghosts of the type on the other side of the sheet.
        ghost = Page(
            number=1, width=472.0, height=624.0,
            text="tress",
            chars=[Char(c, BBox(20.0 + i * 3, 300.0, 3.0, 4.0), "GlyphLessFont", 4.0)
                   for i, c in enumerate("tress")],
        )

        assert segment_lines(ghost) == []


class TestNotationLines:
    def test_selects_a_line_carrying_a_move_number(self):
        lines = segment_lines(
            page(("1.Dxe4! Acxe4 2.Hxe4!", 34.0, 300.0),
                 ("Voila qui pourrait fournir", 34.0, 280.0))
        )

        assert texts(notation_lines(lines, context=0)) == ["1.Dxe4! Acxe4 2.Hxe4!"]

    def test_ignores_a_square_named_in_prose(self):
        # "sur la case e4." ends in a digit and a dot too, and a chess book's
        # prose does this on nearly every line.
        lines = segment_lines(page(("noire sur la case e4, de facon a ce que", 20.0, 300.0)))

        assert notation_lines(lines, context=0) == []

    def test_takes_the_line_below_along(self):
        # A sequence broken by the line break continues with a move that has
        # nothing to announce it.
        lines = segment_lines(
            page(("de clouer la piece qui reprendra en jouant 26.Axf6", 20.0, 300.0),
                 ("Wxe5. Au vu de la position de la Tour noire", 20.0, 280.0),
                 ("en a6, elle aura fort a faire pour defendre", 20.0, 260.0))
        )

        selected = texts(notation_lines(lines, context=1))
        assert len(selected) == 2
        assert selected[1].startswith("Wxe5.")

    def test_does_not_take_the_line_below_across_a_column(self):
        body = [(f"ligne gauche {i}", 20.0, 500.0 - i * LINE_HEIGHT) for i in range(9)]
        body += [(f"ligne droite {i}", 232.0, 500.0 - i * LINE_HEIGHT) for i in range(9)]
        # The last line of the left column carries the move number.
        body[8] = ("gauche 26.Axf6", 20.0, 500.0 - 8 * LINE_HEIGHT)
        lines = segment_lines(page(*body))

        selected = notation_lines(lines, context=1)
        assert texts(selected) == ["gauche 26.Axf6"]
