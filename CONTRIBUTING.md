# Contributing to LayoutKeep

Thank you for looking. This file says how the project is built and what a change is expected to
carry with it, so that a pull request does not have to be a negotiation.

## The one rule everything else follows

**Run the thing.** A green test suite has hidden a broken product here more than once: the
figures were dropped, the flags were discarded, a feature was dead in the packaged build, and
every test passed through all of it. If a change is meant to alter what a user sees, the pull
request should say what was run and what came out.

## Setting up

Requires **Python 3.13** (3.11–3.13 supported; 3.14 breaks the OCR dependencies).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[pdf,epub,docx,ui,fitting,dev]"
```

## Before opening a pull request

```bash
.venv/Scripts/python -m ruff check src/ tests/ tools/
.venv/Scripts/python -m pytest -q
```

Both are what CI runs. The lint rules are stated in `pyproject.toml` rather than left to
whatever version of ruff you happen to have.

## What a change is expected to carry

- **A test that fails without it.** For a bug, the test should reproduce the bug; for a
  feature, it should describe the behaviour rather than the implementation.
- **A reason in the code.** Comments here explain *why*, not what — the code already says what.
  The bar is that a reader who has not seen the bug understands why the line is written that way.
- **Its own measurement, when it makes a claim about quality.** Numbers in this repository are
  reproducible: see `docs/MEASUREMENTS.md` for the format and the commands.

## Layout of the project

```
readers/ ──▶ DocIR ──▶ providers/ ──▶ fitting/ ──▶ writers/
```

Every reader produces DocIR; every writer consumes it; the translation layer never learns which
format the document came from. That contract, and the rules that follow from it, are in
[`docs/CONTRACT.md`](docs/CONTRACT.md) — worth reading before changing anything that crosses a
tier boundary.

## Reporting a bug

The most useful report has the document, or a small one that reproduces it. If the file is
private, a description of its structure (two columns, a scanned page, an EPUB with SVG-wrapped
figures) is usually enough to build a fixture.

Crash reports are written to `%APPDATA%\LayoutKeep\layoutkeep_crash.log` (Python errors) and
`layoutkeep_fault.log` (crashes inside Qt). Both are useful; neither contains document text.

## Licence

By contributing you agree that your contribution is licensed under the AGPL-3.0-or-later, the
same as the project.
