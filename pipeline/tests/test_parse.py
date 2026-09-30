"""Tests for the move tree and the legality pass.

These build tokens directly instead of going through a PDF: the parser's job
is to turn a token sequence into a validated tree, and pinning that down does
not need a document. Extraction is exercised by the notebook's visual check,
which is the only thing that can really tell whether a box sits on its move.
"""

import dataclasses

import chess
import pytest

from rce_pipeline.extract import BBox
from rce_pipeline.parse import (
    _ambiguous_candidates,
    _confusable_distance,
    _number_stripped_of_a_lost_move,
    parse_tokens,
    weight_marks_the_line,
)
from rce_pipeline.tokenize import Token

BOX = BBox(72.0, 640.0, 18.0, 10.0)


def tok(
    kind: str, text: str, page: int = 1, consumed: str = "", lost_symbol: str = "",
    bold: bool = False, lost_piece: str = "",
) -> Token:
    return Token(
        kind=kind, text=text, raw=text, page=page,
        start=0, end=len(text), bbox=BOX, consumed=consumed,
        lost_symbol=lost_symbol, bold=bold, lost_piece=lost_piece,
    )


def moves(*pairs: tuple[str, str]) -> list[Token]:
    return [tok(kind, text) for kind, text in pairs]


def weighed(*triples: tuple[str, str, bool]) -> list[Token]:
    """Tokens carrying the weight the book set them in — bold, or plain."""
    return [tok(kind, text, bold=bold) for kind, text, bold in triples]


def on_the_main_line(result, move) -> bool:
    """Whether this move was played on the game rather than beside it."""
    return chess.Board(move.fen).board_fen() in result.main_lines[move.game_id]


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

    def test_a_licence_is_spent_on_prose_and_not_on_the_move_beside_it(self):
        """What ends a number's licence is prose, not the count of the moves.

        A scan destroys the numbers of the score as readily as anything else —
        "par 1" for "par 18." — and the move that lost its number is still
        printed where it always was, hard against the move in front of it.
        Refused for want of a licence it is dropped with its box, and the
        reader cannot even correct it. Read there it costs nothing that the
        licence was for: what the licence keeps out is the commentary naming a
        square, and prose is what stands in front of that.
        """
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                ("move", "Bc4"),
            )
        )

        assert sans(result) == ["e4", "e5", "Nf3", "Nc6", "Bc4"]

    def test_a_word_after_the_licence_is_spent_is_still_refused(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                ("text", "White develops with"), ("move", "Bc4"),
            )
        )

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
    13...Nb6 14 g5", "Threatening 17...Nxc2" — with no bracket and no indent.
    Read as the continuation, such a line is played on a position the book
    never reached and everything after it breaks.

    The printed number is all there is to go on for a scan, whose text layer
    is the OCR's own and carries no weight. A book that was typeset carries
    the answer in the weight of the type, which is a fact rather than an
    inference: see `TestTheWeightOfTheType`.
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


class TestAGameWithNoStartingPosition:
    def test_analysis_quoted_after_a_result_is_read_but_not_scored(self):
        # "Black resigned in view of 27...Rf6 28 d5": a line nobody played,
        # printed after the game it belongs to has ended.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("result", "1-0"),
                ("move_number", "27..."), ("move", "Rf6"),
                ("move_number", "28."), ("move", "d5"),
            )
        )

        quoted = [m for m in result.moves if m.game_id == result.games[-1].id]
        assert [m.san for m in quoted] == ["Rf6", "d5"]
        assert all(m.status == "broken" and m.fen is None for m in quoted)
        assert result.games[-1].position_known is False
        # None of it counts: the pipeline was never asked to place these.
        assert result.break_diagnosis()["clean"] == 2      # e4 and e5
        assert result.break_diagnosis()["unscored"] == 2

    def test_the_moves_keep_their_boxes(self):
        result = parse_tokens(moves(("move_number", "27..."), ("move", "Rf6")))

        assert result.moves[0].bbox == BOX


class TestAFalseDisambiguator:
    """`♗1g3` is `Bg3`: the `1` is what is left of the bishop, not a rank."""

    def test_the_wreck_between_the_piece_and_the_square_is_dropped(self):
        # `Nbf3` names a knight on the b-file, and there is none: the letter is
        # what is left of the symbol. (`N1f3` would parse as written — a
        # redundant disambiguator is still true — and needs no repair.)
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nbf3"),
            )
        )

        knight = result.moves[-1]
        assert knight.san == "Nf3"
        assert knight.status == "uncertain"
        assert knight.confidence == 0.5

    def test_nothing_is_dropped_where_the_board_cannot_settle_it(self):
        # Both knights reach d2, so removing the letter leaves a move the board
        # cannot choose between. The move stays broken rather than being read
        # as one of the two at random.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "Nf3"), ("move", "d5"),
                ("move_number", "2."), ("move", "e3"), ("move", "e6"),
                ("move_number", "3."), ("move", "Ncd2"),
            )
        )

        assert result.moves[-1].status == "broken"

    def test_a_square_is_never_repaired_this_way(self):
        # `Qh9` is not a disambiguated move, and nothing here may turn it into
        # `Qh5`: that is the mistake `_MAX_REPAIR_COST` exists to refuse.
        result = parse_tokens(
            moves(("move_number", "1."), ("move", "e4"), ("move", "e5"),
                  ("move_number", "2."), ("move", "Qh9")),
        )

        assert result.moves[-1].status == "broken"


