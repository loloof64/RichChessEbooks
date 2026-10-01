"""Tests for turning a page's characters into tokens.

What matters here is which spans become moves and move numbers, since the
parser refuses a move that no number announced and a whole column of a book
can be lost to that alone.
"""

from rce_pipeline.extract import BBox, Char, Page
from rce_pipeline.parse import parse_tokens
from rce_pipeline.tokenize import tokenize_pages


def page_of(text: str) -> Page:
    chars = [
        Char(char=ch, bbox=BBox(float(i), 700.0, 1.0, 10.0), font="Serif", size=10.0)
        for i, ch in enumerate(text)
    ]
    return Page(number=1, width=595.0, height=842.0, text=text, chars=chars)


class TestTheWreckOfASymbol:
    def test_an_angle_is_part_of_a_broken_king(self):
        # `12 ♔fi>h1` arrives with the king drawn away and `fi>` left behind.
        # Without the angle in the run, `h1` was read as a pawn move to the
        # first rank — legal to parse, impossible to play, and it carried
        # fifty-eight moves of one book down with it.
        tokens = tokenize_pages([page_of("12 fi>h1 c5")])

        move = next(t for t in tokens if t.kind == "move" and t.text == "h1")
        assert move.lost_symbol == "fi>"

    def test_an_exclamation_mark_is_part_of_a_broken_knight(self):
        # Grivas page 16 prints `18...♘a4` and the scan has `lL!a4`: the `!`
        # was read as a comment on nothing and `a4` as a pawn move.
        tokens = tokenize_pages([page_of("18 ... lL!a4 19 e5! ")])

        move = next(t for t in tokens if t.kind == "move" and t.text == "a4")
        assert move.lost_symbol == "lL!"
        assert [t.kind for t in tokens].count("annotation") == 1

    def test_an_exclamation_mark_inside_a_broken_queen(self):
        # Grivas page 16: "White had no reason to worry about 18...♕a3 19 ♔c2
        # ♘a4 20 ♖b3!" -- the scan has `.'i!Va3`, the run stopped at the `!`
        # and the queen's move was lost: `19 ♔c2` went onto the game and the
        # variation broke. The same queen stands in five scans more.
        tokens = tokenize_pages([page_of("18 .. .'i!Va3 19 Kc2 ")])

        move = next(t for t in tokens if t.kind == "move" and t.text == "a3")
        assert move.lost_symbol.endswith("'i!V")

    def test_a_wreck_may_begin_with_a_one(self):
        # Grivas page 23, "18...♕xc4! (D)": the scan has `1Wxc4`, and `1i'`,
        # `1W`, `1L` stand for a symbol 69 times in the book. Left out of the
        # wreck, the `1` either stayed in the prose or joined the number in
        # front -- `16 1i'd2` was read as move 1 -- and the move was lost.
        for text, number, square, wreck in (
            ("18 ... 1Wxc4! 19 Rc1? ", "18...", "xc4", "1W"),
            ("15 ... Rxh6 16 1i'd2 Rxh4?! ", "16", "d2", "1i'"),
        ):
            tokens = tokenize_pages([page_of(text)])
            move = next(t for t in tokens if t.kind == "move" and t.text == square)
            numbers = [t.text.strip() for t in tokens if t.kind == "move_number"]
            assert move.lost_symbol == wreck and number in numbers, text

    def test_the_rook_of_the_same_scan_is_not_cut_in_two(self):
        # Page 99 prints its rook `l:!.`: a `!` taken anywhere in a run gave
        # `f2` the half `!.` of it, and the move was read with the wrong piece.
        tokens = tokenize_pages([page_of("23 l:!.f2 l:!.e5! 24 Qg4 ")])

        assert "!." not in [t.lost_symbol for t in tokens if t.kind == "move"]

    def test_it_gives_the_move_number_back_its_dot(self):
        # `9.i.xg5` on Boussole page 65. The run reaches back over the number's
        # dot, and a wreck overlapping the token before it used to be dropped
        # whole — so the bishop was lost, `xg5` was read as a piece the board
        # had to guess, and it could not: fifteen moves of the game went with
        # it. What is left after the number has its own back is still a wreck.
        tokens = tokenize_pages([page_of("8.g5 hxg5 9.i.xg5 Re8")])

        move = next(t for t in tokens if t.text == "xg5")
        number = next(t for t in tokens if t.kind == "move_number" and t.text == "9.")
        assert move.lost_symbol == "i."
        assert number.end == move.start

    def test_nothing_is_left_of_a_wreck_that_was_only_the_number(self):
        tokens = tokenize_pages([page_of("8.g5 hxg5 9.xg5 Re8")])

        assert next(t for t in tokens if t.text == "xg5").lost_symbol == ""

    def test_the_number_a_wreck_hid_still_announces_the_move(self):
        # `16lilxd4` on Grivas page 18: a bare number counts only where a move
        # follows it, and what follows here is the ink the scanner made of a
        # knight. The `16` stayed in the prose above, and every move after it
        # was played a ply early.
        tokens = tokenize_pages(
            [page_of("Practically forced. 16lilxd4 .tb7")], spellings={"lil": "N"}
        )

        number = next(t for t in tokens if t.kind == "move_number")
        move = next(t for t in tokens if t.kind == "move" and t.text == "xd4")
        assert number.text == "16"
        # The move begins at its wreck, so the number ends where it begins:
        # nothing of the score is left standing in the prose.
        assert (move.raw, move.lost_symbol) == ("lilxd4", "lil")
        assert number.end == move.start

    def test_a_space_between_the_number_and_the_wreck_changes_nothing(self):
        # The scanner keeps the space as readily as it loses it, and the
        # bare-number branch is handed a wreck either way.
        tokens = tokenize_pages([page_of("l:xa8 21 lilc6.")], spellings={"lil": "N"})

        assert next(t for t in tokens if t.kind == "move_number").text.strip() == "21"

    def test_a_number_the_font_broke_in_two_stays_whole(self):
        # `'it'g6+ 1 1 Cf4` on Grivas page 28: the number of `11 ♔f4` came
        # out as `1`, and the line was replayed from the first move.
        tokens = tokenize_pages([page_of("10 Kg3 Qg6+ 1 1 Cf4 Qf5+")], spellings={"C": "K"})

        assert next(t for t in tokens if t.kind == "move_number" and t.start > 3).text.strip() == "11"


class TestAWreckAMoveNumberRunsInto:
    """A wreck that reaches back over the number's dots gives them back.

    What is left after the number has its own is still the symbol, and it is
    still the symbol when the book's own spelling is all that says so.
    """

    def test_a_letter_the_book_spells_survives_the_take_back(self):
        # `21...Wb7` on SuperAttaquant: the wreck found is `.W`, the number
        # takes its dot back, and the `W` left standing carries no mark of any
        # kind. Dropped, `b7` reads as a pawn move to the seventh rank — legal
        # to parse, impossible to play, and it took 30 moves of the game down.
        tokens = tokenize_pages([page_of("par 21...Wb7 22.c6")], spellings={"W": "Q"})

        move = next(t for t in tokens if t.text == "b7")
        assert (move.lost_symbol, move.lost_piece) == ("W", "Q")

    def test_a_run_the_book_never_spelled_is_no_wreck(self):
        # And with no wreck in front of it the token is not read at all — the
        # letter running into it is a word as far as anything here can tell.
        tokens = tokenize_pages([page_of("par 21...Zb7 22.c6")], spellings={"W": "Q"})

        assert not [t for t in tokens if t.kind == "move" and t.text == "b7"]


