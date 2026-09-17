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

## 2026-09-17 - born-digital pages read with the layout model too

Restarted run (with `max_tokens`) moved again: 9 NIST pages in 11 minutes. Looking at the first
finished pages before letting 1281 pages run:

- cover (NIST p1): layout, alignment, rules intact, clean translation;
- **table of contents (NIST p6): no word lost, structure lost** - entries run together
  ("... 16 3.13 Sistem ..."). The born-digital reader still uses the rule chain the model replaced
  on scans; it merged the entry lines into paragraphs and the translation reflowed them.

The audit measures lost *words*; this is lost *layout*, and it is recorded here so the report does
not count it as success.

Measured before building (`tools/audit/layout_pure.py` on NIST pages 6, 7, 20, 35, 60): the model
labels both contents pages `document_index`, and on text pages finds section headers and
paragraph boundaries.

**Change** (`pdf_reader._regroup_by_layout`, used when `--layout-detector` is on): the digital page
is rendered at 100 DPI for the model; its regions group the PDF's own lines - text, fonts and
positions still come from the PDF, nothing is re-recognised. A text region becomes one block with
the model's role; a contents, table, form or figure region one block per line; lines in no region,
and rotated text, keep the old rules; blocks built from the model are not fed back into the
"merge wrapped lines" rule. Tests `tests/test_pdf_reader_digital_layout.py` (two failed first; the
two that pass without it guard unclaimed lines and the no-model path).

On the real pages: contents p7 went from 9- and 12-line merged blocks to one block per entry;
text p20 now has its section headers as headings and a 16-line block split at its real paragraph
boundary (9 + 7).

The NIST run was stopped at 9 of 101 pages - every page it translated would have been discarded -
and replaced by a 30-page **digital pilot** first (10 pages each of NIST, The Time Machine and
Think Python: contents, prose, chapter openings, dialogue, code, tables, index), so defects on
the digital path are found on 30 pages instead of 465.

## 2026-09-17 - digital pilot 1: 30 pages of NIST, The Time Machine, Think Python

`_artifacts/campaign/digital_pilot`. First pass: **7 of 30 pages produced no output.**

### Pages lost to a crash: "Point: bad args"

Every NIST page carries a line rotated 90 degrees in its margin. When the writer cannot find a
rotated line again it falls back to redacting the line's box, built as `pymupdf.Quad(rect)` -
which this PyMuPDF rejects. The fallback, written for the rare case, had never run; the whole
page was lost instead. Traceback obtained by running the chunk through the CLI command with the
writer wrapped (the CLI turns writer errors into a one-line message). **Fix:** `rect.quad`, in both
fallbacks. Test `tests/test_pdf_writer_rotated_fallback.py` (failed first with the same error).
The 7 pages then translated on `--resume`.

### The audit's own false alarms, checked one by one

L2 reported 11, then 4 on the full 30 pages. Read block by block: names ("Michael Nieles Kelley
Dempsey ..."), a brand in a footer ("Planet eBook.com"), URLs (text extraction spaces them out:
"https: // thinkpython. com/ code/"), and a program's quoted output kept verbatim inside a Turkish
sentence. All correct translations. One was real: a Time Machine paragraph entirely in English.

**Fix, in `core/copies.py`** (so retry, fitting and the audit share it): a copy is judged on
*ordinary words* - lower-case, outside quotation marks and addresses, with spaced-out addresses
joined back first; "most" means strictly more than half. Short blocks too short to tell a name
from an untranslated phrase are no longer counted either way: the audit lists them as **D2** for
a human. Tests `tests/test_core_copies.py`, each case a real pilot block.

### The Time Machine paragraph: five hypotheses measured, none reproduced

It came back in English from the main pass and from the context-free batch retry. Sent to the model
in isolation it was translated **every time**: as-is 3/3, without its quotation marks 3/3, half of
it 3/3, 8 in parallel x 3 rounds 24/24, in a batch with its whole page 3/3, paired with one
neighbour 3/3 (`echo_experiment/run_quote.py`, `run_parallel.py`, `run_batch.py`). The trigger could
not be reproduced. **Fix, based on what was reproducible:** whatever still fails after the batch
retry is asked for one segment at a time. Test
`test_what_still_echoes_after_the_batch_retry_is_sent_alone`.

### Looking at the pages

- **NIST contents: structure now kept** (one block per entry, page numbers in place) - the
  layout-model change works. But entry sizes varied from 9.3 to 12 pt down one page.
