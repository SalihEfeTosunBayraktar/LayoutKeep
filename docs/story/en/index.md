# LayoutKeep, from nothing to now

**A measured engineering story: what we tried, what broke, what we fixed, what we took back out.**

> **Türkçe özet.** LayoutKeep PDF, EPUB ve DOCX belgelerini sayfada hiçbir şeyi oynatmadan çevirir:
> her metin kutusu yerini ve boyutunu korur, görseller yerinde kalır, tablolar satırlarını korur.
> Bu belge projenin tam kaydıdır — nasıl başladığı, neyin denendiği ve bırakıldığı (baştan yazım ve
> bir ince ayar kampanyası dahil), hangi hataların bulunduğu ve her kök nedenin nasıl ölçüldüğü,
> çalışma zamanı modelinin neden yerel olduğu ve düzen modelinin neden IBM Docling'in Heron'u
> olduğu, ve bugün hâlâ neyin bozuk olduğu. Buradaki her sayı yanında yazılı bir komuttan gelir.
> (Türkçe özgün metin: [`../`](../).)

---

## 0. The summary, in numbers

| What | Value | How it was measured |
|---|---|---|
| Supported formats | PDF → PDF, EPUB, DOCX, PNG/JPG, LKPROJ | the `capabilities.py` matrix, tested both ways |
| Losslessness criterion | **10 loss kinds (L1–L10) + 3 quality thresholds (D1–D3)** | `verify.py`; the criteria are read from the checker itself |
| Published measurement set | **24 documents**, 288 images, 0 "stale record" badges | the comparison site (each document with its own audit numbers) |
| Largest real run | a 220-page statistics textbook, 55 chunks, ~106 minutes | `translate_book.py`, `--workers 7` |
| Test suite | **1,256 tests**, 138 files | `.venv/Scripts/python.exe -m pytest -q` |
| Source code | ~24,000 lines (`src/`), 56 audit tools | `wc -l`, `tools/audit/` |
| The application | a single-file Windows exe (no installer), ~173 MB | PyInstaller onefile |
| Runtime model | `google/gemma-4-e4b`, LM Studio, 2 workers by default | local; the document never leaves the machine |
| Layout model | IBM Docling **Heron** (ONNX, local) | region classification on scanned and complex pages |

---

## 1. How to read this document

The story is split into eight chapters. Each one stands on its own; read in order they give the
project's logic: first the problem, then the architecture, then **measurement** (because every
decision rests on a number), then the bugs, then the model decisions, then the product, then the
honest limits and the sources.

| # | Chapter | What is in it |
|---|---|---|
| 1 | [The problem: what "lossless translation" actually means](01-problem.html) | A definition, four measured difficulties, a comparison table with other tools, the contract (D1–D7) |
| 2 | [Architecture: every part of the pipeline](02-mimari.html) | Modules and line counts, DocIR, readers, the provider chain, fitting, writers, the checker |
| 3 | [Measurement discipline](03-olcum.html) | The L1–L10 + D1–D3 table, 56 audit tools, **the three times measurement itself was wrong** |
| 4 | [The bug catalogue: sixteen cases](04-hatalar.html) | Every case: symptom → investigation → root cause → fix → evidence |
| 5 | [Choosing the model, and the IBM Docling question](05-model.html) | The local-first decision, the Heron layout model (why, measured), why the V2 plan was never built, the fine-tuning line |
| 6 | [From engine to product](06-urun.html) | Welcome, help, glossary/memory, the floating bar, the page range, **the bilingual PDF**, releases, the comparison site |
| 7 | [Honest limits and lessons](07-sinirlar.html) | What does not work today, the roadmap, eight lessons |
| 8 | [External sources and citations](08-kaynaklar.html) | Each dependency's role and licence, the legal status of the test sources |

The Markdown files live in the repository: `docs/story/01-problem.md` … `docs/story/08-kaynaklar.md`.

---

## 2. A short chronology

The project began on **10 September 2026** with a single sentence: *"translate a document without
moving anything on the page"*.

| Date | What happened |
|---|---|
| 10 Sep | The first working pipeline: PDF → PDF, DocIR was born, the contract was written; the first "lossless" report turned out to be wrong (it only looked at text flow) and the **rich fixture** rule arrived |
| 11–13 Sep | EPUB/DOCX paths, text-over-image and table tests, the first measurements on real documents |
| 14 Sep | The fitting pass, the shortening ladder, the first measurements of the `reflow` idea |
| 15–16 Sep | The desktop application (PySide6): setup, progress, completion; provider settings; adding the **IBM Docling Heron** layout model |
| 17 Sep | Source-kind classification (digital/scanned/mixed), the OCR confidence threshold, the four-panel visual comparison |
| 18 Sep | The losslessness campaign: extending the L criteria, `lossless_audit`, the held-out set |
| 19 Sep | Multi-worker chunk translation (`--workers`), `--resume`, the memory and glossary providers, the first version of the comparison site |
| 19–20 Sep (night) | The 220-page book (55 chunks, ~106 min); L10's measurement bug; reflow's two measurements; glossary/memory in the interface; help and welcome; the floating bar |
| 20 Sep | Productisation and fixes: **parallelism in the application**, the page-range behaviour, alignment (justify), a dead setting key, the copyright cleanup, releases **v0.9.1 → v0.9.7** |

---

## 3. Where things stand today, document by document

Every number comes from that run's `audit.json`; the comparison site shows each document's numbers
beside it.

| Document | Chunks | Remaining real losses |
|---|---|---|
| Wikipedia ×2 (re-translated) | 19 / 33 | L2 rows; **L10 = 0** |
| cookbook_1907 | 35 | L6=2, D1 (small type) |
| mushrooms_1895_sample | 41 | L2=1, L6=1 |
| NIST journal / NISTIR scan | 8 / 6 | L1 partial run; **L2–L10 = 0** |
| IRS form (48 chunks) | 48 | L7 (a dense form; measured with reflow off) |
| The 220-page book | 55 | L2=2, L6=4, L7=1, L8=1, L10=0, D1=801 (the small-type class) |

![The comparison site](site.png)

*The published comparison site: original on the left, translation on the right, that document's
audit numbers above.*

**Known limits (summary):** **number strips** in table headings can lose their arrangement;
bibliography rows sometimes stay in the source language (L2, flagged); on dense forms some blocks
fall below the readability floor (D1); scanned pages depend on OCR quality and are flagged when
confidence is low; **right-to-left scripts are not implemented**; quality is the model's ability.
The detailed list and the roadmap: [Chapter 7](07-sinirlar.html).

---

## 4. The one-sentence summary

Translating a document into another language is easy; translating it **while leaving the page where
it is** is hard — and this project does the second and proves it **by counting the losses**: every
run is checked against the source page by page, every loss is either fixed or flagged with its
reason, and no number is hidden.

---

*This document was assembled from `docs/CONTRACT.md`, `docs/campaign/JOURNAL.md`,
`docs/MEASUREMENTS.md`, `docs/KAYIPSIZ_MOD_DURUM.md`, `docs/LOSSLESS-REPORT.md`,
`docs/FEATURE-ROADMAP.md`, the `_artifacts/heldout/**/audit.json` records, and the git history.*
