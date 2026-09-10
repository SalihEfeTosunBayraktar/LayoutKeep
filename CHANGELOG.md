# Changelog

All notable changes to LayoutKeep. Dates are the day the work landed on the release branch.

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
