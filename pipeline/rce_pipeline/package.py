"""Step 5 — write the `.rce` archive.

The archive is a plain ZIP so that anything can open it, and the source
document goes in byte-for-byte: the app renders the book the publisher
shipped, never a re-encoded copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from typing import Any

from .notation import NotationReport
from .parse import ParseResult

SCHEMA_VERSION = "1.0.0"
GENERATOR_NAME = "rce-pipeline"
GENERATOR_VERSION = "0.1.0"

_MEDIA_TYPES = {".pdf": "application/pdf", ".epub": "application/epub+zip"}


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    source_path: str,
    *,
    page_count: int,
    notation: NotationReport,
    counts: dict[str, int],
) -> dict[str, Any]:
    filename = os.path.basename(source_path)
    extension = os.path.splitext(filename)[1].lower()
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "path": f"source/{filename}",
            "filename": filename,
            "media_type": _MEDIA_TYPES.get(extension, "application/octet-stream"),
            "sha256": sha256_of(source_path),
            "page_count": page_count,
        },
        "notation": notation.to_json(),
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
        "counts": {key: counts[key] for key in ("games", "moves", "ok", "uncertain", "broken") if key in counts},
    }


def write_rce(
    output_path: str,
    *,
    source_path: str,
    manifest: dict[str, Any],
    parse_result: ParseResult,
) -> str:
    """Write the archive and return its path."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # The PDF is already compressed internally; storing it uncompressed
        # keeps packaging fast for no meaningful size penalty.
        archive.write(source_path, manifest["source"]["path"], compress_type=zipfile.ZIP_STORED)
        archive.writestr("manifest.json", _dump(manifest))
        archive.writestr("moves.json", _dump(parse_result.to_json()))

    return output_path


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
