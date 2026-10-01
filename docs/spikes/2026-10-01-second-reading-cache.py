"""THROWAWAY spike: Tesseract words of every Grivas page, symbols painted as letters, in PDF points."""
import sys, subprocess, csv, io, json, os
from concurrent.futures import ThreadPoolExecutor
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from rce_pipeline import pipeline

PDF = "/home/laurent/Documents/Echecs/Ebooks/Chess College 1 Strategy - Grivas.pdf"
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
DPI, FONT = 400, "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
res = pipeline.run(PDF, work_dir=OUT + "/w", output_path=None, glyph_model="rce_pipeline/data/classifier.pkl",
                   write_artefacts=False)
glyphs = res.glyphs or []
doc = pymupdf.open(PDF); scale = DPI / 72.0
jobs = []
for number in range(1, doc.page_count + 1):
    pg = doc[number - 1]; H = pg.rect.height
    pix = pg.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples).convert("RGB")
    draw = ImageDraw.Draw(img)
    for g in (g for g in glyphs if g.page == number):
        b = g.bbox
        x0, y0, x1, y1 = (b.x - .6) * scale, (H - b.y - b.h - .6) * scale, (b.x + b.w + .6) * scale, (H - b.y + .6) * scale
        draw.rectangle([x0, y0, x1, y1], fill="white")
        draw.text((x0, y0), g.piece, fill="black", font=ImageFont.truetype(FONT, int((y1 - y0) * .95)))
    path = f"{OUT}/p{number}.png"; img.save(path); jobs.append((number, path, H))

def read(job):
    number, path, H = job
    tsv = subprocess.run(["tesseract", path, "stdout", "-l", "eng", "--psm", "3", "tsv"],
                         capture_output=True, text=True).stdout
    words = []
    for r in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if r["level"] == "5" and (r.get("text") or "").strip():
            L, T, W, Hh = (int(r[k]) for k in ("left", "top", "width", "height"))
            words.append({"text": r["text"], "x": L / scale, "y": H - (T + Hh) / scale, "w": W / scale, "h": Hh / scale,
                          "line": [int(r["block_num"]), int(r["par_num"]), int(r["line_num"])]})
    os.remove(path)
    return number, words

with ThreadPoolExecutor(8) as pool:
    cache = dict(pool.map(read, jobs))
json.dump(cache, open(OUT + "/words.json", "w"))
print("pages", len(cache), "words", sum(len(v) for v in cache.values()))
