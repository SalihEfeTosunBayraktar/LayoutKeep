"""pg79501: zip'te 3 resim ama ImageRef=2 — hangisi kayboluyor ve neden?"""
import os
import sys
from _common import setup

setup()
import zipfile




name = "_artifacts/e2e/pg79501-images-3.epub"
with zipfile.ZipFile(name) as z:
    imgs = [n for n in z.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))]
    print("zip resimleri:", imgs)
    # XHTML'lerde gecen src referanslari
    import re
    for n in z.namelist():
        if n.endswith((".xhtml", ".html", ".htm")):
            raw = z.read(n).decode("utf-8", errors="replace")
            for m in re.finditer(r'src="([^"]+)"', raw):
                print(f"  {n}: src={m.group(1)}")
