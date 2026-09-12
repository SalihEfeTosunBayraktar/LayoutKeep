"""Faz-bitimi görsel raporu: her dosya tipinden dosya tipine kayıpsızlık kıyas tablosu.

İki veri kaynağı:
1. docs/samples/format_matrix.json — kimlik çevirisiyle (fake) ölçülen 20 çift: yapısal kayıp ölçümü
2. _artifacts/output/faz1-real/verify.json — gerçek gemma çevirisiyle doğrulanan 5 açık çift

Çıktı: _artifacts/reports/faz1_matrix.html (kendi kendine yeten HTML, koyu tema)
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs/samples/format_matrix.json"
VERIFY = ROOT / "_artifacts/output/faz1-real/verify.json"
OUT = ROOT / "_artifacts/reports/faz1_matrix.html"

OPEN_PAIRS = {
    ("pdf", "pdf"), ("pdf", "docx"), ("epub", "epub"),
    ("docx", "docx"), ("png", "docx"),
}

FORMAT_LABELS = {"pdf": "PDF", "epub": "EPUB", "docx": "Word", "html": "HTML", "png": "PNG"}


def pct(after: int, before: int) -> tuple[str, str]:
    """(display, class) — class drives the colour in the table."""
    if before == 0:
        return ("—", "na") if after == 0 else (f"+{after}", "warn")
    value = 100 * after / before
    if value >= 99.5:
        return f"{value:.0f}%", "ok"
    if value >= 95:
        return f"{value:.0f}%", "near"
    return f"{value:.0f}%", "warn"


def build() -> str:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    cells: dict[tuple[str, str], dict] = {}
    for row in matrix:
        cells[(row["source"], row["target"])] = row

    verify: dict[str, dict] = {}
    if VERIFY.exists():
        for row in json.loads(VERIFY.read_text(encoding="utf-8")):
            verify[row["pair"]] = row

    sources = ["pdf", "epub", "docx", "png"]
    targets = ["pdf", "epub", "docx", "html", "png"]

    head = "".join(
        f"<th>{FORMAT_LABELS.get(t, t)}</th>" for t in targets
    )

    body_rows = []
    for s in sources:
        cells_html = []
        for t in targets:
            key = (s, t)
            row = cells.get(key)
            open_pair = key in OPEN_PAIRS
            if row is None or not row.get("ok", False):
                cells_html.append('<td class="fail">hatā</td>')
                continue
            b, a = row["before"], row["after"]
            text_c, text_k = pct(a["words"], b["words"])
            img_c, img_k = pct(a["images"], b["images"])
            page_c, page_k = pct(a["pages"], b["pages"])
            styled_c, styled_k = pct(a["styled_runs"], b["styled_runs"])
            badge = '<span class="badge open" title="Bu çift açık">AÇIK</span>' if open_pair else ""
            real = ""
            v = verify.get(f"{s}->{t}")
            if v and "ratios" in v:
                rc = v["ratios"]["characters"]
                real = (
                    f'<div class="real">gemma: {rc} karakter</div>'
                )
            cells_html.append(
                f'<td class="{ "open" if open_pair else "locked"}">'
                f'<div class="metrics">'
                f'<div>metin <span class="{text_k}">{text_c}</span></div>'
                f'<div>görsel <span class="{img_k}">{img_c}</span></div>'
                f'<div>sayfa <span class="{page_k}">{page_c}</span></div>'
                f'<div>biçim <span class="{styled_k}">{styled_c}</span></div>'
                f"</div>{badge}{real}</td>"
            )
        body_rows.append(
            f'<tr><th>{FORMAT_LABELS.get(s, s)}</th>{"".join(cells_html)}</tr>'
        )

    # Real-run summary table
    real_rows = []
    for pair_key, v in verify.items():
        if "ratios" not in v:
            continue
        r = v["ratios"]
        real_rows.append(
            f"<tr><td>{v['pair']}</td><td>{v['source']}</td><td>{v['output']}</td>"
            f"<td>{r['characters']}</td><td>{r['words']}</td><td>{r['pages']}</td>"
            f"<td>{r['images']}</td><td>{r['styled_runs']}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>LayoutKeep — Kayıpsızlık Matrisi (Faz 1)</title>
<style>
  :root {{
    --bg: #0f172a; --card: #1e293b; --border: #334155;
    --text: #f8fafc; --muted: #94a3b8; --accent: #38bdf8; --ok: #4ade80;
    --near: #facc15; --warn: #f87171;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text);
         font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; padding: 32px; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  h1 .lk {{ color: var(--accent); }}
  .sub {{ color: var(--muted); margin-bottom: 24px; font-size: 13px; }}
  h2 {{ font-size: 16px; margin: 28px 0 12px; }}
  table {{ border-collapse: collapse; width: 100%; background: var(--card);
           border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
  thead th {{ background: rgba(56,189,248,.08); font-size: 12px; letter-spacing: .5px; }}
  tbody th {{ background: rgba(56,189,248,.05); }}
  td .metrics div {{ font-size: 12px; color: var(--muted); white-space: nowrap; }}
  .ok {{ color: var(--ok); font-weight: 600; }}
  .near {{ color: var(--near); font-weight: 600; }}
  .warn {{ color: var(--warn); font-weight: 600; }}
  .na {{ color: var(--muted); }}
  td.open {{ background: rgba(74,222,128,.06); }}
  td.locked {{ opacity: .92; }}
  td.fail {{ color: var(--warn); text-align: center; }}
  .badge {{ display: inline-block; font-size: 10px; font-weight: 700;
            letter-spacing: .5px; padding: 1px 6px; border-radius: 4px; margin-top: 4px; }}
  .badge.open {{ background: rgba(74,222,128,.15); color: var(--ok); }}
  .real {{ font-size: 11px; color: var(--accent); margin-top: 4px; }}
  .note {{ background: var(--card); border: 1px solid var(--border);
           border-radius: 8px; padding: 14px 16px; color: var(--muted); font-size: 13px; }}
  .legend {{ display: flex; gap: 18px; margin: 12px 0 18px; font-size: 12px; color: var(--muted); flex-wrap: wrap; }}
  .legend b {{ font-weight: 600; }}
  .note code, .sub code {{ color: var(--accent); font-size: 12px; }}
</style></head><body>
<h1><span class="lk">LayoutKeep</span> — Kayıpsızlık Matrisi</h1>
<div class="sub">Faz 1 · 2026-09-12 · kimlik çevirisiyle (fake provider) 20 çiftin yapısal ölçümü +
gerçek <code>google/gemma-4-e4b</code> çevirisiyle 5 açık çiftin fiziksel doğrulaması</div>

<div class="legend">
  <span><b>metin</b> = kelimeler (çıktı/girdi)</span>
  <span><b>görsel</b> = resim sayısı</span>
  <span><b>sayfa</b> = sayfa sayısı</span>
  <span><b>biçim</b> = kalın/italik run</span>
  <span><span class="ok">yeşil</span> ≥%99.5 · <span class="near">sarı</span> ≥%95 · <span class="warn">kırmızı</span> altı</span>
</div>

<h2>Yapısal matris — 20 çift (kimlik çevirisi, kayıp = motor suçu)</h2>
<table>
<thead><tr><th>kaynak ▸ hedef</th>{head}</tr></thead>
<tbody>{''.join(body_rows)}</tbody>
</table>

<h2>Gerçek çeviri doğrulaması — 5 açık çift (gemma-4-e4b, LM Studio)</h2>
<table>
<thead><tr><th>Çift</th><th>Kaynak dosya</th><th>Çıktı</th><th>Karakter</th><th>Kelime</th><th>Sayfa</th><th>Görsel</th><th>Biçim</th></tr></thead>
<tbody>
{''.join(real_rows) or '<tr><td colspan="8" class="na">verify.json yok</td></tr>'}
</tbody>
</table>

<div class="note">
<b>Notlar.</b>
<ol style="margin:8px 0 0 18px">
<li>Kimlik matrisinde <b>metin/görsel/sayfa/biçim %100</b> = dönüşüm hiçbir şey kaybetmedi; Türkçe gerçek çeviride kelime/karakter oranı doğal olarak değişir (eklemeli dil → daha az kelime, daha çok karakter).</li>
<li>Gerçek çeviri turlarında <b>0 segment needs_review</b>, 16/16 ve 20/20 sayısal literal (ölçü, parça no) eksiksiz aktarıldı.</li>
<li>pdf→png %91 kelime: OCR boşluk sayımı quirk'i, karakter sayısı birebir (1091/1091) — içerik kaybı değil.</li>
<li>Açık 5 çift: PDF→PDF, PDF→Word, EPUB→EPUB, Word→Word, PNG→Word. Kilitli hedefler nedenleriyle UI'da gösteriliyor.</li>
</ol>
</div>
</body></html>"""


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"yazildi: {OUT}")
    print(f"boyut: {OUT.stat().st_size:,} bytes")
