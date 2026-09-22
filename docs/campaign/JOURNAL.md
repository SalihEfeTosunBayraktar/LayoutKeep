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

## 2026-09-18 / 2026-09-19 - scaling to 7 parallel workers and arXiv 19145 v2 results

The translation system was scaled to match LM Studio's 7 parallel slots:
1. Added central `translation.workers` tunable in `src/layoutkeep/core/tunables.py` (default: 7, range: 1-32).
2. Updated `tools/audit/translate_book.py` and `tools/audit/translate_epub.py` to default to 7 workers, reading from `tunables`.
3. Updated repair and campaign runners (`tools/audit/repair_book.py`, `tools/audit/run_campaign.sh`, `_artifacts/heldout/run_heldout2.sh`) to use 7 workers.

**arXiv 2609.19145 v2 (post-fixes re-run):**
Completed 20 chunks (489 blocks) in 74.5 minutes:
- **L1**: 0 (zero lost pages, down from 1)
- **L2**: 7
- **L3**: 0
- **L4**: 0
- **L5**: 0
- **L6**: 3
- **L7**: 6
- **L8**: 6
- **L9**: 0
- **D1**: 299 review flags
Compared to the initial run at `bad981a` (L1 1), L1 is completely eliminated (0 lost pages).

## 2026-09-19 - held-out result: Sherlock Holmes EPUB completed with 7 parallel workers

Sherlock Holmes EPUB (*The Adventures of Sherlock Holmes*, 15 chapters, 628,529 characters, commit `e839938`):
Previously abandoned unfinished after 3+ hours under sequential execution with no measurement, it has now **fully completed and merged** into `gutenberg_sherlock.tr.epub` in **34.3 minutes** of parallel wall time (286.5 minutes of aggregate worker compute across 7 parallel workers).

**Loss Audit Results (2,624 blocks across 15 chapters):**
- **L1**: 0 (all 15 chapters translated and merged)
- **L2**: 1 (a single opening dialogue paragraph left untranslated)
- **L3**: 0
- **L4**: 0
- **L5**: 0
- **L6**: 1 (Project Gutenberg footer royalty fee percentage)
- **L7**: 0
- **L8**: 0
- **L9**: 0
- **Review flags**: 139 blocks (5.3%)

**Key EPUB Engineering Fixes Delivered:**
1. Chapter-aligned `.lkproj` chunking via `translate_epub.py` with multi-threaded execution.
2. Graceful pass-through for non-translatable chunks (frontmatter/cover plates with no text) to avoid false aborts.
3. UTF-8 standard console output/error reconfiguration preventing Windows `cp1254` Unicode crashes.
4. Resumable checkpointing (`--resume`) ensuring zero lost progress across interrupted runs.

## 2026-09-19 - held-out result: 1907 Cookbook completed with 7 parallel workers

1907 Cookbook (*The 1907 Cook Book*, 35 pages, 444 translatable blocks, commit `a0f1a21`):
Finished 35 chunks and merged into `cookbook_1907.tr.pdf` (35 pages) in **15.0 minutes** of parallel wall time.

**Loss Audit Results (444 blocks across 35 pages):**
- **L1**: 0 (all 35 pages present and merged)
- **L2**: 1 (one recipe ingredient measurement left untranslated)
- **L3**: 0
- **L4**: 0
- **L5**: 0
- **L6**: 1 (one number altered in translation)
- **L7**: 0
- **L8**: 0
- **L9**: 0
- **D1 (readability floor)**: 129 blocks
- **D3 (squeezed lines)**: 1 page

## 2026-09-19 - held-out result: 1895 Mushrooms sample completed with 7 parallel workers

1895 Mushrooms (*Our Edible Toadstools and Mushrooms*, 41 pages, 264 translatable blocks, commit `360fad5`):
Finished 41 chunks and merged into `mushrooms_1895_sample.tr.pdf` (41 pages) in **8.4 minutes** of parallel wall time.

**Loss Audit Results (264 blocks across 41 pages):**
- **L1**: 0 (all 41 pages present and merged)
- **L2**: 1 (one paragraph on Boletus preparation left untranslated)
- **L3**: 0
- **L4**: 0
- **L5**: 0
- **L6**: 0 (zero lost numbers)
- **L7**: 0
- **L8**: 0
- **L9**: 0
- **D1 (readability floor)**: 34 blocks
- **D2 (botanical names kept as-is)**: 11 blocks (e.g. *Agaricus campestris*, *Amanita muscaria*)
- **D3 (squeezed lines)**: 0

## 2026-09-19 - held-out result: IRS 1040 Instructions completed with 7 parallel workers

IRS Form 1040 Instructions (*2025 Form 1040 Instructions*, 32 pages, 737 translatable blocks, commit `2f0f94e`):
Finished 32 chunks and merged into `irs_i1040gi.tr.pdf` (32 pages) in **35.5 minutes** of parallel wall time.

**Loss Audit Results (737 blocks across 32 pages):**
- **L1**: 0 (all 32 pages present and merged)
- **L2**: 1 (one married filing jointly threshold line left untranslated)
- **L3**: 0
- **L4**: 0
- **L5**: 0
- **L6**: 6 (numbers altered in complex tax worksheets/tables)
- **L7**: 0
- **L8**: 3 (untouched text moved due to table column flow)
- **L9**: 0
- **D1 (readability floor)**: 209 blocks
- **D2 (short phrases/caution headings kept)**: 3 blocks
- **D3 (squeezed lines)**: 0

With this run, **every held-out source in the entire test suite has finished, been measured, and been audited**.

## 2026-09-19 - the L2 residue attacked from three sides; the V2 branch read and judged

Every held-out source ends with L2 above zero (one block on the cookbook, one on the mushroom book,
one on the Sherlock EPUB, seven on arXiv 2609.19145) while L1/L3/L4/L5/L9 are at zero practically
everywhere. So L2 is the single criterion standing between the pipeline and a lossless document,
and three mechanisms were added against it, each measured on the recorded runs (no model needed):

1. **A paragraph that survives the whole ladder is asked for in pieces** (`providers/split.py`,
   `retry.py`). The ladder already changed a failed request's company and context, never its size -
   and the size is what the echo experiments point at (a Time Machine paragraph echoed twice yet
   translated 24 times out of 24 alone). The block is cut at its sentence and list boundaries, each
   piece is asked for alone, and the replies are put back in the source's own whitespace. Any piece
   that comes back unusable fails the whole attempt: a half-translated paragraph is worse than an
   untranslated one, because it no longer reads as a loss. Tunable
   `translation.piecewise_max_pieces` (default 12, 0 disables).

2. **The number check stopped reporting losses that are not losses** (`core/copies.py`): number
   words are folded to their value ("on iki" -> 12, "iki bin beş yüz" -> 2500), ordinals count
   ("üçüncü" -> 3), and a vulgar fraction is expanded ("½" -> 1 and 2). Measured over the 11
   recorded held-out projects: **1 of the 29 recorded L6 findings was of this kind** (IRS 505's
   "tier 1 railroad benefits" -> "birinci kademe"). The other 28 are real: a source PDF gluing its
   own footnote digit onto a number ("20261"), repeats compressed into one mention ("1099" three
   times in the source, twice in the reply), and values genuinely dropped. L6 is mostly a content
   finding, not a checker artifact.

3. **Code and mathematics are recognised by shape, not only by face** (`readers/_nonprose.py`).
   The reader caught code only in a monospaced face, so a LaTeX paper's verbatim line
   (`trim_offsets=True, use_regex=True)`) and its equations set in the body font went to the model
   as prose, came back as their own source, and were counted as L2 - and the ladder then spent
   three lone requests plus a request per piece on text no model can translate. Both are now
   carried through as `CODE` / `FORMULA`. Measured: **2 of the 34 recorded L2 findings are these
   lines**; a scan of the real corpus (arxiv_19145 115 blocks, Think Python 49, NIST 51, Popular
   Science 147, Time Machine 16, Electricity 16) claimed 13 blocks, every one read by eye, all
   genuine (Python session output, comparison operators, equation fragments, the arXiv stamp) and
   **zero prose**. The first version of the rule did misclassify ("Now, define f(a) = a log a,
   which implies ..." - a single letter in parentheses is how a paper writes a function of x, not
   code); the probe found it and the rule now demands a three-letter call name and refuses any text
   carrying ten or more real words.

Not touched, and why: **L7** (6 pages on arXiv), **L8** (untouched text moved: 4-111 runs on
arXiv) and **D1** (296-509 blocks below the readability floor) all live in the writer's clearing
and the fitting pass, where a change made without measuring L3/L4 back would trade one loss for a
bigger one. The V2 branch's elastic flow is the right idea for D1 and is not portable as written:
it moves `bbox.height` without the `fitting/room.py` measurement or the writer's clearing rules
that depend on it. See `docs/KAYIPSIZ_MOD_DURUM.md` for the branch-by-branch judgement.

No end-to-end run: LM Studio was not serving on 127.0.0.1:1234 during this work, so nothing here is
a claim about output produced by a model - the measurements are over the runs already recorded.

## 2026-09-19 - smoothness: a form that repeats itself now reads the same on every page

The criteria in sections L1-L9 ask whether anything was lost. They do not ask whether the document
reads as one document, and the recorded runs say it did not: irs_p505 repeats 537 of its 2,144
translatable segments (25%; irs_i1040gi 34%, arXiv 2609.19145 31%, plos 30%) - form labels, the
same instruction on every page, repeated table headings - and **80 of those repeated texts came
back with more than one translation** (272 segments). IRS Form 1040's instructions word "Married
filing separately" three ways in one document ("ayrı ayrı beyan eden", "evli ayrı ayrı beyan eden",
"ayrı ayrı evli") and "Head of household" two ("hane başkanı", "hanevi"), each row correct alone.
A quarter of the requests were also spent asking for text the document had already had translated.

Two mechanisms, both on by default:

1. **The same text is translated once** (`providers/dedupe.py`), inside the literal-protection
   wrapper so the shared text is the tokenised text: "Tighten the bolts to 63 Nm" and "...to 150 Nm"
   are one request and each restores its own value. The key ignores whitespace and case, and refuses
   sources under three words - "where" came back as "nerede" and as "ner", "ours" as "biz" and as
   "bizim", and sharing those would spread one sense across a document to save nothing.
   Measured saving on the recorded sources: plos 86 of 468 requests (18%), irs_i1040gi 115 of 737
   (16%), irs_p505 224 of 2,144 (10%), arXiv v2 36 of 489 (7%), nothing on the prose-only sources.
   `--no-repeats`, or `translation.reuse_repeats` off, restores the old behaviour.

2. **What is already written is made to agree with itself** (`core/repeats.py`), after the retry
   ladder and before the fitting pass: a repeated source text with more than one translation keeps
   the majority wording and the minority is rewritten to it. Nothing is re-asked and nothing is
   invented - every rewrite is a translation this document already produced for that exact source -
   and a variant that lost one of the source's numbers is never chosen over one that kept them
   (consistency must not be bought with a lost value). Measured on the recordings as they stand
   (produced with no sharing at all, so this is the upper bound): irs_p505 66 texts disagreeing
   over 87 segments, irs_i1040gi 16/42, arXiv v2 8/22, cookbook_1907 4/4.

Both keep the CLI and the desktop worker on the same code path; the run report says what was shared
(`shared 224 repeated segment(s) answered from their first occurrence instead of being sent again`)
and what was made to agree (`repeats N segment(s) reworded ...`).

Tests: `tests/test_provider_dedupe.py` (14) - shared text asked once and answered everywhere, one
segment out per segment in with its own block id and context, the three-word floor, off-switches,
and the sweep's choice of majority, of numbers over consistency, and of the first occurrence on a
tie. Full suite after the change: 1,075 passed, 1 failed - `test_every_advanced_entry_says_what_breaks`
caught the new tunable's missing consequence warning, which is now written.

## 2026-09-19 - a real model on the line: what the app does on real documents, and the fitting fix it forced

**Setup.** LM Studio keeps its models on `T:\AiModels` and the drive was not mounted: `lms ls`
listed one embedding model, `lms load google/gemma-4-e4b` answered "Model not found", the HTTP API
"No models loaded". Mounting the drive was not enough - the index is built at app start - so
`lms import -L --user-repo local/gemma-4-e4b <the GGUF already on T:>` hard-linked the file where
the scanner looks, and the model returned as `gemma-4-e4b`. Loaded with
`--identifier google/gemma-4-e4b --gpu max -c 8192 --parallel 7`, so the application's own default
model id works and the campaign's 7-worker setting matches the server's slots.

**Runs** (`tools/audit/live_check.py`, added for this: one source through the real pipeline, audited
against the recorded run of the same source):

| source | before | after |
|---|---|---|
| 2-page fixture, repeated text | `fitting 6 blocks: shrunk=2 overflow=4`, 4 flagged | `as_is=6`, nothing flagged, `no losses found` |
| arXiv 2507.03009 p5 (new, born-digital table page) | `fitting 70 blocks: shrunk=42 overflow=28` | `as_is=32 shrunk=12 retranslated=1 expanded=1 overflow=24`, **LOSSLESS**, L7 0, L8 0 |
| arXiv 2507.03009 p7 (author list) | `3 blocks: overflow=3` | `as_is=1 overflow=2` |
| NASA NTRS scan p1 (held-out) | L2 1, D1 6 | L2 1, D1 5, L1-L9 otherwise 0 - unchanged |

