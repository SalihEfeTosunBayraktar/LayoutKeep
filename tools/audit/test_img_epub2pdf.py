import os
import sys
from _common import TMP, setup

setup()




import pymupdf

from layoutkeep.readers.epub_reader import read_epub
from layoutkeep.writers.pdf_generator import generate_reflowed_pdf_from_docir

OUT_DIR = str(TMP)
os.makedirs(OUT_DIR, exist_ok=True)

# 1) E2E klasöründeki mevcut çıktı: görselli Gutenberg EPUBu -> PDF
for name in ("pg79501-images-3.out.pdf",):
    p = os.path.join("_artifacts", "e2e", name)
    if os.path.exists(p):
        d = pymupdf.open(p)
        print(f"{name}: pages={d.page_count} images={sum(len(pg.get_images()) for pg in d)}")
        d.close()
    else:
        print(f"{name}: MISSING")

# 2) Canlı test: pg23319 (görselli EPUB) oku -> PDF yaz, görüntü yaşıyor mu?
epub = os.path.join("_artifacts", "e2e", "pg23319-images-3.epub")
doc = read_epub(epub)
n_img = sum(len(p.images) for p in doc.pages)
print(f"\nlive read {os.path.basename(epub)}: pages={len(doc.pages)} ImageRefs={n_img}")

out_pdf = os.path.join(OUT_DIR, "reflow_test.pdf")
generate_reflowed_pdf_from_docir(doc, out_pdf)
d = pymupdf.open(out_pdf)
print(f"live EPUB->PDF: pages={d.page_count} images={sum(len(pg.get_images()) for pg in d)}")
d.close()

# 3) ImageRef format alanini kontrol et - extension ne?
from collections import Counter
fmts = Counter(i.fmt for p in doc.pages for i in p.images)
print("ImageRef fmts:", dict(fmts))
sizes = [len(i.data) for p in doc.pages for i in p.images]
print("ImageRef data sizes (bytes, base64):", sorted(sizes)[:5], "...", sorted(sizes)[-3:] if len(sizes) > 5 else "")
