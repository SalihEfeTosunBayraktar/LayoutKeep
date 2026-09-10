"""Bundle boyut + interleaved testler + retranslate maliyet analizi."""
import os
import sys
from _common import setup

setup()




# 1) Fit DEFAULT_BATCH_CHARS=2000: 5 segment iceren bir kitap batchinde gercek istek boyu?
import pymupdf
from layoutkeep.readers.epub_reader import read_epub
from layoutkeep.core.docir import segments_from_document

doc = read_epub("_artifacts/corpus/pg11.epub")
segs = segments_from_document(doc)
chars = [len(s.source) + len(s.context_before) + len(s.context_after) for s in segs]
print(f"pg11: {len(segs)} segments, total chars={sum(chars)}, max={max(chars)}, mean={sum(chars)/len(chars):.0f}")

# 2000 char budget kac istek yapar? (tek segment 2000'i asarsa kendi batchi)
req = 0
cur = 0
count = 0
for c in chars:
    if count and cur + c > 2000:
        req += 1
        cur = c
        count = 1
    else:
        cur += c
        count += 1
if count:
    req += 1
print(f"DEFAULT_BATCH_CHARS=2000 -> ~{req} request (batch size 1 oldugu durumda)")

# 2) dist/LaoyutKeep.exe boyutu
exe = "dist/LayoutKeep.exe"
if os.path.exists(exe):
    print(f"\ndist/LayoutKeep.exe: {os.path.getsize(exe)/1e6:.1f} MB")

# 3) font bundle boyutu
total = 0
for root, _, files in os.walk("src/layoutkeep/assets/fonts"):
    for f in files:
        if f.endswith((".ttf", ".otf")):
            total += os.path.getsize(os.path.join(root, f))
print(f"bundled fonts total: {total/1e6:.1f} MB")
