"""Step 2 — how are the pieces written in this book?

Three ways a chess book can name pieces:

``figurine_unicode``
    Real Unicode chess characters, U+2654–U+265F. Trivial to detect and the
    only style the v1 parser handles.
``figurine_font``
    A latin letter rendered through a font whose glyphs are piece drawings.
    The text layer holds a letter that has nothing to do with the piece shown,
    so it is detectable only by font name.
``letters``
    Plain letters, which alphabet depending on the language.

This module reports what it found together with the evidence, so the notebook
can show a conclusion to confirm rather than ask a question cold.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .extract import FIGURINE_FONT_HINTS, GLYPH_FONT, Page, font_inventory

#: Fonts that mark an invisible OCR layer laid over a scanned image rather than
#: a text layer produced by the publisher. Tesseract writes `GlyphLessFont`;
#: it is a positive identification, not a guess.
OCR_LAYER_FONTS = ("glyphlessfont",)

#: Unicode chess pieces mapped to the latin letter SAN uses. White (U+2654) and
#: black (U+265A) map to the same letter: SAN does not encode colour.
FIGURINE_TO_LETTER = {
    "♔": "K", "♕": "Q", "♖": "R",
    "♗": "B", "♘": "N", "♙": "P",
    "♚": "K", "♛": "Q", "♜": "R",
    "♝": "B", "♞": "N", "♟": "P",
}

#: The letters SAN itself uses, in the order King, Queen, Rook, Bishop, Knight.
SAN_PIECE_LETTERS = "KQRBN"

#: How many of a language's five piece letters must actually occur before that
#: language is believed.
#:
#: A summed score is not enough on its own. A figurine-font book whose fonts are
#: embedded under generated names (`Fd97320`) has no font hint to catch it, and
#: its meaningless latin letters still score: one book scored `fr` at 28 with
#: `es` and `it` tied at exactly 28, from a single attested letter, against 436
#: moves naming no piece at all. The tie is the giveaway — those three alphabets
#: overlap on the letters that hit, and `en` and `de` scored zero, which means
#: the rook, queen and king letters never occurred once in ten pages. No book
#: in any language moves its rook and queen zero times, so a language resting
#: on one or two letters is noise and the pieces are drawn rather than written.
#:
#: Three of five is deliberately lenient: a short sample may genuinely never
#: castle a king or move a bishop.
_MIN_ATTESTED_PIECE_LETTERS = 3

#: Piece initials per language, in that same order.
#:
#: The overlaps are what make this dangerous rather than tedious: `R` is the
#: King in French and the Rook in English, `D` is the Queen in four of these
#: and nothing in English, `C` is the Knight in French but the SAN letter for
#: nothing. Reading a French book as English SAN therefore does not fail
#: loudly — it produces legal, wrong moves. Which language is in use has to be
#: settled before any move is parsed.
PIECE_LETTERS_BY_LANGUAGE: dict[str, str] = {
    "en": "KQRBN",
    "fr": "RDTFC",
    "de": "KDTLS",
    "es": "RDTAC",
    "it": "RDTAC",
    "nl": "KDTLP",
}

# A move-shaped token whose piece letter is left open, used to score languages.
_MOVE_WITH_PIECE = r"(?<![A-Za-z])([{letters}])[a-h]?[1-8]?x?[a-h][1-8]"

# A move that names no piece at all (pawn move, castling): present in every
# language, so it proves "this is chess notation" without favouring one.
_LANGUAGE_NEUTRAL_MOVE = re.compile(
    r"(?<![A-Za-z0-9])(?:O-O(?:-O)?|0-0(?:-0)?|[a-h]x?[a-h]?[1-8](?:=[QRBN])?)(?![A-Za-z])"
)


@dataclass
class NotationReport:
    style: str
    language: str | None
    confidence: float
    figurine_count: int = 0
    neutral_move_count: int = 0
    font_names: list[str] = field(default_factory=list)
    language_scores: dict[str, int] = field(default_factory=dict)
    #: True when the text layer is OCR output over a scanned image. Whatever
    #: style is reported alongside is then meaningless: the detector is reading
    #: the scanner's guesses, not the book.
    is_ocr_layer: bool = False
    #: Piece symbols :mod:`rce_pipeline.glyphs` read off the page image and
    #: wrote into the pages. Non-zero means this book's symbols were recovered
    #: rather than read, which is what makes an OCR layer or a figurine font
    #: parseable at all.
    glyphs_recovered: int = 0

    @property
    def piece_letters(self) -> str:
        """The alphabet the tokeniser should read piece initials with.

        Figurine books have already had their symbols mapped to SAN letters by
        the time tokenising starts, so they use the SAN alphabet. A letters
        book uses its own language's, and falls back to SAN when the language
        could not be settled — a fallback worth overriding rather than
        trusting, since English is only right for English books.
        """
        if self.style == "letters" and self.language:
            return PIECE_LETTERS_BY_LANGUAGE.get(self.language, SAN_PIECE_LETTERS)
        return SAN_PIECE_LETTERS

    @property
    def is_supported(self) -> bool:
        """Styles v1 can parse.

        Figurine Unicode, and plain letters once the language is known. A
        figurine *font* is not parseable: its text layer holds latin letters
        that have no relation to the pieces drawn, so there is nothing in the
        characters to read. Neither is an OCR layer, for the same reason plus
        worse — see :attr:`is_ocr_layer`.
        """
        if self.is_ocr_layer and not self.glyphs_recovered:
            return False
        if self.style == "figurine_unicode":
            return True
        return self.style == "letters" and self.language is not None

    @property
    def needs_glyph_recovery(self) -> bool:
        """True when the piece symbols exist only in the page image.

        The two obvious cases are a scan, whose OCR guessed at the symbols, and
        a book whose font name gives a figurine face away. The third is the one
        that matters in practice: a book that is full of moves no piece is
        named in — 75 pawn moves and castlings on two pages, and not one
        `Nf3` in any language's alphabet. That only happens when the symbols
        are drawn rather than written, and it catches the figurine books whose
        font is reported as `Helvetica`, or not reported at all.

        All three are repaired by :func:`rce_pipeline.glyphs.recover_pieces`.
        """
        if self.glyphs_recovered:
            return False
        if self.is_ocr_layer or self.style == "figurine_font":
            return True
        return (
            self.style == "letters"
            and self.language is None
            and self.neutral_move_count >= 20
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "language": self.language,
            "confidence": round(self.confidence, 3),
            "font_names": self.font_names,
            "is_ocr_layer": self.is_ocr_layer,
            "glyphs_recovered": self.glyphs_recovered,
        }

    def summary(self) -> str:
        if self.glyphs_recovered:
            source = "a scan" if self.is_ocr_layer else "a figurine font"
            return (
                f"REPAIRED BOOK — its piece symbols came from {source}, so the text\n"
                f"layer never held them; {self.glyphs_recovered} were read off the page\n"
                "images by the glyph classifier and written in as figurines.\n"
                "\n"
                "What the layer still supplies is everything else: move numbers, the\n"
                "squares, and the prose. On a scan those squares carry the scanner's own\n"
                "error rate, so expect moves the legality pass cannot settle — they are\n"
                "reported broken rather than guessed at.\n"
                "\n"
                f"Notation: {self.style} (confidence {self.confidence:.0%})\n"
                f"Unicode piece characters found: {self.figurine_count}\n"
                f"Language-neutral moves found:   {self.neutral_move_count}"
            )

        if self.is_ocr_layer:
            return (
                "SCANNED BOOK — the text layer is OCR output, not the publisher's.\n"
                f"Identified by the font {', '.join(self.font_names) or '(unknown)'}, "
                "which carries no glyphs and only exists to make a scan searchable.\n"
                "\n"
                "Prose in such a layer is usually good; moves are not. Piece symbols\n"
                "have no OCR category and land on arbitrary characters, and the squares\n"
                "around them degrade with the bold type they are set in. Read as it\n"
                "stands, this layer yields a plausible-looking game that is not the one\n"
                "in the book, so it is refused instead.\n"
                "\n"
                "The symbols can be recovered from the page images: pass a trained glyph\n"
                "classifier as run(glyph_model=...) and this book becomes readable.\n"
                "\n"
                "What it detected underneath is listed only for information:\n"
                f"  style {self.style}, language {self.language}, "
                f"{self.figurine_count} Unicode piece characters, "
                f"{self.neutral_move_count} language-neutral moves."
            )

        lines = [f"Notation: {self.style} (confidence {self.confidence:.0%})"]
        if self.language:
            lines.append(
                f"Language: {self.language} "
                f"(piece letters {self.piece_letters} -> {SAN_PIECE_LETTERS})"
            )
        lines.append(f"Unicode piece characters found: {self.figurine_count}")
        lines.append(f"Language-neutral moves found:   {self.neutral_move_count}")
        if self.font_names:
            lines.append(f"Suspected figurine fonts: {', '.join(self.font_names)}")
        if self.language_scores:
            ranked = sorted(self.language_scores.items(), key=lambda kv: -kv[1])
            lines.append("Language scores: " + ", ".join(f"{k}={v}" for k, v in ranked))
        if self.needs_glyph_recovery:
            if self.style == "figurine_font":
                cause = (
                    "the fonts listed above are figurine faces, so the layer holds\n"
                    "latin letters bearing no relation to the pieces they draw."
                )
            else:
                cause = (
                    f"no piece is named in any of the six alphabets, yet "
                    f"{self.neutral_move_count} moves that\n"
                    "name none — pawn moves, castlings — were found. A book of nothing but\n"
                    "pawn moves does not exist: the symbols here are drawn, not written,\n"
                    "which is why the style above reads `letters` at 0%."
                )
            lines.append(
                "\nDRAWN SYMBOLS — needs_glyph_recovery = True.\n"
                f"{cause}\n"
                "\n"
                "Pass the trained classifier as run(glyph_model=...): it reads the symbols\n"
                "off the page images and writes them back in as figurines. Without it this\n"
                "book has no pieces to parse, and every move comes out broken."
            )
        elif not self.is_supported:
            lines.append(
                "\n/!\\ Not parseable as it stands: the notation is letters, but no\n"
                "language reached the detection threshold, so the pipeline cannot tell\n"
                "which piece each initial names. Set run(force_language=...) if you know\n"
                "the book — see the table in step 5."
            )
        return "\n".join(lines)


def detect_notation(pages: list[Page]) -> NotationReport:
    """Classify the notation used across `pages`."""
    text = "\n".join(page.text for page in pages)
    fonts = font_inventory(pages)

    ocr_fonts = [
        name for name in fonts if any(hint in name.lower() for hint in OCR_LAYER_FONTS)
    ]
    figurine_count = sum(text.count(ch) for ch in FIGURINE_TO_LETTER)
    neutral_moves = len(_LANGUAGE_NEUTRAL_MOVE.findall(text))
    suspect_fonts = [
        name
        for name in fonts
        if any(hint in name.lower() for hint in FIGURINE_FONT_HINTS)
    ]

    recovered = sum(
        1 for page in pages for char in page.chars if char.font == GLYPH_FONT
    )

    if ocr_fonts and not recovered:
        # Stop here. Running the language scorer on a scanner's guesses gives a
        # confident-looking answer drawn from noise — this book scored
        # "letters / de" before this check existed.
        return NotationReport(
            style="letters",
            language=None,
            confidence=0.0,
            figurine_count=figurine_count,
            neutral_move_count=neutral_moves,
            font_names=ocr_fonts,
            is_ocr_layer=True,
        )

    # Enough piece characters, and they outnumber nothing else plausible:
    # Unicode figurine is unambiguous once it appears at all in quantity. A
    # repaired book arrives here by the same route as a real figurine one — the
    # symbols are in the text now, whoever put them there.
    if figurine_count >= 20:
        return NotationReport(
            style="figurine_unicode",
            language=None,
            confidence=_saturating(figurine_count, full=200),
            figurine_count=figurine_count,
            neutral_move_count=neutral_moves,
            font_names=ocr_fonts or suspect_fonts,
            is_ocr_layer=bool(ocr_fonts),
            glyphs_recovered=recovered,
        )

    scores, letter_hits = _score_languages(text)

    if suspect_fonts and neutral_moves >= 20:
        # The text layer's letters are meaningless here, so no language is
        # reported; the font name is the whole of the evidence.
        return NotationReport(
            style="figurine_font",
            language=None,
            confidence=_saturating(neutral_moves, full=200) * 0.8,
            figurine_count=figurine_count,
            neutral_move_count=neutral_moves,
            font_names=suspect_fonts,
            language_scores=scores,
        )

    if not scores or max(scores.values()) == 0:
        return NotationReport(
            style="letters",
            language=None,
            confidence=0.0,
            figurine_count=figurine_count,
            neutral_move_count=neutral_moves,
            font_names=suspect_fonts,
            language_scores=scores,
        )

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best_language, best_score = ranked[0]

    attested = sum(
        1 for letter in PIECE_LETTERS_BY_LANGUAGE[best_language] if letter_hits[letter]
    )
    if attested < _MIN_ATTESTED_PIECE_LETTERS:
        # The winner rests on too few of its letters to be a language. Reporting
        # none leaves `needs_glyph_recovery` free to conclude that the symbols
        # are drawn, which is what a book like this actually needs.
        return NotationReport(
            style="letters",
            language=None,
            confidence=0.0,
            figurine_count=figurine_count,
            neutral_move_count=neutral_moves,
            font_names=suspect_fonts,
            language_scores=scores,
        )

    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    # Confidence blends "is there enough evidence" with "is the winner clear".
    margin = (best_score - runner_up) / best_score if best_score else 0.0
    return NotationReport(
        style="letters",
        language=best_language,
        confidence=_saturating(best_score, full=100) * (0.5 + 0.5 * margin),
        figurine_count=figurine_count,
        neutral_move_count=neutral_moves,
        font_names=suspect_fonts,
        language_scores=scores,
    )


def _score_languages(text: str) -> tuple[dict[str, int], Counter[str]]:
    """Count piece-move tokens for each candidate alphabet.

    Languages share most of their letters (T and D are rooks and queens in
    several), so the raw counts are compared, not treated as exclusive. The
    per-letter tally is returned alongside because the totals alone cannot tell
    an alphabet that occurred from one that merely shares a letter with noise —
    see :data:`_MIN_ATTESTED_PIECE_LETTERS`.
    """
    letter_hits: Counter[str] = Counter()
    all_letters = "".join(sorted(set("".join(PIECE_LETTERS_BY_LANGUAGE.values()))))
    pattern = re.compile(_MOVE_WITH_PIECE.format(letters=all_letters))
    for match in pattern.finditer(text):
        letter_hits[match.group(1)] += 1

    scores = {
        language: sum(letter_hits[letter] for letter in letters)
        for language, letters in PIECE_LETTERS_BY_LANGUAGE.items()
    }
    return scores, letter_hits


def _saturating(count: int, *, full: int) -> float:
    """Map an evidence count to [0, 1], reaching 1.0 at `full` occurrences."""
    return min(1.0, count / full)


def normalise_figurines(text: str) -> str:
    """Replace Unicode piece characters with the latin letters SAN expects."""
    return "".join(FIGURINE_TO_LETTER.get(ch, ch) for ch in text)
