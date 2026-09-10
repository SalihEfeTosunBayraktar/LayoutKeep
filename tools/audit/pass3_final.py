"""Geçiş 3 son — B27 (çift çeviri) ve B28 (bayrak kaybı) kanıtlarının CLI üzerinden doğrulanması
+ GUI worker page_range akışı + README 'skip+limit' davranış karşılaştırması."""
import os
import subprocess
import sys
from _common import TMP, setup

setup()


env = {**os.environ, "PYTHONPATH": "src"}
PY = sys.executable



def run(args, timeout=300):
    r = subprocess.run([PY, "-m", "layoutkeep.cli", *args],
                       capture_output=True, text=True, env=env, timeout=timeout)
    return r.returncode, [ln for ln in (r.stdout + r.stderr).splitlines() if "timestamp" not in ln]


# --- B27: .lkproj iki kez cevriliyor mu? Ilk ceviri 'Form  W-4' -> '[tr] Form  W-4'
# Ikinci kez cevirirsek '[tr] [tr] Form W-4' mi olur? (fake provider onemli degil — davranis)
w4proj = os.path.join(TMP, "w4-full.lkproj")
code, out = run(["translate", w4proj, "--to", "tr", "--provider", "fake",
                 "-o", os.path.join(TMP, "w4-2pass.pdf")])
print("=== B27: .lkproj yeniden ceviri ===")
for ln in out:
    if any(k in ln for k in ("segments", "translated", "protect", "wrote")):
        print(f"  {ln}")

sys.path.insert(0, "src")
from layoutkeep.core.docir import load_project
d2 = load_project(os.path.join(TMP, "w4-2pass.pdf").replace(".pdf", ".lkproj")) if os.path.exists(os.path.join(TMP, "w4-2pass.lkproj")) else None

# CLI -o .pdf verince proje kaydetmedi; ama cevrilen metni projeden gor
# dogru yol: ikinci gecisi kaydet
code, out = run(["translate", w4proj, "--to", "tr", "--provider", "fake",
                 "--save-project", os.path.join(TMP, "w4-2pass.lkproj"),
                 "-o", os.path.join(TMP, "w4-2pass.pdf")])
d2 = load_project(os.path.join(TMP, "w4-2pass.lkproj"))
first = [b for _, b in d2.iter_blocks() if b.source_text][:3]
print("\n  2. gecis sonrasi blok metni (cift ceviri var mi):")
for b in first:
    print(f"    text={b.text[:50]!r}")
    print(f"    source_text={b.source_text[:50]!r}")

d1 = load_project(w4proj)
b1 = [b for _, b in d1.iter_blocks() if b.source_text][:3]
print("\n  1. gecis (karsilastirma):")
for b in b1:
    print(f"    text={b.text[:50]!r}")

# --- README iddiasi: '--skip N' onceki cevrilerden devam mi? Yoksa sadelee mi?
print("\n=== README 'skip' iddiasinin dogrulamasi ===")
readme = open("README.md", encoding="utf-8").read()
i = readme.find("--skip")
print(readme[i-200:i+300] if i > 0 else "(skip README'de yok)")
