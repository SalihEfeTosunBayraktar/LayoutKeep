# 4. The bug catalogue: sixteen cases, from symptom to test

This chapter is the project's memory. Every case is written in the same shape: **symptom** (who
noticed, and how), **investigation** (which measurement was made), **root cause** (where in the code,
and why it was written that way), **fix** (what changed), **evidence** (which test or measurement).
Deliberately not in chronological order, but in order of importance.

## 4.1 "Model not found" — the error message was lying

**Symptom.** The model was loaded in LM Studio and the application said "Model not found". The model
was swapped, the server restarted, nothing helped.

**Investigation.** The provider response's **body** was opened (the first attempt only looked at the
HTTP status code). The body said: `Context size has been exceeded`.

**Root cause.** Two settings were eating each other: LM Studio ran with `-c 8192` (an 8K context)
and the application sent **7 parallel requests**. The context window is **divided** across the
slots — 7 workers on an 8192 window get ~1.2k tokens per request and a long paragraph exceeds it.
The server rejected the overflowing request with "context exceeded"; the provider layer wrapped that
as "model not found".

**Fix.** Three layers: (a) the error body is read and the message tells the truth, (b) an overflow is
no longer fatal — the chunk is cut at a sentence boundary and asked again, (c) the help and welcome
screens spell out the arithmetic: *"the context window is divided across the slots; for 7 workers
`-c 32768` is recommended"*.

**Evidence.** `tests/test_providers_*` for the error-body parsing; the book run completed 220 pages
at 32768. This case is also the reason **the default parallelism came down to 2** (section 4.10).

## 4.2 The floating bar: a heap corruption (0xc0000374)

**Symptom.** On long runs the application closed abruptly; the Windows event log showed
`0xc0000374` (heap corruption).

**Investigation.** The crash happened with the floating progress bar open. The bar is a window
independent of the main one; a drag helper (`WindowDrag`) held the window.

**Root cause.** The `WindowDrag` object was kept only in a local variable; when Python collected it,
the Qt-side signal connections still pointed at it — the C++ side was touching a freed Python
object. The classic "who owns this" bug.

**Fix.** The drag helper is bound to the window with a **strong reference**
(`self._drag = WindowDrag(...)`) — the object lives with the window and dies with it.

**Evidence.** `tests/test_ui_floating_progress.py` (11 tests) + the bar can now stay open through an
entire book run.

## 4.3 The same text was being translated over and over

**Symptom.** In a long document the same sentence (a form label, a heading) went to the model dozens
of times; the run was needlessly slow and the same text could come back with **different**
translations.

**Investigation.** On the IRS form a single label had more than 40 repeats. The request log showed
each repeat as a separate request.

**Root cause.** The pipeline translated every block independently; "repeat" was not a concept.

**Fix.** `providers/dedupe.py`: the same source text is translated once and the result is handed to
every repeat (switchable with `--no-repeats`). In addition, `core/repeats.py` aligns **differing**
translations to the majority — so "Chapter" does not stay "Bölüm" in one place and "Kısım" in
another.

**Evidence.** `tests/test_providers_dedupe.py`, `tests/test_core_repeats.py`; on the IRS run the
request count dropped noticeably and terminology consistency improved.

## 4.4 Broken and shrunk lines — and a fix that was measured and taken back out

**Symptom.** The user reported that lines were breaking in the output pages and that some blocks
were shrunk far more than necessary.

**Investigation.** The hypothesis was "if the block's box is widened, lines will not break". The box
was widened: the number of broken lines went **12 → 12** (no change at all). The hypothesis was
refuted by measurement.

**Root cause.** The real cause was in the fitting ladder: when a translation did not fit, the block
was shrunk immediately — although it first had the right to **ask for a shorter rendering** (a
shorter translation from the model).

**Fix.** The fitting order was rearranged: shrink → ask for shorter → push down → flag. The widening
attempt was **reverted** with its reason written into the code (an unproven fix is not kept).

