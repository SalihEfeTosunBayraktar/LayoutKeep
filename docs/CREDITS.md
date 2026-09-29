# What LayoutKeep is built on, and what each piece does here

LayoutKeep is a small program standing on several large ones. This page says which, under what
licence, and — the part a credit line usually leaves out — **what job each one actually does in this
codebase**. The last column counts the modules that import it (`src/` and `tools/`), so the role can
be checked against the tree rather than taken on faith.

## The engine and its libraries

| Project | Version | Licence | What it does here | Modules |
|---|---|---|---|---|
| [PyMuPDF](https://pymupdf.readthedocs.io/) | 1.28.2 | AGPL-3.0 (or commercial) | The PDF reader and writer: page text with positions, fonts and sizes, the drawn output. The `pdf` extra, and the reason the project is AGPL too. | 31 |
| [ebooklib](https://github.com/aerkalov/ebooklib) | 0.20 | AGPL-3.0 | EPUB container: the OPF and spine, so a translated book keeps its reading order. | 3 |
| [lxml](https://lxml.de/) | 6.1.2 | BSD-3-Clause | The actual XML editing for EPUB and DOCX — `python-docx` is deliberately **not** used, because it re-serialises `document.xml` on save and loses what it does not model. | 5 |
| [fontTools](https://fonttools.readthedocs.io/) | 4.64.0 | MIT | Glyph coverage and real font metrics, so the fitting pass knows whether the target language's letters exist in a face and how wide they are. | 3 |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | 3.9.2 | Apache-2.0 | Reading scanned pages and text inside images (`ocr` extra). | 1 |
| [ONNX Runtime](https://onnxruntime.ai/) | 1.29.0 | MIT | What RapidOCR's models run on. | 1 |
| [OpenCV (headless)](https://opencv.org/) | 5.0.0.93 | Apache-2.0 | Image operations behind OCR; headless on purpose — a bundled desktop app never opens a camera. | 1 |
| [Pillow](https://python-pillow.org/) | 12.3.0 | MIT-CMU | Image handling: page rasters, comparison-site renders, test fixtures that draw their own pictures. | 13 |
| [NumPy](https://numpy.org/) | 2.5.2 | BSD-3-Clause, 0BSD, MIT, Zlib | Arrays behind OCR and the pixel assertions in tests. | 5 |
| [PySide6](https://doc.qt.io/qtforpython-6/) | 6.11.2 | LGPL-3.0 | The desktop application: windows, the welcome screen, the progress bar, settings. | 28 |
| [keyring](https://github.com/jaraco/keyring) | 25.7.0 | MIT | Storing provider API keys in the OS credential store instead of a settings file. | 1 |
| [PyInstaller](https://pyinstaller.org/) | 6.22.2 | GPL-2.0-or-later **with the bootloader exception** | Build tool only: turns the application into the single-file `LayoutKeep.exe` shipped in Releases. Not imported at runtime. | — |

## The fonts it ships

A translated page has to occupy the same boxes as the original, so the writer matches the source's
face rather than substituting whatever it finds. Seven families are bundled in
`src/layoutkeep/assets/fonts/` — each with its licence beside it in `licenses/` — all under the
**SIL Open Font License 1.1**:

| Family | Stands in for |
|---|---|
| Tinos | Times New Roman |
| Arimo | Arial |
| Cousine | Courier New |
| Carlito | Calibri |
| Caladea | Cambria |
| Noto Serif, Noto Sans | broad script and language coverage where the metric-compatible set stops |

They are metric-compatible replacements, which is the point: a page re-typeset in Arimo keeps Arial's
widths, so lines break where they broke in the original.

## What is deliberately *not* bundled

The translation model is not part of this repository and no model weights ship in the exe. LayoutKeep
translates through whatever OpenAI-compatible endpoint the user configures — a local LM Studio
server, or a hosted provider — so the model, its licence and its language ability stay the user's
choice. The measurement work behind that choice is in [`docs/research/`](research/) and
[`docs/QUALITY-FACTORS.md`](QUALITY-FACTORS.md).

## How the licences fit together

LayoutKeep itself is **AGPL-3.0-or-later** (`pyproject.toml`, `LICENSE`). That is coherent with the
stack rather than accidental:

- PyMuPDF and ebooklib are AGPL-3.0 — the same family, so distributing the built application is
  permitted under the terms it already carries.
- PySide6 is LGPL-3.0, which permits use by an AGPL-3.0 application.
- The bundled fonts are OFL-1.1, which permits bundling with the licence text kept alongside; the
  files in `assets/fonts/licenses/` are that text.
- PyInstaller's bootloader exception is what makes packaging a GPL-flagged build tool into a
  non-GPL application permissible.

Anyone redistributing a modified LayoutKeep inherits AGPL-3.0-or-later, and the corresponding source
is this repository.

## Where the rest of the thinking lives

| Document | What is in it |
|---|---|
| [`docs/research/system-one-models.html`](research/system-one-models.html) | Non-autoregressive decision models (Laya, Jev) measured against their sources, and where such a thing could sit in a translation pipeline |
| [`docs/QUALITY-FACTORS.md`](QUALITY-FACTORS.md) | What decides whether a translation comes out well, with the measurements behind each factor |
| [`docs/LOSSLESS-REPORT.md`](LOSSLESS-REPORT.md) | The lossless campaign written for an outside reader |
| [`docs/MAP.md`](MAP.md) · [`docs/CONTRACT.md`](CONTRACT.md) | The tree, the layers, and the architectural rules the code is held to |
| [`docs/STORY.md`](STORY.md) | The project from zero to now: the bug catalogue, the model choice, the honest limits |
