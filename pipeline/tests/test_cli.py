"""The `rce` command, as a reader runs it."""

import pymupdf

from rce_pipeline import cli


def test_rce_says_which_step_it_is_on(tmp_path, capsys):
    pdf = tmp_path / "book.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "1.e4 e5 2.Nf3 Nc6")
    doc.save(pdf)

    cli.main([str(pdf)])

    captured = capsys.readouterr()
    # Not a terminal here, so one plain line per step and no spinner.
    assert "Reading the moves" in captured.err
    assert "\r" not in captured.err
    assert "Moves:" in captured.out
    assert (tmp_path / "book.rce").exists()
