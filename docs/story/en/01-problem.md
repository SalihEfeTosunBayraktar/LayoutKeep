# 1. The problem: what "lossless translation" actually means

This chapter defines the problem the project set out to solve, shows with measurements why it is
hard, and compares it with what exists outside. The chapters after it describe the architecture
built around that problem, the measurements, and the bugs.

## 1.1 The definition

Translating a PDF is not the same as rewriting its text in another language — that part is easy:
read the document, extract the text, hand it to a model, produce a new document. The hard part is
**keeping the page itself**: the same page size, the same column layout, text sitting in the same
box in the same place, the same heading hierarchy, the same table grid, the same figures, the same
footnotes. A reader putting the two documents side by side should see "the same book in another
language", not "a summary that was laid out again".

This project states that goal as: **every translatable block is drawn in its source box, in
typography close to the source's, keeping the source's position; nothing untranslatable disappears
silently — it is either preserved or flagged.**

## 1.2 Why it is hard: four measured facts

**1) Text length changes, boxes do not.** English→Turkish was measured at **0.93x** in this project
(the ratio of character counts over the same segments) — so the translation is, on average, a little
shorter than the source. Averages mislead: a heading goes `Introduction` → `Giriş` at half the
length while a sentence can grow 60% (`state of the art` → `son teknoloji ürünü`). Text that grows
in a fixed box either overflows or is shrunk, and shrinking has a readability floor (in this
project **0.85** — blocks that go below it are flagged as D1).

**2) PDF is not a reflowable format.** PDF is a *print* format: every glyph has a fixed position,
and the file has no concept of a "paragraph". Writing translated text into it requires recovering
the page's *structure* first — which run of text is a paragraph, which is a heading, which is a
table cell, which is a page number. That recovery (reading order, block merging, column splitting)
is the most heavily tested part of the project, and most bugs come from it.

**3) The kind of source document sets the quality directly.** The differences we measured:

| Source kind | What happens | Measurement |
|---|---|---|
| Digital PDF (has a text layer) | The best case; typography, font name, size and colour are readable | NIST journal: 4 chunks, 114 blocks, D1 **52** → 0 with reflow |
| Scanned PDF (an image) | Needs OCR; character errors and a confidence score come into play | NASA scan: the low-confidence block is **flagged** with "low OCR confidence (0.62)" |
| Mixed (text + image) | Decided page by page; the text-over-figure trap | Scanned pages are excluded (the L10 rule, see Chapter 3) |
| EPUB | Layout lives in CSS; reflowable but still preservable | 95%+ fidelity on the rich fixture |
| DOCX | OOXML is handled directly (`python-docx` is deliberately not used) | A public-domain NIST DOCX joined the test sources |
| PNG/JPG | The OCR path only; page layout is recovered from the drawing | Page image → PDF → the same pipeline |

**4) The model's language ability sets the ceiling.** However good the pipeline is, the model is
what writes the sentence. Results from the local `google/gemma-4-e4b` (LM Studio) are weaker on
terminology consistency than cloud models, which is why the glossary (forcing terms) and the memory
(same text, same translation) were put *under* the model rather than on top of it: even when the
model gets it wrong, terminology and consistency are guaranteed by the pipeline.

## 1.3 What exists outside

The difference table below is compiled from BabelDOC's own comparison table (arXiv 2605.10845,
Tables 1–2), mineru-translate's feature list, and commercial tools (Doclingo, Lara Translate,
Doctranslate, Bluente). The "here" column is verified against the code in this repository.

| Feature | Who has it | Here |
|---|---|---|
| Bilingual output (source + translation) | BabelDOC, mineru-translate, Doclingo, Lara | **in the PDF output** (side by side, or alternating pages) and on the site |
| Glossary constraint | BabelDOC (`--glossary` CSV), DeepL, Lara | **yes** (JSON or CSV/TSV, checked in the prompt and the output, edited inside the application) |
| Automatic term extraction | BabelDOC | **yes** — "suggest from document" in the glossary editor |
| Cross-page context | BabelDOC | partial (`context_before/after`) |
| Overlap-resolution ladder (shrink → squeeze → push down) | mineru-translate | partial (`--fit-mode reflow`, experimental, off by default) |
| Translation cache across runs | mineru-translate | **yes** (an SQLite memory, verified on a real 2,555-segment run) |
| Translating text inside figures and tables | BabelDOC | no (deliberate) |
| An editor / post-editing | Doclingo, Lara | no (there is a review queue, not editing) |
| A plugin ecosystem (Zotero, Word) | BabelDOC/PDFMathTranslate | no (deliberate) |
| **Page-by-page loss audit (L1–L10)** | **not seen elsewhere** | **yes** — against the source, on every run |
| Review flag with a reason | partial | **yes** — the reason is written for every flag (the book run) |
| A comparison site built from real held-out documents | no | **yes** — 24 documents, with a slider and their audit numbers |
| Runtime settings (context window, thresholds) | partial | **yes** — 30 settings, all wired to code (Chapter 4, case 11) |

The critical difference: tools outside aim for **output that looks good**; this project aims to
**count what is lost**. Without the second, a claim of "lossless" is an unmeasurable marketing
sentence.

## 1.4 The contract: seven decisions that are not up for negotiation

The project's `docs/CONTRACT.md` writes down seven architectural rules. They are not arbitrary —
each one was written after a bug:

- **D1 — DocIR is the single source of truth.** A format-independent intermediate document model;
  readers produce it, writers consume it. The translation layer does not know about PDF.
- **D2 — The translation layer knows nothing about layout.** A provider sees only text; box, font
  size and position never leak into it. This is what makes the model replaceable and the providers
  parallelisable.
- **D3 — Fitting is a separate stage.** It runs *after* translation; the decisions that make text
  fit (shrink, ask for a shorter rendering, push down) do not affect translation quality.
- **D4 — Latin script, but ready for RTL.** Right-to-left scripts are *not implemented*; the schema
  carries a `direction` field.
- **D5 — Everything must be resumable.** An interrupted run continues where it stopped; the
  document is *not* shrunk when a page range is applied (that rule was implemented wrongly twice,
  see Chapter 4, case 12).
- **D6 — Translation quality is tracked with segment flags.** Every block is either translated or
  has a written *reason* why it was not.
- **D7 — A conversion is offered only after it has been measured.** Unmeasured format pairs are
  disabled in the interface.

## 1.5 The operational definition of "lossless"

The definition that makes the word measurable is written at the top of `docs/campaign/JOURNAL.md`
and has three parts:

1. **No translatable block disappears.** Every block either appears translated in the output or
   stays as it was in the source; neither is an L3/L4 violation.
2. **No untranslated block stays silent.** Every block that could not be translated is flagged
   *with a reason* (L2, D1, D2, OCR confidence, a lost protected value, a lost style…).
3. **Source and output can be compared page by page.** The L1–L10 rules count exactly that; the
   audit output (`audit.json`) sits beside every run and is published on the comparison site.

The practical consequence: the project's success is measured not by "it looks good" but by **the
number of flags that remain** — and that number is written for every run, including the runs where
it comes out bad.
