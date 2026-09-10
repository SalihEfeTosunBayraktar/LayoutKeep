"""EPUB'taki tüm resim dosyaları vs reader'ın çıkardığı ImageRef sayısı — kayıp var mı?"""
import os
import sys
from _common import setup

setup()
import zipfile




from layoutkeep.readers.epub_reader import read_epub

for name in ("_artifacts/e2e/pg23319-images-3.epub", "_artifacts/e2e/pg79501-images-3.epub",
             "_artifacts/corpus/pg11.epub", "_artifacts/corpus/pg1342.epub"):
    if not os.path.exists(name):
        continue
    # zip içindeki resim dosyalari
    with zipfile.ZipFile(name) as z:
        imgs = [n for n in z.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))]
    doc = read_epub(name)
    refs = sum(len(p.images) for p in doc.pages)
    print(f"{os.path.basename(name)}: zip'te {len(imgs)} resim dosyasi, ImageRef={refs}")