- **The Time Machine and Think Python: justified body paragraphs drawn centred.** A regression of
  my own: alignment was inferred from where a block sits on the page, and a text column in the
  middle of a narrow page looks like a centred title; once the writer honoured alignment (the
  NASA cover fix), every such paragraph was centred.
- **Content loss the audit could not see: section numbers.** NIST contents "5.2.1 Basic Components
  ..." came out as "Program Politikasinin Temel Bilesenleri .... 27" - "5.2.1", "5.3.2", "5.4.1"
  gone. The audit's L3 only counts words with letters.

### Fixes for what the pages showed (each with a failing-first test)

- **Alignment from the lines, not the position** (`_layout._alignment_from_lines`): lines sharing a
  left edge are left/justified (from three lines on, a first-line indent is allowed); sharing a
  right edge, right; sharing only a centre, centred. Both readers decide alignment after every
  block has its final lines. Tests in `tests/test_layout_alignment_prose.py`.
- **Section numbers lost:** the cause was a whitespace run in another font becoming an inline
  marker ("5.2.1<0> </0>Basic ..."), which the model dropped together with the number. No marker
  is made around whitespace (`tests/test_docir_whitespace_markers.py`). And a reply that loses a
  number is not accepted: `core.copies.drops_numbers` (digit groups, so "3,14" matches "3.14") is
  used by the retry pass, and by the audit as new criterion **L6 - numbers lost**.
- **Uneven contents sizes:** leader dots are fill. `fit.even_leaders` resizes the translation's
  leader so the entry keeps the source line's length, and entries fit alike.

A fresh 30-page pilot with all of this is running in `_artifacts/campaign/digital_pilot2`.

## 2026-09-17 - digital pilot 2: untranslated reaches zero

`_artifacts/campaign/digital_pilot2`, 30 pages, every fix above, 15.0 min.

| | L1 | L2 | L3 | L4 | L5 | L6 | D1 | D2 |
|---|---|---|---|---|---|---|---|---|
| digital pilot 1 (after resume) | 0 | 1 | 0 | 0 | 0 | - | 52 | 2 |
| digital pilot 2 | 0 | **0** | 0 | 0 | 0 | 2 | 52 | 10 |

L6 did not exist in pilot 1, so its two findings are newly visible, not new.

### L6: numbers lost through the protection layer

Both on the NIST glossary page: "(1)" in a definition, and "4009" in "CNSSI 4009". The protection
layer holds numbers back as placeholder tokens; the model dropped the placeholder. Measured
(`echo_experiment/run_numbers.py`), 3 trials each:

| request | "(1)" kept | "4009" kept |
|---|---|---|
| through protection | 0 / 3 | 0 / 3 |
| plain text | 3 / 3 | 0 / 3 |

Protection *causes* the first loss; the second is the model rewriting "CNSSI 4009" as "CNSS".
Protection is not removed (it keeps values from being altered elsewhere).
**Fixes:** the retry's last, one-at-a-time attempt for a reply that lost a number bypasses the
protection layer (`retry._for_numbers`); fitting no longer accepts a shorter or longer rendering
that loses a number (`fit._is_source`). Tests
`test_a_number_lost_through_protection_is_retried_without_it`,
`test_a_shorter_rendering_that_drops_a_number_is_not_accepted`.

### D1: an unchanged header shrunk on every page

"NIST SP 800-12 REV. 1" is set in small caps and correctly comes back unchanged (a document code),
yet the writer removed its glyphs and redrew it in a wider substitute font, below the readability
floor. **Fix:** a block whose written text is exactly its source (letter case included - an
existing test caught a first version that ignored case, which would have skipped upper-cased
translations) is not redacted or redrawn: the original glyphs stay. Test
`tests/test_pdf_writer_unchanged_blocks.py`.

## 2026-09-17 - campaign book 1 of 6: NIST SP 800-12 (101 pages) - first full pass

Commit `dd6c2d6`, 44.2 min at 8 parallel requests.

| | L1 | L2 | L3 | L4 | L5 | L6 | D1 | D2 |
|---|---|---|---|---|---|---|---|---|
| NIST, first pass | 0 | 1 | 8 | 0 | 1 | 2 | 266 / 1578 | 124 |

A whole book shows what 30 sampled pages did not. Each finding read at the source:

