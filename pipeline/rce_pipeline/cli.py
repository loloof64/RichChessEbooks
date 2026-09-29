"""`rce livre.pdf` — the pipeline from a terminal, for someone who never opens it."""

from __future__ import annotations

import argparse
import importlib.util
import os
import tempfile
import warnings
from importlib.resources import files

from . import __version__
from .pipeline import run

LANGUAGES = ("en", "fr", "de", "es", "it", "nl")
FULL_INSTALL = (
    'pipx install --force "rce-pipeline[glyphs,pictures] @ '
    'git+https://github.com/loloof64/RichChessEbooks.git#subdirectory=pipeline"'
)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="rce", description="Turn a PDF chess book into a .rce archive for the reader app."
    )
    ap.add_argument("pdf", help="the book")
    ap.add_argument("-o", "--output", help="where to write the .rce (default: beside the PDF)")
    ap.add_argument("--first", type=int, default=1, metavar="PAGE", help="first page to read")
    ap.add_argument("--last", type=int, metavar="PAGE", help="last page to read")
    ap.add_argument(
        "--lang", choices=LANGUAGES,
        help="the book's language, for a book in letters: worth setting, a wrong "
             "guess yields legal but wrong moves",
    )
    ap.add_argument("--version", action="version", version=f"rce {__version__}")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.pdf):
        ap.error(f"no such file: {args.pdf}")
    output = args.output or os.path.splitext(args.pdf)[0] + ".rce"
    # Without the `glyphs` extra a scan cannot be read, and the report says so;
    # a book with a usable text layer never needed it.
    model = (
        str(files(__package__) / "data" / "classifier.pkl")
        if importlib.util.find_spec("sklearn") else None
    )

    with tempfile.TemporaryDirectory() as work_dir, warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        result = run(
            args.pdf, work_dir=work_dir, output_path=output,
            first_page=args.first, last_page=args.last,
            force_language=args.lang, glyph_model=model, write_artefacts=False,
        )
    # A step skipped for a missing extra names a `pip install`, which is not
    # how this was installed; the reader gets the one command that fixes it.
    missing_extra = [w for w in caught if "rce-pipeline[" in str(w.message)]
    for w in caught:
        if w not in missing_extra:
            warnings.showwarning(w.message, w.category, w.filename, w.lineno)
    print(result.report())
    if missing_extra or (model is None and result.notation.needs_glyph_recovery):
        print(f"\nThis book needs the full install (~400 MB). Run:\n  {FULL_INSTALL}\n"
              "then run rce again.")


if __name__ == "__main__":
    main()
