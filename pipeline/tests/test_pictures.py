"""Tests for the positions a book draws rather than sets.

There is no real book here. A board is drawn from a position with invented
pieces — six silhouettes, each in a filled form and an outlined one — over
hatched dark squares, and written into a PDF the way a publisher writes one.
That is the point: nothing in `pictures` knows what a knight looks like, so a
test that used real knights would be testing the drawing rather than the code.
What is asserted is what the module actually claims — that two squares
carrying the same thing come back as the same character, whatever colour the
square, and that the position survives the round trip.
"""

import numpy as np
import pytest

pytest.importorskip("scipy")

from rce_pipeline import diagrams, extract, pictures  # noqa: E402

try:  # PyMuPDF 1.24.3+ renamed the module; `fitz` still works but warns.
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz

#: Side of one square in the drawn board, in pixels. Large enough that an
#: outline is several pixels wide and closes — which is exactly what Tactics'
#: 24 pixels to a square do not manage. See the module docstring.
CELL = 64

#: The frame drawn around the board, as `_board_region` expects to find it.
FRAME = 6

_LIGHT, _INK = 1.0, 0.0


def _disc(radius: int) -> np.ndarray:
    y, x = np.mgrid[0:CELL, 0:CELL] - CELL / 2 + 0.5
    return (y**2 + x**2) <= radius**2


def _diamond(radius: int) -> np.ndarray:
    y, x = np.mgrid[0:CELL, 0:CELL] - CELL / 2 + 0.5
    return (abs(y) + abs(x)) <= radius


def _triangle(up: bool) -> np.ndarray:
    y, x = np.mgrid[0:CELL, 0:CELL] - CELL / 2 + 0.5
    height = y if up else -y
    return (height <= 22) & (height >= -22) & (abs(x) <= (22 - height) / 2)


def _bar(width: int, height: int) -> np.ndarray:
    mask = np.zeros((CELL, CELL), dtype=bool)
    top, left = (CELL - height) // 2, (CELL - width) // 2
    mask[top : top + height, left : left + width] = True
    return mask


def _cross() -> np.ndarray:
    return _bar(14, 48) | _bar(48, 14)


#: One silhouette per kind of piece. What they are drawings of does not
#: matter; that they differ once scaled to the same box does.
SHAPES = {
    "k": _disc(24),
    "q": _diamond(26),
    "r": _bar(44, 44),
    "b": _triangle(up=True),
    "n": _triangle(up=False),
    "p": _cross(),
}


def _hatch() -> np.ndarray:
    """The diagonal strokes a publisher shades a dark square with."""
    y, x = np.mgrid[0:CELL, 0:CELL]
    return ((y + x) % 10) < 2


def _cell(piece: str, dark: bool) -> np.ndarray:
    """One square, drawn: its shading, and the piece standing on it."""
    cell = np.full((CELL, CELL), _LIGHT, dtype=np.float32)
    if dark:
        cell[_hatch()] = _INK
    if piece == ".":
        return cell
    from scipy import ndimage

    shape = SHAPES[piece.lower()]
    # The piece is printed over the shading, with a little air around it, so
    # that no stroke of the hatch is closed off against it into a hole.
    cell[ndimage.binary_dilation(shape, np.ones((7, 7)))] = _LIGHT
    if piece.islower():
        cell[shape] = _INK
    else:
        cell[shape & ~ndimage.binary_erosion(shape, np.ones((7, 7)))] = _INK
    return cell


def board_image(board_fen: str) -> np.ndarray:
    """A drawn board, framed, as a publisher would store it."""
    ranks = [
        "".join("." * int(ch) if ch.isdigit() else ch for ch in rank)
        for rank in board_fen.split("/")
    ]
    side = 8 * CELL + 2 * FRAME
    image = np.full((side + 20, side), _LIGHT, dtype=np.float32)
    image[:FRAME, :] = image[side - FRAME : side, :] = _INK
    image[:side, :FRAME] = image[:side, side - FRAME :] = _INK
    for rank, row in enumerate(ranks):
        for file, piece in enumerate(row):
            top, left = FRAME + rank * CELL, FRAME + file * CELL
            image[top : top + CELL, left : left + CELL] = _cell(piece, (rank + file) % 2 == 1)
    return image


