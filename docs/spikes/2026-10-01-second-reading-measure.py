"""THROWAWAY spike: whole Grivas with and without the second reading, judged three ways."""
import sys, os, json, collections
from rce_pipeline import pipeline
PDF = "/home/laurent/Documents/Echecs/Ebooks/Chess College 1 Strategy - Grivas.pdf"
res = pipeline.run(PDF, work_dir=sys.argv[1] + "/m", output_path=None,
                   glyph_model="rce_pipeline/data/classifier.pkl", write_artefacts=False)
moves = [(m.page, m.san, m.status) for m in res.parsed.moves]
verdicts = collections.Counter(c["verdict"] for c in res.parsed.diagram_checks)
json.dump({"moves": moves, "verdicts": verdicts}, open(sys.argv[2], "w"))
