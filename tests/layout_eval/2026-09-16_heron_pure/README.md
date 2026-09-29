# Heron layout model, on its own - 2026-09-16

What `docling-project/docling-layout-heron-onnx` does **before anything is built on top of it**:
each detected region drawn exactly as the model returned it (threshold 0.5), no XY-cut, no
paragraph rules, no size ceiling, no reordering. Taken so that whatever is added later is added
against a measured baseline, not a guess.

Regenerate (images land in `_artifacts/pure/`, which git ignores - copy here to keep):

    python tools/audit/layout_pure.py --source <pdf> --pages 1,2,3 --dpi 200

Model: Apache-2.0, 171 MB ONNX, 0.33 s/page on CPU. Its own report (arXiv 2509.11720) gives
78% mAP for the best variant. Installed at
`%LOCALAPPDATA%\LayoutKeep\models\docling-layout-heron-onnx\`.

## Numbers

| set | pages | regions | dup | orphan / lines | shared | frag | mixed_col |
|---|---|---|---|---|---|---|---|
| book (scanned, 600 DPI textbook) | 10 | 150 | 32 | 7 / 503 | 0 | 7 | 13 |
| notes (scanned, A4 ~100 DPI) | 8 | 18 | 0 | 0 / 69 | 0 | 0 | 0 |
| synthetic styles, 6 x 3 DPI | 18 | 57 | 22 | 0 / 248 | 0 | 1 | 1 |
| arXiv 1706.03762 (digital) | 5 | 71 | 8 | 4 / 308 | 0 | 4 | 3 |
| IRS 1040 + W-4 (forms) | 4 | 224 | 21 | 3 / 585 | 5 | 6 | 2 |
| NASA report (old scan, 2 columns) | 5 | 131 | 107 | 14 / 212 | 0 | 3 | 2 |

- `dup` prose region lying mostly inside another prose region (same text boxed twice)
- `orphan` OCR lines in no region - text the model missed
- `frag` leaf region whose text starts lowercase - **over-counts**: a symbol list ("drag, lb")
  starts lowercase legitimately
- `mixed_col` leaf region holding lines more than 3 line heights apart horizontally - also
  over-counts hanging indents (`1-10.  Simplify ...`)

## What the pictures show (judged by eye, not by the numbers)

- **Book and NASA report: close to right.** Paragraphs, section headers, captions, pictures,
  page headers, and both columns of the NASA report come back as separate, correctly labelled
  regions. `nasa_report_p5`: every symbol-list entry and both prose columns correct.
- **Book p54 (exercises): the reported "equation taken for a heading" bug is gone at the
  source** - every displayed equation is `formula`, every exercise a `list_item`.
- **The main raw defect is duplication**, not wrong boxes: the same line boxed as both `text`
  and `list_item` (NASA symbol list, 107 dups on 5 pages), or a loose box around several
  paragraphs beside a tight box for each (A4 synthetic).
- **Real miss: `small_trim_200dpi`** - the margin keywords (`decoder`, `enable`, `inverter`)
  are boxed together with the body into one region. At 100 DPI the same page is right. The
  fixture itself is artificial (identical paragraphs, last one clipped), but a merged margin
  note would put a stray word inside a translated paragraph, so this must not be trusted blind.
- Orphans are few (28 of 1925 lines overall), mostly on the NASA report's figure pages.

## Conclusion at this point

The model alone solves region finding and labelling far better than any rule this project had,
on real documents. What it does not do by itself: resolve its duplicate boxes, guarantee a
region holds one column, give reading order, or give type sizes. Those are the only things worth
building on top - each to be measured against this baseline.

## Layers added on top, each measured

**1. Duplicate boxes** (`layout_detector.resolve_duplicates`): a box holding two or more other
prose boxes is dropped as their union; of two boxes over the same text, the higher score stays.
Across all 50 pages: dup 190 -> 3, orphan lines 28 -> 29.

**2. Reader integration** (`image_reader._page_from_image(layout=...)`): each text region
becomes blocks with the model's role; inside a region the page's whitespace (XY-cut) still
separates what the box merged; lines in no region, or in a picture/table, take the old path;
blocks are ordered by XY-cut; nothing but a title or heading may be larger than body/list text.

`tools/audit/page_eval.py`, 10 book pages:

| | blocks | frag | tall | lowconf | chars | size spread median / max |
|---|---|---|---|---|---|---|
| before this branch | 279 | 17 | 24 | 20 | 18612 | - |
| XY-cut only (no model) | 271 | 17 | 28* | 20 | 18620 | 1.15 / 1.39 |
| XY-cut + model | 274 | **8** | **21** | 19 | 18615 | **1.00 / 1.09** |

\* not a regression: the same 13.8pt boxes exist in both; three fewer single-line blocks moved
the metric's median from 8.6 to 8.3, and 13.8/8.3 crosses its 1.6 threshold where 13.8/8.6 did
not (page 451).

Synthetic styles, 18 pages: 0 fragments with and without the model.

Notes document: spread median 1.32 -> 1.28, max 1.63 -> 1.67 - **a correction, not a
regression**: the notebook's printed "my notes" label is now a heading and keeps its 30pt,
where an earlier attempt (before duplicates were resolved) wrongly capped it to body size and
the metric looked better for it.

**Known limit, measured and left:** paragraphs separated only by a first-line indent, with no
blank space between them, come out as one block when the model boxes them together (synthetic
`turkish` 3 -> 1, `small_trim` body 3 -> 1). Adding the indent rule back inside regions fixes
those and costs the book frag 8 -> 15, so it is not added. On the book itself the model splits
such paragraphs correctly (`first_probe_book_p61.jpg`).

## Note: images removed from the public repo (2026-09-20)

The `*.jpg` images here contained pages of copyrighted sources, so they were **untracked** (the
files stay on this machine; the rule is that openly licensed content is published and the rest
stays local). The measurements and the method above are unchanged, and the images can be
regenerated with the commands given here.

