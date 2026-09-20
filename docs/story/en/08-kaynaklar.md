# 8. External sources and citations

This project stands on other people's work. Below is each source's **role in the project** and its
licence. (The same table is kept in `CREDITS.md`; this is the longer version with the reasoning.)

## 8.1 Engine and infrastructure

| Source | Its role here | Licence |
|---|---|---|
| [PyMuPDF](https://pymupdf.readthedocs.io/) | The PDF reading and writing engine; text layer, typography, image extraction, redaction, drawing HTML boxes | AGPL-3.0 |
| [Qt / PySide6](https://doc.qt.io/qtforpython/) | The desktop interface: window, floating bar, welcome, tables, theme | LGPL-3.0 |
| [pytest](https://pytest.org/) | The runner for 1,256 tests | MIT |
| [PyInstaller](https://pyinstaller.org/) | Producing the single-file `.exe` | GPL-2.0 (with the usual exception) |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) (PP-OCR models) | OCR on scanned pages; produces a confidence score | Apache-2.0 |

## 8.2 The layout model (IBM Docling)

| Source | Its role here | Licence |
|---|---|---|
| [IBM Docling — the Heron layout model](https://huggingface.co/docling-project/docling-layout-heron-onnx) | Region classification on scanned and complex pages (heading, paragraph, table, figure, footnote). Runs locally as ONNX | MIT |
| [Docling (the project)](https://github.com/docling-project/docling) | The framework the model comes from; its architectural ideas (recovering structure from a page image) | MIT |

The reasoning and the measurement are in section 5.3: in a four-panel comparison over 10 book pages,
"prose still left in English" went 6/82 → 1/82. The model's output **on its own** was recorded as
well (`tests/layout_eval/2026-09-16_heron_pure/`), so that every rule added later was added against a
measured floor.

## 8.3 Translation models

| Source | Its role here | Licence |
|---|---|---|
| [google/gemma-4-e4b](https://huggingface.co/google/gemma-4-e4b) (through LM Studio) | The default local translation model | Gemma Terms of Use |
| [LM Studio](https://lmstudio.ai/) | The local model server (OpenAI-compatible endpoint, parallel slots, context setting) | Proprietary (free to use) |
| [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | The base model of the fine-tuning track (a separate effort, section 5.4) | Apache-2.0 |
| [Hugging Face Transformers](https://huggingface.co/docs/transformers/) + PEFT/QLoRA | Fine-tuning (on Kaggle, without depending on TRL) | Apache-2.0 |

## 8.4 Comparison points (no code taken, ideas and yardsticks taken)

| Source | What we compared | Licence |
|---|---|---|
| [BabelDOC](https://github.com/funstory-ai/BabelDOC) | Parallel PDF translation; its "lossless" claim and its own comparison table (arXiv 2605.10845) | AGPL-3.0 |
| [PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate) | PDF translation; its approach to preserving formulas and figures | AGPL-3.0 |
| [MinerU](https://github.com/opendatalab/MinerU) / mineru-translate | Document-understanding pipelines; bilingual output, caching | AGPL-3.0 |
| Commercial roundups (Doclingo, Lara Translate, Doctranslate, Bluente) | Feature coverage and pricing | — |

**No code was taken.** Not a line in this project was copied from the tools above; the table exists
only to make the question "what exists outside, what is missing here" measurable
(`docs/FEATURE-ROADMAP.md`).

## 8.5 Test sources (the held-out set)

The documents used for measurement, and their licence status. Copyrighted ones **do not enter the
repository** and are not published on the site (`NOT_PUBLISHABLE`); they stay on the user's disk
only.

| Source | Kind | Status |
|---|---|---|
| NIST Journal of Research (journal issues) | Digital PDF | Public domain (US federal) — published |
| NIST IR 6643 (vapour pressure) | **Scanned** PDF | Public domain — published |
| A DOCX produced from the NIST journal | DOCX | Public domain (made with the project's own PDF→DOCX path) — published |
| NASA NTRS report + NASA grant form | Digital + scanned | Public domain — published |
| arXiv papers (19113, 19145, 2510.03959, 2605.18014) | Digital PDF | arXiv licence — published |
| IRS forms (i1040gi, p505) | Form PDF | Public domain (US federal) — published |
| Project Gutenberg #31061, Cajori — A History of Mathematics (556 pages) | PDF, formula-dense | Public domain — published |
| Project Gutenberg books (The Time Machine, Think Python, cookbook) | EPUB/PDF | Public domain / open licence — published |
| Wikipedia pages | PDF | CC BY-SA — published |
| Introductory Statistics (Sheldon M. Ross) | Book PDF | **Copyrighted** — local only |
| computer-systems-Architecture | Book PDF | **Copyrighted** — local only (its images were removed from the repository) |

## 8.6 Method and engineering sources

| Source | What it influenced |
|---|---|
| Google DESIGN.md / design tokens | The rule that the interface palette comes from tokens (no hardcoded hex) |
| Apple HIG, Material Design (general principles) | The structure of the welcome and help screens, the spacing and type scale |
| ISO 639 language codes | Language selection and detection |
| The Unicode private use area (U+E000–U+E001) | Carrying protected values invisibly to the model |
| The Portable Document Format spec (ISO 32000) | Verifying PDF writing and redaction behaviour |

## 8.7 This document's own sources

This story was not invented; it was assembled from these files and measurements:

- `docs/CONTRACT.md` — the architectural invariants (D1–D7)
- `docs/campaign/JOURNAL.md` — the day-by-day measurement journal (the primary source for the cases)
- `docs/MEASUREMENTS.md`, `docs/BENCHMARK.md` — the numbers
- `docs/KAYIPSIZ_MOD_DURUM.md`, `docs/LOSSLESS-REPORT.md` — the losslessness status
- `docs/FEATURE-ROADMAP.md` — the outside comparison and the open work
- `_artifacts/heldout/**/audit.json` — every run's audit numbers
- `git log` — dates and decisions
