"""Step 0 — an EPUB or a DjVu book becomes a PDF before anything reads it.

The app renders PDF only, and every later step reads PDF geometry, so the
archive carries the converted PDF rather than the book as shipped. An EPUB is
laid out into pages by PyMuPDF and keeps its text; a DjVu is a scan, turned
into image pages by `ddjvu` (djvulibre) and read like any other scan.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pymupdf

DJVU_TIMEOUT = 3600  # seconds; a 500-page scan takes minutes, never an hour


def kind_of(path: str) -> str:
    """"pdf", "epub" or "djvu", from the first bytes — never from the name."""
    with open(path, "rb") as handle:
        head = handle.read(64)
    if head.startswith(b"AT&TFORM"):
        return "djvu"
    # The EPUB container requires an uncompressed `mimetype` entry first.
    if head.startswith(b"PK\x03\x04") and b"mimetypeapplication/epub+zip" in head:
        return "epub"
    return "pdf"


def to_pdf(path: str, work_dir: str) -> str:
    """`path` itself for a PDF, else the PDF it was converted into in `work_dir`."""
    kind = kind_of(path)
    if kind == "pdf":
        return path
    os.makedirs(work_dir, exist_ok=True)
    target = os.path.join(work_dir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    if kind == "epub":
        with pymupdf.open(path, filetype="epub") as book:
            with pymupdf.open("pdf", book.convert_to_pdf()) as pdf:
                pdf.save(target, garbage=3, deflate=True)
        return target
    ddjvu = shutil.which("ddjvu")
    if ddjvu is None:
        raise RuntimeError(
            "a DjVu book needs ddjvu: install djvulibre "
            "(Debian/Ubuntu: sudo apt install djvulibre-bin, macOS: brew install djvulibre)"
        )
    # Absolute paths, so a file named `-something` is never taken for an option.
    subprocess.run(
        [ddjvu, "-format=pdf", "-quality=85", os.path.abspath(path), os.path.abspath(target)],
        check=True, timeout=DJVU_TIMEOUT, capture_output=True,
    )
    return target
