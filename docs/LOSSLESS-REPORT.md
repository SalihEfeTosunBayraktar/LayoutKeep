# Measuring "lossless": a report on what this pipeline preserves, and what it does not

*A report for anyone deciding whether to trust LayoutKeep with a document. Every number in it was
produced by the tools in this repository, on the documents named, and can be reproduced with the
commands at the end. The Turkish companion is [`KAYIPSIZ_MOD_DURUM.md`](KAYIPSIZ_MOD_DURUM.md).*

---

## 1. The claim, made checkable

Translating a laid-out document is not one problem but several, and "it worked" hides which ones
you solved. A page can come back in perfect Turkish with one paragraph silently missing, a table
whose numbers changed, a footnote drawn over the line below it, or a figure's caption detached
from its figure. Nobody notices until it matters.

So this project states its claim as nine criteria a written document can be *checked* against,
plus three descriptive measures:

| | Criterion | The question it asks |
|---|---|---|
| **L1** | same pages | Did the page count survive? |
| **L2** | left untranslated | Is there prose in the source language still on the page? |
| **L3** | dropped by writer | Did text the pipeline meant to write fail to appear? |
| **L4** | off the page | Is anything drawn outside the page box? |
| **L5** | markup leaked | Did an internal marker (`<0>`, U+E000 tokens) reach the reader? |
| **L6** | numbers lost | Did a number, unit or date change or disappear? |
| **L7** | text drawn over text | Is one text drawn on top of another that the source kept apart? |
| **L8** | untouched text moved | Did text nobody translated move? |
| **L9** | garbled letters | Did a word come back mixed with another script or language? |
| **L10** | text on a figure | Was a word drawn inside a picture instead of beside it? |
| **D1** | below readability | Blocks set smaller than the readability floor |
| **D2** | short, unchanged | Short blocks left as they were - for a human to judge |
| **D3** | squeezed lines | Lines of one block forced into each other |

L1–L10 are loss conditions: any occurrence means the run is not lossless. D1–D3 are descriptive.
They exist because "no losses found" once described a page where *no block fitted as it was* and
everything was squeezed to 85% - true by the letter of the criteria, and not what a reader means.

The audit that computes them (`tools/audit/lossless_audit.py`, on top of `layoutkeep.verify`) is
run against the **written PDF**, not against the pipeline's intentions: it re-reads the output and
compares it with the source page by page, word by word, box by box.

## 2. How it is measured

Two bodies of documents, both kept out of the repository:

- **The held-out campaign** - 13 real documents, 328 pages: two arXiv papers (29 and 20 pages), an
  IRS instruction book (32 pages) and an IRS publication (48), a NASA scan, a PLOS article, two
  Wikipedia articles, a Gutenberg novel (15 pages, 2,624 blocks), two Internet Archive scans
  (1907 cookbook, 1895 mushrooms), and a WPA poster. Terms and provenance: [CREDITS.md](../CREDITS.md).
  Runs and results: [`campaign/HELDOUT.md`](campaign/HELDOUT.md), dated log in
  [`campaign/JOURNAL.md`](campaign/JOURNAL.md).
- **Live runs** - the same application, run end to end against a real model on a real paper
  (arXiv 2507.03009, "PDFMathTranslate"), which the pipeline had never seen when the fixes below
  were made. `tools/audit/live_check.py` translates, audits, and prints the difference against the
  previous run, and never overwrites a recorded measurement.

The model is a **local** one - `google/gemma-4-e4b` (quantised GGUF, 5.3 GB) on LM Studio,
7 parallel slots, no network. That is deliberate: a measurement that depends on a paid endpoint
cannot be re-run by a reader, and a slow, small model is the honest worst case for a pipeline that
has to repair and retry.

## 3. What the measurements found

The campaign's first pass was not lossless anywhere, and the reasons were not the ones the
architecture diagram suggested. Three classes of fault came out of running it, each fixed and each
re-measured:

### 3.1 A fit that only holds by shrinking is not a fit

On the arXiv table page, **no block of 70 fitted as it was** (`as_is=0`, 42 shrunk, 28 overflow)
while the audit reported *no losses*: the fitting pass could ask for smaller text, never for less
text, and never for more room. Prose set for a 220pt column came back at 9.4pt with 517-1138
characters in it.

Two changes: a block whose fit needs a scale under 0.95 now asks the model for a shorter rendering
of the same meaning (`fit.shorten_below_scale`), and a block may grow into the space the page
actually has under it (`fitting/growth.py`; the fitting pass and the writer call the same function,
so what is measured is what is drawn). Requests on that page fell from 14 to 7 and the shortest
"make it shorter" ask went from 6 characters to 51 - the ladder had been spending its rounds asking
a table cell reading `Ücretli` for four characters.

