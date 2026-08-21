"""Tests for the move tree and the legality pass.

These build tokens directly instead of going through a PDF: the parser's job
is to turn a token sequence into a validated tree, and pinning that down does
not need a document. Extraction is exercised by the notebook's visual check,
which is the only thing that can really tell whether a box sits on its move.
"""

import chess
import pytest

from rce_pipeline.extract import BBox
from rce_pipeline.parse import _ambiguous_candidates, _confusable_distance, parse_tokens
from rce_pipeline.tokenize import Token

BOX = BBox(72.0, 640.0, 18.0, 10.0)


def tok(
    kind: str, text: str, page: int = 1, consumed: str = "", lost_symbol: str = ""
) -> Token:
    return Token(
        kind=kind, text=text, raw=text, page=page,
        start=0, end=len(text), bbox=BOX, consumed=consumed,
        lost_symbol=lost_symbol,
    )


def moves(*pairs: tuple[str, str]) -> list[Token]:
    return [tok(kind, text) for kind, text in pairs]


def sans(result) -> list[str]:
    return [m.san for m in result.moves]


class TestMainLine:
    def test_reads_a_numbered_sequence(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
            )
        )

        assert sans(result) == ["e4", "e5", "Nf3", "Nc6"]
        assert all(m.status == "ok" for m in result.moves)
        assert [m.ply for m in result.moves] == [1, 2, 3, 4]

    def test_links_each_move_to_the_one_before(self):
        result = parse_tokens(
            moves(("move_number", "1."), ("move", "e4"), ("move", "e5"))
        )

        first, second = result.moves
        assert first.parent_id is None
        assert second.parent_id == first.id
        assert all(m.variation_index == 0 for m in result.moves)

    def test_records_the_position_after_the_move(self):
        result = parse_tokens(moves(("move_number", "1."), ("move", "e4")))

        assert result.moves[0].fen.startswith(
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b"
        )
        assert result.moves[0].uci == "e2e4"

    def test_black_only_numbering_admits_a_single_move(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"),
                ("move_number", "2..."), ("move", "Nc6"), ("move", "Bc4"),
            )
        )

        # "2..." announces one move; the next needs a new number.
        assert sans(result) == ["e4", "e5", "Nf3", "Nc6"]
        assert result.skipped[-1]["text"] == "Bc4"
        assert result.skipped[-1]["reason"] == "no move number in context"