**Evidence.** `type_drift`'s "unreadable size" count on the IRS form went 14 → 2; for the broken
lines, `tests/test_pdf_writer_widen.py` documents the revert.

## 4.5 The welcome screen did not appear (because of my own verification runs)

**Symptom.** The user: "in the new 9.1 exe no welcome screen came up at all."

**Investigation.** The settings registry showed `welcome_shown = true`. Who wrote that? **My own
automated runs** that test the welcome screen — they did not put the flag back when they finished.

**Root cause.** The welcome was shown once and then marked; the tests and the real user shared the
same flag. On top of that, a user downloading a new version had no way to see what had changed.

**Fix.** Two changes: (a) automated tests run with the `LAYOUTKEEP_NO_WELCOME` escape hatch, (b) the
welcome is now marked **per version** — a new version is a new welcome, so the user sees what
changed on first launch.

**Evidence.** `tests/test_ui_welcome*.py` + `welcome_shown_version = 0.9.3` in the registry.

## 4.6 The glossary and the memory existed only on the command line

**Symptom.** The user heard about the glossary (forcing terms) and the translation memory and could
not find them in the interface: "where is the glossary?"

**Investigation.** A code scan: `providers/glossary.py` and `providers/memory.py` existed, had tests,
and were **not called from the interface**. For a user there is no difference between "a feature that
does not exist" and "a feature you cannot see".

**Root cause.** The features were added at the engine layer, the interface wiring was left for later,
and later never came.

**Fix.** Both were wired to the interface: a glossary file (JSON **or** CSV/TSV) can be chosen and
**edited as a table inside the application** (add/remove rows, load from a file, save as), the
glossary's fingerprint enters the memory key (changing the glossary invalidates old translations),
and the completion screen shows the memory hit count.

**Evidence.** `tests/test_ui_glossary*.py`, `tests/test_ui_settings_memory*.py`.

## 4.7 The floating bar was holding the main window hostage

**Symptom.** The user: "when I close the pill I cannot get it back" + "the pill and the main window
are visible at the same time".

**Investigation.** The bar was an **owned** window of the main one: minimising the main window hid
the bar too, but once the bar was closed there was no way to bring it back.

**Root cause.** The ownership relationship was set up wrongly: the bar should live independently of
the main window but appear **together** with it, and the switch had to work both ways.

**Fix.** The bar was taken out of the ownership relation; a **▤ "switch to the small window"** button
was added to the title (enabled while a run is going) and "back to the window" returns from the bar.
Minimising the window no longer hides the bar.

**Evidence.** 7 tests (`tests/test_ui_floating_pairing.py`), the v0.9.2/v0.9.3 release notes.

## 4.8 The application was sending its requests one at a time

**Symptom (user).** *"even with 7 slots configured it only sends 1 slot at a time, this must be a
bug."*

**Investigation.** Two paths were compared: the command line (`translate_book.py`) translated chunks
in parallel with a `ThreadPoolExecutor`; the application's worker (`ui/worker.py`) sent requests
**one by one**. So the 7-slot setting only did anything on the command line — book runs were fast,
application runs were slow.

