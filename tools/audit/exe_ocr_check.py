"""Paketlenmiş exe'de OCR model dosyaları var mı? RapidOCR ~31 MB .onnx ağırlığını nereden bulur?"""
import os
from _common import setup

setup()
import zipfile



exe = "dist/LayoutKeep.exe"
print("exe size:", os.path.getsize(exe) / 1e6, "MB")

# venv icinde rapidocr modelleri nerede?
import pathlib
venv_rapidocr = pathlib.Path(".venv/Lib/site-packages/rapidocr")
onnx_files = list(venv_rapidocr.rglob("*.onnx"))
total = sum(f.stat().st_size for f in onnx_files)
print(f"venv rapidocr .onnx files: {len(onnx_files)} adet, {total/1e6:.1f} MB")
for f in onnx_files[:6]:
    print("  ", f.relative_to(venv_rapidocr), f"{f.stat().st_size/1e6:.1f} MB")

# PyInstaller onefile exe'nin icerisinde 'rapidocr' veri dosyalari (onnx) var mi?
# onefile: icerik PKG icinde; kolay yol: exe'yi acmiyoruz, build toc dosyalarindan kontrol.
# PYZ sadece .py; binary/datas PKG-00.toc'ta 'TOC' listesi olarak yok — Analysis-00.toc'ta var.
found = []
for toc_name in ("build/layoutkeep_onefile/Analysis-00.toc", "build/layoutkeep_onefile/PKG-00.toc"):
    if not os.path.exists(toc_name):
        continue
    with open(toc_name, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    hits = [ln.strip() for ln in content.splitlines() if ".onnx" in ln.lower()]
    if hits:
        found.append((toc_name, hits))
if found:
    for name, hits in found:
        print(f"\n{name} icinde .onnx satirlari: {len(hits)}")
        for h in hits[:5]:
            print("  ", h[:150])
else:
    print("\n>>> TOC dosyalarinda HIC .onnx yok — exe icinde OCR modelleri yok muhtemelen")
