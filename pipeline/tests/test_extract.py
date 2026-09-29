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
