"""Tests for step 5, the archive's manifest."""

import pymupdf

from rce_pipeline import package


def test_a_pdf_with_no_extension_is_still_a_pdf(tmp_path):
    # Laurent renamed a book `UneBoussoleSurEchiquier_XavierParmentier`, with
    # no `.pdf`: the pipeline read it whole, the manifest called it
    # application/octet-stream, and the reader refused the archive.
    book = pymupdf.open()
    book.new_page()
    book.save(tmp_path / "UneBoussole")

    assert package._media_type_of(str(tmp_path / "UneBoussole")) == "application/pdf"


def test_the_extension_still_answers_for_what_is_not_a_pdf(tmp_path):
    (tmp_path / "book.epub").write_bytes(b"PK\x03\x04")

    assert package._media_type_of(str(tmp_path / "book.epub")) == "application/epub+zip"
