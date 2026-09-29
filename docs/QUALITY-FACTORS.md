# What decides how good a translation comes out

The README states the factors in a sentence each; this is the measured version, with the numbers
and the cases behind them. The same settings produce very different results on different documents,
so a claim about quality is only meaningful next to the document it was measured on.

## The factors, with what was measured

| Factor | What it does | The measurement |
|---|---|---|
| **The document's kind** | An EPUB keeps its layout in CSS; a digital PDF is next, because its text sits exactly where the source put it; a scanned page is the fragile one — text is recognised, the old letters are painted out, and the translation is written back, so OCR sits in the loop | EPUB conversion holds 95%+ layout fidelity; the held-out scan (`nist_ir6643_vapor_pressure`) exists precisely to exercise the OCR path |
| **Scan resolution and cleanliness** | Clean 300 dpi scans read reliably. Skewed, stained or low-resolution pages lose characters, and a lost character is a lost word | Cropping a page to its content area once ate a whole paragraph on a dense page — threshold-guarded now, and the case became a regression test |
| **The model's skill in the target language** | The biggest lever on the *text*: numbers, names and lists come through faithfully, idioms and terms are where it stumbles | `việt語` for "Vietnamese" was an artefact of asking for a language *code* instead of its *name*; the prompt now names the language and its script |
| **The language pair's length behaviour** | Turkish and English are not symmetric, so the same paragraph needs different room in each direction | English → Turkish measures **0.93x** on average and **0.64x–1.40x per block**. A block far shorter than its box is flagged rather than padded with invented words; one that runs longer is asked for again in shorter form, then shrunk, then flagged |
| **Tables and forms** | The most flagged areas, for a structural reason: a cell has room for the source's words, not for a translation that runs longer | `--fit-mode reflow` (still being measured) lets a block push the ones under it down instead of shrinking |
| **The page range** | A range narrows the *output* too | Choosing 40–60 produces a file with those 21 pages, while the saved project keeps the whole document, so re-exporting cannot silently shorten it |
| **The model server's configuration** | A local model's context window is shared across its parallel slots | Parallelism defaults to **2**; `-c 8192` with 7 workers leaves ~1.2k tokens per request and a long paragraph overflows it — the failure read as "model not found" until the error body was opened. 32768 for 7 workers is what this project runs |
| **The glossary and the translation memory** | A term list pins the vocabulary; the memory translates a repeated string once and keeps it identical everywhere | On a re-run of a document the memory had seen, the first chunks finished in 21 s instead of 229 s |
| **The settings** | Lossless mode, repeat unification, dedupe and piecewise repair trade speed for fidelity | The defaults are the lossless ones; `docs/KAYIPSIZ_MOD_DURUM.md` records what each one costs |

Nothing here is hidden from a run: each factor shows up in the fitting line
(`as_is=50 shrunk=9 expanded=2 overflow=3`), in the audit (L1–L10 loss conditions, D1–D3
descriptive ones) or in the review queue inside the application.

**Also handled, because real documents do this:** rotated text at any angle, mirrored text
(detected and flagged rather than silently un-mirrored), bold and italic runs carried through
translation as inline markers, and metric-compatible font substitution when the original font
cannot render the target language.

**The short version:** the model decides whether the translation reads well, the document decides
whether the layout survives, and the audit decides whether either is true. The `L1`–`L10` criteria
in the application's help screen are the same list from the other end.

## Where the numbers come from

- `docs/BENCHMARK.md` — reader, fit and writer timings on the held-out set.
- `docs/MEASUREMENTS.md` — the per-document audit tables.
- `docs/LOSSLESS-REPORT.md` — the campaign written for an outside reader.
- `docs/campaign/HELDOUT.md` — every sample, its licence and which failure it exists to catch.

## Known limits, and where each is measured

The README keeps one line per limit; the cases behind them live here.

| Limit | The case behind it |
|---|---|
| EPUB→PDF re-flows the book | MuPDF's Story engine resolves the book's own CSS; chapter headings start fresh pages and sizes carry over, but the result is not pixel-identical to a hand-set PDF |
| The EPUB reader captures ~99% of a book's visible text | Measured across the Gutenberg held-out books; images survive as `ImageRef`s so rebuilt documents keep their figures |
| Terminology drifts slightly across segments | `docs/MEASUREMENTS.md` §6; the translation memory keeps a repeated string identical, dedupe keeps a document's repeats identical |
| Mirrored text is detected, not un-mirrored | Flagged (`metin aynalanmış, olduğu gibi geri yazılacak`) rather than silently rewritten |
| Writing a large PDF is slow and slows per page | `insert_htmlbox` embeds a font copy per call; the per-page curve is in `docs/BENCHMARK.md` |
