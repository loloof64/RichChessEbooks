# What I have to do next

Written 2026-08-22, revised 2026-08-29 (eleventh session, second half).
`main` is at `5d15114`, 362 tests green. Every figure was measured locally on
the corpus.

> **Laurent, mid-session: "il faudrait encore améliorer, en priorité ->
> super attaquant -> tactics. Beaucoup trop peu de coups et lignes non
> détecté(e)s."** What follows is that work. **SuperAttaquant 107 -> 129
> clean and `unscored` 106 -> 56**; Tactics did not move, and the reason is
> written down below.
>
> - `88ffd05` **a promotion written with no equals sign.** `=Q` is one way of
>   writing the piece a pawn promoted to; the figurine straight after the
>   square is the other, and it is the one this book uses -- `33.dxe8♕+`,
>   `42.c8♕`, `29.exf8♕#`. With no `=` to find, none of those was a token at
>   all. Only on the promotion ranks and only where no square follows the
>   piece, so `16♗a2♗c7` -- two moves run together by a lost space -- is
>   refused by either guard alone. 107 -> **109**.
> - `5615b33` **the heading a book prints *under* the board.** `c8b345d` reads
>   a heading above a board as opening the game the board belongs to; Markos
>   prints it that way. SuperAttaquant prints it the other way round every
>   time -- the position, then "Anderssen - Zukertort / Barmen, 1869", then
>   the score -- so seven of its boards corrected a game they had nothing to
>   do with. Only the very next token is asked. **And a heading may carry
>   initials** ("Ki. Georgiev", "J.C. Fernandez", "I. Zaitsev", three of
>   sixteen), which the name pattern refused outright; that half is worth as
>   much as the other. 109 -> **125**, `contradicted` 31 -> 14.
> - `12b46a4` **a board's unexplained squares are named together.** A stray is
>   a square no cluster of the picture explains, and one is enough for `decode`
>   to refuse the whole board. `name_the_strays` read them one at a time --
>   which can never settle a board carrying two, because with the second still
>   unexplained the board does not decode at all and no reading of the first
>   can stand. Two of SuperAttaquant's boards are like that; both come out
>   **exactly right** when the strays are tried jointly, checked square by
>   square against a picture of each. `unscored` 106 -> **56**; `clean` does
>   not move, because what those 50 moves now have is a position and not yet a
>   sound line.
> - `bc6dc4e` **a wreck the book spells, when a number takes its dots back.**
>   A symbol's wreck can reach back over the dots of the move number in front
>   of it and the number is given them back; what is left was then tested for
>   being a wreck by its punctuation alone. This scanner writes the queen `W`,
>   a plain capital with no mark of any kind, so every `21...Wb7` lost its
>   queen and `b7` was read as a pawn move to the seventh rank. The book's own
>   spelling answers where the punctuation cannot. 125 -> **129**.
> - `5d15114` **a body that covers most of its own square is shading.**
>   Measured over every board of the corpus: Grivas' 1194 bodies reach 0.53 at
>   the very most, SuperAttaquant's 0.50, Boussole's 0.52 -- against Tactics,
>   where 103 of 382 pass 0.6 and the worst reaches 0.83. It halves what
>   stands between Tactics and its boards (152 squares no cluster explains
>   down to 113) and is **a no-op on `clean` everywhere**. Shipped for the
>   measurement and the next attempt, not for a gain.
>
> **Why Tactics still reads none of its nine boards.** Its dark squares are
> shaded with a fifty-percent dither, and `5d15114` now keeps that out of the
> bodies. What is left is the pieces themselves: the board is a stored image
> **190 pixels wide**, so a square is 23.75 pixels and a piece some 19, and at
> that size the same piece clusters into two or three groups. 113 of its 576
> squares are singletons, `diagrams.settle` returns no table, and every board
> is refused. **Measured and refused: `MERGE_DISTANCE` 0.10** -- it gives
> Tactics 192 candidate tables where 0.06 gives none, but `_best_table`
> refuses all 192 (they are all wrong) and SuperAttaquant collapses 129 ->
> 21. **Measured and refused: the ink threshold taken from the board's paper**
> (the median over one colour of each square's own median, times
> `_INK_SHARE`), which the ninth session had measured and left unshipped: it
> does not change Tactics at all and costs SuperAttaquant 129 -> **28**,
> because that book's dark squares are hatched and the colour-median lands
> below its white pieces' outlines. What is needed is a signature that
> survives 24 pixels to a square, not another threshold.
>
> **Measured and refused a second time: reading the page's blocks in column
> order.** Re-measured after the seeding fixes, since the first measurement
> predated them: SuperAttaquant no longer loses anything, and it now costs
> **Grivas 577 -> 569** on page 16 alone. 2794 against 2806. See the note
> below and `perpage.py`.
>
> **Measured and refused: two digits as a move whose piece *and* file both
> came off as digits** (`20...♗g7` as `20...2.27`). Licensed on the wreck in
> front of them rather than on a bare move number -- a much narrower rule than
> the one the ninth session refused -- and it still **does not fire on the
> case it was written for**, because `_WRECK_RUN` admits no digits and so
> never finds `2.`. It costs Grivas 27. Admitting digits to `_WRECK_RUN` is
> the change that would be needed and its blast radius is the whole corpus.
>
> **Measured and refused: a move number printed hard against another one is
> not one.** SuperAttaquant 129 -> 122 and Boussole `unscored` 82 -> 101.
> Narrowed to a black number in front (the `20...2.` shape), it is an exact
> no-op -- the second number goes but the `27` behind it is still no move.
>
> **Where the corpus stands: Sakaev 1274, Grivas 577, Markos 380, Boussole
> 283, Tactics 163, SuperAttaquant 129 = 2806.**
>
> **What is worth doing next on SuperAttaquant, in order.** Its 610 moves
> break down as 129 clean, 286 cascade, 56 unscored, 43 below a break, 39
> drifted, 20 first breaks. `games.py` prints it game by game and that is the
> instrument to use: **only 20 breaks, but four games die on their own first
> move.**
>
> 1. **g7 (p202, 42 of 44 broken) and g10 (p204, 38 of 39).** Both are seeded
>    by a board that is read correctly and both die on the first move printed
>    after it. g7: the book prints `16.d5!` and the scan gives `16.45`, so the
>    first move read is Black's `♗xc3`, played as White's. g10: the book
>    prints `20...♗g7` and the scan gives `20...2.27`, so Black's twentieth is
>    lost and `21.d4` is played with Black to move. **80 moves on two lost
>    moves**, and the parser already has the shape of the answer in
>    `_settle_lost_file` and in the seeding block's "the board is believed over
>    the number".
> 2. **g1 is 51 unscored moves the range cannot reach** -- page 198 opens at
>    move 20 of a game whose position was printed on 197. The window's edge,
>    not a defect; SuperAttaquant's ceiling is about 559, not 610.
> 3. **g12 (p206, 36 of 50) and g13 (p207, 29 of 48)** are the next two.
> 4. **Tactics' boards** need a signature that survives 24 pixels to a square.
>
> **The eleventh session, 2026-08-29: 2718 -> 2784, three commits, all of it
> on Grivas, and all of it in front of the parser.** Nothing was pushed. The
> annotated pages in `~/Documents/Echecs/rce_apercus/` were redrawn at each
> commit -- `apercus.py` in the scratchpad does all 21 in one run, over each
> book's whole-game range, keeping the names stable so a redraw is a
> comparison.
>
> The scratchpad was rebuilt from the tenth session's, which survived; the
> venv is copied rather than remade, and the pipeline is imported with
> `PYTHONPATH=.../pipeline` (the editable install's `.pth` was gone). The
> rebuilt corpus reproduced 2718 exactly before a line changed.
>
> - `94ad80d` **the last character of a five-character symbol.** A printed
>   figurine arrives in a scan's layer as several characters and only the
>   first is inside the glyph's own box, so `_swallow_leftovers` takes what
>   follows up to a bound -- and that bound was three where Grivas' mappings
>   are five: `tt::l` for a knight, `'ili>` for a king. The last one survived
>   and stood in front of the square, making `♘lxg3` and `♔>xf7`, which are
>   not moves, so the token died and the line under it with it. Four is the
>   run those mappings reach; a fifth is never taken on any book, and 4 and 5
>   measure identically. Grivas 512 -> **547**, `first_breaks` 62 -> 53.
> - `b81d4fd` **the move number a wreck hid.** A bare number -- the dotless
>   form Batsford and Gambit print -- counts only where a move follows it
>   directly, and on a scan whose glyph pass failed what follows is the ink
>   the scanner made of the symbol. `16lilxd4`, with the space gone the way it
>   goes beside any symbol, left the `16` in the prose above and played the
>   move a ply early for the rest of the game; `21 lilc6` does the same with
>   the space kept. The wreck is the licence and a narrow one: a figure, this
>   book's own spelling of a piece, then a square. Plain spaces only between
>   the two, never a newline -- a figure ending a line would otherwise
>   announce whatever opens the next, which in two columns is not the same
>   paragraph. The spaced form is 8 of the 27. Grivas 547 -> **573**.
> - `9220e24` **a leftover that begins on a file is still a leftover.** The
>   run stopped at the first character a move could carry, so that `♘bd2`
>   would keep its `b`. Grivas' queen ends its ink on `fi`, and `f` is a file:
>   the run stopped dead and left `♕fid5`, `♕fixd7+`, `♕fih4` -- no pattern
>   matches those, so no token was made at all. What ends the run is **the
>   move behind it**, at the shortest length that works: `bd2` is already one
>   so nothing is eaten, `fid5` is not and `d5` is. Where no reading leaves a
>   move the old whitelist answers, so `♖al` for `♖a1` keeps its file. Grivas
>   573 -> **577**, 41 more moves read, diagrams confirming exactly as many as
>   before.
>
> **Measured and refused: reading the page's blocks in column order.** Grivas
> page 27 puts the left column down to "achieving a good position." *and* the
> top four lines of the right column in one block, and hands them over before
> the left column's own continuation -- so eight moves of the score are read
> between black's twelfth and white's thirteenth and the game dies on the
> first of them (`gxf6` after `h6`). Cutting a straddling block at the gutter
> and then reading band by band, left column then right, each in the order the
> stream gave it, is the correct order and **costs 19**: Grivas page 16 8 -> 0
> and SuperAttaquant p205/p206 11 -> 0, against **nothing gained on page 27**,
> whose 40 clean moves do not move and whose break is merely traded for
> another. A per-page instrument (`perpage.py`) is what showed this; a sort by
> `(y, x)` and a sort by column without the stable order inside it are both
> worse. **Do not retry without a per-page comparison in hand.**
>
> **Where the corpus stands: Sakaev 1274, Grivas 577, Markos 380, Boussole
> 283, Tactics 163, SuperAttaquant 107 = 2784.**
>
> **What is worth doing next, in order.**
>
> 1. **Grivas' breaks are now the whole pool**: 51 first breaks dragging 470
>    `cascade` and 423 `below_break`, plus 147 `contradicted`. The tokeniser
>    is nearly done with this book -- `lost.py` reports 25 move numbers with
>    no move behind them and 4 of those are a diagram, the rest one-offs. The
>    clusters left are p18 g5 ply7/8 (six breaks at one ply), p21 g6 ply39
>    (six, all `after='dxe5'` -- the a)/b) list branches from the game's board
>    and not from the line that introduced it), p24 g8 ply22 (five).
> 2. **Grivas' 28 correcting diagrams deserve a reading.** `diag.py` prints
>    how many squares each one differs by: four differ by **two squares** and
>    two by three, which is a line one move out or a board read one piece
>    wrong, not a correction. p24's says the rook is on f1 where the line
>    played `Rc1` (`.l:tcl` for `.l:tfl`), which is the `l`/`1` family seen
>    from the other side. Two of p27's are exact inverses of each other.
> 3. **Tactics' boards** are still the largest unclaimed block (~63 moves),
>    measured and unshipped -- see the ninth session below. Laurent ranks it a
>    later stage.
> 4. **Markos is at 380 of 381** with one break left.

