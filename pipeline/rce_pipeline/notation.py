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

from .extract import FIGURINE_FONT_HINTS, Page, font_inventory

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
        if self.is_ocr_layer:
            return False
        if self.style == "figurine_unicode":
            return True
        return self.style == "letters" and self.language is not None

    def to_json(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "language": self.language,
            "confidence": round(self.confidence, 3),
            "font_names": self.font_names,
            "is_ocr_layer": self.is_ocr_layer,
        }

    def summary(self) -> str:
        if self.is_ocr_layer:
            return (
                "SCANNED BOOK — the text layer is OCR output, not the publisher's.\n"
                f"Identified by the font {', '.join(self.font_names) or '(unknown)'}, "
                "which carries no glyphs and only exists to make a scan searchable.\n"
                "\n"
                "Prose in such a layer is usually good; moves are not. Piece symbols\n"
                "have no OCR category and land on arbitrary characters, and the squares\n"
                "around them degrade with the bold type they are set in. This pipeline\n"
                "cannot read moves from it, and reports that rather than producing a\n"
                "plausible-looking game that is not the one in the book.\n"
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
        if not self.is_supported:
            lines.append(
                "\n/!\\ v1 of this pipeline only parses figurine Unicode notation. "
                "Detection above is reported for information."
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

    if ocr_fonts:
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
    # Unicode figurine is unambiguous once it appears at all in quantity.
    if figurine_count >= 20:
        return NotationReport(
            style="figurine_unicode",
            language=None,
            confidence=_saturating(figurine_count, full=200),
            figurine_count=figurine_count,
            neutral_move_count=neutral_moves,
            font_names=suspect_fonts,
        )

    scores = _score_languages(text)

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


def _score_languages(text: str) -> dict[str, int]:
    """Count piece-move tokens for each candidate alphabet.

    Languages share most of their letters (T and D are rooks and queens in
    several), so the raw counts are compared, not treated as exclusive.
    """
    letter_hits: Counter[str] = Counter()
    all_letters = "".join(sorted(set("".join(PIECE_LETTERS_BY_LANGUAGE.values()))))
    pattern = re.compile(_MOVE_WITH_PIECE.format(letters=all_letters))
    for match in pattern.finditer(text):
        letter_hits[match.group(1)] += 1

    return {
        language: sum(letter_hits[letter] for letter in letters)
        for language, letters in PIECE_LETTERS_BY_LANGUAGE.items()
    }


def _saturating(count: int, *, full: int) -> float:
    """Map an evidence count to [0, 1], reaching 1.0 at `full` occurrences."""
    return min(1.0, count / full)


def normalise_figurines(text: str) -> str:
    """Replace Unicode piece characters with the latin letters SAN expects."""
    return "".join(FIGURINE_TO_LETTER.get(ch, ch) for ch in text)
