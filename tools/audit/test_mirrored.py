"""Ad-hoc incelemeler: aynalanmış metin PDF'te yanlışlıkla temizlenmiş mi?"""
import os
import sys
from _common import setup

setup()




from layoutkeep.readers.pdf_reader import read_pdf

doc = read_pdf("_artifacts/e2e/Hello How Are You Today.pdf")
for pg in doc.pages:
    for b in pg.blocks:
        print(f"block {b.id} role={b.role.value} review={b.needs_review} reason={b.review_reason!r}")
        print(f"  text={b.text[:80]!r}")
