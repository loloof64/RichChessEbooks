"""Tests for step 0, an EPUB or a DjVu book turned into the PDF the rest reads."""

import shutil
import subprocess
import zipfile

import pymupdf
import pytest

from rce_pipeline import convert, package


def _epub(path):
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        book.writestr("META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="book.opf" media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>')
        book.writestr("book.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="id">x</dc:identifier><dc:title>t</dc:title>'
            '<dc:language>en</dc:language></metadata><manifest>'
            '<item id="c" href="c.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c"/></spine></package>')
        book.writestr("c.xhtml",
            '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>'
            '<p>1.e4 e5 2.Nf3 Nc6</p></body></html>')
    return str(path)


def test_a_pdf_is_read_as_it_is(tmp_path):
    book = pymupdf.open()
    book.new_page()
    book.save(tmp_path / "book")

    assert convert.to_pdf(str(tmp_path / "book"), str(tmp_path / "work")) == str(tmp_path / "book")


def test_an_epub_becomes_a_pdf_that_keeps_its_text(tmp_path):
    source = _epub(tmp_path / "book.epub")

    converted = convert.to_pdf(source, str(tmp_path / "work"))

    assert package._media_type_of(converted) == "application/pdf"
    with pymupdf.open(converted) as pdf:
        assert "2.Nf3" in pdf[0].get_text()


def test_the_kind_comes_from_the_bytes_not_the_name(tmp_path):
    source = _epub(tmp_path / "book.pdf")
    (tmp_path / "scan.pdf").write_bytes(b"AT&TFORM\x00\x00\x00\x00DJVU")

    assert convert.kind_of(source) == "epub"
    assert convert.kind_of(str(tmp_path / "scan.pdf")) == "djvu"


@pytest.mark.skipif(shutil.which("c44") is None, reason="djvulibre not installed")
def test_a_djvu_becomes_a_pdf_of_the_same_pages(tmp_path):
    page = pymupdf.open()
    page.new_page(width=200, height=300).insert_text((20, 40), "1.e4 e5")
    page[0].get_pixmap(dpi=100).save(tmp_path / "page.ppm")
    subprocess.run(["c44", str(tmp_path / "page.ppm"), str(tmp_path / "-book.djvu")], check=True)

    converted = convert.to_pdf(str(tmp_path / "-book.djvu"), str(tmp_path / "work"))

    with pymupdf.open(converted) as pdf:
        assert pdf.page_count == 1


def test_the_archive_carries_the_converted_pdf(tmp_path):
    from rce_pipeline.pipeline import run

    source = _epub(tmp_path / "book.epub")
    run(source, work_dir=str(tmp_path / "work"), output_path=str(tmp_path / "book.rce"),
        read_pictures=False, write_artefacts=False)

    with zipfile.ZipFile(tmp_path / "book.rce") as archive:
        assert "source/book.pdf" in archive.namelist()
