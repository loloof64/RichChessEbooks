"""Extract chess moves from a PDF chess book and package them as a `.rce`.

The five steps described in the project's CLAUDE.md, one module each:

1. :mod:`rce_pipeline.extract`  — text and per-character geometry
2. :mod:`rce_pipeline.notation` — figurine or letters, and which language
3. :mod:`rce_pipeline.tokenize` — typed tokens, each keeping its box
4. :mod:`rce_pipeline.parse`    — move tree, legality, FEN reconstruction
5. :mod:`rce_pipeline.package`  — the `.rce` archive

:func:`rce_pipeline.pipeline.run` chains them and writes one artefact per step.

:mod:`rce_pipeline.scan` sits beside step 1 and is used only on scanned books,
where the text layer cannot be read and the page has to be looked at instead.
Nothing downstream consumes it yet.
"""

from .pipeline import PipelineResult, run

__all__ = ["PipelineResult", "run", "__version__"]

__version__ = "0.1.0"
