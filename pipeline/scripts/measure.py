#!/usr/bin/env python3
"""Measure the pipeline on the tuned corpus and on pages never tuned on.

    PYTHONPATH=pipeline python pipeline/scripts/measure.py corpus
    PYTHONPATH=pipeline python pipeline/scripts/measure.py heldout --json out.json
    PYTHONPATH=pipeline python pipeline/scripts/measure.py heldout Kaber Silman4

`corpus` is the six books every change so far was tuned on, at the ranges
`user_tasks.md` compares. `heldout` is the control: eleven books outside the
corpus at the window `choose_pages.py --whole-games` picked, Fabrice's
documents whole, and the six corpus books forty pages past their tuned range.
It was fixed on 2026-09-27 before any version was measured on it, and it is
only worth anything while nothing is tuned on it: a change is kept when it
helps the corpus **and does not hurt here**. Look at a held-out page to
understand a defect, never to choose a constant.

To compare two versions, run the same set from two checkouts (`git archive
<commit> pipeline | tar -x -C <dir>`, then point PYTHONPATH at it) and diff
the JSON. The books live outside the repository; `RCE_LIBRARY` and
`RCE_GLYPH_MODEL` override where.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

LIBRARY = os.environ.get("RCE_LIBRARY", os.path.expanduser("~/Documents/Echecs/Ebooks"))
MODEL = os.environ.get(
    "RCE_GLYPH_MODEL",
    os.path.expanduser(
        "~/Documents/Programmation/entrainement_ocr_echecs/6class/chess_glyphs_classifier.zip"
    ),
)

CORPUS = [
    ("Sakaev", "*complete manual of positional*9789056916824*.pdf", 37, 50),
    ("Markos", "*Under the Surface*Markos*.pdf", 85, 96),
    ("Grivas", "Chess College 1 Strategy*.pdf", 14, 31),
    ("Tactics", "Chess Tactics for the Tournament*.pdf", 170, 181),
    ("Boussole", "*boussole*.pdf", 56, 70),
    ("SuperAttaquant", "*SUPER ATTAQUANT*.pdf", 198, 209),
]

HELDOUT = [
    ("Pachman2", "Th*orie *l*mentaire_ 2*", 155, 166),
    ("Loheac", "Comment mater aux *checs*", 167, 182),
    ("Summerscale", "R*pertoire d'ouvertures efficace*", 97, 115),
    ("Grivas3", "Chess College 3 Technique*", 54, 65),
    ("Sicilian", "How to Beat the Sicilian*", 316, 327),
    ("Dutch", "Williams Simon*", 154, 165),
    ("Principes", "Les_principes_fondamentaux*", 94, 108),
    ("Chernev", "The Most Instructive Games*", 341, 352),
    ("Pachman1", "Th*orie *l*mentaire_ 1*", 165, 181),
    ("Critical", "The critical moment -- Neat, Ken; Dorfman, Iossif.pdf", 76, 89),
    ("Kaber", "Tactics Training*", 73, 86),
    # Added by Laurent while the set was first measured; same rule.
    ("Silman4", "Silman/How to reassess your chess - chess mastery through chess*.pdf", 601, 617),
    ("Sakaev+40", "*complete manual of positional*9789056916824*.pdf", 77, 88),
    ("Markos+40", "*Under the Surface*Markos*.pdf", 125, 136),
    ("Grivas+40", "Chess College 1 Strategy*.pdf", 54, 65),
    ("Tactics+40", "Chess Tactics for the Tournament*.pdf", 210, 221),
    ("Boussole+40", "*boussole*.pdf", 96, 107),
    ("SuperAtt+40", "*SUPER ATTAQUANT*.pdf", 238, 249),
] + [
    (f"Fab:{os.path.basename(path)[:-4]}", "DeFabrice/" + os.path.basename(path), 1, None)
    for path in sorted(glob.glob(f"{LIBRARY}/DeFabrice/*.pdf"))
]


def measure(job: tuple[tuple[str, str, int, int | None], int]) -> tuple[str, dict]:
    """One window's figures, read from `lead` pages before it and counted on it alone.

    The lead is what a whole book gives a page and a twelve-page window takes
    away: the games that teach the diagram font, the boards that seed. Sakaev
    77-88 run alone scores 0 of 996 clean — nothing in it opens a game, so no
    diagram is ever read — and run from page 37 it scores 908. A reader
    converts the whole book, so the window alone measures a failure nobody meets.
    """
    (name, pattern, first, last), lead = job
    try:
        from rce_pipeline import pipeline

        path = sorted(glob.glob(f"{LIBRARY}/{pattern}"))[0]
        run = pipeline.run(path, work_dir=f"/tmp/rce-measure/{name}",
                           first_page=max(1, first - lead), last_page=last,
                           glyph_model=MODEL, write_artefacts=False)
    except Exception as error:  # a window that crashes is a figure too
        return name, {"error": f"{type(error).__name__}: {error}"[:200]}
    return name, figures(run.parsed, first, last)


def figures(parsed, first: int, last: int | None) -> dict[str, int]:
    """A reading's figures on pages `first` to `last` alone."""
    by_id = {m.id: m for m in parsed.moves}
    unplaced = {game.id for game in parsed.games if not game.position_known}
    against = set(parsed.contradicted) | set(parsed.drifted)

    reseeded = set(getattr(parsed, "reseeded", ()))

    def below_a_break(move) -> bool:
        # As `break_diagnosis`: up to the break, or to a board a diagram put back.
        current = move
        while current.parent_id is not None and current.id not in reseeded:
            current = by_id[current.parent_id]
            if current.status == "broken":
                return True
        return False

    # The same tests as `ParseResult.break_diagnosis`, move by move, so that
    # only the window's pages are counted.
    in_window = lambda page: page >= first and (last is None or page <= last)
    moves = [m for m in parsed.moves if in_window(m.page)]
    scored_ok = [m for m in moves if m.status == "ok" and m.game_id not in unplaced]
    below = {m.id for m in scored_ok if below_a_break(m)}
    contradicted, drifted = set(parsed.contradicted), set(parsed.drifted)
    clean = sum(m.id not in against and m.id not in below for m in scored_ok)
    caught = sum(m.id in contradicted and m.id not in below for m in scored_ok)
    return {
        # **The figure to compare** (2026-09-29): `clean` with the moves a board
        # proved wrong put back. Those were wrong before the board was read and
        # counted clean then, so reading a board no longer costs a book moves —
        # which is how Chess College 3's right table was nearly refused.
        "sound": clean + caught,
        "moves": len(moves),
        **{status: sum(m.status == status for m in moves)
           for status in ("ok", "uncertain", "broken")},
        "unplaced": sum(m.game_id in unplaced for m in moves),
        "clean": clean,
        # What the boards said. `clean` only ever loses moves to a board that
        # is read — a book whose boards stay unread keeps the same wrong moves
        # clean — so the verdicts are reported beside it.
        "below_break": len(below),
        "contradicted": caught,
        "drifted": sum(
            m.id in drifted and m.id not in contradicted and m.id not in below for m in scored_ok
        ),
        "confirms": sum(
            check["verdict"] == "confirms" and in_window(check["page"])
            for check in parsed.diagram_checks
        ),
        "boards_read": sum(
            check["verdict"] not in ("unread", "unreadable") and in_window(check["page"])
            for check in parsed.diagram_checks
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("set", choices=("corpus", "heldout"))
    parser.add_argument("only", nargs="*", help="measure only these windows")
    parser.add_argument("--json", help="write the figures here")
    parser.add_argument(
        "--lead", type=int, default=None,
        help="pages read before each window and not counted "
             "(default: 60 held out, 0 on the corpus, whose figures are compared bare)",
    )
    args = parser.parse_args()
    lead = args.lead if args.lead is not None else (60 if args.set == "heldout" else 0)
    windows = [w for w in (CORPUS if args.set == "corpus" else HELDOUT)
               if not args.only or w[0] in args.only]
    results: dict[str, dict] = {}
    # Each window is printed as it finishes: a held-out run takes hours, and
    # a window that never ends is then the one missing from the list.
    with ProcessPoolExecutor(6) as pool:
        for done in as_completed([pool.submit(measure, (w, lead)) for w in windows]):
            name, row = done.result()
            results[name] = row
            if "error" in row:
                print(f"{name:34} ERROR {row['error']}", flush=True)
            else:
                print(f"{name:34} moves {row['moves']:5}  sound {row['sound']:5}  "
                      f"clean {row['clean']:5}  broken {row['broken']:5}  "
                      f"confirms {row['confirms']:3}  unplaced {row['unplaced']:5}", flush=True)
    print(f"{'total':34} sound {sum(r.get('sound', 0) for r in results.values())}  "
          f"clean {sum(r.get('clean', 0) for r in results.values())}")
    if args.json:
        with open(args.json, "w") as out:
            json.dump(results, out, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
