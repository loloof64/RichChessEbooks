# Rich Chess Ebooks

Read a chess ebook and tap any move to see the position it leads to.

The book is shown exactly as it was published — the original PDF, unmodified — with an
invisible clickable zone over every move an extraction pipeline found. Tapping one
opens a static board showing the position after that move, with the move highlighted.

Two components, joined by one strict data contract:

```
  PDF  ──▶  Python pipeline  ──▶  book.rce  ──▶  Flutter app
            (Google Colab)         (ZIP)         (reader)
```

| | Where | What it does |
| --- | --- | --- |
| Pipeline | [`pipeline/`](pipeline/), driven by [`notebooks/rce_pipeline.ipynb`](notebooks/rce_pipeline.ipynb) | Reads the PDF, finds the moves and their page geometry, validates them against the rules, writes the archive |
| Reader | [`lib/`](lib/) | Opens the archive, renders the book, overlays the tap zones, shows the board |
| Contract | [`docs/rce-format.md`](docs/rce-format.md) + [`docs/schemas/`](docs/schemas/) | The `.rce` format the two agree on |

Neither side imports the other. The archive is the whole interface.

## Current state

Working, on PDFs that carry a **real text layer** — a book produced digitally rather
than scanned — in either **figurine Unicode** or **plain letters** (`en`, `fr`, `de`,
`es`, `it`, `nl`):

- extraction of moves, variations and comments, with per-move page geometry
- legality checking and FEN reconstruction, with conservative repair of scanning errors
- `.rce` packaging, and import into the app
- clickable zones that stay aligned at any zoom, and a static board on tap

**Scanned books do not work yet, and they are the bulk of the target corpus.** A scan's
text layer is OCR output; its prose is fine but its moves are not, because the piece
glyphs have no OCR category and the surrounding characters degrade with them. Finding
the printed lines and cropping them for a recogniser is built and tested; recognising
what is in the crop is not, and measuring the crops has narrowed what that recogniser
has to do. The reasoning and the numbers are in
[`pipeline/README.md`](pipeline/README.md#scanned-books). This is the main open piece
of work.

Also not built: the correction UI and `patches.json` writing (the format is specified
and the reader is designed around it, but nothing writes patches yet), and EPUB, which
is a separate v2 — a reflowable document has no stable coordinates, so its anchoring
model is incompatible with this one.

## Getting a book in

1. Open [`notebooks/rce_pipeline.ipynb`](notebooks/rce_pipeline.ipynb) in Colab, upload
   your PDF, and run it. Start with a chapter (`FIRST_PAGE` / `LAST_PAGE`) whose
   content you know.
2. Check step 7 — it draws the extracted boxes on the rendered page. If the frames sit
   on the moves, the geometry is right.
3. Download the `.rce` and open it in the app.

## Running the app

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
