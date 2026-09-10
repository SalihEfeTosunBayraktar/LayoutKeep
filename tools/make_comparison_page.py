"""Build the EN/TR page comparison page, with every rendered page embedded in it.

The artifact host serves one file, so the twenty page images travel inside it as data URIs.
They are rendered here rather than checked in: the translated PDF changes whenever the pipeline
does, and a stale image would be a comparison of something that no longer happens.

    .venv/Scripts/python.exe tools/make_comparison_page.py . out.html tools/comparison_page.html
    .venv/Scripts/python.exe tools/make_comparison_page.py . docs/comparison.html tools/comparison_page.html --standalone

The artifact host supplies the document skeleton, so the default output is the page body alone.
`--standalone` wraps it into a complete document instead, for the copy that lives in the
repository and is opened straight from disk or from GitHub Pages - without the charset
declaration that copy renders its Turkish as mojibake.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pymupdf

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
TEMPLATE = Path(sys.argv[3])
DPI = 105
QUALITY = 78


def pages(path: Path) -> list[str]:
    out = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=DPI)
            data = pix.pil_tobytes(format="JPEG", quality=QUALITY, optimize=True)
            out.append("data:image/jpeg;base64," + base64.b64encode(data).decode("ascii"))
    return out


en = pages(ROOT / "docs/samples/academic_paper_10.pdf")
tr = pages(ROOT / "docs/samples/academic_paper_10.tr.pdf")
assert len(en) == len(tr), (len(en), len(tr))

bench = json.loads((ROOT / "docs/samples/bench_deepl_10_fixed.json").read_text(encoding="utf-8"))
template = TEMPLATE.read_text(encoding="utf-8")

stats = {
    "pages": bench["pages"],
    "characters": bench["characters"],
    "segments": bench["segments"],
    "requests": bench["requests"],
    "flagged": bench["flagged"],
    "seconds": round(sum(p["seconds"] for p in bench["phases"]), 1),
    "phases": [{"name": p["name"], "seconds": round(p["seconds"], 1)} for p in bench["phases"]],
}

html = template.replace("/*__EN__*/", json.dumps(en))
html = html.replace("/*__TR__*/", json.dumps(tr))
html = html.replace("/*__STATS__*/", json.dumps(stats))

if "--standalone" in sys.argv:
    # The artifact host supplies the skeleton; a file opened from disk or served by GitHub
    # Pages has to carry its own, charset included - without it the Turkish comes out as
    # mojibake, which is what the local check of this very page showed.
    html = (
        '<!doctype html>\n<html lang="tr">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '</head>\n<body style="margin:0">\n'
        + html
        + "\n</body>\n</html>\n"
    )

OUT.write_text(html, encoding="utf-8")
print(f"{OUT} {OUT.stat().st_size // 1024} KB, {len(en)} page pairs")
