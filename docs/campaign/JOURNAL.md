# Translation campaign journal

Goal (set 2026-09-16): translate `computer-systems-Architecture.pdf` and five different English
books of at least 100 pages found on the internet, **losslessly**, documenting every step, result
and test, and present the results comparatively.

Every entry: what was done, why, the evidence, and the commit. Newest last. This file is the
raw material for the final report (`docs/campaign/REPORT.md`, written when the goal is met).

Environment: LayoutKeep branch `layout-model`; translation model `google/gemma-4-e4b` on LM
Studio (local, 8 parallel slots); layout model `docling-layout-heron-onnx` (Apache-2.0);
text recognition RapidOCR (PP-OCR ONNX); EN -> TR.

---

## Definition of "lossless"

A translation is lossless when all of these hold, measured on the output against the project
file saved for every chunk (what was sent, what came back, what was flagged):

| id | criterion | measured as |
|---|---|---|
| L1 | same pages | output page count == source page count |
| L2 | no text left untranslated | translatable blocks whose written text is still the source, or still reads as English (English stopword share), == 0 |
| L3 | no text dropped by the writer | translated blocks whose words are not found on their output page == 0 |
| L4 | nothing drawn off the page | words outside the page box == 0 |
| L5 | no markup leaked | tags (`<0>`, `</text>` ...) in the output that are not in the source == 0 |
| L6 | nothing the source keeps as-is was damaged | formulas, figures and wordless blocks are not redrawn (checked by tests; spot-checked visually) |

Reported alongside, not part of the pass/fail: **D1 readability** - blocks the fitting pass
could not fit at the readability floor and drew smaller (their text is present, so this is not a
loss, but it is a quality cost), and visual spot checks of sampled pages.

Known limits declared up front, so they are not quietly counted as success:

- Text recognition errors on a scan (e.g. "Fuls nu a uo s sd--s") are translated as read. The
  audit cannot tell a misread from a correct read; they are counted from visual samples.
- Text inside figures is kept as scanned (a product choice made on 2026-09-16: redrawing
  diagram labels damaged the diagrams).

---

## 2026-09-16 - before the goal: the layout model work

Summarised from `tests/layout_eval/` (all evidence there):

1. Heron layout model measured on its own over 50 pages of 6 document types before building on
   it (`2026-09-16_heron_pure/`): region finding far better than the old rules; main raw
   defect duplicate boxes (190 -> 3 after `resolve_duplicates`).
2. Integrated into the scanned-page reader; 10 book pages translated in rounds 1-5 and compared
   side by side with the original (`2026-09-16_e2e_translation/`), plus a NASA report as a
   different document type (`2026-09-16_e2e_nasa/`). Defects found by looking, each fixed with a
   test that fails without it: source line visible after hyphen join; table cells merged; text
   smaller than source (two causes); formula half painted out; diagram labels redrawn over the
   drawing; echoed replies not retried; patches on tinted paper; centred titles flush left;
   folio glued to running header; table rules erased; caption with the next paragraph appended.

| round (10 book pages, model) | prose still English | overflowing blocks |
|---|---|---|
| 1 | 1 / 82 | 48 |
| 3 | 2 / 82 | 46 |
| 4 | 0 / 82 | 34 |
| 5 | 2 / 82 | 34 |

Commits: `066e232` .. `86be2ae`.

## 2026-09-16 - goal start: why a paragraph stayed English through every retry

Round 5 still left book page 61's first paragraph in English, although translating that page
alone produced Turkish. Reading `fitting/fit.py`: when a Turkish translation overflows its box,
fitting asks the model for a shorter rendering. If the model hands back the English source, the
English is shorter than the Turkish - so it fits, and was accepted as a successful
"retranslation", replacing the correct translation. Fitting runs after the retry pass, so no
earlier safeguard could see it.

- Test first: `tests/test_fitting_fit.py::test_a_shorter_rendering_that_is_the_source_is_not_accepted`
  failed with exactly that (English text written back).