class TestVariations:
    def test_branches_from_the_position_before_the_replaced_move(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("var_open", "("),
                ("move_number", "1..."), ("move", "c5"),
                ("move_number", "2."), ("move", "Nf3"),
                ("var_close", ")"),
                ("move_number", "2."), ("move", "Nf3"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        e4, e5, c5 = by_san["e4"], by_san["e5"], by_san["c5"]

        # c5 is an alternative to e5, so both hang off e4.
        assert c5.parent_id == e4.id
        assert e5.parent_id == e4.id
        assert e5.variation_index == 0
        assert c5.variation_index == 1

    def test_resumes_the_main_line_after_the_closing_bracket(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("var_open", "("), ("move_number", "1..."), ("move", "c5"), ("var_close", ")"),
                ("move_number", "2."), ("move", "Nf3"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        # Nf3 continues from e5, not from the variation's c5.
        assert by_san["Nf3"].parent_id == by_san["e5"].id
        assert by_san["Nf3"].fen.split()[0].endswith("RNBQKB1R")

    def test_brackets_with_no_preceding_move_are_just_prose(self):
        result = parse_tokens(
            moves(
                ("var_open", "("),
                ("move_number", "1."), ("move", "e4"),
                ("var_close", ")"),
            )
        )

        assert sans(result) == ["e4"]
        assert result.moves[0].variation_index == 0


class TestVariationsWrittenInProse:
    """Analysis interleaved with the game score, with nothing to mark it.

    Chess books do this constantly — "Another promising continuation is
    13...Nb6 14 g5", "Threatening 17...Nxc2" — with no bracket, no bold and no
    indent. Read as the continuation, such a line is played on a position the
    book never reached and everything after it breaks. Laurent pointed out that
    no typographic signal is available for it, which rules out the font and the
    indent; the printed number is what remains.
    """

    def test_a_number_that_does_not_continue_the_line_opens_a_variation(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                ("move_number", "3."), ("move", "Bb5"),
                # Prose analysis: Black's 2nd, while the line awaits Black's 3rd.
                ("move_number", "2..."), ("move", "d6"),
                ("move_number", "3."), ("move", "d4"), ("move", "exd4"),
                ("move_number", "4."), ("move", "Nxd4"),
                # The game picks up again at the half-move it was waiting for.
                ("move_number", "3..."), ("move", "a6"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        # d6 replaces Nc6, so both hang off Nf3 rather than one off the other.
        assert by_san["d6"].parent_id == by_san["Nf3"].id
        assert by_san["Nc6"].parent_id == by_san["Nf3"].id
        assert by_san["Nc6"].variation_index == 0
        assert by_san["d6"].variation_index == 1
        # And the main line resumed rather than growing out of the analysis.
        assert by_san["a6"].parent_id == by_san["Bb5"].id
        # Nothing was played on a position the book never reached.
        assert all(m.status == "ok" for m in result.moves)

    def test_two_alternatives_to_one_move_are_siblings(self):
        # "Other ideas are 15 Rhg1 and 15 Qh3" — the second is not inside the
        # first, so a prose variation replaces the one in progress.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"),
                ("move_number", "2."), ("move", "Bc4"),
                ("move_number", "2."), ("move", "d4"),
                ("move_number", "2..."), ("move", "Nc6"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        for san in ("Nf3", "Bc4", "d4"):
            assert by_san[san].parent_id == by_san["e5"].id, san
        # `2...Nc6` is genuinely ambiguous here: the last alternative and the
        # game await the very same half-move, so the number cannot tell them
        # apart and nothing else on the page can either. It continues the
        # variation, which is the safe reading — "15 Qh3 0-0" in a real book is
        # Black castling inside the analysis, not the game resuming. The game
        # picks up again as soon as the two diverge, which is the usual case
        # since analysis runs on past the move it started from.
        assert by_san["Nc6"].parent_id == by_san["d4"].id

    def test_brackets_still_win(self):
        # The numbering is a guess; a bracket is not, so it is left alone.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("var_open", "("),
                ("move_number", "1..."), ("move", "c5"),
                ("var_close", ")"),
                ("move_number", "2."), ("move", "Nf3"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["c5"].parent_id == by_san["e4"].id
        assert by_san["Nf3"].parent_id == by_san["e5"].id


class TestComments:
    def test_attaches_prose_to_the_move_it_follows(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"),
                ("text", "The king's pawn opening."),
                ("move_number", "1..."), ("move", "e5"),
            )
        )

        assert result.moves[0].comment == "The king's pawn opening."
        assert result.moves[1].comment is None

    def test_a_comment_after_a_variation_belongs_to_the_move_before_it(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("var_open", "("), ("move_number", "1..."), ("move", "c5"), ("var_close", ")"),
                ("text", "Black chooses the open game."),
            )
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["e5"].comment == "Black chooses the open game."
        assert by_san["c5"].comment is None


class TestProseEndsTheNumbersLicence:
    """A number announces the moves beside it, and a comment ends what it
    announced. Every book in the corpus reprints the number when the score
    resumes, and commentary names squares — "the pawn at d5" — in the shape of
    a move."""

    def test_a_square_named_in_prose_is_not_black_s_reply(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"),
                ("text", "White intends to advance to"),
                ("move", "d4"),
            )
        )

        assert sans(result) == ["e4"]
        assert [s["reason"] for s in result.skipped] == ["no move number in context"]

    def test_the_score_resumes_on_its_number(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"),
                ("text", "The king's pawn opening."),
                ("move_number", "1..."), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"),
            )
        )

        assert sans(result) == ["e4", "e5", "Nf3"]

    def test_the_wreck_of_a_move_does_not_end_it(self):
        # A broken font leaves debris the tokeniser can only emit as prose —
        # `exdS`, `18Rd2`, `:tel`. The moves are still running beside it, so the
        # licence has to survive: this is a Boussole line, and the move after
        # the wreck is real.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("text", "iBxe4"), ("move", "Nf3"),
            )
        )

        assert sans(result) == ["e4", "e5", "Nf3"]


class TestBreakDiagnosis:
    def test_separates_the_line_that_died_from_what_was_read_below_it(self):
        # `Ra5` is illegal here, so the line stays on the position before it
        # and `Nc6` is then read on a board the book never reached — legal,
        # and not the book's move.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Ra5"),
                ("move_number", "3."), ("move", "Nc6"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["Ra5"].status == "broken"
        assert by_san["Nc6"].status == "ok"
        assert result.break_diagnosis() == {
            "first_breaks": 1, "cascade": 0, "clean": 3, "below_break": 1,
        }


class TestLegality:
    def test_castling_written_with_zeros_is_not_treated_as_an_error(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                ("move_number", "3."), ("move", "Bc4"), ("move", "Bc5"),
                ("move_number", "4."), ("move", "0-0"),
            )
        )

        castling = result.moves[-1]
        assert castling.san == "O-O"
        assert castling.status == "ok"
        assert castling.uci in {"e1g1", "e1h1"}

    def test_repairs_a_piece_letter_read_as_a_digit(self):
        # "8b5" is how a scanner mangles "Bb5".
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                ("move_number", "3."), ("move", "8b5"),
            )
        )

        repaired = result.moves[-1]
        assert repaired.san == "Bb5"
        assert repaired.status == "uncertain"
        assert repaired.fen is not None
        assert repaired.repair["raw"] == "8b5"
        # A confusable swap costs half, so confidence stays high.
        assert repaired.confidence == pytest.approx(0.75)

    def test_refuses_to_guess_between_two_equally_plausible_moves(self):
        # Knights on b1 and f3 both reach d2: "Nd2" needs the disambiguation
        # the book printed and the scanner dropped.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "d4"), ("move", "d5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nf6"),
                ("move_number", "3."), ("move", "Nd2"),
            )
        )

        ambiguous = result.moves[-1]
        assert ambiguous.status == "broken"
        assert ambiguous.fen is None
        assert ambiguous.uci is None
        assert "ambiguous" in ambiguous.repair["reason"]
        assert ambiguous.repair["raw"] == "Nd2"

    def test_settles_an_ambiguity_from_the_letter_the_figurine_covered(self):
        # The same position, but the token came from a repaired scan: the
        # figurine was written over `4)` — the scanner's reading of the knight
        # — and over the `b` of the disambiguation printed beside it.
        result = parse_tokens(
            moves(("move_number", "1."), ("move", "d4"), ("move", "d5"),
                  ("move_number", "2."), ("move", "Nf3"), ("move", "Nf6"),
                  ("move_number", "3."))
            + [tok("move", "Nd2", consumed="4)b")]
        )

        settled = result.moves[-1]
        assert settled.san == "Nbd2"
        assert settled.status == "uncertain"
        assert settled.fen is not None
        assert settled.uci == "b1d2"
        # Below a look-alike repair: the evidence is a destroyed character.
        assert settled.confidence == pytest.approx(0.6)
        assert result.ambiguities[-1]["settled_by"] == "consumed"

    def test_stays_broken_when_the_covered_letter_names_no_candidate(self):
        # Only the scanner's guess at the symbol was under the figurine; the
        # disambiguation was never printed or never covered.
        result = parse_tokens(
            moves(("move_number", "1."), ("move", "d4"), ("move", "d5"),
                  ("move_number", "2."), ("move", "Nf3"), ("move", "Nf6"),
                  ("move_number", "3."))
            + [tok("move", "Nd2", consumed="4)")]
        )

        assert result.moves[-1].status == "broken"
        assert result.ambiguities[-1]["settled_by"] is None

    def test_stays_broken_when_the_covered_letters_name_both_candidates(self):
        result = parse_tokens(
            moves(("move_number", "1."), ("move", "d4"), ("move", "d5"),
                  ("move_number", "2."), ("move", "Nf3"), ("move", "Nf6"),
                  ("move_number", "3."))
            + [tok("move", "Nd2", consumed="bf")]
        )

        assert result.moves[-1].status == "broken"
        assert sorted(result.ambiguities[-1]["candidates"]) == ["Nbd2", "Nfd2"]

    def test_keeps_an_explicit_disambiguation(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "d4"), ("move", "d5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nf6"),
                ("move_number", "3."), ("move", "Nbd2"),
            )
        )

        assert result.moves[-1].san == "Nbd2"
        assert result.moves[-1].status == "ok"

    def test_a_broken_move_keeps_its_geometry_and_closes_the_line(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "a6"),
                ("move_number", "2."), ("move", "Qh9"), ("move", "b6"),
            )
        )

        broken = [m for m in result.moves if m.status == "broken"]
        assert len(broken) == 1
        assert broken[0].bbox == BOX
        assert broken[0].page == 1
        # Nothing is read after it: the board no longer matches the book.
        assert sans(result) == ["e4", "a6", "Qh9"]

    def test_promotion_is_recorded_in_uci(self):
        result = parse_tokens(
            [tok("move_number", "1."), tok("move", "a8=Q")],
            initial_fen="4k3/P7/8/8/8/8/8/4K3 w - - 0 1",
        )

        assert result.moves[0].uci == "a7a8q"
        assert result.moves[0].status == "ok"