> **The tenth session, 2026-08-29: 2652 -> 2718, five commits, and the two
> books nobody had looked at paid for themselves.** Nothing was pushed.
>
> Every scratchpad from the ninth session was gone, so the first hour rebuilt
> the instruments: `corpus.py` over the six whole-game ranges (which
> `choose_pages.py --whole-games` reproduces to the page), and the six source
> PDFs, which are **inside the `.rce` archives** under
> `~/Documents/Programmation/entrainement_ocr_echecs/rce/` under stable names --
> far easier than globbing the library's Anna's-Archive filenames. The rebuilt
> corpus reproduced 2652 exactly before a line was changed, which is what makes
> the figures below comparable.
>
> - `c8b345d` **a board printed under a heading opens the game it names.** A
>   diagram that disagrees with the line above it is a correction, and
>   everything since the last agreement is blamed on it. Markos page 89 ends the
>   score of Prusikin - Petrik, prints "Dominik Csiba - Jan Markos / Banska
>   Stiavnica 2011", and then the board that game is joined at -- eight sound
>   moves condemned by a game they have nothing to do with. The **year** is what
>   makes the heading safe to read: two names and a dash is also how a book
>   cites a game in passing, and a citation carries no date at the end of the
>   line. Over the corpus the pattern fires **six times and all six are real
>   headings** (Markos p86, p89, p94; Tactics p170, p171; SuperAttaquant p203);
>   five already read `seeds`, so one reading changes. Markos 372 -> **380**,
>   `contradicted` 8 -> 0.
> - `0dfbfeb` **the annotated page now lives in the repository**
>   (`scripts/preview_page.py`), after being rebuilt from scratch in three
>   sessions. `verdict_of` spreads `break_diagnosis` over the page from the same
>   reading, so picture and tally cannot disagree. **`BBox` measures from the
>   bottom-left and MuPDF draws from the top-left**: drawn without that flip
>   every box lands a line from its move, and the first picture of the session
>   accused the pipeline of a defect that was the drawing's own.
> - `d21fdd4` **`a)` is a label, not a close bracket.** A book lists the
>   alternatives to one move under letters -- "and now: a) 20...Qxe5 ... b)
>   20...dxe5" -- and read as a variation close the label pops the aside those
>   lines belong to, so the whole list is played on the game's board and dies on
>   its first move. A lone letter with whitespace in front of it is the label; a
>   variation ends in a digit, a check or an annotation. It holds back 18
>   brackets of 271 over the corpus and **17 of the 18 are a real label** (the
>   other two are OCR noise, and no close either). Sakaev 1254 -> **1274** with
>   `cascade` 20 -> 6, Grivas 474 -> **492**.
> - **Measured and rejected first, in the parser:** a `)` closes nothing
>   wherever no bracket is open at all. Same gain on those two books and
>   **Boussole 282 -> 270** -- a scan's stray `)` is usually a real one the OCR
>   moved. 2686 against the label rule's 2698. **Do not retry in the parser.**
> - `fc28168` **a move number whose digits are not all digits.** The scanner's
>   `l` for `1` is a per-character loss and the rule reading it demanded a
>   number made of nothing else, so `10 ...Nxd4` as `lO ...` and `21 ...f5` as
>   `2l ...` matched nothing. Each citation lost the number announcing it, the
>   move was dropped for want of one, and the analysis under it branched from
>   the game's own board: **eleven breaks on page 24 alone**. Three clauses hold
>   the alphabet to what it is for -- a run of nothing but digits is left alone,
>   a leading zero is refused, and so is a reading above 120. Grivas 492 ->
>   **508**.
> - `5a40aee` **the space a subset font leaves inside that number.** `11 ...`
>   comes out `1 l ...`; matched as the letter alone it announces move one.
>   Grivas 508 -> **512**, `first_breaks` 62.
>
> **Where the corpus stands: Sakaev 1274, Grivas 512, Markos 380, Boussole 282,
> Tactics 163, SuperAttaquant 107 = 2718.**
>
> **What is worth doing next, in order.**
>
> 1. **Grivas is still the pool**: 62 first breaks dragging 477 `cascade` and
>    406 `below_break`, plus 136 `contradicted`. The breaks cluster -- six or
>    seven variations dying at one ply is *one* defect, not seven. The clusters
>    left are p30 g12 (13 breaks over five plies), p24 g8 ply21/22, p18 g4/g5.
>    `breaks.py` groups them; `preview_page.py` shows them.
> 2. **Grivas' `l` for `1` reaches past move numbers**: `Rfl`, `Kfl`, `Nbl`,
>    `Rdfl` for `Rf1`, `Kf1`, `Nb1`, `Rdf1`. Most come out `uncertain` through
>    `_confusable_distance`; `Nbl` and `Rfl` broke outright. Worth measuring as
>    one rule over the whole book.
> 3. **Tactics' boards** are still the single largest unclaimed block (~63
>    moves) and the rule is measured and unshipped -- see the ninth session
>    below. Laurent ranks it a later stage.
> 4. **Markos is at 380 of 381** with one break left.

