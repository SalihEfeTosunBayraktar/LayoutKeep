"""Geçiş 1 kontrol: (1) OCR/DOCX testleri CI extra'ları yoksa koşmaz; (2) RTL dil + font zinciri."""
import os
import sys
from _common import setup

setup()




# 1) OCR/DOCX testleri importorskip'siz ise CI'da ImportError ile koşmaz -> exe'de OCR/DOCX asla test edilmemis
import subprocess

r = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_ocr_engine.py", "tests/test_docx_reader.py",
     "tests/test_inpaint.py", "--collect-only", "-q"],
    capture_output=True, text=True, timeout=120,
    cwd=r"C:\MyProjects\AntigravityProjects\AI_and_LLM\LayoutKeep",
    env={**os.environ, "PYTHONPATH": "src"},
)
lines = r.stdout.strip().splitlines()
print("collect-only sonuc (son 5 satir):")
for ln in lines[-5:]:
    print(" ", ln)

# 2) RTL dil (ar/hz) + font: REQUIRED_GLYPHS'ta yok -> resolve_font ne yapar?
from layoutkeep.fitting.fontmatch import REQUIRED_GLYPHS, resolve_font

print("\nREQUIRED_GLYPHS dilleri:", sorted(REQUIRED_GLYPHS.keys()))
print("ar listede mi:", "ar" in REQUIRED_GLYPHS)
m = resolve_font("Arial", "ar")
print("resolve_font('Arial','ar') ->", m.quality, m.resolved_path if hasattr(m, "resolved_path") else m)

# 3) UI dil listesinde Latin-olmayan kac dil var? (CONTRACT D4: Faz 1 Latin-only)
from layoutkeep.ui.languages import LANG_DEFINITIONS

NON_LATIN = {"ar", "ru", "zh", "ja", "ko", "he", "hi", "fa", "el", "uk"}
offered = [code for code, _ in LANG_DEFINITIONS if code in NON_LATIN]
print("\nUI'da sunulan ama Faz-1 Latin kapsami disindaki diller:", offered)