class TestAPawnCaptureFromTheWrongFile:
    """Sakaev page 26: "6...♗c5 7.♘c2 d5 8.exd5" for `8.cxd5` — the square and
    the capture are the book's, the file it names has no pawn to make it."""

    def test_the_one_pawn_that_takes_there_is_the_move(self):
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "c4"), ("move", "d5"),
            ("move_number", "2."), ("move", "exd5"),
        ))

        pawn = result.moves[-1]
        assert (pawn.san, pawn.status, pawn.confidence) == ("cxd5", "uncertain", 0.5)

    def test_nothing_is_chosen_where_two_pawns_take_there(self):
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "c4"), ("move", "d5"),
            ("move_number", "2."), ("move", "e4"), ("move", "Nf6"),
            ("move_number", "3."), ("move", "fxd5"),
        ))

        assert result.moves[-1].status == "broken"


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
            "contradicted": 0, "drifted": 0, "unscored": 0,
        }

    def test_counts_the_moves_below_a_number_the_line_no_longer_matches(self):
        # The book announces its third move and the line has only two behind
        # it: one was never read. Nothing here is illegal — `Nc6` and `Bc4`
        # are both fine — and both are played on a board a move behind the
        # one the book printed, which is what `drifted` is for.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"),
                ("move_number", "3."), ("move", "Nc6"), ("move", "Bc4"),
            )
        )

        assert [m.status for m in result.moves] == ["ok"] * 5
        diagnosis = result.break_diagnosis()
        assert diagnosis["clean"] == 3
        assert diagnosis["drifted"] == 2
        assert set(result.drifted) == {result.moves[3].id, result.moves[4].id}

    def test_an_aside_from_before_the_line_drifted_is_not_adrift(self):
        # Pachman's chapters: a model game whose score loses a move, and the
        # other systems cited from its fourth move — "2° 4. e3 …". A system
        # branched at a position the line reached before it lost anything
        # stands on the board the book printed, whatever the score did later.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"),
                ("move_number", "3."), ("move", "Nc6"), ("move", "Bc4"),
                ("text", "Instead of that,"),
                ("move_number", "2..."), ("move", "d6"),
                ("move_number", "3."), ("move", "d4"),
            )
        )

        cited = [m for m in result.moves if m.san in ("d6", "d4")]
        assert [m.status for m in cited] == ["ok", "ok"]
        assert not {m.id for m in cited} & set(result.drifted)

    def test_the_board_a_diagram_puts_back_is_not_below_the_break_above_it(self):
        # A line breaks, and the book then prints the position: the moves after
        # it are played on the printed board, and stand whatever broke above.
        # Counted below the break, Chess College 3's right table showed 156
        # more moves "below a break" than reading no board at all.
        board = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6"):
            board.push_san(san)
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                ("move_number", "3."), ("move", "Bb5"), ("move", "Qh8"),
            ) + [tok("diagram", rows)] + moves(
                ("move_number", "4."), ("move", "Ba4"), ("move", "Nf6"),
            ),
            diagram_table=table,
        )

        after = [m for m in result.moves if m.san in ("Ba4", "Nf6")]
        assert [m.status for m in after] == ["ok", "ok"]
        assert result.break_diagnosis()["below_break"] == 0

    def test_a_diagram_of_the_analysis_does_not_move_the_game(self):
        # Markos page 82: a variation in plain prose ends on a diagram of the
        # position it reached ("he has a beautiful move. Can you see it?"),
        # then "let's get back to the game" and the score resumes in bold.
        # Read as a correction of the game, the board put the score on the
        # variation, and the game's `20.Qg3` was played by Black's queen.
        aside = chess.Board()
        for san in ("e4", "e5", "Nf3", "d6", "d4"):
            aside.push_san(san)
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := aside.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                ("text", "Also possible is", False),
                ("move_number", "2...", False), ("move", "d6", False),
                ("move_number", "3.", False), ("move", "d4", False),
            ) + [tok("diagram", rows)] + weighed(
                ("text", "After", False),
                ("move_number", "3...", False), ("move", "exd4", False),
                ("text", "Black is fine. Back to the game:", False),
                ("move_number", "3.", True), ("move", "Bb5", True), ("move", "a6", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        game = [m for m in result.moves if m.san in ("Bb5", "a6")]
        assert [m.status for m in game] == ["ok", "ok"]
        assert all(on_the_main_line(result, m) for m in game)
        assert not result.contradicted

    def test_a_diagram_read_is_exported_with_its_box_and_position(self):
        # The reader opens a diagram's position when it is tapped, so the
        # contract carries every board that could be read, where it stands.
        board = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6"):
            board.push_san(san)
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows, page=3), bbox=BBox(50, 400, 200, 200))
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                ("move_number", "3."), ("move", "Bb5"), ("move", "a6"),
            ) + [diagram],
            diagram_table=table,
        )

        (exported,) = result.to_json()["diagrams"]
        assert exported["page"] == 3
        assert exported["bbox"] == {"x": 50, "y": 400, "w": 200, "h": 200}
        assert exported["fen"].split()[:2] == [board.board_fen(), "w"]

    def test_a_line_that_matches_again_stops_being_adrift(self):
        # A number the line does agree with clears it: whatever was lost, the
        # book and the board are on the same move again, and what follows
        # stands on the position that was printed.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"),
                ("move_number", "3."), ("move", "Nc6"),
                ("move_number", "3."), ("move", "Bc4"),
            )
        )

        diagnosis = result.break_diagnosis()
        assert diagnosis["drifted"] == 1
        assert diagnosis["clean"] == 4


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

    def test_a_broken_move_keeps_its_geometry_and_empties_the_line(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "a6"),
                ("move_number", "2."), ("move", "Qh9"), ("move", "b6"),
            )
        )

        broken = [m for m in result.moves if m.status == "broken"]
        assert [m.san for m in broken] == ["Qh9", "b6"]
        assert all(m.bbox == BOX and m.page == 1 for m in broken)
        # `b6` is legal here, and it is still not played: the board this line
        # holds is the one from before `Qh9`, and a move that happens to fit it
        # would be scored `ok` on a position the book never reached. What the
        # number announced is read for its box and nothing else — 790 move
        # tokens over the corpus used to be dropped outright, so the reader
        # could not even tap them to correct them.
        assert sans(result) == ["e4", "a6", "Qh9", "b6"]
        assert all(m.fen is None and m.confidence == 0.0 for m in broken)

    def test_the_next_number_starts_the_line_again(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "a6"),
                ("move_number", "2."), ("move", "Qh9"), ("move", "b6"),
                ("move_number", "3."), ("move", "Nf3"),
            )
        )

        # The book reprinting a number is where it starts the score again, so
        # the board is asked once more — `Nf3` is legal after 1 e4 a6.
        last = result.moves[-1]
        assert (last.san, last.status) == ("Nf3", "ok")

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

    def opening(
        self, square: str, wreck: str, plies: int = 5, spelled: str = ""
    ) -> list[Token]:
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
        tokens.append(tok("move", square, lost_symbol=wreck, lost_piece=spelled))
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

    def test_the_square_may_be_wrecked_as_well_as_the_symbol(self):
        # `♘d5` printed `tL!dS`: the symbol is gone and the scanner has read
        # the rank as a letter. Nothing spells a legal move then, so the near
        # -free substitutions the repair path allows are tried against the
        # legal moves that name a piece — and only the knight fits.
        result = parse_tokens(self.opening("dS", "l:t"))
        last = result.moves[-1]

        assert (last.san, last.status) == ("Nd5", "uncertain")

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

    def test_a_capture_with_nothing_in_front_of_it_is_a_lost_piece(self):
        # Grivas page 29: the symbol of `♗xc3+` left no character at all, not
        # even a wreck to hand over. No SAN begins with a capture — a pawn
        # names the file it captures from — so the board is asked which piece,
        # and only the bishop on b4 can take on c3.
        played = ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "Bg5", "h6",
                  "Bh4", "c5", "d5"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        tokens += moves(("move_number", "6..."), ("move", "xc3+"))
        last = parse_tokens(tokens).moves[-1]

        assert (last.san, last.status) == ("Bxc3+", "uncertain")
        assert last.repair["reason"].startswith("read as Bxc3+")

    def test_a_capture_two_pieces_could_have_made_is_left_to_the_reader(self):
        # 1 d4 d5 2 Nc3 Nf6 3 Bf4 Bf5 4 Nb5 Na6 5 Nxc7+ and `xc7`: the queen
        # and the knight on a6 both take there, and nothing on the page
        # separates them.
        played = ["d4", "d5", "Nc3", "Nf6", "Bf4", "Bf5", "Nb5", "Na6", "Nxc7+"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        tokens += moves(("move_number", "5..."), ("move", "xc7"))
        result = parse_tokens(tokens)

        assert result.moves[-1].status == "broken"
        assert sorted(result.ambiguities[-1]["candidates"]) == ["Nxc7", "Qxc7"]


    def test_a_piece_that_only_walks_there_is_not_the_capture_printed(self):
        # `python-chess` reads `Rxh7` on an empty h7 as the quiet move it
        # spells, so every lost capture would find a piece that merely walks
        # to the square. 1 d4 Nf6 2 Nf3 and `xe4`: nothing stands on e4.
        played = ["d4", "Nf6", "Nf3"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        tokens += moves(("move_number", "2..."), ("move", "xe4"))
        last = parse_tokens(tokens).moves[-1]

        assert last.status == "broken"
        assert "no piece reaches this square" in last.repair["reason"]

    def test_the_letter_left_in_the_wreck_names_the_piece(self):
        # Grivas prints `♖f.f7+` and `♔>d2`: the symbol *was* read and its
        # letter written back, and only the ink left around it kept the move
        # from beginning on the letter. After 1 d4 Nf6 2 c4 both the rook and
        # the knight reach g8 and the board cannot choose — the page can.
        result = parse_tokens(self.opening("g8", "R.", plies=3))
        last = result.moves[-1]

        assert (last.san, last.status) == ("Rg8", "uncertain")
        assert result.ambiguities[-1]["settled_by"] == "the letter left in the wreck"

    def test_the_same_wreck_with_the_other_letter_names_the_other_piece(self):
        last = parse_tokens(self.opening("g8", "N>", plies=3)).moves[-1]

        assert (last.san, last.status) == ("Ng8", "uncertain")

    def test_a_letter_no_move_of_that_piece_fits_leaves_it_to_the_board(self):
        # No queen has any move to g7 here. Either the classifier misread the
        # symbol or the line is already somewhere the book never was, and
        # neither is settled here: the five pieces are asked as before, and
        # only the bishop fits.
        last = parse_tokens(self.opening("g7", "Q'")).moves[-1]

        assert (last.san, last.status) == ("Bg7", "uncertain")

    def test_the_books_own_spelling_names_the_piece(self):
        # Boussole page 65 prints `9.i.xg5`, and both the bishop and the
        # knight take on g5. The book has spelled its bishop `i.` thirty-nine
        # times under a symbol the glyph pass did restore, and the parser was
        # asking the board instead: the move died, and fifteen under it.
        result = parse_tokens(self.opening("g8", "l:t", plies=3, spelled="R"))
        last = result.moves[-1]

        assert (last.san, last.status) == ("Rg8", "uncertain")
        assert last.repair["reason"] == "read as Rg8: the book spells its R 'l:t'"
        assert result.ambiguities[-1]["settled_by"] == "the book's own spelling"

    def test_the_letter_in_the_wreck_comes_before_the_spelling(self):
        # The classifier read *this* symbol and wrote its letter back. A
        # spelling is a vote over the ones it read elsewhere.
        last = parse_tokens(self.opening("g8", "N>", plies=3, spelled="R")).moves[-1]

        assert last.san == "Ng8"

    def test_a_spelling_no_move_of_that_piece_fits_leaves_it_to_the_board(self):
        last = parse_tokens(self.opening("g7", "i.", spelled="Q")).moves[-1]

        assert (last.san, last.status) == ("Bg7", "uncertain")

    def test_two_letters_in_the_wreck_name_nothing(self):
        # The run has reached past the symbol into whatever stood before it,
        # so neither letter can be trusted to be the piece.
        result = parse_tokens(self.opening("g8", "RN.", plies=3))

        assert result.moves[-1].status == "broken"
        assert sorted(result.ambiguities[-1]["candidates"]) == ["Ng8", "Rg8"]


class TestABracketAScanInvented:
    """A scan prints brackets the book never had, and they were believed whole.

    Boussole page 65 comments on 5...h6 with a passage the OCR opens a `(` in
    the middle of. Nothing closes it on the page, so the score of the game —
    `6.h3 0-0 7.g4!`, printed bold two lines below — was read inside that
    bracket, and the first move of it that could not be legal there took the
    rest of the page with it.
    """

    def opening(self, *tail: tuple[str, str]) -> list[Token]:
        played = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        return tokens + [tok(kind, text) for kind, text in tail]

    def test_the_game_picking_up_again_closes_it(self):
        # The bracket runs four plies past the game, and then `4.` names the
        # ply the game is waiting for — which nothing in the bracket can be.
        result = parse_tokens(
            self.opening(
                ("var_open", "("),
                ("move_number", "3..."), ("move", "Nf6"),
                ("move_number", "4."), ("move", "Nc3"), ("move", "d6"),
                ("move_number", "5."), ("move", "d3"),
                ("move_number", "4."), ("move", "b4"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["b4"].status == "ok"
        assert on_the_main_line(result, by_san["b4"])
        assert by_san["b4"].parent_id == by_san["Bc5"].id
        assert not on_the_main_line(result, by_san["Nf6"])

    def test_the_bracket_own_line_is_still_left_alone(self):
        # Its numbering continues inside it, and the game is not taken to be
        # picking up because a number happens to come round.
        result = parse_tokens(
            self.opening(
                ("var_open", "("),
                ("move_number", "3..."), ("move", "Nf6"),
                ("move_number", "4."), ("move", "Nc3"), ("move", "d6"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["d6"].status == "ok"
        assert not on_the_main_line(result, by_san["d6"])


class TestWhichSideOfTheMoveABracketOpensOn:
    """`(` branches before the move it follows — unless its number says not.

    "6...h6, and White is already obliged (7.♗xf6 ♕xf6 8.♘d5)": the bracket
    continues the move it follows instead of replacing it, and branched a move
    too early every move of it is read for the wrong colour.
    """

    def opening(self, *tail: tuple[str, str]) -> list[Token]:
        played = ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        return tokens + [tok(kind, text) for kind, text in tail]

    def test_a_bracket_naming_the_ply_awaited_continues_the_move(self):
        result = parse_tokens(
            self.opening(
                ("var_open", "("),
                ("move_number", "4."), ("move", "Bg5"), ("move", "h6"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        assert (by_san["Bg5"].status, by_san["h6"].status) == ("ok", "ok")
        assert by_san["Bg5"].parent_id == by_san["Bb4"].id
        assert not on_the_main_line(result, by_san["Bg5"])

    def test_an_alternative_to_the_move_still_replaces_it(self):
        # `3...` is the move just played, so the bracket is an alternative to
        # it and branches where it always did.
        result = parse_tokens(
            self.opening(
                ("var_open", "("),
                ("move_number", "3..."), ("move", "d5"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["d5"].status == "ok"
        assert by_san["d5"].parent_id == by_san["Nc3"].id

    def test_a_bracket_naming_the_game_s_ply_inside_an_aside_opens_on_the_game(self):
        # Markos page 167, inside "b) 20.♖c1 ♗d5 21.♖xc7": "(From the initial
        # diagram, this position can also be reached by a different route:
        # 19.♖c1 ♗d5 20.cxd6 cxd6 21.♖c7)" — the ply the game awaits, below
        # the aside the bracket opened in.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "d4", True), ("move", "Nf6", True),
                ("move_number", "2.", True), ("move", "c4", True), ("move", "e6", True),
                ("text", "a)", False),
                ("move_number", "3.", False), ("move", "Nc3", False), ("move", "Bb4", False),
                ("text", "b)", False),
                ("move_number", "3.", False), ("move", "g3", False), ("move", "b6", False),
                ("move_number", "4.", False), ("move", "Nf3", False), ("move", "Bb7", False),
                ("move_number", "5.", False), ("move", "Bg2", False),
                ("var_open", "(", False),
                ("text", "or by a different route:", False),
                ("move_number", "3.", False), ("move", "Nf3", False), ("move", "b6", False),
                ("move_number", "4.", False), ("move", "g3", False),
                ("var_close", ")", False),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]
        by_id = {m.id: m for m in result.moves}
        routed = [m for m in result.moves if m.san == "Nf3"][-1]
        assert by_id[routed.parent_id].san == "e6"


class TestTwoAlternativesCitedTogether:
    """"White can choose between 7 ♘a2 and 7 ♘b1", both at the same juncture.

    The second alternative carries the number the main line is waiting for, so
    the aside the first one opened is closed on it and it is played as the
    continuation — where it is illegal, since the two are alternatives to the
    same move and only one of them is the game.
    """

    def opening(self, *tail: tuple[str, str]) -> list[Token]:
        # Grivas-Siebrecht, page 17: 1 d4 d5 2 c4 c6 3 Nf3 Nf6 4 Nc3 dxc4
        # 5 e3 b5 6 a4 Qa5, then "6...b4 is more natural, when White can
        # choose between 7 Na2 and 7 Nb1".
        played = ["d4", "d5", "c4", "c6", "Nf3", "Nf6", "Nc3", "dxc4",
                  "e3", "b5", "a4", "Qa5"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        tokens += moves(("move_number", "6..."), ("move", "b4"),
                        ("move_number", "7"), ("move", "Na2"))
        return tokens + [tok(kind, text) for kind, text in tail]

    def test_the_second_alternative_stands_beside_the_first(self):
        result = parse_tokens(
            self.opening(("move_number", "7"), ("move", "Nb1"))
        )
        by_id = {move.id: move for move in result.moves}
        first = next(move for move in result.moves if move.san == "Na2")
        second = result.moves[-1]

        # Legal after 6...b4 and pinned stiff after 6...Qa5: the queen bears
        # on e1 through c3, so the knight on c3 cannot move at all.
        assert second.san == "Nb1"
        assert second.status == "ok"
        # Beside the move it is an alternative to, not under it.
        assert second.parent_id == first.parent_id
        assert by_id[second.parent_id].san == "b4"

    def test_the_main_line_still_picks_up_where_it_left_off(self):
        # The resumption the number announced is what usually follows, and it
        # must not be diverted: 7 Bd2 is legal in the game and never reaches
        # the aside at all.
        result = parse_tokens(
            self.opening(("move_number", "7"), ("move", "Bd2"))
        )
        by_id = {move.id: move for move in result.moves}
        last = result.moves[-1]

        assert (last.san, last.status) == ("Bd2", "ok")
        assert by_id[last.parent_id].san == "Qa5"


class TestWeightMarksTheLine:
    """Whether the book's own typesetting can be read as marking the score."""

    def bolds(self, pattern: str) -> bool:
        # One move number per character: `#` bold, `.` plain.
        return weight_marks_the_line(
            [tok("move_number", "1.", bold=ch == "#") for ch in pattern]
        )

    def test_the_moves_own_weight_is_not_asked(self):
        # A figurine is a dense drawing, and on a scan the moves carrying one
        # overlap between the weights. Only the numbers are ever measured.
        assert not weight_marks_the_line(
            [tok("move", "e4", bold=n % 2 == 0) for n in range(60)]
        )

    def test_a_book_setting_its_score_apart_is_read(self):
        assert self.bolds("#." * 30)

    def test_one_weight_throughout_says_nothing(self):
        # Every scan: the text layer is the OCR's own and carries no weight.
        assert not self.bolds("." * 60)
        assert not self.bolds("#" * 60)

    def test_a_handful_of_the_other_weight_is_not_a_convention(self):
        # A bold caption or two in a book that sets everything else plain.
        assert not self.bolds("#" * 3 + "." * 60)

    def test_too_few_moves_to_tell(self):
        assert not self.bolds("#." * 8)


class TestTheWeightOfTheType:
    """The line a move belongs to, read from the weight the book set it in.

    Where a publisher typesets the game score bold and the analysis around it
    plain — Sakaev, Markos and the Tactics book all do — the weight is a fact
    where `_place_by_number` has only an inference, and it sees the case the
    arithmetic cannot: analysis printed at exactly the half-move the game is
    waiting for.
    """

    def test_analysis_agreeing_with_the_line_still_opens_a_variation(self):
        # "The main continuations here are the classical 2...d6" — printed
        # where the game awaits Black's second, and not the continuation.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True),
                ("move_number", "2...", False), ("move", "d6", False),
                ("move_number", "2...", True), ("move", "Nc6", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        # Both hang off Nf3, and it is the printed score that carries the game.
        assert by_san["d6"].parent_id == by_san["Nf3"].id
        assert by_san["Nc6"].parent_id == by_san["Nf3"].id
        assert on_the_main_line(result, by_san["Nc6"])
        assert not on_the_main_line(result, by_san["d6"])
        assert all(m.status == "ok" for m in result.moves)

    def test_a_move_in_the_analysis_weight_never_stands_on_the_game(self):
        # Sakaev page 37: "Here it is essential to consider in which variation
        # of the Caro-Kann the move ...b7-b5 will be least useful." The move
        # has no number of its own — the prose ellipsis is its whole licence —
        # so nothing places it, and the game has already played it: illegal
        # where it stands, and every move of the chapter under it. The weight
        # says it is not the score before the board is even asked.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "c6", True),
                ("move_number", "2.", True), ("move", "d4", True), ("move", "d5", True),
                ("move_number", "3.", True), ("move", "Nc3", True), ("move", "b5", True),
                ("move_number", "4.", True), ("move", "e5", True),
                ("text", "essential to consider the move ...", False),
                ("move", "b5", False),
                ("move_number", "4...", True), ("move", "e6", True),
                ("move_number", "5.", True), ("move", "Nf3", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert (by_san["e6"].status, by_san["Nf3"].status) == ("ok", "ok")
        assert on_the_main_line(result, by_san["e6"])
        # The citation is read and it is broken — the game has played it
        # already — but it broke beside the score and not on it.
        cited = [m for m in result.moves if m.san == "b5"][-1]
        assert cited.status == "broken"
        assert result.break_diagnosis()["below_break"] == 0

    def test_the_arithmetic_reads_the_same_line_as_the_continuation(self):
        # The same tokens with the weight taken away. `2...d6` agrees with the
        # board the game stands on, so nothing diverts it: it is played on the
        # game, and `2...Nc6` — the move the book actually printed there — is
        # filed as the variation. The two have swapped places, and every
        # position the rest of the page is read from is one move wrong.
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"),
                ("move_number", "2..."), ("move", "d6"),
                ("move_number", "2..."), ("move", "Nc6"),
            )
        )

        by_san = {m.san: m for m in result.moves}
        assert on_the_main_line(result, by_san["d6"])
        assert not on_the_main_line(result, by_san["Nc6"])

    def test_analysis_of_several_moves_is_not_restarted_at_each_number(self):
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                # "2.Bc4 Bc5 3.Qh5 Nf6" — one variation, three numbers.
                ("move_number", "2.", False), ("move", "Bc4", False), ("move", "Bc5", False),
                ("move_number", "3.", False), ("move", "Qh5", False), ("move", "Nf6", False),
                ("move_number", "3.", True), ("move", "Bb5", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["Bc5"].parent_id == by_san["Bc4"].id
        assert by_san["Qh5"].parent_id == by_san["Bc5"].id
        assert by_san["Nf6"].parent_id == by_san["Qh5"].id
        assert by_san["Bb5"].parent_id == by_san["Nc6"].id
        assert all(m.status == "ok" for m in result.moves)

    def test_the_score_resuming_ends_the_analysis_before_a_new_game_opens(self):
        # A book whose analysis runs to the foot of the page and whose next
        # game opens the one after. Without the score's weight closing the
        # variation first, `1.d4` is read inside it and the two games are one.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", False), ("move", "Bc4", False),
                ("move_number", "1.", True), ("move", "d4", True), ("move", "d5", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert len(result.games) == 2
        assert by_san["d4"].game_id == result.games[1].id
        assert by_san["d4"].parent_id is None

    def test_brackets_still_win(self):
        # The weight is the book's word on prose; inside a bracket it has
        # already said what it means, and publishers set variations in
        # brackets in the score's own weight.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("var_open", "(", True),
                ("move_number", "1...", True), ("move", "c5", True),
                ("var_close", ")", True),
                ("move_number", "2.", True), ("move", "Nf3", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["c5"].parent_id == by_san["e4"].id
        assert by_san["Nf3"].parent_id == by_san["e5"].id


class TestTheScoreGoingBackToAnEarlierMove:
    def test_its_next_number_carries_on_the_line_it_went_back_to(self):
        # Markos pages 192-193, all in bold: "50...f3? 51.♖f8 … 59.♔f2+–
        # Returning to the 50th move, Black, therefore, has to play: 50...♔h3!
        # 51.♖h8† ♔g2 52.h4". `50...♔h3` was placed at the 50th, and `51.`,
        # bold, was read as the score resuming after 59.♔f2.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                ("move_number", "3.", True), ("move", "Bb5", True), ("move", "a6", True),
                ("text", "Returning to the second move, Black has to play:", False),
                ("move_number", "2...", True), ("move", "d6", True),
                ("move_number", "3.", True), ("move", "d4", True), ("move", "exd4", True),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]
        by_id = {m.id: m for m in result.moves}
        d4 = next(m for m in result.moves if m.san == "d4")
        assert by_id[d4.parent_id].san == "d6"


class TestAnalysisInsideAnalysis:
    """Markos page 22: the plain analysis branches inside itself.

    "Ribli's recommendation was: 17...♖g8 18.fxe6 fxe6 / 18...♗xe6 19.♘d5 ♕d8
    20.♘xe6 fxe6 21.e5!+– / 19.e5! dxe5 […] 20.♗g5! Ribli analysed only
    20.♘e4. There is now a forced line: 20...♗c6 21.♗xf6 …" — the game stands
    at 17...♕d8, and every one of these numbers names a ply only Ribli's line
    has reached. Played on the game's board, `18...♗xe6` broke and `19.e5` was
    legal there by chance: a wrong position marked right.
    """

    def test_a_sub_variation_branches_from_the_analysis_and_the_analysis_resumes(self):
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                # The analysis: an alternative to the game's second move…
                ("move_number", "2...", False), ("move", "Nf6", False),
                ("move_number", "3.", False), ("move", "Nxe5", False), ("move", "d6", False),
                # …an alternative inside it, at a ply the game never reached…
                ("move_number", "3...", False), ("move", "Qe7", False),
                ("move_number", "4.", False), ("move", "d4", False), ("move", "d6", False),
                # …and the analysis again, where it stopped.
                ("move_number", "4.", False), ("move", "Nf3", False), ("move", "Nxe4", False),
                ("move_number", "3.", True), ("move", "Bc4", True), ("move", "Bc5", True),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]
        by_id = {m.id: m for m in result.moves}
        qe7 = next(m for m in result.moves if m.san == "Qe7")
        assert by_id[qe7.parent_id].san == "Nxe5"
        knight_back = [m for m in result.moves if m.san == "Nf3"][-1]
        first_d6 = next(m for m in result.moves if m.san == "d6")
        assert knight_back.parent_id == first_d6.id
        bc4 = next(m for m in result.moves if m.san == "Bc4")
        assert by_id[bc4.parent_id].san == "Nc6"
        assert on_the_main_line(result, bc4)

    def test_of_two_lines_awaiting_a_move_the_one_the_score_carries_is_taken(self):
        # "20.♗g5! Ribli analysed only 20.♘e4. There is now a forced line:
        # 20...♗c6 21.♗xf6" — `20...♗c6` plays after either, and the move
        # after it only after the one the book was printing before.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                ("move_number", "2...", False), ("move", "Nf6", False),
                ("move_number", "3.", False), ("move", "Nc3", False),
                ("text", "Ribli analysed only", False),
                ("move_number", "3.", False), ("move", "d3", False),
                ("text", "There is now a forced line:", False),
                ("move_number", "3...", False), ("move", "Bb4", False),
                ("move_number", "4.", False), ("move", "Nd5", False),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]
        by_id = {m.id: m for m in result.moves}
        d3 = next(m for m in result.moves if m.san == "d3")
        assert by_id[d3.parent_id].san == "Nf6"
        bb4 = next(m for m in result.moves if m.san == "Bb4")
        assert by_id[bb4.parent_id].san == "Nc3"

    def test_after_prose_a_number_both_await_goes_back_to_the_game(self):
        # Markos page 61, the game at 38...♖xd8: "38...d2?! is inaccurate,
        # because […] 39.♖d1? ♘b2 40.♖d2 ♗c3 leads to the capture of the
        # rook. 39.b6 gives away a pawn […]: 39...d2" — the aside awaits
        # White's 39th as the game does, and the prose between says it ended.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                ("move_number", "2...", False), ("move", "Nf6", False),
                ("text", "is inaccurate, because it would give White the e5-pawn.", False),
                ("move_number", "3.", False), ("move", "Bb5", False),
                ("text", "gives away a pawn:", False),
                ("move_number", "3...", False), ("move", "Nd4", False),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]
        by_id = {m.id: m for m in result.moves}
        bb5 = next(m for m in result.moves if m.san == "Bb5")
        assert by_id[bb5.parent_id].san == "Nc6"

    def test_prose_that_does_not_end_a_sentence_does_not_end_the_aside(self):
        # Markos page 82, the game at 19...♖e5: "Black could maintain an equal
        # game only with the accurate 19...♗xc3! because after 20.♖xf5?" —
        # the sentence runs on into the aside's next move.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                ("text", "Black could hold with the accurate", False),
                ("move_number", "2...", False), ("move", "d6", False),
                ("annotation", "!", False),
                ("text", "because after", False),
                ("move_number", "3.", False), ("move", "d4", False),
            ),
            weighted=True,
        )

        by_id = {m.id: m for m in result.moves}
        d4 = next(m for m in result.moves if m.san == "d4")
        assert by_id[d4.parent_id].san == "d6"

    def test_the_reply_to_an_alternative_at_its_own_number_carries_it_on(self):
        # Markos page 50, the game at 36.♗g5: "36.♗e3 is best, but still does
        # not save White: 36...♖e2 37.♘f5" — prose between, the game waiting
        # for Black's 36th too, and the moves after playing on both boards.
        # The reply at the alternative's own number is its reply.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True),
                ("move_number", "2.", False), ("move", "Bc4", False),
                ("text", "is best, but still does not save White:", False),
                ("move_number", "2...", False), ("move", "Nf6", False),
                ("move_number", "3.", False), ("move", "d3", False),
            ),
            weighted=True,
        )

        by_id = {m.id: m for m in result.moves}
        nf6 = next(m for m in result.moves if m.san == "Nf6")
        assert by_id[nf6.parent_id].san == "Bc4"

    def test_the_moves_are_tried_on_past_the_prose_that_interrupts_them(self):
        # Markos page 98, the game at 17.♘h3!?: "However, even better is the
        # straightforward: 17.♖h3! … 17...e5 […] 18.♖xh7" — `17...e5` plays
        # after either, and only the move after the prose tells them apart.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Bc4", True),
                ("text", "Even better is the straightforward:", False),
                ("move_number", "2.", False), ("move", "Qh5", False),
                ("text", "and now after", False),
                ("move_number", "2...", False), ("move", "Nc6", False),
                ("text", "White goes", False),
                ("move_number", "3.", False), ("move", "Qxf7+", False),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]

    def test_and_past_the_board_printed_between_them(self):
        # The same page: a diagram stands between `17...e5?` and `18.♖xh7`.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Bc4", True),
                ("text", "Even better is the straightforward:", False),
                ("move_number", "2.", False), ("move", "Qh5", False),
                ("text", "and now after", False),
                ("move_number", "2...", False), ("move", "Nc6", False),
                ("text", "Black is in grave danger.", False),
            ) + [tok("diagram", "/".join(["........"] * 8))] + weighed(
                ("move_number", "3.", False), ("move", "Qxf7+", False),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]

    def test_a_number_the_book_skipped_does_not_send_the_line_to_the_game(self):
        # "22.♘xf3 gxf6 24.♕xf6† ♖g7" — the book's own slip, no 23. On the
        # game's board `♕xf6` happened to be legal and was marked right.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                ("move_number", "2...", False), ("move", "Nf6", False),
                ("move_number", "3.", False), ("move", "Nxe5", False), ("move", "d6", False),
                ("move_number", "5.", False), ("move", "Bc4", False), ("move", "Nxe4", False),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]
        by_id = {m.id: m for m in result.moves}
        bc4 = next(m for m in result.moves if m.san == "Bc4")
        assert by_id[bc4.parent_id].san == "d6"


class TestALineFromTheStartCitedInsideAGame:
    def test_a_first_move_that_only_plays_from_the_start_is_played_from_there(self):
        # Markos page 105: "similar to the Exchange Variation of the Spanish
        # Opening (1.e4 e5 2.♘f3 ♘c6 3.♗b5 a6 4.♗xc6 dxc6 …)" — cited in the
        # middle of another game, and read on its board every move broke.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "d4", True), ("move", "d5", True),
                ("move_number", "2.", True), ("move", "e4", True), ("move", "dxe4", True),
                ("text", "similar to the Spanish", False),
                ("var_open", "(", False),
                ("move_number", "1.", False), ("move", "e4", False), ("move", "e5", False),
                ("move_number", "2.", False), ("move", "Nf3", False), ("move", "Nc6", False),
                ("var_close", ")", False),
                ("move_number", "3.", True), ("move", "Nc3", True),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]
        cited = [m for m in result.moves if m.san in ("e5", "Nc6")]
        assert all(not on_the_main_line(result, m) for m in cited)

    def test_even_where_its_first_moves_play_on_the_game_by_chance(self):
        # Markos page 116, at move 13 of a game: "(… in the Petroff after the
        # moves 1.e4 e5 2.♘f3 ♘f6 3.♘xe5 …)". `1.e4 e5` played on the game,
        # and the line broke at its second move.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "d4", True), ("move", "d5", True),
                ("move_number", "2.", True), ("move", "c4", True), ("move", "e6", True),
                ("move_number", "3.", True), ("move", "Nc3", True),
                ("text", "as in the Spanish after the moves", False),
                ("var_open", "(", False),
                ("move_number", "1.", False), ("move", "e4", False), ("move", "e5", False),
                ("move_number", "2.", False), ("move", "Nf3", False), ("move", "Nc6", False),
                ("move_number", "3.", False), ("move", "Bb5", False),
                ("var_close", ")", False),
                ("move_number", "3...", True), ("move", "Nf6", True),
            ),
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]

    def test_and_in_a_game_the_book_opened_on_a_board(self):
        # Markos page 186, a game seeded in mid-score: "to 6.f4 it would be
        # […] for example, 1.e4 e5 2.♘f3 ♘c6" names a ply before the game's
        # first, and still plays from where every game starts.
        board = chess.Board("r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R2QK2R w KQ - 0 1")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        result = parse_tokens(
            [tok("diagram", rows)] + weighed(
                ("move_number", "9.", True), ("move", "O-O", True), ("move", "b6", True),
                ("text", "but to", False),
                ("move_number", "10.", False), ("move", "a3", False),
                ("text", "it would be like, for example,", False),
                ("move_number", "1.", False), ("move", "e4", False), ("move", "e5", False),
                ("move_number", "2.", False), ("move", "Nf3", False), ("move", "Nc6", False),
            ),
            diagram_table=table,
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]

class TestAGameHeaderIsFoundInTime:
    def test_a_run_of_capitalised_names_does_not_hang_the_book(self):
        # Grivas pages 1-65 never finished: the header pattern tried every
        # way to split each name, and four names in a row took ten seconds.
        import time

        from rce_pipeline.parse import _ends_in_a_game_header

        text = " ".join(["Karpov"] * 8) + " - " + " ".join(["Kasparov"] * 8) + " played on"
        started = time.monotonic()
        assert not _ends_in_a_game_header(text)
        assert time.monotonic() - started < 1.0
        assert _ends_in_a_game_header("Dominik Csiba - Jan Markos, Banska Stiavnica 2011")


class TestAGameTheBookComesBackTo:
    def test_a_board_whose_game_never_starts_does_not_take_the_resumed_score(self):
        # Markos page 111-112: Velicka - Markos stops at `28...e6?`, the book
        # shows "Ostenstad - Hracek, Plovdiv 2010" on a board and plays no move
        # of it, then "Let's return now to my game. After 28...e6? the
        # conclusion was: 29.f4". The board took `28...` and every move broke.
        other = chess.Board("r2q1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R2QK2R w KQ - 0 1")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := other.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True),
                ("text", "My inspiration was a game by a colleague. Ostenstad - Hracek, Plovdiv 2010", False),
            ) + [dataclasses.replace(tok("diagram", rows), to_move="w")] + weighed(
                ("text", "He succeeded in drawing the game. Let's return now to my game. After", False),
                ("move_number", "2...", False), ("move", "Nc6", False),
                ("text", "the conclusion was:", False),
                ("move_number", "3.", True), ("move", "Bb5", True), ("move", "a6", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        game = [m for m in result.moves if m.san in ("Nc6", "Bb5", "a6")]
        assert [m.status for m in game] == ["ok", "ok", "ok"], [
            (m.san, m.status) for m in result.moves
        ]

    def test_nor_when_the_book_comes_back_citing_the_move_the_game_played(self):
        # The page itself: `28...e6?` was the game's, in bold, before the
        # board; "After 28...e6? the conclusion was: 29.f4" cites it again.
        other = chess.Board("r2q1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R2QK2R w KQ - 0 1")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := other.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                ("text", "My inspiration was a game by a colleague. Ostenstad - Hracek, Plovdiv 2010", False),
            ) + [dataclasses.replace(tok("diagram", rows), to_move="w")] + weighed(
                ("text", "He succeeded in drawing the game. Let's return now to my game. After", False),
                ("move_number", "2...", False), ("move", "Nc6", False),
                ("text", "the conclusion was:", False),
                ("move_number", "3.", True), ("move", "Bb5", True), ("move", "a6", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]


class TestAnAlternativeFromBeforeTheBoard:
    def test_a_line_from_a_position_never_printed_is_not_played(self):
        # Markos page 128, the game seeded at White's 19th: "Black's last move
        # was 18...e6. Of course, instead of this move he could have tried to
        # close the centre by playing 18...e5. Still, that would have allowed
        # White to play 19.f5". The board before 18...e6 was never printed:
        # `18...e5` was played by White's e-pawn, and `19.f5` on the game.
        board = chess.Board()
        board.push_san("e4")
        board.push_san("e6")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows), to_move="w")
        result = parse_tokens(
            [diagram] + weighed(
                ("text", "Black's last move was", False),
                ("move_number", "18...", False), ("move", "e6", False),
                ("text", "Instead he could have tried", False),
                ("move_number", "18...", False), ("move", "e5", False),
                ("text", ". Still, that would have allowed White to play", False),
                ("move_number", "19.", False), ("move", "f4", False),
                ("text", "with a strong attack.", False),
                ("move_number", "19.", True), ("move", "Nf3", True),
                ("move_number", "19...", True), ("move", "d5", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert (by_san["e5"].status, by_san["f4"].status) == ("broken", "broken")
        assert (by_san["Nf3"].status, by_san["d5"].status) == ("ok", "ok")

    def test_a_number_a_move_off_still_finds_the_position_the_game_played(self):
        # Markos page 132, the game at 10...♔f8: "Taking the knight is wrong:
        # 11...exf6 12.exf6†" — the book's `11...` for `10...`. No board of
        # Black's 11th exists, and the game's own 10th is where it plays.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True), ("move", "Nc6", True),
                ("text", "Developing the other knight is wrong:", False),
                ("move_number", "3...", False), ("move", "Nf6", False),
            ),
            weighted=True,
        )

        nf6 = next(m for m in result.moves if m.san == "Nf6")
        assert nf6.status == "ok"
        assert {m.id: m for m in result.moves}[nf6.parent_id].san == "Nf3"


class TestTheSideToMoveOfAnExportedDiagram:
    def test_a_board_whose_side_nothing_says_is_exported_as_unknown(self):
        # The reader shows whose move it is beside the board, and must not
        # claim White's for a board where nothing said so.
        board = chess.Board()
        board.push_san("e4")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows), bbox=BBox(50, 400, 200, 200))
        result = parse_tokens([diagram, tok("text", "A study of the centre.")], diagram_table=table)

        (exported,) = result.to_json()["diagrams"]
        assert exported["to_move_known"] is False

    def test_a_board_the_book_marks_is_exported_with_its_side(self):
        board = chess.Board()
        board.push_san("e4")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(
            tok("diagram", rows), bbox=BBox(50, 400, 200, 200), to_move="b"
        )
        result = parse_tokens([diagram, tok("text", "A study of the centre.")], diagram_table=table)

        (exported,) = result.to_json()["diagrams"]
        assert exported["fen"].split()[1] == "b"
        assert "to_move_known" not in exported


