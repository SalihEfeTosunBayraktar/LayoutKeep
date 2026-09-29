"""What a URL-like block does in a box too narrow for it, with and without the nowrap hint.

The hint was added after a footer URL came back 11.9pt tall from a 9.06pt style - but that is the
substitute face's own ascent+descent (Noto Serif is ~1.31em), not the renderer scaling the type.
This probe settles it: draw one token that fits and one that does not, each with and without
`white-space: nowrap`, and print the size the page actually got.

Run: python tools/audit/url_size_probe.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf

# Ölçülen ipucu burada tanımlı; yazıcı bunu hiçbir zaman bir sabit olarak dışa açmadı.
# The hint under test is defined here; the writer never exported it as a constant.
_NO_WRAP_HINT = "white-space: nowrap;"

FITS = "https://platform.openai.com/docs/apireference/chat/create"
TOO_WIDE = "https://platform.openai.com/docs/apireference/chat/create/very-long-tail/segment"

# Çıktı işletim sisteminin geçici klasörüne gider / output goes to the OS temp folder.
work = Path(tempfile.gettempdir()) / "lk-live"
work.mkdir(parents=True, exist_ok=True)

for label, text, hint in (
    ("fits / plain", FITS, ""),
    ("fits / nowrap", FITS, _NO_WRAP_HINT),
    ("too wide / plain", TOO_WIDE, ""),
    ("too wide / nowrap", TOO_WIDE, _NO_WRAP_HINT),
):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=200)
    box = pymupdf.Rect(306, 50, 526, 69)
    html = f"<p>{text}</p>"
    css = f"p {{ font-family: serif; font-size: 9.06pt; margin: 0; {hint} }}"
    spare, scale = page.insert_htmlbox(box, html, css=css, scale_low=0.85)
    out = work / "nowrap_probe.pdf"
    doc.save(str(out))
    doc.close()
    with pymupdf.open(str(out)) as result:
        drawn = result[0].get_text("words")
    described = ", ".join(
        f"{w[4][:18]!r} h={w[3] - w[1]:.1f} x1={w[2]:.0f}" for w in drawn
    ) or "(nothing drawn)"
    print(f"{label:18} spare={spare:7.2f} scale={scale:.2f}  {described}")