### 3.2 The same page, one word drawn over another

The first re-run after that fix came back with **L7 = 1** - an overlap on a page that had none.
Following it to the source took three separate faults, all in the same footer:

1. **A URL's hyphen was eaten.** `.../docs/api-` + `reference/chat/create` was joined into
   `.../docs/apireference/chat/create`, fusing two rows into one line 2.4× too wide. A hyphen join
   now requires a *word* (letters only) before the hyphen, and a continuation that starts no
   further right than the line above.
2. **A block that was never translated was treated as changed.** The pipeline records a block's
   original only when a segment comes back translated; an empty one means the text is *still the
   source* (its batch failed, or it was never sent). The writer redrew those in a substitute face
   from their box's left edge, which moved the URL's first row 82pt left - over the footnote.
3. **"Would this clearing reach that block" was asked of union boxes.** The URL block's box covers
   the footnote's, so it was redrawn even though the footnote's redaction touches neither of its
   rows. It now asks the block's own lines, and touching edges are not a reach.

Re-run, same document, same model: **L7 = 0, L8 = 0, D3 = 0, L1-L6 = 0.**

### 3.3 The reader's own mistakes, found by reading with two readers

A translated project collapses each block to one line, so comparing against saved projects cannot
answer "did the reader change?". `tools/audit/reader_ab.py` reads every held-out source with two
source trees - the committed one and the working tree - and prints what differs. Across 43 chunks:

| | before | after |
|---|---|---|
| arXiv footer | `https://platform.openai.com/docs/apireference/chat/create` - one line, hyphen eaten, 2.4× too wide | `https://platform.openai.com/docs/api-` + `reference/chat/create`, the source's own two rows |
| arXiv p1 | `Exclusion of the non-Englishspeaking` - hyphen eaten | `Exclusion of the non-English-` + `speaking world from ...` |

Two pages changed in content; every other line of all 43 chunks is identical, coordinates included.

## 4. Where it stands

Final live run on the unseen paper (10 pages, 149 blocks, 7 workers, 740 s wall clock):

| | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 | L10 | D1 | D2 | D3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| first measurement | 0 | 2 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 63 | 6 | 1 |
| after the fixes | 0 | 2 | 0 | 0 | 0 | 0 | **0** | **0** | 1 | 65 | 7 | **0** |

**What is still open, stated plainly:**

- **L2 = 2** - the bibliography rows naming authors, which the model returns unchanged. This is the
  documented behaviour of `--preserve-references` (off by default); with it on, L2 is expected and
  the metric has to be read differently, which is why it is a flag and not a default.
- **L9 = 1** - the appendix table of 56 language names. Asked in Turkish, the model wrote
  `Việt語` (Chinese characters inside Vietnamese). The prompt now names the target language *and
  its script* (`core/langs.py`); on the documents in the campaign this is the one loss class left.
- **D1 ≈ 65, D2 = 7** - by design. D1 counts table cells and captions that structurally have no
  room and no shorter equivalent; they are flagged for review rather than silently squeezed. D2
  lists short untouched blocks for a human eye, because "İstatistik" and "Statistics" are neither
  proof of translation nor of failure without knowing the language.

The honest summary: **on the pages measured, nothing is lost or drawn over, and the remaining
findings are either flagged for review by design or are language-quality issues in the model, not
in the layout.**

## 5. Reproducing any of it

```bash
# audit a recorded run again (no model needed)
python tools/audit/lossless_audit.py --work _artifacts/heldout/live/<run> --to tr

# translate a document with the real provider, audit it, compare with the recorded run
python tools/audit/live_check.py document.pdf --name my_run --workers 7

# re-write a recorded run's pages with the current writer and audit: minutes, no model
python tools/audit/rewrite_run.py _artifacts/heldout/live/<run>

# read every held-out source with two source trees and print what the change did
python tools/audit/reader_ab.py src /tmp/after.json

# look at every sample side by side, with a draggable divider
python tools/audit/comparison_site.py     # -> docs/comparison/index.html
```

## 6. Limitations

- **One model.** All numbers come from a 4B-parameter local model. A larger model would fail
  differently, and the repair machinery exists because this one fails often; the criteria are
  model-independent, the costs are not.
- **Deterministic proxies for meaning.** L6 compares numbers, L9 looks for mixed scripts, L2 looks
  for residual source-language prose. None of them can judge whether a sentence kept its meaning;
  that is what the 7 sparse flags and a human reading the comparison site are for.
- **Pages, not books.** The per-page criteria are exact; a book-level property such as running
  headers staying in the right place is covered by the held-out runs (2,624 blocks in one novel)
  but not by a single-page audit.
- **A "lossless" run can still be ugly.** D1 exists exactly because font size is not one of the
  nine: a page can lose nothing and still be a page nobody wants to read.