class TestTheAnalysisNumberUnderABoard:
    def test_a_plain_number_seeds_the_game_and_its_moves_stay_analysis(self):
        # Markos page 167: under the board of Markos - Macak, "let's start
        # with 19.c6. Black has to answer 19...♗xc6" — analysis, and the
        # first number under the board. It seeded the game and its moves were
        # played as the game's, so `19.♗b5!` and every aside after it broke.
        board = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6"):
            board.push_san(san)
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows), to_move="w")
        result = parse_tokens(
            [diagram] + weighed(
                ("text", "Let's start with", False),
                ("move_number", "3.", False), ("move", "d4", False),
                ("text", ". Black has to answer", False),
                ("move_number", "3...", False), ("move", "exd4", False),
                ("text", "Then it was easy to find the right move:", False),
                ("move_number", "3.", True), ("move", "Bb5", True), ("move", "a6", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert all(m.status == "ok" for m in result.moves), [
            (m.san, m.status) for m in result.moves
        ]
        assert on_the_main_line(result, by_san["a6"])
        assert not on_the_main_line(result, by_san["exd4"])

    def test_an_alternative_inside_that_analysis_branches_from_it(self):
        # The same page: "a) 20.♕c2 ♗d5 21.♕xc7 […] 22.♕xd6 ♘b8 23.♕c7 ♘c6
        # […] Capturing the other pawn with 22.♕xa7" — Black's 22nd is one
        # only the analysis reached, and it was played after 23...♘c6.
        board = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6"):
            board.push_san(san)
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows), to_move="w")
        result = parse_tokens(
            [diagram] + weighed(
                ("text", "Let's start with", False),
                ("move_number", "3.", False), ("move", "d4", False),
                ("text", ". Black has to answer", False),
                ("move_number", "3...", False), ("move", "exd4", False),
                ("move_number", "4.", False), ("move", "Nxd4", False), ("move", "Nf6", False),
                ("text", "Capturing the other way with", False),
                ("move_number", "4.", False), ("move", "Qxd4", False),
                ("text", "looks frightening.", False),
                ("move_number", "4.", True), ("move", "Bb5", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        by_id = {m.id: m for m in result.moves}
        qxd4 = next(m for m in result.moves if m.san == "Qxd4")
        assert qxd4.status == "ok"
        assert by_id[qxd4.parent_id].san == "exd4"


class TestTheSideToMovePrintedBesideTheBoard:
    def test_a_black_triangle_beats_the_number_the_prose_cites(self):
        # Markos page 48: the board of Morovic Fernandez - Adams carries a ▼,
        # and the first number under it is the prose's "White's last move,
        # 14.♗g2-h3". Seeded for White, the game's own `14...b5! 15.♘d2` broke.
        board = chess.Board()
        board.push_san("e4")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows), to_move="b")
        result = parse_tokens(
            [diagram] + weighed(
                ("text", "White's last move,", False),
                ("move_number", "14.", False), ("move", "Bh3", False),
                ("text", "signals an expansion.", False),
                ("move_number", "14...", True), ("move", "b5", True),
                ("move_number", "15.", True), ("move", "Nf3", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        game = [m for m in result.moves if m.san in ("b5", "Nf3")]
        assert [m.status for m in game] == ["ok", "ok"]

    def test_the_triangle_is_believed_over_a_citation_the_other_side_can_play(self):
        # The move the prose cites is White's own last move, and White could
        # play one like it: that says nothing against the ▼.
        board = chess.Board()
        board.push_san("e4")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows), to_move="b")
        result = parse_tokens(
            [diagram] + weighed(
                ("text", "White's plan is", False),
                ("move_number", "14.", False), ("move", "Nc3", False),
                ("text", "and then more.", False),
                ("move_number", "14...", True), ("move", "b5", True),
                ("move_number", "15.", True), ("move", "Nf3", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        game = [m for m in result.moves if m.san in ("b5", "Nf3")]
        assert [m.status for m in game] == ["ok", "ok"]

    def test_a_first_move_from_the_start_under_a_marked_board_starts_there(self):
        # Markos page 241: a board marked ▼, then "After 1.e4, the most often
        # played line is the Najdorf". The mark turned `1.` into Black's
        # first on the board, and `1.e4` broke.
        board = chess.Board("2q5/Qp2ppk1/6pp/2P5/4P3/2P2P2/P4P1P/3K4 b - - 0 1")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows), to_move="b")
        result = parse_tokens(
            [diagram] + weighed(
                ("text", "After", False),
                ("move_number", "1.", False), ("move", "e4", False),
                ("text", ", the most often played line is the Najdorf.", False),
            ),
            diagram_table=table,
            weighted=True,
        )

        assert [m.status for m in result.moves] == ["ok"]

    def test_a_number_citing_the_last_move_counts_the_move_after_it(self):
        # Markos page 128: △, then "Black's last move was 18...e6", then the
        # game's `19.♔h1!?`. The board is White's nineteenth, not eighteenth,
        # or every number of the game disagrees with it and the game drifts.
        board = chess.Board()
        board.push_san("e4")
        board.push_san("e6")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        diagram = dataclasses.replace(tok("diagram", rows), to_move="w")
        result = parse_tokens(
            [diagram] + weighed(
                ("text", "Black's last move was", False),
                ("move_number", "18...", False), ("move", "e6", False),
                ("text", "Of course.", False),
                ("move_number", "19.", True), ("move", "Nf3", True),
                ("move_number", "19...", True), ("move", "Nc6", True),
            ),
            diagram_table=table,
            weighted=True,
        )

        game = [m for m in result.moves if m.san in ("Nf3", "Nc6")]
        assert [m.status for m in game] == ["ok", "ok"]
        assert result.break_diagnosis()["drifted"] == 0


class TestANumberAScanWeldedALostMoveOnto:
    """"18.exd5 f5 19.d6" comes off the page as `exd5` and then **519**."""

    def test_the_digits_come_off_where_the_game_is_waiting(self):
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                # "3.Bb5 a6 4.Ba4" with `a6` destroyed and its rank welded on.
                ("move_number", "3."), ("move", "Bb5"),
                ("move_number", "64."), ("move", "Ba4"),
            )
        )

        # One game, not two: an absurd number opens one where the book has
        # none, and every move under it is then unscored.
        assert len(result.games) == 1
        assert [m.san for m in result.moves] == ["e4", "e5", "Nf3", "Nc6", "Bb5", "Ba4"]

    def test_the_helper_takes_the_digits_the_count_names(self):
        board = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6", "Bb5"):
            board.push_san(san)

        # The game awaits Black's third; "64." is White's fourth with the rank
        # of the black move it destroyed welded on — and it kept that rank.
        assert _number_stripped_of_a_lost_move(64, False, board) == (4, 6)
        # And a page number names nothing the count is waiting for.
        assert _number_stripped_of_a_lost_move(170, False, board) == (None, None)

    def test_a_page_number_in_the_score_is_left_alone(self):
        """Tactics prints 170 to 181 where the score can reach them.

        Stripped to 70 and 81 those would move a line that was right, so the
        digits only come off where what is left is the ply the game awaits.
        """
        result = parse_tokens(
            moves(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("move_number", "170."), ("move", "Nf3"),
            )
        )

        assert [m.san for m in result.moves] == ["e4", "e5", "Nf3"]
        assert result.moves[-1].ply == 3


class TestAMarkTheInkMissed:
    """The weight is a measurement, and a measurement misses.

    On a scan there is no weight in the text layer and `weight.mark` reads it
    off the ink: eroded twice, a bold stem keeps its core and a hairline does
    not. The marks are good and they are not perfect — a number the OCR half
    ate, the dots of `17...`, a box running over its neighbour. Before this,
    one number of the score coming out plain cost the rest of the page: the
    score went into an aside and only a bold number could bring it back.
    """

    def test_the_number_that_resumes_the_score_takes_the_aside_back(self):
        # `2.` came out plain, so `Nf3 Nc6` was read as analysis beside a game
        # standing still at its first move. `3.`, in the score's own weight,
        # names White's third — a ply the game has not reached and the aside
        # has, exactly.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", False), ("move", "Nf3", False), ("move", "Nc6", False),
                ("move_number", "3.", True), ("move", "Bb5", True), ("move", "a6", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert all(on_the_main_line(result, by_san[san]) for san in
                   ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6"))
        assert all(m.status == "ok" for m in result.moves)

    def test_a_citation_of_analysis_still_to_come_is_not_taken_back(self):
        # The aside ends exactly where the score's own number picks up, and it
        # is still not the score: its number named White's fifth while the game
        # was waiting for White's second, so it is analysis of a move still to
        # come. Where such a line ends says nothing about the game.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "5.", False), ("move", "Nc3", False), ("move", "Nf6", False),
                ("move_number", "3.", True), ("move", "Bc4", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert not on_the_main_line(result, by_san["Nc3"])
        # Nothing brought the game up to White's third, so `Bc4` is played
        # where the game stood and the book's own numbering says it is adrift.
        assert by_san["Bc4"].parent_id == by_san["e5"].id

    def test_the_analysis_the_weight_diverts_is_still_diverted(self):
        # The rule only ever fires where the game is already behind the book.
        # Here it is not: the score resumes at the ply it was waiting for, so
        # the citation printed there stays a citation.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", True), ("move", "Nf3", True),
                ("move_number", "2...", False), ("move", "d6", False),
                ("move_number", "2...", True), ("move", "Nc6", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert on_the_main_line(result, by_san["Nc6"])
        assert not on_the_main_line(result, by_san["d6"])

    def test_the_aside_whose_number_stood_nearest_the_game_is_the_one_taken(self):
        # `2.` plain (the score, its mark missed) and `5.` plain (a citation of
        # what is coming) both end where `3.` picks up. The number that named
        # the ply the game was waiting for is the score.
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "5.", False), ("move", "Nc3", False), ("move", "Nf6", False),
                ("move_number", "2.", False), ("move", "Nf3", False), ("move", "Nc6", False),
                ("move_number", "3.", True), ("move", "Bb5", True),
            ),
            weighted=True,
        )

        by_san = {m.san: m for m in result.moves}
        assert on_the_main_line(result, by_san["Nf3"])
        assert not on_the_main_line(result, by_san["Nc3"])
        assert by_san["Bb5"].parent_id == by_san["Nc6"].id

    def test_an_aside_taken_back_carries_its_positions_to_the_diagrams(self):
        """A diagram below is read against the line, so the line has to be whole."""
        result = parse_tokens(
            weighed(
                ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
                ("move_number", "2.", False), ("move", "Nf3", False), ("move", "Nc6", False),
                ("move_number", "3.", True), ("move", "Bb5", True),
            ),
            weighted=True,
        )

        board = chess.Board()
        for san in ("e4", "e5", "Nf3", "Nc6", "Bb5"):
            board.push_san(san)
        assert result.main_lines[result.games[0].id][-1] == board.board_fen()


class TestTwoAlternativeVariationsAtOneNumber:
    """A book cites two lines in one breath, both branching at the same move.

    Laurent, reading Boussole page 65: *"7 ♗xf6 ♕xf6 8 ♘d5 ♕d8 et 7 ♗h4 g5
    8 ♗g3 ♗g4 sont deux variantes alternatives"*. The second one's number is
    one the **first has passed** and the game has not reached, so neither the
    game's record nor the position answers it, and it was played as the
    continuation of the first — where its own first move is illegal.

    The aside keeps the same record of itself the game keeps, and a move
    already broken is offered it.
    """

    def line(self, *pairs: tuple[str, str]) -> list[Token]:
        return [tok(kind, text) for kind, text in pairs]

    def tokens(self, second: str) -> list[Token]:
        # 1 e4 e5 2 Nf3 Nc6, and beside it the gambit: 2 d4 exd4 3 c3 dxc3
        # 4 Nxc3, four plies further on than the game itself.
        return self.line(
            ("move_number", "1"), ("move", "e4"), ("move", "e5"),
            ("move_number", "2"), ("move", "Nf3"), ("move", "Nc6"),
            ("text", "Or the gambit:"),
            ("move_number", "2"), ("move", "d4"), ("move", "exd4"),
            ("move_number", "3"), ("move", "c3"), ("move", "dxc3"),
            ("move_number", "4"), ("move", "Nxc3"),
            ("text", "and equally:"),
            ("move_number", "4"), ("move", second),
        )

    def test_the_second_alternative_branches_where_the_first_did(self):
        # `4 Bc4` on the board the aside reached is White moving with Black to
        # play. On the board the aside printed at its own fourth move it is
        # the alternative the book meant.
        last = parse_tokens(self.tokens("Bc4")).moves[-1]

        assert (last.san, last.status) == ("Bc4", "ok")

    def test_a_move_legal_where_it_stands_is_left_alone(self):
        # Only a move already dead is offered another board: the aside is
        # waiting for Black's fourth and `Bc5` is Black's fourth.
        last = parse_tokens(self.tokens("Bc5")).moves[-1]

        assert (last.san, last.status) == ("Bc5", "ok")
        assert last.ply == 8


class TestTheGameGoesOnPastItsResult:
    """A book plays out the moves the loser resigned in the face of.

    Grivas page 17 ends `27 ♗xe7 1-0` and then prints "Black resigned due to
    27...♔xe7 28 ♕f6+ ♔d7 29 ♕xc6+". Laurent: *"en dépit du résultat 1-0 plus
    haut, tu peux interpréter cette ligne, car il s'agit bien de la ligne
    principale comme si elle avait vraiment été jouée avant l'abandon"*.

    A result closed the game and emptied the stack, so those half-moves opened
    a game of their own — one starting at move 27 from a position the book
    never printed, every move of it broken and none of it scored. What says
    otherwise is the number: it carries on the numbering of the game that just
    ended.
    """

    def game(self, *after: tuple[str, str]) -> list[Token]:
        played = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        tokens.append(tok("result", "1-0"))
        tokens += [tok(kind, text) for kind, text in after]
        return tokens

    def test_the_line_after_the_result_is_the_game_that_just_ended(self):
        result = parse_tokens(self.game(
            ("text", "Black resigned in view of"),
            ("move_number", "4..."), ("move", "dxc6"),
            ("move_number", "5"), ("move", "Nxe5"),
        ))

        assert len(result.games) == 1
        assert [m.san for m in result.moves[-2:]] == ["dxc6", "Nxe5"]
        assert [m.status for m in result.moves[-2:]] == ["ok", "ok"]

    def test_a_number_that_starts_over_starts_a_game(self):
        result = parse_tokens(self.game(
            ("move_number", "1"), ("move", "d4"), ("move", "d5"),
        ))

        assert len(result.games) == 2
        assert result.games[1].position_known

    def test_a_number_neither_continuing_nor_starting_still_opens_nothing_known(self):
        # Analysis quoted after a result and belonging to no game the book
        # printed. It is read and kept for its box; none of it is scored.
        result = parse_tokens(self.game(
            ("move_number", "18..."), ("move", "Rf6"),
        ))

        assert len(result.games) == 2
        assert not result.games[1].position_known


class TestAnAsideThatCaughtTheGameUp:
    """A one-move citation, and then the game's own number waiting behind it.

    Boussole page 65: "13.a3! ... et les Blancs menacent 14.b4. 13...♗b6
    14.♘h4". The citation branches at the game's own position and plays one
    ply, so the aside and the game are both waiting for Black's thirteenth,
    and the aside took it — and with it every move to the end of the page,
    thirty of them, read beside the game instead of as the game.

    What separates them is the aside's own numbering, which never goes
    backwards: the book cited White's fourteenth and is now printing Black's
    thirteenth.
    """

    def tokens(self) -> list[Token]:
        played = ["e4", "e5", "Nf3", "Nc6", "Bb5"]
        out: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                out.append(tok("move_number", str(index // 2 + 1)))
            out.append(tok("move", san))
        return out + [
            tok("text", "White threatens"),
            tok("move_number", "4."), tok("move", "Bc4"),
            tok("move_number", "3..."), tok("move", "a6"),
            tok("move_number", "4."), tok("move", "Ba4"),
        ]

    def test_the_game_takes_the_number_back(self):
        result = parse_tokens(self.tokens())
        main = [m for m in result.moves if m.variation_index == 0]

        assert [m.san for m in main] == [
            "e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4",
        ]
        assert [m.san for m in result.moves if m.variation_index] == ["Bc4"]

    def test_the_citation_is_still_beside_the_game(self):
        cited = next(m for m in parse_tokens(self.tokens()).moves if m.san == "Bc4")

        assert (cited.variation_index, cited.status) == (1, "ok")


class TestAnAsideThatLostItsFirstMove:
    """A citation whose opening move never read, and its own next number.

    SuperAttaquant page 198 prints "...auraient mieux fait de penser a donner
    leur Dame, par 21...♕b7 22.c6 ♖xa1!" — a citation of a move the game has
    already gone past. The queen's symbol is destroyed in the scan, so `♕b7`
    arrives as a bare `b7`, is illegal for Black there and is never played.
    The aside is then standing exactly where its own number left it, and
    `22.`, the citation's own second number, disagrees with that board for no
    other reason.

    Read as the game resuming, the whole citation is played as the score and
    the game's own `22.♖xa8 ♕c6 23.♖fa1` is diverted beside it; 54 moves died
    under the inversion. The aside carrying on one ply from its own number is
    what says otherwise.
    """

    def tokens(self) -> list[Token]:
        played = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]
        out: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                out.append(tok("move_number", str(index // 2 + 1)))
            out.append(tok("move", san))
        return out + [
            tok("text", "Black would have done better with"),
            # Black's third, a ply the game has passed, and illegal besides:
            # the pawn it names is already there. The aside reads nothing and
            # stays on the ply its own number gave it.
            tok("move_number", "3..."), tok("move", "b7"),
            tok("move_number", "4."), tok("move", "Bc4"),
            # And here the game really does resume.
            tok("move_number", "4."), tok("move", "Ba4"),
        ]

    def test_the_citation_does_not_take_the_score(self):
        result = parse_tokens(self.tokens())
        main = [m for m in result.moves if m.variation_index == 0]

        assert [m.san for m in main] == [
            "e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4",
        ]

    def test_the_citation_stays_beside_the_game(self):
        result = parse_tokens(self.tokens())
        cited = [m for m in result.moves if m.san in ("b7", "Bc4")]

        assert [m.variation_index for m in cited] == [1, 1]


class TestAFileTheScannerReadAsADigit:
    """`♗g5+` off the scan as `♗25+`: no notation writes a piece and two digits.

    The rank survives and the piece survives, and the file is the wreck. This
    scan wrecks it differently every time — `♘d5` as `♘45`, `♗f4` as `♗41` —
    so nothing on the page puts it back and the board is asked instead.
    """

    def opening(self, printed: str) -> list[Token]:
        # 1 e4 e5 2 Nf3 Nc6 3 Bb5 a6, and then whatever the scan made of
        # White's fourth.
        played = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", str(index // 2 + 1)))
            tokens.append(tok("move", san))
        return tokens + [tok("move_number", "4."), tok("move", printed)]

    def test_the_board_names_the_file_when_only_one_move_fits(self):
        # Only the bishop on b5 reaches rank 3, and it reaches d3.
        last = parse_tokens(self.opening("B13")).moves[-1]

        assert (last.san, last.status) == ("Bd3", "uncertain")

    def test_two_readings_are_left_for_the_reader(self):
        # The rook has both g1 and f1, and a wrong move here would be played
        # at half confidence on a position the book never printed.
        result = parse_tokens(self.opening("R71"))

        assert result.moves[-1].status == "broken"
        assert result.ambiguities[-1]["candidates"] == ["Rg1", "Rf1"]

    def test_the_check_mark_the_page_printed_has_to_hold(self):
        # `Bd3` gives no check, so a token that printed one is not this move.
        last = parse_tokens(self.opening("B13+")).moves[-1]

        assert last.status == "broken"

    def test_a_file_that_left_no_character_is_read_the_same_way(self):
        # `28.♔g1` off the scan as `28.♔1`: the digit standing for the file is
        # gone as well, and the piece and the rank are read exactly as above.
        last = parse_tokens(self.opening("B3")).moves[-1]

        assert (last.san, last.status) == ("Bd3", "uncertain")


class TestALostMoveTheProseSeparatesFromItsLine:
    """The move a number announced, with the book's comment standing after it.

    SuperAttaquant page 201 prints "20...♗g7", then a paragraph — "Short
    préfère rendre la pièce plutôt que d'exiler son Cavalier en h5" — and only
    then the score again, "21.d4! ♕b8 22.dxc5 bxc5". The scan leaves `20...2.27`
    of the move, so all that is left is its rank, and the line that names it is
    past the prose. Its second move is damaged too: `♕b8` arrives as `b8` with
    the queen's wreck beside it. Without the move the game's reply is played as
    the move that never arrived, on the wrong side, and all 39 of its moves die.

    The prose is crossed only where the number after it is the very next ply:
    then the run is still one line, by the book's own count.
    """

    def tokens(self, resumes: str = "6.") -> list[Token]:
        played = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O"]
        out: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                out.append(tok("move_number", f"{index // 2 + 1}."))
            out.append(tok("move", san))
        return out + [
            # `5...♗e7`, of which the scan kept the rank.
            dataclasses.replace(tok("move_number", "5..."), lost_move="2.27"),
            tok("text", "Black keeps his knight rather than put it on"),
            tok("move", "h5"),
            tok("text", "and White builds his centre."),
            tok("move_number", resumes), tok("move", "e1", lost_symbol="H", lost_piece="R"),
            tok("move", "b5"),
            tok("move_number", "7."), tok("move", "Bb3"), tok("move", "d6"),
            # Only the bishop leaving f8 lets Black castle: the line names it.
            tok("move_number", "8."), tok("move", "c3"), tok("move", "O-O"),
        ]

    def test_the_move_is_put_back_from_the_line_after_the_prose(self):
        result = parse_tokens(self.tokens())
        main = [m for m in result.moves if m.variation_index == 0]

        assert [m.san for m in main][9:] == ["Be7", "Re1", "b5", "Bb3", "d6", "c3", "O-O"]
        assert all(m.status != "broken" for m in main)

    def test_nothing_is_put_back_where_the_number_is_not_the_next_ply(self):
        result = parse_tokens(self.tokens(resumes="7."))

        assert "Be7" not in sans(result)


class TestAFiveReadAsASmallS:
    """`C x es` — Pachman's scan reads `5` as `s` as well as `S`."""

    def test_it_is_the_look_alike_it_is(self):
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "e4"), ("move", "e5"),
            ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
            ("move_number", "3."), ("move", "Nxes"),
        ))

        assert (result.moves[-1].san, result.moves[-1].status) == ("Nxe5", "uncertain")


class TestTwoAlternativesInOneBracket:
    """Pachman, Théorie élémentaire 1: "5. Fg5 Fe7 (le plus solide, mais vont
    toutefois également 5. ... Fb4 et 5. .. h6 6. Fh4 g5 ?)" — two answers to
    the same move inside one bracket. The second was read as the first
    carrying on, with White to play, and the bracket died on it."""

    def test_the_second_is_played_where_the_first_began(self):
        played = ["d4", "Nf6", "c4", "e6", "Nf3", "b6", "Nc3", "Bb7", "Bg5", "Be7"]
        tokens: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                tokens.append(tok("move_number", f"{index // 2 + 1}."))
            tokens.append(tok("move", san))
        tokens += [
            tok("var_open", "("),
            tok("move_number", "5..."), tok("move", "Bb4"),
            tok("move_number", "5..."), tok("move", "h6"),
            tok("move_number", "6."), tok("move", "Bh4"), tok("move", "g5"),
            tok("var_close", ")"),
            tok("move_number", "6."), tok("move", "e3"),
        ]
        result = parse_tokens(tokens)

        assert all(m.status == "ok" for m in result.moves)
        h6 = next(m for m in result.moves if m.san == "h6")
        # Played after 5.Bg5, not after 5...Bb4: the bishop is still on f8.
        assert chess.Board(h6.fen).piece_at(chess.F8) == chess.Piece(chess.BISHOP, chess.BLACK)
        assert result.moves[-1].san == "e3" and result.moves[-1].variation_index == 0

    def test_also_where_the_book_sets_its_score_bold(self):
        # Sakaev page 32: "(19.♘b3 comes under attack after 19...a5 […]
        # Another possible development […]: 19.♖d1 ♖c8" — played after
        # 19...a5, the knight stayed on b3 and the line died on page 33.
        tokens = weighed(
            ("move_number", "1.", True), ("move", "e4", True), ("move", "e5", True),
            ("move_number", "2.", True), ("move", "Nf3", True),
            ("var_open", "(", False),
            ("move_number", "2.", False), ("move", "Nc3", False),
            ("move_number", "2...", False), ("move", "Nf6", False),
            ("text", "Another possible development is", False),
            ("move_number", "2.", False), ("move", "Bc4", False), ("move", "Bc5", False),
            ("var_close", ")", False),
            ("move_number", "2...", True), ("move", "Nc6", True),
        )
        result = parse_tokens(tokens, weighted=True)

        assert all(m.status == "ok" for m in result.moves)
        bc4 = next(m for m in result.moves if m.san == "Bc4")
        # Played after 1...e5, not after 2.Nc3 Nf6: the knight is still on b1.
        assert chess.Board(bc4.fen).piece_at(chess.B1) == chess.Piece(chess.KNIGHT, chess.WHITE)


class TestAMovePairTheNextNumberNumbers:
    """Sakaev page 87: "23...♘b3 24.♖xb3 Also winning is d5 ♘xc5 25.dxe6" —
    the `24.` is left implicit, and the `25.` behind the pair says so."""

    def test_the_pair_is_the_move_before_the_number(self):
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "e4"), ("move", "e5"),
            ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
            ("move_number", "3."), ("move", "Bb5"),
            ("text", "Also good is"),
            ("move", "Bc4"), ("move", "Bc5"),
            ("move_number", "4."), ("move", "c3"),
        ))

        assert [(m.san, m.status) for m in result.moves][-3:] == [
            ("Bc4", "ok"), ("Bc5", "ok"), ("c3", "ok"),
        ]
        bc4 = next(m for m in result.moves if m.san == "Bc4")
        assert bc4.parent_id == next(m for m in result.moves if m.san == "Nc6").id


class TestAGameFromADiagramCitesItsFirstMoveAgain:
    """Sakaev page 297, Yates-Marshall from the board: "1.♕c2 In the game,
    there followed 1.♔c4?? b1♕ 2.♕xb1+ ♔xb1" — the `1.` is the other answer
    to the same board, not a new game from the initial position."""

    def test_the_second_first_move_is_played_on_the_board(self):
        board = chess.Board("8/8/8/8/p2K4/3Q4/kp3P2/8 w - - 0 1")
        rows = "/".join(
            "".join(
                piece.symbol() if (piece := board.piece_at(chess.square(file, rank))) else "."
                for file in range(8)
            )
            for rank in range(7, -1, -1)
        )
        table = {char: char for char in rows if char != "/"}
        result = parse_tokens(
            [tok("diagram", rows)] + moves(
                ("move_number", "1."), ("move", "Qc2"),
                ("text", "In the game, there followed"),
                ("move_number", "1."), ("move", "Kc4"), ("move", "b1=Q"),
                ("move_number", "2."), ("move", "Qxb1+"), ("move", "Kxb1"),
            ),
            diagram_table=table,
        )

        assert [(m.san, m.status) for m in result.moves] == [
            ("Qc2", "ok"), ("Kc4", "ok"), ("b1=Q", "ok"), ("Qxb1+", "ok"), ("Kxb1", "ok"),
        ]
        assert len({m.game_id for m in result.moves}) == 1


class TestABracketWhoseNumberNamesNoPosition:
    """Sakaev page 239: "12.e4 dxe4 (12.♕xe4+ ♔f8 …) 13.♘xe4" — `13.` meant.
    Neither the position before `dxe4` nor any other awaits a white twelfth,
    and the queen only takes on e4 once the pawn is there."""

    def test_the_first_move_says_where_it_plays(self):
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "e4"), ("move", "d5"),
            ("move_number", "2."), ("move", "Qe2"), ("move", "dxe4"),
            ("var_open", "("),
            ("move_number", "2."), ("move", "Qxe4"), ("move", "Nf6"),
            ("var_close", ")"),
            ("move_number", "3."), ("move", "Nc3"),
        ))

        assert all(m.status == "ok" for m in result.moves)
        by_san = {m.san: m for m in result.moves}
        # Both answer `dxe4`: the queen's capture beside the knight's move.
        assert by_san["Qxe4"].parent_id == by_san["dxe4"].id == by_san["Nc3"].parent_id


