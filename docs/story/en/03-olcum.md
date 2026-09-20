# 3. Measurement discipline: how the numbers are produced, and how measurement itself was wrong

The lesson this project repeats most: **a wrong measurement is worse than no measurement.** A wrong
number is not ignored — it produces a correction that has to be corrected, burns human hours, and
after a while makes the claim of "lossless" untrustworthy. This chapter first describes what
measurement is here, then the four times it was wrong.

## 3.1 Ten loss kinds, three quality thresholds

`verify.py` counts these criteria on every run. The rule: **every criterion is either zero or has a
written reason.**

| Code | What it counts | How it is measured |
|---|---|---|
| **L1** | Page count differs | The page counts of the source and output PDFs |
| **L2** | Left untranslated, or in another language | The words on the output page are compared against the source's language |
| **L3** | Text not on the page | A block in the DocIR cannot be found in the output |
| **L4** | Text past the page edge | A word box outside the page rectangle |
| **L5** | Markup leaked | A `<…>` pattern in the output |
| **L6** | Numbers lost in translation | The source's set of numbers is looked for in the output |
| **L7** | Text drawn over other text | Word boxes overlapping |
| **L8** | Untouched text moved | A block that stayed as it was in the source, elsewhere in the output |
| **L9** | Letters from another script mixed in | Example: `Việt語` — Latin and CJK in one word |
| **L10** | Text drawn over a figure | A word box intersecting an image box |
| **D1** | Below the readability floor | Blocks whose type size went below the 0.85 scale |
| **D2** | Short blocks left unchanged | Blocks shorter than three words that were not translated |
| **D3** | Text squeezed in its box | The space between words collapsed to zero |

L criteria are **losses**, D criteria are **quality**: an L violation means "something was lost" and
is not acceptable; a D finding means "something got worse" and is counted, reported, and fixed
where possible. The book run's final table (220 pages, 4,491 translatable blocks):
**L1=1, L2=2, L3=0, L4=0, L5=0, L6=4, L7=1, L8=1, L9=0, L10=0, D1=801, D2=163, D3=0.** The single
L1 is deliberate (the bibliography page at the end of the book was left out of the output), the two
L2s are bibliography rows, and the 801 D1s are long translations being shrunk — all of them with a
reason.

## 3.2 The audit tools

`tools/audit/` holds 56 tools; the ones used most:

- `lossless_audit.py` — sweeps a run directory and produces the L1–L10 + D1–D3 table (`audit.json`).
- `type_drift.py` — compares the **typography** of the written page against the style the reader
  recorded: blocks that grew (did a heading get bigger), blocks that shrank (the fitting ladder),
  blocks whose alignment changed, blocks that fell to an unreadable size.
- `text_over_image.py` — deepens L10 only (see 3.3, the first wrong measurement).
- `side_by_side.py` — produces the four-panel visual comparison (original | old | new | model).
- `comparison_site.py` — turns every run into one site with a slider (that is the published site).
- `translate_book.py` / `translate_epub.py` — chunked, multi-worker live run drivers.
- `rewrite_run.py`, `repair_book.py` — rewrite or mend an existing output with the current engine.
- `live_check.py`, `format_matrix.py`, `translation_completeness.py` — measurements for format
  pairs and translation completeness.

The tools share a rule: **the output is machine-readable** (JSON) and **carries no claim**, only
numbers.

## 3.3 Measurement itself was wrong four times

### Case A: L10's false positives — half the numbers were a measurement bug

L10 means "text drawn over a figure". The first implementation counted a loss whenever a word box
intersected an image box. The results were: cookbook **182**, mushrooms **124**, the book **6**,
arXiv **25** — that is, it looked as if every document had text on its figures.

Looking one by one, two bugs appeared:

1. **Full-page and tiled scan images.** In a scanned document the whole page is one image; every
   word on top of it counted as "over a figure". The rule was fixed: if the **union** of the image
   areas covers essentially the whole page (≥100%), L10 does not apply.
2. **The source's own graphic labels.** The axis labels inside an arXiv paper's chart were already
   in the source; the translation preserved them, and they were counted as "lost". The rule was
   fixed: a word the **source also wrote** is not an L10 loss.

The corrected measurement: cookbook 182→**0**, mushrooms 124→**0**, book 6→**0**, arXiv 25→**0**
(all false positives). On the Wikipedia runs 13/13 were **real** — and the re-translation brought
them to **0**. So the fix both removed the false positives and kept catching the real case. The same
rule moved into the core (`verify.words_over_figures`); on the NIST journal L10 went 8→0.

