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

from . import (
    diagrams,
    extract,
    figurines,
    notation,
    package,
    parse,
    pictures,
    tokenize,
    weight,
)

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
        if parse.weight_marks_the_line(self.tokens):
            lines.append(
                "Weight:      the score is set apart from the analysis around "
                "it, and is read from the type"
            )
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
        # What the book has been seen spelling each piece, and then the symbols
        # the layer's boxes put one group to the right of that ink. Learned
        # before the correction and used to make it: the book's habit and the
        # classifier's reading have to agree before a symbol is moved.
        pages = [glyphs.unshift_symbols(page, glyphs.spellings(pages)) for page in pages]
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
        pages,
        piece_letters=report.piece_letters,
        diagrams=boards,
        # What the glyph pass restored teaches how this book's scanner spells
        # each piece, and the same spellings stand where it failed.
        spellings=glyphs.spellings(pages) if recovered else None,
    )
    if recovered:
        # A scan's boxes are the OCR's own and drift inside a word; a typeset
        # book's come from the type itself and are exact. Done before the
        # weight is measured, which reads the boxes it moves.
        try:
            from . import boxes as tap_zones

            tap_zones.snap(pdf_path, pages, tokens)
        except ImportError:  # pragma: no cover - numpy is an optional install
            warnings.warn(
                "step 3c skipped: moving a scan's tap zones onto its ink needs "
                "numpy (pip install 'rce-pipeline[pictures]'). The boxes stay "
                "as the text layer drew them.",
                RuntimeWarning,
                stacklevel=2,
            )
    marked = 0
    if not parse.weight_marks_the_line(tokens):
        # A scan's text layer is the OCR's own: one subsetted face for the
        # whole page, and the weight the publisher set the score in nowhere in
        # it. The ink still carries it. Only asked here, because reading it
        # costs a rendering of every page and the text layer is free.
        try:
            marked = weight.mark(pdf_path, tokens)
        except ImportError:  # pragma: no cover - numpy is an optional install
            warnings.warn(
                "step 3b skipped: measuring the weight a scan prints its score "
                "in needs numpy (pip install 'rce-pipeline[pictures]'). A book "
                "whose text layer carries the weight is unaffected.",
                RuntimeWarning,
                stacklevel=2,
            )

    parsed = parse.parse_tokens(tokens, strict_numbering=strict_numbering)
    table: dict[str, str] = {}
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
                parsed,
                strict_numbering=strict_numbering,
                weight_in_doubt=bool(marked),
            )
        if table:
            parsed = parse.parse_tokens(
                tokens, strict_numbering=strict_numbering, diagram_table=table
            )

    if marked:
        # The ink separated the two weights cleanly; whether reading them helps
        # is for the book to say, as it says which table of diagram characters
        # to keep. Asked here rather than beside the measurement, because the
        # reading to judge is the finished one: a book's diagrams correct its
        # lines, and a comparison made before they are read compares two
        # readings neither of which is the one it will ship.
        #
        # What the measurement cannot see is the score's own numbers going
        # missing. On a scan the OCR runs them into the prose around them —
        # `16lilxd4`, "White has a large advantage. 17" — and a rule that waits
        # for a number in the score's weight to resume the score then never
        # resumes it. Grivas' marks are right on every one of page 17's
        # forty-five numbers, and it gains fifteen moves there and loses
        # fifty-seven on the three pages where the numbers did not survive.
        plain = parse.parse_tokens(
            tokens,
            strict_numbering=strict_numbering,
            diagram_table=table or None,
            weighted=False,
        )
        if plain.break_diagnosis()["clean"] >= parsed.break_diagnosis()["clean"]:
            for token in tokens:
                token.bold = False
            parsed = plain
    _write(write_artefacts, work_dir, "tokens", [t.to_json() for t in tokens])
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
    candidates: list[dict[str, str]],
    tokens: list[Any],
    without: parse.ParseResult,
    *,
    strict_numbering: bool,
    weight_in_doubt: bool = False,
) -> dict[str, str]:
    """The one of `candidates` that leaves the book reading best, or none.

    Legality alone cannot separate a knight from a bishop, nor say which
    colour a book fills: a position with the two colours exchanged is still a
    position. The moves can, and reading them is what settles it.

    **Each table is weighed at the weight the book would ship it in.** Where
    the score's weight was measured off the ink, whether to read it is decided
    after the diagrams by exactly this kind of comparison — so a table judged
    on the weighted reading alone is judged on a reading the book may be about
    to throw away. On Grivas it was: twelve tables came in between 26 and 29
    weighted, four of them tied at the top, and the one the tie handed the
    book was worth **55** clean moves against the **425** of its neighbour once
    the weight was dropped. The two decisions are one decision.

    A confirmation breaks what is left of the tie, ahead of the count of boards
    read: the board this table decoded is a position the line itself reached,
    and a wrong table decodes boards no line ever reaches.

    **Reading no diagram is one of the candidates**, and `without` is it — the
    parse the book already got before any table was tried. A table that leaves
    the book worse than that is not a near miss to be taken for want of
    something better: it seeds wrong positions into lines that were sound, and
    every line downstream of one follows it. Boussole is where this was
    measured. Under a clustering that got `settle` to return 20 tables at all,
    the best of them took the book from 133 clean moves to 118 — legal
    throughout, and wrong. Refusing it costs the book nothing it had.
    """
    def score(attempt: parse.ParseResult) -> tuple[int, int, int]:
        verdicts = Counter(check["verdict"] for check in attempt.diagram_checks)
        read = sum(n for verdict, n in verdicts.items()
                   if verdict not in ("unread", "unreadable"))
        return attempt.break_diagnosis()["clean"], verdicts["confirms"], read

    def best_reading(table: dict[str, str] | None) -> tuple[int, int, int]:
        """This table at the weight the book would ship it in."""
        attempts = [parse.parse_tokens(
            tokens, strict_numbering=strict_numbering, diagram_table=table
        )]
        if weight_in_doubt:
            attempts.append(parse.parse_tokens(
                tokens, strict_numbering=strict_numbering, diagram_table=table,
                weighted=False,
            ))
        return max(score(attempt) for attempt in attempts)

    best: dict[str, str] = {}
    best_score = best_reading(None) if weight_in_doubt else score(without)
    for table in candidates[:MAX_TABLES_TRIED]:
        this = best_reading(table)
        if this > best_score:
            best, best_score = table, this
    return best


def _write(enabled: bool, work_dir: str, key: str, payload: Any) -> None:
    if not enabled:
        return
    path = os.path.join(work_dir, ARTEFACTS[key])
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
