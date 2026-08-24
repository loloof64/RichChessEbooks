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