def book(tmp_path, boards, *, text="1 e4 e5 2 Nf3"):
    """A PDF with one board to a page, each followed by a line of text."""
    path = str(tmp_path / "drawn.pdf")
    doc = fitz.open()
    for board_fen in boards:
        image = board_image(board_fen)
        samples = (np.clip(image, 0.0, 1.0) * 255).astype(np.uint8).tobytes()
        pixmap = fitz.Pixmap(fitz.csGRAY, image.shape[1], image.shape[0], samples, 0)
        page = doc.new_page(width=400, height=600)
        page.insert_image(fitz.Rect(40, 40, 240, 250), pixmap=pixmap)
        page.insert_text(fitz.Point(40, 300), text)
    doc.save(path)
    doc.close()
    return path


OPENING = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
MIDDLE = "r1bq1rk1/pp2ppbp/2np1np1/8/2P1P3/2N1BP2/PP2N1PP/R2QKB1R"
ENDGAME = "8/5pk1/6p1/8/8/6P1/5PK1/8"


def test_a_piece_reads_the_same_on_a_light_and_on_a_dark_square():
    """The one claim the whole module rests on."""
    light = pictures._signature(_cell("r", dark=False), _body(_cell("r", dark=False)))
    dark = pictures._signature(_cell("r", dark=True), _body(_cell("r", dark=True)))
    assert float(np.abs(light - dark).mean()) < pictures.MERGE_DISTANCE


def test_an_empty_square_is_the_same_character_whatever_its_colour():
    light = pictures._signature(_cell(".", dark=False), _body(_cell(".", dark=False)))
    dark = pictures._signature(_cell(".", dark=True), _body(_cell(".", dark=True)))
    assert not light.any() and not dark.any()


def test_two_different_pieces_are_two_characters():
    rook = pictures._signature(_cell("r", dark=False), _body(_cell("r", dark=False)))
    knight = pictures._signature(_cell("n", dark=True), _body(_cell("n", dark=True)))
    assert float(np.abs(rook - knight).mean()) > pictures.MERGE_DISTANCE


def test_a_filled_piece_and_an_outlined_one_are_two_characters():
    """Same silhouette, different colour: it is the shading that tells them
    apart, and it is kept beside the shape for exactly this."""
    black = pictures._signature(_cell("r", dark=False), _body(_cell("r", dark=False)))
    white = pictures._signature(_cell("R", dark=False), _body(_cell("R", dark=False)))
    assert float(np.abs(black - white).mean()) > pictures.MERGE_DISTANCE


def _body(cell):
    from scipy import ndimage

    radius = max(1, int(round(CELL * pictures.OPENING_RATIO)))
    return ndimage.binary_opening(
        ndimage.binary_fill_holes(cell < 0.5), structure=np.ones((radius * 2 + 1,) * 2, dtype=bool)
    )


class TestAsPlaced:
    """A picture is read the way the page places it, not the way it is stored.

    Tactics draws every board of the book with `d = -145.5` where Grivas draws
    its with `+145.92`: the same eight ranks, stored bottom to top.
    """

    image = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    def test_a_plain_scaling_leaves_the_picture_alone(self):
        placed = pictures._as_placed(self.image, (146.0, 0.0, 0.0, 146.0, 40.0, 55.0))

        assert placed.tolist() == [[1.0, 2.0], [3.0, 4.0]]

    def test_a_negative_height_turns_the_ranks_back_over(self):
        placed = pictures._as_placed(self.image, (150.0, 0.0, 0.0, -145.5, 36.0, 250.9))

        assert placed.tolist() == [[3.0, 4.0], [1.0, 2.0]]

    def test_a_negative_width_turns_the_files_back_over(self):
        placed = pictures._as_placed(self.image, (-150.0, 0.0, 0.0, 145.5, 36.0, 250.9))

        assert placed.tolist() == [[2.0, 1.0], [4.0, 3.0]]

    def test_a_picture_set_at_an_angle_is_left_as_it_is(self):
        # Not a board this module can cut into sixty-four squares anyway.
        placed = pictures._as_placed(self.image, (0.0, 146.0, -146.0, 0.0, 40.0, 55.0))

        assert placed.tolist() == [[1.0, 2.0], [3.0, 4.0]]


