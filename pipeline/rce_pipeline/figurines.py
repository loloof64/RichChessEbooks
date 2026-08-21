"""Piece symbols printed as ordinary characters of a figurine font.

A publisher who does not use the Unicode chess block prints `¤c3` and lets a
font draw a knight over the character. The text layer keeps the character, so
nothing is lost — but nothing downstream knows what `¤` is either, and the move
is read as a pawn move to c3 or thrown away.

The characters are found by what they do rather than by the name of their font.
A book's fonts are often named `Fd97320` or `Helvetica`, and one of the corpus
identifies its OCR layer as `GlyphLessFont`, so a name proves nothing; what a
figurine does prove is where it stands — always in front of a square, in a font
that is not the one the prose is set in.

Which character is which piece is then settled **by the board**: every reading
is tried on a sample of the book and the one that leaves the most moves legal
wins. On Quality Chess's `SPAriesFig` the winner reads `¢£¤¥¦` as K, Q, N, B, R
— the Figurine Symbol T1 encoding — and does so 111 sound moves to 82 for the
runner-up. Nothing here knows that encoding; it is the answer, not the method.
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from itertools import permutations
from typing import Iterable

from .extract import Page
from .notation import FIGURINE_TO_LETTER, SAN_PIECE_LETTERS

#: SAN letter -> the figurine the page is rewritten with, so that everything
#: downstream sees the book the Unicode chess block would have given it.
_TO_FIGURINE = {letter: figurine for figurine, letter in FIGURINE_TO_LETTER.items()}

#: A square, with the capture and disambiguation a move may carry between the
#: symbol and it. What a piece symbol is always followed by.
_LEADS_A_MOVE = re.compile(r"[a-h1-8]?x?[a-h][1-8]")

#: A symbol has to be printed this often before it is worth settling. Below it
#: the sample cannot tell one reading from another anyway.
_MIN_OCCURRENCES = 5

#: At most this many pages are read to settle the alphabet. Every reading is
#: tried on them, so the work is a permutation count times a sample.
_SAMPLE_PAGES = 12


def candidates(pages: Iterable[Page]) -> list[str]:
    """The characters of this book that behave like piece symbols.

    Ordered by how often they occur, which is not how the meaning is settled —
    it only decides which are worth trying when a book prints more than five.
    """
    body = Counter()
    for page in pages:
        body.update(char.font for char in page.chars)
    prose_font = body.most_common(1)[0][0] if body else None

    seen: Counter[str] = Counter()
    for page in pages:
        for index, char in enumerate(page.chars):
            if char.font == prose_font or char.char in FIGURINE_TO_LETTER:
                continue
            if char.char.isascii() or char.char.isspace():
                continue
            if _LEADS_A_MOVE.match(page.text[index + 1 : index + 6]):
                seen[char.char] += 1
    return [char for char, count in seen.most_common(5) if count >= _MIN_OCCURRENCES]


def settle(pages: list[Page], symbols: list[str]) -> dict[str, str]:
    """Which piece each symbol is, decided by how many moves come out legal.

    Returns the rewriting map, empty when no reading beats leaving the book
    alone — which is the answer for a book whose odd characters were never
    piece symbols at all.
    """
    from . import diagrams, notation, parse, tokenize

    sample = _sample(pages)

    def sound(mapping: dict[str, str]) -> int:
        pages_read = rewrite(sample, mapping) if mapping else sample
        report = notation.detect_notation(pages_read)
        tokens = tokenize.tokenize_pages(
            pages_read,
            piece_letters=report.piece_letters,
            diagrams=diagrams.find(pages_read),
        )
        return parse.parse_tokens(tokens).break_diagnosis()["clean"]

    best: dict[str, str] = {}
    best_score = sound({})
    for letters in permutations(SAN_PIECE_LETTERS, len(symbols)):
        mapping = {symbol: _TO_FIGURINE[letter] for symbol, letter in zip(symbols, letters)}
        score = sound(mapping)
        if score > best_score:
            best, best_score = mapping, score
    return best


def _sample(pages: list[Page]) -> list[Page]:
    """The pages worth settling the alphabet on: the ones carrying the moves."""
    if len(pages) <= _SAMPLE_PAGES:
        return pages
    ranked = sorted(pages, key=lambda page: -len(re.findall(r"\d\s*\.", page.text)))
    return sorted(ranked[:_SAMPLE_PAGES], key=lambda page: page.number)


def rewrite(pages: list[Page], mapping: dict[str, str]) -> list[Page]:
    """The same pages with every symbol replaced by its Unicode figurine.

    Rewriting rather than teaching the tokeniser a second alphabet is what
    keeps the rest of the pipeline unaware that this book was ever different:
    notation detection, glyph recovery and the move pattern all go on reading
    the Unicode chess block, and the geometry is untouched — a figurine takes
    the place of exactly one character, in its own box.
    """
    rewritten = []
    for page in pages:
        chars = [
            dataclasses.replace(char, char=mapping.get(char.char, char.char))
            for char in page.chars
        ]
        text = "".join(mapping.get(char, char) for char in page.text)
        rewritten.append(dataclasses.replace(page, text=text, chars=chars))
    return rewritten
