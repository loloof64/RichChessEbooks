#!/usr/bin/env python3
"""What the glyph classifier is worth on a given scanned book.

Two modes, both over the notation lines of the pages asked for:

    python scripts/eval_glyphs.py book.pdf --model classifier.zip --pages 5-6
        Reports what was found and at what confidence. Works on any book, and
        is the quick check that a new one is being read at all.

    python scripts/eval_glyphs.py book.pdf --model classifier.zip \
        --truth scripts/sample_truth.json
        Scores it: how many of the glyphs actually printed on those pages came
        back, and how many pieces were invented that were never there. `--sweep`
        adds the same numbers across a range of confidence thresholds, which is
        how `glyphs.DEFAULT_MIN_CONFIDENCE` was chosen and how it should be
        re-chosen for a book set in a different face.

The truth file is a hand-read transcript of the pieces on each notation line —
`{"5": ["", "NNRNRQ", ...]}`, one string per line in the order
:func:`scan.notation_lines` returns them, plus the OCR text of each line so
that a segmentation change shows up as a mismatch instead of as a silent
misalignment. Making one takes an hour with the page crops on screen; it is
what turns "the classifier looks good" into a number.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from rce_pipeline import extract, glyphs, scan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", help="the scanned book")
    parser.add_argument("--model", required=True, help="classifier zip, directory or pickle")
    parser.add_argument("--truth", help="hand-read transcript to score against")
    parser.add_argument("--pages", help="page range, e.g. 5-6 (default: the truth's pages, or all)")
    parser.add_argument("--confidence", type=float, default=glyphs.DEFAULT_MIN_CONFIDENCE)
    parser.add_argument("--sweep", action="store_true", help="score across confidence thresholds")
    args = parser.parse_args(argv)

    truth = json.load(open(args.truth, encoding="utf-8")) if args.truth else None
    pages = _page_numbers(args.pages, truth)

    # Detection runs once at a confidence of zero and is filtered afterwards, so
    # a sweep costs one pass rather than one per threshold.
    classifier = glyphs.GlyphClassifier.load(args.model)
    found: dict[int, list[list[glyphs.PieceGlyph]]] = {}
    texts: dict[int, list[str]] = {}
    for page in _read_pages(args.pdf, pages):
        lines = scan.notation_lines(scan.segment_lines(page))
        texts[page.number] = [line.text for line in lines]
        with scan.PageRenderer(args.pdf) as renderer:
            images = [renderer.crop(line) for line in lines]
        detected = glyphs.find_glyphs(images, classifier, min_confidence=0.0)
        found[page.number] = _by_line(images, detected)
        print(f"page {page.number}: {len(lines)} notation lines, "
              f"{sum(len(g) for g in found[page.number])} candidates")

    if truth is None:
        _report_findings(found, texts, args.confidence)
        return 0

    _check_alignment(truth, texts)
    if args.sweep:
        print("\nconfidence  recovered  invented")
        for step in range(30, 71, 5):
            threshold = step / 100
            recovered, total, invented = _score(found, truth, threshold)
            print(f"      {threshold:.2f}  {recovered:3}/{total}   {recovered / total:6.1%}   {invented:3}")
        return 0

    recovered, total, invented = _score(found, truth, args.confidence)
    print(f"\nAt confidence {args.confidence:.2f}: "
          f"{recovered}/{total} glyphs recovered ({recovered / total:.1%}), {invented} invented")
    _report_mismatches(found, truth, texts, args.confidence)
    return 0


def _page_numbers(spec: str | None, truth: dict | None) -> list[int] | None:
    if spec:
        if "-" in spec:
            first, last = spec.split("-", 1)
            return list(range(int(first), int(last) + 1))
        return [int(spec)]
    if truth:
        return sorted(int(key) for key in truth if key != "book")
    return None


def _read_pages(pdf: str, numbers: list[int] | None) -> list[extract.Page]:
    if numbers is None:
        return extract.extract_pages(pdf)
    return [
        page
        for number in numbers
        for page in extract.extract_pages(pdf, first_page=number, last_page=number)
    ]


def _by_line(
    images: list[scan.LineImage], detected: list[glyphs.PieceGlyph]
) -> list[list[glyphs.PieceGlyph]]:
    """Split the page's glyphs back per line, in printed order.

    :func:`find_glyphs` returns a flat list because the caller repairing a page
    does not care which line a glyph came from; scoring against a per-line
    transcript does.
    """
    per_line: list[list[glyphs.PieceGlyph]] = []
    for image in images:
        box = image.line.bbox
        inside = [
            glyph
            for glyph in detected
            if glyph.page == image.line.page
            and box.y <= glyph.bbox.y + glyph.bbox.h / 2 <= box.y + box.h
            and box.x - 5 <= glyph.bbox.x <= box.x + box.w
        ]
        per_line.append(sorted(inside, key=lambda glyph: glyph.bbox.x))
    return per_line


def _line_truth(truth: dict, page: int) -> list[str]:
    entries = truth[str(page)]
    return [entry["pieces"] if isinstance(entry, dict) else entry for entry in entries]


def _check_alignment(truth: dict, texts: dict[int, list[str]]) -> None:
    """Refuse to score a transcript that no longer matches the segmentation."""
    for page, lines in texts.items():
        expected = truth.get(str(page))
        if expected is None:
            continue
        if len(expected) != len(lines):
            print(f"! page {page}: truth has {len(expected)} lines, segmentation gives "
                  f"{len(lines)} — the transcript needs redoing", file=sys.stderr)
            continue
        for index, entry in enumerate(expected):
            if isinstance(entry, dict) and entry.get("text", lines[index]) != lines[index]:
                print(f"! page {page} line {index}: truth recorded {entry['text']!r}, "
                      f"segmentation gives {lines[index]!r}", file=sys.stderr)


def _score(
    found: dict[int, list[list[glyphs.PieceGlyph]]], truth: dict, threshold: float
) -> tuple[int, int, int]:
    recovered = total = invented = 0
    for page, per_line in found.items():
        expected = _line_truth(truth, page)
        for line_glyphs, want in zip(per_line, expected):
            got = "".join(g.piece for g in line_glyphs if g.confidence >= threshold)
            matched = _longest_common(got, want)
            recovered += matched
            invented += len(got) - matched
            total += len(want)
    return recovered, total, invented


def _report_findings(
    found: dict[int, list[list[glyphs.PieceGlyph]]],
    texts: dict[int, list[str]],
    threshold: float,
) -> None:
    counts: Counter[str] = Counter()
    for page, per_line in sorted(found.items()):
        for line_glyphs, text in zip(per_line, texts[page]):
            kept = [g for g in line_glyphs if g.confidence >= threshold]
            counts.update(g.piece for g in kept)
            if kept:
                symbols = "".join(g.figurine for g in kept)
                scores = " ".join(f"{g.piece}{g.confidence:.2f}" for g in kept)
                print(f"  {symbols:8s} {scores:28s} {text[:60]}")
    print(f"\nAt confidence {threshold:.2f}: {sum(counts.values())} pieces — "
          + ", ".join(f"{piece} {count}" for piece, count in counts.most_common()))


def _report_mismatches(
    found: dict[int, list[list[glyphs.PieceGlyph]]],
    truth: dict,
    texts: dict[int, list[str]],
    threshold: float,
) -> None:
    for page, per_line in sorted(found.items()):
        expected = _line_truth(truth, page)
        for index, (line_glyphs, want) in enumerate(zip(per_line, expected)):
            kept = [g for g in line_glyphs if g.confidence >= threshold]
            got = "".join(g.piece for g in kept)
            if got == want:
                continue
            near = " ".join(
                f"{g.piece}{g.confidence:.2f}@{g.width_ratio:.1f}" for g in line_glyphs
            )
            print(f"  page {page} line {index:02d}: want {want!r}, got {got!r}"
                  f"\n      candidates: {near}\n      layer: {texts[page][index][:70]}")


def _longest_common(got: str, want: str) -> int:
    """Length of the longest common subsequence — matches in printed order.

    Order matters and position does not: a glyph missed at the start of a line
    must not make every glyph after it count as wrong too.
    """
    table = [[0] * (len(want) + 1) for _ in range(len(got) + 1)]
    for i, left in enumerate(got):
        for j, right in enumerate(want):
            table[i + 1][j + 1] = (
                table[i][j] + 1 if left == right else max(table[i][j + 1], table[i + 1][j])
            )
    return table[-1][-1]


if __name__ == "__main__":
    raise SystemExit(main())