class TestCheckMarkIsNotAnError:
    """The check mark belongs to the position, not to what the reader wrote.

    `python-chess` derives `+` and `#` from the board, so a book printing
    `Nxc3` where the SAN is `Nxc3+` has made no error. Charging a full
    insertion for it put every checking move at 1.5 against a budget of 0.5,
    so no repair on one was ever affordable — four books in a row reported not
    one `uncertain` move, across 945 of them.
    """

    def test_a_look_alike_is_repaired_on_a_checking_move(self):
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "e4"), ("move", "e5"),
            ("move_number", "2."), ("move", "Qh5"), ("move", "Nc6"),
            # `S` read for `5`, on a move that happens to give check.
            ("move_number", "3."), ("move", "QxeS"),
        ))

        last = result.moves[-1]
        assert last.san == "Qxe5+"
        assert last.status == "uncertain"
        assert "0.5" in last.repair["reason"]

    def test_a_missing_check_mark_alone_is_not_a_repair(self):
        # Nothing was misread here, so the move stays `ok` rather than being
        # demoted for a mark the book chose not to print.
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "e4"), ("move", "e5"),
            ("move_number", "2."), ("move", "Qh5"), ("move", "Nc6"),
            ("move_number", "3."), ("move", "Qxe5"),
        ))

        last = result.moves[-1]
        assert last.san == "Qxe5+"
        assert last.status == "ok"