The table page is the finding. **Not one of its 70 blocks fitted as it was**, and the audit of the
same output said "no losses found": the criteria ask whether anything was *lost*, never whether the
page looks right, and a page of text shrunk to the readability floor loses nothing and still reads
badly. On the scan the 10 of 14 segments recovered by the retry ladder are the model echoing a page
of OCR noise, and the ladder is what keeps that page's L2 at 1 rather than 10.

**The fix** (`fitting/growth.py`, tunable `write.grant_room_pt`, default 24 pt): a block the
pipeline translated may grow downward into the room the page really has under it - bounded by the
next block in its column, stopped by any picture, capped by the tunable and keeping 2 pt of the gap.
`fitting.room.room_below` could not serve this: it answers "how much of the writer's 3 pt slack is
free" and by construction never returns more than that slack, so it can never say "the page has
room". The fitting pass and the writer both call the new function - if they disagree the text is
measured in one box and drawn in another, which is the reason `fitting/room.py` exists at all. A
block kept as it was is still drawn in its own box (its text must not move: L8), and a rotated block
is measured as before (its `TextWriter` path has no such room).

**Still rough, honestly.** 24 of the 70 table-page blocks overflow and 22 of its 33 checked blocks
sit below the readability floor: a table cell has no room under it by construction, and the ladder
can only shrink to the floor, ask for a shorter rendering, then flag. On a scan the grant is inert
by design - the page image is the obstacle that stops it, and `image_reader._grant_blank_paper`
(from the pixels) is its counterpart. Author lists and commit-message lines are still sent for
translation and then have to fit.

Tests: `tests/test_fitting_growth.py` (6, including the decision itself: the same render overflows
in the tight box and fits once the room is granted); the 56 fitting/writer/verify tests stay green.

### 2026-09-19 - the grant does not reach a running header (found by the full suite)

The first version of the room grant applied to every translated block, and the full suite failed on
`tests/test_pdf_writer.py::test_page_number_and_header_survive_untouched`: the running header's
translation ("XX Running Header Text") wrapped onto two lines instead of being shrunk, because the
grant reached it too. Wrapping a header changes the shape of the page, which is what the reader is
told not to do - so a block whose role is a single-line design element (`heading`, `title`,
`header`, `footer`, `page_number`) keeps its one-line box, in both the fitting pass and the writer,
on the same shared rule (`fitting/growth.may_grow`). 1,096 tests green after it.

## 2026-09-19 - why the overlap guard works, the shrink guard is half-off, and what was fixed

**Question asked:** are the protections against overlap (shorter sentences, smaller type) actually
working? Measured on arXiv 2507.03009 with gemma-4-e4b, 7 workers, and on the recorded projects.

**They are, and the page still reads badly - the two facts have different causes.**

1. **Overlap protection works.** 148 blocks, **L7 0** and **L4 0**: nothing drawn over anything, and
   nothing off the page. `fitting.room` + the writer's clearing rules + the one-line rule for
   headings are doing their job. The 10-page run's whole loss list is L2 2, L8 1, L9 1 - and the
   two L2s are author lists ("Tom Brown, Benjamin Mann, ..." came back unchanged) that the model
   was right to leave alone.

2. **The shrink guard is working against itself.** `fit.min_scale = 0.85` is the floor, and D1
   counts blocks that reached it: 63 of them. But 42 of the page-5 blocks "fitted" at a scale
   between 0.878 and 0.997 - they were shrunk, the measurement said "fits", and **the engine stopped
   there**: the shorter-rendering ladder is only reachable from OVERFLOW. So the blocks that most
   needed fewer words (23 prose blocks of 9.4pt in a 220pt column, 517 to 1138 characters) were
   never asked. A block shrunk to 0.88 is not a loss, so nothing flagged it either: 63 D1 blocks
   and only some of them carry a review reason.

3. **The ladder that does exist was spending its rounds on the wrong blocks.** Replaying the fitting
   pass over page 5 with a model that refuses everything (the worst case) recorded 14 requests, and
   they were: `'IMT5'` asked for 12 characters, `'Doc2X'` for 10, `'Ücretsiz'` for 4, `'Ücretli'` for
   4, `'✓'` for 2. Targets no reply can meet, three rounds each, and each round is a chance to
   replace a correct short translation with a worse one.

**Fixes (`fitting/fit.py`, tunable `fit.shorten_below_scale` = 0.95):**

* A fit held only by shrinking below the threshold now asks for a rendering that fits at full size
  (`_try_shorten`, two attempts, not three - the block is already readable, so the prize is smaller
  and the request cost is not). It accepts a candidate only if it fits at a *better* scale than the
  current one, and only if it does not lose a number the source has - the same rule the overflow
  direction already applied. The correct translation is never replaced by a worse one: when nothing
  better comes back, the shrunk fit is kept unchanged.
* A text under 24 characters is never asked to compress (`'Ücretli'` -> 4 was the measured waste),
  and the overflow budget is now clamped by the proof in hand - the text does not fit at
  `min_scale`, so the target is always strictly below it, never the box's optimistic estimate.

**Measured after:** the same dry replay of page 5 makes **7 requests instead of 14**, and the
oversized ones are gone: the shortest text asked to compress is 51 characters. The table cells that
used to absorb three pointless rounds each are now simply flagged, which is what they always were -
table cells with no room under them.

Tests: `test_fitting_fit.py` gained six (a hard shrink asks for a shorter rendering; a candidate
that does not fit better is refused; a 1% shrink is left alone; the ladder can be turned off; a
candidate that drops a number is refused; a candidate that is the source is refused) plus one for
the short-text floor. 37 fitting tests green, ruff clean.

### 2026-09-19 (devam) - the L7 the shrink fix turned up, and what it really was

The first real run with the shrink ladder (`fresh_pdfmt_r3`, 758s) came back L7=1 - a word pair
drawn over another, on chunk_0001, a page that had none before. Chased it to the source page:

    pymupdf block 30, bbox (306,755,526,775), three lines
        (319,755,338,765)   '1See:'          <- a footnote, our reader splits it out as its own block
        (388,756,526,765)   'https://platform.openai.com/docs/api-'
        (306,766,381,775)   'reference/chat/create'

Three separate faults, each found by measurement, each fixed:

1. `join_hyphenation` ate a hyphen that belongs to a link. The row ends `api-`, the next begins
   `reference` - a letter before the hyphen and a lowercase letter after it, which is all the rule
   asked. Joined, the URL became `.../docs/apireference/chat/create`, and the block's one line
   was 2.4x the width of either source row. Guards: the token ending in the hyphen must be a word
   (letters only), and the next row must continue the same column (overlap it, start at or left of
   its left edge). A footer's two rows need not overlap at all.

2. `_unchanged` read a block with no `source_text` as *changed*. The pipeline only records
   `source_text` when a segment comes back translated (`apply_segments`), so an empty one means
   the text is still the source: the batch failed, or the block was never sent. Such blocks were
   redrawn in a substitute face for nothing - and a redrawn block is laid out from its own box's
   left edge, which put the URL's first row 82pt left of where the source set it, over the
   footnote. Now they are kept, like any other unchanged block.

3. `_clearing_reaches`: the "would this redaction eat that block" test used union boxes. The URL
   block's box is the union of its two rows and covers the footnote's box, so the block was
   pulled in and redrawn even though the footnote's clearing touches neither row. The test now
   asks the kept block's own lines, with a 1pt margin (a redaction takes whole glyphs, and a glyph
   box can stick out of its line's), and touching edges are not a reach.

Also tried and reverted: `white-space: nowrap` for blocks with no words, on the theory that
`insert_htmlbox` was scaling the URL's type up to fill its box. A probe (`tools/audit/url_size_probe.py`)
showed the 11.9pt height was the substitute face's own ascent+descent (1.31em at 9.06pt), and that
nowrap changes nothing - a token wider than its box draws nothing either way. Unproven fixes do
not stay in.

`tools/audit/rewrite_run.py` re-writes a recorded run's pages from its projects with the current
writer and audits the result - no model needed, so a writer change can be measured in minutes.
On the recorded `fresh_pdfmt_shorten` run: L7 1 -> 0. Its remaining D3=1 and L8=1 are artifacts of
that run's saved projects (written by the older reader, the URL block still holds the merged
one-line text); a fresh run is what settles those.

### 2026-09-19 (devam) - the reader's own mistakes, found by an A/B of the reader alone

`tools/audit/reader_ab.py` reads every held-out source with two source trees (`git worktree` of
HEAD vs the working tree) and prints the lines that differ. It is the only honest way to judge a
reader change: a translated project collapses each block to one line, so comparing against saved
projects says nothing.

Two more faults, both on the same footer, both now fixed:

1. **A refused hyphen join left the line to be grouped with the wrong neighbour.** The URL's
   second row (`reference/chat/create`) overlaps the footnote's column, so
   `_split_side_by_side_lines` grouped it with the footnote and the pair was translated as
   `1See: reference/chat/create` (a block that then overflowed, D1). A line under a line ending in
   a hyphen, beginning lowercase, belongs to *that* line - `_hyphen_parents`, and lines are now
   read in text order rather than by column, so the parent is always seen first.

2. **The column guard was too strict, and split a name.** `_continues_the_column` required the two
   boxes to overlap; a paragraph's last line is short, so `(Von Gizy-` at the right of a column
   followed by `cki; Montgomery).` at the margin shares no width with it and the join was refused.

The A/B then reads, over 43 held-out chunks: 21 chunks differ only in block *ids* (internal), and
**2 pages differ in content, both in the right direction**:

| page | before | after |
|---|---|---|
| chunk_0001 (arXiv footer) | `https://platform.openai.com/docs/apireference/chat/create` - one line, hyphen eaten, 2.4x too wide | `https://platform.openai.com/docs/api-` + `reference/chat/create` - the source's own two rows, hyphen intact |
| chunk_0005 (arXiv p1) | `Exclusion of the non-Englishspeaking` - hyphen eaten | `Exclusion of the non-English-` + `speaking world from ...` - the source's own rows |

### 2026-09-19 - branch survey: what is where, and why nothing gets merged

