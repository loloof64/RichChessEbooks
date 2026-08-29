#!/usr/bin/env python3
"""Draw a book's pages with every move the parser read marked on them.

The figures say how much of a book came out clean; they never say *which*
moves, or where on the page the reader would have tapped. Three defects in one
session were found by looking at a page and none of them moved a metric before
it was fixed — a diagram belonging to the next game, a tap zone squeezed onto
half a word, a line running a move behind the book. So this is not a debugging
aid on the side: it is the instrument the rest are checked against.

    python scripts/preview_page.py book.pdf 89 90 --out /tmp

Every move is boxed in the colour of what became of it, and the box is drawn
**outside** the rectangle rather than padded to look tidy — a box padded by two
pixels hides the half-character it is out by, which is the whole point.

    green    clean       nothing stands against this move
    magenta  contradicted a board further down printed a different position
    orange   drifted     legal and in order, but a move behind the book
    blue     below break the line above it died; this is played on a ghost
    red      broken      no legal reading
    grey     unscored    a game the book never printed the start of

A board the diagram reader found is outlined too, labelled with its verdict.
"""
from __future__ import annotations

import argparse
import os
import sys

from rce_pipeline import parse, pipeline

#: status -> (stroke, label). Kept in the order they are worth looking at.
COLOURS = {
    "clean": ((0.0, 0.6, 0.0), "clean"),
    "contradicted": ((0.8, 0.0, 0.8), "contradicted"),
    "drifted": ((0.9, 0.5, 0.0), "drifted"),
    "below_break": ((0.0, 0.3, 0.9), "below a break"),
    "broken": ((0.9, 0.0, 0.0), "broken"),
    "unscored": ((0.5, 0.5, 0.5), "unscored"),
}

VERDICTS = {
    "confirms": (0.0, 0.6, 0.0),
    "seeds": (0.0, 0.3, 0.9),
    "corrects": (0.8, 0.0, 0.8),
    "unread": (0.9, 0.0, 0.0),
    "unreadable": (0.9, 0.0, 0.0),
}


def verdict_of(parsed: parse.ParsedBook) -> dict[str, str]:
    """What `break_diagnosis` counts each move as, move by move.

    The tally is the measurement and this is the same reading spread over the
    page, so the two can never disagree about a move.
    """
    by_id = {m.id: m for m in parsed.moves}
    unscored = {g.id for g in parsed.games if not g.position_known}
    contradicted = set(parsed.contradicted)
    drifted = set(parsed.drifted)

    def below_a_break(move: parse.MoveNode) -> bool:
        parent = move.parent_id
        while parent is not None:
            if by_id[parent].status == "broken":
                return True
            parent = by_id[parent].parent_id
        return False

    out = {}
    for move in parsed.moves:
        if move.game_id in unscored:
            out[move.id] = "unscored"
        elif move.status == "broken":
            out[move.id] = "broken"
        elif below_a_break(move):
            out[move.id] = "below_break"
        elif move.id in contradicted:
            out[move.id] = "contradicted"
        elif move.id in drifted:
            out[move.id] = "drifted"
        elif move.status == "ok":
            out[move.id] = "clean"
        else:
            out[move.id] = move.status
    return out


def draw(pdf_path, parsed, pages, out_dir, zoom=2.0):
    # The package's own handle on PyMuPDF, so this follows it across the
    # `fitz` -> `pymupdf` rename rather than warning on its own.
    from rce_pipeline.extract import fitz

    marks = verdict_of(parsed)
    doc = fitz.open(pdf_path)
    written = []
    for number in pages:
        page = doc[number - 1]
        height = page.rect.height
        for move in parsed.moves:
            if move.page != number or move.bbox is None:
                continue
            colour = COLOURS.get(marks.get(move.id), ((0, 0, 0), "?"))[0]
            box = move.bbox
            # `BBox` measures from the bottom-left of the page and MuPDF draws
            # from the top-left, so the flip `extract` performs once on the way
            # in is undone here on the way out. Drawn wrong, every box lands a
            # line or two from its move and the picture accuses the pipeline of
            # a defect that is the drawing's own.
            rect = fitz.Rect(
                box.x, height - (box.y + box.h), box.x + box.w, height - box.y
            )
            page.draw_rect(rect, color=colour, width=0.7)
        for row, check in enumerate(
            c for c in parsed.diagram_checks if c["page"] == number
        ):
            page.insert_text(
                fitz.Point(24, 24 + 11 * row),
                f"diagram: {check['verdict']}",
                fontsize=8,
                color=VERDICTS.get(check["verdict"], (0, 0, 0)),
            )
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        path = os.path.join(out_dir, f"page_{number:03d}.png")
        pix.save(path)
        written.append(path)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("pages", type=int, nargs="+")
    ap.add_argument("--first", type=int, help="first page to parse (default: the first drawn)")
    ap.add_argument("--last", type=int, help="last page to parse (default: the last drawn)")
    ap.add_argument("--glyph-model", default=os.environ.get("RCE_GLYPH_MODEL"))
    ap.add_argument("--out", default=".")
    args = ap.parse_args(argv)

    first = args.first or min(args.pages)
    last = args.last or max(args.pages)
    # Parsed over the whole range, drawn only where asked: a game runs across
    # pages, and a page read on its own opens in mid-score with nothing to
    # score it against.
    result = pipeline.run(
        args.pdf, first_page=first, last_page=last,
        glyph_model=args.glyph_model, write_artefacts=False,
    )
    os.makedirs(args.out, exist_ok=True)
    for path in draw(args.pdf, result.parsed, args.pages, args.out):
        print(path)
    tally = result.parsed.break_diagnosis()
    print(" ".join(f"{k}={v}" for k, v in tally.items()))


if __name__ == "__main__":
    sys.exit(main())
