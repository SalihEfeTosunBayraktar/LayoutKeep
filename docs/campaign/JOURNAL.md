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

## 2026-09-17 - L8: untouched text that moved (Think Python Figure 3.1)

Looking at Think Python pages after repair, Figure 3.1 (a stack diagram) had labels one line lower
than in the original, some drawn over each other. Nothing had translated them - the picture fix
above keeps them. Only the two pages where the shift made words overlap had shown up at all (as L7).

**New loss criterion L8 - untouched text moved:** on born-digital pages, every source text run that
no translated block covers must be in the output at the same place (same text, x and y within half
the run's own height). The tolerance is measured, not chosen: kept blocks redrawn because a
neighbour's clearing reached them land 2-3 pt off (NIST's author names), which is no damage;
Figure 3.1's labels dropped 10-11 pt, a whole line.

**Cause:** the figure is a form XObject. MuPDF's redaction rewrites every form on the page it
touches, even when no redaction rectangle is inside it, and the rewritten form's text came out
shifted. **Fix (`redact_keeping_forms`):** after redaction, each rewritten form is put back to its
original object unless a redacted area actually held words of that form. Tests
`test_redaction_elsewhere_leaves_form_text_where_it_was` (failed first) and
`test_text_redacted_inside_a_form_stays_redacted`. On the real page: moved runs 9 -> 3, the figure
visually identical to the original.

**Rewrite without the model (`tools/audit/rewrite_book.py`):** a writer defect does not need the
translation again - every chunk's project holds the translated document. The tool redraws the
chosen chunks from their projects with the current writer and merges the book. Think Python: 11
pages rewritten, L8 11 -> 2.

## 2026-09-17 - the last two L8 findings were two different things

**Chunk 0129 (Figure 11.1, dict/list diagram): a stale project, not a new defect.** Labels
translated ("dict" -> "sozluk", "hist" -> "tarih") and digits displaced. Read again with the current
code, all 28 labels are FIGURE (the model labels the region `picture`, 0.95). The page was
translated before the picture fix, and `rewrite_book` redraws the saved project, which still holds
the old blocks. So a reader fix needs a repair round (re-read, re-translate), a writer fix only a
rewrite.

