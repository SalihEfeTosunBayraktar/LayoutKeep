# Changelog

All notable changes to LayoutKeep. Dates are the day the work landed on the release branch.

## Unreleased — 2026-09-22/23 (after 0.9.10)

Measured on a fixed bench (`tools/audit/bench.py`, 21 sources × 3 pages, both directions) with three
bars per direction: quality (MQM judge), term consistency, and layout (share of blocks drawn intact).
Quality is above 90 in both directions; layout rose from 80.1% / 73.6% to 90.8% / 90.8%
(EN→TR / TR→EN). Consistency is still being measured.

### Translation quality
- An automatic document glossary (`translation.auto_glossary`, off by default): the document's
  recurring terms are rendered once and enforced and checked in every segment.
- A glossary term counts as honoured when inflected, capitalised or with a softened final consonant.
- Grammar (Turkish postpositions, function words) is no longer offered as a term.
- A block cut mid-sentence is translated as the fragment it is, never completed or trimmed.
- Paths, repository names and e-mail addresses are protected; paragraph and list numbers
  (`(1)`, `(b)`, `4.Text`) survive the model dropping them.
- Academic reference lists can be kept untranslated from the application too
  (`translation.preserve_references`).

### Layout
- A line may use the blank paper beside it, not only the space below (`write.grant_room_right_pt`).
- Unchanged blocks (names, codes) are no longer fitted, shrunk and flagged.
- Inline markers are no longer measured as drawn glyphs.
- A Word PDF's leftover lines form one block per run; whitespace-only lines join none.
- Two lines are not enough to call a block justified; titles are no longer stretched.
- Restored form XObjects are matched by their box (a badge and an ORCID icon were destroyed).
- A source font subset is reused only when it holds every letter the translation draws
  (English w/q/x were drawn from another face).

### Product
- Every translated file records what translated it: version, commit, model, settings
  (`core/provenance.py`); `docs/campaign/RUNS.md` lists every run on disk.
- The command line reads the stored settings, as the application does (D-020).
- Every interface text follows the chosen language (tr/en/de), settings included.
- The desktop run checks glossary terms in the output; the CLI's memory key carries the glossary.

## 0.9.0 — 2026-09-10

The first published build, and it does one thing.

- **Only PDF to PDF is enabled.** Every format pair was measured with an identity translation
  (`tools/audit/format_matrix.py`). None of them fail; five of them return a document quietly
  missing its images, its emphasis or a third of its words. Those are locked in the interface
  with a padlock and the reason, rather than removed or offered.
  `docs/ENGINE-ARCHITECTURE.md` is the measurement and the plan.
- `core/capabilities.py` is the single place that decides, read by both the application and the
  command line, so they cannot disagree about what is ready. `docs/CONTRACT.md` D7 makes it a
  rule: a conversion is offered only when it has been measured.
- The version was 1.0.0 before this. A build that deliberately does one conversion is not a 1.0,
  so it is 0.9.0 and the release is marked as a pre-release.

### Earlier work, previously listed as 1.0.0 — 2026-09-09

The first release. A desktop application and a CLI that translate a document and hand back the
same document, with readers and writers for PDF, EPUB, DOCX, HTML and images. A desktop application and a CLI that translate a document and hand back the
same document, with readers and writers for PDF, EPUB, DOCX, HTML and images.

### Translation

- **DocIR** as the single intermediate representation: every reader produces it, every writer
  consumes it, and the translation layer never learns which format it came from
  (`docs/CONTRACT.md`).
- **Protected values.** Torque figures, tolerances, part numbers and form identifiers are
  replaced with tokens before the model sees them and restored from the source afterwards — a
  model cannot paraphrase what was never in its prompt.
- **Inline styling** carried through translation as markers, so a bold run in the middle of a
  sentence survives it.
- **Adaptive batching** that finds the model's real ceiling instead of assuming one, and a
  per-batch timeout computed from the measured rate rather than a fixed guess.
- **Providers:** any OpenAI-compatible endpoint (LM Studio, Ollama, llama.cpp, cloud), DeepL, and
  a clearly-labelled test provider that does not translate.
- **Review flags** with a reason on the segment — passthrough, missing protected values, lost
  styling, text that would not fit — written to the project file and counted by the CLI.

### Layout

- Original PDFs are edited in place, so figures and vector art are untouched.
- Font substitution by real metrics and glyph coverage when the embedded font cannot draw the
  target language.
- Rotated text at any angle; mirrored text detected and flagged rather than silently corrected.
- Fitting engine that shrinks, then reports rather than overflowing in silence.

### Application

- Three steps and no fourth: document, translation, done — with the output openable from the
  completion screen.
- **Provider endpoints** managed as a list: dragged to reorder, dropped onto one another to make
  a group, renamed and deleted from the right-click menu, and tested without saving. The test
  asks each provider the question it can answer — a model list, DeepL's remaining quota, nothing
  at all for the test provider.
- **Tunable settings** applied without a restart, with the ones that quietly worsen output kept
  in a separate section, each carrying what goes wrong rather than a warning to be careful.
- English by default, with Turkish and German in the header; the choice is remembered.
- Portable mode: `portable.txt` beside the executable keeps settings and crash reports with it
  and leaves nothing on the host machine.
- Crash reports for Python errors, and native stacks for anything that dies inside Qt.

### Known at release

See `docs/ENGINE-ARCHITECTURE.md` for what was verified before release and what is still open, with
evidence for each. The largest open defect is table structure: cells on one line are read as a
single block, so a translated table loses its rows even though its numbers survive.