Asked to tidy the branch structure. What the refs actually say:

    feature/lossless-campaign-continuation   77f77bb   <- everything is here
    layout-model                             7ef33ea   ancestor (17 commits behind)
    scanned-pdf-ocr                          298e04f   ancestor (50 behind)
    main / origin/* (6 branches)             f58f0eb   ancestor (77 behind)
    v2-vision-layout (fetched from the V2 clone) b89396b  1 commit, NOT an ancestor

Every branch of this repository - local and remote - is already contained in the feature branch, so
there is nothing to merge from any of them. The one branch with unique work is Gemini's
`v2-vision-layout`, which lives in the separate `LayoutKeep_V2` clone (its own `.git`); it is now
fetched into this repository as a local branch so the work cannot be lost with that folder.

Merging it is **not** conflict-free: `git merge-tree --write-tree` reports six conflicts, because
this branch already carries its own, campaign-hardened implementation of the same ideas -
`fitting/elastic_flow.py` and `readers/_segment.py` are add/add (both sides wrote them),
`readers/pdf_reader.py`, `readers/image_reader.py`, `fitting/pdf_pass.py` and one test file
conflict on content. Two files exist only on that branch: `readers/vision_layout.py` (a VLM layout
detector wired to no model) and `readers/glyph_fusion.py`.

Housekeeping done: three detached worktrees left inside `_artifacts/heldout/` (`code`,
`code_epub`, `audit_bad981a`, ~60 MB each, clean, all at commits this branch already contains)
were removed with `git worktree remove`. The V2 clone also holds 10 untracked sample files under
`docs/`; they stay where they are.

## 2026-09-20 — gece: kullanıcının üç şikâyeti ve ölçümleri

**1) "Bariz daha büyük font"** — ölçüm bunu çürüttü: `tools/audit/type_drift.py` (yeni) kayıtlı
koşularda büyümüş blok bulamadı (irs 0, cookbook 0, arxiv 0, wikipedia 4). İlk ölçümüm "12pt'ye
büyümüş" diyordu; eşleştirme hatasıydı — karşılaştırdığı kaynak satır 10pt'lik başka bir satırdı,
bloğun kendi stili 12pt'ydi (kaynakla aynı). Probe artık bloğun kendi kaydıyla karşılaştırıyor.

**2) Kırılan (okunamaz) satırlar** — gerçek sorun buymuş: 29 blok 5pt'nin altına inmiş.
Kök neden: `room_below` birkaç punto negatif çıkınca yazar kutuyu kısaltıyor, 6.7pt'lik bir dizin
satırı 4.5pt'ye düşüyordu. Çözüm: yazar, taban ölçeği tutmadığında bloğun **kendi kutusunu** da
deniyor. Aynı koşu (`rewrite_run` ile, model yok) önce/sonra: okunamaz 12 → 2, küçültülmüş 84 → 6,
hizası değişmiş 4 → 0; bedeli bir sayfada sıkışan satır (D3 1 → 2). Denenip geri alınan hipotez:
kutuyu sağdaki boşluğa genişletmek (12 → 12, etkisiz; kısıt genişlik değil yükseklikti).

**3) "Sayı/başlık hizalamaları kaybolmuş"** — `type_drift` 14 hiza değişikliği buldu (IRS formu).
Tek tek bakıldığında bunlar tablonun **dikey sayı şeritleri**: kaynakta her sayı kendi satırında,
8pt genişliğinde, 56 satırlık bir blok. Yazıcı da her sayıyı kendi satırına koyuyor, yani görsel
sonuç aynı; flag probe'un hiza çıkarımından geliyor. Görünür bir bozulma bulunmadı ve **kanıtsız
düzeltme yazılmadı** - kayıt burada duruyor.

**4) Sözlük ve bellek** — araştırma sırasında ikisinin de yalnız komut satırında olduğu çıktı
(`--glossary` arayüzde yok, `memory_path` boş). Aynı gece arayüze bağlandı (Gelişmiş Ayarlar),
sözlük parmak izi bellek anahtarına katıldı. `docs/FEATURE-ROADMAP.md` bu yanlış iddiayı düzeltti.

**5) Telif** — sitede telifli ders kitabının (Ross) sayfa görüntüleri yayındaydı; üreticiye
`NOT_PUBLISHABLE` listesi eklendi, site yeniden üretildi, düzeltme `main`e push edildi.

**6) 220 sayfalık kitap** — 55/55, 106 dakika, `ross_stats.tr.pdf`. Denetim: L1=1, L2=2, L6=4,
L7=1, L8=1, L10=1; D1=801, D2=163. Koşu bugünkü son düzeltmelerden önceki kodla yapıldı (L7/L10=1
o sınıftan). Sitede yayınlanmıyor (telif).

## 2026-09-20 — gece 2: L10'un yarısı ölçüm hatasıymış

**Yeniden çevirim bitti** (5 belge, ~2 saat): printing_press 19 parça, photosynthesis 33,
arxiv_19145 20, mushrooms 41, cookbook 35. Ardından L10 taraması tuhaf bir tablo verdi:
Wikipedia'nın ikisi 13 → 0 (düzeldi) ama arxiv 25 → 26, mushrooms 124 → 128, cookbook 182 → 126
(nedeyse hiç değişmedi).

**Kök neden: aracın kendisi.** İki ayrı yanlış-pozitif sınıfı vardı:

1. **Taranmış sayfalar.** Cookbook'un sayfalarında görsel *döşemeli*: iki tam-sayfa katman + basılı
   satırların üzerinde bir düzine yama; hiçbiri tek başına sayfanın %6'sından büyük. Araç her
   görseli ayrı değerlendirdiği için "tarama" sayılmıyordu ve sayfadaki **her kelime** görselin
   üstünde görünüyordu (126 kelime). Ölçüm: sayfadaki görsellerin **birleşimi** %100 → kural artık
   birleşime bakıyor (`union_area`, x-şeritli tarama). cookbook 126 → **0**, mushrooms 128 → **0**,
   kitap 6 → **0**.
2. **Grafiğin kendi etiketleri.** arXiv sayfasındaki 26 kelime, kaynağın kendi çubuk grafiğinin
   değerleri ve kategori adları; kaynak sayfa 28 tanesini sayıyor. Bunlar bizim kaybımız değil,
   grafiğin *içeriği*. Araç artık kaynağın o görsel üzerinde zaten yazdığı kelimeleri çıkarıp
   **net** sayıyı bildiriyor: arxiv 26 → **0**.

**Aynı iki kural çekirdeğe de girdi** (`verify.words_over_figures`): NIST dergisi koşusunda L10
8 sayfa diyordu, düzeltmeden sonra **0**.

**Gerçek kalan:** Wikipedia'nın iki sayfası — kaynakta fotoğrafın çevresinden akan satırlar,
çeviride fotoğrafın üstüne biniyordu; `fitting/figures.py` düzeltmesiyle yeniden çevirimde
**13 → 0**. Yani "L10 düzeldi" iddiası yalnız bu iki sayfa için doğruydu ve öyle kalıyor.

**Yeni kaynaklar (NIST, kamu malı):** `nist_jres_v98n1` (8 parça, 158 blok) L2=1, L6=1, D1=54 —
ikisi de inceleme kuyruğunda; L7=L10=0. `nist_ir6643_vapor_pressure` (6 parça, 29 blok, tarama)
L2–L10 = **0**, D1 = 0. L1 yalnız "--chunks" kısmi koşu olduğu için 1 (denetim artık
"(partial run)" diye işaretliyor).

## 2026-09-20 — gece 3: reflow modunun ölçümü (varsayılan değişmedi)

`--fit-mode reflow` şimdiye kadar yalnız bir bayraktı ve **arayüz onu hiç kullanmıyordu** (sabit
STRICT). Ölçtüm, çünkü D1'in ("çeviri kutuya sığmadı") tamamı bu modun çözmeyi vaat ettiği sınıf:

| koşu | parça | D1 strict | D1 reflow | L kaybı |
|---|---|---|---|---|
| NIST dergisi | 4 (114 blok) | 52 | **0** | L1-L10 aynı |
| IRS formu | 4 (69/101 blok) | 15 | **0** | **L7 0 -> 1** (aşağı itilen blok hareketsiz metne bindi) |

Sonuç: reflow "sığmadı" bayraklarını tamamen kaldırıyor ama akışkan olmayan formlarda gerçek kayıp
üretebiliyor. **Varsayılan strict kaldı**; mod artık `fitting.reflow` ayarı (Gelişmiş Ayarlar'da iki
ölçümü yazan uyarısıyla) ve hem CLI hem arayüz aynı ayarı okuyor — eskiden ikisi ayrı davranıyordu.

## 2026-09-20 — gece 4: taranmış belgede OCR gürültüsü nasıl görünüyor

`nasa_ntrs_scan_r2` (1 sayfa, kamu malı NASA taraması) L2=1 ile bitti ve tek tek bakıldığında
sebep çeviri değil **tarama**: sayfanın metin katmanı yok (`''`), OCR dekoratif başlığı
"Naga Merorautigs Frogrom Amerika" diye okumuş, çeviri de okunanı taşımış. Aynı bloklar zaten
işaretli: "OCR güveni düşük (0.62)" ve "çeviri kutuya sığmadı". Yani bu, sessiz bir kayıp değil -
tarama kalitesinin doğrudan sonuca yansıdığı, kullanıcıya söylenen bir vaka.

Bu, "kaliteyi ne belirler" maddesinin (kullanıcının 6. ek kriteri) ölçülmüş örneği: belge türü
(tarama), görsel kalite ve süslü tipografi → OCR güveni → inceleme bayrağı.

## 2026-09-20 — gece 5: "kırılan satır" düzeltmesi geri alındı

Gece 1'de yazıcıya eklenen "bloğun kendi kutusunu dene" değişikliği cookbook'ta ölçülebilir bir
kazanç veriyordu (okunamaz 12 → 2). Bedeli ölçülmemişti: IRS formunun tam koşulunda L7=11 çıktı ve
aynı kayıtlı çeviriler üzerinde iki sürüm karşılaştırıldığında sebebin bu değişiklik olduğu
doğrulandı (korumasız L7=10, korumalı L7=0 - ama korumalı sürüm cookbook'ta kazancı da sıfırlıyor:
12 → 12). İkisi de kalmadı, değişiklik tamamen geri alındı. Kural: kazancı ölçmek yetmez, bedelini
de ölç.

## 2026-09-20 - the audit sweep, and what L3 actually means

Ran every held-out run through `tools/audit/sweep_runs.py` (new: three tools per run, one table).
The outlier was `plos_animal_movement` with **L3 = 8** - "dropped by the writer", the worst kind
of finding, so it got the full treatment:

- The flagged block was in the writer's "to draw" list, had one line of 79pt, and its box on the
  page holds only its first 13 words: the paragraph is a page of **math**, the reader merged it
  into a single line, nothing can fit that box, and `insert_htmlbox` clipped the rest. The block
  is flagged for review (not silent) - the policy holds - but the audit's *label* was wrong:
  nothing was dropped by the writer.
- The label is now "text not on the page", which covers both causes, and the Turkish string says
  the same in full.
- The remaining sweep rows are the known classes: `hizası değişmiş` on runs made before the
  justify fix, `L2` on bibliographies, `L6` on table numbers. Three runs are clean: `wpa_poster`,
  `arxiv_2510_03959`, `arxiv_2605_18014`.

## 2026-09-20 - the leading step, and what the overflow blocks actually need

The largest review-flag class on the book is "the translation did not fit, shrinking was not
enough" (1,130 of 6,014 blocks in the first 42 chunks; D1=1,130). The roadmap's next lever is the
ladder, so the ladder got a new leading step: when the box does not fit even at the readability
floor, try tighter leading (1.0x, then 0.92x) *before* asking the model for a shorter text. It
costs no model round-trip, keeps the type at or above the floor, and never touches the words.

Measured with `tools/audit/fit_probe.py` (new instrument: re-runs the fitting pass over a recorded
run's saved translations - `rewrite_run.py` re-runs the writer and cannot see a fitting change):

| run | overflow blocks | rescued by 1.0x leading | need more than 0.65x |
|---|---|---|---|
| ross_stats_full (20 chunks) | 158 | 20 (13%) | 138 |
| cookbook_1907 | 29 | 0 | 29 |
| arxiv_19145 | 47 | 0 | - |
| irs_p505 | 61 | 0 | - |

**That table was wrong, and the correction is the point.** The "20 rescued" number came from
measuring with `block.dominant_style()` while the fitting pass measures with `_as_drawn(...)` -
the style with the target language's substitute font already resolved. The two fonts have
different metrics, and with the pass's own font **no block is rescued**: instrumented over six
chunks, `_try_tighten` was called 14 times and fitted 0, and the written-page A/B (`fit_ab.py`,
20 chunks) came back identical in both arms - D1=627, D3=0, every L the same. A step that changes
nothing is dead weight, so it came back out (the attempt is commit `bbf5958` on the unmerged
branch `fit-tighten`); the two
instruments stayed. Lesson for the next measurement: **use the pass's own style, not the block's**,
or the probe answers a question the engine never asks.

The measurement also answers the bigger question. The 138 blocks that no leading rescues are not
short of lines, they are short of **box**: `room_below` can shorten a block's measured box to 6pt
to keep it off the next block, and nothing fits in 6pt. Their fix is the box (the reflow/room
work), not the ladder - which is why the next lever is roadmap item 4, and why this step was left
where it does no harm.

## 2026-09-20 - L3, L6 and D1 are the same problem wearing three names

Checked the book's L6 findings ("numbers lost", 43 of them, the largest L class) block by block:
`drops_numbers(source, target, "tr")` returns False for the examples - the numbers are all in the
translation. The audit's L6 comes from the *written page*, so what it is really reporting is the
same thing L3 reports: a block that did not fit, drawn clipped, with its tail - often the number -
not on the page. The TOC line ("Problems .... 468") and "Table 2.8 gives the birth rates ... in
each of the 50 states" both survive translation intact and both are flagged.

So the three biggest numbers on this run - D1=1,130 flagged blocks, L3=1, L6=43 - have one cause
and one lever: the box. That is roadmap item 4 (reflow/room), not the ladder (measured and
reverted above), and not the model. Worth knowing before spending another evening on prompts.

## 2026-09-20 (evening) - the story in three languages, and the day's numbers

The user asked why the story was Turkish only; it now publishes in tr/en/de with a switcher on every
page (`tools/story_site.py`). Turkish stays the original in `docs/story/`; English and German live in
their own directories with the same file names; a chapter without a translation falls back to the
closest language that has one, behind a visible note. All sixteen chapters were written by hand
(Turkish original, English set, German set) - no model was spent on them.

The same evening, the day's measurements, for the record:

- **The book finished**: 106/106 chunks, the full audit **L1=0, L2=48, L3=1, L4=0, L5=0, L6=120,
  L7=2, L8=3, L9=5, L10=0, D1=2,155, D2=273, D3=39** over 12,647 blocks; all 106 chunks were joined
  into **one local PDF of the whole book, 841 pages** (72 MB, copyrighted, never published).
- **A new held-out source ran**: Project Gutenberg #31061 (Cajori, A History of Mathematics, 556
  pages, public domain) - 6 chunks, 24 pages, 11.4 minutes; **every real loss zero: L2-L10 = 0**
  (L1=1 only because the run is a 24-page slice of a 556-page book), D1=31 of 185 blocks. It is now
  on the comparison site, which went from 24 documents/288 images to **25/304**.
- **The instruments that stayed**: `fit_probe.py` and `fit_ab.py` (both model-free), the L3 label
  correction, and the review-reason split that reached the completion screen in 0.9.7.
- Releases today: **v0.9.1 through v0.9.7**, each verified by downloading the asset and comparing its
  SHA-256 with the local build.

## 2026-09-20, evening — the other direction (TR -> EN)

Every run so far had gone English -> Turkish. The user asked for the reverse: five Turkish documents
of at least 60 pages, translated to English, plus the opposite direction tried as well.

The Turkish side needed sources first, and the usual one was closed: **mevzuat.gov.tr does not answer
from this machine at all** (curl times out with no response, not even a 4xx). The Ministry of Family
and Social Services mirrors the same law texts and answers fine, so the set came together from two
hosts that work:

| document | pages | direction | licence |
|---|---|---|---|
| Türk Ceza Kanunu (5237) | 88 | tr -> en | law, no copyright (FSEK art. 31) |
| Ceza Muhakemesi Kanunu (5271) | 91 | tr -> en | law, no copyright |
| Türk Medeni Kanunu (4721) | 162 | tr -> en | law, no copyright |
| On İkinci Kalkınma Planı (2024-2028) | 253 | tr -> en | state publication |
| On Birinci Kalkınma Planı (2019-2023) | 198 | tr -> en | state publication |
| Twelfth Development Plan (English edition) | 263 | **en -> tr** | state publication |

All six are publishable (no third-party rights), so unlike the Ross book they can go on the
comparison site once they have run.

`tools/run_tr_en_campaign.bat` runs them smallest-first, detached, logging to
`%LOCALAPPDATA%\Temp\lk_tr_campaign.txt`. It opens with a **two-chunk smoke run of the new
direction** and aborts the whole campaign if that fails — a direction that has never been exercised
should not be trusted with six hours of model time. It passed: 8 pages in 5.4 minutes, `smoke exit=0`,
and the main run's first two chunks then finished in 21 and 22 seconds because the translation memory
already held those pages.

Measured rate: ~1 minute per page (4-page chunks, 7 workers) — the same rate the Ross book ran at.
So the full set is a night's work: the three laws land first, the reverse direction in the middle,
the two plans after that. Every step is `--resume`-safe; relaunching the same file picks up at the
first chunk that has no `.lkproj` yet.

## The type-drift readings, checked against the page

`type_drift.py` reported inflated blocks on the NIST scan (chart labels at 1.23-1.50x) and two
alignment changes on the Turkish law run. Rendering those pages and *looking* at them settled it:
the charts are scaled as a unit and come out slightly **smaller** than the source, the caption that
the tool called centred is **justified exactly like the original** (confirmed at 300 dpi on a crop,
after the same crop at reading size had suggested otherwise), and the body type matches. The law
pages the tool flagged as right-aligned are left-aligned to the eye.

The reason is the instrument's own shape: it compares a block-level median against that block's
*dominant* style, and on a scan the OCR boxes put chart labels, body text and captions into blocks
whose dominant style is not the style of every line inside them — a mixed-size block reports drift
nobody can see. The alignment check has the same weakness, and its docstring already records two
earlier rounds of false positives on an IRS form and an arXiv paper. Lesson for the next session:
**before fixing what this tool reports, render the page and look at it.** The tool is a detector,
not a verdict.

The two readings that do survive a look are real and already known: the fit ladder squeezing dense
translations toward the readability floor (D1), and single-line headings in narrow boxes. Both are
the box/room problem, not a type-size bug.

## The tidy pass

The owner asked for the repository to be cleaned of clutter. The inventory found three things
worth more than tidiness:

- **`arxiv_2605.18014v1.pdf` was tracked, in the repository root, at 10.4 MB** — the largest file
  the repository carried, and an arXiv paper whose licence never allowed redistribution. It is now
  under `_artifacts/heldout/sources/` and out of git, and `/*.pdf` is ignored so a source can never
  land in the root again.
- **The NASA page images were still 6997x3163 and 2.5 MB each** — the cap the comparison site's own
  notes describe (3200 px, quality 76) had been applied to the *generator's defaults* but never to
  the files themselves. Re-encoded: **9 MB -> 1 MB** across the four, still sharp at zoom.
- **`tools/comparison_page.html` was dead** — a 16 KB hand-made page from before
  `comparison_site.py` existed, referenced by nothing. Removed. `docs/comparison.html` stays: it is
  a redirect with a canonical link, so addresses shared before the viewer moved still land on the
  current site — and the GitHub About link now points at the landing page, which opens the story,
  the viewer and the releases.

## Branch cleanup

The owner asked for the other branches to be either merged into main or removed. The remote was
already clean - after `git fetch --prune`, GitHub holds only `main`, the feature branch and three
dependabot branches - and the work of the removed ones is provably in the feature branch
(`tests/fixtures/rich_book.epub` and `src/layoutkeep/fitting/elastic_flow.py` both exist there, and
two of the local branches were ancestors of it). The local copies, with their tips recorded so
nothing is lost silently:

| branch | tip | why it goes |
|---|---|---|
| `layout-model` | `7ef33ea` | an ancestor of the feature branch; merged |
| `scanned-pdf-ocr` | `298e04f` | an ancestor of the feature branch; merged |
| `v2-vision-layout` | `b89396b` | the abandoned second clone's branch, never merged; the owner said to forget V2 |

## The workflow's first green run, and why it had never been green

The GitHub workflow had failed on every run since it was written, and the reason was in the first
step: `lint` failed, so the test step never executed and the suite had never been run on the
runners at all. Fixing lint exposed what that had been hiding: browserless mistakes that only show
up in a clean environment.

1. **Three scanned-page modules imported the OCR engine from inside a reader**, so a runner without
   `rapidocr` collected an ImportError instead of skipping. Two more were named by the CI itself,
   and instead of chasing them one run at a time the whole suite was run locally with `rapidocr`
   blocked by a sitecustomize shim: **1259 passed, 4 xfailed, 1 xpassed, exit 0** - no module
   outside the conftest list needs the engine, so the list is complete and the chase is over.
2. **Two tests asserted Turkish wording without pinning the language.** They passed on this machine
   only because an earlier test had left Turkish set, and failed on the runner, where the state is
   clean - exactly the order-dependence that makes a suite lie. Both now set the language they
   assert, and the worker test also asserts the English message, which is the point of the change.

CI at `af268f8` + `4bd07c2`: `test (ubuntu-latest)`, `test (windows-latest)`, `test (macos-latest)`,
`package`, `build-windows` - all **success**. The suite also gained the language test that would have
caught the original English/Turkish mixing on its own.

Noted for later: one test is marked `xfail` but passes (an expected-failure marker left behind by a
fix). `strict=False` keeps it harmless, and it is a small, separate piece of tidying.

## The glued footnote number, measured: not a merge, and not a regression

The owner reported that section numbers and headings come out glued to the text that follows
("34 gibi icerik yazarken sayi baslik hizalamalari kaybolmus"). `type_drift.py` over the recorded
runs put numbers on it: `arxiv_19145_r2` carries 16 blocks drawn larger than the reader's style,
3 with a changed alignment and 61 below the readability floor; `tr_tmk_4721` 0/0/13,
`tr_tck_5237` 1/2/10, `tr_cmk_5271` 0/0/3.

Two hypotheses died on the way, both worth keeping:

1. **The reader was not merging anything.** A first look at the written page showed
   `'10 9 8k vocabulary'` as one block while the source had them apart, so the reader's
   `_merge_wrapped_lines` looked guilty. Replaying the same recorded chunk through the reader with
   the layout model off (`read_pdf`, 89 blocks) kept `'8k vocabulary'` in its own block, and the
   written page puts it back at the *identical* bbox (137.4, 70.5, 193.3, 83.9), same size, same
   face. The apparent merge was PyMuPDF grouping the two runs when the written page is re-extracted
   - a measurement artifact, not a defect. Nothing was changed, so nothing had to be reverted.
2. **The glue is in the source, and the model is faithful to it.** The footnote line of the same
   document reads `'14Because several of these differences are small, we addi-'` in the *source*,
   with the marker span at 6.0 pt touching the 9.1 pt text - a LaTeX superscript with no space in
   the text layer. The output carries `'14Bu farkliliklarin bircogu kucuk oldugundan'`, which is
   the right translation of exactly what was read.

**What is actually lost is the inline size.** The marker is set in 6.0 pt in the source and comes
out at 8.9 pt in the output: the writer gives a block one style, so a smaller run inside it - a
superscript marker, a footnote reference, a formula fragment set apart from the surrounding prose -
is drawn at the block's size. That is the visible change the owner noticed, and it is a real
limitation of the block-level writer rather than a reader bug. Preserving per-run sizes inside a
block is a feature-sized change (it needs its own A/B against `type_drift.py` and the written-page
comparison), so it is recorded here as the next candidate rather than patched blind.

Still open from the same scan, and genuinely unexplained: the 16 *inflated* blocks on
`arxiv_19145_r2` are all equation fragments (`'= Cafter(s) -Cbefore(s)'` at 1.37x,
`'N D <-N D -nD s1,s2.'` at 1.62x), so the inflated set is the formula path, not prose.

### Follow-up: the three symptoms are one cause

A span-level size histogram of one page settles it (`src/chunk_0013.pdf` against `out/t_0013.pdf`,
3196 -> 3266 characters):

| size | source | output |
|---|---|---|
| 10.8-11.0 pt (body) | 91.6% | 14.8% |
| 9.2-9.4 pt | - | 57.5% |
| 8.0 pt | 194 chars | 157 chars, plus new 8.7 and 9.1 runs |
| 5.8-6.0 pt | 43 chars | 35 chars |

The body shrinking from ~11 to ~9.3 pt is the fitting ladder doing its job on a longer Turkish text
and is expected. What is not expected is the small end moving *up*: runs set at 8.0 pt reappear at
8.7-9.1 pt, and that is why `type_drift.py` counts "inflated" blocks at 1.33-1.62x on this
document - they are the small equation and marker runs drawn at the block's larger size, not prose
that grew.

So the glued footnote marker, the inflated equation fragments and the grown 8.0 pt runs are one
limitation seen three ways: **the writer gives a block a single style, so a run that was smaller
than its block - a superscript marker, a formula fragment, a footnote reference - is drawn at the
block's size.** The reader is doing nothing wrong, the translations are faithful to a source whose
text layer carries the marker touching the following word, and the fitting ladder is not the
culprit. A fix means carrying per-run sizes from the reader through the fitting pass to the writer,
which is a design change with its own A/B (`type_drift.py` plus the written-page size histogram
above), so it is queued rather than patched blind.

### The readability floor splits by direction, and one whole direction is a real loss

`type_drift.py --verbose` prints the ratio between the size drawn and the size the reader recorded,
and that ratio separates two things the headline count ("N blocks below the readability floor")
lumps together:

- **EN -> TR: faithful.** Every flagged block on `arxiv_19145_r2` is at ratio **1.0** - `'Yll'`,
  `'Gkomp ↓'`, `'Gl Aşağı'`, a bibliography line. These are source-tiny runs (figure labels, a
  reference in small type) drawn exactly as the reader measured them. Nothing was lost; the
  criterion is describing the document, not the translation.
- **TR -> EN: a real loss.** On the three Turkish documents the same criterion is reporting blocks
  squeezed to **0.26-0.65 of their size** - `'Article 134- (1) Anyone who violates ...'` at 0.27,
  `'Child abortion (6) If a woman becomes ...'` at 0.26, `'Each spouse is responsible for their
  own ...'` at 0.37. A Turkish article translated into English is long enough that the fitting
  ladder runs to the bottom of its range, and what comes out is unreadable while still being on
  the page.

So "61 unreadable blocks" on the arXiv document is not a defect and "13" on the civil code is not
the same thing as "13" on the penal code: read the ratio, not the count. The standing rule about
checking what a criterion counts applies to this one as well.

**Next, queued:** (1) why TR -> EN squeezes to 0.26 when EN -> TR never does - is the shorten /
retranslate path in the fitting pass firing for the legal documents, and if it fires, why does the
result still not fit; the per-chunk logs differ (`tr_tck_smoke` reports `shrunk=15 overflow=22`
while `tr_tck_5237`'s chunks report no fitting line at all). (2) The inline-size design from the
entry above, which owns the inflated 8.0 pt runs and the glued superscript marker.

### Correction: the direction "split" was the instrument, not the pipeline

The entry above read a real difference between the directions out of `type_drift.py`'s ratios. Reading
the instrument and the fitting module together takes it back:

- `fitting/fit.py` sets `MIN_SCALE = 0.85` - "point size never shrinks past this fraction of the
  original" - so a **genuinely drawn 0.26x is impossible**. A ratio below 0.85 cannot be describing a
  shrink.
- `type_drift._written_lines` collects every written line whose *centre* falls inside a block's
  recorded box and divides its size by that box's **single** recorded style. A 6 pt footnote marker
  inside an 11 pt block therefore reads as 0.55x, and text from a neighbouring block drawn into the
  box reads as whatever it happens to be. The ratio is direction-blind: it measures how much of a box
  is occupied by runs of a different size, and legal text with small article numbers next to body copy
  simply gives it more to trip over.
- The same mechanism explains the 1.33-1.62x "inflated" blocks on the arXiv run, so both tails of the
  distribution are one blind spot rather than two defects.

What survives: the directions *are* different, but the module already knows it and says so with
measured numbers - `FitLayer.EXPANDED` exists because EN->TR expands 0.93x on average and 0.64x at the
low tail, and `MIN_FILL = 0.75` is set to catch exactly that tail. The direction rule stays (a fitting
change is still read on both directions before it is kept), but it is a rule about blast radius, not
evidence of a TR->EN loss. **Before either the inline-size design or any per-language-pair knobs are
built, `type_drift` has to measure per run/line instead of per block**, or every judgement it feeds
will keep mixing boxes with the runs inside them.

## A per-box instrument replaces the confounded ratio

`tools/audit/type_map.py` prints, for every box, the *set of point sizes* the source prints there and
the set the written page prints there, then names the difference (`faithful` / `flattened` / `shrunk`
/ `grown` / `mixed`). It pairs `out/t_NNNN.pdf` with `src/chunk_NNNN.pdf` and matches boxes by
overlap, so no model is needed. Five recorded runs:

| run | direction | boxes | faithful | shrunk | flattened | grown | mixed |
|---|---|---|---|---|---|---|---|
| arxiv_19145_r2 | EN->TR | 737 | 396 | **317 (43%)** | 15 | 1 | 8 |
| tr_tmk_4721 | TR->EN | 354 | 275 | 64 | 9 | 6 | - |
| tr_tck_5237 | TR->EN | 74 | 36 | 31 | 6 | - | 1 |
| tr_cmk_5271 | TR->EN | 240 | 174 | 52 | 10 | 4 | 4 |
| en_sbb_plan_12 | TR->EN | 1137 | 1046 | 70 (6%) | 9 | - | 12 |

Two things this settles:

1. **The inline-size loss is real but small.** `flattened` - the source had a small run and the
   written page prints everything at the box's larger size - is 6-15 boxes per document, not the
   61-13-10 block counts the confounded ratio suggested. It is worth fixing (a glued footnote
   marker is visible), but it is not where the quality goes.
2. **The lever is the shrink, and it follows the direction.** TR->EN from a Turkish source comes back
   with 43% of boxes shrunk on the arXiv document, while Turkish produced from English shrinks only
   6% on the SBB plan. Turkish is the longer target language, and a box whose translation is longer
   is a box the ladder squeezes. That is the same asymmetry `FitLayer.EXPANDED`, `MIN_FILL` and
   `HEAVY_SHRINK` were designed around - the module's own answer to it is to ask for a shorter
   rendering (`fit.shorten_below_scale`), which is the path to instrument next: for the shrunk boxes,
   did the shorten request fire, and did it arrive inside the budget.

## Driving the shipped exe, and the two defects only that could find

The release rule is that the exe is done when it has been *driven*, not when it has been built
(0.9.8's `dist/LayoutKeep.exe`, 173,006,812 bytes). Walked it by accessibility tree, background
delivery, while the user slept:

- It starts (two processes, the one-file bootstrap and the app) and raises the **floating progress
  bar** with its own controls: `Duraklat`, `Pencereye dön`, minimize.
- The **welcome screen** opens with the five page dots, the interface language picker and the theme
  button *on the first page*, `Bir daha gösterme`, `Atla` / `İleri` / `Geri` - the first-run
  experience the user asked for is real and reachable.
- The **setup screen** carries the header (logo, 1-2-3 step marker, language, `?`, theme, settings),
  the drop zone with the supported-format list, output format, output path, source/target language
  (`auto` -> `tr`), document type, provider (`LM Studio (1234)`) and `Çeviriyi Başlat`.
- The **help dialog** lists eight topics, among them `Kayıpsızlık kriterleri` and `Çevirinin
  kalitesini ne belirler` - the in-app explanation the project treats as a feature.
- About twenty-five minutes of use left **no `crash.log`** (`%LOCALAPPDATA%\LayoutKeep\`).

Two defects came out of it, both invisible to the suite because a test never switches the language
and never reads a widget's wording:

1. **The welcome screen's second page said the worker default was 7**, and `core/tunables.py` has
   set `translation.workers` to 2 since the default was lowered - Turkish even contradicted itself,
   with the provider page two paragraphs later already saying 2. Corrected in tr/en/de (`9db30c5`).
2. **A label and a button did not follow the language.** The setup card showed an *English*
   dual-output hint among Turkish labels, and the help dialog's button read `Close`.
   `JobSetupWidget` read `UIStrings.DUAL_HINT` / `RANGE_HINT` once in `__init__` and
   `retranslate_ui()` refreshed every other label but those; the button's text comes from
   `QDialogButtonBox`, i.e. Qt's own catalog, which is not installed. Fixed with a `CLOSE_BTN` key in
   three languages and a refresh in `retranslate_ui()`, plus
   `tests/test_ui_strings_follow_language.py` - **proven red on the base by stashing the fix**
   (`0f23538`).

**Not yet carried by the shipped file:** both fixes are in the source; the 0.9.8 exe still shows the
old strings, so the next build is the one that carries them.

**Next in this walk** (not done): the provider settings dialog's `Test Et` button, which is the one
free end-to-end proof that the *built* exe reaches a model server (`Bağlantı çalışıyor - N model
bulundu`).

## 0.9.9: the build that carries the language fixes, driven before it was published

The exe in the 0.9.8 release predates the two language defects found by driving it, so the source
fixes reached nobody yet. Rebuilt with the documented recipe (`packaging/build.bat`, detached, log
polled - the script now exists in the tree instead of being retyped per release), which produced
173,007,377 bytes against 0.9.8's 173,006,812.

Driven before publishing, as the rule requires. The first-run screen did not open this time (the
setting remembers it has been seen), so the decisive check was the setup screen in a Turkish window:
the dual-output hint now reads `'Çevrilmiş dosyanın yanına, kaynağı da içeren ikinci bir PDF
yazılır. Denetim ve asıl çıktı değişmez.'`, where before the fix that same label was English in the
middle of Turkish ones. That is the fix, in the built artefact, on the page. No `crash.log` after the
walk.

`v0.9.9` is published with bilingual notes (the changed behaviour, and the measured known limits:
dense forms below the readability floor, L2 rows on an arXiv bibliography, OCR dependence, no RTL).
The published asset was downloaded back and compared: **`cmp -s` says byte-for-byte identical**, and
the asset is 173,007,377 bytes. A `sha256sum` comparison printed a stray `\` escape marker in front
of the second hash (coreutils marks an escaped filename), which looks like a mismatch and is not one -
`cmp` is the check to reach for.

**Noted while walking, then disproved - the floating bar at startup is the designed hand-over.**
The bar showing `Hazırlanıyor… · 0/0 parça` before any job existed looked like a stale window; it is
not. `main_window.changeEvent` watches `WindowStateChange` and hands the run to the bar whenever the
window is minimized (`if self.isMinimized() or not self.isVisible()`, `main_window.py:127`). The exe
was launched with `-WindowStyle Minimized`, so the bar was doing exactly its job, and both launches
told the same story because both used the same launch flag. Launch it normally and the window stays.

## The scan that carried alpha, and the chunk that could never be written

The TR -> EN campaign finished at 23:25 with `tr_plan_11 exit=1`, and its log said why in one line:
`1 chunk(s) produced no output; not merging a document with holes`. Refusing to merge a document with
a hole is the right behaviour - and it left one document unfinished.

Forty-nine of the fifty chunks were on disk. The hole was chunk 0000, which had neither an output nor
a `.lkproj` progress marker, so `--resume` retried it - and it failed again, in 11-12 seconds, every
time. Its own log ends on three lines that are not a Python traceback:

    'created' timestamp out of range; ignoring top bytes
    'created' timestamp seems very low; regarding as unix timestamp
    cannot reshape array of size 32770400 into shape (3425, 2392, 3)

The failure sits below Python: `faulthandler` produced no native traceback either, and the chunk's
entire stderr is captured into that log, so nothing was being swallowed. The numbers are the clue:
32,770,400 = 2392 x 3425 x 4, and 2392 x 3425 is exactly the page - a four-component buffer was being
reshaped into three.

The line is in `writers/pdf_writer.py`. The whitening pass rebuilds the scanned image's pixel buffer
with a hard-coded three channels, while the guard above it converted the colour space only when
`pixmap.n != 3`. Measured on that page's image: `Pixmap(doc, xref)` gives `n=4, alpha=1`, and
`Pixmap(csRGB, pixmap)` **keeps** the alpha, so the buffer stayed four components wide. Dropping alpha
first was measured to give `n=3, alpha=0`, and `csRGB` after it w*h*3 bytes.

Fixed by dropping alpha before the colour conversion and reshaping on the pixmap's own component
count, and the conversion now lives in `_scan_pixels` so it can be tested on its own
(`tests/test_pdf_writer_scan_alpha.py`). The test was **proved red** by putting the base's logic back
inside the helper: `ValueError: cannot reshape array of size 192 into shape (6,8,3)` - the same defect
on a smaller page.

Then the real thing, with the fix in place: `[50/50] ok chunk 0000 ... wrote out/t_0000.pdf` and
**`merged 50 chunks -> tr_plan_11.en.pdf (198 pages)`**. The Eleventh Development Plan is whole, and it
is a publishable source (state publication, no third-party rights), so it can go on the comparison
site with the others.

Two things this leaves on the table, worth doing rather than forgetting:

1. **The failure was undiagnosable from the campaign log for a while.** One line, `exit=1`, and a
   chunk log whose last lines are library noise. **Done the same night:** `translate_book.py` now
   names the stage a failing chunk died in (`died after 'review'`), read from the pipeline's own stage
   lines by `_stage_reached` - `tests/test_translate_book_stage.py` keeps the real log tail from this
   incident as its fixture, and its end-to-end test was **proved red** by disabling the branch (the
   base's tail is the `retry … | fitting … | review …` line this campaign printed).
2. **A chunk that fails after eleven hours of a campaign gets no automatic second try.** `--resume`
   covers it, but only if someone notices the document was not merged. **Done the same night:**
   `translate_book.py` retries each failed chunk once, sequentially, through `_retry_failed`
   (`tests/test_translate_book_retry.py`, four tests, no model server involved). A chunk that fails
   twice is still a real failure and is reported as one, and the tool was re-run over the finished
   document afterwards to prove the edit did not break the runner (`merged 50 chunks -> 198 pages`).

## The budget-capped dedupe fix, measured: the readability floor moves for the first time

The dedupe pass shared a repeat whenever the source text matched, so the fitting pass's *capped*
shorten request (`max_len`) could be answered by a sister occurrence's uncapped translation - a
capping segment received text that ignored its budget, and `providers/cached.py` already refuses to do
that with a memory hit. The fix forwards a capped repeat to the provider instead of sharing.

Measured on `tr_tck_5237`, which is the only honest way to keep it: a **copy** of the recorded run with
its `out/t_*.pdf` deleted, re-run with `--resume`, so the memory answers the translations and only the
shorten path reaches the model. One variable changed - the fix. 21.6 minutes, 22 chunks, 88 pages.

| criterion | before | after | change |
|---|---|---|---|
| L2 left untranslated | 52 | **31** | **-21** |
| L6 numbers lost | 44 | 41 | -3 |
| L7 text drawn over text | 13 | 14 | **+1** |
| D1 below readability floor | 429 | **391** | **-38** |
| D2 short blocks left unchanged | 12 | 9 | -3 |
| L1, L3-L5, L8-L10, D3 | 0 / 0 / 0 / 16 / 0 / 2 | unchanged | - |

The cost is recorded with the benefit: **L7 goes up by one**, which is the same trade this project has
paid before when more text is drawn honestly rather than squeezed into place. The per-box typography
measurement (`type_map.py`) is flat - 74 boxes, `faithful` 36 -> 35, `shrunk` 31 -> 31, `flattened` 6
-> 6, `mixed` 1 -> 2 - so the fix does not change the *drawn sizes*; it changes *which text* is drawn,
which is why the criterion that moved is the readability floor and the untranslated count, not the
shrink count. Two instruments, two answers, and both belong in the record.

This is the first A/B in the campaign where D1 has moved at all. Until now every attempt at the shrink
ladder (the writer's own box, tighter leading, widening a narrow box) came back flat or worse; the
lever turns out to be *what the model is asked for*, not how the fitting pass is tuned.

The re-run is kept at `_artifacts/heldout/live/tr_tck_5237_ab` (untracked, like everything under
`_artifacts/`), so the comparison site can be regenerated from the improved pages rather than the older
run - its `tr_tck_5237` images currently come from before this fix.


## Gece nöbeti: kısaltma merdiveni neden hiç istek atmıyor (TR -> EN)

`fit.shorten_below_scale` (`_SHRUNK_ATTEMPTS = 2`) yolunun ölçümü iki aletle yapıldı:
`type_map.py` (kutu başına boy kümesi) ve manuel bir `fit_segment` tekrar koşusu — hiç model yok.

**Ölçüm (tr_tck_5237, TR -> EN):** 1.701 blok · as_is 1.169, shrunk 374, overflow 158.
374 shrunk'un 362'si kutusunun tam-boy karakter bütçesinin ÜZERİNDE — yani kısaltma isteği
atılması gereken halde atılmamış. **retranslate yalnızca overflow'da çağrılmış** (514 çağrının
tamamı overflow bloklarından). Kapılar doğru: `_MIN_SHORTEN_CHARS` 34 kutuyu düşürüyor,
headroom kapısı yalnız 8, `would_ask` (soru sorulmalıydı) **156-237 kutu** — hiçbiri sorulmamış.

**Kök neden: çeviri belleği kısaltma isteğini aynı uzunlukta yanıtlıyor.** `TranslationMemory`
anahtarı yalnız `source src tgt model` — `max_len` anahtarın parçası değil. Merdiven
"X karakterden kısa yaz" diye soruyor, önbellek orijinal uzunlukta cevap veriyor, `fit_segment`
"aynı metin geldi" görüp merdiveni bırakıyor. TR sadece hedef dil olduğundan Türkçe kaynaklar
EN çevirisiyle büyüyor, bu yüzden 43%'lük ezilme yalnız bu yönde görünüyor.

**Düzeltmeler (ölçülü):**
1. `providers/cached.py`: önbellek isabeti isteğin `max_len`'ini ihlal ediyorsa servis edilmez,
   istek iç sağlayıcıya gider (`tests/test_provider_cached.py`, 3 senaryo).
2. `providers/dedupe.py`: kapsamlı istek, ortak cevap bütçesinden uzunsa kendi isteğiyle modele
   gider — aynı kural önbelleğe de uygulandı (`tests/test_provider_dedupe.py`).

Hedefteki beklenen etki: TR -> EN'de `shrunk` tablosu aşağı iner (merdiven artık gerçekten
fikir isteyebiliyor). Bunu kanıtlamak için gerçek model koşusu gerekli — makine boşaldığında
`tr_tck_5237` yeniden koşulup `type_map.py` ile karşılaştırılacak.

## Gece nöbeti: yeni açık test kaynakları indirildi (henüz koşulmadı)

Üç kaynak `_artifacts/heldout/incoming/` altına indirildi, koşusuna sıra bekliyor; lisans notu
jurnale alındı (klasör .gitignore içinde, içerik burada):

- **arXiv 2601.00135** - Chow/Lim/Mudgal, "Generalised Fermat equations in dense variables over
  finite fields and rings", 24 sayfa, dip dizi formüllü. **CC BY 4.0** (abs sayfasındaki license
  ikonu doğrulandı) - yayınlanabilir.
- **arXiv 2609.06115** - Varshalovich "Quantum Theory of Angular Momentum" e-sürümü, 408 sayfa,
  **CC-BY 4.0** (abs sayfasında beyan). Uzun-kitap kampanyası adayı, tek geceye sığmaz.
- **Gutenberg #56464** (Turkish Literature, 620 kB EPUB) ve **#64807** (Turkish fairy tales,
  2,2 MB EPUB) - ABD'de kamu malı; şiir/drama düzeni, uzun cümleler, imgalı EPUB testleri.

Öncelik sırası: önce önbellek düzeltmesini kanıtlamak için tr_tck_5237 yeniden koşusu, sonra bu
kaynaklar. Eski kural sürüyor: Ross kitabı, basılı yasal kodların taramaları, IRS formları
NOT_PUBLISHABLE.

## Gece nöbeti: düzeltmenin gerçek-model sınavı — istek açıldı, kazanç çıkmadı

`tr_tck_5237` önbellek düzeltmesiyle yeniden koşuldu (r2, 2 işçi, 15,8 dk, 88 sayfa, exit=0).
Karşılaştırma aynı parça üzerinden (chunk 0000):

| | as_is | shrunk | overflow |
|---|---|---|---|
| r1 (önbellek öncesi) | 31 | 15 | 22 |
| r2 (önbellek düzeltmeli) | 31 | 14 | 23 |

`type_map.py` r2'de: 74 kutu — faithful=36, shrunk=31, flattened=6, mixed=1; r1 ile aynı dağılım.
`_try_shorten` saniyor (`would_ask` 117 -> r2'de 95; token farkı önbellek ıskalarından), ama model
kısa yanıt üretmiyor: soru artık Modele gidiyor, gelen yanıt bütçe içine sığmıyor ve merdiven
"aynı metin" görmeden devam edip yine en son çabayı bırakıyor.

Yani iki şey ayrıştı: **isteğin tıkanıklığı giderildi** (ölçülebilir: r2'de retranslate çağrıları
gerçek oldu), ama **istekler sonucu değiştirmiyor** — gemma-4-e4b bu istemde kısaltmayı öğrenmiyor.
Bu, bir sonraki adımın yönünü değiştirir: aynı bütçeyi daha etkili sormak (prompt'ta "N karakterden
kısa bir kuşak yaz, en önemlileri koru" gibi) ya da ezilen kutucuklar için MIN_SCALE'ı yön bazında
ayarlamak. Fibonacci-vari kısaltma stratejisi ölçülmeden yapılmayacak; jurnale kaydedildi.

Ayrıca: r2 çıktısı `_artifacts/heldout/live/tr_tck_5237_r2/` altına alındı (çalışma dizinini --out
göreli bırakınca proje köküne yazan bir araç ayrıntısı的原因; görsel olarak aynı).

## Gece nöbeti: Gutenberg #56464 (Turkish Literature) EN->TR koşusu bitti

Yeni açık kaynak ilk defa koşuldu: Project Gutenberg #56464 — "Turkish Literature; Comprising
Fables, Belles-lettres, and Sacred Traditions" (kamu malı, EPUB, 11 bölüm). `translate_epub.py`
3 bölüm parçası / 2 işçi, 75,5 dakika, exit=0. Çıktı + proje + parça kayıtları
`_artifacts/heldout/live/gutenberg_56464/` altında; koşu günlüğü `run_log.txt`.

Talimat: EPUB kaynağı `translate_book.py`'ye verilmez (kaynağı PDF parçalara böler, "source or
target not a PDF" ile ölür); EPUB için `translate_epub.py` doğru araçtır. Bat dosyası güncellendi.

Sıradaki gece işi: bu koşunun `lossless_audit.py` denetimi ve karşılaştırma sitesine eklenmesi
(arXiv 2601.00135 CC BY 4.0 da sıradadır).

## Gece nöbeti: kısaltma istemi "sert limit" olarak yazıldı — r3 ölçümü: kutu tipografisi değişmedi

Önceki turun sonucu, kısaltma merdiveninin tıkanıklığının önbellek düzeltmesiyle açıldığı ama
gemma-4-e4b'nin "try to keep within N characters" (bir hedef gonka gibi okunan yumuşak ifade)
isteminden kısa yanıt üretmediğiydi. İstem sertleştirildi: "write its translation SHORT enough to
stay within that many characters ... Max length is a hard limit measured in characters; do not
pad, do not expand" (`providers/openai_compat.py`, commit 7189d37).

Ölçüm yine aynı parça üzerinde: `tr_tck_5237` kopyası, `out/t_*.pdf` silinmiş, bellekten
cevaplanan r3 koşusu (22 parça, 14,2 dk, exit=0 — yalnızca kısaltma yolu modele gitti):

| | as_is | shrunk | overflow |
|---|---|---|---|
| r1 (önbellek öncesi) | 31 | 15 | 22 |
| r2 (bütçe düzeltmesi) | 31 | 14 | 23 |
| r3 (sert istem) | 31 | 14 | 23 |

`type_map.py` r3: 74 kutu — faithful=36, shrunk=31, flattened=6, mixed=1 — r1/r2 ile aynı.
İstek başına ölçüt toplamları (parça günlüklerinden): L2 34→32, L6 43→43, L7 14→14, L8 16→16.

Sonuç: kısaltma merdiveni bu modelde **istemle çözülmüyor**. İstek açıldı (r2), istem sertleştirildi
(r3); ikisi de kutu tipografisinde ve ölçütlerde ölçülebilir bir değişiklik üretmiyor. Bu, merdiven
kalıcı olarak çıkmaz demek değil — bir sonraki kol aynı bütçeyi daha farklı bir *şekilde* sormak
(ör. "bu cümlenin en önemli bilgi taşıyan parçalarını seç, kalanı at" gibi bir ilkeli kısaltma
kosteni) ya da jurnalde daha önce not edilen yön bazlı MIN_SCALE ayarı. İstem dilini daha fazla
ceydetmek ölçülmeden yapılmaz; üç veri noktası artık jurnale yazıldı.

r3 kayıtları `_artifacts/heldout/live/tr_tck_5237_r3/` altında (kaynak parçaları r2'den kopyalandı).

## Gece nöbeti: README sadeleştirme devamı — Known limits tabloya taşındı

Kalan indirim: README (EN) 289→284 satır, TR 278→277. Known limits bölümü artık tek paragraf:
her sınır vaka ölçümüyle `docs/QUALITY-FACTORS.md`'deki yeni "Known limits" tablosunda.
_TR tablosu yok_ — README.tr.md bu bölümü zaten İngilizce README'ye işaret ediyordu; şimdi
kaliteli ölçüm sayfasına işaret ediyor. Kuyruğun 3. maddesi için kalan: comparison site yenileme
(4. madde) sonrası tekrar satır sayısı ölçümü.

## Gece nöbeti: kuyruk 1 kapanış — kısaltma merdiveninin önce/sonra tablosu

Kuyruk madde 1 (TR→EN ezilme oranını düzeltme sonrası yeniden ölçme) üç koşuyla kapandı.
Ölçüm hep aynı parça üzerinden (`type_map.py`, 74 kutu, model-siz araç):

| koşu | işlenen değişiklik | faithful | shrunk | flattened | mixed |
|---|---|---|---|---|---|
| r1 | önbellek düzeltmesi öncesi | 36 | 31 | 6 | 1 |
| r2 | bütçe-dolu dedupe düzeltmesi | 36 | 31 | 6 | 1 |
| r3 | sert kısaltma istemi | 36 | 31 | 6 | 1 |

fitting çizgisi de sabit (as_is=31, shrunk=14, overflow=23). İstek başına ölçüt toplamları:
L2 34→32, diğerleri değişmedi. **Sonuç: üç veri noktası da tipografiyi değiştirmedi** — bu gece
elinde olan iki kol (isteğin açılması, istemin sertleştirilmesi) için ölçüm eksi. Merdivenin
çıkmazı istem dilinde değil; sonraki kol daha farklı bir istek *şekli* (ilkeli seçim/kısaltma)
ya da yön bazlı MIN_SCALE. r1–r3 kayıtları `_artifacts/heldout/live/tr_tck_5237{,_ab,_r2,_r3}/`.

## Gece nöbeti: kuyruk 2 için keşif — satır-içi boyut kaybının mekanik haritası

Flattened (kaynaktaki küçük satır-içi çalıştırmanın bloğun büyük boyutuyla yazılması, belge başına
6-15 kutu) için üç katman birbirine göre okundu; mekanik dört açık nokta verdi:

1. **Marker kümesindeki Style kayıp küçük boyutu taşımıyor.** `docir._inline_styles` yalnız
   `dominant_style()`'dan * farklı* stili marker yapar (key: aile, boyut, kalın, italik, renk).
   Bağlaç/k bölüm numarası gibi 6 pt parça marker'ı yapılmaz — bunlar direkt yok olur; kalan
   uzunlukları kalın/italik flag'iyle taşınan koşularda da **Style.size alanı korunur**, sorunun
   yazı taraflı olmadığı buradan görülür.
2. **Yazıcı** (`pdf_writer._span_html`) her span'in kendi stiliyle `font-family`/`color` taşır
   ama `font-size`'ı blok seviyesinde CSS'ten (`_css_for_block`, dominant.size) alır — span
   boyutu kullanılmaz. yani span-in-italik gibi geri gelen koşullarda boyut korunmaz.
3. **`fitting.pdf_pass.apply_scale`** ölçek uygular (`span.style.size *= scale`) — ki burada
   zaten scale uygulanır ama yalnızca blok ölçeği, span içi kayıtları sıfırlar. `insert_htmlbox`
   zaten kendi shrink'ini yapar.
4. **Ölçüm aleti** hazırlık: `type_map.py` artık `--flattened-by-page` veriyor (3 file'ı tek
   sayfada gösterebiliyor).

**Tasarım kararı** (ölçülmeden değişiklik yapılmayacak): writer'da span'in Style.size kullanmak
dahil her amaç, bir önceki kolun gerçek model koşusuyla A/B'dir; kutu başına flattened sayısının
önce/sonrası ölçülür, L7 artışı da okunur. A/B bu gece yapılmayacak — makine saat başında boşaldı
ve kısaltma merdiveni yolu ölçümünden çözüm çıkmadı; flattened yazıcı değişikliği ayrı bir kuyruk
öğesi olarak jurnalde öyle duruyor.

## Gece nöbeti: arXiv 2601.00135 (CC BY 4.0) EN->TR koşusu — iki tur

Yeni açık kaynak ilk defa koşuldu. İlk tur *geçersizdi ve silindi*: koşucu çalışma dizisini
(`--work`) vermediğimde `_artifacts/heldout/live/src`, r2/r3 koşularının TCK parçalarıyla
doluydu ve koşu oartefakt parçaları okudu; çıktı TCK metni taşıdı. Ders: uzun koşular her zaman
kendi `--work` dizinini alır, paylaşılan `live/src` asla doğrudan kullanılmaz.

İkinci tur temiz çalışma diziniyle (`work_arxiv`) koşuldu: 6 parça / 2 işçi, 29,5 dk, exit=0,
24 sayfa birleşti. Kayıt `_artifacts/heldout/live/arxiv_2601_00135_run/` altına taşındı
(kök dizine yazılan merge PDF'i — araç `--out` göreli yolun çalışma dizinine yazılan bilinen
ayrıntısı). Denetim (`--to tr`):

| ölçüt | değer |
|---|---|
| L1, L4, L5, L7, L9, L10 | 0 |
| L2 left untranslated | 6 |
| **L3 text not on the page** | **20** |
| L6 numbers lost | 5 |
| L8 untouched moved | 1 |
| D1 readability floor | 97 |
| D2 | 3 |
| D3 squeezed | 9 |

Karakteristik: yoğun matematik formül paragrafları — model denklem ağır satırları çevirmede
taşıyamıyor (L2/L3 açık); D1 kısmen formül satırlarının küçültülmesi. dipnottar (L3'ün dağılımı)
sonraki analiz için örnek girdi. Gutenberg #56464'ün EPUB koşusu tamamlanmıştı; sitedeki yerini
EPUB karşılaştırma girdisi ayrı iş olarak bekliyor.

**Düzeltme (aynı gün, ölçümle): L3'ün sebebi model değil.** Bu koşunun L3=20'si "model denklem ağır
satırları taşıyamıyor" diye okunmuştu; `verify.py`'nin kendi yorumu ve bu ölçüm bunu çürütüyor.
Çıktı PDF'lerinde işaretlenen satırlar arandı: `SONLU ALANLAR…FERMAT DENKLEMLERİ` başlığı **7 dosyanın
hepsinde** var, `Anahtar kelimeler`, `Özet`, `Matematik Ders Sınıflandırması` da var — blok **çizilmiş**,
kutusunda kırpılmış. Yalnızca `Aritmetik denklemler…` bulunamadı (kırpılan kuyruk). Yani L3 burada
"yazıcı düşürdü" değil "fitting sığdıramadı": `verify.py`'nin L3 tanımı bunu zaten yazıyor ve PLOS'un
matematik paragrafları için aynı şeyi not ediyor (okuyucu bir sayfa formülü tek 79 pt "satır" olarak
birleştirdi, hiçbir şey sığamadı, denetim sayfada duran sekiz bloğu "düşmüş" saydı).

**Sıradaki iş bu yüzden kriterin kendisindeydi — ve ölçüldü.** L3 "kaç kelime eksik" demediği için
iki okuyucu (nöbet ve bu satırları yazan) aynı sayıyı yanlış okudu. Detay artık
`<eksik> of <toplam> words not on the page` yazıyor (`verify.py`; `missing == total` = sayfada hiç
olmayan blok, daha azı = kırpılmış blok) ve testli (`tests/test_verify_l3_counts.py`).

Aynı koşu bu detayla yeniden ölçüldü (parça 0, 7 L3):

```
10 of 67 words not on the page: Özet. Let A bir sonlu cisim…
 7 of 41 words not on the page: |A| ≫p koşulunu…
 1 of  9 words not on the page: SONLU ALANLAR VE HÜKÜMLER…
 1 of  5 words not on the page: 2020 Matematik Ders Sınıflandırması…
 1 of  5 words not on the page: O halde en az εqs−1 tane çözüm…
```

**Hepsi kırpılmış, hiçbiri kayıp değil** ✓ — "N of N" hâli bu koşuda hiç çıkmadı ve kayıp 1-10
kelimelik kuyruklar. Yani L3'ün 20'si ne "model formülü taşıyamadı" ne "okuyucu birleştirdi": hedef
dil uzun olduğu için **son satır kutuya sığamıyor**, fitting kırpıyor ve blok incelemeye düşüyor —
D1'in aynı sayfada işaretlediği bloklarla aynı küme. Sıradaki iş bu yüzden hâlâ kutu/sığdırma
kaldıracı (D1'in kaldıracı), okuyucu değil.

## Ölçüm, karar değil: EPUB -> PDF çiftinin sayıları (kullanıcı doğrulaması bekliyor)

Kullanıcı, kendi doğrulaması olmadan hiçbir şeyin yayınlanmış sayfalarda "çalışıyor" diye
yazılmamasını istedi. Bu yüzden **hiçbir kapı açılmadı** ve karşılaştırma sitesine EPUB girdisi
eklenmedi; yalnızca projenin kendi adımı çalıştırıldı
(`tools/audit/faz2_candidates.py`, "measure candidate pairs ... before any of these pairs get added
to capabilities.OPEN_PAIRS") ve çift listeye *ölçüm için* eklendi.

Sonuç, satır birebir:

```
ok   rich_book.epub     -> pdf   words 101%  (68/67) img 1/1 pages 1/1 styled 0/5
```

Okunuşu: kelime düzeyinde kayıp yok (68/67 - fazladan bir kelime, tire kırılması), görsel 1/1,
sayfa 1/1, ama **biçimlendirme taşınmıyor (0/5)**. Aynı ölçümde hâlihazırda *açık* olan çift
`rich_book.epub -> png` de `styled 0/5` veriyor; yani çift, mevcut çıtayla tutarlı. Uygulama zaten
yazılı (`tests/test_epub_pdf_reflow.py` ona bağlı) ve CLI/arayüz yalnız
`capabilities.OPEN_PAIRS` bayrağıyla kilitli.

Karar kullanıcının: açılırsa (1) CLI ve arayüzde EPUB -> PDF görünür olur, (2) karşılaştırma sitesi
Gutenberg EPUB koşusunu XML yerine **sayfa olarak** gösterebilir. Açılmadan önce kullanıcının kendi
gözüyle bir EPUB'ı PDF'e çevirip bakması gerekiyor.

## A/B: satır-içi boyutları korumak — ölçüldü, kazanç var, varsayılan yine de kapalı

Yazıcı bir bloğa tek bir `font-size` veriyordu (`_css_for_block`), yani kaynakta küçük olan satır-içi
parça - üst simge işareti, dipnot numarası, formül kırıntısı - bloğun büyük boyutuyla çiziliyordu.
Ölçüm önce veriyi doğruladı: `arxiv_19145`'in altı parçasında **145 bloğun 48'i** farklı boyut taşıyor
(10,2 pt blok içinde 6,8 pt parçalar). Yani kayıp yazıcıda; okuyucu boyutu koruyor.

Değişiklik geliştirici ayarı olarak eklendi (`writer.inline_span_sizes`, varsayılan **kapalı**;
`pdf_writer._span_html` farklı boyutlu koşuya `font-size` veriyor) ve aynı kayıtlı koşu iki kez
yazıldı (model yok, `rewrite_run.py`):

| | kutu | sadık | ezilmiş | **düzleşmiş** | karışık |
|---|---|---|---|---|---|
| saklı taban (eski motor) | 697 | 363 | 318 | **7** | 8 |
| yeniden yazılmış, **ayar kapalı** | 698 | 361 | 322 | **7** | 7 |
| yeniden yazılmış, **ayar açık** | 698 | 363 | 322 | **4** | 8 |

**Düzeltme (önemli): ilk yazdığım "+4 ezilme bedeli" ayardan değil, yeniden yazmanın kendisinden
geliyordu.** O tabloda "taban" olarak *saklı* koşuyu (eski motorun ürünü) kullanmıştım; projenin kendi
kuralı bunu yasaklıyor - "iki koşuyu değil, aynı kaydın iki kod sürümünü karşılaştır". Koşuyu iki kez
yeniden yazınca (yalnız ayar farkıyla) gerçek tablo yukarıdaki üç satır oluyor: **ezilme 322 -> 322,
yani ayar hiç ek sıkıştırma yapmıyor**; +4 tamamen eski motordan bugünkü motora geçişin etkisi.
Ayarın ölçülen etkisi: **düzleşmiş 7 -> 4**, karışık 7 -> 8 (+1), diğerleri sabit.

Ölçütler (aynı koşu, `lossless_audit.py --to tr`):

| ölçüt | taban | ayar açık |
|---|---|---|
| **L7 üst üste metin (asıl risk)** | **0** | **0** |
| D1 okunabilirlik tabanı | 296 | 296 |
| D2 | 7 | 7 |
| **D3 sıkışmış** | 2 | **1** |
| L2 / L3 / L6 / L8 | 7 / 0 / 2 / 1 | aynı |

Yani ayar üç kutuyu düzeltiyor, hiçbir ölçütü kötüleştirmiyor, D3'ü iyileştiriyor - ama varsayılan
**kapalı** bırakıldı: kullanıcı, kendi doğrulaması olmadan hiçbir şeyin "çalışıyor" diye
yazılmamasını istedi, ve tek bir belgede ölçülmüş bir kazanç onu açmaya yetmez. Sayfa başına fark:
`t_0002` (1 kutu) ve `t_0013` (2 kutu) düzeliyor; `t_0000` ve `t_0008` aynı kalıyor - yani
düzleşmenin bir kısmının sebebi başka (fitting'in kendi ölçek uygulaması) ve o kısım bu ayarla
kapanmıyor.

**Aynı A/B, iki kolu da yeniden yazarak, beş belgede** (hepsi kayıtlı koşu; `×_off` ve `×_on`
dizinleri aynı motorla yazıldı, tek fark ayar; `rewrite_run.py` + `type_map.py` + `lossless_audit.py`):

| koşu | kutu | düzleşmiş | ezilmiş | sadık | ölçütler |
|---|---|---|---|---|---|
| `arxiv_19145` | 698 | 7 -> **4** | 322 -> 322 | 361 -> 363 | aynı |
| `cookbook_1907` | 440 -> 441 | 61 -> **53** | 271 -> **252** | 3 -> 3 | aynı |
| `arxiv_19113` | 353 | 5 -> **3** | 163 -> 163 | 169 -> 171 | aynı |
| `irs_p505` | 1670 | 22 -> **14** | 739 -> **689** | 719 -> **763** | aynı |
| `plos_animal_movement` | 526 | 9 -> **1** | 232 -> 232 | 276 -> **281** | aynı |
| **toplam** | | **104 -> 75 (-%28)** | **1727 -> 1658 (-69)** | **1528 -> 1581** | **5/5 aynı** |

Yani ayar beş belgede düzleşmeyi %28 azaltıyor, **69 blok daha az sıkıştırıyor** (kaybı azaltıyor, yeni
sıkıştırma getirmiyor) ve **hiçbir ölçütü kıpırdatmıyor**: `L3`, `L7` (ayarın taşıdığı asıl risk),
`D1` ve `D3` beş koşunun beşinde birebir aynı. Tek ölçülmüş maliyet `cookbook_1907`'nin `grown`
sayısı (104 -> 130); bu sayı henüz açıklanmadı - per-span boyutlarla satır yüksekliği değişince yazılan
sayfa yeniden çıkarılırken kutu başına boyut kümesinin değişmesi olası, ama tahmin etmek yerine
ölçülmesi gerekiyor.

**Bu tablo, önceki iki tablonun yerine geçer.** İlki saklı koşuyu taban alıyordu (eski motor) ve
"+4 ezilme bedeli" o kusurdan geliyordu; ikincisi aynı kusuru beş belgeye yayıyordu ve ölçütlerde
görünen "iyileşmeler" (plos L3 8 -> 0, irs_p505_rewritten L7 10 -> 0) da eski motorun eseriydi -
iki kolu da yeniden yazınca ikisi de kayboldu. Ayarın kendini açma şartı buydu: uyarısı "ölçülmeden açılmaz" diyordu. Ölçüm yapıldı, kullanıcı da
"sen test ettiysen açabilirsin" dedi - **varsayılan artık açık** (`default=True`), etiketteki
"(deneysel)" kaldırıldı, yardım ve uyarı metinleri ölçülen sayılarla değiştirildi. Kararı bir daha
sessizce geri çevirmeyi imkânsız kılmak için `test_the_default_is_on_and_only_a_measurement_turns_it_off`
yazıldı: varsayılanı çevirmek isteyenin aynı iki-kollu A/B'yi yeniden yapması gerekiyor.

### Açık kusur: çevrilmiş EPUB geçersiz XHTML döndürüyor (kaynak: kıyas isteği)

`gutenberg_56464` çevirisinde (`_artifacts/heldout/live/gutenberg_56464/gutenberg_56464.tr.epub`) bir
belge **geçersiz** çıkıyor: `OEBPS/6311803512635209464_56464-h-8.htm.xhtml`, satır 22, sütun 5617,
"mismatched tag". Ölçüm: kaynak EPUB'ta **14 belge, 0 bozuk**; çevrilmiş EPUB'ta **1 belge bozuk**.
Etiket farkı: kaynakta olup çeviride olmayan - 1 adet `<div>` açılışı (bu yüzden dosyada 45 açılış /
46 kapanış), 1 `<span>` + 1 `</span>` çifti, 3 farklı `<a href>` açılışı (karşılık gelen iki `</a>`
duruyor). MuPDF bunu tolere ediyor (uyarı basıp açıyor); katı okuyucular reddeder. Yani EPUB→PDF
çiftinin önündeki gerçek engel burada: çıktı kendi başına geçerli değil.

Denenip **elenen** yol: `epub_writer._apply_edits` içindeki üst üste binme. Düzenlemeler blok
aralıklarından (ayrık) ve `<img>` alt/title değer aralıklarından geliyor; ikincisi bloğun içinde
kalabildiği için gerçekten üst üste biniyor ve `cursor` geri gidebiliyordu (metin çoğaltan bir hata,
artık kapatıldı), ama kaybolan `<a>`/`<span>`/`<div>` bunun eseri değil - blok yeniden yazılırken
satır-içi işaretlemenin yalnız kalın/italik taşınması (kodun kendi yorumu bunu söylüyor). Kusur
**açık**: reprodüksiyon bir `<p>` içindeki bağlantıyı çevirip `<a href>`in durup durmadığına bakmak.

Ders (kendi hatam): aynı dosyada test eklerken import satırını değiştirdim ve 11 testi kırdım; bunu
"düzeltmem bozuk" sanıp geri aldım - yanlış teşhis. Şüpheli bir kırılmada önce **kendi değişikliğini**
`git stash` ile ayır, sonra suçla.

### Araç tuzağı: `rewrite_run.py` ayarları yüklemiyor

İlk A/B **hiçbir şey ölçtü**: `LAYOUTKEEP_TUNABLES` ile verilen geçersiz kılma dosyası yerindeydi ama
`tunables.get('writer.inline_span_sizes')` **False** dönüyordu, çünkü `rewrite_run.py` okuyucu/yazıcıyı
doğrudan çağırıyor ve `tunables.load()`'u (CLI ile arayüzün açılışta çağırdığı satır) hiç
çağırmıyor. İki koşu aynı çıktıyı verdi ve yorum "ayar etkisiz" olacaktı. Doğru çağrı:

```
LAYOUTKEEP_TUNABLES=<geçici.json> python -c "
from layoutkeep.core import tunables; tunables.load()
import runpy, sys; sys.argv=['rewrite_run.py', <koşu>, <hedef>]
runpy.run_path('tools/audit/rewrite_run.py', run_name='__main__')"
```

Ayar A/B'lerinde önce `tunables.load()`'un çağrıldığını **doğrula** (`tunables.overrides()` boş
dönmemeli); yoksa ölçüm, hiç okunmamış bir ayarı ölçer.

### Yan bulgu: geliştirici ayarlarının etiketleri tek dilli

`core/tunables.py` içindeki etiket, `help_text` ve `warning` alanları **yalnız Türkçe** ve arayüzde
anahtar başına çevirileri yok - yani uygulama İngilizce ya da Almanca çalışırken geliştirici ayarları
ekranı Türkçe kalıyor (madde 12'nin kapsamı). ~115 ayar girdisi var; çeviri kararı kullanıcının.

## Gece nöbeti kapanışı (07:0x, pazar ertesi sabah)

Kuyruğun durum: (1) kapandı — tipografi üç koşuda sabit, tablo jurnale yazıldı; (2) keşfi
yazıldı, yazıcı A/B'si sonraki geceye kaldı; (3) README bilinen sınırlar bölümü ve
QUALITY-FACTORS tablosu yapıldı, satır sayıları 284/277; (4) site r3'ten yayınlandı ve
curl ile doğrulandı; (5) arXiv 2601.00135 koşuldu, denetimi kaydedildi.

Bilinen açık işler:
- kısaltma merdiveni istemle çözülmüyor — sonraki kol farklı bir istek *şekli* ya da yön bazlı MIN_SCALE;
- flattened için yazıcı-tarafı span font-size A/B'si (kuyruk 2'nin tasarımı, ölçülmeden kodlanmaz);
- Gutenberg EPUB koşusunun karşılaştırma sitesine EPUB girdisi olarak eklenmesi;
- koşucunun `--work` paylaşımı hatası — kaynak parçaların harmanlanması jurnalde kayıtlı.

### Düzeltildi: koşu artık kendi çalışma dizinini alıyor ve başkasının dizinini reddediyor

`translate_book.py`'nin `--work` varsayılanı paylaşılan `_artifacts/book` idi; bayrağı vermeyen her
koşu parçalarını oraya yazıyordu. Yeni bir 24 sayfalık makale o dizindeki **başka bir belgenin**
parçalarından kesildi, çevrildi ve başka bir belgenin metnini taşıyarak döndü - yarım saatlik model
süresi ve sessizce yanlış bir çıktı; yalnızca insan okuyunca fark edildi.

İki değişiklik:

- Varsayılan artık çıktıdan türetiliyor: `--work` verilmezse `<out>`'un yanında `<out-adı>_work`.
  İki koşu farklı çıktılar için yazdığı için asla aynı dizini paylaşamaz.
- Çalışma dizinine `input.txt` yazılıyor ve içinde parçaların hangi girdiden kesildiği duruyor.
  Dizin başka bir girdiyi gösteriyorsa koşu **başlamadan** duruyor ve iki yolu da söylüyor;
  bilerek kullanmak için `--force`.

Testler `tests/test_translate_book_work_dir.py` (6 test, model yok) ve koruma, geçici olarak kapatılıp
**kırmızı kanıtlandı** (`DID NOT RAISE SystemExit` - olayın kendisi). Gerçek CLI üzerinde de ölçüldü:
başka bir belgeyi işaret eden dizinle koşu, model çağrısı yapmadan
`refusing to reuse ... its chunks were cut from C:/baska/belge/paper.pdf, not .../tck_5237.pdf` diyerek
durdu.

---

## 2026-09-21 · Gece: sığdırma sürenin %56'sı, ve iki kolda ölçüm

**Kullanıcının kitabı bitti (70 dk 42 sn).** Kullanıcı zaman tablosunu ilk kez gördü ve dağılımı sordu:

| Aşama | Süre | Pay |
|---|---|---|
| read | 8 dk 10 sn | %12 |
| translate | 21 dk 18 sn | %30 |
| **fit (sığdırma)** | **~39 dk 30 sn** | **%56** |
| write | 40,5 sn | %1 |
| verify | 58 sn | %1 |

Sığdırma, çevirinin **iki katına yakın**. Sebebi de görüldü: sığmayan **her kutu için ayrı istek**
atılıyor (`worker.py` → `provider.translate([segment])`). Kullanıcı bunu LM Studio'da "aynı anda 1
istek" olarak izledi ve sordu.

**Yapılan:** `fit_pdf_pass`'e `fetch_many` eklendi — tur toplanır, tek istekte sorulur, ikinci geçiş
yanıtlarla sığdırır (D-010). Gece incelemesi bir hata buldu: toplama turu `on_fitted`'ı da çağırıp
yanlış ölçeği yazıyor, bayrak açıyor, `box_crushed`'ı iki kez sayıyordu — testle çivildi.

**Kullanıcının fikri (D-011):** karakter bütçesi **çeviriden önce** verilsin. Bulgu: `openai_compat.py`
zaten `max_len`'i gönderiyor ve "kısa yaz" diyor, ama değer yalnız sığdırma sırasında doluyordu — yani
talimat hiç ateşlenmiyordu. Artık `translation.prefit_budget` (kapalı / %120 paylı / tam kutu) ile
bölümlemeden sonra hesaplanıyor.

**A kolu (kontrol, 3 sayfa, yerel gemma):** toplam **19 dk 22 sn** — translate %25, **fit %60**,
verify %13. **B kolu (toplu + bütçe):** toplam **18 dk 04 sn** — fit **11:22 → 6:26 = −%43** ✓✓,
translate aynı ✓, bütçe 0,2 sn ✓. Ama toplam yalnız **−%6,8** ✗: kurtarma adımı B'de 7 segment (A'da 2)
ve o adım zamanlayıcıda yoktu → ~300 sn kör noktaydı; `recover` ve `unify` artık faz ✓.
**Kalite iki kolda da eşit ✓✓:** 13 ölçütün tamamı 0, `LOSSLESS YES`, bayraklı blok 29 ↔ 30 (1214 blok).

**Not ✗:** Tek koşuyla "toplam süre kısaldı" denmez ✓ — kurtarma sayısının koldan kola değişmesi
tekrar koşu gerektiriyor ✓; `prefit_budget` varsayılanı bu yüzden hâlâ kapalı ✓ (D-011).

**Kapak kusuru (D-012):** kullanıcı çıktıda orijinal kapak yazısının çevirinin altında kaldığını gördü.
Ölçüm: kaynağın 1. sayfasında **metin katmanı boş** (tek bir 700×866 görüntü) → kapak OCR'lanmış,
çeviri **resmin üstüne** çizilmiş; silinecek metin yoktu. Çözüm (uygulanacak): OCR kutusuna örneklenmiş
zemin dolgusu.

**agy (Antigravity CLI) kuruldu:** agy-staff v0.7.3 hem Claude Code'a hem Codex'e kuruldu ve enabled.
Hermes'e plugin gerekmiyor — beceriye personalar eklendi. Kota ölçümü: hesap
`legendnoobeoffical@gmail.com`, **Gemini grubu %0** (25 Eyl Cuma 14:46 UTC yenilenir), **Claude/GPT %97**;
yani 429 hatası kotanın gerçeği, arıza değil. `/usage` artık model çağırmadan okunabiliyor.

**Kural:** ağır GPU/CPU işleri 23:00'ten sonra başlatılmaz; gece kod okuma, optimizasyon ve kayıt işleri
yapılır. agy'nin bıraktığı izler (`.antigravitycli/`, `.gemini/`, `agy*.log`) `.gitignore`'da; ajan
proje içinde çalışır, izleri repoya girmez.

## 2026-09-22 öğleden sonra · DeepL ile ölçüm (kullanıcı isteği)

- **Düzenek**: `lk_prefit_ab.py` artık `LK_ARM_KIND=deepl` ile çalışıyor ✓ (anahtar Windows kimlik
  kasasından ✓, GPU hiç kullanılmıyor ✓). DeepL profili `base_url=""` istiyor ✗ — varsayılan
  bırakılınca LM Studio adresine bağlanmaya çalıştı ✗.
- **DeepL hatası bulundu ve düzeltildi (D-013)**: arXiv makalesinde bir segmentin kaynağı tek başına
  `\x08`'di ✗; XML ayrıştırıcısı yüzünden **tek bayt 40 segmentlik isteği** düşürüyordu ✗✗.
  `562d25d` + 2 test ✓.
- **Ölçüm (3 sayfa, arXiv 2609.19145)**:
  - **a** (tek tek istek, eski davranış): toplam **134,9 sn** — fit **81 sn (%60)** ✗, translate 4,0 sn,
    yazma 31,3 sn, kurtarma 3,9 sn, okuma 13,3 sn, **hata yok** ✓.
  - **b** (toplu istek): fit **6,5 sn (%12)** ✓✓ → **−%92** ✓ (yerel modelde aynı A/B −%43'tü).
  - b'nin tam sonucu kayboldu ✗ (durdurulan zincir kolun klasörünü temizlemişti ✗); fit/yazma/kurtarma
    sayıları koşu çıktısından alındı ✓.
- **Kota maliyeti** ✗✗: 3 sayfa ≈ **35k karakter** (17.987 kaynak + **17.157 bağlam** ✗) + tekrar
  istekler → tek kol ~40-50k ✗. Kullanıcının kotası 890k → **982k**'ya çıktı ✗ (17.691 kaldı ✗);
  koşu durduruldu ✓. **Karar: ağır ölçümler yerel modelle** ✓ (ücretsiz ✓); DeepL yalnız tek sayfalık
  son kontrol için ✓.
- **c/d/e kolları koşmadı** ✗ (kota ✗) — yerel modelle tamamlanacak ✓.

## 2026-09-22 gündüz (hafif iş · dışarıda)

- **04:05 koşusu neden üretmedi**: zincir çalıştı ✓ ama beş kol **0,3 sn**'de düştü ✗ — cron ortamı
  çocuk sürece Hermes'in `PYTHONPATH`'ini geçiriyor, venv (3.13) oradan 3.11 numpy'ını yüklüyor ✗
  (`_multiarray_umath.cp311-win_amd64.pyd`). Özet fonksiyonu da `phases` alanını sözlük varsayıyordu ✗
  (çöken kol `[]` yazıyor). İkisi de düzeltildi ✓ + zincire **ön kontrol** eklendi ✓
  (`preflight()`: venv sağlığı + betik varlığı; başarısızsa hiçbir kol başlamaz ✓).
- **Cron işleri düşme sebebi**: `config.yaml`'da `model.default` **ve** `cron.model` bayat dizeyi
  taşıyordu (`opencode-go/glm-5.3-flash` ✗ — TokenRouter listesinde böyle bir önek yok). TokenRouter
  bakiyesi de bitmiş ✗ (tüm modellerde "gift balance $0"). Çalışan yol bulundu ✓: `llmtr` +
  `qwen/qwen3.8-27b-free` (ücretsiz, canlı test "OK" ✓; eskisi 19 Eylül'de emekliye ayrılmış ✗).
  `cron.model` + `providers.llmtr.model` buna çevrildi ✓.
- **Sığdırma analizi (kod okuma)**: maliyet = **tur × sığmayan kutu** ✓. İki kol kodda hazır:
  toplu istek (`fetch_many`, ilk tur hepsini tek istekte sorar ✓, sonraki turlar tekil ✓) ve
  ön bütçe (`prefit_budget` ✓). İkisinin katkısı **ölçüm bekliyor** ✗ — gece koşusu yeniden
  zamanlanmalı ✓ (04:00-06:00 penceresi ✓).
- **Duraklatılmış gece nöbeti** (`dcadaafb6130`) kendi modelini taşıyor ✗ (`glm-5.3-flash`/`opencode-go`)
  — devam ettirilirse önce modeli düzeltilmeli veya iş yeniden kurulmalı ✓.
- **Exe**: durum hazır ✓ (ağaç temiz ✓, dünkü testler yeşil ✓); derleme ağır olduğu için (pil ✗)
  kullanıcı "başla" dediğinde koşulacak ✓ — öncesinde tam test paketi ✓.

## 2026-09-22 gece (00:00-04:00 hafif iş)

- **Kapak düzeltmesi (D-012)**: renkli panelde Otsu "koyu" kütleyi mürekkep sanıp zemini siliyordu;
  medyan doygunluk eşiği (120) eklendi. Kutu içi sarı piksel 20.369 → 3.960 (−%81), yazar satırı → 0.
  Eski kodla aynı kutu 44.436 (daha kötüydü). Kanıt: `51aee55`.
- **İç sayfa güvencesi** (kullanıcı uyarısı: "kapağı düzelteceğim diye sayfa çevirilerini bozma"):
  aynı kaynak + aynı hedef yazıyla iki kural karşılaştırıldı → sıradan kâğıt sayfada **0 piksel** fark.
  Testle çivilendi: `test_the_panel_rule_never_changes_a_paper_page`. Kanıt: `8a13d3b`, `a003c4a`.
- **Ayar penceresi**: kombo artık en uzun seçeneğe göre boyamıyor (ipucu 666 → 314); pencerenin
  gerçek tabanı **620**, açılışı 760×620 (1322 yalnız bilgi ipucuydu). Kanıt: `1d11c51`.
- **Okuma fazı**: 1201 sayfa / 8 dk = **0,4 sn/sayfa** → darboğaz değil. ONNX yerleşim dedektörü
  CPU-only (`docling-layout-heron-onnx`), GPU'ya dokunmuyor.
- **Ağır ölçüm**: `a/b/c/d/e` kolları **04:05**'te (cron `982752d2a607`), rapor **06:15** (`961cb9c99e0e`).
- **Zincir kilidi**: `lk_night_chain.py` yalnız `run` argümanıyla çalışır — gece yanlışlıkla
  çalıştırma olayı (fan sesi) BrainOS'a `mistake` olarak kaydedildi.
## Gece ölçüm zinciri — 5 kol (yerel gemma, 3 sayfa, aynı belge)

| kol | ne | süre | kalite |
|---|---|---|---|
| a | eski davranış (tek istek, bütçe yok) | faz kaydı yok ✗ | kayıpsız ✓ |
| b | toplu istek | **643 s** ✓ en hızlı | kayıpsız ✓ |
| c | toplu + bütçe (strict) | 956 s | kayıpsız ✓ |
| d | yalnız bütçe (strict) | 1158 s ✗ en yavaş | kayıpsız ✓ |
| e | toplu + konu haritası | 690 s ✓ (harita ≈ 47 s) | kayıpsız ✓ |

Beş kolun beşi de kayıpsız; bozuk ölçüt yok; bayrak listeleri boş. Sonuç: toplu istek en hızlı yol;
bütçe tek başına yavaşlatıyor (yeniden deneme maliyeti); konu haritası ~47 s ekliyor.
Not: kollarda `output.timing_report` açık olmadığı için faz kırılımı yok, yalnız toplam süreler var.
