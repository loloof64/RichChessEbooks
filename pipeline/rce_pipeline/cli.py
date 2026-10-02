"""`rce livre.pdf` — the pipeline from a terminal, for someone who never opens it."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import itertools
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import warnings
from importlib.resources import files

from . import __version__
from .pipeline import run

LANGUAGES = ("en", "fr", "de", "es", "it", "nl")
FULL_INSTALL = (
    'pipx install --force "rce-pipeline[glyphs,pictures] @ '
    'git+https://github.com/loloof64/RichChessEbooks.git#subdirectory=pipeline"'
)

PIPELINE_COMMITS = (
    "https://api.github.com/repos/loloof64/RichChessEbooks/commits?path=pipeline&per_page=1"
)


def update_notice() -> str | None:
    """What to run to get a newer pipeline, if GitHub has one; else None.

    The last commit to touch `pipeline/` as seen from the commit pip installed,
    against the same on GitHub's main: a later commit that only touched the
    app is no reason to reinstall. Silent whenever it cannot tell: a checkout run from
    source, no network, GitHub slow or refusing. RCE_NO_UPDATE_CHECK turns it
    off.
    """
    if os.environ.get("RCE_NO_UPDATE_CHECK"):
        return None
    installed = _installed_commit()
    if installed is None:
        return None
    mine, latest = _pipeline_commit(installed), _pipeline_commit()
    if mine is None or latest is None or mine == latest:
        return None
    return ("A newer version of rce is available. To install it:\n"
            "  pipx reinstall rce-pipeline")


def offer_update(argv: list[str]) -> None:
    """Ask, before the book is read, whether to install a newer rce first.

    Accepted, pipx reinstalls the pipeline and the same command starts again
    on the new version, told not to ask twice. Refused, or not at a terminal
    to answer, the book is read with the version installed and the notice is
    printed at the end as before.
    """
    notice = update_notice()
    if notice is None or not sys.stdin.isatty():
        return
    print(notice.splitlines()[0])
    try:
        answer = input("Update now, before reading the book? [y/N] ")
    except EOFError:
        return
    if answer.strip().lower() not in ("y", "yes", "o", "oui"):
        return
    if subprocess.run(["pipx", "reinstall", "rce-pipeline"]).returncode != 0:
        print("The update failed; reading the book with the version installed.")
        return
    os.execvpe("rce", ["rce", *argv], {**os.environ, "RCE_NO_UPDATE_CHECK": "1"})


def _installed_commit() -> str | None:
    """The commit a `pipx install git+...` was built from, as pip recorded it."""
    try:
        recorded = importlib.metadata.distribution("rce-pipeline").read_text("direct_url.json")
        return json.loads(recorded or "{}").get("vcs_info", {}).get("commit_id")
    except (importlib.metadata.PackageNotFoundError, ValueError):
        return None


def _pipeline_commit(ref: str | None = None) -> str | None:
    """The last commit to touch `pipeline/` as of `ref`, main by default."""
    url = PIPELINE_COMMITS + (f"&sha={ref}" if ref else "")
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return json.load(response)[0]["sha"]
    except Exception:  # any failure means "cannot tell", never an error for the reader
        return None


class Waiting:
    """Which step is running and for how long, on stderr, while the book is read.

    A whole book takes minutes and a scan can take an hour: without this the
    terminal says nothing from the command to the report. In a terminal, a
    spinner and a clock on one line, and a line left behind per finished step;
    elsewhere (a log, a pipe), one plain line per step. ASCII only, so an old
    Windows console with a legacy code page shows it too.
    """

    def __init__(self) -> None:
        self.live = sys.stderr.isatty()
        self.step: str | None = None
        self.started = self.step_started = time.monotonic()
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._spin, daemon=True)

    def __enter__(self) -> "Waiting":
        if self.live:
            self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.done.set()
        if self.live:
            self.thread.join()
            with self.lock:
                self._finish_step()
        total = time.monotonic() - self.started
        print(f"Done in {_clock(total)}.\n", file=sys.stderr)

    def __call__(self, step: str) -> None:
        with self.lock:
            if self.live:
                self._finish_step()
            else:
                print(f"{step}...", file=sys.stderr, flush=True)
            self.step, self.step_started = step, time.monotonic()

    def _finish_step(self) -> None:
        if self.step is not None:
            line = f"  {self.step} ({_clock(time.monotonic() - self.step_started)})"
            sys.stderr.write("\r" + line.ljust(72) + "\n")
            sys.stderr.flush()
            self.step = None

    def _spin(self) -> None:
        for frame in itertools.cycle("|/-\\"):
            with self.lock:
                if self.step is not None:
                    line = (f"{frame} {self.step}...  {_clock(time.monotonic() - self.step_started)}"
                            f"  (total {_clock(time.monotonic() - self.started)})")
                    sys.stderr.write("\r" + line.ljust(72))
                    sys.stderr.flush()
            if self.done.wait(0.2):
                return


def _clock(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}:{seconds:02d}"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="rce", description="Turn a PDF chess book into a .rce archive for the reader app."
    )
    ap.add_argument("pdf", help="the book")
    ap.add_argument("-o", "--output", help="where to write the .rce (default: beside the PDF)")
    ap.add_argument("--first", type=int, default=1, metavar="PAGE", help="first page to read")
    ap.add_argument("--last", type=int, metavar="PAGE", help="last page to read")
    ap.add_argument(
        "--lang", choices=LANGUAGES,
        help="the book's language, for a book in letters: worth setting, a wrong "
             "guess yields legal but wrong moves",
    )
    ap.add_argument("--version", action="version", version=f"rce {__version__}")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.pdf):
        ap.error(f"no such file: {args.pdf}")
    offer_update(sys.argv[1:] if argv is None else argv)
    output = args.output or os.path.splitext(args.pdf)[0] + ".rce"
    # Without the `glyphs` extra a scan cannot be read, and the report says so;
    # a book with a usable text layer never needed it.
    model = (
        str(files(__package__) / "data" / "classifier.pkl")
        if importlib.util.find_spec("sklearn") else None
    )

    with tempfile.TemporaryDirectory() as work_dir, \
            warnings.catch_warnings(record=True) as caught, Waiting() as waiting:
        warnings.simplefilter("default")
        result = run(
            args.pdf, work_dir=work_dir, output_path=output,
            first_page=args.first, last_page=args.last,
            force_language=args.lang, glyph_model=model, write_artefacts=False,
            progress=waiting,
        )
    # A step skipped for a missing extra names a `pip install`, which is not
    # how this was installed; the reader gets the one command that fixes it.
    missing_extra = [w for w in caught if "rce-pipeline[" in str(w.message)]
    for w in caught:
        if w not in missing_extra:
            warnings.showwarning(w.message, w.category, w.filename, w.lineno)
    print(result.report())
    notice = update_notice()
    if notice:
        print(f"\n{notice}")
    if missing_extra or (model is None and result.notation.needs_glyph_recovery):
        print(f"\nThis book needs the full install (~400 MB). Run:\n  {FULL_INSTALL}\n"
              "then run rce again.")


if __name__ == "__main__":
    main()
