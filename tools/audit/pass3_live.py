"""Geçiş 3 — canlı uç testleri (yeniden, sistematik):
1) .html girdi reddi (B26 kanıtı)
2) sayfa aralığı uçları (parse_page_range sessizce 'tümü'ne düşüyor!)
3) skip+limit
4) .lkproj çift-çeviri (B27 kanıtı — source_text yerine block.text)
5) bellek review bayrağı kaybı (B28 kanıtı)
6) DeepL hata yolu traceback
7) scanned PDF → OCR boşluğu (B3)
8) sığdırma ölçüm: fit öncesi/sonrası
"""
import os
import subprocess
import sys
from _common import TMP, setup

setup()


env = {**os.environ, "PYTHONPATH": "src"}
PY = sys.executable



def run(args, timeout=180):
    r = subprocess.run([PY, "-m", "layoutkeep.cli", *args],
                       capture_output=True, text=True, env=env, timeout=timeout)
    out = [ln for ln in (r.stdout + r.stderr).splitlines() if "timestamp" not in ln]
    return r.returncode, out


sys.path.insert(0, "src")

# 2) parse_page_range uclari — '0', '-1', 'abc' sessizce 'hepsi'ne dushuyor mu?
from layoutkeep.core.range_helper import parse_page_range
print("=== 1) parse_page_range sessiz fallback ===")
for expr in ["0", "-1", "abc", "99", ""]:
    res = parse_page_range(expr, 5)
    print(f"  {expr!r:>6} -> {sorted(res)}  {'TUMU (sessizce yutuldu!)' if res == {1,2,3,4,5} else ''}")

# 1) .html girdi
print("\n=== 2) .html girdi ===")
html_f = os.path.join(TMP, "in.html")
with open(html_f, "w", encoding="utf-8") as f:
    f.write("<p>Hello world paragraph.</p>")
code, out = run(["translate", html_f, "--to", "tr", "--provider", "fake", "-o", os.path.join(TMP, "x.epub")])
print(f"  exit={code}, son satir: {out[-1][:120] if out else '(bos)'}")

# 3) skip+limit
print("\n=== 3) skip+limit ===")
code, out = run(["translate", "_artifacts/input/sample.epub", "--to", "tr", "--provider", "fake",
                 "--skip", "2", "--limit", "3", "-o", os.path.join(TMP, "skip.epub")])
for ln in out:
    if any(k in ln for k in ("skip", "limit", "segments")):
        print(f"  {ln}")
print(f"  exit={code}")

# 7) scanned pdf: 10-char threshold uzerinde metin varsa OCR'a hic gitmez
print("\n=== 4) scanned-PDF algilama esigi testi ===")
import pymupdf
scanned = os.path.join(TMP, "scanned_text.pdf")
doc = pymupdf.open()
page = doc.new_page()
img = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100))
page.insert_image(page.rect, pixmap=img)
doc.save(scanned)
# inspect
code, out = run(["inspect", scanned])
seg_count = [ln for ln in out if "blocks" in ln or "segments" in ln]
print(f"  bos-image sayfa: exit={code}, {seg_count}")
# simdi uzerine 15 karakter metin yerlestir -> esik 'scanned' demez, OCR yine gitmez
doc = pymupdf.open(scanned)
page = doc[0]
page.insert_text((10, 20), "Page 1")   # 6 karakter — esik alti ama text layer var
doc.saveIncr()
doc.close()
code, out = run(["inspect", scanned])
seg_count = [ln for ln in out if "blocks" in ln or "segments" in ln]
print(f"  'Page 1' metni olan sayfa (6 karakter, esik 10 alti): exit={code}, {seg_count}")
print("  -> text layer var ama esigin altinda: is_scanned_page TRUE olmali ama kimse cagirmiyor")
