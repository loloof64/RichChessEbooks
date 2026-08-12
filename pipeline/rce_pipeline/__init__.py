"""Extract chess moves from a PDF chess book and package them as a `.rce`.

The five steps described in the project's CLAUDE.md, one module each:

1. :mod:`rce_pipeline.extract`  — text and per-character geometry
2. :mod:`rce_pipeline.notation` — figurine or letters, and which language
3. :mod:`rce_pipeline.tokenize` — typed tokens, each keeping its box
4. :mod:`rce_pipeline.parse`    — move tree, legality, FEN reconstruction
5. :mod:`rce_pipeline.package`  — the `.rce` archive

:func:`rce_pipeline.pipeline.run` chains them and writes one artefact per step.

:mod:`rce_pipeline.scan` and :mod:`rce_pipeline.glyphs` sit beside step 1 and
are used only on books whose piece symbols exist nowhere but the page image — a
scan, or a book set in a figurine font. The first rebuilds the printed lines and
renders them, the second recognises the symbols in them and writes them back
into the pages as figurines, after which the rest of the pipeline is unchanged.
"""

from .pipeline import PipelineResult, run

__all__ = ["PipelineResult", "run", "__version__"]

__version__ = "0.1.0"
