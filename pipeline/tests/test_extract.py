"""Tests for step 1 on a page that is a picture of a page."""

import shutil

import pytest

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz

from rce_pipeline import extract


def picture_of(columns: list[str], path) -> str:
    """A one-page PDF whose only content is an image of `columns`, side by side.

    Set as Fabrice's documents are: two columns of prose split by a rule.
    """
    filler = "\n".join(["Les Blancs preparent leur attaque de minorite."] * 12)
    typed = fitz.open()
    page = typed.new_page()
    page.draw_line((297, 50), (297, 500))
    for index, text in enumerate(columns):
        page.insert_textbox(fitz.Rect(60 + 245 * index, 60, 290 + 245 * index, 500),
                            f"{text}\n{filler}", fontsize=10)
    image = page.get_pixmap(dpi=200)
    pictured = fitz.open()
    pictured.new_page().insert_image(fitz.Rect(0, 0, 595, 842), pixmap=image)
    pictured.save(path)
    return str(path)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="needs tesseract")
def test_a_picture_page_is_read_column_by_column(tmp_path):
    pdf = picture_of(
        ["1.d4 Cf6 2.c4 e6\nfirst column\nends here",
         "17.a3 g5 18.b4\nsecond column\nends here"],
        tmp_path / "picture.pdf",
    )
    (page,) = extract.extract_pages(pdf)
    text = " ".join(page.text.split())
    assert "1.d4 Cf6 2.c4 e6 first column ends here" in text
    assert "17.a3 g5 18.b4 second column ends here" in text
    start = page.text.index("Cf6")
    box = page.bbox_for(start, start + 3)
    assert box is not None and box.x < 300  # in the left column, in PDF points


def test_the_running_head_and_the_folio_are_not_the_book(tmp_path):
    # Sakaev prints its title and the page number at the head of every page,
    # and the layer puts them between the last move of one page and the first
    # of the next: "22.♖f3 | 72 The Complete Manual of Positional Chess |
    # ♕xc5+", which ended the line on page 72.
    book = fitz.open()
    for number in range(1, 5):
        page = book.new_page(width=482, height=666)
        page.insert_text((66, 30), "The Complete Manual of Positional Chess", fontsize=9)
        page.insert_text((68, 620), str(number), fontsize=9)
        page.insert_text((62, 100), f"{number}.e4 e5", fontsize=10)
    book.save(tmp_path / "book.pdf")

    pages = extract.extract_pages(str(tmp_path / "book.pdf"))

    assert [" ".join(page.text.split()) for page in pages] == [
        f"{number}.e4 e5" for number in range(1, 5)
    ]


def test_a_column_the_stream_left_mid_paragraph_is_finished_first(tmp_path):
    # Grivas page 16: the layer hands over the left column down to "relatively
    # minimal", then the right column's new game, then "value. Indeed, 19
    # ♗xa8?" on the very next left line -- so the old game's moves were read
    # inside the new one.
    book = fitz.open()
    page = book.new_page(width=432, height=648)
    page.insert_text((24, 100), "19 e5! The black rook is of minimal", fontsize=10)
    page.insert_text((223, 60), "Grivas - Szkudlarek", fontsize=10)
    page.insert_text((223, 80), "1 c4 f5 2 Nc3 Nf6", fontsize=10)
    page.insert_text((24, 112), "value. Indeed, 19 Bxa8? Bxc3+!", fontsize=10)
    page.insert_text((223, 300), "5...fxe4 Here 5...e5", fontsize=10)
    book.save(tmp_path / "book.pdf")

    (page,) = extract.extract_pages(str(tmp_path / "book.pdf"))

    assert " ".join(page.text.split()) == (
        "19 e5! The black rook is of minimal value. Indeed, 19 Bxa8? Bxc3+! "
        "Grivas - Szkudlarek 1 c4 f5 2 Nc3 Nf6 5...fxe4 Here 5...e5"
    )


def test_a_right_column_welded_to_the_left_one_waits_for_it():
    # Grivas page 27: one block holds the left column down to "achieving a
    # good position." and the right column's head ("19...gxf6"), handed over
    # before the left column's own "13 Qe1 b6" -- gxf6 was played after h6.
    def line(x0, y0, x1, text):
        return {"bbox": (x0, y0, x1, y0 + 10),
                "spans": [{"chars": [{"c": c} for c in text]}]}

    def block(*lines):
        return {"lines": list(lines)}

    welded = block(line(24, 194, 212, "20 Nxe6 fxe6 21 Bd4 b6"),
                   line(24, 206, 209, "22 Rb1 Rf7, achieving a good posi-"),
                   line(24, 219, 44, "tion."),
                   line(235, 218, 329, "19...gxf6 20 Qxf6 Rg8"),
                   line(235, 231, 411, "20...Kg8 21 Rf1! Qe7"))
    label = block(line(24, 267, 34, "W"), line(224, 267, 410, "should have tried"))
    below = block(line(35, 410, 212, "13 Qe1 b6 14 fxe5! dxe5"))
    right = block(line(234, 278, 269, "21 Bf4!"))

    order = extract._cut_at_the_gutter([welded, label, below, right], 433)

    assert ["".join(c["c"] for s in l["spans"] for c in s["chars"])
            for b in order for l in b["lines"]] == [
        "20 Nxe6 fxe6 21 Bd4 b6", "22 Rb1 Rf7, achieving a good posi-", "tion.",
        "W", "13 Qe1 b6 14 fxe5! dxe5",
        "19...gxf6 20 Qxf6 Rg8", "20...Kg8 21 Rf1! Qe7", "should have tried", "21 Bf4!",
    ]


def test_a_two_column_table_of_short_lines_is_left_alone():
    def block(*rows):
        return {"lines": [{"bbox": (x, y, x + 30, y + 10),
                           "spans": [{"chars": [{"c": c} for c in t]}]}
                          for x, y, t in rows]}

    table = block((24, 100, "1 e4"), (250, 100, "e5"), (24, 112, "2 Nf3"), (250, 112, "Nc6"))
    assert extract._cut_at_the_gutter([table], 433) == [table]
