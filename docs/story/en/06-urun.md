# 6. From engine to product

An engine that is correct but unusable is not a finished project. This chapter describes the steps
from "a library" to "an application anyone can download and run", and which user complaint each step
was born from.

## 6.1 The welcome screen

**The complaint:** *"there should be a welcome and explanation screen on first launch: how to do a
first translation, what each setting is for, the local provider, and so on — quite detailed, with the
language and theme selectable right there."*

The welcome has four pages and opens on the **first run**:

1. **What it does** — it translates a document inside its own boxes; a three-sentence summary and the
   definition of "lossless".
2. **How to run it** — drag and drop, choosing a language, choosing a provider; local vs cloud.
3. **Which setting does what** — the arithmetic of the context window and slot count (7 workers + an
   8192 window = ~1.2k tokens per request), the fitting thresholds, protected values.
4. **Language and theme** — the interface language (TR/EN/DE) and the light/dark theme are chosen
   here.

The welcome is marked **per version**: a new version is a new welcome. (That is the permanent fix for
the "no welcome screen appeared" complaint — section 4.5.)

## 6.2 Help: the criteria, explained to the user

**The complaint:** *"there should be plenty of help and explanation so any user can work it out."*

The help screen has seven sections and explains **the engine's own criteria**: the first
translation, choosing a provider, what the settings mean, review flags (what each flag means), the
losslessness criteria (L1–L10 + D1–D3, with their names), where the outputs are (`.lkproj`, the
memory, the logs, portable mode), and troubleshooting.

The rule: help never promises something the code does not do. Every section describes a behaviour
that really works in that release — and when a behaviour changes, the help text changes with it
(visible in the release notes: when the default parallelism went 7→2, three separate texts were
updated).

## 6.3 The glossary and the memory, inside the interface

**The complaint:** *"where is the glossary?"* (section 4.6)

- **Glossary**: choose a file (JSON or CSV/TSV), **edit it as a table** inside the application (add
  and remove rows, load from a file, save as), and it is applied both in the prompt and in the output
  check. The glossary's fingerprint enters the memory key — when you change the glossary, old
  translations are not silently reused.
- **Memory**: SQLite, across runs. The completion screen shows the **hit rate**. A real run
  accumulated 2,555 segments; restarting the same document never calls the model for those.

## 6.4 The floating bar and the window switch

**The complaints:** *"the pill and the main window are visible at the same time, and hiding the big
window hides the small one — fix that"* + *"when I close the pill I cannot get it back."*

On long runs the window needs to be able to go to the back. The answer is a switch that works both
ways:

- The **▤ "switch to the small window"** button in the title hides the window and progress continues
  in the floating bar (it is enabled while a run is going).
- **"Back to the window"** on the bar brings it back; minimising the window does **not** hide the bar
  (the ownership relation was removed — section 4.7).
- The bar shows the progress percentage, the phase, the segment counters and the file name. If the
  name does not fit it is shortened, but the **full name stays in a tooltip** (a name you cannot
  verify is a name that does not help).

## 6.5 The page range does what it promises

**The complaint:** *"should it not output only the range I selected?"* (section 4.12)

When a range is chosen:

- **Translated**: only the selected pages.
- **Output**: only the selected pages (the writer is handed a slice of the source).
- **Project (`.lkproj`)**: the **whole** document — the review screen shows the rest too, and
  re-exporting never silently shortens the document.

The interface says what will happen the moment a range is chosen (TR/EN/DE). This behaviour is
pinned by 11 tests and was measured on a real 15-page corpus PDF: the range "1-2" → a 2-page output,
a 15-page project.

## 6.6 The bilingual PDF

**What was asked for:** the comparison site shows source and translation side by side, but the PDF
output does not.

`--dual side|alternate` (and a checkbox in the interface): `side` puts the source on the left and the
translation on the right of every page (the page width doubles), `alternate` puts the translation
after every source page (the page count doubles). The design decision was **not to touch the
pipeline**: the composition is done afterwards, from two finished files, because the audit pairs
source page N with output page N and a bilingual document would break that pairing. So the translated
PDF and `audit.json` stay exactly as they were; the bilingual file is written beside them. On an
interrupted run only the pages both documents have are composed, and the count is reported. The plan
and the measurement: `docs/DUAL-OUTPUT-PLAN.md`.

## 6.7 The glossary: term candidates from the document

**Roadmap item 5.** The glossary is the pipeline's strongest quality lever (a term is forced in the
prompt and checked in the output), but filling it by hand means reading the document and noticing the
repeats — a machine's job. `core/terms.py` finds the phrases that **recur** in the document: one to
three words, not starting or ending with a function word, appearing at least N times, not a number.
The ranking is frequency × length.