- Fix: `fit._is_source` - a re-rendering equal to the source is not accepted, in both the
  shrink and the expand direction. Shared by the CLI and the desktop worker.

Also changed for the campaign: `tools/audit/translate_book.py` now saves each chunk's project
(`.lkproj`) and full log, so the audit reads what was actually sent and returned.

## 2026-09-16 - the lossless audit, and what it found on its first run

`tools/audit/lossless_audit.py` implements L1-L5 and D1 over a `translate_book.py` work
directory, reading each chunk's saved project and output PDF.

Pilot: the same 10 book pages, translated with every fix so far (`_artifacts/campaign/pilot10`,
7.5 min at 8 parallel requests).

| | L1 pages | L2 untranslated | L3 dropped | L4 off page | L5 markup | D1 below floor |
|---|---|---|---|---|---|---|
| pilot10 | 0 | 5 | 0 | 0 | 0 | 16 |

The older completeness tool had reported 2 verbatim paragraphs for the same kind of run; the audit
found 5, because it also catches a reply that is English but not byte-identical.

Two causes behind the five, read from the per-chunk logs and projects:

1. **The model echoes the same segments on every attempt** (exercises 1-14, 1-15, 8-5 and its
   sub-item): one retry does not recover them. All carry formulas, variable names or recognition
   noise.