- **L3 - URLs and an author name really gone** (DOI line on the imprint page, gpo.gov links in the
  references, "Victoria Yan Pillitteri"). Caused by my own previous fix: blocks that come back
  unchanged were left as set - and then erased by the redaction of a translated neighbour whose
  box reaches a few points into them (imprint page: sentence 328-341 pt, DOI line 338-351 pt).
  Before that fix these were redrawn, so the loss was new. **Fix:** a kept block that a changed
  neighbour's box reaches is redrawn like any other. The first test did not reproduce it (its two
  lines were close enough to be read as one block); rewritten to the measured geometry, it failed,
  then passed with the fix.
- **L5 - `<br/>` drawn on page 34.** The model formatted a reply with HTML. Replies are cleaned of
  line breaks (to a space) and common formatting tags; numeric style markers are untouched.
- **L2 - one paragraph "got no reply"** (page 72). Sent alone it translates every time. The retry
  that should have recovered it left no trace: it swallows transport errors silently, so a timeout
  under full load and a refusal look identical. **Fix for visibility:** a failed retry request is now
  logged with its error. **Fix for the loss:** a verify-and-repair loop (below).
- **L6 - "1996" dropped** from a sentence; a second L6 is doubtful (the extracted source repeats
  "part 1").
- **D1 266 of 1578 blocks (17%)** below the readability floor; D2 124, most of them the repeated
  running header "NIST SP 800-12 REV. 1" and author names, correctly unchanged.

### Verify-and-repair

A failure the pipeline cannot prevent (a batch reply missing a segment under load, a one-off echo)
does not repeat when its page is translated again. `lossless_audit.py` now lists every chunk with a
loss (`failing_chunks`), and `tools/audit/repair_book.py` deletes those chunks' outputs, translates
them again with `--resume`, and re-audits, for up to N rounds, recording each round in
`repair_history.json`. A loss that survives every round is visible as exactly that.

**Consistency note for the comparison:** these fixes landed while the campaign was translating The
Time Machine, so that book's pages were produced by a mix of code before and after them. Every book
gets the same repair rounds with the final code, and the report compares books after repair.

## 2026-09-17 - campaign books 2 and 3: The Time Machine, Electricity in Agriculture

### The Time Machine (120 pages, born-digital novel): lossless on the first pass

16.6 min. L1-L6 all 0 over 532 blocks; D1 74 (14%); D2 0. Visual spot check (pages 2, 8, 40, 77,
110): fully Turkish, coloured links keep their colour, page numbers in place. Typography not kept,
recorded rather than counted as loss: first-line paragraph indents are lost, and the licence
paragraph on page 2 is drawn centred.

### Electricity in Agriculture (148 pages, 1922 scan with a hidden OCR layer): first pass

42.9 min. The hidden-layer fixes held on a real book - spot check of pages 6, 21, 34, 51, 67: the
English is erased from the scan, the yellowed paper's texture is intact with no patches, photographs
and drawings untouched, captions translated. (The typeface changes from serif to sans.)

**7 pages produced no output**, so the book did not merge:

- 6 were pages with nothing to translate (blanks, plates). The CLI rightly refuses a document with
  nothing to translate; inside a book such a page translates to itself. `translate_book.py` now
  keeps it as it is, with a project the audit reads.
- 1 (page 140) was a 2,247-character paragraph that never came back, twice.

**The generation ceiling was too tight - my own regression.** LM Studio's log: 13 replies ended
with `finish_reason: length`, e.g. a 1,213-token request cut at 915 tokens. One output token per two
characters sent does not hold for Turkish, which takes more tokens than the English it translates;
a cut reply is malformed JSON, so its segments count as "no reply". **Fix:** one token per character
sent, at least 1024 (still bounded - a runaway cannot fill the context). Test
`test_the_ceiling_leaves_room_for_a_long_turkish_reply` (failed first).

After completing the missing pages: L1 1 (page 140), L2 8, L3 3, L5 1, L6 15, D1 22, D2 13 - 26
failing chunks. The largest losses sit in the longest blocks (the publisher's price lists, 40+
numbers each; a results table in prose), which matches truncated replies; they are left to the
repair round with the loosened ceiling rather than explained by guesswork.

**L5 "</vagon>"** - the model invented a tag named with a Turkish word. Handling tags by name
("<br/>", "</text") cannot keep up. **Fix:** any named tag the source does not itself contain is
removed from a reply; numeric style markers have no name and are untouched, and real content such as
"<stdio.h>" is kept (checked). Test `test_a_tag_the_source_does_not_have_is_removed_whatever_its_name`.

Commit `f6fbbe7`.

