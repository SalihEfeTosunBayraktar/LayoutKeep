"""PKG-00.toc doğru parse: ('ad', 'kaynak', 'TÜR') üçlüleri — exe içeriğinde OCR var mı?"""
import os
from _common import setup

setup()
import re


content = open("build/layoutkeep_onefile/PKG-00.toc", encoding="utf-8", errors="replace").read()

# ('name', 'path', 'TYPE') üçlü regex
triples = re.findall(r"\('([^']*)',\s*\n?\s*'([^']*)',\s*\n?\s*'(\w+)'\)", content)
print(f"toplam girdi: {len(triples)}")

onnx = [(n, p) for n, p, t in triples if n.lower().endswith(".onnx")]
print(f".onnx girdisi: {len(onnx)}")
for n, _ in onnx[:6]:
    print("  ", n)

rapidocr_any = [(n, t) for n, p, t in triples if "rapidocr" in n.lower()]
print(f"rapidocr adlı girdi: {len(rapidocr_any)} (örnekler:)")
for n, t in rapidocr_any[:5]:
    print(f"   {t}: {n}")

cfg = [(n, t) for n, p, t in triples if "config.yaml" in n.lower()]
print(f"config.yaml girdisi: {len(cfg)}")
for n, t in cfg[:8]:
    print(f"   {t}: {n}")

fonts = [n for n, p, t in triples if t == "DATA" and "fonts" in n.lower()]
print(f"DATA olarak fonts: {len(fonts)}")

data_all = [(n, t) for n, p, t in triples if t == "DATA"]
print(f"toplam DATA girdisi: {len(data_all)}")
for n, t in data_all[:30]:
    print(f"   DATA: {n[:100]}")
