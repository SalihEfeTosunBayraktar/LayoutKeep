# 5. Choosing the model: which one, why — and the IBM Docling question

There are two separate model decisions in this chapter and they are often confused:

- **The model that translates** (an LLM): the local `google/gemma-4-e4b`, through LM Studio.
- **The model that finds the page's layout**: IBM Docling's **Heron** layout detector (ONNX).
- Plus a **third track**: a project-specific fine-tune (Qwen2.5-7B QLoRA), a separate effort.

The answer to "why did we move to the IBM model" is the **second** row, not the third: the IBM model
does not do the translating; IBM's model *understands the page*. Each decision's reasoning and
measurement is below.

## 5.1 The translation model: why local

The project's default is to run **locally**, and that is not a preference but a design axis:

| | Local (LM Studio) | Cloud (OpenAI-compatible, DeepL) |
|---|---|---|
| Does the document leave the machine | **no** | yes |
| Cost | none | usually some |
| Speed | depends on the GPU | network + provider |
| Quality | depends on the model (weaker on small ones) | usually stronger |
| Parallelism | the server's slot count | the provider's limit |

Cloud is **supported** (add an endpoint in the provider settings, try it with "Test" before saving a
key) — but it is not the default. The reason is simple: this is a tool for *documents*, and a user's
document (a copyrighted book, a personal scan, a corporate form) usually should not leave the
machine. Being local-first is a second promise standing next to the claim of "lossless".

On the local side there is a **one-model rule**: a single model is loaded on the machine and requests
go through it (apart from the parallel slots). That avoids the loading penalty and the instability of
swapping models while GPU memory is shared. The measured result: a 220-page book, 55 chunks, ~106
minutes.

## 5.2 The quality ceiling, and the pipeline's answer

A small local model's language ability is limited. The project's answer was not "find a better
model" but **putting mechanisms under the model rather than on top of it**:

- **Protected values** (numbers, measurements, DOIs/URLs, part numbers, Roman numerals) are never
  shown to the model — even if the model gets it wrong, they cannot be lost.
- **The glossary** forces terms (in the prompt and in the output check): the model cannot render
  "hypothesis" as "hipotez" in one place and "varsayım" in another.
- **The memory** gives the same text the same translation (across runs, in SQLite).
- **Unify repeats** aligns differing translations of the same source to the majority.
- **The checker** finds a loss, asks again, and flags what remains with its reason.

The measured consequence of this approach: the model's weakness stays in *the fluency of the text*,
not in *the integrity of the document*.

## 5.3 The IBM Docling (Heron) layout detector — the actual "IBM model"

### Why it was needed

The reading pipeline's classical method is **XY-cut**: it finds blocks by cutting the page along
horizontal and vertical gaps. It works well on aligned, clean pages and collapses on complex ones:

- a box inside a box (form fields), captions under pictures, formulas squeezed between two columns,
  footnotes spilling into the margin;
- scanned pages (no lines, only pixels).

In those cases what is misread is not the *text* but the **region boundary**: a heading merges into a
paragraph, a footnote enters the body, a table row becomes a block of its own. The result: the
translation is right and the placement is wrong — which is exactly what the user complains about.

### What was done

The layout model from IBM Research's **Docling** project (`docling-layout-heron-onnx`) was added.
The model looks at the page as an image and classifies its regions: heading, paragraph, table,
figure, list, footnote. It runs as ONNX **locally** (even on CPU), so it does not break the
local-first principle.

- It is enabled on the command line with `--layout-detector`; in the interface it is on by default.
- It only runs where it is needed: if a page can be read through its text layer and the structure is
  simple, XY-cut is enough; the model comes in on scanned or complex pages.

### The measurement: what actually changed

A **four-panel** comparison was produced over 10 book pages: `original | old run | XY-cut | with the
detector`. The metric measured: "prose still left in English in the output" and "words past the page
edge".

| | Prose left in English | Words past the page edge |
|---|---|---|
| Old run (524 pages, no model) | 6/82 (7%) | 0 |
| XY-cut | 6/82 (7%) | 0 |
| **With the detector** | **1/82 (1%)** | 0 |

What the model does **on its own** was recorded as well (`tests/layout_eval/2026-09-16_heron_pure/`):
every region drawn exactly as the model returned it — no XY-cut, no paragraph rules, no ordering.
That "clean baseline" is what let every rule added later be added against a **measured** floor; no
one assumed "the model probably finds this too".

### The V2 plan: why we did not rewrite

A **V2 plan** was written around the same time: rebuild the pipeline around Gemini, with the layout
model at its centre. The plan document sits at `docs/YENI_MIMARI_VE_GECIS_PLANI.md`. It was never
applied, because:

1. A rewrite would invalidate the losslessness audit (L1–L10) and more than 1,000 tests.
2. The working engine had **exactly one gap**: finding regions on complex pages. Adding the model to
   the *existing* reader was enough to close it — and that is what was done.
3. The V2 branch (`v2-vision-layout`) did not merge without conflicts (six of them); forcing it
   would have replaced measured behaviour with unmeasured behaviour.

So "moving to the IBM model" was not a **rewrite** but a **reading capability** added to the existing
pipeline. The useful part of the plan was taken and the rest sits in the archive — and that decision
is written down too: *an unproven fix is not kept, and neither is an unproven rewrite.*

## 5.4 The third track: a project-specific fine-tune (LayoutKeepLLM)

A separate workstream (in its own folder), chasing two goals at once:

1. **Conforming to the application's wire protocol**: a multi-segment JSON answer, `<0>…</0>`
   markers, protected-value tokens in the U+E000–U+E001 range, context/length limits. The aim is for
   the model to produce a **protocol**, not free text.
2. **Academically consistent EN↔TR translation** — not merely correct, but terminologically
   consistent.

The design decisions:

- Base model **Qwen2.5-7B-Instruct**; training **QLoRA on Kaggle** (not on the local GPU).
- The dataset's backbone is **hand-written domain-expert pairs** (generator:
  `01_Dataset/build_dataset.py`, corpus: `_dataset_corpus.py`); about 6,000 records in total.
- **OPUS-100 was rejected**: its EN-TR portion was measured and is weighted towards news and everyday
  speech — while what this project translates is academic and technical documents. "Plenty of data"
  and "the right data" are not the same thing.
- The training script **does not depend on TRL** (a plain `transformers.Trainer` plus
  `apply_chat_template`), because TRL's `SFTConfig` API changes between versions and the notebook
  kept breaking on Kaggle.

This track is **not used** by the product as it stands: the runtime model is gemma. The fine-tune is
a path kept for raising the quality ceiling; its measuring stick is the same: the L/D table and
terminology consistency.

## 5.5 Summary: which model does what

| Layer | Model/tool | Why that one |
|---|---|---|
| Page layout (scanned/complex) | IBM Docling **Heron** ONNX | Works where XY-cut collapses on region classification; runs locally; measured gain 6/82 → 1/82 |
| Text extraction (digital) | PyMuPDF | The most accurate source when a text layer exists; carries typography |
| OCR (scanned) | RapidOCR (PP-OCR models) | Gives a confidence score; low confidence is flagged |
| Translation | `google/gemma-4-e4b` (LM Studio) | Local, free, parallel across slots; the document never leaves the machine |
| Cloud translation (optional) | OpenAI-compatible endpoints, DeepL | Stronger models; only if the user chooses them |
| Quality guarantee | `verify.py` + the glossary + the memory | Does not let the model's weakness reach the document's integrity |
