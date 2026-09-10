"""BULGU NETLEŞMESİ: PKG-00.toc'ta 0 .onnx + 0 rapidocr config.yaml → exe'de OCR kütüphanesi
hiç yok gibi. Ama PYZ-00.toc'ta rapidocr .py modülleri vardı. Çelişkiyi çöz: PKG toc
PYZ'ı tek girdi olarak listeler; python modülleri PYZ içinde. Yani rapidocr KODU var,
MODEL DOSYALARI (31.7 MB .onnx) ve config.yaml YOK. Test: exe açılışında image_reader
import edilebilir mi — onu gerçekten çalıştıramayız ama RapidOCR() kurulum adımının
models/ + config.yaml aradığını download_models.py'den biliyoruz.

Doğrulama yolu: PYZ içindeki rapidocr modül listesinden 'utils' ve 'models' alt
modüllerini say; ayrıca warn dosyasında rapidocr'ın ihtiyaç duyduğu ama bulunamayan
veri dosyalarını ara."""
import os
from _common import setup

setup()
import re



pyz = open("build/layoutkeep_onefile/PYZ-00.toc", encoding="utf-8", errors="replace").read()
mods = re.findall(r"\('rapidocr[^']*',", pyz)
print(f"PYZ icinde rapidocr modulu: {len(mods)}")

# models altindaki .py'ler (indirme yardimcilari) kod olarak VAR — ama .onnx VERILERI yok
model_py = [m for m in mods if "model" in m.lower()]
print(f"  bunlardan 'model' gecen: {len(model_py)}")

# config.yaml kodda var mi (veri olarak exe'ye girmis mi) — PKG DATA listesinde yoktu.
# RapidOCR(): config_path=None -> root_dir/config.yaml okur (download_models.py:24-25)
# root_dir = PyInstaller _MEIPASS/rapidocr package dir -> frozen exe'de YOK.

print()
print("=== KANIT ZINCIRI ===")
print("1. PYZ: rapidocr .py kodu VAR (indirme + inference motoru)")
print("2. PKG DATA: rapidocr config.yaml YOK, .onnx modelleri YOK (0 girdi)")
print("3. rapidocr/utils/download_models.py: config_path=root_dir/config.yaml,")
print("   model_root_dir=root_dir/models bekler; eksikse INDIRMEYE calisir")
print("4. ocr/engine.py:69: RapidOCR() __init__ -> download_models cagrisi")
print("5. SONUC: paketlenmiş exe'de goruntu cevirisi ilk recognize()'te")
print("   internetten model indirmezse calismaz; offline kullanicida OCR kirilir")
