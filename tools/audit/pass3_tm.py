"""Geçiş 3 devam: çeviri belleği gerçek SQLite + CachedProvider zinciri; context_blocks=0 yolu;
PDF sayfa aralığı (worker._filter_segments) ile CLI'da page-range YOK kontrolü."""
import os
import sys
from _common import TMP, setup

setup()




from layoutkeep.core.docir import segments_from_document
from layoutkeep.readers.epub_reader import read_epub
from layoutkeep.providers.protected import ProtectedProvider
from layoutkeep.providers.cached import CachedProvider
from layoutkeep.providers.memory import TranslationMemory
from layoutkeep.providers.fake import FakeProvider


db = os.path.join(TMP, "tm_test.sqlite")
if os.path.exists(db):
    os.remove(db)

doc = read_epub("_artifacts/input/sample.epub")
segs = segments_from_document(doc)

memory = TranslationMemory(db)
cached = CachedProvider(FakeProvider(), memory, "fake:model-1")
prot = ProtectedProvider(cached)

# 1. geçiş
out1 = prot.translate(segs, "en", "tr")
print(f"1. geçiş: {sum(1 for s in out1 if s.from_memory)} memory hit, {len(out1)} segment")
st = memory.stats()
print(f"   bellek: hits={st['hits']} misses={st['misses']} entries={st['entries']}")

# 2. geçiş — hepsi bellekten gelmeli
doc2 = read_epub("_artifacts/input/sample.epub")
segs2 = segments_from_document(doc2)
out2 = prot.translate(segs2, "en", "tr")
print(f"2. geçiş: {sum(1 for s in out2 if s.from_memory)} memory hit, {len(out2)} segment")
st = memory.stats()
print(f"   bellek: hits={st['hits']} misses={st['misses']} entries={st['entries']}")

# 3. geçiş: FARKLI model kimliği — bellek isabet etmemeli
memory3 = TranslationMemory(db)
cached3 = CachedProvider(FakeProvider(), memory3, "fake:model-2")
out3 = cached3.translate(segs2, "en", "tr")
print(f"3. geçiş (baska model): {sum(1 for s in out3 if s.from_memory)} memory hit (0 olmali)")

# 4) context_blocks=0 yolu
segs_n = segments_from_document(doc, context_blocks=0)
ctx_chars = sum(len(s.context_before) + len(s.context_after) for s in segs_n)
print(f"\ncontext_blocks=0: {len(segs_n)} segment, context {ctx_chars} kr (0 olmali)")

# 5) review bayrağı belleğe giriyor mu? needs_review'lu segment saklanirsa geri donen bayraksiz geliyor
from layoutkeep.core.docir import Segment
mem4 = TranslationMemory(os.path.join(TMP, "tm4.sqlite"))
flagged = Segment(block_id="x", source="A longer source sentence here", target=" çeviri")
flagged.needs_review = True
flagged.review_reason = "test"
mem4.put(flagged, "en", "tr", "m")
back = mem4.get(Segment(block_id="x", source="A longer source sentence here"), "en", "tr", "m")
print(f"\nbayrakli segment bellekten dondu: needs_review={back.needs_review} (False = bayrak kaybolur)")
