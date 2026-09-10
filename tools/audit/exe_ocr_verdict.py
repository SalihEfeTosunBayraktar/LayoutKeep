"""KESİN TEST: dist/LaoyutKeep.exe'de OCR gerçekten çalışıyor mu?
Exe'yi çalıştırıp image_reader import'unu deneyemeyiz (GUI), ama PKG içeriğini
ayıklayabiliriz: PyInstaller onefile archive'ı PKG-00.toc'ta listelenen her şeyi içerir.
Eğer rapidocr/models/*.onnx datas olarak eklenmemişse, exe'de OCR ÇALIŞMAZ."""
import os
from _common import setup

setup()
import re



# PKG-00.toc: exe'ye giren HER SEYIN listesi (pure python + binaries + datas + zip)
content = open("build/layoutkeep_onefile/PKG-00.toc", encoding="utf-8", errors="replace").read()

# 'rapidocr' ile ilgili tum girdiler
entries = re.findall(r"\('[^']*',\s*'[^']*'", content)
rapid = [e for e in entries if "rapidocr" in e.lower()]
print(f"PKG icinde rapidocr girdisi: {len(rapid)}")

# .onnx uzantili gercek dosya girdileri
onnx = [e for e in entries if e.lower().endswith(".onnx'")]
print(f"PKG icinde .onnx dosyasi: {len(onnx)}")
for e in onnx[:5]:
    print("  ", e[:150])

# config.yaml? rapidocr config dosyasi
cfg = [e for e in entries if "config.yaml" in e.lower() and "rapidocr" in e.lower()]
print(f"PKG icinde rapidocr config.yaml: {len(cfg)}")

# Font datas'lari dogrula (karsilastirma icin: bunlar spec'te var)
fonts = [e for e in entries if "assets/fonts" in e.lower()]
print(f"PKG icinde assets/fonts dosyalari: {len(fonts)} (karsilastirma: bunlar calisiyor)")

print()
if not onnx:
    print(">>> SONUC: exe icinde OCR .onnx modelleri YOK.")
    print(">>> RapidOCR ilk recognize() cagrisinda root_dir/models altina bakacak")
    print(">>> (PyInstaller frozen _MEIPASS'te boyle bir klasor yok) ve indirme ")
    print(">>> deneyecek (offline kullanicida crash) ya da FileNotFoundError.")