> **The ninth session, 2026-08-27: the tap zone, which no metric had ever looked
> at.** Laurent, on the annotated pages again: *"attention quand tu repères les
> coups, à bien cerner les boites, les zones — tu captures mal les coups, pas en
> entier"*. He was right, and the cause was `boxes.snap`.
>
> - `cfb0736` **a word's ink was the one run its middle fell in.** The tap zone is
>   moved onto the ink by one scale and one shift per word, and what the layer calls
>   a word is not always what the book printed as one: a scanner that loses the space
>   in `17.gxf6! ♗xf6` reports twelve characters unbroken, the run under the middle
>   covers 33 points of a word the layer spreads over 58, and that scale of **0.57**
>   passed every guard — dragging each box in the word two characters left at half
>   its width. Every run the layer's word stands over is now the word's. **Grivas,
>   a typeset book that goes through the same correction because its figurine font
>   needs glyph recovery, goes from 250 boxes leaving more than half a point of
>   their move's ink outside to one.** Corpus 2643 -> **2652**.
> - The measure worth keeping: for each move token, the ink under the characters it
>   was read from, and how much of it falls outside the box (`audit2.py`). It reads
>   **0 of 430 (Markos), 0 of 261 (Tactics), 0 of 1398 (Sakaev), 1 of 1879
>   (Grivas)** — the three books that never enter `snap` are exact by construction.
>   On the two scans it over-reports: where the layer spreads a word by a third, the
>   token's own characters no longer bound its ink, and the ink of the next word is
>   counted as missing. Judge those two on the page.
> - `apercu_page.py` **draws the zone exactly** now, outside the rectangle rather
>   than two pixels around it. A box padded to look tidy hides the half-character it
>   is out by, which is the whole point of the picture.
>
> **`cd3fb18` — a board picture is read the way the page turns it.** A picture is
> placed by a matrix, and a negative scale in it means the stored rows run the other
> way: Tactics draws **every** board with `d = -145.5` where Grivas draws its with
> `+145.92`. Its nine boards were being read upside down, a position no game can
> reach, so neither `learn` nor `settle` could ever name one of its characters. The
> corpus does not move — the book fails again at the next step, below.
>
> **`4c16c4a` — a move whose file left no character at all.** `28.♔g1` off
> SuperAttaquant's scan as `28.♔1`: `d058f7b`'s shape with the digit gone too, so the
> regular expression needs one `?` and the resolution none. What it needs is a
> licence, because a piece and a rank is what a bare rank makes in prose — and the
> licence is **the move number in front of it**. Twelve on this scan, none on the five
> other books. Corpus unmoved at 2652 and every one of the twelve reads `broken`:
> they all stand inside a line that broke above them. What they are worth today is
> the box, on twelve moves the page held nothing for.
>
> **Measured and reverted: the same rule for a pawn move** (`16.d5!` off the scan as
> `16.45`, the head of 42 dead moves on p202). Two digits after a move number, read
> as a pawn move to that rank, refusing a `)` after it so Boussole's `2.23)` exercise
> labels stay labels. It does not reach `16.45` and it costs **Grivas 474 -> 464** and
> Boussole 25 false tokens with 23 moves cascading under them: corpus 2652 -> **2642**.
> A pawn move names no piece, so the shape has nothing in it but two digits, and that
> is a fragment of far too much. **Do not retry.**
>
> **The instrument this came from, worth writing again: `lost.py`** — for every
> `move_number` token, the characters between it and the next token. Where the next
> token is not a move, whatever stands there is the move the book printed and the
> pipeline lost. **Twenty-one on SuperAttaquant**, in two shapes: nine are the queen's
> wreck `W` (which *is* read, the token beside it carrying it as `lost_symbol`), and
> seven are the piece-and-rank `4c16c4a` now reads. The rest are one-offs.
>
> **The two books never looked at, previewed for the first time (Markos 87/89,
> Tactics 170/172/177):**
>
> - **Markos is the second Sakaev** — 372 of 381 clean, both diagrams read on p89,
>   every box exact. Its only failure is 8 `contra` on p89, and the diagram
>   contradicting them **belongs to the next game** (Csiba–Markos, printed under its
>   own header): the check is comparing a line to a board that is not its own.
> - **Tactics 170-173 are 63 broken moves out of 63, and none of it is the parser's
>   fault.** The book prints a position, `White to move`, and a two-column score from
>   move 1 of the *diagram*, not of the game. Its boards are pictures the diagram
>   reader refuses (`unread: 9` on the whole range), so nothing seeds the game and
>   every move is illegal from the standard start. p177 is the same book with a
>   diagram that *was* seeded: main line all clean, and the 9 breaks are one aside
>   (`If 22.Kxg2 ... 22. ... Qg4+ 23.Kh1 ...`) played from the wrong position.
>   **Reading Tactics' boards is worth ~63 moves and Markos' game-scoped diagram
>   check ~8.**
>
> **Why Tactics' boards do not read, measured to the pixel** (Laurent: *"même si ça
> m'arrange si tu y arrives dès maintenant"* — so this is where it stopped, not why
> it was dropped). The picture holds nine grey levels. On an empty dark square
> **nothing is darker than 0.53**; a piece's ink is **0.27 and darker**. `_ink_below`
> takes the paper as the square's ninetieth percentile, and on a square shaded with a
> 50% dither that percentile is the white half of the dither — so the threshold comes
> out at **0.85**, the shading counts as ink, `binary_fill_holes` closes its
> one-pixel gaps, and **an empty dark square is a body covering 70% of itself**.
> Every piece on a dark square merges with it and nothing clusters: 165 characters
> over 9 boards, ~150 of them singletons.
>
> Two candidates, both measured in the scratchpad (`tsig.py`, `tsig2.py`):
>
> - a flat threshold of 0.40: 106 labels, 93 singletons — the empty squares collapse
>   into one cluster of 345 and the pawns start to group (white pawn ×29, black ×18);
> - **the threshold taken from the board rather than the square** — the median, over
>   the squares of one colour, of each square's own median, times `_INK_SHARE`: **52
>   labels, 39 singletons**, and it is a **no-op on Grivas** (whose hatch is black
>   strokes, so a shaded square's median is still 1.0) and nearly one on
>   SuperAttaquant (0.69 against the shipped 0.72). That is the rule to ship if this
>   is picked up.
>
> What is left after it: **the same sprite still splits by the colour of the square it
> stands on** — f7, g7 and h7 hold three identical black pawns and cluster as 5, 11
> and 2 — because the threshold now differs between a light square and a dark one, so
> the body grows on one and not the other. Nothing was shipped: with 39 singletons
> over 9 boards every board still carries a stray and is refused whole, and `clean`
> does not move.

> **The seventh session, 2026-08-26: 2539 -> 2600, five commits, pushed, and
> SuperAttaquant stopped being a book with no positions in it.** Its figures are
> `unscored` and the games placed, and both moved further than `clean` did:
> **`unscored` 262 -> 100 of 583 moves, games placed 9 -> 12 of 17, boards found
> 13 -> 22, `drifted` 357 -> 278.**
>
> - `aea71f1` **the rank no move has a piece to carry.** SAN writes a rank only to
>   disambiguate, so a move that names no piece can never carry one: `16.2b2` is a
>   bishop, `32.8h3+` a rook, and the digit is the symbol as this scanner drew it.
>   Twenty-three of them, none on any other book. **It scores nothing today** — all
>   twenty-three stood in games nothing had placed — and is right anyway.
> - `b2d804d` **the letter a scanner leaves where a symbol was.** `_WRECK_MARK` knows
>   a wreck by the punctuation in it, and this book's queen has none: it comes out
>   `W`, ninety times over, and `29.♔h1 Wf3+` was a token the pattern refused
>   outright. `glyphs.spellings` already knew what `W` is. Two clauses keep it from
>   becoming the word-tail rule it replaces — no letter may stand in front of the
>   spelling (the `n` Grivas spells its queen with lives inside "positional", worth a
>   **false +58**), and a spelling of nothing but dots is refused whatever the book
>   does with it (`21 ...f5` is not a bishop move). +4.
> - `d9e7f30` **the file a symbol's own box swallowed.** Tesseract divides a word's
>   box evenly among the characters it read, so a symbol — twice a letter's width —
>   reaches half a letter past its ink and takes the move's file: `20.♗b5!!` is
>   written `20.♗5!!`, which is not a move at all. What proves it is a **bare rank**
>   behind the symbol, and the last letter of the ink is the file. Thirty of them, 19
>   on SuperAttaquant and 11 on Boussole. SuperAttaquant 25 -> 46 with `contradicted`
>   10 -> 5, Boussole 264 -> 271.
> - `928e4bc` **the largest, and it is one line of `_rules`.** A rule's reach was the
>   longest stretch any one of its rows held. Page 199 prints two boards whose top
>   rules drift through **nineteen rows** over their own width, where the smear covers
>   eight: the widest row gave 554 pixels of 617, the corner fell 50 pixels outside
>   the side rule's column, and neither board was found. A rule reaches as far as its
>   rows reach *between* them, and only a row touching what is already spanned may
>   widen it — so two boards side by side stay two rules. Boards 13 -> 22, all signed,
>   nine of them seeding a game the book opens in mid-score.
>
> - `3da6054` **a black number that lost one dot of its ellipsis.** `21...♕xb5` comes
>   off the page as `21..♕xb5`, the pattern took one dot or three and nothing between,
>   and the move was read as White's — the line a ply out of step with the page from
>   there, sixty-three moves of one game tallied `drifted`. Nineteen of this book's
>   black numbers and fifteen of Boussole's. A white number carries one dot and only
>   one. The two-dot form is **tight** where the three-dot one tolerates spaces:
>   `9. .i.xg5` is a number and then a bishop's wreck, and a loose second dot eats it.
>   SuperAttaquant 56 -> 64 with `drifted` 357 -> 278; Boussole 271 -> **282**.
>
> **Measured and rejected: a move that names its piece and its rank and no file**
> (`♗5`, `♖3`, `♔1`) read as a move, with the board asked for the file and refusing
> where two of that piece's moves reach the rank. Twenty tokens over two books, three
> of them resolved, **corpus 2581 either way** — and it costs a Boussole game and
> nine drifted moves. The rest of them stand in the pages nothing has placed.

> **The fifth session, 2026-08-25: 2461 -> 2500, four commits, and the book to work
> on is now SuperAttaquant.** Laurent ranked the three books himself — "Sakaev
> parfait, Grivas peut mieux faire, Super Attaquant ultra médiocre" — and named the
> cause before the measurement did: *"la luminosité et l'orientation des pages t'ont
> sûrement perturbé, il ne faut pas hésiter à traiter l'image de chaque page en
> amont"*. He was right about the first half and it was worth 145 moves.
>
> - `56e625b` **the score an aside ran into, taken back.** A weight mark is a
>   measurement and it misses; where the score's own number came out plain,
>   `_place_by_weight` read the rest of the page as analysis on a copy of the game's
>   board. The number printed in the score's weight says so exactly: it names a ply
>   the game has not reached and one of the asides opened since has. Boussole's
>   weighted reading 122 -> 239, Grivas' 350 -> 465, and **Grivas now ships the
>   weighted reading** (465 against the arithmetic's 413). With it, the licence: a
>   move printed hard against the move in front of it is read even where the licence
>   is spent — prose, not the count of the moves, is what ends a licence. Alone that
>   is worth -15; behind the take-back, 45.
> - `170ccbd` **a drawn board that decodes into no position at all.** SuperAttaquant
>   decoded two of eleven boards and both put a king in check on the side the number
>   says is not to move. Seeded on one, a game is worse than unplaced. `_stands`
>   already asks python-chess this when `settle` chooses a table; nothing asked it of
>   the board that seeds a game.
> - `28b2403` **the two things that were stopping that book's boards being read.**
>   Its paper is 0.85 and its white pieces are drawn as an outline reaching only
>   0.60, so under a fixed threshold of 0.5 the outline never closes and the piece
>   has no body at all — its queen signed darker than a pawn. And `INSET` was taking
>   a tenth of the square off each edge, which is where a knight keeps its crown:
>   same failure, same cause. Ten of eleven boards read now, against one. Two rules
>   came out of it: a **learned** table is asked not to break the book (Boussole
>   learns one from two boards of seventeen and loses 55 clean moves to it), and a
>   board **opens** a game the book never placed.
> - `fc67755` **the number a scan welded a lost move onto.** `18.exd5 f5 19.d6`
>   arrives as `exd5` then **519**. Ten on that book.
>
> **SuperAttaquant: `unscored` 452 -> 307 of 522 moves, one board read -> ten, two
> false games gone, four placed.** It is still the worst book in the corpus and it is
> now the one with the most to gain. Grivas 437 -> 465. Corpus 2461 -> **2500**.

> **The fourth session, 2026-08-25: 2378 -> 2461, eleven commits, pushed.** Three
> rounds, each opened by Laurent reading a page and rejecting what he saw. The first
> round is his list of 08-24 evening, and the instrument was the first thing fixed:
>
> - `c9d8295` **the diagram table was a coin toss.** A book that draws its boards has
>   its character table chosen by `_best_table`, and the weight of its score is settled
>   one step later — so the table was judged on a reading the book was about to throw
>   away. Weighted, Grivas' twelve tables come in between 26 and 29 clean with **four
>   tied at the top**; flat, the right one scores 425 and no other beats 65. A
>   three-move change anywhere in the parser reordered that tie and cost 370 moves.
>   Each candidate is now read at both weights. This buys nothing and stops everything
>   else from turning on a coin — **measure nothing on Grivas from before it**.
> - `adf9184` **the wreck that still spells its letter.** `♕'e5+`, `♔>d2`: the
>   classifier read the symbol and wrote the letter back, and the ink around it kept
>   the move from starting there. The letter was thrown away and the board asked.
> - `5482808` **the book's own spelling of each piece, learned for free.** Every symbol
>   the glyph pass restored covers the ink the OCR made of it (`Char.consumed`), so
>   Boussole has spelled `ltJ` = knight 60 times, `i.` = bishop 39, `:` = rook 27, with
>   the answer beside each. `glyphs.spellings` learns the table; the wrecks the pass
>   *failed* on are read off it. **Every miss Laurent listed on Boussole page 65 now
>   reads.** Boussole 162 -> 175.
> - `c89a65a` **an aside keeps the record of itself the game keeps.** Two alternative
>   variations at one number: the second's number is one the first has passed and the
>   game has not reached. Offered to a **broken** move only. Corpus +16.
> **Then Laurent read Boussole page 65 again and rejected the result**, naming two
> things: the two alternative variations at the top right still not read as such, and
> the whole finish of the page read as a variation. Both were real, both had a cause
> upstream of everything above, and four more commits came out of them:
>
> - `5229456` **the symbol written one group to the right of its own ink.** The layer's
>   boxes are half a letter out, so the figurine lands on the **square**: `12.♗xd5 ♘a5?`
>   comes out `12.i.♗d5 ltJ♘5?`, the bishop on the `x` and the knight on the `a`.
>   Repairable because a symbol is never printed twice in a row and `spellings` says
>   which ink is which piece.
> - `3c56a0b` **two moves the lost space welded into one.** `16♗a2♗c7`: neither read.
>   Boussole 181 -> **228**.
> - `8fa44e0` **a bracket the scan invented.** Page 65 opens one inside the word
>   "obliges" and nothing closes it, so every rule of the numbering was switched off
>   below it — which is why no rule could ever have read the two alternatives. Balanced
>   **per game**: per page costs three pages, per book lets a stray `)` keep the
>   invention alive.
> - `716bcd8` **the number an aside caught the game up on.** A one-move citation is at
>   the game's own ply after one move, and took every move to the end of the page.
>
> **Boussole 162 -> 232, page 65 itself 28 -> 50 clean and 24 -> 4 broken**, corpus
> 2407 -> **2461**. Grivas did not move in that round and its three pages look the same
> as they did — see item 5, which is what is left.
>
> **Then two more, from what Laurent said next.**
>
> - `5c0575b` **Boussole does print its score in a weight the ink can show**, against
>   what `weight.py` said. Three things filled the band: the dots of `17...`, which
>   erode away in either weight; the loose box running on into the figurine beside it;
>   and a tenth of the boxes covering a neighbour, which the 2.5th-percentile edges
>   could not survive. Crop to the digits, cut at the next token, take the edges at
>   the quartiles: 223 numbers come out bold and **the marks are right almost move for
>   move** on page 66. The book still refuses the weighted reading, 146 to 232 — see
>   "what the weight still needs" below.
> - `ccffaaf` **the tap zones sit on the ink now.** Laurent: "tes boîtes ne recouvrent
>   pas bien tous les coups". The layer spreads `8.g5` over 22.4 points where the ink
>   covers 17.8. Corrected a word at a time against the rendering. The corpus does not
>   move and that is the point: the box is not a diagnostic, it is what the reader
>   presses.
>
> - `1ea4856` **the game goes on past its result.** "Black resigned due to 27...♔xe7
>   28 ♕f6+": a number continuing the numbering of the game just closed resumes it.
>   `unscored` Grivas 17 -> 0, Boussole 183 -> 168, SuperAttaquant 461 -> 448.

> **The corpus is measured on whole games now, and nothing before `c6616f6` compares
> to anything after it.** Laurent's conclusion from the second session was that a
> twelve-page window cuts a game at each end and the measurement then blames the
> pipeline for what the window removed. `choose_pages.py --whole-games` grows the
> window it picks out to the game boundaries around it, and the corpus runs on those
> ranges: Sakaev 37-50, Grivas 14-31, Boussole 56-70, the other three already whole.
> The same code that scored **1852** on the old windows scores **2115** on these.
>
> **The session then added 263 on top of that, 2115 -> 2378.** Six of the seven fixes
> are a move the book printed and the pipeline never read: a capture whose piece left
> no character (`xc3+`); a diagram falling inside a bracketed variation and taking the
> variation off its own board; a move number the scan ran into its own move (`2Nf3`);
> the stump of a symbol the glyph pass restored (`lNc3`); a word carried over the line
> break swallowing the number behind it (`cloua-ge 6.♗g5`); the long form of a move
> (`...b7-b5`) read as two. **The seventh is the largest**: where the book sets its
> score in its own weight, a move in the analysis weight no longer stands on the game
> even when no number placed it. Sakaev 1039 -> **1251**, Markos 333 -> **372**,
> Boussole 72 -> **146**, Grivas 386 -> **426**.
>
> **Two of the five came from looking at the annotated page, not from any figure** —
> the whole opening of a Boussole game with no box on it, and Laurent naming the
> comment on 5...h6 as the place the line dies. See
> [[laurent-reads-the-annotated-page]]; it has now happened in three sessions running.
>
> **What Laurent asked for on 08-24 evening, and where it stands.** Sakaev: nothing to
> report. Boussole p.65: both his points fixed (`2839694`), the page 2 clean -> **28**.
> Grivas p.17 and p.18: diagnosed, not fixed — and he then read all three pages again
> and named, one by one, the reason each remaining line fails. **That reading is the
> plan for the next session, and it is written out below as "What Laurent found on the
> three pages".** It reorders everything: the largest lever is no longer the asides but
> **the wreck of the symbol, which knows which piece it is and is thrown away.**

**Where this stands, in a paragraph.** A book prints its positions either as characters
of a diagram font (`diagrams.py`, done) or as a picture (`pictures.py`, step 1d). The
pictures are cut into 64 squares, clustered over the whole book, and handed to the
parser as eight rows of eight invented characters; what a character means is named by
the book's own games (`diagrams.learn`) or by the boards themselves (`diagrams.settle`).
Grivas reads all 30 of its boards, SuperAttaquant 4 of 11, Boussole and Tactics none.
The score itself is placed by the weight the book sets it in where the type marks it
(`parse.weight_marks_the_line`) and by arithmetic where it does not.

## How this work is done

**The whole pipeline runs locally in about eighty seconds for all six books**, glyph
classifier included, and reproduces a Colab run to the unit. The classifier is a
scikit-learn pickle with scikit-image HOG features; there is no deep-learning stack.

```bash
cd /tmp/scratch && uv venv .venv
uv pip install --python .venv/bin/python pymupdf chess pytest pillow numpy scipy \
    scikit-image "scikit-learn==1.6.1"      # 1.6.1 is what the model was trained on
                                            # scipy is step 1d, the drawn boards
PYTHONPATH=<repo>/pipeline .venv/bin/python -c '
from rce_pipeline import pipeline
r = pipeline.run("<book>.pdf", work_dir="/tmp/w", first_page=17, last_page=28,
                 glyph_model="<classifier>.zip", write_artefacts=False)
print(r.report())'
```

Colab is for confirming a pushed commit and for the cells that draw images — sections
4b and 8, the only things that cannot be looked at from here. It opens from the badge
in `README.md`, which loads the notebook from `main` itself, so reloading the tab is
the whole update of the notebook — but **Runtime → Restart session, then Run all** is
what updates the *code*: the clone is re-fetched by section 2 and a live kernel keeps
whatever it already imported. Section 2 prints `/!\ STALE` when that has happened. A
session's edits stay in the session.

**The annotated page is the instrument Laurent reads, and it lives outside the repo**:
`~/Documents/Echecs/rce_apercus/apercu_page.py <Book> <pdf page>` writes
`<Book>_p<n>.png` beside itself — the page rendered at 3x with every move's box drawn
in the colour of its verdict and a legend under it. Keep the previous state beside it
(`*_0825b.png` and so on) so the two can be compared. Its `BOOKS` table is a copy of
`corpus.py`'s and has to be kept in step. Four sessions running, the thing that found
the defect was this picture and not a figure.

**And the boxes themselves are worth looking at.** Since `ccffaaf` a scan's tap zones
are snapped onto the ink; a crop with the boxes drawn on it is how that was found and
how it was checked — the scratchpad's `boxes2.py`, a clip rectangle in PDF points and
a zoom of 14 for one line.

**A board can be looked at from here, and this is what the day turned on.** The
notebook's image cells are not the only way: write a PNG and open it. A contact sheet
— one row per cluster, each row the squares that fell in it, the greyscale cell beside
the body the signature is taken from — answers in one glance what a week of histograms
could not. `_signatures` and `_signature` are the two functions to spy on; both take
the cell, and appending `(cell, body)` to a list in call order gives an array parallel
to the signatures. The scripts are in the session scratchpad, not the repository:
`sheet.py` (all clusters, small), `big.py` (a few clusters, large, with bodies),
`side.py` / `inset.py` (a constant swept, boards located once because a scan costs a
rendering pass).

## Where the numbers stand

`clean` is **the figure to compare**. It counts the `ok` moves with nothing against
them: no break above, no diagram below contradicting them, and — since `deae505` —
no disagreement between the line's own count and the numbers the book prints beside
it. Never compare an `ok`, and **never compare anything to a figure from before
`deae505`**: the third exclusion took 42 moves off the corpus that had been counted
since the beginning, and it took most of SuperAttaquant's.

**And the pages are the ones `--whole-games` picks** (`c6616f6`): a range that cuts a
game at either end blames the pipeline for what the window removed. Three of the six
moved, so **nothing measured before `c6616f6` compares to anything measured after it**.

| Book | pages | moves | clean | drifted | cascade | contr | unscored | placed | weight | what it is |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sakaev | 37-50 | 1298 | **1254** | 0 | 7 | 0 | 0 | 10/10 | span | Unicode figurines, 22 diagrams in the text layer |
| Markos | 85-96 | 381 | **372** | 0 | 0 | 8 | 0 | 7/7 | span | figurine font + 25 framed diagrams, all read |
| Grivas | 14-31 | 1795 | **465** | 644 | 435 | 120 | 0 | 13/13 | ink, taken | drawn symbols, and 45 drawn boards all read |
| Tactics | 170-181 | 255 | **163** | 74 | 4 | 0 | 0 | 6/6 | span | the only letters book, `en` at 92% |
| Boussole | 56-70 | 931 | **282** | 348 | 70 | 0 | 82 | 26/31 | ink, refused | loose OCR boxes, 604 glyphs recovered |
| SuperAttaquant | 198-209 | 591 | **107** | 278 | 60 | 33 | 100 | 12/17 | none | a scan; 22 boards found by their frames |

Total **2643** at `HEAD`. On these same ranges `3da6054` scores 2600, `1b9e9a8` — the end of the sixth
session — scores 2539, `2e46d43` scores 2378, `3f55c6b` scores 2115, and on the old
windows it scored 1852. `weight` is where the book's own marking of its game score
came from: `span` is the text layer, free; `ink` is the measurement of step 3b, and
`refused` means the book itself judged that reading it made things worse.

**Grivas' 154 → 126 is deliberate and is not a regression** — see `657d099` and item 5.
The twenty-seven fall *below* a break the fix makes visible, and the book's own
diagrams say the reading improved (corrects 26 → 25, confirms 3 → 4). **When `clean`
and a printed position disagree, believe the printed position**; that is the one
exception to the rule at the top of this section, and it took the whole of 08-23 to
earn it.

Where they were on the morning of 08-21: 250, 33, 67, 0, 23, 3. The corpus total,
which only means anything against itself: 1171 on the morning of 08-24, 1322 at the end
of the first session and **1836** at the end of the second. **Nothing before `52a6374`
is comparable to anything after it**, exactly as with `deae505`.

**Grivas' trusted fell on 08-22, and that is the honest direction.** Reading its drawn
boards took its moves from 764 to 850, its `ok` from 272 to 519 and its `broken` from
472 to 294 — and then contradicted 108 of those `ok` moves, which were legal, wrong,
and had nothing standing against them until a diagram printed the position. Checked
before believing it: none of the 25 corrections is one ply away from the board the
parser had reached, so they are drift and not a diagram token landing in the wrong
place. Its `unscored` fell 60 → 13 in the same run: a diagram seeds the game a page
opens in mid-score, so the moves are placed after all.

**`unscored` is not a failure, but on a scan it is usually a board nobody found.**
It counts moves in a game the book never placed — analysis quoted after a result, or a
run of pages opening in mid-score with no diagram to seed it. They are read, they keep
their page and their box so the reader can correct them, they are all `broken`, and
none of them is measured. SuperAttaquant was 461 of them out of 495 and this was
written down as what the book *is*: twelve pages of which one opens a game from move
1. It was half true. Its examples do open in mid-score — and each one prints the
board it opens on, which four sessions of work read at 1, then 10, then 13, and now
**22 of 22**. `unscored` is 113 and 46 of those are one page's window. See `928e4bc`.

## What 08-21 found, in order

| Commit | What it was |
| --- | --- |
| `cd2172f` | prose ends what a move number announced — commentary names squares constantly ("the pawn at d5"), and each is shaped like a move. Except when the prose is the wreck of one (`exdS`, `18Rd2`), which costs Boussole nine real moves without the exception |
| `b88a3dc` | `break_diagnosis`: `broken` split into the lines that died and what followed them, `ok` into what stands clean and what stands below a break. Sakaev's `ok` was 527 with 277 of them below a break |
| `a6f04b2` | the positions a book prints as pictures are **text** — a diagram font, eight rows of eight characters. The font is learned from the book, observations voting as wholes |
| `02cf00e` | a correction counts against the moves above it; the board is found inside its frame; the printed position is looked for on both sides of where the diagram was met; and the piece symbols themselves (`¤c3`) are read, the board deciding which character is which piece |
| `9eeafd3` | the other case of a letter a font hid in the private use area — U+F070 is `p`, so its partner is U+F050 |
| `3f3b94c` | a game the book never placed is read and not scored (`position_known: false`) |
| `9466223` | every book read whole, on the pages `choose_pages.py` picks. Grivas 67 → 133, Boussole 23 → 88, with no code change |
| `9f1e590` | the wreck welded **inside** a move (`♗1g3` read as `B1g3`) is dropped when the board leaves one reading. Grivas 133 → 208 |
| `3a06a3a` | the letters path measured on a book that has some: Tactics 0 → 98 |

**The lesson of the day, twice over: a book was being made to look unreadable by
something already sitting in its text layer.** Markos's diagrams and Markos's piece
symbols were both there, and the pipeline was rendering page images to recover what it
could have read. Before believing a book cannot be scored, look at what its characters
actually are.

## What 08-22 added

| Commit | What it was |
| --- | --- |
| `5ba0208` | the notebook still selected `ChessStrategy_Grivas_1`, the label of the extract `9466223` replaced, so section 4a died on a KeyError and took the eight cells below it |
| `595c978` | **step 1d, `pictures.py`**: the boards a book draws as an image, read without a piece recogniser |
| `a518bf2` | step 1d skipped for want of numpy or scipy said so instead of reporting a book with no diagrams |
| `a62d8f7` | section 8 draws the diagrams too — blue — since a drawn board's box is where the reader will tap |
| `7875ef9` | the board inside a **scan**, found by the frame around it. Boussole 13 boards, SuperAttaquant 11, 13 kinds each |
| `206497b` | **`diagrams.settle`**: the characters named by the boards themselves when no game can teach them. SuperAttaquant reads 4 of its 11, and 25 moves leave its unscored pile |
| `cb57f74` | reaching thirteen kinds by merging the clusters instead of cutting — **reverted the same day**, see item 1 |
| `da979d7` | the revert, with what it measured |
| `da98179` | **the guard**: reading no diagram is one of the candidates `_best_table` scores, so a table legality allowed but the book reads worse with is refused. Corpus unmoved |

`pictures.py` is the same bargain as the diagram font, made on pixels. It never says
what a square holds, only that two squares hold the same thing: a board is cut into
sixty-four, each square reduced to a signature, the signatures clustered over the whole
book, and each cluster called an invented character. From there the board is eight rows
of eight characters, exactly what a diagram font hands over, and `diagrams.learn` names
the characters from the positions the book's own moves reach.

What makes a square comparable, all of it measured on Grivas' thirty boards:

- **The shading is thrown away, not compared.** A hatch has a phase, so two empty dark
  squares are not the same bitmap — raw comparison gave 189 clusters where 13 exist.
  What is compared is the *body*: the ink, holes filled, thin structures opened away.
  An empty square is then empty whatever its colour, and a piece on a dark square is
  the same as on a light one, which is what lets one diagram teach both.
- **The body is centred and scaled** before comparison, or the same rook three pixels
  over clusters twice.
- **The reduction is by area, not by whole pixels.** This is what a small board needs:
  bins of one and two pixels move a body's ink around as it shifts.
- **The board is found from its frame, not from its ink.** A speck of dirt above one
  Grivas board was taken for its edge and put every rank a third of a square out.
- **The clustering is held to the thirteen things a board can carry.** A fourteenth
  cluster is a second reading of a piece already found. This alone took Grivas from
  seventeen unreadable boards to none.

Grivas: 30 boards, **all read** — 4 confirm the line, 25 correct it, 1 seeds a game.

`diagrams.settle` (`206497b`) names the characters when no game can. The characters
come in **twins** — a piece is the same drawing in both colours, only the fill changes
— so the shape half of the signature pairs them and the search falls from twelve
characters onto twelve pieces (479 million) to six twins onto six kinds, 720, each
either way round. Legality then cuts 1440 tables to 12 on Grivas and 22 on
SuperAttaquant, and the book breaks the tie: each table is read with, and the one
leaving the most moves standing clean wins. **Checked where the answer is known**:
forced onto Grivas, it returns the table `learn` taught, character for character.

Two things worth keeping from it. The pairing is a **matching**, not a poll of each
character's own nearest — three characters can point in a chain and leave all three
unpaired, which gave SuperAttaquant five twins out of six and no readable board. And
`python-chess` does not count promotions: a piece beyond the ones a side begins with
was made from a pawn, and it only had eight, so three rooks beside eight pawns never
happened. Eight rooks alone are legal, six promotions; it is the two counts together
that catch it.

## What 08-24 added

| Commit | What it was |
| --- | --- |
| `20f42d9` | a square the font breaks in two (`♖ac 1`), the tolerance the move number already had. Only at a word boundary — see the dead ends |
| `530d15a` | **the second of two alternatives cited together** stands beside the first instead of being played on the game. Neutral alone; it is what unblocks the next one |
| `068c545` | **the move a number announced beside one it could not read** is read for its box instead of dropped. 790 move tokens over the corpus had no node at all — the ones beside a failure, which are the ones the reader most needs to tap |
| `52a6374` | **a correction is an agreement**, like the confirmation beside it. Found by Laurent on the annotated page: the game's first eleven moves were marked contradicted while the diagram beside them confirmed them |
| `dd0c345` | a first rank printed as a letter (`♘cl`, `Khl`), plus the guard that no move is followed by an apostrophe — with `l` a rank, the French `de l'échiquier` is shaped exactly like `Re1` |
| `7495fe0` | **the line a move belongs to, read from the weight it is set in.** The three typeset books mark their score in bold and none was being read. +514 clean |
| `3c5709f` | the same fact measured from the ink where the text layer lost it, and refused by the book itself on the one scan that shows it |

**`52a6374`, and why it is the one to understand.** A diagram that *corrects* re-seeds
the line — the book says where the pieces are, the next number puts them back, and
everything below is played on the printed board. So blame for a later disagreement
cannot reach above that point; `agreed_at` was cleared there instead of moved, and the
second correcting diagram of a game walked the parent chain to the root. Grivas-Siebrecht
opens `1 d4 d5 2 c4 c6 3 ♘f3 ♘f6 4 ♘c3 dxc4 5 e3 b5 6 a4` from the initial position with
the book's own board confirming it, and all eleven were marked wrong. Contradicted 316 →
194 over the corpus. It changes no reading at all: Sakaev 657 → 682, Markos 209 → 238,
Grivas 156 → 224.

### The fonts, and what they gave

Laurent, reading the annotated page: the main line is set **bolder** than the asides.
He is right, and it answers by typographic fact the question `_place_by_number` guesses
at by arithmetic. Two commits, `7495fe0` and `3c5709f`, and they are the largest gain
this project has had.

**The cheap half was the whole gain.** All three typeset books mark it in their text
layer and none of them was being read — `NICHelveticaUtf-8-Bold`, `AGaramondPro-Bold`,
`TimesNewRoman,Bold`, MuPDF flag bit 4. `extract._is_bold` reads the span (the flag, or
the face's name: a subsetted face can arrive without the flag), `tokenize._weight_of`
carries it per token by majority of the characters holding ink, and
`parse.weight_marks_the_line` decides per book whether the typography marks anything —
both weights present among the **move numbers**, neither of them a handful. Every scan
fails that test and keeps the arithmetic untouched.

| book | clean | the diagrams' verdict |
| --- | --- | --- |
| Sakaev | 681 -> **1039** | corrects 10 -> **0**, confirms 10 -> 20 |
| Markos | 238 -> **333** | corrects 10 -> 2, confirms 13 -> 21 |
| Tactics | 102 -> **163** | its boards are unread either way |

The diagrams are the arbiter and they moved with it: on Sakaev every one of the twenty
positions the book prints now agrees with the line, where half of them used to correct
it.

**What the rule sees that the number cannot.** Analysis printed at exactly the half-move
the game is waiting for — *"The main continuations here are the classical 6...e6 and the
trendy 6...♘bd7"*, right after `6.♗g5`. It agrees with the position on every count and
is not the continuation. `_place_by_number` is silent there by construction.

**Two things it needed beyond the weight itself**, both found by measuring a regression:
a variation of more than one move must not be restarted at each number it prints
(Tactics 102 -> 57 without it), and a number in the score's weight must end the analysis
**before** the test for a new game — a game only ever opens at the top of the stack, so
without it a puzzle book whose analysis runs to the foot of the page reads a hundred
pages as one game (57 -> 163).

**The ink half works and does not pay** (`weight.py`, step 3b — run only where the text
layer gave nothing, because it costs a rendering of every page). Render at 4x grey,
threshold the token's box at 128, erode twice with a 3×3, report
`eroded.sum() / dark.sum()`. **One erosion does not separate, two do.** Only the move
numbers: a figurine is dense, so the moves overlap. The threshold is learned per book —
Otsu's split, then the test that says whether there were two groups at all: the heavier
group's floor at twice the lighter group's ceiling, taken at the 2.5th and 97.5th
percentiles so that one bad box cannot speak for a group.

| book | n | split | lighter ceiling | heavier floor | |
| --- | --- | --- | --- | --- | --- |
| Grivas | 660 | 0.062 | 0.021 | 0.108 | separated, a factor of five |
| Boussole | 450 | — | 0.076 | 0.077 | one unbroken band, refused |
| SuperAttaquant | 427 | — | 0.055 | 0.056 | the same, refused |

Two of the three scans mark nothing this can see; the third marks it perfectly and
loses by it. That is the whole finding on the ink, and it is worth keeping: the
measurement is sound, and it is the token that fails.

And on Grivas **the marks are right** — page 17's forty-five numbers are marked exactly
as the book prints them, score and citation alike — while reading them scores 224 ->
182. What the measurement cannot see is the score's own numbers **going missing**: the
OCR runs them into the prose around them (`16lilxd4`, "White has a large advantage. 17"),
so on three pages of twelve there is no bold number left to resume the score with and
the aside never closes. p17 +15, p18 -20, p19 -15, p24 -17.

So the book judges the reading, as it already judges a table of diagram characters:
parse both ways, keep the better. **Made on the finished reading, after the diagrams
have been read** — made before, it compares two readings neither of which is the one
that ships, and it kept the wrong one, which is how this was found.

**Measured and rejected on the way there — do not retry.** An *additive* rule, where the
weight only adds the one case the arithmetic is blind to and everything else stays with
`_place_by_number`: Sakaev 1010, Markos 289, Tactics 90, Grivas 191. Worse than the
replacing rule on all three typeset books and worse than doing nothing on two.

### The number a board and a scanner took away

**Fixed, `3f55c6b`, and Laurent found it by naming the moves**: on p.17 `8 ♘a2 e6
9 ♗xc4` is the continuation of the main line, and two of the three were red. A move
number is only recognised by the dot or the move behind it; take either away and the
move is placed as a citation, into a variation, so the main line stops recording where
it stands and everything that resumes it is played on the variation.

- **A drawn board between the number and its move**: `... w 7`, a board, `♗d2 b4`. A
  drawn board occupies no characters, so the prose ends on a bare figure — which the
  token pattern refuses, and must, or every page number and every year is a move
  number. Read only where all three stand together: prose ending in a figure, a
  diagram, a move.
- **The number printed as letters**: `11 ... ♗d6` opening a page, where the scanner
  reads `ll` and the running head swallows it. The **ellipsis** is what makes the
  letters a number — it announces a black move and can follow nothing else. This was
  the residue this file listed as beyond any number-based rule.

**Neither pays alone.** The first scores **-7**: it makes twelve moves right, and they
fall between two diagrams of which the second still disagrees — `11...♗d6` was the
missing move all along. With both, the span closes: Grivas 224 -> **240**, corpus
1836 -> **1852**, corrects 25 -> 24, confirms 4 -> 5. Grivas–Siebrecht has no red move
left on p.17.

**Measured and rejected before these, on the same defect — do not retry**: joining the
span across a drawn board (156 -> 149), and letting a citation that lands where the
main line is waiting *be* the main line (156 -> 134).

**The scripts are all in `~/Documents/Echecs/rce_apercus/`**, outside the repository with
the rest of the measurement artefacts: `corpus.py` (the six books and the one figure to
compare), `apercu_page.py` (the annotated page, `<book> <page>`, writing beside itself),
`bold.py` (what the text layer marks, and where it disagrees with the placement),
`encre.py` (the ink weight of every move number, as a histogram), `ink.py` (the original
spike, one page), `game.py` (one game's moves, parents and verdicts), `letters.py` (every
token whose rank is a letter). They need `PYTHONPATH=<repo>/pipeline` and the venv of the
section above.

## What 08-24 added, third session

| Commit | What it was |
| --- | --- |
| `c6616f6` | **the corpus is measured on whole games**, not on a window cut where it falls. `choose_pages.py --whole-games` |
| `8f54da3` | a capture whose piece left **no character at all** — `xc3+`, and no SAN begins with a capture |
| `72c7be0` | a diagram falling **inside a bracketed variation** no longer takes the variation off its own board |
| `47e7d0c` | a bare number announces a move whose **rank the scanner printed as a letter** (`19 eS!! dxeS`) |
| `18e9bf1` | the move number a **restored symbol ran into** (`2.ltJf3` -> `2Nf3`), given back |
| `053c93e` | the **stump** of a symbol the glyph pass restored (`lNc3`) no longer refuses the move |
| `3bbab0a` | a **word carried over the line break** (`cloua-\nge 6.♗g5`) no longer swallows the number behind it, and a wrecked square is repaired with its lost symbol |
| `f1b2f3a` | **a move in the analysis weight never stands on the game**, even with no number to place it — and `...b7-b5` is one move, not two |
| `2839694` | **a bracket a scan invented**: the game picking up again closes one, and a bracket branches after the move it follows when its number says so |
| `2e46d43` | a square whose rank carries a dot is a move number — the French `de 5...h6` was eating one |

### The brackets a scan invents, and what they cost (Laurent, on the page again)

Boussole page 65 comments on 5...h6 in a passage the OCR opens a `(` in the middle of,
and nothing closes it on the page. Everything below was read inside that bracket:
the variation of the first column (`7.♗xf6 ♕xf6 8.♘d5`) branched a move too early and
so read for the wrong colour, and the **score of the game** — `6.h3 0-0 7.g4!`, printed
bold two lines below — placed inside a variation four plies away. Laurent named both.

Two rules, and the numbering carries both. **The game picking up again closes a
bracket**: placement stays suspended below a bracket except for a number naming the ply
the *game* awaits, which the bracket's own line cannot be waiting for or the test above
would have continued it. **And a bracket branches after the move it follows when its
first number says so** — "6...h6, and White is already obliged (7.♗xf6 ♕xf6)" continues
the move rather than replacing it. Boussole 146 -> **162** with `2e46d43`, page 65 itself 16 clean ->
**28**, no book lower.

### The weight, again, and the largest single gain of the session

`_place_by_weight` reads the weight of the **number** and sends what follows to the
line it names. A move arriving with no number of its own never reaches it: its licence
is a prose ellipsis, and it is played on the game. Sakaev page 37 — "the move ...b7-b5
will be least useful", a move the game played three plies earlier — is illegal there,
and **93 moves stood under it**, half of them on the next page. The weight says it is
not the score before the board is asked. Sakaev 1156 -> **1251**, Markos 333 -> **372**
with its cascade at zero, page 37 itself 31 clean -> **60 of 61**.

**Grivas loses 7 to it and not through its own reading — traced, and the trace is the
useful part.** It ships the *unweighted* parse (the ink weight is refused: weighted
scores 29 clean against plain's 426), so this rule never fires on the reading that
ships. What it changes is the **first pass**, and the first pass is what teaches the
diagram table through `diagrams.learn`. A table learned from the weighted first pass
took the plain reading to 433; the one learned from the plain first pass takes it to
426. Measured both ways, and moving the first pass to `weighted=False` does not
recover it either.

**So the table is taught by a reading nobody ships, and which one it is matters by
seven moves.** The fix is the one `_best_table` already embodies one level down: learn
a table from *each* first pass, read the book with each, and keep the better — four
finished readings scored on `clean`, at the cost of two more parses on a marked book.
Not done, measured only as the diagnosis above.

### Whole games, and what the window was costing

A twelve-page window opens in the middle of a game and closes in the middle of
another. The first has no printed starting position, so every move of it is read and
none is scored; the last loses the diagrams that would have judged it. `_whole_games`
grows the range outwards to the boundaries: back to where the interrupted game begins,
forward to the page before the next one starts, six pages at most either way so that a
puzzle book — which has no boundary within reach — keeps the window it was given.

Whether a page opens a game or continues one is read from **what stands above its
first move 1**: a page that opens a game prints nothing there, a page that continues
one prints a score. Over the six books that count is 23, 18 and 33 above the line and
0, 0 and 0 below it. Sakaev 38-49 -> 37-50, Grivas 17-28 -> **14-31**, Boussole 56-67
-> 56-70.

Grivas' left edge was worse than unscored, and only the widening showed it: page 17
opens 72% of the way down with `Grivas - Siebrecht`, and the tail of page 16's game
above it was being read as a game of its own from the initial position.

### The five defects, and where they came from

**Two came from the annotated page.** Boussole page 65 prints `1.e4 e5 2.♘f3 ♘c6
3.♗c4 ♗c5 4.♘c3 ♘f6` and **six of those moves had no box at all** — the glyph pass
gives back one character where the scan had three (`ltJ` -> `N`), and the space or the
dot beside them goes too, so `2.♘f3` reaches the tokeniser as `2Nf3` and a move growing
out of a digit is refused like a move growing out of a word. A digit is not a word:
the number is cut out and stands as its own token (`18e9bf1`, Boussole 72 -> 121). The
same restoration leaves the rest of the ink standing in front of the letter — `lNc3`,
`ltNxe5`, `iQd8` — and that was refused too, 93 moves on Boussole and 11 on Grivas
(`053c93e`, 121 -> 141, and Grivas' cascade 640 -> 514).

**And Laurent named the third**, reading the same page: the comment on 5...h6 dies at
`6.♗g5`, and it dies because the hyphenated `cloua-\nge` before it reads as a square
with its file and rank apart — the tolerance `Rac 1` needs — and takes the move number
with it (`3bbab0a`).

**The bracket and the diagram** (`72c7be0`) is the one worth understanding. A diagram
is a figure the text flows around, so it can fall in the middle of a bracketed
variation, and the position it prints is the game's and not the variation's. Seeding on
it there collapses the whole stack back onto the main line while the variation is still
running. Grivas page 20 ends `(13...♘xg3` and a diagram; page 21 opens with the rest of
that bracket, `14 fxg3 ♗xe5 15 ♘xe5!! ♗xd1 16 ♘xf7!`, read on the game and dead from
its first move. **The page had not one clean move on it and now has 68.** Seven such
diagrams in the corpus, one of them this.

**Measured and rejected, this session:**

- **`!` and `?` as part of a wreck.** A Grivas knight is drawn with a `!` in it
  (`lL!g4`, `tL!eS`, 22 of them) and is read as a pawn move — legal, wrong, at full
  confidence. Reading them right scores Grivas 435 -> **422**, and two of its diagrams
  turn from confirming the line to correcting it. The reading is right and the book
  says the line is worse for it; do not retry without knowing why.
- **Spelling the move out exactly in the bare number's lookahead.** It is a loose
  two-character test on purpose — that is what lets it see past the wreck of a symbol,
  `12 ♔h1` arriving as `12 Kfi>h1`. Being exact cost three numbers on page 27 alone.

## What Laurent found on the three pages (2026-08-24 evening) — DONE, 2026-08-25

He read `Boussole p.65`, `Grivas p.17` and `Grivas p.18` and named the cause of each
remaining failure. **Four of the five items are shipped; one was measured and does not
exist on the current text layer.** What each turned out to be:

### 1. The wreck of a symbol knows which piece it was — DONE (`adf9184`, `5482808`)

Two halves, and the second is the one that pays.

**The wreck that still spells its letter** (`adf9184`). Grivas prints `♕'e5+`, `♔>d2`,
`♖f.f7+`: the classifier read the symbol and wrote its letter back, and only the ink
left around it kept the move from beginning on the letter. `_piece_named_by` reads it.
Alone it is +15 moves read and `clean` unmoved — a piece the board deduced is never
`ok` in the first place, so the figure cannot see it.

**The book's own spelling, learned from the glyph pass itself** (`5482808`). This is
the one the plan asked for and it needs no legality at all. Every symbol the pass
*restored* covers the ink the OCR made of it, kept on the character as `Char.consumed`
— so the book has already spelled each of its pieces several hundred times over with
the answer beside it. `glyphs.spellings` votes on that: Boussole says `ltJ` is a knight
60 times and never anything else, `i.` a bishop 39, `:` a rook 27, `<it` a king, `'ii`
a queen. Kept at three occurrences and four fifths of the vote, which is what drops
Grivas' `'ili` (11 queens and 10 kings).

**The free check the plan asked for passes**: forced onto the wrecks legality settles
on its own, the two agree 29 times and differ 3. Where the spelling's piece has no
legal move at all — 21 cases, all on lines already adrift — the five pieces are asked
exactly as before.

**And the wreck stopped giving up its whole self to the move number.** `9.i.xg5` runs
back over the `.` of `9.`, and a wreck overlapping the token before it was dropped
whole rather than trimmed. Every miss Laurent listed on Boussole page 65 now reads:
9.Bxg5, 10.Nd5, 14...Kf8, and the moves under them. Boussole 162 -> **175**.

### 2. A wreck separated from its square by a space — MEASURED, does not exist

`10.ltJ d5`: the current text layer prints `10.ltJd5`, with no space, and reads it.
Allowing one space was measured on both scans before it was written: **7 hits on
Boussole and 2 on Grivas, and every one of them is the previous move** — `3.BgS cS`,
`14.gS hxgS`, `23.eS dxeS`. The thing standing one space before a square is the move
before it. Do not build this.

### 3. Two alternative variations at the same number — DONE (`c89a65a`)

Every level keeps the record the game keeps (`_Level.history`), and a move **already
broken** where it stands is offered the aside's record along with the game's, through
`_place_a_citation`. +16 on the corpus, no book lower.

**The version Laurent described literally does not pay and was measured**: placing
*every* such number by the aside's history inside `_place_by_number`, before the move
is tried, is **-2** (Boussole 175 -> 173) and fires 39 times over the two scans. The
difference is the entry condition — nothing to lose. Restricting it instead to the
aside's own opening ply makes it fire nowhere at all.

### 4. The main line goes on after the result — DONE (`1ea4856`)

A number that carries on the numbering of the game the result just closed — the ply
after the last one it declared, or the ply its board awaits — resumes that game.
`unscored` Grivas 17 -> **0** (three phantom games gone), Boussole 183 -> 168,
SuperAttaquant 461 -> 448. `clean` is unmoved, which is right: these moves were never
counted and are not counted now. What changed is that they hang from the game they
belong to, with a position under them.

Guarding it on `line_sound` was measured and is worse for the purpose: Grivas p.17's
game has broken by move 27, so the four half-moves Laurent named would stay unplaced.
They are read on the drifted board instead, and the drift detector says so.

### 6. What the weight still needs — the next piece, and it is named

`5c0575b` measured Boussole's weight and the marks are good. The reading is still
refused, 146 against 232, and the reason is not the marks:

- **`_place_by_weight` sends every plain number into an aside and only a bold number
  brings the score back.** Each number the OCR destroys — "par 1" for "par 18." —
  strands the score there for the rest of the page. Already written down for Grivas
  in `pipeline.run`; now measured on a second book.
- **The moves split too, and reading them makes it worse.** Cropping a move to what is
  not its piece symbol — the same trick as the number's digits — separates cleanly:
  Boussole at 0.078, Grivas at 0.085. But marking them turns on the rule of `f1b2f3a`
  ("a move in the analysis weight does not stand on the game"), and against marks that
  are merely good the score is broken up at every miss: Boussole's weighted reading
  falls 146 -> **114** and Grivas' 377 -> **108**. Measured 2026-08-25 and reverted.
  The marks are worth having; the rule that reads them has to tolerate a miss first.

**And this is what Boussole page 65 has left.** `17.♘f5` is the game and `17.b4` is a
citation inside the comment beside it; the numbering has no way to tell them apart —
both are White's seventeenth, and the aside `16...c5` opened is waiting for exactly
that ply. **The type says it and nothing else does.** So the variation Laurent asked
for, `17...b5 18 ♘xg7 ♔xg7 19 ♗xf6+`, is dead on its second move: the game has `b4`
where the book has `♘f5`, so there is no knight on f5 to take on g7.

Three narrower rules were measured against that inversion and all cost more than they
brought: handing the number to the game on every collision (2457 -> 2181), an aside
whose licence is spent giving it up (2254), and a sentence closing a prose aside
(2054) or breaking the tie for it (2338).

### 5. And the printed board settles what nothing else can — STILL OPEN

Unchanged and untouched: when a move stays ambiguous after the wreck table has spoken,
a diagram standing a few plies below knows the answer. Try each candidate, keep the one
that reaches the position the book printed. Grivas p.21's `16...♘g4` is the case.

**Its companion, retried with the new idea and still not paying:** `!` and `?` inside a
wreck (`lL!g4`, 22 of them on Grivas). With the spelling table behind it this is no
longer -13 but **-1** — Grivas 437 -> 436, ok 965 -> **975**, so ten more moves are
read and one clean move is lost. Closer than it has ever been; still not a gain.

> **The sixth session, 2026-08-25 evening: 2506 -> 2539, and SuperAttaquant is a
> different book.** Laurent: *"Super attaquant a encore un ratio très faible ...
> tout en minimisant les régressions pour les autres livres."* Five books were
> checked at every step and not one moved except upwards.
>
> - `da8895f` **the scan was being read below the resolution it is stored in.**
>   SuperAttaquant keeps its pages at 360 dpi and Boussole at 600; `pictures`
>   rendered both at 200, which *aliases the printed halftone* — the screen of a
>   dark square comes out 2 pixels against 4, the width of a white piece's outline,
>   and its phase moves with the square. Three sessions of clustering work were
>   reading an aliased screen. At 300 the board of page 198, typed out by eye,
>   comes back a **perfect bijection**: thirteen kinds in thirteen clusters.
> - `f1e3842` **`£` is an `f` and `¢` is a `c`** wherever one stands in front of a
>   rank digit — 21 on SuperAttaquant, 7 on Boussole, none on the typeset books.
>   `18.exd5 £5 19.d6` was arriving as `exd5` then a move number of **519**.
>   **Boussole 239 -> 264.** With it, `settle` now orders its tables by how many of
>   each piece they put on a board: legality cannot tell a rook from a bishop and
>   nor could the moves, and the book was seeding a permuted position.
> - `e5c2c41` **the one square of a board no cluster explains**, read by the
>   nearest character legality allows there — and kept only where it gives moves a
>   position they did not have, which is what stops Grivas paying seven clean moves
>   for three boards it did not need.
> - `1b9e9a8` **a number that lost its ellipsis**: `24` for `24...`, believed only
>   where the move after the board refuses the side it names.
>
> **SuperAttaquant: `clean` 5 -> 21, `unscored` 452 -> 262 of 543 moves, one board
> read of eleven -> thirteen of thirteen, three placed games -> nine of nineteen.**

> **Eighth session, 2026-08-27: 2600 -> 2643, and SuperAttaquant's largest break was
> an inversion, not a misread move.** Its `clean` is **64 -> 107**, the moves under a
> first break 325 -> 293. The first change alone took it to 89 and 302.
>
> **The annotated pages are current** (`apercu_page.py`, 2026-08-27): the state of the
> 25th is kept beside each as `*_0825e.png`, and **SuperAttaquant p199, p200 and p206
> have been added to the set** — the two fixes and the largest open item are on them.
> p198 shows the inversion undone move by move: `23.♖fa1!?` orange on the game,
> `23.♖a7` purple beside it, `24.♖e7+ ♔d8 25.♕xb4` red, and `23...f4 24.♖1a7! ♘d7`
> green again.
>
> **An aside that loses the move its own number announced looks exactly like the
> score resuming.** Page 198 cites *"auraient mieux fait de penser a donner leur Dame,
> par 21...♕b7 22.c6 ♖xa1!"*. The queen's symbol is destroyed in the scan, so `♕b7`
> arrives as a bare `b7`, is illegal for Black and is never played — and the aside is
> then standing exactly where its own number left it. `resumes` tests a board against
> a number, and that disagreement was made out of nothing: the citation's own `22.` was
> read as the game picking up, **the citation was played as the game score**, and the
> game's own `22.♖xa8 ♕c6 23.♖fa1` was diverted into an aside in its place. The
> citation `23.♖a7 24.♖e7+` then took the main line and broke on White moving twice;
> 54 moves died under it, the largest single break on the book.
>
> The rule is one clause: **the ply straight after the aside's own last number is the
> aside carrying on.** Only that ply — the wider form ("any number while the aside has
> lost its move") costs Boussole two clean moves and gains nothing.
>
> **A file the scanner read as a digit, and the board that names it back.**
> `20.♗g5+ f6` comes off page 200 as `20.♗25+ f6`, and **no notation writes a piece
> and two digits** — so the first of them stands where the file belongs. Nothing on
> the page puts the letter back: this scan wrecks it differently every time (`♘d5` as
> `♘45`, `♗f4` as `♗41`, `♔g2` as `♔22`), so it is not a look-alike of anything and
> no substitution table reaches it. The piece survives, the rank survives, and a
> piece with one legal move to a rank has named its own square.
>
> Eight over the corpus and **every one on this scan** — none on the other five books,
> which is why the shape can be read at all. One settles (`♗25+` -> `♗g5+`, correct
> against the print) and it stood at the head of a game with 54 moves under it:
> **SuperAttaquant 89 -> 107**. The other seven become broken nodes where before they
> were prose — the reader gets a box on each.
>
> **The check mark is the third thing the page still says.** `38.♗g6+` came off as
> `♗26+`, whose only bishop move to rank 6 is a capture giving no check: read without
> the mark it is legal, is played at half confidence, and is not the book's move.
> Honouring it costs no `clean` and removes that reading. This is the same shape item
> E rejected — `♗5`, `♖3`, `♔1` with the board asked for the file — and the reason it
> pays here and not there is that **a bare rank can be a fragment of anything, while a
> piece and two digits can only be a move**.
>
> **And a note on the instrument.** `_ply_awaited` is measured off the seeded board's
> fullmove number, so a diagram-seeded game's arithmetic is sound — but `parse_tokens`
> runs **fourteen times** in one `pipeline.run` (weighted against plain, named against
> read, with and against the diagrams), and a trace that does not say *which* run it
> came from reads as though every number arithmetic were dead. Tag the run.

> **And a third change measured and reverted, with its reason.** The move a number
> announced, destroyed down to its rank — `16.e6` printed `16.6`, `16.d5!` printed
> `16.45`. Ten of them on SuperAttaquant, none on the typeset books, four false ones
> on Boussole (`2.23 )`, an exercise index). `_move_of_the_eaten_ply` is already the
> tool: it takes a rank, tries every legal move to it, and keeps the one the printed
> line carries furthest. On p202's board `d5` carries four plies and the next-best
> carries two — as clean a signal as this book gives.
>
> **It fired nowhere and cost twelve.** Two reasons, both worth keeping:
>
> - **The seeding branch `continue`s before any of it.** p202's `16.45` *is* the
>   number that seeds its game from the printed board, so the placement code below it
>   never runs. That board is the book's own and is trustworthy at exactly that
>   instant, which is when this rule could most be believed — if it is retried, it
>   goes **inside** the seeding branch.
> - **Folding the digits into the number token costs a prose boundary.** Carrying them
>   on the `move_number` (`16.` -> `16.6`) is what lets `parse` see them at all, and it
>   also removes the `text` token that used to end the number's licence: two of p207-8's
>   games merged into one and SuperAttaquant fell 107 -> 95. The digits are the *head of
>   the following prose token* (`'6 Le pion'`), so a `parse`-side test on a text token
>   that begins with one or two digits and stands right after a number keeps the
>   boundary and still sees them.
>
> And it would not have reached the two largest breaks anyway: **g11 is broken at its
> seed**, not by a lost move (see below).

## Where to pick it up — 2026-08-27, in order

**Still SuperAttaquant, and its figures are `unscored` (100 of 583), `drifted` (278)
and the games placed (12 of 17).** `clean` is 64 and says almost nothing about this
book on its own. Grivas has not moved in two sessions and is item F.

**Rebuild the instruments first — a scratchpad does not survive the session.** A
`uv venv` with `pymupdf chess pytest pillow numpy scikit-image "scikit-learn==1.6.1"`,
then `PYTHONPATH=<repo>/pipeline .venv/bin/python`. The probes worth writing again,
each ten to twenty lines: `corpus.py` (the six books in parallel, now with `unscored`
and games-placed columns), `sa_audit.py` (per game: placed or not, status counts,
where it dies), `probe_drift.py` (per game: where drift opens and the five moves
above it), `probe_stream.py` (a page's tokens in order), `probe_boards.py`
(`_framed_boards` per page against the page image), `render.py` + `crop.py` (a page
or a crop as a PNG, then the Read tool — see the memory note, it is how three of this
session's four defects were found).

**A2 (2026-08-27, the new item A). Three of SuperAttaquant's placed games break on
the first move after their own diagram seed, and the board is what is wrong.**
`seeds.py` in the scratchpad prints, per game, the seeded FEN and whether the first
move printed under it plays there for either side:

| Game | page | seed | first move | plays | flipped |
| --- | --- | --- | --- | --- | --- |
| g7 | 202 | move 16 w | `♗xc3` | no | no |
| g11 | 205 | move 12 w | `♕xh7+` | no | no |
| g16 | 209 | move 48 w | `b3` | no | no |
| g12 | 207 | move 12 w | `e5` | **yes** | yes — a coin toss |
| g9 | 203 | move **98** b | `♘e5` | yes | no — the number is `98..` for `28...` |

- **g7 is not the board.** Its seed is right and its first move is right: the book
  prints `16.d5! ♗xc3` and `♗g7xc3` needs the d4 pawn gone, which `16.d5` is exactly
  what does. The lost move is the whole of it — see the reverted change above.
- **g11 is the board.** Its seed puts the black king on h8 with h7 **empty** and a
  black pawn on h6, and the move printed under it is `♕xh7+` from a queen on d2 —
  whose only diagonal reaches **h6**. Either the decode moved that pawn a rank or the
  scan moved the move's; one square decides 39 moves. Look at the page image before
  touching anything ([[look-at-the-squares-as-images]]).
- **g9's number is `98` for `28`.** `_number_stripped_of_a_lost_move` strips a digit
  the scan welded in *front* of a number; nothing repairs a digit **inside** one, and
  here the wrong digit is seeded into the board's own fullmove count.

**A3 (2026-08-27). What page 200 shows now that its line is read.** `20.♗g5+` is
orange on the page and the score runs from it — and the **diagram at the foot of the
page contradicts the whole opening of the line** (10 `contra`, `16.cxd5!?` through
`21.♖xd1 ♗c5`). The moves are read, they are legal, and the board the book printed
says one of them is wrong: that is the instrument working, not failing. Its own
remaining break is `22.♗f4`, printed **`2♗2f4`** — the digit-for-a-file family again,
but with the debris running into the number beside it, which is the one shape
`_FILE_READ_AS_A_DIGIT` deliberately refuses (`♗41` on p202 is the same). Settle A3
against the diagram, not against `clean`.

**A. `drifted`, 278 of 583, is the biggest number on the book.** It fell from 357
when the lost ellipsis was fixed and what is left is not one cause. `probe_drift.py`
ranks it: `g5` 51, `g12` 47, `g7` 41, `g11` 39, `g14` 32, `g3` and `g9` 27 each.
**Take them one at a time and look at the printed page beside the token stream** —
each is a move the book printed and the pipeline never read, and the shape differs.
Two already seen and not yet answered:

- `g3` p199 dies on `20.c3!` where the book prints `20.g3!`. One OCR letter, and
  `c`/`g` is not in `_CONFUSABLE_PAIRS`. **Do not widen that table on one case** —
  count first how many of the 278 turn on a single letter and which letters, then
  decide. `_MAX_REPAIR_COST` is 0.5 for a reason written down at its definition.
- `g9` p203 carries `98..♘e5` for `28...♘e5`: a `2` read as a `9` inside the number
  itself. `_number_stripped_of_a_lost_move` already strips a digit the scan welded
  **in front** of a number; nothing repairs a digit inside one.

**B. The `(D)` marker's board, which now falls inside its own example.** `parse`
starts a *new* game from a diagram met inside a game the book never placed the start
of, and the comment there says why: before this session a board met that way was the
head of the next example. It no longer is — p209 prints `47.c7 ♗f5 (D)` and the board
under it is the same game's, seven moves after it began. That is most of what is left
of `unscored` outside p198. What is needed is a test for "this board is the game
running, not the next one": the diagram's own offset against where the game started,
or the caption printed under it.

**C. `g1`, 46 moves on p198, is the window and not the pipeline.** The page opens
`20...f5!?`, continuing an example that begins on p197. `choose_pages.py
--whole-games` reads whether a page opens a game from what stands above its first
`1.` — and no example in this book ever prints one, so the heuristic cannot see the
boundary. Widening the range breaks every comparison in this file; decide it
deliberately or leave it.

**D. The two boards that decode into nothing** (`unreadable`, 2 of 22), and
SuperAttaquant's `contradicted` 5 -> 33 across the session. The verdict counter did
not move — 11 corrects, 9 seeds, 2 unreadable, before and after every change of the
day — so the rise is moves correctly attributed to a board that was always right.
Worth one look anyway: a board that decodes *wrong* is worse than one not found, and
`_stands` only refuses a position nobody could have reached.

**E. Measured and rejected this session, do not redo it**: `♗5`, `♖3`, `♔1` read as
moves with the board asked for the missing file, refusing where two of that piece's
moves reach the rank. Twenty tokens over two books, three resolved, **corpus 2600
either way**, and it costs a Boussole game and nine drifted moves. The rest of those
tokens stand in pages nothing has placed — it may be worth reopening *after* B.

**F. Grivas has not moved in two sessions** (465, `drifted` 644, `cascade` 435) and
Laurent said so himself on 08-25: "j'ai du mal à percevoir tes progrès". Its `drifted`
is now the largest of any book. The older sections below rank what is under its
breaks; the four largest are all the asides.

**G. Everything below is the older work.**

## Where the older work stands — 2026-08-25, in order

**Everything below this heading is SuperAttaquant, which is where Laurent asked the
effort to go**, minimising regressions elsewhere. Its figure is not `clean` — 7 of
522 — but **`unscored`, 307**, and the games placed, 4 of 16. `boards.py` in the
scratchpad prints both; `clean` alone says nothing about this book.

**A. Recover the move the welded number destroyed.** `519.` keeps the rank of the
move it ate — Black's move to *something*5 — and `fc67755` throws it away after
reading the number. Try every legal move to that rank and keep the one under which
the *next* move is legal too, which is how `_settle_lost_symbol` already works. Ten
occurrences, and each is a line that is a ply short of the page from there on.

**B. The clustering, which is now two named faults and not a fog.** With the board
read by its own paper the contact sheet is legible (`sheet.py`, `check.py` and
`truth.py` in the scratchpad — the last is board 0 of page 198 typed out by eye, and
it scores a run in seconds):

- **the black bishop signs as two things** — ten of its squares are strays at 0.18
  to 0.21 from any cluster, where the widest real cluster is 0.092. The cause is
  visible: on a hatched square the hatch converges beside the piece and survives the
  opening as a lump on its left.
- **and the opening is what does that**, because at `OPENING_RATIO` 0.08 it is a 9x9
  element on a 50-pixel square: it eats the queen's crown and the bishop's mitre and
  leaves a torso, which is why the white bishop clusters with the white king. The
  detail that tells the pieces apart is destroyed on purpose, to remove the hatch.
- **so the hatch has to go some other way.** A median filter (5x5, 7x7, with the
  opening cut to match) is **measured and much worse** — it takes the piece's detail
  with it and strays go from 1 to between 29 and 81. What has not been tried: a
  directional filter along the hatch's own 45 degrees, or estimating the hatch from
  the empty dark squares of the board and subtracting it.

**C. `settle` cannot reach the truth while those two faults stand.** It permutes six
twins onto six kinds; with the bishop split in two and the queens sharing a character
no permutation is right, and the nine candidates it offered were all wrong. Fixing B
is what unblocks it. The tie-break to add if they are still tied: a character
appearing exactly once on every board is a king.

**D. And `INSET` is a band, not a point.** 0.005 and 0.01 both give ten boards on
SuperAttaquant and all 45 on Grivas; 0.02 gives one; 0.00 costs Grivas eleven. What
it is really doing is dropping half a pixel of grid line, and measuring the grid
line's own width per board would say it properly.

## Where the older work stands — 2026-08-25, in order

Laurent read the pages three times over that day and each reading found something no
figure could. **Show him the pages before anything else**, and take the order below.

**A. The rule that reads the weight has to tolerate a miss.** This is the one that
blocks what he asked for last, twice over, and it is the only thing that can:

- Boussole page 65's `17.♘f5` (the game) against `17.b4` (a citation in the comment
  beside it). Both are White's seventeenth and the aside `16...c5` opened is waiting
  for exactly that ply, so the numbering cannot tell them apart — and the variation he
  asked to see completed, `17...b5 18 ♘xg7 ♔xg7 19 ♗xf6+`, dies on its second move
  because the game has `b4` where the book has `♘f5`.
- Boussole page 66, which he named: "la page reprend par la ligne principale (elle est
  en gras et elle continue par 18., complétant le 17...g6 de la page précédente)". The
  page stands at 21 clean and 76 broken.

The marks exist and are good (`5c0575b`); item 6 above has the two reasons the reading
is still refused and the figures for each. **The moves' marks are measured and waiting
too** — Boussole 0.078, Grivas 0.085 — and cost 30 to 270 clean moves the moment they
are turned on, because `f1b2f3a` treats one missed mark as proof the move is analysis.
A rule that asks the position as well as the type is what is missing.

**B. Item 5 above, the printed board as the second arbiter.** Untouched, unblocked, and
the last of Laurent's list of 08-24. Grivas page 21's `16...♘g4` is the case.

**C. Grivas, where nothing moved on 08-25 and he said so**: "j'ai du mal à percevoir
tes progrès". Its three pages read the same as they did that morning. Item 4 below
ranks what is under each of its breaks; the four largest are all the asides.

**D. Everything below**, which is the diagram work and is older.

**1. The scans' boards: the squares have now been looked at, and the diagnosis of
08-23 was wrong.** Naming is solved (`206497b`) and geometry is solved (`7875ef9`).
What is left is that a board carrying **one** character no cluster explains cannot be
read at all — `decode` refuses rather than guess — and on the noisy books almost every
board carries one:

| Book | boards | kinds | strays | boards read |
| --- | --- | --- | --- | --- |
| Grivas | 30 | 13 | 0 | **30** |
| SuperAttaquant | 11 | 13 | 10 | 4 |
| Boussole | 13 | 13 | 48 | 0 |
| Tactics | 9 | 8 | ~20 | 0 |

**What the contact sheets say, and it is not one story but two.** The support histogram
had been read as "the same thing on the board is making more than one cluster", on both
scans. The pictures say otherwise:

- **SuperAttaquant is not over-splitting.** What looked like a duplicated pawn is a
  pawn and a **bishop** — 0.73 of the cell high against 0.87, the same width, and the
  taller one twins with the taller one of the other colour (shape distance 0.007, shade
  0.319: one drawing, two fills). Its thirteen believed clusters are thirteen genuinely
  different things. What it is missing is the **white knight**, which has no cluster at
  all, and six of its ten strays are black knights that did not join the black knight's
  cluster. The knights are the tallest pieces on the board — 0.90 to 0.95 of the cell —
  so `INSET` clips them, and how much it clips depends on where the grid falls.
- **Boussole is over-splitting, and badly.** Its white pawn is **three** clusters
  (16, 7, 6) while its **white queen is none**: every one of its occurrences is a
  singleton, which is why d1 is the worst square on the book. Its pieces are drawn
  crisply — the failure is not the picture.
- The two books therefore fail for different reasons and a single fix for both is
  unlikely.

**Measured today and all worse — the axes, not just the thresholds.**

| What | Result |
| --- | --- |
| `binary_closing` before the fill, to repair a broken outline | SuperAttaquant 10 strays → **139**; the hatch closes into a solid body and the empty cluster falls 458 → 283 |
| `INSET` 0.10 → 0.03, so a tall piece is not clipped | strays fall (super 10 → 4, boussole 48 → 35) and `clean` does not follow: **SuperAttaquant 14 → 13**, everything else level. Grivas is unchanged at 0.03 and breaks at 0.00 |
| average-linkage hierarchical clustering, cut at thirteen | merges **by colour**: black pawn with black rook (121), black bishop with black king and queen (43), white rook with white queen. Grivas comes out identical to the greedy partition |
| `SIGNATURE_SIDE` 10 → 14, 18, 24, to give a crown room | monotonically worse everywhere: boussole 48 → 50 → 75 → 87 strays, super 10 → 11 → 18 → 18, and it even costs Grivas its perfect 0 |

**What that leaves.** A greedy grouping and a hierarchical one fail in opposite
directions on the same signatures, so the limit is the **signature** and not the
algorithm. On Boussole a solid black piece signs as its silhouette twice over — the
shade half of the vector repeats the shape half — and what separates a queen from a
king from a bishop is the top of the piece, one or two cells of a hundred. A finer grid
does not recover it, because the ink varies faster than the drawing does. Something
that weighs *where* a difference falls, or that compares the outline rather than the
filled body, is the next thing to try — but not before item 5, which is untouched and
not blocked on any of this.

**And a warning about the instrument.** SuperAttaquant scores 14 clean out of 488
moves: 436 of them are unscored, because 292 pages open **one** game from move 1. A
change of ±1 there is noise, and it is the book every diagram experiment has been
judged on. Boussole is the scan to work on — 88 clean, ten game starts on its range,
so its own games can teach a table through `learn` instead of `settle` guessing one.

**2. Tactics needs a better picture, or to be left alone.** It draws its boards 190
pixels wide, 24 to a square, where a white piece is a one-pixel outline that breaks:
the holes do not fill and the opening takes the piece away with the hatch. Only 8 kinds
emerge. Rendering the page at 150, 300 and 600 dpi is **measured and worse** — the
publisher stored nothing more than the picture. If the stray work above does not carry
it, leave it: Tactics already measures the letters path, which is its job.

**3. Recall on the scans is partial and unmeasured.** SuperAttaquant prints two boards
on the one page I looked at, and 11 were found over 12 pages. Count what each page
actually prints before tuning anything — `SKEW_TOLERANCE`, `RULE_OVERLAP` and
`SCAN_SQUARE_TOLERANCE` are the three knobs, and all three were set from one page each.

**4. What Grivas has left.** On 14-31: 1730 moves, **433 clean**, 515 under 54 first
   breaks. Ranked by the subtree under each (`audit.py` in the scratchpad), the four
   largest on 2026-08-24 evening are `fxg3` p.30 (116), `Nbd4` p.15 (108), `Qxe5` p.21
   (108) and `fl` p.22 (92) — and the first three are all the same shape: the line
   resumes after a comment on the aside the comment opened, a move or two behind the
   page. That is the asides, and it is where the next session starts. What is still
   its own defect: the wreck welded to the *square* rather than the piece
   (`2 e4lilf6`, black's move swallowed whole), and the knight drawn with a `!` in it
   (see the dead end, which is not the same thing as being unfixable).

**5. DONE (`657d099`). Boussole's breaks, audited 2026-08-23 — and what the audit found
is not about Boussole.** Each break ranked by the subtree under it (`audit.py` in the scratchpad:
first breaks, the moves above, the printed line, and the position the line died on).
Its 26 first breaks fall into three classes:

- **Analysis quoted with no starting position** — 5 of the top 12, all in games marked
  `position_known: false`. Not a failure and not scored; see the note on `unscored`.
- **A rank the scanner printed as a letter.** `dS` for `d5`, `eS`, `cS`, `S.a3` — **40
  of them over Boussole's twelve pages**, 32 on Grivas, 13 on SuperAttaquant. The move
  matches no pattern, is never read, the side to play is wrong from there, and the line
  dies a few plies later on a castling that is suddenly illegal — which is why `O-O`
  appears as the dying move three times over and is not itself the problem.
- **A move number that lost its dot** (`3♘c3`, `4♗g5`, `2♘c♘c6`), which drops the move
  the same way.

**DONE for both ranks (`dd0c345`, 2026-08-24).** The paragraph below is the history of
the fifth rank; the first rank followed it, once the aside defect it was blocked behind
was found — and that defect was neither item 10 nor the numbering, but two alternatives
sharing one number. Grivas 129 → 156.

**The letter rank was implemented, measured twice, and reverted twice** — once on its
own and once on top of item 10's fix, which was expected to unblock it and does not. `parse` already treats
`5`/`S` as a near-free substitution — the pair is in `_CONFUSABLE_PAIRS` — so the whole
change is to let the tokeniser *emit* `dS` and let the position decide. It reads
correctly: Boussole 88 → 93 clean and 28 more moves read, Grivas' `♕aS?!` becomes
`Qa5 uncertain (edit cost 0.5)`, correct against the print. And Grivas falls **140 →
121**, which traces to a single line and to a defect that has nothing to do with ranks
— item 10. Adding `l` and `I` for rank 1 costs Grivas 3 more. Reverted, and worth
re-running the moment item 10 is solved: those two are one piece of work.

**6. One anomaly to confirm or dismiss.** Page 3 of the old Grivas extract reported
   `♗xg5 broken ambiguous: the disambiguating letter is missing (Nfxe4, Ncxe...)` —
   candidates naming a knight to e4 for a move naming a bishop to g5. Either the audit
   pairs printed text with moves loosely, which its own comment says it does, or
   `_settle_ambiguity` is being handed the wrong token.

**7. `uncertain` is live and worth watching.** 20 on Grivas, 6 on Boussole. Each is a
   move the board settled rather than the page: a piece the position named, or a false
   disambiguator dropped. Check a few against the print before trusting them at scale.

**8. Held back deliberately, with its number:** a `>= 3 squares on the line` rule for
   `scan` adds 7 lines on Grivas and none elsewhere. A heuristic where the shipped
   rules are principles. Available if recall falls short again.

**9. Two residues no rule keyed on the number can reach:** `ll ll:\f3`, where the move
   number itself printed as letters; and a comment ending in an ellipsis ("by a later
   ...b7-b5"), which keeps the number's licence alive because `...` is how a black move
   is announced.

**10. A prose citation on the wrong board — fixed, `cc90d5c`, and the biggest single
gain since the pages were chosen.** A book cites an earlier move in the middle of a
sentence, with no bracket and no indent: *"Theory also suggests 4 ...g6 here"*, *"and
7 ♗a4 (Zhang Zhong-Grivas, Elista OL)"*. `_place_by_number` diverts those by
arithmetic, and the arithmetic fails exactly where it is needed: the parser's ply count
drifts from the book's by a whole move for every move it could not read, so on a badly
scanned game no number matches any position, the citation is played as the
continuation, and it is illegal there. **113 moves died under one such move on Grivas,
96 under another.**

`_place_a_citation` lets the board decide instead: among the positions the main line
passed within a move of the printed number, one may make the move legal, and a citation
only one position can play is a citation that says where it belongs. 69 of them over
the corpus. Sakaev 645 → 661, Grivas 140 → 162, Tactics 98 → 102, Boussole 88 → 91,
Markos and SuperAttaquant level.

Three guards, each of which cost something measured to find:

- **Only a move already `broken`** is offered another position, so nothing that stands
  can be taken away.
- **Only a move whose number says it is not the continuation.** Without this, `2 Nc6`
  finds a legal Black square a ply back — the one thing `_MAX_REPAIR_COST` exists to
  prevent — and five tests fail. This is the guard that makes the whole thing honest.
- **Whole moves only.** An odd offset reads the citation for the wrong colour.
  Allowing it scored thirteen more on Markos, every one of them wrong.

Span 2 is the setting; 4 was measured and is worse (Grivas 162 → 156, Tactics 102 → 99
against three more on Sakaev). What it does **not** fix: a game whose drift is three
plies or more, which is what Grivas' largest remaining break is (p.21, 134 moves under
`14 fxg3`, the parser three plies behind).

**And it does not unblock item 5, nor does `deae505`.** The letter rank was retried on
top of both: still −28 on Grivas for +3 on Boussole. Traced all the way this time.
Grivas p.17 prints `6 a4 ♕aS?!`; reading that `Qa5` is **correct**, and it takes the
game's shortfall from two lost half-moves to one. Two is a whole move: the line stays
colour-consistent and goes on scoring `clean` a move behind the page. One inverts the
colours, and the line breaks at `14 f4!` — honestly. So the change trades 28 moves that
were wrong-but-legal for a break that is right, and the metric cannot see it: the
drift detector of `deae505` never speaks there, because when `14 f4!` arrives the aside
opened by the citation *"the futility of 6 ...♕a5"* is still standing, and a number
that lands in an aside says nothing about the main line.

**Extending the detector to that case was measured and is worse**: marking the main
line adrift whenever a number matches *nothing* — not the aside, not the main line, not
any position it passed — costs Tactics 102 clean of which 74 become `drifted`, because
a puzzle book prints numbers that are not move numbers at all. What is needed is a way
to tell a resumption from a puzzle index, and there is none in hand.

**And the one narrow way left of making the drift visible there was measured too, and
fails.** Letting the asides `_place_a_citation` opens close themselves — holding exactly
the moves their number licensed, then popping — was the only "close the aside" variant
that had not been tried, and the only one narrow enough to be worth trying: it touches
no aside the older mechanism opens. Grivas 154 → **122**, Tactics 102 → 100, and
Grivas' `drifted` does not rise (8 → 5). Closing the aside does not expose the drift,
it hands the moves back to the main line where they break. Fifth attempt at ending an
aside, fifth failure.

So item 5 stays closed, and so does this. The rank fix is right, the corpus cannot show
it, and every route to making it show it has now been measured. **Do not reopen either
without a new idea about the numbering itself** — not another rule about asides.

## Dead ends — measured, do not retry

- **A wreck one space from its square** (08-25). `10.ltJ d5` was the case named, and
  the text layer prints `10.ltJd5` with no space at all. Measured over both scans
  before writing it: 7 candidates on Boussole, 2 on Grivas, and **every one is the
  previous move** — `3.BgS cS`, `14.gS hxgS`, `23.eS dxeS`, `16.lNfS .BxfS 17.gxfS
  exf4`. What stands one space before a square is the move before it.
- **Placing every number by the aside's own history** (08-25). The general form of
  "give every level its own history", inside `_place_by_number` and before the move is
  tried: **-2** (Boussole 175 -> 173), firing 39 times over the two scans. Offered
  instead to a move already broken, through `_place_a_citation`, the same record is
  **+16** — see `c89a65a`. Restricted to the aside's opening ply it fires nowhere.
- **A citation of a move the game has not yet reached, diverted into an aside**
  (08-24, third session). `_place_by_number` leaves such a move where the stack stands
  — on the game — and Grivas page 17 shows what that costs: "Now both 17 ♕fxc6+ and
  17 g4 are threatened", printed while the game awaits Black's 16th, are played *as*
  the game, and the game's own `16...♔d7` then hangs off `g4`. Giving them the
  `_place_by_weight` treatment (the current main-line position when the number names no
  position the line has passed) is **worse everywhere**: corpus 2377 -> 2367, Boussole
  160 -> 144, Grivas' diagrams confirms 8 -> 4, and the drift detector of `deae505`
  goes **silent** — `drifted` falls to 0 on every book, because a number that matches
  nothing now opens an aside instead of leaving the line to disagree with the page.
  Two tests fail on that alone. The case is real; this is not the way to it.
- **`!` and `?` read as part of a wreck** (08-24, third session). A Grivas knight is
  drawn with a `!` in it — `lL!g4`, `tL!eS`, 22 over its eighteen pages — and what is
  read instead is the pawn move the rest spells: legal, wrong, at full confidence.
  Adding the two marks to `_WRECK_RUN` reads them right and scores Grivas 435 ->
  **422**, with two of its diagrams turning from confirming the line to correcting it.
  The change also has to take back the annotation token the mark already made, which
  is why `_tokenize_span` now builds a list instead of yielding.
  **Retried 2026-08-25 with the spelling table behind it** (`5482808`), which is a new
  idea about why: no longer -13 but **-1** — Grivas 437 -> 436, `ok` 965 -> **975**.
  Ten more moves read for one clean move lost. Closer than it has ever been and still
  not a gain; the next idea to try on it is item 5, the printed board.
- **Spelling the move out exactly in the bare number's lookahead** (08-24, third
  session). It is a loose two-character test on purpose: that is what lets a number be
  believed in front of the wreck of a symbol, `12 ♔h1` arriving as `12 Kfi>h1`. Being
  exact cost three numbers on Grivas page 27 alone. Only the *pawn* move behind the
  number is read with the book's letter ranks.
- **An additive weight rule**, where the book's own bold only adds the case the
  arithmetic is blind to and everything else stays with `_place_by_number`: Sakaev
  1010, Markos 289, Tactics 90, Grivas 191. Worse than replacing the arithmetic on all
  three typeset books, and worse than doing nothing on two.
- **Judging the ink weight before the diagrams are read.** The comparison then runs
  between two readings neither of which is the one that ships, and it kept the wrong
  one on Grivas — 182 instead of 224, silently.
- **The space inside a move, unanchored.** `[a-h] [1-8]` anywhere reads the tail of an
  ordinary word as a square — "the move 6.♗g5" as `e 6` — and eats the number beside it.
  It scores **+78** on the corpus for that reason alone, six of Sakaev's prose citations
  silently dropped, boxes and all. The general form of the same idea (a number preceded
  by a word announces nothing) costs 253: Sakaev 657 → 506, Grivas 129 → 54.
- **Joining the span across a drawn board**, so a number can see the move beside it.
  Right in principle — it recovers the `7` of Grivas p.17 — and Grivas 156 → **149**:
  numbers that announced nothing start opening asides that divert lines.
- **Letting a citation that lands on the position the main line awaits continue the
  main line** rather than open an aside. Grivas 156 → **134**.
- **Raising `STRAY_DISTANCE` to absorb the scans' strays.** At 0.25 every board comes
  out clean and both books score *lower* end to end (SuperAttaquant `ok` 18→16,
  Boussole 133→117). A stray absorbed into the wrong kind costs more than a board
  refused. A ratio rule in its place is worse at every ratio tried.
- **Raising `MAX_KINDS` above 13.** Boards come out clean carrying up to 17 distinct
  characters, which no board can. The cut is not the fault — the over-splitting is.
- **Reaching 13 by merging the clusters instead of cutting** (`cb57f74`, reverted by
  `da979d7`) — nearest pair, weighted by support at 0.25 and 0.5, and shape-first
  (6 shapes × 2 colours). All read more boards; all read them wrong.
- **Closing the outline before filling it** (`binary_closing`, then fill, then open).
  A hatch closes into a solid body: SuperAttaquant goes from 10 strays to 139, and 175
  of its empty squares stop being empty.
- **Taking more of each square** (`INSET` 0.10 → 0.03). It does what it is for — the
  tall pieces stop being clipped, strays fall by half on both scans — and `clean` does
  not move except down (SuperAttaquant 14 → 13). At 0.00 the grid lines come in and
  Grivas breaks.
- **Hierarchical clustering** (average linkage, cut at thirteen). Merges by colour, not
  by piece. Grivas comes out with exactly the greedy partition, which is worth knowing:
  on a clean book the two agree square for square.
- **A finer signature** (`SIGNATURE_SIDE` 10 → 14, 18, 24). Monotonically more strays
  on all three books. The ink varies faster than the drawing does.
- **Reading a letter-shaped rank** (`dS` as `d5`), on its own. Right on Boussole
  (88 → 93) and right on Grivas move by move, and Grivas scores 140 → 121 because of
  item 10. Not a dead end — a change blocked behind another one.
- **Three ways of ending a prose aside** — see item 10. All three cost more than the
  stranding they fix.
- **Judging any of this on `ok`.** The merge looked like +4 on SuperAttaquant's `ok`
  and was −9 on its `clean`. `break_diagnosis` says which figure to use, in the
  docstring, and it is `clean`.
- **A geometric threshold for the spurious spaces.** The ink gap around a space
  character, in font sizes over six pages: 0.0→50, 0.1→97, 0.2→403, 0.3→874, 0.4→445,
  0.5→203, 0.6→63. One peak, no valley: real word spaces sit at 0.1 beside the spurious
  ones. They are genuine space characters in the PDF's own stream.
- **A font's name as the route to a figurine face.** Two books embed their fonts as
  `Fd97320`, one reports plain `Helvetica`, and the one that identifies itself calls
  its OCR layer `GlyphLessFont`. `figurines.py` finds symbols by where they stand.
- **Voting character by character to learn a diagram font.** Most observations are
  wrong, because a diagram is most useful where the parser had drifted: sixteen
  observations left four letters standing out of twenty-three. They vote as wholes.
- **The lookahead for SAN ambiguity.** Measured three times, most recently on 08-21
  with a sound corpus: 12 ambiguities on Grivas, 2 on Sakaev, 1 on Markos, and most sit
  below a repair. Surfacing `candidates` to the app is enough.
- **`context=2` in `notation_lines`** — catches 4 of 6 missing lines and adds a fifth of
  every book, Tactics included.
- **Counting squares to find a line of play** — catches 1 of 6: the same wreck welds
  itself to the square and hides it from a square counter too.
- **Intersecting a rule's span across its rows.** On a tilted page each row of a rule
  starts a pixel later than the last, so what they agree on is the part in the middle:
  every rule came out five pixels long. Take the longest stretch any one row holds.
- **Comparing the gap between two rules against the length they run over.** That is an
  inside against an outside, and the difference is two rules thick — enough to fail a
  board that is square. Locate all four rules first, then measure the inside.
- **Rendering a small drawn board at a higher dpi.** Tactics at 150, 300 and 600 dpi:
  27, 52 and 56 stray clusters against 18 from the stored picture. The publisher stored
  190 pixels and there is nothing else to read.
- **Searching for the board inside a picture by its shading.** A grid a third of a
  square out still has two thirds of every cell in the right square, so the alternation
  barely weakens; the search chose the wrong offset on the one Grivas board it was
  written for. The frame is what locates a board.
- **The move a number announced, destroyed down to its rank** (08-27). Ten on
  SuperAttaquant (`16.6` for `16.e6`, `16.45` for `16.d5!`, `35.4`, `32.26`, `29.8`)
  and four false ones on Boussole. Carried on the number token so `parse` can see
  them, it fires **nowhere** and costs **twelve**: the seeding branch returns before
  the placement code, and the swallowed digits were a `text` token that ended the
  number's licence. Both halves are fixable and the case is real — see the session
  note above for where each would have to go.
- **Raising `_MAX_REPAIR_COST` to 1.0** — that is how `Qh9` becomes `Qh5`. The narrow
  deletion of `9f1e590` is allowed only between a piece and its square, and only where
  the board leaves one reading.

## The files, all outside this repository

| Path | Use |
| --- | --- |
| `~/Documents/Programmation/entrainement_ocr_echecs/6class/chess_glyphs_classifier.zip` | the classifier |
| `~/Documents/Echecs/Ebooks/` | the library, ~60 PDFs; `scripts/choose_pages.py` is how to pick from it |
| `…/The complete manual of positional chess … 9789056916824 … .pdf` | Sakaev, **320 pages** — the 368-page edition of the same book is a different one and its range means nothing |
| `…/Under the Surface -- Markos, Jan … .pdf` | Markos, 287 pages |
| `…/Chess College 1 Strategy - Grivas.pdf` | Grivas, 114 pages (the old `ChessTrategy_Grivas_1.pdf` fixture is an extract of it) |
| `…/Chess Tactics for the Tournament Player.pdf` | Tactics, 302 pages |
| `…/Une boussole sur l'échiquier_ … Parmentier … .pdf` | Boussole, 340 pages |
| `…/COMMENT DEVENIR UN SUPER ATTAQUANT_ … LeMoir … .pdf` | SuperAttaquant, 292 pages |

All six are on Drive under `/content/drive/MyDrive/entrainement_ocr_echecs/pdfs/`,
verified 2026-08-21 by their page counts in notebook section 3. The hand-cut extracts
that used to stand in for three of them are superseded: they were poor material.
