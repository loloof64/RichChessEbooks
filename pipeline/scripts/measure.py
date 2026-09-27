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
from concurrent.futures import ProcessPoolExecutor

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


def measure(window: tuple[str, str, int, int | None]) -> tuple[str, dict]:
    name, pattern, first, last = window
    try:
        from rce_pipeline import pipeline

        path = sorted(glob.glob(f"{LIBRARY}/{pattern}"))[0]
        run = pipeline.run(path, work_dir=f"/tmp/rce-measure/{name}", first_page=first,
                           last_page=last, glyph_model=MODEL, write_artefacts=False)
    except Exception as error:  # a window that crashes is a figure too
        return name, {"error": f"{type(error).__name__}: {error}"[:200]}
    parsed = run.parsed
    unplaced = {game.id for game in parsed.games if not game.position_known}
    return name, {
        "moves": len(parsed.moves),
        **{status: sum(m.status == status for m in parsed.moves)
           for status in ("ok", "uncertain", "broken")},
        "unplaced": sum(m.game_id in unplaced for m in parsed.moves),
        "clean": parsed.break_diagnosis()["clean"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("set", choices=("corpus", "heldout"))
    parser.add_argument("only", nargs="*", help="measure only these windows")
    parser.add_argument("--json", help="write the figures here")
    args = parser.parse_args()
    windows = [w for w in (CORPUS if args.set == "corpus" else HELDOUT)
               if not args.only or w[0] in args.only]
    with ProcessPoolExecutor(6) as pool:
        figures = dict(pool.map(measure, windows))
    for name, row in figures.items():
        if "error" in row:
            print(f"{name:34} ERROR {row['error']}")
        else:
            print(f"{name:34} moves {row['moves']:5}  clean {row['clean']:5}  "
                  f"broken {row['broken']:5}  unplaced {row['unplaced']:5}")
    print(f"{'total':34} clean {sum(r.get('clean', 0) for r in figures.values())}")
    if args.json:
        with open(args.json, "w") as out:
            json.dump(figures, out, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