### Case B: "obviously bigger type" — a measurement bug, not a code bug

The user reported "in some examples the type is obviously bigger". The first measurement had matched
each written line against the source line **of the nearest height**. On a form, every label sits in
the same height band as its value — a 10-point label was "compared" against its 12-point neighbour,
and a correct page looked inflated. The measurement was rewritten to match the style and geometry
the reader **recorded for that block** (`type_drift.py`); the result: **no block grew.** The problem
was not in the code but in the measurement — and that was only understood by auditing the measuring
tool itself.

### Case C: alignment flags — reading past the column boundary

For a while `type_drift` said "alignment changed" for 4 blocks on arXiv. Looking block by block, the
source was **justified** (every line 72→540, last line short) while the output was flush left with a
ragged right edge — a real loss, but **its cause was not where it was expected**: the writer already
supported `text-align: justify` (blocks are drawn as HTML boxes), and what was missing was **the
reader never producing "justify"** (it only produced left/right/center).

The fix needed two distinguishing rules: straight left edges **and** a short last line **and** the
last line's **left edge** level with the body. Without the third, a centred heading also read as
"justify" (its lines shorten too, but its last line starts in the middle) — the NASA cover heading
was drifting off centre for exactly that reason, and a test caught it. The indent rule added in the
same session was too broad as well: a centred block's first line (its longest) starts at the left
and must not be mistaken for an indent.

**Result:** 19 alignment tests + 218 reader/layout tests green; two old tests converted to the new
contract, four new ones added (ragged flush-left stays "left", a centred short line is not
justify, two right-aligned lines stay right). **In a real run the same day:** on the book's
re-translated chunks, 26 of 70 long body blocks were read as "justify" and `type_drift`'s alignment
flag came out 0 — the fix was verified from the measurement all the way to the drawn page.

### Case D: the probe answered a question the engine never asks (2026-09-20)

The book's largest review-flag class was "the translation did not fit its box" (1,130 of 6,014
blocks in 42 chunks). A **leading step** was added to the ladder: when the box does not fit even at
the readability floor, tighten the lines before asking the model. The step worked — it passed its
tests in a synthetic box.

The measurement was made twice and **the two disagreed**:

- *The probe* (measuring over a recorded run's translations): **20** of 158 overflowing blocks are
  rescued.
- *The instrumented pass* (the function wrapped and counted): over 6 chunks the step was called
  **14 times and fitted 0**.
- *The written-page A/B* (20 chunks, two arms): **identical** — D1=627, D3=0, every L the same.

The difference was one line: the probe measured with `block.dominant_style()`, while the pass
measures with `_as_drawn(…)` — the style with the target language's **substitute font** already
resolved. The two fonts have different metrics, and the probe was answering a question the engine
never asks.

**Result:** the step was reverted (the branch was never merged; the attempt stays in the journal as
`bbf5958`). The rule "a change the measurement does not show comes back out" saved an *idea* here,
not just a probe. The two instruments (`fit_probe.py`, `fit_ab.py`) stayed; neither spends a model
call.

**The next lever came out of the same measurement:** the 138 blocks no leading rescues are not
short of lines, they are short of **box** — `room_below` crushes a block's measured box to 6pt to
keep it clear of the next one, and nothing fits in 6pt. So the real work is overlap/room handling
(roadmap item 4), not the ladder.

## 3.4 The rules of the measurement infrastructure

What these four cases produced, and what is now written down:

1. **The measuring tool is itself tested.** `text_over_image.py`'s fix was verified by re-running it
   over old runs: it kept catching the real case (Wikipedia 13/13) and dropped the false positives
   (cookbook, mushrooms, book, arXiv).
2. **A measurement is cross-checked against the source's own data.** Something called a "loss" that
   the source also wrote is not a loss (the arXiv chart labels).
3. **A number that came out wrong is written down together with the corrected one.** Phrases like
   "182 → 0" are deliberate in this repository: hiding that the old number was wrong would take away
   the trust the new one needs.
4. **When a probe and the pipeline disagree, the pipeline is instrumented.** A probe measuring a
   change must use the inputs the engine uses (style included: the pass measures with `_as_drawn`,
   not with the block's style). The right move on a disagreement is to wrap the function under test
   and count — not to fix the probe.
5. **A default is off when a loss is proven.** `reflow` took D1 from 52 to 0 on NIST but took L7
   from 0 to 1 on the IRS form; the gain depends on the document while the loss is a losslessness
   violation — so the mode exists, but it is not the default.
