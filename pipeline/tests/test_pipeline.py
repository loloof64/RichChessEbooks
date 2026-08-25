"""Tests for the steps `pipeline.run` takes between the modules.

Only what the modules cannot answer on their own lives here: which of the
tables `diagrams.settle` allows a book should actually be read with.
"""

import chess

from rce_pipeline import pipeline
from rce_pipeline.extract import BBox
from rce_pipeline.parse import parse_tokens
from rce_pipeline.tokenize import Token

BOX = BBox(72.0, 640.0, 18.0, 10.0)


def tok(kind: str, text: str, bold: bool = False) -> Token:
    return Token(
        kind=kind, text=text, raw=text, page=1, start=0, end=len(text), bbox=BOX,
        bold=bold,
    )


def rows_of(board: chess.Board) -> str:
    """A board as eight rows of eight characters, the diagram token's shape."""
    return "/".join(
        "".join(
            board.piece_at(chess.square(file, rank)).symbol()
            if board.piece_at(chess.square(file, rank))
            else "."
            for file in range(8)
        )
        for rank in range(7, -1, -1)
    )


def game_and_diagram() -> tuple[list[Token], dict[str, str]]:
    """Three sound moves, then a diagram of the position they reach."""
    board = chess.Board()
    for san in ("e4", "e5", "Nf3"):
        board.push_san(san)
    tokens = [
        tok("move_number", "1."), tok("move", "e4"), tok("move", "e5"),
        tok("move_number", "2."), tok("move", "Nf3"),
        tok("diagram", rows_of(board)),
    ]
    return tokens, {char: char for char in set(rows_of(board)) - {"/"}}


def test_the_table_the_book_reads_best_is_the_one_taken():
    tokens, right = game_and_diagram()
    without = parse_tokens(tokens)
    assert pipeline._best_table([right], tokens, without, strict_numbering=True) == right


def test_a_table_that_leaves_the_book_worse_is_refused():
    """Reading no diagram is one of the candidates, and it can win.

    The wrong table has the knights and bishops exchanged, so every character
    is known and the position it prints is legal — and contradicts the three
    moves that reached it. Legality cannot tell the two tables apart; the
    book can.
    """
    tokens, right = game_and_diagram()
    wrong = dict(right)
    for one, other in (("N", "B"), ("n", "b")):
        wrong[one], wrong[other] = right[other], right[one]

    without = parse_tokens(tokens)
    assert without.break_diagnosis()["clean"] == 3
    assert parse_tokens(tokens, diagram_table=wrong).break_diagnosis()["clean"] < 3

    assert pipeline._best_table([wrong], tokens, without, strict_numbering=True) == {}


def test_a_learned_table_is_asked_only_not_to_break_the_book():
    """A table the book's own games taught clears a lower bar than a guess.

    Every character of it was named by a position one of the book's own lines
    reached, so it is not asked to leave the book better than reading nothing
    — a board only ever takes moves out of `clean`, and a reading with no
    diagrams wins that comparison by never disagreeing. It is asked not to
    break the book.
    """
    tokens, right = game_and_diagram()
    without = parse_tokens(tokens)
    assert pipeline._worth_reading(right, tokens, without, strict_numbering=True)


def test_a_learned_table_that_breaks_the_book_is_refused():
    """Boussole is what this is for: two boards read of seventeen drawn.

    The table those two taught seeds positions the book never printed, and the
    moves that follow are illegal on them. Here the knights and bishops are
    exchanged, so the diagram puts a bishop where the game has a knight and
    `4.Bb5` has no bishop to play — the line dies under the board.
    """
    board = chess.Board()
    for san in ("e4", "e5", "Nf3"):
        board.push_san(san)
    tokens = [
        tok("move_number", "1."), tok("move", "e4"), tok("move", "e5"),
        tok("move_number", "2."), tok("move", "Nf3"),
        tok("diagram", rows_of(board)),
        tok("move_number", "2..."), tok("move", "Nc6"),
        tok("move_number", "3."), tok("move", "Bb5"), tok("move", "a6"),
        tok("move_number", "4."), tok("move", "Ba4"), tok("move", "Nf6"),
    ]
    right = {char: char for char in set(rows_of(board)) - {"/"}}
    wrong = dict(right)
    for one, other in (("N", "B"), ("n", "b")):
        wrong[one], wrong[other] = right[other], right[one]

    without = parse_tokens(tokens)
    assert pipeline._worth_reading(right, tokens, without, strict_numbering=True)
    assert not pipeline._worth_reading(wrong, tokens, without, strict_numbering=True)


def shuffling_game() -> tuple[list[Token], dict[str, str]]:
    """Eighty plies of knights walking out and back, and a diagram of the end.

    Long enough for `weight_marks_the_line` to have an opinion, and marked the
    way a scan's ink marks a book the measurement was wrong about: four numbers
    in ten and every second move, neither of them the score. Two moves stand
    clean at that weight; read flat, all eighty do.

    Both halves of the marking matter. A number alone can no longer cripple a
    book, because a bold number resuming the score at the ply the aside beneath
    it has reached takes that aside back: the whole score comes home from one
    mark in ten. It is the moves' own marks that no number repairs — a plain
    move standing on the main line with no number to place it is analysis, and
    against marks like these the score is broken up at every miss.
    """
    board = chess.Board()
    walk = ("Nf3", "Nf6", "Ng1", "Ng8")
    tokens: list[Token] = []
    for number in range(1, 41):
        tokens.append(tok("move_number", f"{number}.", bold=number % 10 in (1, 2, 3, 4)))
        for half in range(2):
            san = walk[((number - 1) * 2 + half) % 4]
            board.push_san(san)
            tokens.append(tok("move", san, bold=half == 1))
    tokens.append(tok("diagram", rows_of(board)))
    return tokens, {char: char for char in set(rows_of(board)) - {"/"}}


def test_a_table_is_weighed_at_the_weight_the_book_would_ship_it_in():
    """The two decisions are one decision, and Grivas is where that was paid.

    Whether to read the weight measured off the ink is settled *after* the
    diagrams, by a comparison of exactly this kind — so a table judged on the
    weighted reading alone is judged on a reading the book may be about to
    throw away. Here the weighted reading is the one it throws away: it leaves
    two moves clean where reading the book flat leaves 80, and against a
    crippled reading a table with the knights and bishops exchanged looks like
    a gain. Weighed at both weights, it is refused.
    """
    tokens, right = shuffling_game()
    wrong = dict(right)
    for one, other in (("N", "B"), ("n", "b")):
        wrong[one], wrong[other] = right[other], right[one]
    without = parse_tokens(tokens)

    assert without.break_diagnosis()["clean"] == 2
    assert parse_tokens(tokens, weighted=False).break_diagnosis()["clean"] == 80

    assert pipeline._best_table(
        [wrong], tokens, without, strict_numbering=True
    ) == wrong
    assert pipeline._best_table(
        [wrong], tokens, without, strict_numbering=True, weight_in_doubt=True
    ) == {}


def test_the_right_table_still_wins_when_the_weight_is_in_doubt():
    tokens, right = shuffling_game()
    wrong = dict(right)
    for one, other in (("N", "B"), ("n", "b")):
        wrong[one], wrong[other] = right[other], right[one]

    assert pipeline._best_table(
        [wrong, right], tokens, parse_tokens(tokens),
        strict_numbering=True, weight_in_doubt=True,
    ) == right
