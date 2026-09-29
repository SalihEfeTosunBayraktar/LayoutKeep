# Where everything is

The shape of the repository and what each part is responsible for. All paths are relative to the
repository root.

---

## The tree

```
LayoutKeep/
├── _artifacts/           Everything generated (not in git, safe to delete)
│   ├── corpus/           Test corpus: arXiv, Gutenberg, official-form PDFs
│   ├── input/            Test inputs (EPUB/PDF fixtures built by code)
│   ├── output/           Test outputs, comparisons, .lkproj files
│   ├── e2e/              End-to-end manual test inputs and their .out.* results
│   ├── reports/          Test, lint and demo reports
│   ├── unpacked/         Unpacked EPUB inputs, for reading the XHTML directly
│   ├── heldout/          The held-out campaign: sources/, runs/, live/ and its scripts -
│   │                     what "lossless" is measured against (docs/campaign/HELDOUT.md)
│   └── gemini_v2/        Artefacts of the abandoned V2 clone, kept out of the tree
├── build/  dist/         PyInstaller intermediate output and the built exe (not in git)
├── docs/                 Architecture, measurements and usage
│   ├── CONTRACT.md       The architectural rules, binding on everyone
│   ├── ENGINE-ARCHITECTURE.md  Which conversions work, measured, and what to build next
│   ├── BENCHMARK.md      What a translation costs, stage by stage
│   ├── MEASUREMENTS.md   Older measurement results
│   ├── PACKAGING.md      Building the exe
│   ├── MAP.md            (this file)
│   ├── comparison/       The published side-by-side site: every held-out sample, original
│   │                     against translation, with audits (tools/audit/comparison_site.py)
│   ├── comparison.html   Redirect to it, for links shared before the site existed
│   ├── KAYIPSIZ_MOD_DURUM.md  What lossless mode does today, measured, in Turkish
│   ├── campaign/         The held-out campaign: HELDOUT.md (the runs) and JOURNAL.md (the log)
│   ├── notes/            Working notes, in Turkish, for work that is not current
│   └── mockups/          Logo and interface mockups, dark and light
├── packaging/            PyInstaller spec files
├── src/layoutkeep/       The application (below)
├── tests/                The pytest suite and its fixtures/
├── tools/                Developer scripts (tools/README.md): bench/, site/, samples/, audit/
├── pyproject.toml        Package definition and dependencies
└── README.md             What the project is
```

### src/layoutkeep — the layers

| Directory | Responsibility |
|---|---|
| `core/` | The DocIR schema and shared types (Document, Block, Span, Segment, Style), plus `capabilities.py` — which conversions are open. No heavy dependencies. |
| `readers/` | Reading a document into DocIR: PDF, EPUB, DOCX, images |
| `writers/` | DocIR to output: PDF, EPUB, DOCX, HTML, images, and the cross-format conversions |
| `fitting/` | Fitting a translation back into the box it was given: shrink, re-translate shorter, measure |
| `providers/` | The translation layer (OpenAI-compatible, DeepL, fake, memory, glossary) — knows nothing about layout |
| `ocr/` | Reading text out of an image |
| `ui/` | The PySide6 desktop application: set up, run, done |

### Inside the large pieces

Each of these is split into single-purpose modules; the entry module keeps the public API.

| Entry | Helpers | What the helpers hold |
|---|---|---|
| `readers/pdf_reader.py` (`read_pdf`) | `readers/_pdf_*.py` | `common` (raw types, thresholds), `images`, `mirror`, `math`, `scan`, `raster_labels`, `layout_regroup`, `table_cells`, `line_merge`, `table_grid`, `reading_order`, `roles` |
| `writers/pdf_writer.py` (`write_pdf`, `measure_fit`, …) | `writers/_pdf_*.py` | `writer_common`, `measure`, `draw`, `markup`, `fonts`, `redaction`, `scan_cover`, `provenance` |
| `providers/openai_compat.py` (`OpenAICompatProvider`) | `providers/chat_prompts.py`, `reply_parser.py`, `reply_cleanup.py` | the messages sent, reading the reply, cleaning the result |
| `ui/worker.py` (`TranslationWorker`) | `ui/batch_timing.py`, `document_io.py`, `provider_factory.py`, `translation_loop.py`, `document_prep.py`, `document_finalizer.py`, `fit_pass_runner.py` | timeouts, reading/writing, the provider chain, the loop, preparation, write-back and fitting |
| `core/terms.py` (`candidates`, `suggest_from_document`) | `core/stopwords.py` | function words per language, Turkish postpositions, URL/citation pieces, the language guess |
| `ui/glossary_dialog.py` (`GlossaryDialog`) | `ui/term_candidates_dialog.py`, `providers/glossary.py` (`save_terms`) | the candidate preview; writing JSON/CSV/TSV |
| `ui/job_setup.py` (`JobSetupWidget`) | `ui/page_picker.py`, `core/range_helper.py` (`format_page_range`) | the thumbnail page picker; pages to range text |

---

## The application flow

Three steps; there is no correction editor (removed 2026-09, see CONTRACT.md D6):

1. **Document and format** (`ui/job_setup.py`) — pick a file, source and target language, output
   format, provider. Formats this build does not do well are shown locked, with the reason.
2. **Translating** (`ui/worker.py` + `ui/progress.py`) — progress, characters per second, ETA
3. **Done** (`ui/completion.py`) — open the output, show it in its folder, or start another

The result is a `.out.<format>` file and a `.lkproj` project file. Segments carry
`needs_review` and `confidence`; those flags do real work inside the engine and are written to
the project file, but there is no separate screen for them.

---

## Running the tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
.venv\Scripts\python.exe -m ruff check .
```

With reports, for the HTML view:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v --html=_artifacts\reports\tests.html --self-contained-html
```

Test inputs live under `_artifacts\corpus\` and `_artifacts\input\`; tests reach them with
`Path("_artifacts/...")` and can also build their own fixtures (`tests/fixtures/`).

## Measuring

```powershell
.venv\Scripts\python.exe tools\audit\format_matrix.py docs\samples\format_matrix.json
.venv\Scripts\python.exe tools\bench\bench_pipeline.py docs\samples\academic_paper_10.pdf deepl --json run.json
```

The first says what every format pair keeps and loses; the second says what a translation costs
stage by stage. Rerun the first after any change to a reader or a writer.

---

## Translating a document from the command line

```powershell
.venv\Scripts\python.exe -m layoutkeep.cli inspect "book.pdf" --sample 10
.venv\Scripts\python.exe -m layoutkeep.cli models
.venv\Scripts\python.exe -m layoutkeep.cli translate "book.pdf" --to tr --model MODEL --memory tm.sqlite --limit 20
```

`--limit 20` translates only the first 20 segments. The translation memory `tm.sqlite` stops the
same text being paid for twice. Only PDF to PDF runs in this build — the command line applies the
same policy as the interface, from the same module.

## Building the exe

```powershell
.venv\Scripts\python.exe -m PyInstaller packaging\layoutkeep_onefile.spec --noconfirm --clean
```

Produces `dist\LayoutKeep.exe`. Details in [PACKAGING.md](PACKAGING.md).