class TestAPieceWhoseSquareWasLost:
    """`2.NO` — the knight printed, its square read as `O`: the board and the
    score after it name the move, as they name a move a number destroyed."""

    def test_the_line_names_the_square(self):
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "e4"), ("move", "e5"),
            ("move_number", "2."), ("move", "N?"), ("move", "Nc6"),
            ("move_number", "3."), ("move", "Bb5"), ("move", "a6"),
            ("move_number", "4."), ("move", "Ba4"), ("move", "Nf6"),
            # Only a knight on f3 takes on e5.
            ("move_number", "5."), ("move", "Nxe5"),
        ))

        assert [(m.san, m.status) for m in result.moves][2:4] == [
            ("Nf3", "uncertain"), ("Nc6", "ok"),
        ]

    def test_a_move_the_line_only_finds_ambiguous_is_not_ruled_out(self):
        # Svidler-Jakovenko, Silman p612: `2.NB` for `2.Nf3`, and `9.Nbd2`
        # read `Nhd2`. With the knight on f3 two knights reach d2, so the line
        # stops there; with it on h3 only one does, and the line runs on — so
        # the wrong knight carried it further. Two pieces reaching a square
        # says nothing against either: the right move is still standing.
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "d4"), ("move", "d5"),
            ("move_number", "2."), ("move", "N?"), ("move", "Nf6"),
            ("move_number", "3."), ("move", "e3"), ("move", "e6"),
            ("move_number", "4."), ("move", "Nhd2"), ("move", "c5"),
            ("move_number", "5."), ("move", "c3"),
        ))

        assert "Nh3" not in sans(result)

    def test_the_line_is_followed_until_it_tells_the_knights_apart(self):
        # `2.Nf3` and `2.Na3` both play the next six moves; only the twelfth,
        # `7.Nxe5`, needs the knight on f3. Silman's `2.NO` is `Nf3` against
        # `Nh3` over ten plies as often as not.
        result = parse_tokens(moves(
            ("move_number", "1."), ("move", "e4"), ("move", "e5"),
            ("move_number", "2."), ("move", "N?"), ("move", "Nc6"),
            ("move_number", "3."), ("move", "Bc4"), ("move", "Bc5"),
            ("move_number", "4."), ("move", "c3"), ("move", "Nf6"),
            ("move_number", "5."), ("move", "d3"), ("move", "d6"),
            ("move_number", "6."), ("move", "O-O"), ("move", "O-O"),
            ("move_number", "7."), ("move", "h3"), ("move", "a6"),
            ("move_number", "8."), ("move", "Nxe5"),
        ))

        assert (result.moves[2].san, result.moves[2].status) == ("Nf3", "uncertain")