**Chunk 0160: a justified line cut into two paragraphs.** A line of the paragraph came out of the
PDF as two lines - a URL fragment in the code font, a space stretched by justification, then
prose. The side-by-side rule (NIST's reference labels) took them for two columns and cut the
paragraph there; the URL's continuation became its own block, the paragraph was squeezed to a
fraction of its size. The audit saw it only as one "." that moved. **Fix:** a cut is a column gap
only if no line of the group crosses it - a paragraph's other lines run across a stretched space,
two real columns leave it empty. Test
`test_a_justified_line_split_at_a_wide_space_stays_in_its_paragraph` (failed first). The real page
reads as one paragraph again.

The rule was checked on every page of the three born-digital books before keeping it: the guard
decides a cut on 36 Think Python pages and on none of NIST or The Time Machine (so NIST's reference
labels still split). The one that looked risky, the two-column index (p. 221), reads better with it:
the left column comes back as one block instead of three.

## 2026-09-17 - a scanned catalogue page lost whole (Electricity in Agriculture, chunk 0140)

Reading the remaining Electricity findings one by one: the L6 "numbers lost" on chunk 0140 was not
a lost number but a lost page. The publisher's catalogue at the back - thirty book titles with
authors and prices - was one block, and the reply to it was "s. d.", the price column's heading.
The model had labelled the page `document_index` (0.82), as it labels a table of contents; born-digital
pages already read that label one block per line, but on the scanned path it went through the
paragraph cut, which found no gap. **Fix:** an index's lines are one block each on scans too.
Test `test_an_index_region_is_one_block_per_line_on_a_scan_too` (failed first). The real page reads
as 70 blocks, one per entry line.

## 2026-09-17 - stale projects: a reader fix does not reach a page read before it

Two findings in a row (Think Python 0129, Electricity 0140) were pages read by an older reader.
`rewrite_book.py` fixes writer defects only; a reader fix needs the page read and translated again.
Worse, some reader defects leave no count behind - a diagram's labels translated word for word lose
nothing the audit measures. **New tool `tools/audit/stale_chunks.py`:** reads every chunk again with
the current reader and lists those whose translatable blocks differ from the saved project. Those
chunks go into the next repair round alongside the ones with losses.

First results: **Think Python 81 of 244 chunks read differently now, NIST 2 of 101, The Time Machine
0 of 120.** A sample of what Think Python's differences are (chunks 0065, 0094): blocks translated in
the first pass that are now FIGURE - a stack diagram's "countdown" written as "geri sayim", a string
diagram's "fruit" as "meyve", the letter "a" as "bir". The page that the audit counted as lossless
carried diagrams that no longer match the code beside them. **So "Think Python: L1-L7 = 0, L8 = 2"
did not mean lossless.** Those 81 chunks go into the next repair round.

## 2026-09-17 - projects forgot which pages were scanned

Re-auditing Electricity after the audit fix above changed nothing, and L8 - a check for
born-digital pages only - suddenly reported nine of its scanned pages. The project files say
`"scanned": true`; `load_project` returned False. The flag was written but never read back.

This is a product defect, not an audit one: every scanned page drawn from a project - a book redrawn
with `rewrite_book.py`, a document corrected in the review window and exported - went down the
born-digital writer path, where redaction does not touch the image and the translation is drawn over
the scanned English. (No campaign output was affected: only Think Python, born-digital, had been
rewritten.) **Fix:** the page's `scanned` is read back. Test
`test_a_scanned_page_is_still_scanned_after_a_project_round_trip` (failed first).

Also fixed in the audit: an unchanged block on a scanned page is not drawn - its text is the scan's
pixels - so it is no longer checked against the text layer (Electricity 0020: our OCR read the
running header as "APYJIN", the file's own invisible layer as the title, and the "missing" word was
never missing from the page).

**Open question raised by the same page:** the file's own OCR layer read that header correctly and
ours did not, so the header was never translated - and no criterion notices an untranslated line
that is not recognisable English. Which text source is better on searchable scans is to be measured,
not assumed.

## 2026-09-17 - measured: the file's own OCR layer is not better than ours

The open question above, measured (`tools/audit/ocr_source_compare.py`, every 10th page of both
searchable scans; result in `tests/layout_eval/2026-09-17_ocr_source/`). No transcription exists, so
each reading is scored by the share of its words (3+ letters) found in an English vocabulary built
from the three born-digital books' text layers:

| book | pages | invisible layer | our OCR | pages where the layer scored higher |
|---|---|---|---|---|
| Electricity in Agriculture | 14 | 76.7% | 75.3% | 7 of 14 |
| Popular Science Monthly | 14 | 73.6% | 74.6% | 4 of 14 |

A point either way, and a split by page. **Decision: the text source stays as it is**; the running
header read as "APYJIN" is a single miss, not a pattern that switching would fix. (Limits of the
measure: a vocabulary from modern books under-counts 1920s terms for both sources alike, and a
known word read in the wrong place still scores.)

Re-audit of both scans with the project loader fixed (scanned pages audited as scans again):
Electricity L1 1, L2 9, L3 0, L5 1, L6 13, L7 3, L8 0; Popular Science L1 1, L2 34, L3 17, L5 3,
L6 11, L7 61, L8 0. Neither has had a repair round yet.

## 2026-09-17 - the repair plan, from stale projects and audited losses

`stale_chunks.py` on all five translated books, against the audit's failing chunks:

| book | chunks | read differently now | with a loss | both | to translate again |
|---|---|---|---|---|---|
| NIST SP 800-12 | 101 | 2 | 0 | 0 | 2 |
| The Time Machine | 120 | 0 | 0 | 0 | 0 |
| Think Python | 244 | 81 | 2 | 2 | 81 |
| Electricity in Agriculture | 148 | 30 | 26 | 10 | 46 |
| Popular Science Monthly | 144 | 38 | 82 | 28 | 92 |

The overlap is the point: on the scans, 10 of 26 and 28 of 82 chunks with a loss were also read
differently now - the reader fixes since their first pass reach those losses. And on Think Python,
79 chunks with no measured loss would have stayed wrong. `repair_book.py --stale` puts both sets
into round 1; later rounds take the audit's losses only. Books are repaired one at a time, so the
server never has more than 8 requests.

## 2026-09-17 - campaign book 6: computer-systems-Architecture (524-page scan) - first pass

Translated in 313.9 min (8 parallel requests, one page per chunk, layout model on). Note for the
record: each chunk runs the CLI as its own process, so the pages were translated with the code as
it stood when each chunk started - fixes made during the run reached the later pages only. The
stale-project check settles which pages that matters for.

First-pass audit, 7417 translatable blocks: **L1 0, L2 41, L3 0, L4 0, L5 0, L6 39, L7 0, L8 0**;
D1 567, D2 99, D3 0. No text dropped, off the page, leaked or drawn over other text on any of the
524 pages; what remains is untranslated or wrong-language replies and lost numbers - the kind a
repair round has fixed on every other book.

## 2026-09-17 - Think Python after the stale-project repair

`repair_book.py --stale`: round 1 translated the 81 stale chunks again with the current code (31.4
min), round 2 found **0 chunks with a loss: L1-L8 all 0**, D1 390, D2 12 (was 16). This time the
count means more than before - the pages whose diagrams had been translated are among the 81, and
the check that exposed them (`stale_chunks.py`) is what put them into the round.

# Phase 2 - into the product, then unseen sources

The user's question after the campaign's first results: are these fixes cumulative and forward
looking, or arranged per document? The answer had two halves. The code fixes are general rules
(no condition anywhere looks at a book's name, page or file - checked: the 31 mentions of campaign
books in `src/` are all in comments recording why a rule exists). But the verification, the repair
rounds and the layout model's use were campaign tools: a user of the application got none of them.
Decision (user): carry both into the product first, then measure on as many unseen sources as
possible, with the product as a user runs it and no campaign repair.

## 2026-09-17 - verification and repair in the application (`layoutkeep/verify.py`)

- **The loss criteria L1-L8 moved into the package.** The audit tool now calls them and keeps only
  its diagnostics (D1-D3). Checked that nothing changed in the move: the rewritten audit on NIST,
  The Time Machine, Electricity and computer-systems-Architecture gives the same counts, block
  totals, failing chunks and examples as the committed tool, on all four.
- **After writing, the CLI and the desktop worker verify.** Losses a new request can mend (L2 wrong
  language / untranslated, L6 numbers) are asked for again through the retry machinery, fitted
  again, applied and the output written again, up to `--verify-rounds` (default 2) and only while a
  round mends something. Everything still lost - including what no request mends (L3, L4, L5,
  L7, L8) - raises the review flag on its block with the reason ("doğrulama: ..."), so the review
  queue names every place the output departs from the source. The CLI prints a `verify` line;
  the worker adds the counts to the completion statistics.
- **The layout model is used whenever it is installed**, in the CLI and in the desktop worker
  (which had never used it). `--no-layout-detector` turns it off; `--layout-detector` still makes
  a missing model an error. Tests run without whatever model a machine has installed (conftest),
  so their results do not depend on LOCALAPPDATA.
- Tests: `test_verify.py` (7: wrong language flagged with its reason, lost number, asking again
  mends and rewrites, a request that mends nothing is not repeated, L3/L7/L8 found on real PDFs
  and attributed to the right blocks), `test_cli_layout_default.py` (4), and the CLI end-to-end
  test now requires the verify line.
- Live, one page through the CLI with defaults against LM Studio: `verify 9 blocks checked, no
  losses found`. That page did not exercise a repair; the measurement that does is next.
- The overlap check now sweeps words sorted by height instead of comparing every pair - same
  result (the four-book comparison above includes L7), far fewer comparisons on a dense page.

## 2026-09-17 - the completion screen says what verification found

The worker already sent the counts; the screen showed none of them. It now reports, in Turkish,
English and German, segments mended by asking again, losses flagged for review by kind, or that no
loss was found (`test_ui_completion.py`: 2 tests, failed first). A job that was not verified says
nothing about it.

## 2026-09-17 - held-out measurement: sources never seen during development

**Method.** The application as a user runs it - layout model on (installed), verification on,
`--verify-rounds 2` - and *no* campaign repair. The code is frozen at commit `bad981a` in a git
worktree (`_artifacts/heldout/code`, imported through PYTHONPATH), so a fix made while the
measurement runs cannot reach the pages still waiting. PDFs go through `translate_book.py` one page
per CLI process, 7 in parallel (the CLI sends its own batches one after another, so this is only
throughput - each page is exactly one `layoutkeep translate`); the EPUB and the image run as one CLI
call each, on the eighth connection. Every output is then audited with `lossless_audit.py`, whose
criteria are now the same code as the application's verification - so the audit is not an
independent judge of the verification. Visual checks against the source are what cover that.

Downloaded with the user's approval (licences checked on the source page):

| source | kind | pages | licence |
|---|---|---|---|
| arXiv 2609.19145 | academic paper, math, tables | 20 | CC BY 4.0 |
| arXiv 2609.19113 | academic paper | 29 | CC BY 4.0 |
| PLOS ONE 10.1371/journal.pone.0235750 | journal article, figures | 30 | CC BY 4.0 |
| Wikipedia "Photosynthesis" (PDF export) | encyclopedia, images, references | 33 | CC BY-SA |
| Wikipedia "Printing press" (PDF export) | encyclopedia | 19 | CC BY-SA |
| IRS Publication 505 | government guide, worksheets, tables | 48 | public domain |
| IRS Form 1040 general instructions | dense multi-column instructions | 126 | public domain |
| Twentieth Century Cook Book (1907), archive.org | searchable scan, recipes, lists | 140 | public domain |
| Our Edible Toadstools and Mushrooms (1895), archive.org | searchable scan, plates; every 3rd page | 121 of 362 | public domain |
| NASA NTRS 19750007530 | one-page image-only scan | 1 | public use permitted |
| The Adventures of Sherlock Holmes, Project Gutenberg | EPUB to EPUB | book | public domain (US) |
| WPA poster "Occupations related to mathematics" (1938), Wikimedia Commons | image to DOCX | 1 | public domain |

Two sources were dropped before download: a Library of Congress newspaper page (the site answered
with a bot check, which is not something to get around) and three US agency PDFs that refused
scripted access.

## 2026-09-17 - held-out finding 1: a letter from another alphabet inside a word (new criterion L9)

The first held-out output, the WPA poster (image to DOCX), passed verification ("8 blocks checked,
no losses found") and was not clean. Read block by block against the source:

| source (OCR) | translation | what it is | flagged? |
|---|---|---|---|
| MECHANICAL ENGINEER 7 | MAKİNE MÜHEN**Д**İSİ 7 | a Cyrillic letter inside a Turkish word | **no** |
| FEUERAL ARI IHVALE (OCR of the poster's credit line) | an invented agency name | hallucination on garbage input | yes - OCR confidence 0.73 |
| E三三三 (a graphic read as text) | nonsense letters | noise in, noise out | yes - OCR confidence 0.74 |
| ACTUARY STATISTICIAN | a wrong term for "actuary" | translation quality, not a loss | no (no criterion claims it) |

The low-confidence readings already reach the review queue. The Cyrillic letter reached nobody.
Measured before building anything: across the campaign's 21,618 translated blocks, words mixing
letters of two alphabets appeared 3 times, all genuine - "MÜHENДİSİ" twice more in Popular Science
(the same model, the same word, in capitals) and a kana mark glued to a Turkish word. A first
version also caught subscripts, superscripts and fractions ("A₃", "x²", "l½", 20 blocks in
computer-systems-Architecture and Electricity): those are not letters, and only letters count now.

**Fix:** `core.copies.garbled_words` - a word of the reply mixing letters of two writing systems,
one of which the source does not use. The retry pass asks again for such a reply (and does not
accept one), and verification reports it as **L9 garbled letters**, asks again and flags what
remains. Tests: `test_a_letter_from_another_alphabet_inside_a_word_is_garbled`,
`test_scripts_the_source_has_and_symbols_that_are_not_letters_are_not_garbled`,
`test_a_reply_with_a_letter_from_another_alphabet_is_retried`,
`test_a_letter_from_another_alphabet_is_a_loss_asked_for_again` (all failed first).

The held-out measurement keeps running on the frozen commit without L9; its outputs are audited
with both criteria sets, so the effect of the new check is visible rather than mixed in.

## 2026-09-17 - held-out finding 2: serif text redrawn in a sans (Type 1 fonts, and a fallback that ignored the serif flag)

arXiv 2609.19145, page 4, first held-out paper: the layout survived - two columns, display
equations and footnotes in place - but every translated paragraph was drawn in a sans, much
smaller than the Times-like source, and 13 of the page's 15 blocks overflowed. The fitting pass
then asked the model for shorter versions one by one, which is also why that one page took 27
minutes. Think Python's output had shown the same thing ("NimbusSans-Regular" for a Palatino
source) and it had gone unremarked.

The chain, measured:
1. The source faces are Type 1 programs ("%!PS") - what pdfLaTeX embeds, and most older publishing.
2. `resolve_font` checks an embedded font's glyph coverage with fontTools, which opens only
   TrueType/OpenType; on a Type 1 program it raised `TTLibError`.
3. The writer caught that and gave up on the style, falling back to a generic family chosen by the
   font's *name*: "NimbusRomNo9L", "URWPalladioL", "CMR10", "LMRoman", "TeXGyreTermes", "Charter",
   "Utopia" all carry no hint, so all became `sans-serif` - although the reader had the PDF's serif
   flag on every one of those spans.

**Fixes:** a font whose program cannot be opened has unknown coverage, and substitution proceeds as
if no bytes were given (`test_an_embedded_type1_font_does_not_stop_substitution`, failed first);
the writer's last resort asks the font classification first and the source's serif flag when the
name cannot answer - a recognised sans name still outranks a careless flag, as in resolution
(`test_pdf_writer_serif_fallback.py`, the serif case failed first).

**Measured on the real page** (the held-out run's own Turkish text, fitted and written with each
version, no model call): before - NimbusSans for 3,795 characters, NimbusSans-Italic for 259;
after - Noto Serif for 3,790, a serif italic for 259, Noto Serif Bold for the heading. Overflowing
blocks 3 -> 2 in that offline fit. Seen side by side with the source, the paragraphs now carry the
paper's typography instead of a Helvetica.

Not fixed and noted: inline math inside a paragraph is flattened to plain text in the translation
("n^D_{s1,s2}" becomes "nD s1,s2") - no criterion measures it; and fitting measures with a generic
family while the writer draws with the resolved font, so the shrink it decides is not measured on
the face actually drawn.

## 2026-09-17 - held-out finding 3: "text drawn over text" on an untouched equation

arXiv 2609.19145 page 4: verification flagged L7 on a page whose display equations were not
translated and stand exactly as set. Rendered side by side, the flagged spot is a superscript over
a subscript - the equation's own typesetting, which PyMuPDF happened to split into separate text
blocks. Counted: the *source* page itself has 14 overlapping word pairs; the output had 11 flagged.

**Fix:** a pair of overlapping words both standing where the source set them (same text, within
1 pt) is the source's typesetting, not text drawn over text. `overlapping_words(..., as_in=source)`;
test `test_words_that_already_overlap_in_the_source_are_not_drawn_over_each_other` (failed first).
A PDF-level synthetic test was tried first and passed without the fix - PyMuPDF puts two
overlapping `insert_text` runs into one text block - so it was replaced by a word-level test.

**Measured:** the arXiv page 11 -> 0. The campaign's real overlaps stay visible: Electricity 3 -> 3;
Popular Science 61 -> 54, and each of the 7 pages that dropped out has at least as many
overlapping pairs on its source page (1/1, 3/14, 2/2, 5/5, 2/2, 1/1, 2/2) - the magazine's own
invisible OCR layer overlapping itself, not text the pipeline drew. Popular Science also shows
**L9 = 3** under the new criterion (the words found when L9 was measured).

## 2026-09-17 - held-out finding 4: a page lost to a crash in form restoration

arXiv 2609.19145 finished at 15:53 with one page missing (L1): page 18 raised
`FzErrorSyntax: invalid key in dict` in `redact_keeping_forms` - the fix for Think Python's
Figure 3.1. pdfLaTeX writes `/PTEX.FileName (./vocab_venn5.pdf)` into every PDF figure it
includes; restoring the form with `xref_copy` sets it key by key, and PyMuPDF parsed the path in
that value as a key path. So any paper with an included PDF figure could lose the page it is on.

**Fix:** the form is restored as a whole object (`update_object` + `update_stream`), and a form
that still cannot be restored keeps MuPDF's rewrite instead of taking the page down - a label a
little off is reported by verification (L8); a missing page is not a trade anyone would make.
Test `test_a_form_pdflatex_tagged_with_its_file_name_is_restored_without_crashing` reproduces the
crash with the same key on a synthetic figure (failed first). The real page now writes, and
verification finds no loss on it.

The first held-out paper's audit (commit bad981a, no repair): L1 1 (this crash), L2 7, L6 2, L7 8,
L8 2; the L7 count predates the typesetting fix above.

## 2026-09-17 - correction to the held-out protocol: code switched under running processes

To let later sources benefit from fixes found on earlier ones, the frozen worktree was moved to the
new commit "between documents" by a watcher that polled for the end of one document. It lost the
race by two seconds - the next document's first pages had already started - and it overlooked a
worse problem: a CLI process imports some modules when it starts and others only when it reaches
them (retry, verification, the PDF writer). The EPUB run, started at 14:49, would have loaded the
new `providers/retry.py` against the old `core/copies.py` it had loaded at start and crashed at the
end of the book. Nothing had been measured wrongly yet, but it would have been.

**Fix to the protocol:** all held-out processes were stopped (22, matched by path) and a second
runner started. The PDF worktree is moved only by the runner itself, before a document starts,
when no process of the previous one is left; the EPUB runs from its own worktree so those moves
never reach it; each run writes its commit to `commit.txt`. Kept as measured: the WPA poster and
arXiv 2609.19145 (both entirely at `bad981a`). Restarted from scratch: Wikipedia "Printing press"
and the EPUB. arXiv 2609.19145 runs once more at the end with the current code, for a before/after
on the same source.

## 2026-09-17 - held-out finding 5: what the first paper's losses were, one by one

arXiv 2609.19145 at `bad981a`, audited with the current criteria: L1 1, L2 7, L6 2, L7 1, L8 2, L9 0.
Every L2 and L6 block read against its source:

| block | what it is | verdict |
|---|---|---|
| p. 3 paragraph with inline math (set-minus written as a backslash) | never answered, through the batch and all lone retries | **real loss**, flagged |
| p. 7 paragraph "Distributional Properties of Tokens" | never answered; no backslash, but 43 style markers (every math symbol in its own font) | **real loss**, flagged; cause not yet proven |
| 5 bibliography entries | titles left as published; one entry has only its title translated; one has "and" written as "ve ve" | policy question (should references be translated at all?) plus one real defect ("ve ve") |
| p. 10 "Approximate top-down deletion scores" | a number dropped | **real loss**, flagged |
| p. 19 table header "95% CI" -> "% GA" | the 95 dropped | **real loss**, flagged |

**Finding and fix - one backslash lost the whole reply.** `json.loads` rejects a backslash that
starts no JSON escape, and the parser then treated the entire reply as malformed: every segment of
that batch unanswered, and a lone retry of the math paragraph failed the same way each time. A
backslash that begins no valid escape is now read as the literal character it is; valid escapes are
untouched. Tests `test_a_raw_backslash_in_a_reply_does_not_lose_the_whole_batch` (failed first) and
`test_valid_escapes_are_left_as_json_means_them`.

The paragraph with 43 markers is recorded as unexplained rather than given a cause: the application
does not keep the raw reply, and asking the server again now would exceed the 8 parallel requests
agreed for tests.

## 2026-09-17 - held-out finding 6: a page lost as one 4,000-character paragraph

Wikipedia "Printing press" (at `583027d`) finished with page 9 missing (L1). The page is four
paragraphs separated by blank lines; the layout model boxed the whole page as one text region, and
the whitespace cut inside it did not split them. Measured on that page: 15.0 pt between paragraphs,
2.5-3.2 pt between lines, and a cut threshold of 1.2 line heights = 15.9 pt (citation superscripts
make the line boxes tall). One 4,056-character segment went out, no reply came back, the CLI wrote
nothing for a document with no translated segment, and the book could not be merged.

**Fix:** inside a region, a gap of at least 3x the region's own usual gap between lines (and at least
half a line height) is a blank line between paragraphs. Test
`test_paragraphs_inside_one_text_region_are_split_at_their_blank_line` (failed first; a first
version ignored overlapping line boxes, which tightly set text has, and the synthetic case caught it).
The real page reads as 4 blocks (357, 1655, 723, 1234 characters). Checked for side effects with
`stale_chunks.py` on the campaign's born-digital books: The Time Machine 0 of 120 pages read
differently, Think Python 0 of 244, NIST the same 2 of 101 as before the change.

**Also:** a reply the parser cannot read now leaves its reason and the text around the fault in the
log (`reply     unreadable for N segment(s): <json error> at character K: '...'`), never the whole
reply. Two held-out paragraphs had gone unanswered with no record of why; the next sources collect
that evidence. Test `test_why_a_reply_could_not_be_read_is_said` (failed first).

Not changed, noted: when *no* segment of a document comes back, the CLI writes no output. For a
one-page chunk that is a lost page; for a whole document it avoids presenting an untranslated copy as
a result. Splitting the paragraphs removes the case that caused it here.

## 2026-09-17 - held-out result: arXiv 2609.19113, and finding 7 (a table cell answered with another cell's text)

arXiv 2609.19113 (29 pages, commit `6390410`, no repair): **L1 0, L2 1, L6 7, L7 1, L8 0, L9 0** over
511 blocks, D1 96; 27.6 minutes against about 66 for the 20-page first paper under the sans-font
defect. Every L2/L6 read against its source: 3 paragraphs lost a figure (e.g. "GPT's $2.46") and one
heading stayed in English - real, all flagged; 2 flags show no missing digit at all (a number
written as an ordinal, "round-1" -> "ilk tur") - the criterion's false alarms; and 2 table cells are
the finding below.

**Two cells holding "GLM-5.3" were written as unrelated text** - one as the neighbouring cell's
question translated ("Konu bireysel bir insan mi?"), one as a warning sign. Traced: the reply lost
the version number, so the retry asked again, once in a batch and three times alone. Reproduced
offline with a model that answers every request with "GLM-5.3": 4 requests, 0 accepted - each right
answer was rejected as an echo, and the wrong first reply stayed. A first fix accepted an identical
reply whenever the source has no ordinary words; the existing test for English headings failed at
once, because ordinary words exclude every capitalised word and "Decoder Expansion" looks exactly
like a name to that check. Reverted.

**Fix:** a source with no ordinary words (a name, a code, a label) whose every reply lost its
figures keeps the source text. A heading with no figures is unaffected and its echo is still retried.
Test `test_a_name_whose_every_reply_lost_its_figures_keeps_the_source` (the failing scenario first).

## 2026-09-17 - held-out result: PLOS ONE, and findings 8-10 (text cut off with nothing noticing)

PLOS ONE 10.1371/journal.pone.0235750 (30 pages, commit `6390410`, no repair): **L1 0, L2 3, L3 8,
L6 0, L7 0, L8 0, L9 0** over 468 blocks, 28.3 minutes. The 3 L2 are bibliography entries (the
references question again). The 8 L3 were one-line blocks whose last words were not on the page -
"...model su" drawn, "sekilde verilmistir" missing - and neither fitting nor the writer had flagged
them. Three causes, each measured before it was fixed:

**Finding 8 - fitting measured a narrower face than the writer drew.** The source face is Minion
(serif); with no font file resolved, fitting measured in the generic serif (Times) and found the line
fit at full size, while the writer substitutes Noto Serif. The same Turkish sentence at 10 pt: Times
260.5 pt, Noto Serif 335.8 pt - 29% wider. **Fix:** fitting measures with the font file the writer
will substitute (`pdf_pass._as_drawn`, the same resolution with the serif flag; the block's own style
is not changed). Test `test_a_line_that_wraps_in_the_drawn_face_does_not_fit_as_it_is`; a first
version of the test passed without the fix (its geometry left room to shrink) and was rebuilt on the
PLOS geometry, where it failed first.

**Finding 9 - `insert_htmlbox` reports a fit and draws only the first line.** Probed the same line in
Noto Serif across box heights: 11, 12, 13.5, 14 and 20 pt were reported as not fitting; at exactly
13 pt - a 10 pt glyph box plus the 3 pt slack, one line of 10 pt text - it returned "spare 0, scale
1.0" and laid out half the sentence. **Fix:** `measure_fit` counts a layout as fitting only if the
laid-out text holds the whole text (compared without whitespace and hyphens, ligatures unfolded);
the writer lays each block out on a scratch page first and draws the first attempt that holds all of
it - the floor, then no floor, then the box a little taller - never a layout that cut text. Tests
`test_a_layout_cut_short_at_the_boundary_height_is_not_a_fit` and
`test_the_writer_draws_the_whole_text_at_the_boundary_height` (both failed first).

**Finding 10 - a NUL character ends the drawn text.** Page 13's paragraph with inline math came out of
the PDF with NUL where its symbol font had no mapping; the layout stops at a NUL, silently. **Fix:**
control characters are removed before drawing - they have no drawable form. Test
`test_a_control_character_from_extraction_does_not_end_the_drawn_text` (failed first).

**Measured on the real pages** (the run's own translations redrawn from their projects, no model
call): L3 on 7 of 7 pages -> none.

## 2026-09-17 - held-out result: Wikipedia "Photosynthesis", and finding 11 (the new log's first catch)

Wikipedia "Photosynthesis" (33 pages, commit `ccf5348`, no repair): **L1 0, L2 5, L3 0, L6 1, L7 0,
L8 0, L9 0** over 359 blocks, D1 24, 24.6 minutes. Read one by one: one paragraph ("In 1893, the
American botanist...") came back in English through every retry - real, flagged; four L2 and the L6
are reference-list entries (the references question), one of which lost a page range and an
identifier in translation - real; and one paragraph ("Cyanobacteria possess carboxysomes...") was
never answered.

**Finding 11.** That last one is the first loss the unreadable-reply log explained: `reply unreadable
for 1 segment(s): a dict, not a list: '{"id": "p0#m0.2", "text": "..."}'` - asked for one segment,
the model answered with the item itself, a good translation, not a list of one, and the parser threw
it away. An existing test (`test_parse_reply_rejects_non_list_json`) had pinned exactly that
rejection. **Fix:** a single `{id, text}` item is read as a list of one; JSON that is neither a list
nor an item is still rejected, and the old test now checks that. Test
`test_a_single_item_reply_without_its_list_is_read` (failed first).

## 2026-09-17 - held-out result: NASA NTRS one-page scan, and finding 12

NASA NTRS 19750007530 (one image-only page, commit `e45ddb8`, no repair): **L1-L9 all 0 except L2 1**
over 13 blocks. The counts say little here: the OCR of this scan is poor ("The Naga Merorautigs
Frogrom is direcled" for a line about the NASA aeronautics program), and garbage in gave garbage out,
including a word that is not Turkish ("bidangolo"). No loss criterion measures recognition quality
against a transcription that does not exist. What the application did do: 13 of the 14 segments are
flagged for review (low OCR confidence, overflow), so the review queue shows the page as unreliable.

**Finding 12.** The log caught another thrown-away reply: `reply unreadable for 2 segment(s): Extra
data at character 392: '...afficicntly."}\n{"id": "img0#11", ...'` - asked for two segments, the model
wrote the two items one after the other, not inside a list. **Fix:** items written in sequence
(separated by whitespace or commas) are read as the list they should have been; the backslash repair
and this now share one decoding step (`_decode_reply`). Test
`test_items_written_one_per_line_instead_of_a_list_are_read` (failed first).

## 2026-09-17 - held-out result: IRS Publication 505; measurement stopped here

IRS Publication 505 (48 pages, commit `dd52021`, no repair): **L1 0, L2 2, L3 0, L6 8, L7 0, L8 2,
L9 0** over 2,144 blocks, D1 509, 71.6 minutes - the densest source so far (worksheets and tables,
65 blocks on one page). The unreadable-reply log recorded three more malformed-JSON shapes from the
model: a missing `:` delimiter, an unterminated string (a reply cut off), and items written in
sequence (the last is fixed in `9efc608`, which this document did not have).

**Stopped at the user's request** after this document, at 18:54. Not measured: the 1907 cookbook,
the 1895 mushroom book, the IRS Form 1040 instructions and the planned re-run of arXiv 2609.19145
with every fix. The Sherlock Holmes EPUB was stopped unfinished after about three hours of an
estimated 10-16 (581,282 characters through one sequential connection); the CLI keeps no partial
result, so the EPUB path has no measurement. The table in `docs/campaign/HELDOUT.md` holds every
source that finished.
