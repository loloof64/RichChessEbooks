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

        table = diagrams.learn([(rows, chess.STARTING_BOARD_FEN)])

        assert diagrams.decode(rows, table) == chess.STARTING_BOARD_FEN

    def test_a_diagram_read_on_a_drifted_board_does_not_teach(self):
        # The board the parser had reached is wrong here, and it is the only
        # observation that disagrees: the two sound ones outvote it as wholes.
        sound = [
            (rows_of(chess.STARTING_BOARD_FEN), chess.STARTING_BOARD_FEN),
            (rows_of(fen_after("e4")), fen_after("e4")),
        ]
        drifted = (rows_of(fen_after("e4", "e5")), fen_after("d4", "d5"))

        table = diagrams.learn(sound + [drifted])

        assert diagrams.decode(rows_of(fen_after("e4", "e5")), table) == fen_after("e4", "e5")

    def test_learns_the_letter_it_never_saw_from_its_other_case(self):
        # No game reaches a position with a white queen on a dark square, so
        # the book never prints that form beside a board anyone knows.
        table = diagrams.learn([(rows_of(chess.STARTING_BOARD_FEN), chess.STARTING_BOARD_FEN)])

        assert table["q"] == "Q"
        assert table["m"] == "k"


class TestDecoding:
    def test_refuses_a_diagram_holding_a_character_it_has_not_learned(self):
        table = diagrams.learn([(rows_of(chess.STARTING_BOARD_FEN), chess.STARTING_BOARD_FEN)])
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
        return diagrams.learn([(rows_of(chess.STARTING_BOARD_FEN), chess.STARTING_BOARD_FEN)])

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
