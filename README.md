# Rich Chess Ebooks

Read a chess ebook and tap any move to see the position it leads to.

The book is shown exactly as it was published — the original PDF, unmodified — with an
invisible clickable zone over every move an extraction pipeline found. Tapping one
opens a static board showing the position after that move, with the move highlighted.

Two components, joined by one strict data contract:

```
  PDF  ──▶  Python pipeline  ──▶  book.rce  ──▶  Flutter app
            (`rce` command)        (ZIP)         (reader)
```

| | Where | What it does |
| --- | --- | --- |
| Pipeline | [`pipeline/`](pipeline/), installed as the `rce` command | Reads the PDF, finds the moves and their page geometry, validates them against the rules, writes the archive |
| Reader | [`lib/`](lib/) | Opens the archive, renders the book, overlays the tap zones, shows the board |
| Contract | [`docs/rce-format.md`](docs/rce-format.md) + [`docs/schemas/`](docs/schemas/) | The `.rce` format the two agree on |

Neither side imports the other. The archive is the whole interface.

## Installing it

You need **Python 3.10 or later** and a terminal. The tool is installed with
[`pipx`](https://pipx.pypa.io), which puts it in an environment of its own so it never
conflicts with anything else on the machine.

**1. Install pipx** (once):

| System | Command |
| --- | --- |
| Debian / Ubuntu | `sudo apt install pipx` |
| Fedora | `sudo dnf install pipx` |
| macOS | `brew install pipx` |
| Windows | `py -m pip install --user pipx` |

then run `pipx ensurepath` (on Windows: `py -m pipx ensurepath`, since `pipx` is not on
the PATH yet), and **open a new terminal** so the `rce` command is found.

> **Windows.** `py` is the Python launcher, installed with Python by the official
> installer from [python.org](https://www.python.org/downloads/windows/). The Microsoft
> Store version of Python does not provide it: there, type `python` instead of `py`.

**2. Install the tool** — choose one:

> ⚠ **Size.** The full install downloads about **400 MB** of dependencies (scipy,
> scikit-learn, numpy, scikit-image). The minimal one is about **70 MB**. The piece
> classifier itself is included and weighs 0.5 MB.

```bash
# Full (~400 MB): every kind of book, including scans, figurine fonts and
# diagrams drawn as images. Take this one unless disk space matters.
pipx install "rce-pipeline[glyphs,pictures] @ git+https://github.com/loloof64/RichChessEbooks.git#subdirectory=pipeline"

# Minimal (~70 MB): only books whose moves are real text in the PDF
# (digitally produced books). A scan will be reported unreadable.
pipx install "git+https://github.com/loloof64/RichChessEbooks.git#subdirectory=pipeline"
```

**EPUB and DjVu books.** Both are converted to PDF first, and the `.rce` carries that
PDF: the app shows an EPUB as fixed pages, not reflowed text. An EPUB needs nothing
more. A DjVu needs the `ddjvu` command from djvulibre (about **5 MB**), and is read
like a scan, so take the full install:

| System | Command |
|---|---|
| Debian / Ubuntu | `sudo apt install djvulibre-bin` |
| Fedora | `sudo dnf install djvulibre` |
| macOS | `brew install djvulibre` |
| Windows | the installer from [djvu.sourceforge.net](https://djvu.sourceforge.net/), with its folder on `PATH` |

**3. Use it:**

```bash
rce book.pdf                       # writes book.rce beside the PDF
rce book.pdf --lang fr             # tell it the language of a book in letters
rce book.pdf --first 20 --last 40  # a range of pages, to try a book quickly
rce book.epub                      # an EPUB or a DjVu works the same way
```

Open the `.rce` in the app, and tap the eye icon to see what was read and where the
pipeline is unsure. On a new book, try a chapter whose content you know first.

**Updating.** `rce` checks GitHub at the end of each run and, when the pipeline has
changed since you installed it, ends its report with the command to run:
`pipx reinstall rce-pipeline` (not `pipx upgrade`, which only acts when the version
number changes). The check takes at most two seconds, says nothing when offline, and is
turned off by setting `RCE_NO_UPDATE_CHECK=1`. `pipx uninstall rce-pipeline` removes
everything.

## Current state

Working, on PDFs that carry a **real text layer** — a book produced digitally rather
than scanned — in either **figurine Unicode** or **plain letters** (`en`, `fr`, `de`,
`es`, `it`, `nl`):

- extraction of moves, variations and comments, with per-move page geometry
- legality checking and FEN reconstruction, with conservative repair of scanning errors
- `.rce` packaging, and import into the app
- clickable zones that stay aligned at any zoom, and a static board on tap

**Scanned books are half-way in, and they are the bulk of the target corpus.** A scan's
text layer is OCR output: its prose is fine, its squares are 92% right, and its piece
symbols are worthless — a knight has no OCR category, so it lands on whatever character
looked closest. Those symbols are now read off the page images instead, by a trained
classifier, and written back into the pages as figurines: **53 of the 54 printed on two
hand-read pages, none invented**. A book set in a figurine *font* takes the same route
and used to be unparseable too.

What is not settled is where a recovered symbol belongs in the text, which depends on
boxes the scanner placed, not the classifier: 77% of them land at the head of their move
on a well-boxed book and 46% on a loosely boxed one. The pipeline measures and reports
that share rather than assuming it. The reasoning and the numbers are in
[`pipeline/README.md`](pipeline/README.md#books-whose-symbols-are-only-in-the-image).

Also not built: the correction UI and `patches.json` writing (the format is specified
and the reader is designed around it, but nothing writes patches yet), and EPUB, which
is a separate v2 — a reflowable document has no stable coordinates, so its anchoring
model is incompatible with this one.

## Running the app

Ready-made packages are on the [releases page](https://github.com/loloof64/RichChessEbooks/releases):

| System | Files |
| --- | --- |
| Linux | `.AppImage` (any distribution, no install), `.deb`, `.rpm` |
| Windows | `-setup.exe` (installer), `.msi`, `-portable.zip` (unzip and run, nothing installed) |
| macOS | `.dmg`, `.zip` (Apple silicon and Intel) |

The Windows and macOS builds are not signed, so the system warns on first launch. On
Windows, choose *More info* → *Run anyway*. On macOS, right-click the app → *Open*, or run
`xattr -cr "/Applications/Rich Chess Ebooks.app"` if macOS says it is damaged.

To run from source:

```bash
flutter pub get
flutter run          # linux, macos, windows, android, ios
```

Once a book is open:

- **tap a move** — the board for the resulting position
- **eye icon** — tint the tap zones, so you can see what the pipeline found and where
  it is unsure (green: read cleanly, amber: repaired, red: unreadable)
- **skip icon** — jump to the next page carrying moves

## Tests

```bash
flutter test                      # reader: geometry, archive loading, tree navigation
cd pipeline && pytest             # pipeline: move tree, legality, repairs
```

The geometry tests matter more than their size suggests. Converting a box from PDF
space (origin bottom-left) to Flutter space (origin top-left) is one flip and one
scale, and getting the flip wrong mirrors every zone about the middle of the page —
which looks plausible on a symmetric layout and is wrong everywhere else.
