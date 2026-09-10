"""Taranmış PDF testi - sadece görüntü içeren sayfa (text layer yok)."""
import os
import sys
from _common import TMP, setup

setup()




import pymupdf
from layoutkeep.readers.pdf_reader import read_pdf

tmp = os.path.join(TMP, "blank_scan.pdf")
d = pymupdf.open()
page = d.new_page(width=612, height=792)
pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 200))
page.insert_image(pymupdf.Rect(50, 50, 550, 350), pixmap=pix)
d.save(tmp)
d.close()

doc = read_pdf(tmp)
print(f"image-only PDF: blocks={sum(len(p.blocks) for p in doc.pages)}, "
      f"ImageRefs={sum(len(p.images) for p in doc.pages)}")
print("Sonuc: metin katmanı olmayan taranmış PDF -> 0 blok, 0 ImageRef.")
print("pdf_reader'da is_scanned_page/OCR cagrisi yok; goruntu sessizce kaybolur.")
