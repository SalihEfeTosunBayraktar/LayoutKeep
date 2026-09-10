"""Geçiş 2 — tutarlılık denetimi (tam):
A) Sınıf boyutu (kullanıcı kuralı ~220 satır) + modül boyutları
B) .html girdi tutarsızlığı (converter listeliyor ama reader yok)
C) Ölü tunable'lar (B9 genişletme: TÜM tanımlı tunable'lar kullanılıyor mu?)
D) Ölü sabitler: NEEDS_REVIEW_THRESHOLD gibi
E) k-means 8 iterasyon maliyeti ölçümü
"""
import ast
import os
from _common import setup

setup()
import re



# --- A) Sinif boyutlari ---
print("=== A) SINIFLAR (>220 satir) ===")
viol = []
for root, dirs, files in os.walk("src"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(root, fn)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                size = node.end_lineno - node.lineno + 1
                if size > 220:
                    viol.append((size, node.name, path))
for size, name, path in sorted(viol, reverse=True):
    print(f"  {size:>4}  {name:<30} {path}")
if not viol:
    print("  (yok — tum siniflar sinirin altinda)")

print("\n=== B) MODULLER (>400 satir) ===")
for root, dirs, files in os.walk("src"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if fn.endswith(".py"):
            path = os.path.join(root, fn)
            n = sum(1 for _ in open(path, encoding="utf-8"))
            if n > 400:
                print(f"  {n:>5}  {path}")

# --- B) .html girdi tutarsizligi ---
print("\n=== C) .html GIRDI TUTARSIZLIGI ===")
conv = open("src/layoutkeep/writers/converter.py", encoding="utf-8").read()
listed = '".html"' in conv and '".htm"' in conv
reader_case = 'suffix == ".html"' in conv or 'suffix in {".html"' in conv or "'.html'" in conv.split("read_docx")[-1] if "read_docx" in conv else False
print(f"  DOCUMENT_EXTENSIONS'da .html/.htm listeli: {listed}")
print(f"  read_any_document icinde html reader case'i: {'read_docx' in conv and '.html' in conv[conv.find('def read_any_document'):conv.find('def _write_pdf_target')]}")
# dogru parantezle:
seg = conv[conv.find("def read_any_document"):conv.find("def _write_pdf_target")]
print(f"  (dogru segment: html case var mi -> {'.html' in seg})")

# --- C) Tum tunable'lar kullaniyor mu ---
print("\n=== D) TUNABLE KULLANIM AUDITI ===")
tun_src = open("src/layoutkeep/core/tunables.py", encoding="utf-8").read()
defined = re.findall(r'"([a-z_.0-9]+)":\s*[\(\[]?\s*(?: Tunable\()?', tun_src)
names = re.findall(r'"([a-z0-9]+\.[a-z0-9_.]+)"\s*:', tun_src)
print(f"  tanimlanan tunable: {len(names)}")
all_src = {}
for root, dirs, files in os.walk("src"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if fn.endswith(".py"):
            p = os.path.join(root, fn)
            all_src[p] = open(p, encoding="utf-8").read()
dead = []
for name in names:
    used_anywhere = False
    for p, s in all_src.items():
        if p.endswith("core/tunables.py"):
            continue
        if f'"{name}"' in s:
            used_anywhere = True
            break
    if not used_anywhere:
        dead.append(name)
print(f"  HICBIR YERDE okunmayan (olu) tunable: {len(dead)}")
for d in dead:
    print(f"    OLU: {d}")

# --- D) Olu sabit: NEEDS_REVIEW_THRESHOLD ---
print("\n=== E) OLU SABIT KONTROLU ===")
ir_path = [p for p in all_src if p.replace("\\", "/").endswith("readers/image_reader.py")][0]
ir_src = all_src[ir_path]
uses = len(re.findall(r"\bNEEDS_REVIEW_THRESHOLD\b", ir_src))
print(f"  image_reader.py NEEDS_REVIEW_THRESHOLD gecis: {uses} (tanim + test importu)")
other = sum(s.count("NEEDS_REVIEW_THRESHOLD") for p, s in all_src.items()
            if p.replace("\\", "/").endswith("readers/image_reader.py") is False
            and "test_" not in p)
print(f"  src icinde baska kullanim: {other} (0 ise kod olmus sabit — cunku bloklar tunables.get ile isaretleniyor)")

# --- E) 2-means maliyet olcumu ---
print("\n=== F) _box_colors 2-means maliyet (buyuk sayfa simülasyonu) ===")
import sys
import time
import numpy as np

rng = np.random.default_rng(42)
big = rng.integers(0, 255, size=(2000, 1500, 3), dtype=np.uint8)
from layoutkeep.core.docir import BBox  # bos onemli degil

sys_path = r"C:\MyProjects\AntigravityProjects\AI_and_LLM\LayoutKeep\src"
if sys_path not in sys.path:
    import sys
    sys.path.insert(0, sys_path)
from layoutkeep.readers.image_reader import _box_colors

t0 = time.perf_counter()
n = 0
for i in range(50):  # 50 kutu
    x0 = (i * 37) % 1200
    y0 = (i * 53) % 1800
    _box_colors(big, BBox(x0, y0, x0 + 200, y0 + 40))
    n += 1
dt = time.perf_counter() - t0
print(f"  {n} kutu (200x40 px) 2-means sure: {dt:.2f} sn -> kutu basina {dt/n*1000:.1f} ms")
print(f"  200 kutuluk gercek sayfa tahmini: {dt/n*200:.1f} sn (sadece renk olcumu)")
