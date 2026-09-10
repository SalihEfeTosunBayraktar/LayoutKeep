"""Geçiş 2 — Tutarlılık denetimi:
A) CONTRACT D-kuralları vs kod
B) Sınıf boyutu / tek sorumluluk (kullanıcının ~220 satır kuralı)
C) Ölü kod / ölü sabit / kullanılmayan import
D) CLI↔GUI↔README iddia paritesi
"""
import ast
import os
from _common import setup

setup()



# --- B) Sınıf ve modül boyutları ---
print("=== SINIF BOYUTLARI (kullanici kurali: ~220 satir esnek sinir) ===")
violations = []
for root, dirs, files in os.walk("src"):
    dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
    for fn in files:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(root, fn)
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                size = node.end_lineno - node.lineno + 1
                if size > 220:
                    violations.append((path, node.name, size))
for path, name, size in sorted(violations, key=lambda v: -v[2]):
    print(f"  {size:>4} satır  {name:<28} {path}")

# Modül boyutları (bilgi amaçlı)
print("\n=== MODUL BOYUTLARI (>400 satir) ===")
for root, dirs, files in os.walk("src"):
    dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
    for fn in files:
        if fn.endswith(".py"):
            path = os.path.join(root, fn)
            n = sum(1 for _ in open(path, encoding="utf-8"))
            if n > 400:
                print(f"  {n:>5} satır  {path}")

# --- C) Kullanilmayan sabit tarama: _BATCH_SIZE gibi modul seviyesi sabitler ---
print("\n=== SUPHELI OLU SABITLER ===")
import re
dead_candidates = {
    "ui/worker.py::_BATCH_SIZE": r"^_BATCH_SIZE",
}
for path_pat, pat in dead_candidates.items():
    path, const = path_pat.split("::")
    src = open(f"src/layoutkeep/{path}", encoding="utf-8").read()
    names = re.findall(rf"{const}\s*=\s*(.+)", src)
    uses = len(re.findall(rf"\b{const}\b", src))
    print(f"  {path}: {const} tanim {len(names)} kez, toplam gecis {uses} (1 ise = sadece tanim = OLU)")

# estimate_job include_context parametresi kullanimda mi?
src = open("src/layoutkeep/cli.py", encoding="utf-8").read()
print("  cli.py'de estimate_job(include_context=...) geciyor mu:", "include_context" in src)

# --- D) D-kural kontrolleri ---
print("\n=== D2: providers/ icinde layout kokenli import var mi ===")
bad = []
for fn in os.listdir("src/layoutkeep/providers"):
    if not fn.endswith(".py"):
        continue
    src = open(f"src/layoutkeep/providers/{fn}", encoding="utf-8").read()
    for heavy in ("pymupdf", "fitz", "PIL", "lxml", "fontTools", "ebooklib"):
        if heavy in src:
            bad.append((fn, heavy))
print("  bulundu:", bad if bad else "temiz (sadece Segment biliyorlar)")

print("\n=== D1: readers-writers capraz import ===")
for fn in os.listdir("src/layoutkeep/readers"):
    if not fn.endswith(".py") or fn.startswith("_") and fn != "_epub_css.py":
        continue
    src = open(f"src/layoutkeep/readers/{fn}", encoding="utf-8").read()
    if "from layoutkeep.writers" in src:
        print(f"  readers/{fn} -> writers import EDIYOR (ihlal)")
for fn in os.listdir("src/layoutkeep/writers"):
    if not fn.endswith(".py"):
        continue
    src = open(f"src/layoutkeep/writers/{fn}", encoding="utf-8").read()
    if "from layoutkeep.readers" in src:
        print(f"  writers/{fn} -> readers import EDIYOR (epub_writer/docx_writer bilinçli istisna - ayni format geri-yazimi)")