class TestALostMoveTwoMovesExplainAlike:
    """A destroyed move the line cannot name, on a line that does not care.

    Plaskett-Short, SuperAttaquant page 201: `20...♗g7` comes off the scan as
    `20...2.27`, and `♗e7` carries "21.d4 ♕b8 22.dxc5 bxc5 23.exf6 ♗xf6"
    exactly as far — the bishop takes on f6 from either square, and from there
    the two games are one. Refusing the move loses all 38 moves of the game;
    putting one back is wrong, if it is wrong, only until the positions meet.

    So one is put back, and every move played on a position that depends on
    which it was is left for the reader to check. Below the meeting the moves
    are on the book's own board whichever the book printed.
    """

    def tokens(self) -> list[Token]:
        played = ["e4", "e6", "d4", "g6", "Nf3", "Nf6", "e5"]
        out: list[Token] = []
        for index, san in enumerate(played):
            if index % 2 == 0:
                out.append(tok("move_number", f"{index // 2 + 1}."))
            out.append(tok("move", san))
        return out + [
            # `4...♗g7` or `4...♗e7`: the scan kept the rank.
            dataclasses.replace(tok("move_number", "4..."), lost_move="2.27"),
            tok("move_number", "5."), tok("move", "exf6"), tok("move", "Bxf6"),
            tok("move_number", "6."), tok("move", "Nc3"), tok("move", "O-O"),
            tok("move_number", "7."), tok("move", "Bd3"), tok("move", "d5"),
        ]

    def test_the_moves_before_the_positions_meet_are_left_to_check(self):
        main = [m for m in parse_tokens(self.tokens()).moves if m.variation_index == 0]

        assert [m.san for m in main][7] in ("Be7", "Bg7")
        assert [(m.san, m.status) for m in main][8:] == [
            ("exf6", "uncertain"), ("Bxf6", "ok"), ("Nc3", "ok"), ("O-O", "ok"),
            ("Bd3", "ok"), ("d5", "ok"),
        ]
        assert main[7].status == "uncertain"
        assert all(m.repair and m.repair["reason"] for m in main[7:9])