class TestPromotion:
    """The piece a pawn promoted to, written with no equals sign.

    A figurine set straight after the square is how SuperAttaquant writes it —
    `33.dxe8♕+`, `42.c8♕`, `29.exf8♕#` — and with no `=` to find, none of
    those was a token at all: the move vanished and the line went with it.
    """

    def test_the_piece_after_the_square_is_the_promotion(self):
        tokens = tokenize_pages([page_of("33.dxe8Q+ Rxe8")])

        assert [t.text for t in tokens if t.kind == "move"] == ["dxe8Q+", "Rxe8"]

    def test_two_moves_run_together_are_not_a_promotion(self):
        # `16♗a2♗c7` on Boussole page 65: a lost space runs two moves together,
        # and read as a promotion the second move disappears into the first.
        # The second rank is not a promotion rank and a square follows the
        # piece, so either guard alone refuses it.
        tokens = tokenize_pages([page_of("16 Ba2Bc7")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Ba2", "Bc7"]

    def test_the_equals_sign_form_still_reads(self):
        tokens = tokenize_pages([page_of("51.a8=Q Kf7")])

        assert [t.text for t in tokens if t.kind == "move"] == ["a8=Q", "Kf7"]


class TestTheBooksOwnSpelling:
    """The piece a wreck is, where the book has been seen spelling it so.

    `glyphs.spellings` learns the table from the symbols the glyph pass did
    restore; here it is only looked up.
    """

    def test_the_spelling_names_the_piece(self):
        tokens = tokenize_pages([page_of("9.i.xg5 Re8")], spellings={"i.": "B"})

        assert next(t for t in tokens if t.text == "xg5").lost_piece == "B"

    def test_a_spelling_the_book_never_taught_names_nothing(self):
        tokens = tokenize_pages([page_of("9.i.xg5 Re8")], spellings={"ltJ": "N"})

        assert next(t for t in tokens if t.text == "xg5").lost_piece == ""

    def test_the_longest_ending_the_book_taught_is_the_one_read(self):
        # The wreck runs back over whatever stood before the symbol, so the
        # book's spelling is at the end of it — and the longest ending wins,
        # a book that spells both `.i.` and `.` having meant the first.
        tokens = tokenize_pages(
            [page_of("9. .i.xg5 Re8")], spellings={".i.": "B", ".": "R"}
        )

        assert next(t for t in tokens if t.text == "xg5").lost_piece == "B"


class TestANumberTheScannerSpelled:
    """A move number whose digits the OCR read as letters.

    Silman's *How to Reassess Your Chess* is a scan whose layer spells `10.`
    as `lO.`, `15.` as `IS.` and `38.` as `3S.` — over seventy numbers in
    seventeen pages, some welded to their move (`lO.b3`) and read as the wreck
    of a piece symbol, some standing alone and read as prose. Either way the
    move has no number, and the game it opens is never placed.
    """

    def test_a_number_welded_to_its_move_is_a_number(self):
        tokens = tokenize_pages([page_of("9.Nf3 Nf6 lO.Bd3 Be7")])

        numbers = [t.text for t in tokens if t.kind == "move_number"]
        move = next(t for t in tokens if t.text == "Bd3")
        assert numbers == ["9.", "10."]
        assert move.lost_symbol == ""


class TestAPieceWhoseSquareTheScannerLost:
    """`2.NO Nc6` — Silman's scan reads `f3` as `O` about half the time.

    `NO`, `BO`, `QO`: the piece is printed and its square is not a square, so
    the token matched nothing and the move was gone — and `2...Nc6` was then
    played as White's second, killing eleven games of seventeen pages on
    their third ply. Inside a score, hard behind a number, it is a move whose
    square the board has to name.
    """

    def test_it_is_a_move_with_its_square_lost(self):
        tokens = tokenize_pages([page_of("1.e4 c5 2.NO Nc6 3.c3")])

        move = next(t for t in tokens if t.raw.strip() == "NO")
        assert (move.kind, move.text) == ("move", "N?")


class TestACaptureSetWithSpaces:
    """`D x b2`, `T X f5`, `c x d5` — Pachman's *Théorie élémentaire* sets the
    capture sign between spaces, 351 times in seventeen pages against seven
    tight. None of those captures was a token, and every line died on its
    first one."""

    def test_the_capture_is_one_move(self):
        tokens = tokenize_pages(
            [page_of("26. T x a7 D X b2 27. c x d5")], piece_letters="RDTFC"
        )

        assert [t.text for t in tokens if t.kind == "move"] == ["Rxa7", "Qxb2", "cxd5"]

    def test_a_line_may_break_behind_the_sign(self):
        # `7. F X e7 D X \ne7`: the queen's recapture, across a line break in a
        # narrow column — the layer keeps the space before the break. Lost,
        # the queen never reached e7 and `9...Db4` died.
        tokens = tokenize_pages([page_of("7. F X e7 D X \ne7 8. C X e4")], piece_letters="RDTFC")

        assert [t.text for t in tokens if t.kind == "move"] == ["Bxe7", "Qxe7", "Nxe4"]

    def test_a_five_read_as_a_small_s_behind_the_sign(self):
        # `13. C x es`, `d x cs`: this scan reads `5` as `s` as well as `S`.
        # Behind the sign a square is due, so the letter is its rank; the
        # move goes out as printed and `parse` weighs the look-alike.
        tokens = tokenize_pages([page_of("13. C x es d x cs")], piece_letters="RDTFC")

        assert [t.text for t in tokens if t.kind == "move"] == ["Nxes", "dxcs"]


class TestANumberThatLostADot:
    """`21..♕xb5` — a scan loses one dot of an ellipsis as readily as it
    loses anything else. Nineteen of SuperAttaquant's black numbers and
    fifteen of Boussole's, and each one throws the rest of its line a ply out
    of step with the page: `21...♕xb5` read as White's twenty-first."""

    def test_two_dots_announce_a_black_move(self):
        tokens = tokenize_pages([page_of("20 Bb5 axb5 21 axb5 21..Qxb5")])

        assert [t.text for t in tokens if t.kind == "move_number"][-1] == "21.."

    def test_the_side_it_names_is_black(self):
        result = parse_tokens(tokenize_pages([page_of("1 e4 e5 2 Nf3 2..Nc6")]))

        move = result.moves[-1]
        assert (move.san, move.variation_index) == ("Nc6", 0)

    def test_the_second_dot_may_not_stand_off(self):
        # `9. .i.xg5` is a move number and then the wreck of a bishop. A loose
        # second dot eats the wreck, and the board is left guessing the piece.
        tokens = tokenize_pages([page_of("8.g5 hxg5 9. .i.xg5 Re8")])

        assert next(t for t in tokens if t.text == "xg5").lost_symbol == ".i."


class TestARankNoMoveCanCarry:
    """A digit at the head of a move that names no piece.

    SAN writes a rank only to say which of two pieces moved, so it cannot
    stand where there is no piece letter to disambiguate. SuperAttaquant's
    scanner draws the bishop as `2` and the rook as `8`, and `16.2b2` was read
    as a move to b2 with a rank in front of it that means nothing.
    """

    def test_the_rank_is_the_wreck_of_the_piece(self):
        tokens = tokenize_pages([page_of("15.b3 Nbd7 16.2b2 Nxe5")])

        move = next(t for t in tokens if t.text == "b2")
        assert move.lost_symbol == "2"
        assert move.raw == "2b2"

    def test_the_number_that_announced_it_keeps_its_own_digits(self):
        # The digit used to be read as a move number of its own — `16.` fell
        # into the prose and `2` announced a pawn move to b2.
        tokens = tokenize_pages([page_of("15.b3 Nbd7 16.2b2 Nxe5")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["15.", "16."]

    def test_the_board_names_the_piece(self):
        result = parse_tokens(
            tokenize_pages([page_of("1 d4 d5 2 b3 Nf6 3 2b2 e6")])
        )

        move = next(m for m in result.moves if m.ply == 5)
        assert move.san == "Bb2"

    def test_a_move_that_names_its_piece_keeps_its_rank(self):
        tokens = tokenize_pages([page_of("20 R1e2 Kh8")])

        move = next(t for t in tokens if t.kind == "move" and t.text.startswith("R"))
        assert (move.text, move.lost_symbol) == ("R1e2", "")


class TestASpellingWithNoMarkInIt:
    """A symbol a scanner read as one ordinary letter and nothing else.

    `_WRECK_MARK` knows a wreck by the punctuation in it, and there is none in
    SuperAttaquant's queen: it comes out `W`, ninety times over the twelve
    pages. The book's own spelling table is what says so.
    """

    def test_a_letter_the_book_spells_is_a_wreck(self):
        tokens = tokenize_pages([page_of("29.Kh1 Wf3+ 30.Kg1")], spellings={"W": "Q"})

        move = next(t for t in tokens if t.text == "f3+")
        assert (move.lost_symbol, move.lost_piece) == ("W", "Q")

    def test_without_the_spelling_the_move_is_not_read_at_all(self):
        tokens = tokenize_pages([page_of("29.Kh1 Wf3+ 30.Kg1")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Kh1", "Kg1"]

    def test_a_word_may_not_stand_in_front_of_the_ink(self):
        # A symbol's ink begins where the word does. Grivas spells a queen
        # `n`, which stands inside "positional" — and the word then ended in
        # a move to a1, taking the citation beside it down.
        tokens = tokenize_pages([page_of("a positional edge")], spellings={"n": "Q"})

        assert [t.text for t in tokens if t.kind == "move"] == []

    def test_a_spelling_of_nothing_but_dots_is_refused(self):
        # Whatever the book has been seen doing with it: a dot in front of a
        # move is how every book in the corpus announces a black one.
        tokens = tokenize_pages([page_of("21 ...f5 22 e4")], spellings={".": "B"})

        assert next(t for t in tokens if t.text == "f5").lost_symbol == ""


class TestALetterWhereARankBelongs:
    def test_a_rank_read_as_a_letter_still_becomes_a_move(self):
        # Grivas prints black's sixth as `6 a4 QaS?!` and Boussole prints
        # `3.gS cS` forty times over twelve pages. Left out of the pattern the
        # move is not a move at all, so the side to play is wrong from there
        # and the line dies a few plies later.
        tokens = tokenize_pages([page_of("6 a4 QaS")])

        assert [t.text for t in tokens if t.kind == "move"] == ["a4", "QaS"]

    def test_the_position_is_what_reads_it(self):
        # Emitted as printed, and repaired by the board or not at all: `5`/`S`
        # is a confusable pair, so `QaS` costs half an edit and only `Qa5`
        # answers it here.
        result = parse_tokens(tokenize_pages([page_of("1 d4 c6 2 Nc3 QaS")]))

        move = result.moves[-1]
        assert move.san == "Qa5"
        assert move.status == "uncertain"
        assert move.repair["raw"] == "QaS"

    def test_the_first_rank_is_a_letter_too(self):
        # `11 ♘c1!` prints as `11 ♘cl`, and losing it left the rest of the
        # game a move behind the page. Thirty-four of them on Grivas alone.
        tokens = tokenize_pages([page_of("11 Ncl Rdfl Khl")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Ncl", "Rdfl", "Khl"]

    def test_an_elided_article_is_not_a_move(self):
        # With `l` read as a rank, the French `de l'échiquier` is shaped
        # exactly like `Re1`: a file, a first rank, and a word boundary after
        # it. Twenty-seven articles over two scanned books, and no real move
        # in the corpus is followed by an apostrophe.
        tokens = tokenize_pages([page_of("le fou de l'aile Rel")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Rel"]

    def test_a_letter_the_book_uses_for_a_piece_is_not_a_rank(self):
        # A German book spells its Knight `S`. Reading `dS` as `d5` there
        # would turn one of its moves into another.
        tokens = tokenize_pages([page_of("6 a4 dS")], piece_letters="KDTLS")

        assert [t.text for t in tokens if t.kind == "move"] == ["a4"]


class TestTheMoveWrittenFromSquareToSquare:
    """`...b7-b5`, `♗f1-g2` — the long form, and how a book names a plan."""

    def test_the_destination_is_the_move(self):
        tokens = tokenize_pages([page_of("1.e4 c6 2.d4 d5 3.Nc3 b5 4.e5 ...b7-b5 ")])

        assert [t.text for t in tokens if t.kind == "move"][-1] == "b5"

    def test_the_piece_carries_over(self):
        tokens = tokenize_pages([page_of("White intends Bf1-g2 and O-O ")])

        assert "Bg2" in [t.text for t in tokens if t.kind == "move"]

    def test_the_reader_taps_the_whole_journey(self):
        tokens = tokenize_pages([page_of("1.e4 c6 2.d4 ...b7-b5 ")])
        journey = [t for t in tokens if t.kind == "move"][-1]

        assert journey.raw == "b7-b5"

    def test_the_line_may_break_behind_the_dash(self):
        # Sakaev page 21: "17.♖ad1, followed by ♗e2-\nc4." — the square left
        # alone on the next line was read as a pawn going to c4.
        tokens = tokenize_pages([page_of("17.Rad1, followed by Be2-\nc4.\n")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Rad1", "Bc4"]


class TestTheStumpOfARestoredSymbol:
    """What the glyph pass leaves in front of the letter it restored.

    A move that names its piece never looks for the wreck of one, since
    asking the board for a second piece in front of it can only fail. But the
    ink the symbol was drawn with is still there — `lNc3`, `ltNxe5`, `iQd8` —
    and a move running out of a letter was refused outright, which on Boussole
    is 93 moves and on Grivas 11.
    """

    def test_a_move_keeps_the_stump_of_the_symbol_it_names(self):
        tokens = tokenize_pages([page_of("1.e4 e5 2.lNf3 ltNc6 3.iBc4 ")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "e4", "e5", "Nf3", "Nc6", "Bc4",
        ]

    def test_the_tap_zone_covers_the_stump_as_well(self):
        # The stump is the piece as the book drew it, so it belongs to the
        # zone the reader taps — exactly as an unrestored wreck does.
        tokens = tokenize_pages([page_of("1.e4 e5 2.lNf3 ")])
        knight = [t for t in tokens if t.text == "Nf3"][0]

        assert knight.raw == ".lNf3"

    def test_a_stump_names_no_second_piece(self):
        # It is ink, not a symbol the board has to read: `lost_symbol` stays
        # empty, or the parser would look for a piece in front of the knight.
        tokens = tokenize_pages([page_of("1.e4 e5 2.lNf3 ")])
        knight = [t for t in tokens if t.text == "Nf3"][0]

        assert knight.lost_symbol == ""


class TestASquareBrokenInTwo:
    def test_a_space_between_the_file_and_the_rank(self):
        # The subset font that breaks `18` into `1 8` breaks `♖ac1` into
        # `♖ac 1`. Left out, the move matches nothing and the line loses it.
        tokens = tokenize_pages([page_of("23 Rac 1 Qa5 24 Rc 1")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Rac1", "Qa5", "Rc1"]

    def test_rs_is_f5(self):
        # Grivas page 16, "1 c4 rs 2 lLlc3": thirteen times in the book, and
        # every one is f5 — `f` read as `r` and `5` as `s`. Left as a word,
        # 1...f5 was lost and the game played on the wrong side.
        tokens = tokenize_pages([page_of("1 c4 rs 2 Nc3 Nf6 and Mrs rsa ")])

        assert [t.text for t in tokens if t.kind == "move"] == ["c4", "f5", "Nc3", "Nf6"]

    def test_a_move_welded_to_the_wreck_of_the_next_one(self):
        # Grivas page 18, "1 d4 d6 2 e4lilf6 3 f3": the space went with the
        # knight's symbol, `e4` was read as prose and the whole game was
        # played a ply short. Not a French word between two squares: Loheac
        # prints "g5 ou en f6" as `g5ouenf6`.
        tokens = tokenize_pages([page_of("1 d4 d6 2 e4lilf6 3 f3 e5 4 g5ouenf6 ")])

        moves = [t.raw for t in tokens if t.kind == "move"]
        assert moves[:3] == ["d4", "d6", "e4"] and "g5" not in moves

    def test_a_dot_behind_the_capture_sign(self):
        # Grivas folio 20 prints `18 ♖axd1` and the scan has `♖ax.d1`: only
        # `d1` was read, as a knight, the rook never reached d1 and `20 ♖df1`
        # behind it was broken. The French Advance has `fx.e6` the same way.
        tokens = tokenize_pages([page_of("18 Rax.d1 Kxh8 19 fx.e6 and x.y ")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Raxd1", "Kxh8", "fxe6"]

    def test_a_j_ending_an_ellipsis_is_its_last_dot(self):
        # Grivas page 16, "salvation: 21..J!h8 22 lLlf5": the scan reads the
        # third dot as `J`, eight times in the book. Left there, `J♖h8` is no
        # move and the whole alternative was played without Black's 21st.
        tokens = tokenize_pages([page_of("salvation: 21..JRh8 22 Nf5 and 5 .. Jba1 ")])

        assert [t.text for t in tokens if t.kind in ("move", "move_number")][:3] == [
            "21...", "Rh8", "22"
        ]

    def test_rs_behind_a_restored_symbol_is_f5(self):
        # Grivas page 16, "24 ♘f5 ♕b2+ 25 ♔d1": the layer has `♘rs` once
        # the knight is restored. Behind the letter `N` the `rs` was a word,
        # the knight's move was lost and `♔d1` was played as White's 24th.
        tokens = tokenize_pages([page_of("23 Rxf6 Qb4 24 \u2658rs \u2655b2+ 25 Kd1 Mrs ")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "Rxf6", "Qb4", "Nf5", "Qb2+", "Kd1"
        ]

    def test_n_behind_a_piece_is_f1(self):
        # Grivas page 22, "33 ♖af1 ♕e6": the layer has `♖an`, the `fl` of f1
        # read as one `n`. The move was lost and the game ran a move behind
        # the book to its end. Not a word ending in n: "an", "Then".
        tokens = tokenize_pages([page_of("33 Ran Qe6 34 b4 24 Rn Qe7 Then an ")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "Raf1", "Qe6", "b4", "Rf1", "Qe7"
        ]

    def test_a_seven_read_as_a_question_mark_behind_a_piece(self):
        # Grivas page 24, "17 ♕f6 ♗e7 18 ♕h6": the scan has `♗e?`, five
        # times in the book and every one e7. A piece and a file with no
        # rank is no move, and a `?` cannot comment on half a square.
        tokens = tokenize_pages([page_of("17 Qf6 Be? 18 Qh6 Be? ! e4? ")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Qf6", "Be7", "Qh6", "Be7", "e4"]

    def test_ink_left_in_front_of_a_restored_symbol(self):
        # Grivas page 25, "7 ♗g5!? ♗b4! 8 ♗d3 h6 9 ♗xf6": the glyph pass
        # writes the bishop after its own ink, `1L♗b4`. A restored symbol is
        # a piece the page prints there, so what is welded to its left is
        # the rest of that symbol; read as a word, both moves were lost.
        tokens = tokenize_pages([page_of("7 \u2657g5!? 1L\u2657b4! 8 \u2657d3 h6 9 \n1L\u2657xf6 gxf6 ")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "Bg5", "Bb4", "Bd3", "h6", "Bxf6", "gxf6"
        ]

    def test_n_behind_a_wreck_is_f1(self):
        # Grivas page 23, "20...♔f6! 21 ♖f1": the scan has `21 :n`, the rook
        # left as its wreck and f1 as one `n`. Not a word: "21 an" stays.
        tokens = tokenize_pages([page_of("20 ... Kf6! 21 :n \nA sad square, 22 an ")])

        move = next(t for t in tokens if t.kind == "move" and t.text == "f1")
        assert move.lost_symbol == ":"
        assert "21" in [t.text.strip() for t in tokens if t.kind == "move_number"]
        assert [t.text for t in tokens if t.kind == "move"] == ["Kf6", "f1"]

    def test_a_one_read_as_t_behind_a_wreck(self):
        # Grivas page 24, "13 a4 bxa4 14 ♖e1 ♗d6": the scan has `.:r.et`,
        # the 1 of e1 read as a t. The move was never a token, so the
        # variation lost a ply and broke on 15 ♕h5. Only behind a mark of a
        # wreck: "at", "et" and "it" are words.
        tokens = tokenize_pages([page_of("13 a4 bxa4 14 .:r.et Bd6 15 Qh5 at it ")])

        move = next(t for t in tokens if t.kind == "move" and t.text == "e1")
        assert move.lost_symbol.endswith(".")
        assert [t.text for t in tokens if t.kind == "move"] == ["a4", "bxa4", "e1", "Bd6", "Qh5"]
        # And the same behind the symbol the glyph pass restored: `♖et`.
        tokens = tokenize_pages([page_of("13 a4 bxa4 14 \u2656et Bd6 15 Qh5 ")])
        assert [t.text for t in tokens if t.kind == "move"] == ["a4", "bxa4", "Re1", "Bd6", "Qh5"]

    def test_a_move_run_into_the_ink_of_the_next(self):
        # Grivas page 25, "24 bxc5 ♗xc5 ... 26 ♕e2 ♗xf5": the scan has
        # `bxc51L♗xc5` and `♕e21L♗xf5`, the bishop's `1L` hard against the
        # move before it. Neither that move nor its bishop was read.
        tokens = tokenize_pages([page_of(
            "23 b4 c5 24 bxc51L\u2657xc5 25 Kh1 Kg8 26 \u2655e21L\u2657xf5 17 \u2656ae11L\u2657e5 "
        )])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "b4", "c5", "bxc5", "Bxc5", "Kh1", "Kg8", "Qe2", "Bxf5", "Rae1", "Be5"
        ]

    def test_a_restored_piece_and_a_rank_behind_its_wreck(self):
        # Page 25, "22 ♕c2 ♔f8": the scan has `<♔8`, the file gone. A symbol
        # the glyph pass restored, behind its own wreck, is a move even with
        # no number of its own in front: Black's reply.
        tokens = tokenize_pages([page_of("22 Qc2 <\u26548 23 b4 ")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Qc2", "K8", "b4"]

    def test_a_small_s_rank_behind_a_restored_piece(self):
        # Grivas page 26, "33 ♖a5 ♗xf4?": the scan has `♖as`. Behind a symbol
        # and a file the `s` is the rank `S` is elsewhere -- a 5, or an 8.
        tokens = tokenize_pages([page_of("33 \u2656as \u2657xf4? as is ")])

        assert [t.text for t in tokens if t.kind == "move"] == ["RaS", "Bxf4"]

    def test_a_restored_symbol_names_the_piece_of_its_wreck(self):
        # Page 26, "46 ♖xa1 ♕xa1+": the layer has `♕fJ/xal`, ink left between
        # the queen and its capture. The queen the glyph pass restored is the
        # piece, whatever the ink behind it.
        tokens = tokenize_pages([page_of("46 Rxa1 \u2655fJ/xa1+ 47 Kh2 ")])

        move = next(t for t in tokens if t.kind == "move" and t.text.startswith("xa1"))
        assert move.lost_piece == "Q"

    def test_a_foreign_character_in_front_of_a_restored_symbol(self):
        # Grivas page 26, "42...♕b6! 43 f4": the layer has `Ϩ♕6`, the file
        # gone and a stray character in its place. A character from no
        # alphabet a book is set in, against a restored symbol, is its ink.
        tokens = tokenize_pages([page_of("42 ... \u03e8\u26556! 43 f4 ")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Q6", "f4"]

    def test_a_pawn_move_and_a_number_both_spelled_with_s(self):
        # Grivas page 26, "49 ♔g1 e5 50 ♖d1 e4": the scan has `es so`, the 5
        # read as s in the square and in the number, the 0 as o. Only where
        # the number is the one due after the last: prose stays prose.
        tokens = tokenize_pages([page_of("49 Kg1 es so Rd1 e4 51 Kf1 and es so Rd1 ")])

        assert [t.text for t in tokens if t.kind == "move"][:4] == ["Kg1", "eS", "Rd1", "e4"]
        assert "50" in [t.text.strip(". ") for t in tokens if t.kind == "move_number"]

    def test_a_colon_between_the_file_and_the_rank(self):
        # Grivas page 14 prints `12 ♕xa8?` and the layer has `'it'xa:8?`: the
        # move matched nothing and `♘c6` behind it was played by White.
        # Behind a piece or a capture only, where nothing else is shaped so.
        tokens = tokenize_pages([page_of("12 Qxa:8? Nc6 13 Nxc8 a:1 e:4 ")])

        assert [t.text for t in tokens if t.kind == "move"] == ["Qxa8", "Nc6", "Nxc8"]

    def test_a_preposition_before_a_number_is_not_a_square(self):
        # Boussole page 65: "Le probleme principal de 5...h6". The `de 5` is
        # shaped exactly like a square whose file and rank the font broke
        # apart, and reading it as one eats the number that announces the
        # move. A rank carrying a dot is a move number, never a square.
        tokens = tokenize_pages([page_of("Le probleme principal de 5...h6 est le roque ")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["5..."]
        assert [t.text for t in tokens if t.kind == "move"] == ["h6"]

    def test_a_word_carried_over_from_the_line_above_swallows_nothing(self):
        # Boussole page 65: "pour Ie cloua-\nge 6.♗g5". The `ge` ending the
        # broken word reads as a square with its file and rank apart, which
        # takes the number of the move behind it — and the comment's whole
        # line with it. Laurent found this one on the annotated page.
        tokens = tokenize_pages([page_of("pour Ie cloua-\nge 6.Bg5, alors ")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["6."]
        assert [t.text for t in tokens if t.kind == "move"] == ["Bg5"]

    def test_the_tail_of_a_word_does_not_swallow_the_number(self):
        # "the move 6.Bg5" ends in a file letter, a space and a rank, so the
        # tolerance would read `e 6` there and eat the number with it —
        # leaving the citation it announced with nothing to hang from. The
        # space is only allowed where the move begins at a word boundary.
        tokens = tokenize_pages([page_of("the move 6.Bg5 is best")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["6."]
        assert [t.text for t in tokens if t.kind == "move"] == ["Bg5"]


class TestMoveNumbers:
    def test_a_dot_is_not_required_to_announce_a_move(self):
        # Batsford, Gambit and Informator print `12 Nb1`, and so does the
        # Grivas book. Requiring the dot left every move of it unannounced, so
        # `strict_numbering` refused the lot: a page whose left column opened
        # `1 e4 c5 2 Nf3` produced no game at all, losing even the pawn moves
        # that need no piece symbol.
        tokens = tokenize_pages([page_of("12 Nb1 Nd7 13 Bd2 Nb4 14 Na4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["12", "13", "14"]
        # The moves are all read. None is scored: a page opening at move 12
        # never said where the game starts, so `position_known` is false and
        # they are kept for their boxes alone.
        result = parse_tokens(tokens)
        assert [m.san for m in result.moves] == ["Nb1", "Nd7", "Bd2", "Nb4", "Na4"]
        assert result.games[0].position_known is False

    def test_an_opening_score_with_no_dots_starts_a_game(self):
        tokens = tokenize_pages([page_of("1 e4 c5 2 Nf3 Nc6 3 d4 cxd4 4 Nxd4")])

        assert [m.san for m in parse_tokens(tokens).moves] == [
            "e4", "c5", "Nf3", "Nc6", "d4", "cxd4", "Nxd4",
        ]

    def test_figures_in_prose_are_not_move_numbers(self):
        # Which is why a bare number counts only when a move follows it
        # directly: this sentence would otherwise announce four of them, and
        # every book is full of such sentences.
        text = "He won 12 games and lost 3 in 1997 at the age of 24 years."

        tokens = tokenize_pages([page_of(text)])

        assert [t for t in tokens if t.kind == "move_number"] == []

    def test_a_bare_number_announces_a_move_whose_rank_is_a_letter(self):
        # Grivas page 21 prints `19 e5!! dxe5`, and the scan reads `19 eS!!
        # dxeS`. The number is only a number where a move follows it, and
        # `eS` was not one: it stayed in the prose ending "...a slow but
        # certain defeat.", so neither move was read at all — no node, no box,
        # nothing for the reader to correct.
        text = "doomed to a slow but certain defeat. 19 eS!! dxeS "

        tokens = tokenize_pages([page_of(text)])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["19"]
        assert [t.text for t in tokens if t.kind == "move"] == ["eS", "dxeS"]

    def test_a_word_after_a_figure_does_not_announce_a_move(self):
        # The letter ranks are what makes this worth guarding: with `l` a
        # rank, "elle" and "ell" are shaped like a pawn move, and a figure in
        # front of any of them would open a score in the middle of a sentence.
        text = "Il en a joue 27 elle-meme, et 14 ella dans 8 ellipses."

        tokens = tokenize_pages([page_of(text)])

        assert [t for t in tokens if t.kind == "move_number"] == []

    def test_the_dotted_forms_still_work(self):
        tokens = tokenize_pages([page_of("1.e4 e5 2. Nf3 Nc6 13...Nb4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == [
            "1.", "2.", "13...",
        ]

    def test_a_number_the_font_broke_in_two_is_read_whole(self):
        # A subset font emits `18` as `1 8`, with a real space between the
        # digits. The leading `1` then carries no dot and announces nothing,
        # so the number was read as 8 — ten moves early, which the variation
        # detector reads as a branch rather than the continuation.
        tokens = tokenize_pages([page_of("1 7 Bd2 Nb4 1 8 Na4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["17", "18"]

    def test_a_number_run_into_its_own_move_still_announces_it(self):
        # The glyph pass gives back one character where the scan had three,
        # and the space beside them goes too: Boussole prints `2.♘f3 ♘c6
        # 3.♗c4` and the scan reads `2.ltJf3 ltJc6 3.i.c4`, which arrives here
        # as `2Nf3 Nc6 3Bc4`. Neither the number nor the move it carries was
        # read, and an opening lost like that takes the whole game with it.
        tokens = tokenize_pages([page_of("1.e4 e5 2Nf3 Nc6 3Bc4 Bc5 ")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["1.", "2", "3"]
        assert [t.text for t in tokens if t.kind == "move"] == [
            "e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5",
        ]

    def test_a_move_growing_out_of_a_word_is_still_not_one(self):
        # What the lookbehind is there for: the tail of a word is not a move,
        # and a digit welded to one does not make it a number either.
        tokens = tokenize_pages([page_of("Sur la case4 le pion est faible ")])

        assert [t for t in tokens if t.kind == "move"] == []

    def test_a_number_does_not_reach_into_the_word_before_it(self):
        # Tolerating a space inside the number let it start on any digit at
        # all, including one ending a word: `Nf6 6 Nc3`, with the knight's
        # symbol unrecovered so that nothing covered `f6`, offered the rank
        # digit and the move number as one — 66, a hundred plies forward, and
        # the game lost from its fifth move. The wreck is a move of its own
        # now, so the same reach is pinned here on the game header the book
        # prints above every score: the year and the first move read as 31.
        tokens = tokenize_pages([page_of("Kotronias-Grivas Athens 1993 1 e4 c5")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["1"]

    def test_a_number_does_not_swallow_the_digit_below_it(self):
        # Only a plain space joins two digits. A line ending on a number sits
        # next to the first digit of the line under it, and joining across
        # that break would invent a number neither line printed.
        tokens = tokenize_pages([page_of("Bd2 Nb4 17\n8 Na4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["8"]

    def test_an_ellipsis_printed_as_bullets_still_announces_black(self):
        # The Grivas book sets `...` as three 2.8pt bullets. Read as the
        # single dot that survives, `15 .••` announces a white move, and the
        # black move that follows is played for white.
        tokens = tokenize_pages([page_of("15 .•• Nb4 16 h4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["15...", "16"]


class TestBrokenTypography:
    def test_a_bulleted_ellipsis_keeps_the_line_on_the_right_side(self):
        # `.••` is the damaging form: the leading dot is a real one, so the
        # number was recognised — as white's third, which rewinds the line to
        # before the move just played and opens a variation on it. Three bare
        # bullets are merely unrecognised, which costs nothing here.
        tokens = tokenize_pages(
            [page_of("1 e4 e5 2 Nf3 Nc6 3 Bb5 3 .•• a6 4 Ba4")]
        )

        moves = parse_tokens(tokens).moves

        # The status and the line matter as much as the reading here: a broken
        # move keeps its san, so comparing san alone would pass either way.
        assert [m.san for m in moves] == [
            "e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4",
        ]
        assert {m.status for m in moves} == {"ok"}
        assert {m.variation_index for m in moves} == {0}

    def test_a_move_inside_a_broken_symbol_is_marked_not_dropped(self):
        # `ll:\c3` is a knight this book's font broke apart. Read from `c3`
        # on it is a legal pawn move — scored ok at full confidence, with a
        # position the book never reached under every move after it. The token
        # is kept, because the board can often name the piece the page lost,
        # but it carries the wreck so that nothing reads it as a pawn move.
        tokens = tokenize_pages([page_of("3 ll:\\c3 i.g7 4 e4 'ii'e8")])
        moves = [t for t in tokens if t.kind == "move"]

        assert [t.text for t in moves] == ["c3", "g7", "e4", "e8"]
        assert [t.lost_symbol for t in moves] == ["ll:\\", "i.", "", "'ii'"]

    def test_a_word_run_into_an_ellipsis_is_not_a_broken_symbol(self):
        # One book's OCR drops the space and prints `jouer...e5`. The dot does
        # carry a letter, and it still announces nothing but an ordinary black
        # move — reading a lost piece into it would refuse the pawn move and
        # then find no piece able to reach the square.
        tokens = tokenize_pages([page_of("Il faut jouer...e5 et non 12 Bxf5")])
        moves = [t for t in tokens if t.kind == "move"]

        assert [(t.text, t.lost_symbol) for t in moves] == [("e5", ""), ("Bxf5", "")]

    def test_the_tap_zone_covers_the_symbol_and_not_only_the_square(self):
        # The wreck is the piece as the book printed it, so it belongs to the
        # move's span: the reader puts its tap zone there.
        tokens = tokenize_pages([page_of("3 i.g7")])
        move = next(t for t in tokens if t.kind == "move")

        assert move.raw == "i.g7"

    def test_a_dot_still_opens_a_move(self):
        # The refusal has to leave the two forms a dot legitimately precedes.
        tokens = tokenize_pages([page_of("1.e4 e5 2. Nf3 Nc6 13...Nb4")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "e4", "e5", "Nf3", "Nc6", "Nb4",
        ]


class _Board:
    """A drawn board, which occupies no characters of the text layer."""

    def __init__(self, at: int, page: int = 1):
        self.page = page
        self.start = self.end = at
        self.rows = tuple(["........"] * 8)
        self.bbox = BBox(100.0, 400.0, 200.0, 200.0)


class TestAPlanIsNotAMove:
    """Markos' plans, which a reader saw marked as moves of the game."""

    def test_a_chain_of_squares_is_a_plan(self):
        # Page 22, "White would have to play g2-g4-g5-g6"; page 29, "a
        # pawn-chain f3-g4-h5". The last squares were played, legal by chance.
        text = "12.Bd3 Qc7 White would have to play g2-g4-g5-g6 first. 13.Qf3 Nd7"
        tokens = tokenize_pages([page_of(text)])

        assert [t.raw for t in tokens if t.kind == "move"] == ["Bd3", "Qc7", "Qf3", "Nd7"]

    def test_two_squares_of_a_chain_on_two_files_are_a_plan(self):
        # Grivas page 16, "the weakness of the pawn-chain g6-h7": a pawn
        # written square to square never changes file without an `x`, so this
        # names two squares and was played as `h7`.
        text = "13 h5 the weakness of the pawn-chain g6-h7. 13...Bf5 14 e2-e4 Nf6"
        tokens = tokenize_pages([page_of(text)])

        assert [t.raw for t in tokens if t.kind == "move"] == ["h5", "Bf5", "e2-e4", "Nf6"]

    def test_a_run_of_one_side_s_moves_each_with_its_ellipsis_is_a_plan(self):
        # Page 26, "he wants to play ...♘g6, ...♘e4 and recapture"; page 39,
        # "intending to play ...♕c7, ...♘d7 and ...0-0-0". One side's moves
        # in a row are a list of intentions, not a line from the position.
        text = "12.Bd3 Qc7 Black intends to play ...Nd7, ...Nb6 and ...0-0-0 here. 13.Qf3 Nd7"
        tokens = tokenize_pages([page_of(text)])

        assert [t.raw for t in tokens if t.kind == "move"] == ["Bd3", "Qc7", "Qf3", "Nd7"]

    def test_a_square_the_prose_names_is_not_a_move(self):
        # Page 56, "his dark-squared bishop, either from b2 or a3": `a3` was
        # played as a move and marked the game's.
        text = "10.b3 Nc6 with his dark-squared bishop, either from b2 or a3. 11.Bb2 e5"
        tokens = tokenize_pages([page_of(text)])

        assert [t.raw for t in tokens if t.kind == "move"] == ["b3", "Nc6", "Bb2", "e5"]

    def test_moves_listed_with_commas_are_a_plan(self):
        # Page 150, "played in succession, Nf3, g2-g3, Bg2"; page 157, "the
        # Torre Attack: 1.d4, 2.Nf3, 3.Bg5"; page 186, "decide between Bf1,
        # b2-b4 or h2-h3". A line of play never puts a comma between moves.
        for text in (
            "10.Bd3 Nc6 White played in succession, Nf3, g2-g3, Bg2 because 11.Qe2 e5",
            "10.Bd3 Nc6 the Torre Attack: 1.d4, 2.Nf3, 3.Bg5 (or the London) 11.Qe2 e5",
            "10.Bd3 Nc6 then decide between Bf1, b2-b4 or h2-h3. 11.Qe2 e5",
        ):
            tokens = tokenize_pages([page_of(text)])
            assert [t.raw for t in tokens if t.kind == "move"] == ["Bd3", "Nc6", "Qe2", "e5"], text

    def test_commas_between_alternatives_or_a_move_and_its_reply_are_kept(self):
        for text, kept in (
            ("10.Bd3 Nc6 White can play 11.Qe2, 11.Nf3 or 11.h3 here.", ["Qe2", "Nf3", "h3"]),
            ("1. e4, e5; 2. Nf3, Nc6", ["e4", "e5", "Nf3", "Nc6"]),
        ):
            tokens = tokenize_pages([page_of(text)])
            assert [t.raw for t in tokens if t.kind == "move"][-len(kept):] == kept, text

    def test_a_move_and_its_reply_across_a_comma_are_a_line(self):
        # Sakaev page 279, "On 19.♖fe1, 19...♘xg3 20.hxg3 ♘b6 is also good".
        text = "19.Rae1 Nxg3 On 19.Rfe1, 19...Nxg3 20.hxg3 Nb6 is also good."
        tokens = tokenize_pages([page_of(text)])

        assert [t.raw for t in tokens if t.kind == "move"][-4:] == ["Rfe1", "Nxg3", "hxg3", "Nb6"]

    def test_a_numbered_move_after_an_intention_is_the_line_resuming(self):
        # Sakaev page 122, "If 19...♕c7, with the idea of ...b7-b6, 20.♘c4
        # ♗e8 21.♘b6": the comma closes the idea, and the line goes on.
        text = "19.c5 b5 If 19...Qc7, with the idea of ...b7-b6, 20.Nc4 Be8 21.Nb6"
        tokens = tokenize_pages([page_of(text)])

        assert [t.raw for t in tokens if t.kind == "move"][-3:] == ["Nc4", "Be8", "Nb6"]

    def test_a_single_move_the_prose_announces_is_still_a_move(self):
        text = "12.Bd3 Qc7 Black threatens ...Nd7 here. 13.Qf3"
        tokens = tokenize_pages([page_of(text)])

        assert [t.raw for t in tokens if t.kind == "move"] == ["Bd3", "Qc7", "Nd7", "Qf3"]


class TestTheSideToMoveBesideTheBoard:
    def test_a_black_triangle_at_the_board_s_corner_is_black_to_move(self):
        # Markos prints ▼ (Wingdings3 `q`) at the top right of a board, and
        # the text layer hands it over after the prose that follows the board.
        text = "A typical position. 14.Bh3 "
        page = page_of(text)
        corner = BBox(305.0, 590.0, 10.0, 10.0)
        page.chars[-1] = Char(char="", bbox=corner, font="Wingdings3", size=10.0)
        tokens = tokenize_pages([page], diagrams=[_Board(0)])

        (diagram,) = [t for t in tokens if t.kind == "diagram"]
        assert diagram.to_move == "b"


class TestANumberSeparatedFromItsMove:
    """The move number a board or a scanner took away.

    `parse` refuses a move no number announced, and a move number is only
    recognised by the dot or the move behind it. Take either away and the move
    is placed as a citation, into a variation — so the main line stops
    recording where it stands, and the moves that resume it a few lines later
    are played on the variation, where they are illegal.
    """

    def test_a_drawn_board_between_the_number_and_its_move(self):
        # Grivas p.17: `... w 7`, a drawn board, then `Bd2 b4`. The board
        # occupies no characters, so the prose simply ends on a bare figure.
        text = "6 a4 Qa5 A dubious move. w 7 Bd2 b4"
        tokens = tokenize_pages([page_of(text)], diagrams=[_Board(text.index(" Bd2"))])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["6", "7"]
        assert parse_tokens(tokens).moves[-1].san == "b4"

    def test_a_figure_ending_prose_anywhere_else_is_a_figure(self):
        # No board, no move behind it: the year stays part of the sentence,
        # as does every page number in the book.
        text = "6 a4 Qa5 Played in Budapest 1994 and never since."
        tokens = tokenize_pages([page_of(text)])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["6"]

    def test_a_figure_before_a_board_with_no_move_after_it_is_a_figure(self):
        text = "6 a4 Qa5 Diagram 7 and the game went on."
        at = text.index(" and")
        tokens = tokenize_pages([page_of(text)], diagrams=[_Board(at)])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["6"]

    def test_the_number_printed_as_letters(self):
        # `11 ... Bd6` opening a page: the scanner reads `ll`, and the running
        # head swallows it. What makes the letters a number is the ellipsis,
        # which announces a black move and can follow nothing else.
        text = "ATTACKING THE UNCASTLED KING 17 ll ... Bd6 12 Bd3"
        tokens = tokenize_pages([page_of(text)])

        numbers = [t for t in tokens if t.kind == "move_number"]
        assert [t.text for t in numbers] == ["11...", "12"]
        assert numbers[0].raw == "ll ..."
        assert [t.text for t in tokens if t.kind == "move"] == ["Bd6", "Bd3"]

    def test_a_word_ending_in_l_is_not_a_number(self):
        # The ellipsis has to follow the letters and nothing else.
        text = "1 e4 It is all ... e5 that matters"
        tokens = tokenize_pages([page_of(text)])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["1"]

    def test_the_letters_and_the_digits_mix(self):
        # The confusion is per character, not per number: Grivas prints
        # `10 ...Nxd4` as `lO ...` and `21 ...f5` as `2l ...`, one character
        # lost out of two either way.
        for raw, read in (("lO ...", "10..."), ("2l ...", "21..."),
                          ("1O ...", "10..."), ("Il ...", "11...")):
            tokens = tokenize_pages([page_of(f"9 Nf3 Practically forced. {raw} Nxd4")])
            numbers = [t.text.strip() for t in tokens if t.kind == "move_number"]
            assert numbers == ["9", read], (raw, numbers)

    def test_the_number_split_by_a_subset_font(self):
        # `11 ...` set in a subset face comes out `1 l ...`, the two figures
        # separated. Read as the letter alone it announces move one, and the
        # citation branches ten moves before the book put it.
        tokens = tokenize_pages([page_of("9 Nf3 was compelled to play 1 l ... Nxd4")])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["9", "11..."]

    def test_a_figure_in_front_of_an_ellipsis_is_left_alone(self):
        # All digits already: whatever kept this from being read as a number,
        # it was not the scanner's alphabet. Reading it here would take every
        # figure standing in front of an ellipsis.
        text = "1 e4 He had won in 1994 ... e5 was still to come"
        tokens = tokenize_pages([page_of(text)])

        assert [t.text for t in tokens if t.kind == "move_number"] == ["1"]

    def test_letters_that_read_as_no_move_number_are_letters(self):
        # `O ...` reads as move zero and `lOO ...` as move one hundred: the
        # first is no move at all, and neither is what the letters were.
        for raw in ("O ...", "OO ..."):
            tokens = tokenize_pages([page_of(f"9 Nf3 and so {raw} Nxd4")])
            assert [t.text for t in tokens if t.kind == "move_number"] == ["9"]


class TestTwoMovesRunTogether:
    """A restored symbol takes the space beside it, and welds two moves.

    `16 ♗a2 ♗c7` arrives as `16♗a2♗c7`: the pattern refuses the first move
    because the second runs into it, and then refuses the second because a
    word is already running. Neither is read, and Boussole page 65 loses
    White's sixteenth and Black's — after which the game is two plies behind
    the page to the end of the game.
    """

    def test_both_moves_are_read(self):
        moves = [t for t in tokenize_pages([page_of("15.Qf3 c6 16Ba2Bc7 17.Nf5")])
                 if t.kind == "move"]

        assert [t.text for t in moves] == ["Qf3", "c6", "Ba2", "Bc7", "Nf5"]

    def test_the_number_welded_in_front_still_stands_on_its_own(self):
        numbers = [t for t in tokenize_pages([page_of("15.Qf3 c6 16Ba2Bc7")])
                   if t.kind == "move_number"]

        assert [t.text for t in numbers] == ["15.", "16"]

    def test_only_a_move_may_run_into_a_move(self):
        # The lookahead this relaxes is what stops a move from being read out
        # of the middle of a word, and it is only given up for a piece letter
        # with a square behind it. A capital that begins anything else still
        # refuses the move in front of it.
        moves = [t for t in tokenize_pages([page_of("1.e4 Ra1Zurich 1993")])
                 if t.kind == "move"]

        assert [t.text for t in moves] == ["e4"]


class TestABracketNothingCloses:
    """A scan prints a `(` the book never had, and `parse` trusts a bracket.

    Boussole page 65 opens one in the middle of the word "obliges"; nothing
    closes it, and everything below — the game's own score included — is read
    as one enormous variation, with every rule of the numbering suspended
    inside it.
    """

    def kinds(self, text: str) -> list[str]:
        return [t.kind for t in tokenize_pages([page_of(text)])
                if t.kind in ("var_open", "var_close")]

    def test_an_open_nothing_closes_is_dropped(self):
        assert self.kinds("1.e4 (t de renoncer par 2.Nf3 e5 1-0") == []

    def test_a_bracket_the_book_closed_is_kept(self):
        assert self.kinds("1.e4 (1.d4 d5) e5 1-0") == ["var_open", "var_close"]

    def test_a_game_is_as_far_as_a_bracket_reaches(self):
        # The stray `)` of the second game must not pair with the invented `(`
        # of the first: balancing the whole book instead of each game lets the
        # invention survive. The stray `)` itself is left where it is — it
        # closes nothing, and `parse` ignores one that arrives at the top of
        # the stack.
        assert self.kinds("1.e4 (t de renoncer 1-0 1.d4 d5) 0-1") == ["var_close"]


class TestABraceIsABracket:
    """Grivas sets a variation inside a variation in braces.

    Page 14: "11 ♕xf7+? ♔h6 12 ♘f3 ♖f8! {12...♗xb2? 13 g4!! ♕a5+ 14 ♘d2 c3
    15 g5+!} 13 0-0-0 ♗xb2+ 14 ♔c2 ♕f6!)". Read as prose, `12...` was sent
    to a neighbouring line of the same bracket and `13 0-0-0` stayed inside
    the braces: seven moves broke.
    """

    def kinds(self, text: str) -> list[str]:
        return [t.kind for t in tokenize_pages([page_of(text)])
                if t.kind in ("var_open", "var_close")]

    def test_braces_open_and_close_a_variation(self):
        assert self.kinds("1.e4 e5 (1...c5 2.Nf3 {2.c3 d5} 2...d6) 2.Nf3 1-0") == [
            "var_open", "var_open", "var_close", "var_close",
        ]

    def test_a_brace_after_a_label_closes_nothing(self):
        # A scan reads the label's `)` as a brace: "b} 16 ... ♖g8!?", the
        # Killer Dutch page 183.
        assert self.kinds("1.e4 e5\na} 2.Nf3 Nc6\nb} 2.Bc4 Bc5 1-0") == []


class TestALabelIsNotACloseBracket:
    """`a)` and `b)` label the alternatives a book lists under one move.

    "19...Bxe5 20 Nxe5, and now: a) 20...Qxe5 ... b) 20...dxe5" — the label's
    bracket closes nothing, and read as a variation close it pops the aside
    those very lines belong to. Grivas page 21 played both lists on the
    game's board; Sakaev prints the same shape with capitals on pages 45
    and 48.
    """

    def kinds(self, text: str) -> list[str]:
        return [t.kind for t in tokenize_pages([page_of(text)])
                if t.kind in ("var_open", "var_close")]

    def test_a_lettered_label_closes_nothing(self):
        assert self.kinds("1.e4 e5\na) 2.Nf3 Nc6\nb) 2.Bc4 Bc5 1-0") == []

    def test_a_capital_label_closes_nothing(self):
        # Sakaev sets its lists with capitals and an en space in front.
        assert self.kinds("1.e4 e5\n\u2002A)\u2002 2.Nf3 Nc6 1-0") == []

    def test_a_numbered_label_closes_nothing(self):
        # Sakaev page 86 goes one level down: "B1) After 26.\u2656xb7".
        assert self.kinds("1.e4 e5 and now:\n\u2002B1)\u2002 2.Nf3 Nc6 1-0") == []

    def test_a_label_two_levels_down_is_neither_a_bracket_nor_a_move(self):
        # And one more: "B21) on 30.\u2655h4 \u2656h5" \u2014 `B21` is shaped like a bishop
        # whose file a scanner read as a digit.
        tokens = tokenize_pages([page_of("1.e4 e5\n\u2002B21)\u2002 2.Nf3 Nc6 1-0")])

        assert [t.text for t in tokens if t.kind in ("move", "var_open", "var_close")] == [
            "e4", "e5", "Nf3", "Nc6",
        ]

    def test_a_variation_ending_in_a_move_still_closes(self):
        # What the lookbehind must not reach: a variation ends in a digit, a
        # check or an annotation, never in one letter with a space in front.
        assert self.kinds("1.e4 (1.d4 d5 2.c4) e5 1-0") == ["var_open", "var_close"]
        assert self.kinds("1.e4 (1.d4 Nf6!) e5 1-0") == ["var_open", "var_close"]


class TestAFileTheScannerReadAsADigit:
    """`20.♗g5+` off SuperAttaquant's scan as `20.♗25+`.

    A piece and two digits is not a move in any notation, so the first digit
    stands where the file belongs. The token is emitted with the box the page
    gave it and `parse` asks the board which file it was.
    """

    def test_the_piece_and_two_digits_are_a_move(self):
        tokens = tokenize_pages([page_of("19.d7+ Kd8 20.B25+ f6 21.Rxd1")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "d7+", "Kd8", "B25+", "f6", "Rxd1",
        ]

    def test_a_digit_running_on_into_the_next_number_is_left_alone(self):
        # `♗f4 12.♘bd2` comes off as `♗412♘bd2`, a different mangling that
        # nothing here can take apart.
        tokens = tokenize_pages([page_of("11.Qd3 B412Nbd2 Be7")])

        assert not [t for t in tokens if t.kind == "move" and t.text.startswith("B4")]

    def test_the_move_carries_the_box_of_what_was_printed(self):
        tokens = tokenize_pages([page_of("20.B25+ f6")])

        move = next(t for t in tokens if t.text == "B25+")
        assert move.bbox is not None and move.raw == "B25+"


class TestAFileThatLeftNoCharacter:
    """`28.♔g1` off the same scan as `28.♔1`.

    The piece and the rank are all the page still has. That is a shape prose
    makes as well, so the move number in front of it is the whole licence for
    reading it: there, and only there, a move is due.
    """

    def test_a_piece_and_a_rank_a_number_announced_are_a_move(self):
        tokens = tokenize_pages([page_of("27.Qf3 Rd8 28.K1 Rd2+")])

        assert [t.text for t in tokens if t.kind == "move"] == [
            "Qf3", "Rd8", "K1", "Rd2+",
        ]

    def test_the_same_shape_in_prose_is_not_a_move(self):
        # Nothing announces it, and a piece and a rank is a fragment of
        # anything: an exercise number, a diagram's caption, a bare rank the
        # scanner left behind a symbol it destroyed.
        tokens = tokenize_pages([page_of("le Cavalier N4 et la Tour R3 sont")])

        assert [t.text for t in tokens if t.kind == "move"] == []

    def test_the_check_mark_stays_on_the_move(self):
        tokens = tokenize_pages([page_of("30.B3+ Kh8")])

        assert [t.text for t in tokens if t.kind == "move"] == ["B3+", "Kh8"]


class TestTheMoveANumberAnnouncedAndTheScanDestroyed:
    """`16.d5!` off SuperAttaquant's page as `16.45!`.

    The move matches nothing, the run is too short to be kept as prose, and
    the move is gone from every count — not a token, not a node, not a box.
    The digits are kept on the number so `parse` can ask the board which move
    ended on the rank they still name.
    """

    def test_the_digits_are_kept_on_the_number(self):
        tokens = tokenize_pages([page_of("16.45! Bxc3 17.Red1 exd5")])

        number = next(t for t in tokens if t.kind == "move_number")
        assert number.text == "16." and number.lost_move == "45"

    def test_the_paragraph_the_digits_open_keeps_everything_but_them(self):
        tokens = tokenize_pages([page_of("15.exf7+ Kh8 16.6 Le pion e6 assure la suite")])

        number = [t for t in tokens if t.kind == "move_number"][-1]
        assert number.text == "16." and number.lost_move == "6"
        assert [t for t in tokens if t.kind == "text"][0].text.startswith("Le pion")

    def test_a_number_printed_hard_against_another_one_goes_with_it(self):
        tokens = tokenize_pages([page_of("20...2.27 Short prefere rendre la piece")])

        numbers = [t for t in tokens if t.kind == "move_number"]
        assert [(t.text, t.lost_move) for t in numbers] == [("20...", "2.27")]

    def test_nothing_is_kept_where_a_move_does_follow(self):
        # `29.♖g7+!` as `29.8 g7+!`: the promise is kept and the digit in
        # front of the move is the wreck of its own symbol, not a lost move.
        tokens = tokenize_pages([page_of("28.Rf1 Rc8 29.8 g7+! Kh8")])

        assert all(not t.lost_move for t in tokens if t.kind == "move_number")

    def test_a_figure_a_space_away_is_not_the_wreck_of_this_move(self):
        tokens = tokenize_pages([page_of("34. 8xf8+ Qxf8 35.Qxf8")])

        assert all(not t.lost_move for t in tokens if t.kind == "move_number")
