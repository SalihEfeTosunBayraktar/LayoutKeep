# LayoutKeep — the contract (binding on everyone working on this project)

The invariants every contributor works to. Read it before writing code. Where this document and
an opinion disagree, this document wins; where this document and a measurement disagree, fix the
document and say what the measurement was.

---

## 1. What this project is

| | |
|---|---|
| Name | LayoutKeep |
| Purpose | Translate documents, e-books and images **keeping their layout, fonts, colour and styling** |
| Licence | **AGPL-3.0-or-later** |
| Platforms | Windows / macOS / Linux |
| Phase 1 scope | **Latin script only** (TR, EN, DE, FR, ES, IT, PT, NL, PL…) |
| Interface | PySide6 |
| Python | **3.13** (3.14 wheels are not dependable yet — do not use a system 3.14, make a venv) |

---

## 2. Architectural invariants — not open for debate

### D1 — DocIR is the single source of truth
Every reader in `readers/` turns its input into **DocIR**. Every writer in `writers/` produces
its output from DocIR and nothing else. A reader and a writer never know about each other.
Adding a format means adding one reader and one writer; the core does not change.

### D2 — The translation layer knows nothing about layout
`providers/` only knows `list[Segment] -> list[Segment]`. It has no concept of a font, a bounding
box or a PDF. That is what makes changing provider a one-line job.

### D3 — Fitting is a separate stage, after translation
`fitting/` takes the translated text and fits it to its box. The provider does not think about
fitting; it receives a `max_len` hint, and `fitting` may ask for a **shorter translation** when
it needs one.

### D4 — Latin-only, but ready for RTL
`Span.direction` exists **now** and is pinned to `"ltr"`. No code anywhere hard-codes the
assumption of left-to-right — logic like "text starts at the left" reads `direction` instead.
RTL is not implemented, but the architecture does not shut it out.

**Scope, confirmed by the project owner (2026-09-02):** Latin only. RTL and CJK are **out of
scope** — no need to ask; just leave the architecture able to accept them.

**But direction is not orientation.** Latin text can be tilted, vertical, upside down or
mirrored, and real documents are full of it. `Block.rotation` is for that. Two distinct things:

- **Rotation** — derived from the flow direction vector (`line["dir"]`), carried as an angle.
- **Mirroring** — the transform matrix has a negative determinant. The direction vector
  **cannot show this**: a mirrored line reports a perfectly ordinary angle and renders
  backwards. Writing it back from the angle alone silently "corrects" the text and destroys the
  layout.

Even where mirroring cannot be reproduced, **detecting it and setting `needs_review`** beats
silently correcting it. Handing someone a wrong document that looks right is the worst outcome
this project can produce.

**Status: detected.** This was recorded for a long time as "the direction vector cannot show the
determinant, therefore mirroring cannot be detected". The first half is true and the second was
not. The vector cannot carry it, but the glyphs can: in a pure rotation a glyph extends from its
baseline origin towards `dir` turned a quarter turn; mirroring flips that side without touching
`dir`. Measured at 0/45/90/180/270 degrees, mirrored and not — the projection came out +0.65 in
ten upright cases and −0.65 in ten mirrored ones. No threshold to tune; the sign is enough. See
`readers/pdf_reader.py:_span_is_mirrored`.

### D5 — Everything must be resumable
A job's state is written to disk as `.lkproj` (JSON). Close the application and reopen it and the
work continues; a translation can be corrected by hand and the document rebuilt. **Do not write
a one-shot, stateless pipeline.**

### D6 — Translation quality is tracked with segment flags
There is no goal of 100% automatic correctness. Every segment carries `confidence` and
`needs_review`, and those flags do real work inside the engine: the fitting engine marks a
segment that overflowed, the passthrough check flags a literal it caught, the CLI's score table
counts them. **The correction editor was removed** (2026-09): the application flow is
1. Document → 2. Translation → 3. Done (open the output / show it in the folder / start another).
Flags are still written to `.lkproj`; there is no separate correction screen in the interface.

### D7 — A conversion is offered only when it has been measured
A format pair is enabled when the evidence says it holds up, and locked otherwise — visible, with
a lock and one sentence saying what it would cost. `core/capabilities.py` is the one place that
decides, and both the interface and the command line read it, so they cannot drift apart.
`docs/ENGINE-ARCHITECTURE.md` holds the measurements and
`tools/audit/format_matrix.py` reproduces them.

---

## 3. Directory ownership — the rule that prevents collisions

**Write only in your own directory.** If a change is needed elsewhere, do not write it; report it.

| Directory | Owner |
|---|---|
| `src/layoutkeep/core/` | Lead — DocIR and the shared types |
| `readers/pdf_reader.py`, `writers/pdf_writer.py` | `lk-pdf` |
| `readers/epub_reader.py`, `writers/epub_writer.py` | `lk-epub` |
| `src/layoutkeep/providers/` | `lk-provider` |
| `src/layoutkeep/fitting/` | `lk-fitting` |
| `src/layoutkeep/ui/` | `lk-ui` |
| `tests/` | `lk-verify` (others may write their own tests, `lk-verify` audits them) |
| `docs/` | Lead |

`core/` is **not modified by any sub-agent.** A schema change is a request to the lead.

---

## 4. Coding rules

- Code, commit messages and in-code comments are **English**. Reports to the project owner are
  **Turkish**.
- Type hints are required. `from __future__ import annotations` in every file.
- Core modules (`core/`, `fitting/`, `providers/`) **import no heavy dependency** — PyMuPDF
  appears only in `readers/pdf_reader.py` and `writers/pdf_writer.py`. That is what keeps them
  testable and leaves the door open to changing engine later.
- No unrequested abstraction. Do not write a factory, a registry or a plugin system for code
  with one caller.
- Match the surrounding style. Do not "improve" unrelated code. If you find dead code,
  **report it, do not delete it** — unless your own change is what orphaned it.
- Every changed line must be traceable to the task that was asked for.

## 5. The verification rule

Before saying "done", **run it and show the output**. If there is no test, write one. A claim of
"it works" without output is not accepted. Never report a failing test as passing — if it fails,
say so and show it.

## 6. Forbidden

- DRM circumvention, in any form.
- Changing the `core/` schema without asking.
- Bringing a heavy dependency (torch, paddle) into Phase 1.
- Writing an API key to a plain-text file — the OS keychain (`keyring`) is used.