def test_the_frame_is_peeled_and_a_speck_above_it_ignored():
    image = board_image(OPENING)
    image[2, 300] = _INK  # a speck of dirt above the board, as Grivas has one
    top, bottom, left, right = pictures._board_region(image)
    assert top >= FRAME and left >= FRAME
    assert abs((bottom - top) - 8 * CELL) <= 2
    assert abs((right - left) - 8 * CELL) <= 2


def test_a_picture_that_is_not_a_board_is_not_read(tmp_path):
    """No alternating shading, no position: a figure is not a diagram."""
    path = str(tmp_path / "figure.pdf")
    doc = fitz.open()
    image = np.full((520, 520), _LIGHT, dtype=np.float32)
    image[:FRAME, :] = image[-FRAME:, :] = image[:, :FRAME] = image[:, -FRAME:] = _INK
    image[200:320, 200:320] = _INK
    samples = (image * 255).astype(np.uint8).tobytes()
    page = doc.new_page(width=400, height=600)
    page.insert_image(
        fitz.Rect(40, 40, 240, 240),
        pixmap=fitz.Pixmap(fitz.csGRAY, 520, 520, samples, 0),
    )
    doc.save(path)
    doc.close()
    assert pictures.find(path, extract.extract_pages(path)) == []


def test_one_board_teaches_the_others(tmp_path):
    """The whole round trip: draw three positions, learn the characters from
    one of them, and read the other two back."""
    positions = [OPENING, MIDDLE, ENDGAME]
    path = book(tmp_path, positions)
    found = pictures.find(path, extract.extract_pages(path))
    assert len(found) == 3

    table = diagrams.learn([(found[0].rows, [OPENING])])
    assert [diagrams.decode(diagram.rows, table) for diagram in found] == positions


def test_a_board_is_met_where_it_was_printed(tmp_path):
    """The diagram token has to stand before the text under the picture: the
    move number printed there is what says whose move it is."""
    path = book(tmp_path, [MIDDLE], text="14 Nf3 Bg4")
    pages = extract.extract_pages(path)
    (found,) = pictures.find(path, pages)
    assert pages[0].text[found.start :].startswith("14 Nf3")
    assert found.bbox is not None and found.bbox.w > 0


def test_the_offset_never_lands_inside_a_word():
    """Which character of the line below sits lowest is a fraction of a point,
    and Grivas' `14` split into a `1` above the diagram and a `4` below it."""
    from rce_pipeline.extract import BBox, Char, Page

    chars = [
        Char("1", BBox(40.0, 300.0, 5.0, 11.0), "F", 10.0),  # a hair taller
        Char("4", BBox(45.0, 300.0, 5.0, 10.0), "F", 10.0),
        Char(" ", BBox(50.0, 300.0, 3.0, 10.0), "F", 10.0),
        Char("h", BBox(53.0, 300.0, 5.0, 10.0), "F", 10.0),
    ]
    page = Page(number=1, width=400.0, height=600.0, text="14 h", chars=chars)
    assert pictures._offset_for(page, BBox(40.0, 311.0, 150.0, 150.0)) == 0


def test_the_clustering_is_held_to_the_thirteen_things_a_board_can_carry():
    """A fourteenth cluster is a second reading of a piece already found."""
    rng = np.random.default_rng(0)
    kinds = [rng.random(20).astype(np.float32) for _ in range(13)]
    squares = [kind + rng.normal(0, 0.001, 20).astype(np.float32) for kind in kinds for _ in range(6)]
    # One square a long way from any of them, and one a whisker from a kind.
    squares.append(kinds[0] + 0.02)
    labels = pictures._cluster(squares)
    assert len(set(labels)) == 13
    assert labels[-1] == labels[0]


