#!/usr/bin/env python3
"""Which book to add to the corpus, and which of its pages to run.

A complete book is not a fixture. Most of its pages are prose, front matter or
index, and the pipeline's numbers only mean something on pages that carry a
line of play. Worse, a book can look ideal and still be unable to score above
zero: a puzzle book or a collection of analysis fragments starts from a
diagram the pipeline never saw, so every move it reads is illegal from the
first ply. Two of the four books in the corpus are like that, and neither can
be told apart from a good one by its notation style.

    python scripts/choose_pages.py ~/books/*.pdf
        One line per book: pages, notation style, language, whether glyph
        recovery is needed, and — the deciding column — how many pages open a
        game from the initial position.

    python scripts/choose_pages.py book.pdf --window 12
        For one book, the best run of `--window` pages: the one opening the
        most games, densest in move numbers to break the tie. Feed the range
        it prints to `pipeline.run(first_page=..., last_page=...)`.

Ranking by game starts rather than by notation density is deliberate. Density
finds the analysis pages, which are exactly the ones that cannot be replayed.
"""
from __future__ import annotations

import argparse
import re
import sys

from rce_pipeline import extract, notation

#: A piece, however the book writes one: a Unicode figurine, or the initial of
#: any of the alphabets `notation` knows. Kept permissive on purpose — this
#: runs before any detection, on a book nothing is known about yet.
_PIECE = r"[♔-♟KQRBNDTFCLSPTVA]?"

#: White's first move and black's reply, both printed. A page carrying this
#: opens a game from the initial position, which is the one thing that decides
#: whether the book can measure legality end to end.
_GAME_START = re.compile(
    rf"(?<![\d.])1\s*\.?\s*(?:{_PIECE}[a-h][1-8])\s+(?:1\s*\.\.\.|{_PIECE}[a-h][1-8])"
)

_MOVE_NUMBER = re.compile(r"(?<![A-Za-z\d])\d{1,3}\s*\.")

#: Enough characters on the sampled pages to call it a text layer. Below this
#: the book is a scan, and belongs to the OCR path rather than this one.
_MIN_TEXT = 400


def _page_texts(path: str) -> list[str]:
    import fitz

    doc = fitz.open(path)
    try:
        return [doc[i].get_text() for i in range(doc.page_count)]
    finally:
        doc.close()


def _survey(path: str) -> dict[str, object]:
    """One book's verdict, from a sample taken out of its body."""
    texts = _page_texts(path)
    total = len(texts)
    # Front matter and index are skipped: they carry no notation, and a
    # detector fed on them reports a book with no chess in it.
    first = max(1, int(total * 0.15))
    last = min(total, first + 11)
    sample = "".join(texts[first - 1 : last])

    row: dict[str, object] = {
        "path": path,
        "pages": total,
        "starts": sum(1 for t in texts if _GAME_START.search(t)),
        "numbers": sum(len(_MOVE_NUMBER.findall(t)) for t in texts),
    }
    if len(sample.strip()) < _MIN_TEXT:
        row.update(style="no text layer", language="-", glyphs="-")
        return row

    report = notation.detect_notation(
        extract.extract_pages(path, first_page=first, last_page=last)
    )
    row.update(
        style=report.style,
        language=str(report.language or "-"),
        glyphs="required" if report.needs_glyph_recovery else "-",
    )
    return row


def _best_window(path: str, size: int) -> tuple[int, int, int, int]:
    """The run of `size` pages opening the most games, densest to break ties."""
    texts = _page_texts(path)
    if len(texts) <= size:
        # A book shorter than the window is its own window, and its game
        # starts still have to be counted — returning zero here reported the
        # Grivas fixture as opening no game when the survey said three.
        return (
            1,
            len(texts),
            sum(len(_MOVE_NUMBER.findall(t)) for t in texts),
            sum(1 for t in texts if _GAME_START.search(t)),
        )

    best: tuple[tuple[int, int], int] | None = None
    for start in range(len(texts) - size + 1):
        window = texts[start : start + size]
        opens = sum(1 for t in window if _GAME_START.search(t))
        numbers = sum(len(_MOVE_NUMBER.findall(t)) for t in window)
        key = (opens, numbers)
        if best is None or key > best[0]:
            best = (key, start)
    (opens, numbers), start = best
    return start + 1, start + size, numbers, opens


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+")
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        help="report the best run of this many pages for each book",
    )
    args = parser.parse_args()

    rows = []
    for path in args.pdfs:
        try:
            rows.append(_survey(path))
        except Exception as exc:  # a corpus contains broken files
            rows.append({"path": path, "pages": 0, "starts": 0, "numbers": 0,
                         "style": f"error: {type(exc).__name__}",
                         "language": "-", "glyphs": "-"})

    rows.sort(key=lambda r: (-r["starts"], -r["numbers"]))
    width = min(56, max(len(r["path"].rsplit("/", 1)[-1]) for r in rows))
    header = (f"{'book':<{width}} {'pages':>6} {'style':<17} {'lang':<5} "
              f"{'glyphs':<9} {'from move 1':>11}")
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['path'].rsplit('/', 1)[-1][:width]:<{width}} {row['pages']:>6} "
              f"{row['style']:<17} {row['language']:<5} {row['glyphs']:<9} "
              f"{row['starts']:>11}")

    if args.window:
        print()
        for row in rows:
            if row["pages"] < 2:
                continue
            first, last, numbers, opens = _best_window(row["path"], args.window)
            print(f"{row['path'].rsplit('/', 1)[-1][:width]:<{width}} "
                  f"pages {first}-{last}: {numbers} move numbers, {opens} game starts")


if __name__ == "__main__":
    main()
