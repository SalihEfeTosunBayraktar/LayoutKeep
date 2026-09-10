"""Bulgu netleştirme: .lkproj girdi + yeniden çeviri davranışı.
1) .lkproj girdiğinde reader olarak load_project çalışıyor — segment'ler zaten ÇEVRİLMİŞ
   metinden üretilir mi (çift çeviri hatası), yoksa source_text'ten mi?
2) Yeniden çeviri sonrası ilk geçişin review bayrakları kayboluyor mu?"""
import os
import sys
from _common import TMP, setup

setup()




from layoutkeep.core.docir import load_project, segments_from_document

doc = load_project(os.path.join(TMP, "w4-full.lkproj"))

# .lkproj'ten segment uretimi: bloklarin MEVCUT metni (cevrilmis) mi kaynagi?
# Block.text, lines'tan gelir; apply_segments sonrasi lines = ceviri icerir.
sample = [b for _, b in doc.iter_blocks() if b.source_text][:3]
for b in sample:
    print(f"block {b.id[:40]}")
    print(f"  block.text (mevcut) = {b.text[:70]!r}")
    print(f"  source_text (orijinal) = {b.source_text[:70]!r}")
    print()

segs = segments_from_document(doc)
seg = segs[5]
print("segment[5].source neyden uretildi?", repr(seg.source[:70]))
print("-> source == block.text ise ceviri ZATEN uygulanmis, tekrar cevrilir (cift ceviri)")
print("-> source == source_text olsaydi D5 'kaldigi yerden devam' gerceklesirdi")