## 2026-09-17 - correction: "The Time Machine: lossless" was wrong - replies in the wrong language

Spot-checking Popular Science's first finished pages: a headline and its deck came back **in German**
("Sahne ist schockierend! Die Schauspieler sind aufgeladen ..."). The audit could not see it - the
words are not the source's (no copy), the numbers are all there. Measured across the finished books
with function-word profiles: replies not in Turkish in **every** book, including **The Time Machine,
which the audit had called lossless** (a paragraph in German) - so that verdict is withdrawn.
Partial translations too: "ELEKTRIK CIHAZLARININ TAHMINI GUC TUKETIMI OF ELECTRICAL APPLIANCES".

**Fix:** `core.copies.wrong_language(reply, target)` - function-word profiles for tr, en, de, fr, es,
it, pt, nl; a reply is in another language when that language's function words are at least 12% of
its words and outnumber the target's; quoted text and addresses left out; an unknown target is never
judged. Used by the retry pass (a wrong-language reply is resent, and not accepted) and by the audit
as part of L2 (`--to` gives the target). Tests in `tests/test_core_copies.py` (real replies) and
`test_a_reply_in_another_language_than_asked_is_retried`.

Re-audited (no re-translation):

| book | L2 before | L2 with language check | verdict |
|---|---|---|---|
| NIST | 1 | 1 | no |
| The Time Machine | 0 | **2** | **no** (was "yes") |
| Electricity in Agriculture | 8 | 15 | no |

Also seen on the magazine and recorded for the next step: on a dense multi-column page some
translated blocks are drawn over each other, and the erased English leaves grey smudges where the
scan is halftoned - the text is present, but part of it is not legible.

## 2026-09-17 - L7: text drawn over text

Popular Science's multi-column pages had translated blocks drawn over each other: legible nowhere,
though every word is present. The audit counted words, so it passed them. A measurement first
(overlapping word boxes from different lines, over 30% of the smaller): a broken magazine page 17
pairs; a clean novel page, a contents page, a scanned book page and the source PDF itself 0. Added to
the audit as **L7 - text drawn over text** (pages with any such pair).

Re-audited: NIST 3 pages, The Time Machine **46**, Electricity 16.

### Cause 1 - magazine: words of two columns joined into one line

On a page with a narrow gutter, OCR words of both columns at the same height were joined into one
"line" spanning x=33-570, so the translation mixed two paragraphs and was drawn over both columns.
**Fix:** with the layout model, words are grouped by region *before* they are joined into lines, so
a line can never cross a column the model found. Test
`test_words_of_two_columns_are_never_joined_into_one_line` (failed first).

### Cause 2 - novel: the writer's slack below reached into the next paragraph

The writer lays text out in the block's box plus 3 pt of slack right and below (for the renderer's
own inset). Paragraphs set close together have no room below: one box ended at 194.8 pt, the next
began at 194.1 pt, and the last line of one was drawn over the first line of the next.
**Fix:** `fitting/room.room_below` - the slack below is only what the page has free above the next
block in the same column; used by the fitting measurement and by the writer, so both agree. The box
itself is not shortened, because the writer clears the source by that box.

Verified on the real pages rather than only on a synthetic test (the synthetic test passed with and
without the fix, so it is a guard, not evidence): The Time Machine pages 3, 6, 7, 10 and 14 rewritten
from their saved projects - overlapping word pairs **18 -> 0**; visually no line over another, the
first paragraph slightly smaller. A one-line paragraph whose translation needs two lines is still
drawn very small - D1, not L7.

## 2026-09-17 - campaign book 4: Popular Science Monthly, January 1920 - first pass

The hardest document: 144 pages of a magazine scan with columns, adverts and decorative type.
3 h 06 min (dense pages; one took 23 minutes).

| L1 | L2 | L3 | L4 | L5 | L6 | L7 | D1 | D2 |
|---|---|---|---|---|---|---|---|---|
| 1 | 46 | 33 | 0 | 3 | 13 | 114 | 846 / 4222 | 89 |

(L1: two blank pages translated before the keep-as-is fix; `--resume` fills them.)

### The L7 fixes were not enough for the magazine - measured, not assumed

Split by when each page was translated: before the column/slack fixes 63 of 77 pages had text over
text; **after both fixes still 51 of 65**. On a post-fix page two different things were counted:

