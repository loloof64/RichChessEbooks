# The `.rce` format — v1.0.0

A Rich Chess Ebook (`.rce`) is a ZIP archive that pairs an untouched source document
with the chess data extracted from it.

```
book.rce
├── source/book.pdf     the original file, byte-for-byte unchanged
├── manifest.json       metadata, schema versions, source hash
├── moves.json          extracted moves — written by the pipeline, immutable
└── patches.json        user corrections — written by the Flutter app only (optional)
```

`source/` holds exactly one file. The reader locates it through
`manifest.source.path`, never by guessing the name.

JSON Schemas for the three documents live in [`schemas/`](schemas/). They are the
normative reference; this page explains the intent behind them.

## Coordinate system

This is the one place where a silent mistake costs the most, so it is stated
explicitly and only once.

`bbox` values in `moves.json` use **PDF user-space points, origin at the bottom-left
of the page**, matching the PDF specification:

- `x` — distance from the left page edge to the left edge of the box
- `y` — distance from the **bottom** page edge to the **bottom** edge of the box
- `w`, `h` — width and height, both positive

Coordinates are expressed in the page's *rotated* (visible) space, so a page with
`/Rotate 90` is described as the reader sees it. `page` is **1-based**.

Two consequences, one per component:

- **Pipeline** — PyMuPDF reports text boxes with the origin at the top-left and `y`
  growing downwards. It must convert before writing: `y_rce = page_height - y1_mupdf`
  (where `y1_mupdf` is the *bottom* edge in MuPDF space, i.e. the larger value).
- **App** — `pdfrx` reports page dimensions in points and lays page overlays out in
  Flutter's top-left-origin space. Converting one box is a scale plus a `y` flip:

  ```dart
  final scale = pageRectInViewer.width / page.width;
  Rect.fromLTWH(
    bbox.x * scale,
    (page.height - bbox.y - bbox.h) * scale,   // flip to top-left origin
    bbox.w * scale,
    bbox.h * scale,
  )
  ```

  Because `pageRectInViewer` already carries the viewer's zoom and scroll, `scale` is
  the only factor to apply — the overlay stays aligned at any zoom level.

## `manifest.json`

```json
{
  "schema_version": "1.0.0",
  "source": {
    "path": "source/book.pdf",
    "filename": "book.pdf",
    "media_type": "application/pdf",
    "sha256": "3b1f…",
    "page_count": 210
  },
  "notation": { "style": "figurine_unicode", "language": "fr", "confidence": 0.98 },
  "generator": { "name": "rce-pipeline", "version": "0.1.0", "generated_at": "2026-08-11T09:12:00Z" },
  "counts": { "games": 3, "moves": 412, "ok": 400, "uncertain": 10, "broken": 2 }
}
```

`source.sha256` is the hash of the original file's bytes. The app compares it against
the `source_sha256` recorded in `patches.json`: a mismatch means the corrections were
written against a different edition of the book and their `bbox` values can no longer
be trusted.

`notation.style` is one of:

| value               | meaning                                                             |
| ------------------- | ------------------------------------------------------------------- |
| `figurine_unicode`  | pieces are Unicode chess characters (U+2654–U+265F) — v1 target      |
| `figurine_font`     | pieces are latin letters rendered through a figurine font            |
| `letters`           | pieces are plain letters; `language` says which alphabet             |

v1 of the pipeline parses `figurine_unicode`, and `letters` once `language` is known.

`figurine_font` is detected but cannot be parsed: its text layer holds latin letters
bearing no relation to the pieces drawn, so there is nothing in the characters to read.

For `letters`, `language` is not decoration — it decides which alphabet the piece
initials come from, and the alphabets overlap. `R` is the King in French and the Rook
in English; both readings are frequently legal in the same position, so the wrong
language does not fail, it produces a different game.

## `moves.json`

```json
{
  "schema_version": "1.0.0",
  "games": [
    { "id": "g1", "title": "Fischer – Spassky, Reykjavík 1972 (1)",
      "initial_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
      "root_move_id": "g1-m1",
      "position_known": true }
  ],
  "moves": [
    {
      "id": "g1-m1",
      "game_id": "g1",
      "parent_id": null,
      "san": "e4",
      "uci": "e2e4",
      "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
      "ply": 1,
      "page": 12,
      "bbox": { "x": 72.0, "y": 640.2, "w": 18.4, "h": 9.6 },
      "variation_index": 0,
      "comment": null,
      "confidence": 1.0,
      "status": "ok"
    }
  ]
}
```

A move is a node in a tree, not a row in a list:

- `parent_id` — the move played immediately before, `null` for a game's first move.
  Variations are reconstructed by following these links; the array order carries no
  meaning.
- `variation_index` — `0` on the main line, `>0` inside a variation. Siblings of the
  same parent are distinguished by it.
- `fen` — the position **after** `san` has been played. This is what the board shows.
- `uci` — the same move in long algebraic form (`e2e4`, `e7e8q`). The app reads it
  directly to highlight the from/to squares rather than re-deriving them, which keeps
  rendering independent of SAN disambiguation.
- `ply` — 1-based half-move count within the game, used to label `12.` / `12…`.
- `page` / `bbox` — where the move is printed. `bbox` covers the move token alone,
  not the surrounding sentence.

`status` is set by the pipeline's legality pass:

| value       | meaning                                                                |
| ----------- | ---------------------------------------------------------------------- |
| `ok`        | the move is legal in its parent position and unambiguous                |
| `uncertain` | accepted after an OCR-style repair (`0`↔`O`, `l`↔`1`, `B`↔`8`, `x`↔`×`) |
| `broken`    | no legal reading found; `fen` and `uci` are `null`                      |

`confidence` is a `[0, 1]` hint driving the overlay colour in the app. A `broken`
move still carries `page` and `bbox` so the user can find and fix it.

`position_known` on the game is `false` when the book never printed where that game
starts — analysis quoted after a result (*"Black resigned in view of 27…Rf6 28 d5"*),
or a run of pages opening in mid-score with no diagram to seed it. `initial_fen` is
then a placeholder, every move is `broken`, and the app should offer the moves for
correction without showing a board: the pipeline knows the squares the book printed
and nothing about the position they were printed in. A diagram the book *did* print
lifts this — it gives the game its starting position, and the moves are scored
normally.

Fields not listed in the schema are ignored by the app rather than rejected, so the
pipeline can add diagnostics without breaking older builds.

## `patches.json`

`moves.json` is never edited. Corrections are layered on top of it at read time, so
re-running the pipeline on an improved parser does not discard manual work.

```json
{
  "schema_version": "1.0.0",
  "source_sha256": "3b1f…",
  "patches": [
    { "move_id": "g1-m24", "type": "san_edit",
      "value": { "san": "Nbd2" },
      "source": "user", "timestamp": "2026-08-11T10:04:31Z" }
  ]
}
```

| `type`         | `value`                          | effect                                              |
| -------------- | -------------------------------- | --------------------------------------------------- |
| `san_edit`     | `{ "san": "Nbd2" }`              | move retyped; revalidated by `dartchess`, FEN recomputed |
| `bbox_edit`    | `{ "page": 12, "bbox": { … } }`  | clickable zone redrawn by hand                      |
| `fen_override` | `{ "fen": "…" }`                 | position entered directly — diagrams with no move, non-standard positions |

Patches apply in array order; the last one of a given `type` for a given `move_id`
wins.

A `san_edit` or `fen_override` **propagates**: every descendant is replayed from the
corrected position until a move turns out illegal (that one becomes `broken`, and the
subtree below it stops) or the line ends. This is why a correction is worth making —
one fix repairs the rest of the line.
