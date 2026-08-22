"""The five steps, wired together.

Each step writes its artefact to `work_dir` before the next one starts, so a
step can be re-run — and its code changed — without redoing the ones before
it. On a 400-page book the extraction pass is by far the slowest, and it is
the one you least often need to repeat.
"""

from __future__ import annotations

import json
import os
import warnings
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from . import diagrams, extract, figurines, notation, package, parse, pictures, tokenize

ARTEFACTS = {
    "pages": "01_pages.json",
    "glyphs": "01b_glyphs.json",
    "diagrams": "01c_diagrams.json",
    "pictures": "01d_pictures.json",
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
    #: The diagram blocks found in the text layer, empty unless the book sets
    #: its positions in a diagram font.
    diagrams: list[Any] = field(default_factory=list)
    #: The diagrams read out of the pictures a book draws, empty unless it
    #: draws them and the arrays `pictures` works on are installed.
    pictures: list[Any] = field(default_factory=list)
    #: The book's own piece symbols, and the figurine each was read as, empty
    #: unless it printed them as ordinary characters of a figurine font.
    figurines: dict[str, str] = field(default_factory=dict)
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
        if self.figurines:
            from .notation import FIGURINE_TO_LETTER

            read = "  ".join(
                f"{symbol}={FIGURINE_TO_LETTER[figurine]}"
                for symbol, figurine in self.figurines.items()
            )
            lines.append(f"Figurines:   {read}   (settled on legality, not on the font's name)")
        if self.diagrams or self.pictures:
            verdicts = Counter(c["verdict"] for c in self.parsed.diagram_checks)
            printed = len(self.diagrams) + len(self.pictures)
            # Where they came from is worth printing beside what they did: a
            # book setting its boards in a font and a book drawing them are
            # read by different steps, and only one of the two can be turned
            # off by a missing install.
            source = (
                f"of which {len(self.diagrams)} set in the text layer "
                f"and {len(self.pictures)} drawn"
                if self.diagrams and self.pictures
                else ("set in the text layer" if self.diagrams else "drawn as pictures")
            )
            lines.append(
                f"Diagrams:    {printed} {source}"
                f"  ({verdicts['confirms']} confirm the line,"
                f" {verdicts['corrects']} correct it, {verdicts['seeds']} seed a game,"
                f" {verdicts['unreadable'] + verdicts['unread']} unread)"
            )
        breaks = self.parsed.break_diagnosis()
        lines += [
            # `ok` alone flatters a long line that broke early: see
            # `ParseResult.break_diagnosis`.
            f"Trusted:     {breaks['clean']} of those ok moves have nothing against them"
            f"  ({breaks['below_break']} stand below a break,"
            f" {breaks['contradicted']} are contradicted by a diagram)",
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
    read_pictures: bool = True,
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

    `read_pictures` turns off step 1d, which reads the boards a book draws as
    images. It is on by default and costs one pass over the page's images on a
    book that draws none; turn it off to measure what the diagrams are worth.
    """
    os.makedirs(work_dir, exist_ok=True)

    pages = extract.extract_pages(
        pdf_path, first_page=first_page, last_page=last_page, sort_blocks=sort_blocks
    )

    # A book printing its pieces as characters of a figurine font — `¤c3` for a
    # knight — is turned into the Unicode book it would otherwise have been,
    # before anything downstream looks at it. Costs nothing on a book that does
    # not: with no candidate character there is nothing to settle.
    symbols = figurines.candidates(pages)
    read_as = figurines.settle(pages, symbols) if symbols else {}
    if read_as:
        pages = figurines.rewrite(pages, read_as)
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

    printed = diagrams.find(pages)
    _write(write_artefacts, work_dir, "diagrams", [d.to_json() for d in printed])

    # A book draws its boards or sets them, and the two are read by different
    # steps; from here down neither the tokeniser nor the parser is told which
    # of the two a position came from.
    drawn: list[Any] = []
    reading: Any = None
    if read_pictures:
        if pictures.available():
            reading = pictures.read(pdf_path, pages, skip_pages={d.page for d in printed})
            drawn = reading.diagrams
            _write(write_artefacts, work_dir, "pictures", [d.to_json() for d in drawn])
        else:
            # Said out loud rather than skipped quietly: a book whose boards
            # are all drawn would otherwise report no diagrams at all, which
            # reads as "this book has none" and is a different thing.
            warnings.warn(
                "step 1d skipped: reading the boards a book draws needs numpy and "
                "scipy (pip install 'rce-pipeline[pictures]'). A book that sets its "
                "diagrams in a font is unaffected.",
                RuntimeWarning,
                stacklevel=2,
            )
    boards = sorted(printed + drawn, key=lambda d: (d.page, d.start))

    tokens = tokenize.tokenize_pages(
        pages, piece_letters=report.piece_letters, diagrams=boards
    )
    _write(write_artefacts, work_dir, "tokens", [t.to_json() for t in tokens])

    parsed = parse.parse_tokens(tokens, strict_numbering=strict_numbering)
    if boards:
        # The first pass reads the diagrams as nothing but eight rows of
        # characters, and that is enough to learn what the characters mean:
        # wherever a game reached one without breaking, the position is known.
        # The second pass has the font, so a diagram can seed a game printed
        # from a picture and correct a line that drifted.
        table = diagrams.learn(
            (tuple(check["rows"]), [check["reached"]])
            for check in parsed.diagram_checks
            if check["sound"] and check["reached"]
        )
        if not table:
            # No line reached a diagram intact — the case of a book whose piece
            # symbols had to be recovered from the page images. The recent
            # history of every line is trawled instead, and two diagrams must
            # then agree before the font is believed.
            table = diagrams.learn(
                (
                    (tuple(check["rows"]), diagrams.around(parsed.main_lines, check))
                    for check in parsed.diagram_checks
                ),
                min_diagrams=2,
            )
        if not table and reading is not None and reading.twins and reading.empty:
            # No game reached a diagram, so nothing taught the characters what
            # they mean. Ask the boards: `diagrams.settle` returns every table
            # the positions themselves allow, and the book breaks the tie —
            # each is read with, and the one leaving the most moves standing
            # clean wins. That is `figurines.settle`'s argument, one level up.
            table = _best_table(
                diagrams.settle([d.rows for d in drawn], reading.twins, reading.empty),
                tokens,
                strict_numbering=strict_numbering,
            )
        if table:
            parsed = parse.parse_tokens(
                tokens, strict_numbering=strict_numbering, diagram_table=table
            )
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
        diagrams=printed,
        pictures=drawn,
        figurines=read_as,
    )


#: How many of the tables `diagrams.settle` allows are tried against the book.
#: Reading one costs about twenty milliseconds, and the tie shrinks fast as
#: boards are added: two boards leave 96 tables standing, Grivas' thirty leave
#: 12 and SuperAttaquant's eleven leave 22.
MAX_TABLES_TRIED = 200


def _best_table(
    candidates: list[dict[str, str]], tokens: list[Any], *, strict_numbering: bool
) -> dict[str, str]:
    """The one of `candidates` that leaves the book reading best.

    Legality alone cannot separate a knight from a bishop, nor say which
    colour a book fills: a position with the two colours exchanged is still a
    position. The moves can, and reading them is what settles it.
    """
    best: dict[str, str] = {}
    best_score = (-1, -1)
    for table in candidates[:MAX_TABLES_TRIED]:
        attempt = parse.parse_tokens(
            tokens, strict_numbering=strict_numbering, diagram_table=table
        )
        read = sum(
            1
            for check in attempt.diagram_checks
            if check["verdict"] not in ("unread", "unreadable")
        )
        score = (attempt.break_diagnosis()["clean"], read)
        if score > best_score:
            best, best_score = table, score
    return best


def _write(enabled: bool, work_dir: str, key: str, payload: Any) -> None:
    if not enabled:
        return
    path = os.path.join(work_dir, ARTEFACTS[key])
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
