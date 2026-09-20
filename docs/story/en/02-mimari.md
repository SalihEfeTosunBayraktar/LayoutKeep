# 2. Architecture: every part of the pipeline

This chapter describes how the code in the repository fits together — what each module does, why it
stops at that boundary, and which bug drawing that boundary prevented. The numbers come from this
repository (`wc -l`, 2026-09-20).

![The LayoutKeep translation pipeline](architecture.png)

## 2.1 The overall flow

```
read → DocIR → segment → provider chain → fit → write → verify → flag
```

Every stage produces the next one's input and **none of them does another's job**. The separation is
not theoretical: each boundary was drawn while fixing a bug. The rule "fitting must be a stage of
its own" (D3), for example, was written after the model, answering a request to "make this sentence
shorter", damaged translation quality — the model now sees a shortening request only on the
*second* pass and only in the fitting stage.

## 2.2 Modules and their sizes

| Module | Lines | Responsibility | The boundary rule |
|---|---|---|---|
| `readers/` | 3,819 | PDF, EPUB, DOCX and image readers | The output is DocIR only; a reader writes nothing |
| `core/` | 2,519 | DocIR, protection, number words, settings, page ranges | Knows no format; data only |
| `providers/` | 2,718 | The provider chain: dedupe, memory, glossary, protection, splitting, retry | Knows no layout (D2) |
| `fitting/` | 1,881 | Fitting into a box, growing, figure collisions, text-over-image | Does not ask for translations; it measures |
| `writers/` | 3,196 | PDF, DOCX and EPUB writers + converters | Decides nothing; it draws |
| `ocr/` | 726 | Reading scanned pages, the layout detector (IBM Docling Heron) | Supplies data to the reader |
| `ui/` | 7,864 | The PySide6 interface, the worker, the floating bar, welcome, help, the glossary editor | Calls the engine, never copies it |
| `verify.py` | 576 | The L1–L10 and D1–D3 checks + repair | The CLI and the interface run the same file |
| `cli.py` | 703 | The command line | The same engine, a different door |

That the interface is larger than the engine is not an accident: every convenience the user sees
(the welcome screen, help, the glossary table, the floating bar, the review queue) lives there. The
engine was kept small — because the engine's correctness depends on how testable it is.

## 2.3 DocIR: why a format-independent intermediate model

`core/docir.py` carries this chain:

```
Document → Page → Block → Line → Span
```

- **Block** is a translatable unit: `text`, `bbox`, `role` (title/paragraph/table/caption/…),
  `align`, `direction`, `rotation`, `source_ref` (which page it came from), `table_id/row/col`.
- **Line/Span** carry typography: font family, size, bold/italic, colour.
- **Segment** is the translation unit: `source` (text with protected values masked), `target`,
  `block_id`, flags and reasons.

Why a model of its own? Because the transformation between readers and writers goes **both ways**:
PDF→DOCX, DOCX→EPUB, EPUB→PDF all pass through the same intermediate model and the same audit.
Without it, every format pair would need a pipeline of its own, and each would have its own bugs.

**Protected values.** Numbers, measurements, DOIs/URLs, part numbers, dates and (toggleable) Roman
numerals are **never shown to the model**: they are lifted out of the text and replaced with
invisible placeholders in the U+E000–U+E001 range, then put back after translation. That makes it
structurally impossible for the model to invent or drop a number. On the book run this rule brought
the "numbers were lost" flag down to 49 cases — most of what remains are number groups inside
tables.

## 2.4 Readers

**The PDF reader** (`readers/pdf_reader.py`) uses two paths: the text layer when there is one, OCR
when there is not. The decision is made page by page — two of a book's 841 pages can be scans
(measured) and only those two go through OCR. Reading order runs XY-cut (horizontal/vertical
splitting) with column separation, then line merging and paragraph rules.