2. **A paragraph came back in English with its recognition noise corrected** (page 251, "Simple
   CPU design examples ...") - identical to nothing, so no check caught it.

The audit's own criterion was checked against all its findings before being trusted: a first
version that used "identical" with no length floor reported 39, of which 34 were labels and
formulas ("NAND", "F1 = xy", "a. A*B + C*D") that correctly stay unchanged. L2 now judges only
blocks with at least four content words; the remaining findings are all real.

### Fix for cause 2: a language-independent "copy of the source" check

`passthrough.is_copy_of_source`: when a majority of a reply's content words also occur in its
source, the reply is the source (verbatim or lightly edited). A translation keeps names, acronyms
and technical terms and changes the rest. It compares the two texts, so it needs no word list for
either language. Used by the retry pass and by the audit. Tests:
`test_a_reply_that_only_cleaned_up_the_source_is_retried`,
`test_a_translation_sharing_names_and_terms_is_not_taken_for_a_copy`. (The retry tests' fake
translator used to return `"TR:" + source`, which is itself a copy - changed to a reversed string.)

### Cause 1: measured before fixing

`_artifacts/campaign/echo_experiment/`. The four stubborn segments were sent to the model 12 times
in four request shapes (as a batch / one at a time, with / without a stronger instruction), all
**without** the neighbouring-paragraph context the pipeline sends: translated 12 times out of 12.
So the instruction wording is not the cause; the next experiment sends the same segments with
their real context.

### Other fixes in this stretch (each with a failing-first test)

- **Searchable scans read as born-digital** (`test_pdf_reader_hidden_ocr_layer.py`). Two of the
  five campaign books are archive.org "Text PDF": a page image with an invisible OCR text layer
  (render mode 3; 136 and 137 of their pages). Read as digital, the writer removed the invisible
  layer and drew the translation over the scanned English, which stayed. A page whose image covers
  most of it and whose text is mostly invisible is now read as a scan. A designed page with a
  background picture and visible text stays digital (tested).
- **The invisible English layer survived in the output** of a scanned page, so the page looked
  Turkish but searched and copied as English: the scanned-page writer now redacts text (never
  images) under translated blocks.
- **`</text` leaked into a paragraph** (round 5, page 251): the model closed a JSON value with a
  tag named after the field. `openai_compat._parse_reply` strips `<text>`, `</text>`, `<id>`
  tags; the numeric style markers are untouched, and "<textbook>" is not matched (checked).

## 2026-09-16 - the five books

Chosen for difference, each exercising a path the architecture book does not:

| # | book | pages | kind | how it reads | rights |
|---|---|---|---|---|---|
| 0 | computer-systems-Architecture | 524 | 1990s textbook scan, no text layer | scanned (OCR + layout model) | user's file |
| 1 | Electricity in Agriculture (1922) | 148 | old book scan with hidden OCR layer | scanned (136 searchable + 12 image-only) | public domain, archive.org |
| 2 | Think Python, 2nd ed. | 244 | born-digital textbook, code listings | digital | CC BY-NC 3.0, Green Tea Press |
| 3 | NIST SP 800-12 Rev. 1 | 101 | born-digital government report, tables | digital | US government work |
| 4 | The Time Machine (H. G. Wells) | 120 | born-digital novel, plain prose | digital (1 image page) | public-domain text, Planet eBook edition |
| 5 | Popular Science Monthly, Jan 1920 | 144 | magazine scan: columns, adverts, pictures, hidden OCR layer | scanned (137 searchable + 7 image-only) | public domain (US, pre-1929), archive.org |

Total 1281 pages. Downloaded to `_artifacts/campaign/books/` (not committed).

## 2026-09-16 - cause 1 found: the context makes the model echo

Second experiment (`_artifacts/campaign/echo_experiment/run_context.py`, `result_context.txt`):
the same whole pages sent to the model three times each way.

| request | trial 1 | trial 2 | trial 3 |
|---|---|---|---|
| with neighbouring-paragraph context (as the pipeline sends) | 4 / 4 English | 4 / 4 English | 4 / 4 English |
| without context | 0 / 4 | 0 / 4 | 0 / 4 |

Deterministic, not noise. Resending the identical request - what the retry pass did - can never
recover these.

**Fix:** `retry_untranslated` sends its retry without `context_before` / `context_after`; the main
pass keeps context, which helps everything else. Test
`test_the_retry_is_sent_without_the_context_that_caused_the_echo`.

Pilot rerun (`_artifacts/campaign/pilot10b`, 6.3 min): **L2 5 -> 1**, L1/L3/L4/L5 still 0,
D1 16 -> 12.

## 2026-09-16 - the last one: two definitions of "the source handed back"

The remaining L2 block (page 61, "When the circuit is disabled ...") was flagged as an echo, and
still written in English. Hypothesis first: its source carried noise style markers
(`<0>...</0>` around whole lines - on a scan these come from per-box size/colour measurement
noise, not real bold) and those make the model echo. **Refuted** by experiment
(`run_markers.py`): with markers 4/4 translated, plain 4/4 translated.

Actual cause, from the project file: fitting's guard compared a re-rendering with the source
*including* its markers; the model's English reply had none, so they were "not equal" and the
English was accepted. The retry pass used a different comparison (word overlap) that ignored
markers - two definitions of the same thing, and the gap between them let the English through.

**Fix:** one definition, `core/copies.py` (`is_identical`, `is_copy`: markers removed, whitespace
and case normalised, plus the majority-word-overlap test), used by the retry pass, the passthrough
report, fitting and the audit. Pure text in `core/`, so fitting does not import the provider
layer. Test `test_the_source_is_recognised_even_when_its_style_markers_were_dropped` failed first.

## 2026-09-17 - campaign run 1 stalled: replies that never end

First book (NIST SP 800-12, 101 pages) started 00:09. After 38 minutes: zero pages out. All
eight chunk processes idle, waiting on the server; the server "GENERATING"; its log's last
completed reply at 00:09:58.

Cause: no request set `max_tokens`. A reply that does not stop holds its slot until the 56,000-
token context is full, and the client's protection is slow by design - an adaptive timeout of up
to 900 s, retried 3 times, so one runaway reply can occupy a worker for up to 45 minutes. Eight
of them and the server is taken.

**Fix:** every request carries `max_tokens`, derived from the request (one output token per two
characters sent in the user message, at least 512) - about twice what the input itself takes,
room for a longer target language and the JSON. A reply cut there is malformed, which the
provider already splits, retries and flags. Tests `tests/test_http_max_tokens.py` (failed first).

Only the campaign's own processes were stopped (matched by their `_artifacts/campaign/runs`
command line). The server returned to IDLE when the clients disconnected.
