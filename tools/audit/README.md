# LayoutKeep Audit Evidence (tools/audit)

Denetim kanıtı betikleri — `docs/AUDIT-BULGULAR.md` ve `docs/AUDIT-PROJE-ANALIZI.md`'deki
"kanıt (koşuldu)" iddialarının tamamı buradaki betiklerle yeniden üretilebilir.

## Nasıl koşulur

```bash
# repo kökünden (venv aktifken)
python tools/audit/<betik>.py
```

Betikler kendi konumlarından repo kökünü bulur (`_common.py::setup()`), çalışma dizininden
bağımsızdır. Karalama çıktıları (epub/pdf/sqlite) depoya değil geçici dizine yazılır
(`%TEMP%/lk-audit`; `LK_AUDIT_TMP` ile değiştirilebilir) — denetlenen ağaç kirletilmez.

`tools/audit` ruff kapsamı dışıdır (`pyproject.toml [tool.ruff] exclude`): kanıt betikleri
**koşuldukları halleriyle** korunur; bulguyu taşıyan satırı sonradan güzelleştirmek, kanıtı
değiştirmek olur. (Not: `ruff check tools/` tüm tools'u tararken exclude'u uygular; yalnızca
`ruff check tools/audit` explicit yol verildiğinde hata gösterir — beklenen davranış.)

## Betik → bulgu eşlemesi

| Betik | Doğruladığı bulgular |
|---|---|
| `edge_epub_test.py` | B1 (SVG-sarmalı resim), B2 (OPF kapak), B4 (`<th>`), B5 (`<figcaption>`) |
| `imgpos_test.py` | B7 (resim konumu / DUMMY_BBOX sıralama) |
| `check_ocr_gap.py`, `check_ocr_gap2.py` | B3 (taranmış PDF → OCR boşluğu) |
| `check_imgloss.py`, `check_pg79501.py` | resim kapsama ölçümü (pg23319/pg79501) |
| `cli_error_test.py` | B8 (CLI traceback sızıntısı) |
| `check_perf.py`, `check_perf2.py` | B13/B14 verisi (bağlam payı, chunk×adaptive) |
| `e2e_pipeline.py` | tam akış duman testi |
| `test_img_epub2pdf.py` | EPUB→PDF görsel koruma (kullanıcı şikayetinin kökü) |
| `test_mirrored.py` | aynalanmış metin temizliği (negatif bulgu) |
| `check_ui.py` | mockup 10/11 karşılığı, app.py akışı |
| `pass1_ci_rtl.py` | 1. tur: CI extra'ları, RTL dil listesi, font zinciri |
| `pass1_img_docs.py` | image dokümanı iddiaları: R1 vurgu, R3, R4, D4, vision transport |
| `pass2_consistency.py`, `pass2_full.py` | 2. tur: sınıf boyutları, `.html` tutarsızlığı, ölü tunable, 2-means maliyet |
| `tunable_audit.py` | 10 tunable'ın kullanım denetimi (2 ölü: `timeout.first_batch_s`, `fit.min_scale`) |
| `pass3_html.py`, `pass3_live.py`, `pass3_more.py` | B26 (`.html` girdi), B30 (page-range), B32 (eşik), skip+limit, DeepL hata yolu |
| `pass3_final.py` | B27 — çift çeviri kanıtı (`[tr] [tr]` katmanlaşması) |
| `pass3_tm.py` | B28 (bellek bayrak kaybı), model kimliği ayrımı, `context_blocks=0` |
| `exe_ocr_check.py`, `exe_ocr_verdict.py`, `pkg_parse2.py`, `ocr_chain.py` | B31 (exe içinde 0 `.onnx`) |
| `lkproj_behavior.py` | B27 ön incelemesi (segment kaynağı `block.text` mi `source_text` mi) |

## Notlar

- Betikler kasıtlı olarak minimal/bağımsızdır; bazıları aynı setup kalıbını tekrarlar — bu
  bilinçli: her kanıt kendi kendine yeter.
- Çıktı dosyaları (`*.epub`, `*.pdf`, `*.sqlite`) betiklerle üretilir; repo'ya girmez
  (`.gitignore`: `*.epub`, `*.lkproj`, `*.sqlite`).
- Denetim raporları: `docs/AUDIT-BULGULAR.md` (33 bulgu, B1–B33), `docs/AUDIT-PROJE-ANALIZI.md`.
