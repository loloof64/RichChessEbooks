"""Tests for the positions a book prints as pictures.

The book of the corpus that needs this sets its diagrams in a font whose
letters nothing here knows in advance, so the tests use an invented one — the
point is that the table is learned, not that it is right.
"""

import chess
import pytest

from rce_pipeline import diagrams
from rce_pipeline.extract import BBox, Char, Page
from rce_pipeline.parse import parse_tokens
from rce_pipeline.tokenize import Token, tokenize_pages

#: An invented diagram font: the letter says the piece, the case says nothing
#: at all, and `.` is an empty square.
FONT = {
    "T": "r", "S": "n", "L": "b", "D": "q", "M": "k", "J": "p",
    "R": "R", "N": "N", "B": "B", "Q": "Q", "K": "K", "I": "P",
    ".": ".",
}
_INVERSE = {piece: char for char, piece in FONT.items()}


def rows_of(board_fen: str) -> tuple[str, ...]:
    """The eight rows this font would print for a position."""
    rows = []
    for rank in board_fen.split("/"):
        squares = "".join("." * int(ch) if ch.isdigit() else ch for ch in rank)
        rows.append("".join(_INVERSE[piece] for piece in squares))
    return tuple(rows)


def fen_after(*moves: str) -> str:
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board.board_fen()


def page_of(text: str) -> Page:
    chars = [
        Char(char=ch, bbox=BBox(72.0 + i, 640.0, 6.0, 10.0), font="Serif", size=10.0)
        for i, ch in enumerate(text)
    ]
    return Page(number=1, width=595.0, height=842.0, text=text, chars=chars)


class TestFinding:
    def test_reads_a_block_of_eight_rows(self):
        rows = rows_of(chess.STARTING_BOARD_FEN)
        page = page_of("A caption.\n" + "\n".join(rows) + "\n1.e4\n")

        found = diagrams.find([page])

        assert [d.rows for d in found] == [rows]

    def test_folds_a_row_the_book_prints_twice(self):
        # One book draws every row over itself; the second copy is the same
        # rank, not the next one.
        rows = rows_of(chess.STARTING_BOARD_FEN)
        doubled = "\n".join(f"{row}\n{row}" for row in rows)
        page = page_of(doubled + "\n")

        assert [d.rows for d in diagrams.find([page])] == [rows]

    def test_ignores_eight_short_lines_of_prose(self):
        page = page_of("\n".join(["opening,", "middle,", "endgame,"] * 3))

        assert diagrams.find([page]) == []


class TestLearning:
    def test_recovers_the_font_from_one_known_position(self):
        rows = rows_of(chess.STARTING_BOARD_FEN)

        table = diagrams.learn([(rows, [chess.STARTING_BOARD_FEN])])

        assert diagrams.decode(rows, table) == chess.STARTING_BOARD_FEN

    def test_a_diagram_read_on_a_drifted_board_does_not_teach(self):
        # The board the parser had reached is wrong here, and it is the only
        # observation that disagrees: the two sound ones outvote it as wholes.
        sound = [
            (rows_of(chess.STARTING_BOARD_FEN), [chess.STARTING_BOARD_FEN]),
            (rows_of(fen_after("e4")), [fen_after("e4")]),
        ]
        drifted = (rows_of(fen_after("e4", "e5")), [fen_after("d4", "d5")])

        table = diagrams.learn(sound + [drifted])

        assert diagrams.decode(rows_of(fen_after("e4", "e5")), table) == fen_after("e4", "e5")

    def test_the_other_case_is_found_through_the_private_use_area(self):
        # A font carrying no Unicode meaning of its own is mapped into U+F0xx,
        # keeping the ASCII layout underneath: the partner of U+F070 is U+F050,
        # exactly as `p` and `P`. Quality Chess's board is printed like that.
        private = tuple(
            "".join(chr(ord(char) + 0xF000) for char in row)
            for row in rows_of(chess.STARTING_BOARD_FEN)
        )

        table = diagrams.learn([(private, [chess.STARTING_BOARD_FEN])])

        assert table[chr(ord("q") + 0xF000)] == "Q"

    def test_learns_the_letter_it_never_saw_from_its_other_case(self):
        # No game reaches a position with a white queen on a dark square, so
        # the book never prints that form beside a board anyone knows.
        table = diagrams.learn([(rows_of(chess.STARTING_BOARD_FEN), [chess.STARTING_BOARD_FEN])])

        assert table["q"] == "Q"
        assert table["m"] == "k"


