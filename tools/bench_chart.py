"""Chart the LayoutKeep protocol benchmark: models x scenario fidelity.

Reads _artifacts/bench_combined.json (a dict {model: {scenarios: [...]}}) and renders a set of
comparison charts into an HTML file. Marks which models are usable for LayoutKeep's bidirectional
protocol and which direction they fail.

Writes _artifacts/benchmark_report.html. Open it in a browser, or the agent renders it inline.

The decisive measure is `ok` (full protocol pass: parses via the real _parse_reply, id set
matches, markers balanced, protected tokens preserved, no passthrough). Speed and length ratio
are secondary. A model must pass BOTH directions to be usable by LayoutKeep.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "_artifacts"


def load() -> dict:
    with open(ART / "bench_combined.json", encoding="utf-8") as f:
        return json.load(f)


def _short(model: str) -> str:
    # noesis-qwopus3.5-9b-translate-v3.5 -> noesis-9b
    for long, short in [("noesis-qwopus3.5-9b-translate-v3.5", "noesis-9b"),
                        ("google/gemma-4-e4b", "gemma-4-e4b"),
                        ("google/gemma-4-e2b", "gemma-4-e2b")]:
        if model.startswith(long):
            return short
    return model.replace("google/", "")


def build_html(data: dict) -> str:
    models = list(data)
    # scenario order: single_en, multi3_en, single_tr, multi3_tr
    order = ["single_en", "multi3_en", "single_tr", "multi3_tr"]
    labels = {"single_en": "tek·EN→TR", "multi3_en": "çok3·EN→TR",
              "single_tr": "tek·TR→EN", "multi3_tr": "çok3·TR→EN"}

    # per-model summary across the 4 scenarios
    model_summary = []
    for m in models:
        scs = data[m]["scenarios"]
        by_name = {s["name"]: s for s in scs}
        passes = [by_name[n]["ok"] for n in order if n in by_name]
        en_ok = all(by_name.get(n, {}).get("ok") for n in ("single_en", "multi3_en"))
        tr_ok = all(by_name.get(n, {}).get("ok") for n in ("single_tr", "multi3_tr"))
        bidir = en_ok and tr_ok
        avg_s = round(sum(by_name[n]["seconds"] for n in order if n in by_name) / 4, 1)
        model_summary.append((_short(m), m, passes, en_ok, tr_ok, bidir, avg_s))

    # ---- build the bar data as JSON for a canvas chart ----
    bars = []
    for m in models:
        scs = {s["name"]: s for s in data[m]["scenarios"]}
        for n in order:
            if n not in scs:
                continue
            bars.append({"model": _short(m), "scenario": labels[n], "ok": scs[n]["ok"]})
    bars_json = json.dumps(bars, ensure_ascii=False)

    rows = []
    for short, _full, passes, en_ok, tr_ok, bidir, avg_s in model_summary:
        status = ("✅ çift yönlü" if bidir
                  else ("TR→EN yalnız" if tr_ok and not en_ok
                        else ("EN→TR yalnız" if en_ok and not tr_ok else "❌ başarısız")))
        cls = "good" if bidir else ("warn" if (en_ok or tr_ok) else "bad")
        segs = "".join(
            f'<span class="seg {"ok" if p else "fail"}">{labels[o]}</span>'
            for o, p in zip(order, passes, strict=False))
        rows.append(
            f"<tr><td class='model'>{escape(short)}</td><td>{segs}</td>"
            f"<td class='{cls}'>{status}</td><td>{avg_s}s</td></tr>"
        )

    return f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<title>LayoutKeep Protokol Benchmark</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, sans-serif; margin: 24px; max-width: 980px; }}
  h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.1rem; margin-top: 28px; }}
  .note {{ color: #888; font-size: .85rem; }}
  table {{ border-collapse: collapse; margin: 12px 0; }}
  td, th {{ border: 1px solid #ddd; padding: 6px 10px; font-size: .85rem; text-align:left; }}
  .good {{ color: #16a34a; font-weight:600; }}
  .warn {{ color: #d97706; font-weight:600; }}
  .bad  {{ color: #dc2626; font-weight:600; }}
  .seg {{ display:inline-block; margin:2px; padding:2px 6px; border-radius:4px; font-size:.7rem; }}
  .seg.ok {{ background:#dcfce7; color:#166534; }}
  .seg.fail {{ background:#fee2e2; color:#991b1b; }}
  #heat {{ width:100%; max-width:760px; }}
  .row {{ display:flex; align-items:flex-end; gap:2px; }}
  .col {{ flex:1; display:flex; flex-direction:column; align-items:center; }}
  .barw {{ width:100%; display:flex; justify-content:center; }}
  .cell {{ width:42px; height:30px; margin:1px; border-radius:3px; }}
  .cell.pass {{ background:#22c55e; }} .cell.fail {{ background:#ef4444; }}
  .ax {{ font-size:.65rem; color:#888; margin-top:4px; }}
</style></head><body>
<h1>🧪 LayoutKeep protokol benchmark — lokal modeller</h1>
<p class="note">Gerçek tel protokol: JSON segment dizisi + <code>&lt;0&gt;…&lt;/0&gt;</code> marker'ları +
U+E000..U+E001 korunan değer token'ları. <b>ok</b> = LayoutKeep'in kendi <code>_parse_reply</code>'ıyla
ayrışır, id kümesi birebir, marker/token korunur, passthrough yok. Modelin LayoutKeep'te kullanılabilir
olması için <b>iki yön de</b> ok olmalı.</p>

<h2>Model × senaryo geçiş ısı haritası</h2>
<div id="heat"></div>

<h2>Özet</h2>
<table><tr><th>Model</th><th>Senaryolar (tek/çok × iki yön)</th><th>Sonuç</th><th>Ort. süre</th></tr>
{''.join(rows)}</table>

<h2>Çıkarımlar</h2>
<ul id="takeaways"></ul>

<script>
const bars = {bars_json};
const orderL = Object.keys(Object.fromEntries(bars.map(b=>[b.scenario,1])));
const models = [...new Set(bars.map(b=>b.model))];
const heat = document.getElementById('heat');
for (const m of models) {{
  const row = document.createElement('div'); row.className='row';
  const lbl = document.createElement('div'); lbl.style.width='90px'; lbl.className='ax'; lbl.textContent=m;
  row.appendChild(lbl);
  for (const sc of orderL) {{
    const b = bars.find(x=>x.model===m && x.scenario===sc);
    const cell = document.createElement('div'); cell.className='cell '+(b&&b.ok?'pass':'fail');
    cell.title = (m+' '+sc+' : '+(b?'ok':'fail'));
    row.appendChild(cell);
  }}
  heat.appendChild(row);
}}
const tl = document.getElementById('takeaways');
const notes = [];
// directionality
const mset = [...new Set(bars.map(b=>b.model))];
for (const m of mset) {{
  const ok = bars.filter(b=>b.model===m && b.ok).length;
  const tot = bars.filter(b=>b.model===m).length;
  if (ok===tot) notes.push('<li><b>'+m+'</b>: tüm senaryolarda protokol tam — çift yönlü kullanılabilir.</li>');
  else if (ok>0) notes.push('<li><b>'+m+'</b>: kısmen — '+ok+'/'+tot+' senaryo; tek yönlü veya kararsız.</li>');
  else notes.push('<li><b>'+m+'</b>: hiçbir senaryoda protokolü tutturamadı.</li>');
}}
notes.push('<li>LayoutKeep çift yönlü istediği için yalnızca iki yönü de geçen modeller uygundur.</li>');
notes.push('<li>Kendi modelimiz GGUF çıkınca aynı benchmark ile bu tabloya eklenir — hedef: iki yönde de tam ok + hızlı.</li>');
tl.innerHTML = notes.join('');
</script>
</body></html>"""


def main() -> None:
    data = load()
    out = ART / "benchmark_report.html"
    out.write_text(build_html(data), encoding="utf-8")
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
