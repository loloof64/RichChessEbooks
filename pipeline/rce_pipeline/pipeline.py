"""The five steps, wired together.

Each step writes its artefact to `work_dir` before the next one starts, so a
step can be re-run — and its code changed — without redoing the ones before
it. On a 400-page book the extraction pass is by far the slowest, and it is
the one you least often need to repeat.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from . import extract, notation, package, parse, tokenize

ARTEFACTS = {
    "pages": "01_pages.json",
    "glyphs": "01b_glyphs.json",
    "notation": "02_notation.json",
    "tokens": "03_tokens.json",
    "moves": "04_moves.json",
}


@dataclass
class PipelineResult:
    pages: list[extract.Page]
    notation: notation.NotationReport
    tokens: list[tokenize.Token]
    parsed: parse.ParseResult
    rce_path: str | None
    #: Piece symbols recovered from the page images, empty unless the book
    #: needed it and a `glyph_model` was given.
    glyphs: list[Any] = field(default_factory=list)

    def report(self) -> str:
        counts = self.parsed.counts()
        lines = [
            self.notation.summary(),
            "",
        ]
        if self.glyphs:
            from . import glyphs as glyph_step

            placed, total = glyph_step.placement_score(self.pages)
            share = placed / total if total else 0.0
            lines.append(
                f"Symbols:     {total} recovered, {placed} spliced into a move ({share:.0%})"
                + ("" if share >= 0.75 else "  <- low: see glyphs.placement_score")
            )
        lines += [
            f"Pages read:  {len(self.pages)}",
            f"Tokens:      {len(self.tokens)}",
            f"Games:       {counts['games']}",
            f"Moves:       {counts['moves']}"
            f"  (ok {counts['ok']}, uncertain {counts['uncertain']}, broken {counts['broken']})",
        ]
        breaks = self.parsed.break_diagnosis()
        lines += [
            # `ok` alone flatters a long line that broke early: see
            # `ParseResult.break_diagnosis`.
            f"Trusted:     {breaks['clean']} of those ok moves have no break above them"
            f"  ({breaks['below_break']} do)",
            f"Breaks:      {breaks['first_breaks']} lines died"
            f"  ({breaks['cascade']} further moves read below them)",
            f"Skipped:     {counts['skipped']} move-shaped tokens rejected before validation",
        ]
        diagnosis = self.parsed.ambiguity_diagnosis()
        if diagnosis["total"]:
            lines.append(
                f"Ambiguous:   {diagnosis['total']} moves named a square two pieces reach"
                f"  ({diagnosis['settled_from_consumed']} settled from the figurine,"
                f" {diagnosis['downstream_of_repair']} below an earlier repair)"
            )
            # A book whose ambiguities mostly sit below a repair is not asking
            # for a cleverer disambiguator: it is reporting that the repairs
            # above them put the board somewhere the book never went. See
            # `ParseResult.ambiguity_diagnosis`.
            if diagnosis["downstream_of_repair"] > diagnosis["clean_line"]:
                lines.append(
                    "             <- most sit below a repair: suspect the repairs, "
                    "not the disambiguation"
                )
        if self.rce_path:
            lines.append(f"\nArchive:     {self.rce_path}")
        return "\n".join(lines)

    def problems(self, limit: int = 20) -> list[parse.MoveNode]:
        """Moves worth a human look, worst first."""
        flagged = [m for m in self.parsed.moves if m.status != "ok"]
        flagged.sort(key=lambda m: (m.status != "broken", m.confidence))
        return flagged[:limit]


def run(
    pdf_path: str,
    *,
    work_dir: str = "work",
    output_path: str | None = None,
    first_page: int = 1,
    last_page: int | None = None,
    sort_blocks: bool = False,
    strict_numbering: bool = True,
    force_notation: str | None = None,
    force_language: str | None = None,
    glyph_model: str | None = None,
    glyph_confidence: float | None = None,
    write_artefacts: bool = True,
) -> PipelineResult:
    """Run every step on `pdf_path`.

    `force_notation` overrides step 2 — pass `"figurine_unicode"` to parse a
    book whose detection came out below the threshold because only a few pages
    were selected.

    `force_language` overrides the detected language, and with it the piece
    letters used to read moves. Worth setting explicitly whenever you know the
    book: French `Rd2` is the King moving and English `Rd2` is the Rook, so a
    wrong language does not fail loudly — it yields legal, wrong moves.

    `glyph_model` is the trained piece classifier, and turns on step 1c for the
    two kinds of book whose text layer holds no readable piece symbols — a scan
    and a figurine font. It costs a rendering pass over every line carrying a
    move number, and it is what makes those books parseable at all.
    `glyph_confidence` overrides the threshold it accepts a piece at; see
    `glyphs.DEFAULT_MIN_CONFIDENCE` for what it is worth changing.
    """
    os.makedirs(work_dir, exist_ok=True)

    pages = extract.extract_pages(
        pdf_path, first_page=first_page, last_page=last_page, sort_blocks=sort_blocks
    )
    _write(write_artefacts, work_dir, "pages", [p.to_json() for p in pages])

    report = notation.detect_notation(pages)
    recovered: list[Any] = []
    if glyph_model is not None and report.needs_glyph_recovery:
        from . import glyphs  # optional dependencies; only imported when used

        classifier = glyphs.GlyphClassifier.load(glyph_model)
        pages, recovered = glyphs.recover_pieces(
            pdf_path,
            pages,
            classifier,
            min_confidence=(
                glyphs.DEFAULT_MIN_CONFIDENCE
                if glyph_confidence is None
                else glyph_confidence
            ),
        )
        _write(write_artefacts, work_dir, "glyphs", [g.to_json() for g in recovered])
        # The pages are different documents now — figurines where the layer had
        # the scanner's guesses — so what they are is settled again from them.
        report = notation.detect_notation(pages)

    if force_notation is not None:
        report.style = force_notation
        # Detection ran on too little text to reach its threshold, but the
        # caller has decided; leaving the measured confidence in place would
        # record "figurine_unicode at 0%" in the manifest.
        report.confidence = 1.0
    if force_language is not None:
        report.language = force_language
    _write(write_artefacts, work_dir, "notation", report.to_json())

    tokens = tokenize.tokenize_pages(pages, piece_letters=report.piece_letters)
    _write(write_artefacts, work_dir, "tokens", [t.to_json() for t in tokens])

    parsed = parse.parse_tokens(tokens, strict_numbering=strict_numbering)
    _write(write_artefacts, work_dir, "moves", parsed.to_json())

    rce_path: str | None = None
    if output_path is not None:
        manifest = package.build_manifest(
            pdf_path,
            # The whole document, not just the range processed: the app
            # renders the complete book and page numbers stay absolute.
            page_count=extract.page_count(pdf_path),
            notation=report,
            counts=parsed.counts(),
        )
        rce_path = package.write_rce(
            output_path, source_path=pdf_path, manifest=manifest, parse_result=parsed
        )

    return PipelineResult(
        pages=pages,
        notation=report,
        tokens=tokens,
        parsed=parsed,
        rce_path=rce_path,
        glyphs=recovered,
    )


def _write(enabled: bool, work_dir: str, key: str, payload: Any) -> None:
    if not enabled:
        return
    path = os.path.join(work_dir, ARTEFACTS[key])
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