class TestStrayTokens:
    def test_move_shaped_prose_is_skipped_when_no_number_announces_it(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("text", "See diagram"),
                ("move", "b4"),
            )
        )

        assert sans(result) == ["e4", "e5"]
        assert result.skipped[0]["text"] == "b4"

    def test_relaxed_mode_reads_unnumbered_sequences(self):
        result = parse_tokens(
            moves(("move_number", "1."), ("move", "e4"), ("move", "e5"), ("move", "Nf3")),
            strict_numbering=False,
        )

        assert sans(result) == ["e4", "e5", "Nf3"]

    def test_a_result_ends_the_game(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("result", "1-0"),
                ("move_number", "1."), ("move", "d4"),
            )
        )

        assert len(result.games) == 2
        assert result.games[1].root_move_id == result.moves[-1].id
        # Each game roots its own tree rather than sharing a null parent.
        assert result.moves[-1].parent_id is None
        assert result.moves[-1].variation_index == 0


class TestConfusableDistance:
    @pytest.mark.parametrize(
        "a,b,expected",
        [
            ("Bb5", "Bb5", 0.0),
            ("8b5", "Bb5", 0.5),   # 8 / B, a half-cost swap
            ("Nf3", "Nf4", 1.0),   # 3 / 4, unrelated shapes
            ("O-O", "0-0", 1.0),   # two half-cost swaps
            ("Nd2", "Nbd2", 1.0),  # one insertion
        ],
    )
    def test_scores_edits(self, a, b, expected):
        assert _confusable_distance(a, b) == pytest.approx(expected)

    def test_is_symmetric(self):
        assert _confusable_distance("8b5", "Bb5") == _confusable_distance("Bb5", "8b5")

    def test_a_wrong_rank_digit_is_not_repaired_into_a_legal_move(self):
        # The trap this threshold exists for: Nc6 is illegal for White, and
        # Nc3 sits one ordinary substitution away. Guessing it would produce a
        # legal, wrong move and corrupt every position after it.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nc6"),
            )
        )

        assert result.moves[-1].status == "broken"
        assert result.moves[-1].fen is None


class TestAmbiguityDiagnosis:
    """Where a book's ambiguities come from — the measurement, not a fix.

    `python-chess` excludes the moves of a pinned piece from `legal_moves`, so
    the usual reason a book prints no disambiguation — only one of the two
    pieces may legally go there — never reaches this path. An ambiguity that
    survives means either the token lost a character or the board is not the
    one the book was on, and only the second is a reason to distrust the FENs
    that follow. Telling them apart is what these counts are for.
    """

    def _ambiguity_below_a_repair(self):
        # `8f5` is repaired to `Bf5` (8/B is a confusable pair), and the
        # ambiguity arrives one ply later.
        return parse_tokens(
            moves(
                ("move_number", "1."), ("move", "d4"), ("move", "d5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nf6"),
                ("move_number", "3."), ("move", "Bf4"), ("move", "8f5"),
                ("move_number", "4."), ("move", "Nd2"),
            )
        )

    def test_counts_an_ambiguity_standing_below_a_repair(self):
        result = self._ambiguity_below_a_repair()

        assert result.moves[-2].status == "uncertain"  # the repaired Bf5
        diagnosis = result.ambiguity_diagnosis()
        assert diagnosis["total"] == 1
        assert diagnosis["downstream_of_repair"] == 1
        assert diagnosis["clean_line"] == 0
        assert diagnosis["nearest_repair_plies"] == [1]

    def test_counts_an_ambiguity_on_a_line_with_no_repair_above_it(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "d4"), ("move", "d5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nf6"),
                ("move_number", "3."), ("move", "Nd2"),
            )
        )

        diagnosis = result.ambiguity_diagnosis()
        assert diagnosis["downstream_of_repair"] == 0
        assert diagnosis["clean_line"] == 1
        assert result.ambiguities[0]["upstream_repair_distance"] is None

    def test_an_unambiguous_book_reports_nothing(self):
        result = parse_tokens(
            moves(("move_number", "1."), ("move", "e4"), ("move", "e5"))
        )

        assert result.counts()["ambiguous"] == 0
        assert result.ambiguity_diagnosis()["total"] == 0

    def test_ambiguities_stay_out_of_the_contract_file(self):
        result = self._ambiguity_below_a_repair()

        assert "ambiguities" not in result.to_json()