def scan(tmp_path, boards, *, tilt=0.0):
    """A PDF of scanned pages: one image per page, the page itself.

    The board is pasted into a sheet of paper with a few rules of text-like
    ink beside it, which is the situation `_framed_boards` is for — there is
    no picture to ask about, only a page.
    """
    from scipy import ndimage

    path = str(tmp_path / f"scan{tilt}.pdf")
    doc = fitz.open()
    for board_fen in boards:
        sheet = np.full((1000, 760), _LIGHT, dtype=np.float32)
        board = board_image(board_fen)
        if tilt:
            board = ndimage.rotate(board, tilt, reshape=True, cval=_LIGHT, order=1)
        sheet[40 : 40 + board.shape[0], 60 : 60 + board.shape[1]] = board
        for line in range(12):  # something for the rule finder to reject
            sheet[620 + line * 24 : 626 + line * 24, 80:700:9] = _INK
        samples = (np.clip(sheet, 0.0, 1.0) * 255).astype(np.uint8).tobytes()
        page = doc.new_page(width=400, height=530)
        page.insert_image(
            fitz.Rect(0, 0, 400, 530),
            pixmap=fitz.Pixmap(fitz.csGRAY, sheet.shape[1], sheet.shape[0], samples, 0),
        )
        page.insert_text(fitz.Point(40, 500), "14 Nf3 Bg4")
    doc.save(path)
    doc.close()
    return path


def test_a_board_inside_a_scan_is_found_by_its_frame(tmp_path):
    """A scanned book stores the page and nothing else: the board has to be
    found in it, and its frame is what finds it."""
    positions = [OPENING, MIDDLE, ENDGAME]
    path = scan(tmp_path, positions)
    found = pictures.find(path, extract.extract_pages(path))
    assert len(found) == 3

    table = diagrams.learn([(found[0].rows, [OPENING])])
    assert [diagrams.decode(diagram.rows, table) for diagram in found] == positions


def test_a_tilted_scan_is_still_found(tmp_path):
    """A scanned rule is not straight. Measured on SuperAttaquant, a degree
    out of true: the longest unbroken stretch of its top rule is half the
    board. Only that the board is found is asserted — a tilt leaves the grid
    tilted too, and what that costs the reading is measured on the corpus,
    not here."""
    path = scan(tmp_path, [OPENING, MIDDLE, ENDGAME], tilt=0.8)
    assert len(pictures.find(path, extract.extract_pages(path))) == 3


def test_a_scan_tilted_further_than_the_smear_is_still_found(tmp_path):
    """SuperAttaquant's pages are not all a degree out: two of them carry
    boards tilted through nineteen rows over their own width, where the smear
    covers eight. No single row then holds the whole of the top rule — the
    widest gave 554 pixels of 617 — the corner fell outside the side rule's
    column, and the four pages' boards were not found at all."""
    path = scan(tmp_path, [OPENING, MIDDLE, ENDGAME], tilt=1.8)
    assert len(pictures.find(path, extract.extract_pages(path))) == 3


def test_a_rule_reaches_as_far_as_its_rows_reach_between_them(tmp_path):
    ink = np.zeros((12, 300), dtype=bool)
    for step in range(6):  # one rule, drifting down as it crosses
        ink[step, 250 - step * 50 : 300 - step * 50] = True

    assert pictures._rules(ink, 1, 40) == [(0, 5, 0, 300)]


def test_a_second_rule_on_the_same_rows_stays_its_own(tmp_path):
    # Two boards side by side share their rows, and page 199 prints exactly
    # that. What widens a rule has to touch it.
    ink = np.zeros((4, 300), dtype=bool)
    ink[0:2, 0:100] = True
    ink[1:3, 200:300] = True

    assert pictures._rules(ink, 1, 40) == [(0, 2, 0, 100)]


def test_a_page_already_read_is_not_read_again(tmp_path):
    """A diagram font draws a framed board when the page is rendered, so the
    search of the last resort finds it a second time — 45 diagrams on Markos
    where the book prints 25."""
    path = scan(tmp_path, [OPENING, MIDDLE, ENDGAME])
    pages = extract.extract_pages(path)
    assert pictures.find(path, pages, skip_pages={1, 2}) == pictures.find(
        path, [p for p in pages if p.number == 3]
    )


def test_the_two_colours_of_a_piece_are_paired_by_their_silhouette(tmp_path):
    """What makes naming the characters tractable: a piece is the same drawing
    in both colours, so the shape half of the signature pairs them and the
    problem falls from twelve characters onto twelve pieces to six onto six."""
    path = book(tmp_path, [OPENING, MIDDLE, ENDGAME])
    reading = pictures.read(path, extract.extract_pages(path))

    assert len(reading.twins) == 6
    assert reading.empty is not None
    table = diagrams.learn([(reading.diagrams[0].rows, [OPENING])])
    for one, other in reading.twins:
        assert table[one].swapcase() == table[other]
