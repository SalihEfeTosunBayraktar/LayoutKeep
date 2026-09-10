"""Taranmış PDF (görüntü) → DocIR ne üretiyor? pdf_reader görüntü sayfasını ne yapıyor?"""
import os
import sys
from _common import TMP, setup

setup()




import pymupdf
from layoutkeep.readers.pdf_reader import read_pdf

# outlined_text.pdf: corpus'ta "drawn text" örneği
doc = read_pdf("_artifacts/corpus/outlined_text.pdf")
total_blocks = sum(len(p.blocks) for p in doc.pages)
total_img = sum(len(p.images) for p in doc.pages)
texts = [b.text for _, b in doc.iter_blocks() if b.text.strip()]
print(f"outlined_text.pdf: pages={len(doc.pages)} blocks={total_blocks} images={total_img}")
print(f"  extracted text: {texts[:3]}")

# Bir de gerçek tarama simülasyonu: text'i olmayan bir sayfa
tmp = os.path.join(TMP, "blank_scan.pdf")
if not os.path.exists(tmp):
    d = pymupdf.open()
    page = d.new_page(width=612, height=792)
    # görüntü koy ama text yok
    img = pymupdf.utils.getImageList  # noqa
    page.insert_image(pymupdf.Rect(50, 50, 550, 300), pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 60)))
    d.save(tmp)
    d.close()
doc2 = read_pdf(tmp)
print(f"\nimage-only PDF: blocks={sum(len(p.blocks) for p in doc2.pages)}, images={sum(len(p.images) for p in doc2.pages)}")
print("  -> Hiç blok yoksa OCR'a hiç düşülmüyor (is_scanned_page pdf_reader'da çağrılmıyor)")