class TestDecoding:
    def test_refuses_a_diagram_holding_a_character_it_has_not_learned(self):
        table = diagrams.learn([(rows_of(chess.STARTING_BOARD_FEN), [chess.STARTING_BOARD_FEN])])
        rows = rows_of(chess.STARTING_BOARD_FEN)
        damaged = ("?" + rows[0][1:],) + rows[1:]

        assert diagrams.decode(damaged, table) is None

    def test_a_full_fen_takes_its_turn_from_the_number_under_it(self):
        fen = diagrams.initial_fen(fen_after("e4"), number=1, black_to_move=True)

        assert chess.Board(fen).turn == chess.BLACK
        assert chess.Board(fen).fullmove_number == 1

    def test_castling_is_credited_where_the_pieces_have_not_moved(self):
        assert "KQkq" in diagrams.initial_fen(
            chess.STARTING_BOARD_FEN, number=1, black_to_move=False
        )
        moved = fen_after("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "Ke2")
        assert " kq " in diagrams.initial_fen(moved, number=4, black_to_move=True)


class TestInTheParser:
    def make_tokens(self, *pairs):
        return [
            Token(kind=kind, text=text, raw=text, page=1, start=0, end=len(text),
                  bbox=BBox(72.0, 640.0, 18.0, 10.0))
            for kind, text in pairs
        ]

    def table(self):
        return diagrams.learn([(rows_of(chess.STARTING_BOARD_FEN), [chess.STARTING_BOARD_FEN])])

    def test_a_diagram_gives_a_game_the_position_it_opens_on(self):
        # What a chapter opening on a picture used to cost: every move read
        # from the standard initial position, illegal from the first ply.
        position = fen_after("d4", "d5", "c4", "e6", "Nc3", "Nf6")
        result = parse_tokens(
            self.make_tokens(
                ("diagram", "/".join(rows_of(position))),
                ("move_number", "4."), ("move", "Bg5"), ("move", "Be7"),
            ),
            diagram_table=self.table(),
        )

        assert [m.san for m in result.moves] == ["Bg5", "Be7"]
        assert all(m.status == "ok" for m in result.moves)
        assert result.games[0].initial_fen.startswith(position)
        assert [c["verdict"] for c in result.diagram_checks] == ["seeds"]

    def test_a_diagram_opens_a_game_on_any_number_it_likes(self):
        # A game begins on its first move — unless the book printed where it
        # begins. Here the previous game has ended and the next position is
        # given as a picture, so `23...` opens a game that is fully scored.
        position = fen_after("d4", "d5", "c4", "e6", "Nc3", "Nf6")
        result = parse_tokens(
            self.make_tokens(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("result", "1-0"),
                ("diagram", "/".join(rows_of(position))),
                ("move_number", "4."), ("move", "Bg5"), ("move", "Be7"),
            ),
            diagram_table=self.table(),
        )

        opened = result.games[-1]
        assert opened.position_known is True
        assert opened.initial_fen.startswith(position)
        assert [m.status for m in result.moves if m.game_id == opened.id] == ["ok", "ok"]

    def test_a_diagram_puts_a_line_that_drifted_back_on_the_board(self):
        # The score is read into the wrong branch, and then the book prints
        # where the pieces actually are.
        printed = fen_after("d4", "d5", "c4")
        result = parse_tokens(
            self.make_tokens(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("diagram", "/".join(rows_of(printed))),
                ("move_number", "2..."), ("move", "dxc4"),
            ),
            diagram_table=self.table(),
        )

        by_san = {m.san: m for m in result.moves}
        assert by_san["dxc4"].status == "ok"
        assert [c["verdict"] for c in result.diagram_checks] == ["corrects"]

    def test_a_correction_puts_the_moves_above_it_in_doubt(self):
        # None of these moves is illegal, so nothing breaks; the diagram is the
        # only thing in the document that knows they are wrong.
        printed = fen_after("d4", "d5", "c4")
        result = parse_tokens(
            self.make_tokens(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("diagram", "/".join(rows_of(printed))),
                ("move_number", "2..."), ("move", "dxc4"),
            ),
            diagram_table=self.table(),
        )

        by_san = {m.san: m for m in result.moves}
        assert result.contradicted == [by_san["e5"].id, by_san["e4"].id]
        assert result.break_diagnosis()["clean"] == 1      # dxc4, below the diagram
        assert result.break_diagnosis()["contradicted"] == 2

    def test_a_confirmation_clears_what_stands_above_it(self):
        printed = fen_after("e4", "e5")
        drifted = fen_after("d4", "d5", "c4")
        result = parse_tokens(
            self.make_tokens(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("diagram", "/".join(rows_of(printed))),
                ("move_number", "2."), ("move", "Nf3"), ("move", "Nc6"),
                ("diagram", "/".join(rows_of(drifted))),
            ),
            diagram_table=self.table(),
        )

        by_san = {m.san: m for m in result.moves}
        # Only the two moves played since the diagram that agreed are in doubt.
        assert result.contradicted == [by_san["Nc6"].id, by_san["Nf3"].id]

    def test_a_diagram_that_agrees_says_so_and_changes_nothing(self):
        result = parse_tokens(
            self.make_tokens(
                ("move_number", "1."), ("move", "e4"), ("move", "e5"),
                ("diagram", "/".join(rows_of(fen_after("e4", "e5")))),
                ("move_number", "2."), ("move", "Nf3"),
            ),
            diagram_table=self.table(),
        )

        assert [m.san for m in result.moves] == ["e4", "e5", "Nf3"]
        assert [c["verdict"] for c in result.diagram_checks] == ["confirms"]

    def test_without_the_font_a_diagram_is_only_recorded(self):
        result = parse_tokens(
            self.make_tokens(
                ("move_number", "1."), ("move", "e4"),
                ("diagram", "/".join(rows_of(fen_after("e4")))),
            )
        )

        assert [c["verdict"] for c in result.diagram_checks] == ["unread"]
        assert [m.san for m in result.moves] == ["e4"]


class TestInTheTokeniser:
    def test_the_rows_become_one_token_and_not_prose(self):
        rows = rows_of(chess.STARTING_BOARD_FEN)
        page = page_of("Before.\n" + "\n".join(rows) + "\nAfter.\n")

        tokens = tokenize_pages([page], diagrams=diagrams.find([page]))

        kinds = [t.kind for t in tokens]
        assert kinds == ["text", "diagram", "text"]
        assert tokens[1].text == "/".join(rows)


TWINS = [("T", "R"), ("S", "N"), ("L", "B"), ("D", "Q"), ("M", "K"), ("J", "I")]

MIDDLEGAME = "r1bq1rk1/pp2ppbp/2np1np1/8/2P1P3/2N1BP2/PP2N1PP/R2QKB1R"
ENDGAME = "8/5pk1/6p1/8/8/6P1/5PK1/8"


def test_the_boards_name_the_characters_when_no_game_can():
    """A book of puzzles never plays a move up to a diagram, so `learn` is
    handed nothing. The positions themselves still say a great deal."""
    boards = [rows_of(fen) for fen in (chess.Board().board_fen(), MIDDLEGAME, ENDGAME)]
    tables = diagrams.settle(boards, TWINS, ".")

    assert FONT in tables
    assert all(diagrams.decode(rows, table) for table in tables for rows in boards)


def test_legality_cannot_do_it_alone_and_says_so_by_leaving_a_tie():
    """Swapping a knight for a bishop leaves every position legal, and so does
    exchanging the two colours. What comes back is a shortlist, not an answer
    — `pipeline._best_table` reads the book with each of them."""
    boards = [rows_of(fen) for fen in (MIDDLEGAME, ENDGAME)]
    tables = diagrams.settle(boards, TWINS, ".")

    assert len(tables) > 1
    # A shortlist all the same, and it shrinks as boards are added: two boards
    # leave 96 tables standing, and Grivas' thirty leave 12.
    assert len(tables) < 200


def test_a_character_no_twin_covers_leaves_nothing_to_settle():
    """A board carrying a stray cannot be read under any table, so it supports
    none of them; a book of nothing but such boards settles nothing."""
    rows = list(rows_of(MIDDLEGAME))
    rows[4] = "?" + rows[4][1:]
    assert diagrams.settle([tuple(rows)], TWINS, ".") == []


def test_three_rooks_beside_eight_pawns_never_happened():
    """`python-chess` counts pawns and kings but not promotions. A third rook
    was made from a pawn, and a side that still has all eight never made one.
    Eight rooks on their own are legal — six promotions — so it is the two
    counts together that this catches."""
    impossible = "7k/8/8/8/8/8/PPPPPPPP/RRRK4"
    assert not diagrams._stands(rows_of(impossible), FONT)
    assert diagrams._stands(rows_of(ENDGAME), FONT)