1. **Blocks overlapping each other:** the model's regions overlap *partly* (5-10 pt); duplicate
   resolution only removes near-containment. The slack fix could not help - the boxes themselves
   overlap. **Fix:** `room_below` may be negative; the writer stops drawing a block where the next
   block in its column starts (never shorter than 6 pt), the fitting pass measures the same box, and
   the box the source is cleared by stays whole. Test
   `test_negative_room_when_the_next_block_starts_inside_this_one` (failed first).
2. **A block's own lines squeezed into each other:** recognition noise from decorative adverts
   ("STHHTTLLTY", "PTH") forced into a tiny box. Not one text over another. The audit now separates
   it: **L7** counts words of *different* blocks; **D3** (reported, not a loss) counts a block's lines
   squeezed together.

Verified by rewriting 12 post-fix magazine pages from their projects: words of different blocks
drawn over each other **45 -> 17**. The remaining 17 read, word by word: advert recognition scraps 2-4
pt tall ("AR" over "STW"), already below the readability floor. The audit's L7 now counts legible
words only (at least 5 pt tall) - smaller text is D1 territory.

Re-audited first-pass outputs (not yet repaired): L7 NIST 1, The Time Machine 26, Electricity 3,
Popular Science 61.

## 2026-09-17 - campaign book 5: Think Python (244 pages) - first pass, and what its L2 really was

78.6 min. First audit: L1 0, L2 18, L3 1, L4 0, L5 0, L6 7, L7 2, D1 419 / 3696, D2 15, D3 0.

The 18 "untranslated" blocks, read one by one, were three different things:

1. **Real English left** (4): "3. If I leave my house at 6:52 am ...", "The reason for the IndexError
   ...", and two more - loss, for the repair round.
