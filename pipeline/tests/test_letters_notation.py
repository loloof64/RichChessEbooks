"""Tests for books that spell pieces out in letters rather than symbols.

The stake here is not tolerance to noise but silent wrongness: `Rd2` is the
King moving in French and the Rook moving in English, and both are often legal
in the same position. A wrong language therefore produces a valid-looking game
that is not the one the book printed.
"""

import pytest

from rce_pipeline.extract import BBox, Char, Page
from rce_pipeline.notation import (
    PIECE_LETTERS_BY_LANGUAGE,
    NotationReport,
    detect_notation,
)
from rce_pipeline.parse import parse_tokens
from rce_pipeline.tokenize import tokenize_pages


def page_of(text: str, number: int = 1) -> Page:
    """A page whose characters sit on one row, one point apart.

    The geometry is fake but well-formed, which is all the tokeniser needs:
    what is under test is which characters become moves, not where they are.
    """
    chars = [
        Char(char=ch, bbox=BBox(float(i), 700.0, 1.0, 10.0), font="Serif", size=10.0)
        for i, ch in enumerate(text)
    ]
    return Page(number=number, width=595.0, height=842.0, text=text, chars=chars)


def sans_of(text: str, *, piece_letters: str) -> list[str]:
    tokens = tokenize_pages([page_of(text)], piece_letters=piece_letters)
    return [m.san for m in parse_tokens(tokens).moves]


class TestFrench:
    def test_translates_french_initials_to_san(self):
        # Cavalier, Fou, Dame, Tour, Roi.
        text = "1.e4 e5 2.Cf3 Cc6 3.Fb5 a6 4.Fa4 Cf6 5.O-O Fe7 6.Te1 b5 7.Fb3 d6"

        assert sans_of(text, piece_letters="RDTFC") == [
            "e4", "e5", "Nf3", "Nc6", "Bb5", "a6",
            "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "d6",
        ]

    def test_king_and_rook_do_not_collide(self):
        # French T -> R and R -> K. Translating in one pass keeps them apart;
        # applying the map twice would turn every Rook into a King.
        text = "1.e4 e5 2.Cf3 Cc6 3.Fc4 Fc5 4.O-O Cf6 5.Te1 O-O 6.Rh1 Te8 7.Tf1 Rh8"

        assert sans_of(text, piece_letters="RDTFC") == [
            "e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5",
            "O-O", "Nf6", "Re1", "O-O", "Kh1", "Re8", "Rf1", "Kh8",
        ]

    def test_queen_and_promotion(self):
        tokens = tokenize_pages(
            [page_of("1.a8=D")], piece_letters="RDTFC"
        )
        result = parse_tokens(tokens, initial_fen="4k3/P7/8/8/8/8/8/4K3 w - - 0 1")

        # The recorded SAN is regenerated from the board, not echoed from the
        # page: the check marker is present even though the book's token had
        # none.
        assert result.moves[0].san == "a8=Q+"
        assert result.moves[0].uci == "a7a8q"

    def test_prose_is_left_alone(self):
        # Every French piece initial starts common words. Translating the page
        # instead of the move tokens would turn this comment into noise.
        text = "1.e4 Dans cette Formation, Trois Cavaliers Restent actifs. 1...e5"

        tokens = tokenize_pages([page_of(text)], piece_letters="RDTFC")
        prose = [t.text for t in tokens if t.kind == "text"]

        assert prose == ["Dans cette Formation, Trois Cavaliers Restent actifs."]

    def test_reading_a_french_book_as_english_is_caught_by_legality(self):
        # 3.Fb5 is a Bishop in French. Read as English, `F` is not a piece
        # letter at all, so the token is not even seen as a move.
        text = "1.e4 e5 2.Cf3 Cc6 3.Fb5"

        as_english = sans_of(text, piece_letters="KQRBN")

        assert "Bb5" not in as_english


class TestOtherLanguages:
    @pytest.mark.parametrize(
        "language,text,expected",
        [
            ("en", "1.e4 e5 2.Nf3 Nc6 3.Bb5", ["e4", "e5", "Nf3", "Nc6", "Bb5"]),
            ("de", "1.e4 e5 2.Sf3 Sc6 3.Lb5", ["e4", "e5", "Nf3", "Nc6", "Bb5"]),
            ("es", "1.e4 e5 2.Cf3 Cc6 3.Ab5", ["e4", "e5", "Nf3", "Nc6", "Bb5"]),
            ("nl", "1.e4 e5 2.Pf3 Pc6 3.Lb5", ["e4", "e5", "Nf3", "Nc6", "Bb5"]),
        ],
    )
    def test_reads_each_alphabet(self, language, text, expected):
        letters = PIECE_LETTERS_BY_LANGUAGE[language]

        assert sans_of(text, piece_letters=letters) == expected


class TestDetection:
    def test_spots_french_piece_letters(self):
        moves = " ".join(
            f"{n}.Cf3 Fb5 Td1 Dh5 Re2" for n in range(1, 12)
        )
        report = detect_notation([page_of(moves)])

        assert report.style == "letters"
        assert report.language == "fr"
        assert report.piece_letters == "RDTFC"
        assert report.is_supported

    def test_a_language_resting_on_one_letter_is_refused(self):
        # A figurine-font book whose fonts are embedded under generated names
        # (`Fd97320`) offers no font hint, and its meaningless latin letters
        # still score: this scored `fr` at 28 with `es` and `it` tied at 28,
        # off one attested letter, against 436 moves naming no piece. `en` and
        # `de` scoring zero is the proof — no book moves its rook and queen
        # zero times in ten pages.
        moves = " ".join(f"{n}.e4 d5 Cf3" for n in range(1, 15))

        report = detect_notation([page_of(moves)])

        assert report.language is None
        assert report.confidence == 0.0
        # Which is what lets the drawn-symbol conclusion through.
        assert report.needs_glyph_recovery

    def test_letters_with_no_language_is_not_parseable(self):
        report = NotationReport(style="letters", language=None, confidence=0.0)

        assert not report.is_supported
        # Falls back to SAN rather than guessing, and the caller is expected to
        # settle it instead of trusting the fallback.
        assert report.piece_letters == "KQRBN"

    def test_a_figurine_font_is_detected_but_not_parseable(self):
        report = NotationReport(style="figurine_font", language=None, confidence=0.8)

        assert not report.is_supported


class TestScanDetection:
    def test_an_ocr_layer_is_identified_by_its_font(self):
        # Tesseract writes the text layer in a font with no glyphs in it,
        # whose only purpose is to make a scan searchable.
        page = page_of("1.e4 e5 2.4)f3 Wc6")
        for char in page.chars:
            char.font = "GlyphLessFont"

        report = detect_notation([page])

        assert report.is_ocr_layer
        assert not report.is_supported
        assert "SCANNED BOOK" in report.summary()
        assert report.to_json()["is_ocr_layer"] is True

    def test_it_refuses_to_name_a_language_from_scanner_noise(self):
        # Before this check, this book scored "letters / de" and looked like a
        # German book. Reporting nothing beats reporting a plausible fiction.
        page = page_of("22.Wf5 23.4)xf7! Exf7 24.We6 25.Web Sg7 26.Wxf7+ Gh6")
        for char in page.chars:
            char.font = "GlyphLessFont"

        report = detect_notation([page])

        assert report.language is None
        assert report.confidence == 0.0

    def test_an_ordinary_text_layer_is_not_flagged(self):
        report = detect_notation([page_of(" ".join(f"{n}.Cf3 Fb5 Td1 Dh5 Re2" for n in range(1, 12)))])

        assert not report.is_ocr_layer
        assert report.is_supported
