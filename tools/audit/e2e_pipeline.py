"""E2E: küçük bir PDF'i fake provider ile baştan sona çevir — pipeline'ın tümü çalışıyor mu?
Ayrıca sığdırma (fitting) retranslate maliyetini ölç: kaç ek istek çıkıyor?"""
import os
import sys
import time
from _common import TMP, setup

setup()




from layoutkeep.readers.pdf_reader import read_pdf
from layoutkeep.core.docir import segments_from_document, apply_segments
from layoutkeep.providers.protected import ProtectedProvider
from layoutkeep.providers.openai_compat import OpenAICompatProvider
from layoutkeep.fitting.pdf_pass import fit_pdf_pass
from layoutkeep.fitting import FitMode

# Istek sayacı: OpenAICompatProvider._chat'u sarmalayarak kac HTTP istegi cikti sayalim
class CountingProvider(OpenAICompatProvider):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = 0
        self.segments_sent = []

    def _chat(self, messages):
        self.calls += 1
        self.segments_sent.append(len(messages[1]["content"]))
        return super()._chat(messages)

# Fake sunucu: LM Studio calismiyorsa pratik olmasi icin zaman olcumu ayri yapilacak
# Bunun yerine provider'i direkt kullanicaz ama _chat'u mock'layalim.
class MockChatProvider(CountingProvider):
    def __init__(self):
        super().__init__(base_url="http://localhost:9999/v1", model="mock")

    def _chat(self, messages):
        self.calls += 1
        # Basit cevirici: JSON dizisi dondur
        import json
        items = json.loads(messages[1]["content"])
        reply = json.dumps([{"id": i["id"], "text": f"TR-{i['text']}"} for i in items], ensure_ascii=False)
        return reply

src = "_artifacts/input/two_column.pdf"
doc = read_pdf(src)
segs = segments_from_document(doc)
print(f"two_column.pdf: {len(doc.pages)} pages, {len(segs)} segments")

provider = MockChatProvider()
prot = ProtectedProvider(provider)

t0 = time.monotonic()
translated = prot.translate(segs, "en", "tr")
t1 = time.monotonic()
print(f"translate: {len(translated)} segments in {t1-t0:.2f}s, HTTP(chat) istek sayisi={provider.calls}")

# Fitting pass: retranslate callback'i gercek provider'a bagla (mock)
fit_calls = {"n": 0}
def retranslate(segment, budget):
    fit_calls["n"] += 1
    return f"TR-{segment.source}"[:budget]

from layoutkeep.writers.pdf_writer import write_pdf
out = os.path.join(TMP, "two_col.tr.pdf")
t0 = time.monotonic()
stats = fit_pdf_pass(doc, translated, retranslate=retranslate, mode=FitMode.STRICT, target_lang="tr")
t1 = time.monotonic()
print(f"fitting: {stats} in {t1-t0:.2f}s, retranslate cagrilari={fit_calls['n']}")

orphans = apply_segments(doc, translated)
print(f"orphans: {len(orphans)}")
write_pdf(doc, src, out)
print(f"write_pdf OK -> {out} ({os.path.getsize(out)} bytes)")
