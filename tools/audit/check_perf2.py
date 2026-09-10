"""Çeviri worker'ın gerçek çalışma şeklini simüle et: worker chunk=20, provider batch_chars=2000."""
import os
import sys
from _common import setup

setup()




from layoutkeep.readers.epub_reader import read_epub
from layoutkeep.core.docir import segments_from_document

doc = read_epub("_artifacts/corpus/pg11.epub")
segs = segments_from_document(doc)

# GUI worker: chunk_size=20 ile parçalar, sonra her chunk ProtectedProvider(CachedProvider(OpenAICompat))'a verir
# ProtectedProvider segment bazlı ilerler; OpenAICompat.translate icinde run_batches (batch_chars=2000, adaptive).
# Sim: 20'lik chunklarin karakter boyutlari
chunk = 20
sizes = []
for i in range(0, len(segs), chunk):
    c = sum(len(s.source) + len(s.context_before) + len(s.context_after) for s in segs[i:i+chunk])
    sizes.append(c)
print(f"GUI worker chunk sizes: n={len(sizes)}, mean={sum(sizes)/len(sizes):.0f}, min={min(sizes)}, max={max(sizes)}")

# CLI: hepsi tek seferde provider'a gider -> run_batches 2000-char budget ile boler
# Sim: adaptive batch size 1 baslar; her basarili batch +1 (max 20), her failure ceiling koyar.
# 2000 char budget ile kac istek?
req = 0
cur = 0
cnt = 0
cap = 1
ceiling = None
for c in [len(s.source) + len(s.context_before) + len(s.context_after) for s in segs]:
    over_chars = cnt and cur + c > 2000
    over_count = cnt and cnt >= cap
    if over_chars or over_count:
        req += 1
        cur = c
        cnt = 1
        cap = min(20, cap + 1)
    else:
        cur += c
        cnt += 1
if cnt:
    req += 1
print(f"CLI adaptive sim (no failures): ~{req} requests")

# Context oranlari: context kac karakter tasiyor?
src_only = sum(len(s.source) for s in segs)
ctx = sum(len(s.context_before) + len(s.context_after) for s in segs)
print(f"source chars={src_only}, context chars={ctx}, context share={ctx/(src_only+ctx):.1%}")