class TestAmbiguousCandidates:
    def test_a_partial_disambiguation_narrows_the_set(self):
        # Both white rooks sit on the a-file and both reach a3, so naming the
        # file changes nothing and only the rank can settle it.
        board = chess.Board("4k3/8/8/R7/8/8/8/R3K3 w - - 0 1")

        assert len(_ambiguous_candidates(board, "Ra3")) == 2
        assert len(_ambiguous_candidates(board, "Raa3")) == 2
        assert len(_ambiguous_candidates(board, "R1a3")) == 1

    def test_a_capture_reads_the_same_with_or_without_the_x(self):
        board = chess.Board("4k3/8/8/R7/8/r7/8/R3K3 w - - 0 1")

        assert len(_ambiguous_candidates(board, "Rxa3")) == 2
        assert len(_ambiguous_candidates(board, "Ra3")) == 2


def test_starting_position_is_the_default():
    result = parse_tokens(moves(("move_number", "1."), ("move", "e4")))

    assert result.games[0].initial_fen == chess.STARTING_FEN


class TestLostSymbol:
    """A move whose piece symbol the glyph pass never restored.

    What is left on the page spells a pawn move, and playing it is worse than
    losing the move: it is legal often enough to be taken at full confidence,
    and every move after it is then played on a position the book never
    reached. The board is asked instead.
    """

    def opening(self, square: str, wreck: str, plies: int = 5) -> list[Token]:
        # 1 d4 Nf6 2 c4 g6 3 Nc3, the first five plies of page 3 of the Grivas
        # book, whose sixth is printed `i.g7` and was read as a pawn move.
        played = ["d4", "Nf6", "c4", "g6", "Nc3"][:plies]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        if len(played) % 2 == 0:
            tokens.append(tok("move_number", str(len(played) // 2 + 1)))
        tokens.append(tok("move", square, lost_symbol=wreck))
        return tokens

    def test_the_board_names_the_piece_when_only_one_can_reach(self):
        # No knight, rook, queen or king has any move to g7 here. The bishop
        # on f8 does, and it is what the book printed.
        result = parse_tokens(self.opening("g7", "i."))
        last = result.moves[-1]

        assert last.san == "Bg7"
        # Deduced, not read: it must not pass for a move the book spelled out.
        assert last.status == "uncertain"
        assert last.repair["reason"].startswith("read as Bg7")

    def test_the_pawn_move_it_spells_is_never_the_answer(self):
        # a7-a6 is perfectly legal here, and `ll:\a6` used to be scored as it,
        # ok, at full confidence. The wreck says a piece was printed, so the
        # pawn reading is not a candidate at all — only the knight reaches a6,
        # the bishop on c8 being shut in by its own pawn.
        result = parse_tokens(self.opening("a6", "ll:\\"))
        last = result.moves[-1]

        assert (last.san, last.status) == ("Na6", "uncertain")

    def test_two_pieces_reaching_the_square_are_left_to_the_reader(self):
        # After 1 d4 Nf6 2 c4, black can play both Rg8 and Ng8, and nothing on
        # the page separates them. Guessing would hide the problem; the pair
        # goes out as `candidates` for the reader to pick between.
        result = parse_tokens(self.opening("g8", "l:t", plies=3))
        last = result.moves[-1]

        assert last.status == "broken"
        assert sorted(result.ambiguities[-1]["candidates"]) == ["Ng8", "Rg8"]

    def test_a_move_with_no_wreck_is_read_as_printed(self):
        result = parse_tokens(self.opening("a6", ""))
        last = result.moves[-1]

        assert (last.san, last.status, last.confidence) == ("a6", "ok", 1.0)