2. **Python code** (6): ">>> eng2sp = {...}", "def different_words(hist): return len(hist)", a
   traceback. Code should stay as it is - but these blocks had been *sent for translation*, and some
   came back with the strings inside `print()` translated, which changes the program the book
   prints. **Fix:** a born-digital PDF marks runs set in a monospaced face (PyMuPDF span flag 8;
   Think Python's code font SFTT1000 carries it on every span, its body text on none). `Style` now
   records `monospace`, and a block entirely in such a face is role CODE - not translatable. Test
   `tests/test_pdf_reader_code_blocks.py` (failed first).
3. **Correct Turkish taken for another language** (6) - false alarms of the new language check:
   "... olursa ne olur?" read as French ("ne"), "Sekil 16.1'e" as Italian (the apostrophe split off
   "e"), "Latince'deki" as Dutch; and "Iste bir kare cizen for ifadesi" flagged by the audit's older
   English-stopword share because of the Python keyword "for". **Fix:** apostrophe suffixes stay
   part of their word; another language needs at least two different function words; the crude
   English share is removed from the audit (the language check covers it). Test
   `test_short_turkish_sentences_are_not_taken_for_other_languages` (failed first).

Every finished book re-audited with the refined checks (still first-pass outputs):

| book | L1 | L2 | L3 | L4 | L5 | L6 | L7 |
|---|---|---|---|---|---|---|---|
| NIST SP 800-12 | 0 | 1 | 8 | 0 | 1 | 2 | 1 |
| The Time Machine | 0 | 1 | 0 | 0 | 0 | 0 | 26 |
| Electricity in Agriculture | 1 | 9 | 3 | 0 | 1 | 15 | 3 |
| Popular Science, Jan 1920 | 1 | 35 | 33 | 0 | 3 | 13 | 61 |
| Think Python | 0 | 13 | 1 | 0 | 0 | 7 | 2 |

(Think Python's L2 13 still counts the code blocks, which only a re-translation with the code fix
removes.) The architecture book is translating; repair rounds for all six follow it.

## 2026-09-17 - repair round works: The Time Machine lossless, checked by eye

`repair_book.py`, all current fixes (commit `7e52d51`), while the architecture book translates:

| round | chunks with a loss |
|---|---|
| before repair (re-audited first pass) | 26 (L2 1, L7 26) |
| after round 1 (9.6 min) | 1 (page 41) |
| after round 2 (1.6 min) | **0** |

Final: L1-L7 all 0; D1 72 of 532 blocks; D2 0; D3 20.

Not taken on the audit's word this time - the earlier "lossless" on this book was wrong. Pages
checked side by side with the original: page 41 (the paragraph that had come back in German) is
Turkish and nothing overlaps; page 14 (lines drawn over each other in the first pass) is clean.
Remaining, recorded as quality not loss: a one-line paragraph whose translation needs two lines is
drawn very small, some paragraphs are smaller than the source, and the model's wording is weak in
places ("Konakji hastaliklar tum konaklamam boyunca" for "contagious diseases during all my stay").

## 2026-09-17 - NIST repair: two losses that came back every round, and why

Rounds 1-3: chunks with a loss 8 -> 2 -> 2. A loss that survives re-translation is not chance;
both were read at the source.

1. **"part 1" lost on the references page (L6)** - a reader defect, not the model's. The page sets
   "[SP800-57 part 1]" in a narrow left column beside its entry; the model drew one region over
   both, and sorted by height the label's lines were interleaved with the entry's ("Recommendation
   [SP800-57 for Key Management ... part 1] Technology"). The model lost "part 1" from that mixture
   every time. Scanned pages already cut each region by whitespace; born-digital pages did not.
   **Fix:** `pdf_reader._cut_by_whitespace` - digital regions are split with the same XY-cut. Test
   `test_a_label_column_inside_one_region_is_not_mixed_into_the_entry` (failed first with exactly
   that interleaving).
2. **A URL's second line dropped by the writer (L3)** - a chain: a translated entry reached the
   unchanged line above the URL, which was therefore redrawn, and *that* line's clearing reached the
   URL line, which nothing had marked. **Fix:** the set of kept blocks to redraw grows until no
   clearing reaches another. Test `test_a_kept_block_reached_through_another_kept_block_is_not_lost`
   (failed first).

## 2026-09-17 - NIST lossless after repair; a layout defect the audit could not see

Repair with the two fixes above: chunks with a loss 2 -> **0**. Final: L1-L7 all 0; D1 270 of 1578;
D2 126 (the running header code and author names, correctly unchanged); D3 2.

Checked by eye, pages 71, 73 and 7 against the original. Page 71: every URL present, labels in their
column. **Page 73 showed what no loss criterion measures:** one-line reference labels ("[SP800-39]")
were still set in the middle of their entries' sentences - every word and number present, the
layout wrong. Cause: the label (x 77-136) sits 18 pt from its entry (x 154), just under the
whitespace-cut threshold for 16 pt lines. **Fix:** within a group, two lines side by side on one row
(overlapping vertically, disjoint horizontally, both at least two line-heights wide - so a footnote
mark beside a word is not a column) cannot be one run of text; the group is split at the gap
between them. Test `test_a_one_line_label_beside_its_entry_is_separated_however_narrow_the_gap`
(failed first); guard `test_a_superscript_beside_a_word_does_not_split_its_paragraph`.

Pages 81-84 re-translated: labels in the left column for 8 of the 9 entries on page 73; "[SP800-53A]"
still joins its entry (the longest label - PyMuPDF appears to deliver it on the same PDF line as the
entry's first line). Audit: **lossless**.

## 2026-09-17 - Think Python repair: 19 -> 10 -> 8 chunks, and what the eight were

Three rounds did not reach zero. Every remaining finding read at the source:

| finding | what it was | fix (failing test first) |
|---|---|---|
| L2 "... ne olur?" style | a correct Turkish sentence called Dutch: Python's "in" + Turkish "de" | a function word the target language also has is no evidence (`test_a_function_word_the_target_shares_is_no_evidence_of_another_language`) |
| L6 "3 sifir olmadigi icin" | "0" written as the word "sifir" - nothing lost | the target language's words for 0-10 count as those digits (tr, en, de, fr, es) (`test_a_small_number_written_as_a_word_is_not_lost`) |
| L2 "3. If I leave my house ..." (2 exercises) | echoed through three rounds, yet translated when sent by hand under the same load | a failing segment is asked for alone up to 3 times, not once (`test_a_lone_segment_that_keeps_echoing_is_asked_more_than_once`); the old "exactly one attempt" test now asserts a bound instead |
| L6 exercise "3." lost | the model drops the leading list number, every time | a list label ("3.", "1.4.", "a)") the source starts with is put back when the reply lost it (`test_a_leading_list_number_the_model_dropped_is_put_back`) |
| L3 "__main__" | **a stack diagram's labels, translated**: "letters" became "harfler", "delete_head" "basligi sil", the value 'c' became 'k', "t" and "__main__" vanished - the figure no longer described the code | text inside a picture region is FIGURE on digital pages too, as on scans (`test_text_inside_a_picture_is_kept_as_it_is_on_a_digital_page_too`) |

The last one is the worst kind of defect in this campaign: no count in the audit says "the diagram
is wrong", only one missing word hinted at it.