**Root cause.** The parallelism feature was added to the CLI and never carried into the interface's
translation loop. (This is 4.6's sibling: an engine capability that the interface does not have.)

**Fix.** The loop was written to work in **waves**: each wave runs `translation.workers` batches in
parallel, pause/cancel is checked at the end of a wave, and the results are merged **in document
order** (not in the order they happened to finish). Each parallel piece of work gets its own provider
chain — sharing the dedupe cache and the memory connection would have been a race. The loop moved
from `worker.py` into `ui/translation_loop.py` (one responsibility per file).

**Evidence.** `tests/test_ui_translation_parallel.py`: (a) concurrency really is greater than 1,
(b) a single worker stays sequential, (c) the output is in document order. The suite is green.

## 4.9 OCR noise is not silent

**Symptom.** On the NASA scan a decorative heading was read as "Naga Merorautigs Frogrom Amerika".

**Investigation.** The OCR confidence for that block was 0.62 (the threshold is 0.75).

**Root cause.** Noise is in OCR's nature; the problem would not have been the noise but the
**silence**.

**Fix.** Low-confidence blocks are written to the output but land in the review queue with the reason
**"low OCR confidence (0.62)"**. The user knows what is doubtful.

**Evidence.** `tests/test_ocr_confidence*.py`; the journal entry (2026-09-20).

## 4.10 The default parallelism was too aggressive

**Symptom (user).** *"the default parallelism can be 1 or 2."*

**Investigation.** The arithmetic of 4.1: on a single local GPU, 7 concurrent requests share the
context window, tokens per request drop, and on small models the risk of quality loss and overflow
rises.

**Fix.** `translation.workers` defaults to **2** (it was 7). On a server with enough slots (LM Studio
`-c 32768 --parallel 7`) the user raises it; the setting's warning text says so. The command-line
tools' fallback constant was brought to 2 as well, so there is one story.

**Evidence.** `tests/test_parallel_workers.py` + `tests/test_core_tunables_wired.py`.

## 4.11 The dead key in the settings screen

**Symptom (user).** *"find the settings that are not wired to the interface and wire them."*

**Investigation.** The keys of all 30 declared settings were compared against the keys read anywhere
in `src/` (a static scan, plus the constant names settings are read through). Result: **one** dead
key — `timeout.first_batch_s`: it appeared in the settings screen, it saved, and **nothing read it**
(the first batch's timeout came from a constant). The screen showing 30/30 was measured as well.

**Fix.** The key was wired to the worker (a cold model's first answer can take minutes; that is this
machine's property, not the code's). Five tests were added: *every declared setting must be read*,
the first-batch timeout reaches the timeout, a warm batch is unaffected by it, the default is 2, and
the settings screen shows every declared setting.

**Lesson.** A key that does nothing is worse than a key that does not exist — it spends the trust in
the ones that work.

## 4.12 The page range did not narrow the output

**Symptom (user).** A range was chosen in the 841-page book; the output was still **the whole book**:
*"but should it not output only the range I selected, why did it give the whole book."*

**Investigation.** The output PDF: 841 pages, 194 of them in Turkish (23% — the selected range), the
rest in English. The engine applied the range **to the translation only**; the output was a copy of
the entire source.

**Root cause 1 (historical).** This had been a deliberate, written decision: a range had once been
applied by **deleting** pages from the document, and when the project kept only the selected pages
the review was lost and re-exporting was silently shortened (CONTRACT.md, D5). The right fix was to
**split the range in two**: apply it to the written copy, keep every page in the saved project.

**Root cause 2 (found by measuring).** The first attempt — dropping pages from the document — was not
enough: the output still came out 841 pages, because the PDF writer draws pages **from the source
file**. The writer was handed a **slice** of the source; the pages in the slice were renumbered 0..n
so verification compares page N with N, while the project keeps the original numbers (by copying the
pages — mutating shared objects in place would corrupt the project).

**Fix.** `_output_document` + `_source_slice`; the interface says what a range will do (RANGE_HINT,
tr/en/de). **Evidence:** 11 new tests plus the old D5 test converted to the new contract — on a real
15-page corpus PDF, the range "1-2" produced a 2-page output and a 15-page project.

## 4.13 Justified paragraphs came out flush left

**Symptom (user).** *"number and heading alignments are lost in the translations."*

**Investigation.** `type_drift` flagged 4 body paragraphs on arXiv 19113 as `right → left`. Line by
line, the source was justified (every line 72→540, last line short) and the output was flush left
with a ragged right edge.

**Root cause.** The writer draws blocks as HTML boxes, where `text-align: justify` was already
supported; what was missing was **the reader never producing "justify"** (only left/right/center).

**Fix.** A three-condition rule: straight left edges, a short last line, and the last line's **left
edge** level with the body. The third is critical — a centred heading's lines shorten too, but its
last line starts in the middle; without that condition the NASA cover heading drifted off centre (a
test caught it).

**Evidence.** 19 alignment tests plus 218 reader/layout tests; two old tests converted to the new
contract, four new ones added. **Verified in a real run (same day):** on the first re-translated
chunks of the 220-page book, the reader read **26 of 70** long body blocks as "justify" and
`type_drift`'s alignment flag came out **0** (before the fix the same measurement gave 4 flags on
arXiv). The decision carried from the reader to the writer, and from the writer to the drawn page.

## 4.14 Folder hygiene: copyrighted page images in the repository

**Symptom (a user criterion).** *"publish the openly licensed content on GitHub, keep the rest
local."*

**Investigation.** A scan of tracked files: `tests/layout_eval/` held 62 JPEGs; two of them were
pages of a copyrighted textbook (`computer-systems-Architecture.pdf`), one was a personal scan
(`Notes_...`), plus a `run.log`. The tracked repository totalled **36 MB**.

**Fix.** The copyrighted and personal images were **untracked** (the files stayed on disk, with a
note in their README that they were removed from publication for copyright reasons and can be
regenerated with the commands). Public-domain NASA images stayed. `.gitignore` rules were added. A
second pass removed zooms in a nested folder (missed by the first scan). **Tracked repository:
36 MB → 12 MB.**

**Lesson.** The first scan was not enough; the glob did not reach subdirectories. Scanning again was
not "needless fussiness" but part of a finished job.

## 4.15 Measurement and drawing used different line heights (a sleeping bug)

**Symptom.** None — the bug was asleep. It was noticed while adding a "tighten the leading" step to
the fitting ladder.

**Investigation.** `fitting/measure.py` **reads** `style.line_height` when deciding whether a text
fits its box; `pdf_writer`'s CSS **never wrote** that field. So a block with a named line height
would be *measured* at that height and *drawn* at the engine's own. The only reason it is invisible
today: readers never fill the field (`None`), so both sides fall back to their defaults.

**Why it matters now.** In the book's first 12 finished chunks the largest review-flag class was
"the translation did not fit its box, shrinking was not enough" (352 of 6,570 blocks). The step that
would melt that class — tightening the leading — uses exactly this field; without closing the
mismatch that step would measure wrongly.

**Fix.** `_css_for_block` writes `line-height: ...pt` when the block's style has one. Three tests:
does the measurement see the field (noting that testing it with a short text passes wrongly — a
single-line text "fits" at any leading), does the CSS carry the field, and is the CSS left alone when
the field is empty (so the engine's calibrated default is not overridden for every paragraph).

## 4.16 The packaged application could not open its own help screen

**Symptom.** None — nobody had noticed. The project's own spec audit
(`tools/audit/check_spec.py`) found it: **six** modules were missing from the list PyInstaller packs.

**Investigation.** `check_spec.py` runs the static analysis and compares it against the spec's
`hiddenimports` list. Missing: `ui.help_dialog` and `ui.glossary_dialog` (both opened from a menu
handler, which static analysis does not see), `fitting.figures`, and the three modules added in
0.9.5 — `core.terms`, `core.profiles`, `writers.dual_pdf` (all three imported inside the functions
that use them).

**Why it was serious.** Three of them had been missing for **several releases**: in the published
exe, a user touching the help screen or the glossary editor would get an `ImportError`. The tests ran
from source, so they were green; the screenshots came from source too. It is the "two doors" lesson
in a third form: **the source tree and the package are two different products.**

**Fix.** The six modules were added to the spec; the audit now says "every lazy import is reachable,
no stale names". The release was rebuilt as 0.9.6 and published.

**Lesson.** The packaged product's path is not the source tree's path. `check_spec.py` exists for
that reason — and an audit tool proves its worth when it finds a bug nobody complained about.