This is a **frequency rule**, not an understanding of meaning — the docstring says so plainly. The
result is a list that opens in the editor with **empty target cells**; a human writes the
translations, and nothing enters a run until the user saves. A term already in the glossary is not
suggested. 9 tests; two of them talk to the editor over a real PDF page.

## 6.8 Setting presets

The settings screen shows thirty values; the honest answer to "which should I change for a quick
draft" is "the few that carry meaning together". There are two presets:

| Preset | What changes | Who it is for |
|---|---|---|
| **Fast draft** | 7 parallel requests, readability floor 0.80, shorter-rendering requests off | A first pass to read; type shrinks in tight boxes |
| **Publication quality** | 2 requests, floor 0.85, shortening threshold 0.95 (the measured defaults) | An output worth keeping; a short rendering costs one extra model round |

The values are written through the same validated path and the editors update immediately;
`current()` names a preset only when **every** value matches, and says "custom" when one was edited
by hand. The default installation already is "publication quality". The interface note says plainly
that chunked command-line jobs re-read the values on every new chunk.

## 6.9 Releases and the publishing flow

The application is published as a **single file** (`LayoutKeep.exe`, ~173 MB, onefile) through GitHub
Releases. The flow:

1. The version in `pyproject.toml` + `__init__.py` is raised.
2. It is built with `PyInstaller packaging/layoutkeep_onefile.spec --noconfirm --clean`.
3. The full test suite runs.
4. Tag + release; **the downloaded file's SHA-256 is compared against the local build**.

The published versions and what each brought:

| Version | What it brought |
|---|---|
| 0.9.1 | The first public release: welcome, help, the glossary/memory interface, the review queue |
| 0.9.2 | The bar ↔ window switch; the welcome per version; Roman-numeral protection (a toggle) |
| 0.9.3 | The ▤ button + help texts |
| 0.9.4 | **The application sends its requests in parallel** (in waves, merged in document order) |
| 0.9.5 | The dead setting key wired; the parallelism default down to 2; the bar's tooltip; a range narrows the output |
| 0.9.6 | **The packaged application can open its own dialogs** — 0.9.5 raised `ImportError` on the help and glossary screens because `help_dialog` and `glossary_dialog` were missing from the PyInstaller list (found by the project's own `check_spec.py`; three modules had been missing for several releases) |
| 0.9.7 | The completion screen tells two kinds of review flag apart: how many are **shortened boxes** (a page-layout problem, which re-translating cannot fix). The help screen explains what a flag means |

## 6.10 The comparison site

**What was asked for:** *"a slider web site where I can compare the original sources and their
translations side by side, for every example."*

The site is generated under `docs/comparison/` and published on GitHub Pages:

- **A single-document viewer**: original on the left, translation on the right, a draggable divider in
  the middle; zoom with the wheel; page navigation with the keyboard.
- **An audit summary per document**: the L and D numbers, the page count, the model, the date.
- **24 documents**: arXiv papers, the NIST journal and form, IRS forms, a NASA report (digital and
  scanned), Project Gutenberg books, a public-domain DOCX, two scanned pages.
- **Development runs** are hidden by default and one checkbox away — the published list is made of
  real documents.
- **The copyright rule**: only openly licensed or public-domain sources are published; copyrighted
  ones (`NOT_PUBLISHABLE`) stay on the user's disk only.

Images load per document (lazily): the whole archive is ~49 MB, which means ~1 MB of traffic per
visitor. The NASA document's 6997×3163 renders were capped at 3200px (10.4 MB → 1.9 MB) — more than
enough for zooming, and half the data per document.

## 6.11 GitHub Pages: the landing page and the links

- **The root** (`/LayoutKeep/`): the landing page — the download, the comparison site and the story.
- **`/docs/comparison/`**: the comparison site.
- **`/docs/story/`**: this document (multi-page), **in three languages** with a switcher; a chapter
  without a translation yet shows the Turkish original behind a visible note.
- **The old address** (`docs/comparison.html`): the old 4.4 MB single-file page, turned into a
  **redirect** so shared links do not break.
- **The READMEs** (EN/TR): the download link goes through `releases/latest`; the showcase buttons
  point at the current site; the "where the code in this branch stands" note is permanent in both
  languages (a push once deleted it; it was put back and is now kept on both sides).

## 6.12 Scale: today's numbers

| | Value |
|---|---|
| Source code | ~24,000 lines (`src/`), 133 files |
| Tests | **1,256 tests**, 138 test files |
| Audit tools | 56 (`tools/audit/`) |
| Largest real run | a 220-page book, 55 chunks, ~106 minutes |
| Largest single document | 841 pages (when fully translated, ~23% in one run) |
| Comparison site | 24 documents, 288 images |
| Settings | 30, all wired to code and tested |