**The layout detector (IBM Docling Heron).** XY-cut looks at the page's *lines*: it finds aligned
blocks. On complex pages (a box inside a box, a caption under a picture, a formula squeezed between
two columns) it is not enough. So the `docling-project/docling-layout-heron-onnx` model was added:
it looks at the page as an image and classifies it region by region (heading, paragraph, table,
figure, footnote). The model is enabled with `--layout-detector` and is on by default in the
interface. Its effect was measured: in a four-panel comparison over 10 book pages (original | old
run | XY-cut | with the detector), the detector cut "prose still left in English" from 6/82 to 1/82.

**The EPUB and DOCX readers** handle their own formats' structure directly. In DOCX, `python-docx`
is deliberately **not used**: that library re-serialises the document, which rewrites everything
that has to be preserved (style ids, relationships, content controls). OOXML is read directly.

## 2.5 The provider chain

The order matters — each link makes the one above it unnecessary:

```
protection (mask)  →  dedupe (translate the same text once)  →  memory (across runs)  →
glossary (forcing terms)  →  the model call  →  splitting (sentence by sentence if it echoes)  →
retry (ask again for what came back empty)  →  unify repeats (one translation per source)
```

- **dedupe**: the same text appears dozens of times in a document (headings, table labels, form
  fields). It is translated once; on the IRS form this cuts the request count noticeably.
- **memory** (`providers/memory.py`): SQLite, across runs. A real run accumulated 2,555 segments,
  and when the user restarted the same book those segments never went to the model at all.
- **splitting** (`providers/split.py`): sometimes the model hands the paragraph back unchanged.
  The paragraph is then cut into sentences and each one asked separately — the problem is not
  "the model is lazy" but attention drifting over a long context, and asking sentence by sentence
  gets past it.
- **unify repeats** (`core/repeats.py`): if the same source was translated differently in different
  places, it is aligned to the majority rendering. So "Chapter" does not become "Bölüm" in one
  place and "Kısım" in another.

## 2.6 Fitting

If a translation does not fit its box, these are tried in order: **shrink** (down to the 0.85
floor) → **ask for a shorter rendering** (a shorter translation from the model) → **push down**
(grow the block if there is room below it) → **flag**. `--fit-mode reflow` adds a step (tightening
the leading and pushing down) but is **off** by default: on the NIST journal it took D1 from 52 to
0, but on the IRS form the pushed-down blocks ran into untouched text (L7 0→1). The gain depends on
the document while the loss is a losslessness violation — the rule is: *a proven loss means the
default stays off.*

A **leading step** (tighten the line spacing before asking the model for a shorter text) was built
on 2026-09-20, measured, and **reverted**: with the fitting pass's own substituted font it rescued
no block on the book, and the written-page A/B came back identical in both arms. The measurement
also answered the bigger question: most flagged blocks are not short of lines, they are short of
*box* — `room_below` can shorten a block's measured box to six points to keep it clear of the next
one, and nothing fits in six points. See Chapter 3 and `docs/campaign/JOURNAL.md`.

## 2.7 Writers, and the decision to write

The PDF writer draws the page **from the source file**: each block is redacted in its own box and
written again. Blocks that did not change are left alone (a name, a document code, a running header
stays exactly as it was — erasing and redrawing it loses its typography). Blocks are drawn with an
HTML box plus CSS, which means using the browser engine's work for alignment (centre, right,
justify) and font mapping.

The DOCX and EPUB writers pour the same DocIR into their own formats. `writers/converter.py`
manages the format pairs and, per D7, offers **only measured** pairs.

## 2.8 The checker: the part that sets the project apart

`verify.py` compares the output against the source and counts ten kinds of loss (L1–L10) and three
quality thresholds (D1–D3). The audit runs on **both sides**: on the DocIR before writing, and on
the written PDF itself. The second is critical — some bugs only appear *in the drawing* (text
overlapping text, a word past the page edge, text landing on a figure).

The audit does not merely report: when it finds a loss it **asks again** (`ask_again`), mends what
can be mended, and flags the rest with its reason. The "review queue" the user sees in the
interface is exactly those flags — every row has a reason, and the reason is written in the
interface's language.
