"""Geçiş 3 — canlı uç testleri:
1) .html girdi: converter listesinde var ama reader case'i var mı?
2) page-range uç değerleri (0, negatif, sayfa sayısından büyük)
3) image->image tam akış
4) skip+limit birleşimi CLI'da
5) DeepL çevirisi sahte sunucuya karşı (RuntimeError yolu)
"""
import os
import subprocess
import sys
from _common import TMP, setup

setup()


env = {**os.environ, "PYTHONPATH": "src"}
PY = sys.executable



def run(args, **kw):
    return subprocess.run([PY, "-m", "layoutkeep.cli", *args],
                          capture_output=True, text=True, env=env, timeout=180, **kw)


# 1) HTML girdi
html_file = os.path.join(TMP, "in.html")
with open(html_file, "w", encoding="utf-8") as f:
    f.write("<html><body><p>Hello world paragraph.</p></body></html>")
r = run(["translate", html_file, "--to", "tr", "--provider", "fake",
         "-o", os.path.join(TMP, "in.tr.epub")])
print("=== 1) HTML GIRDI ===")
print("stdout son satir:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(bos)")
print("stderr son satir:", r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "(bos)")
print("exit:", r.returncode)

# inspect da deneyelim
r2 = run(["inspect", html_file])
print("inspect stdout:", r2.stdout.strip().splitlines()[:2])
print("inspect stderr son:", r2.stderr.strip().splitlines()[-1] if r2.stderr.strip() else "(bos)")
