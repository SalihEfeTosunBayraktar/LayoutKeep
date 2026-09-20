# 8. Externe Quellen und Zitate

Dieses Projekt steht auf der Arbeit anderer. Unten stehen die **Rolle** jeder Quelle in diesem
Projekt und ihre Lizenz. (Dieselbe Tabelle wird auch in `CREDITS.md` geführt; dies ist die längere
Fassung mit den Begründungen.)

## 8.1 Motor und Infrastruktur

| Quelle | Ihre Rolle hier | Lizenz |
|---|---|---|
| [PyMuPDF](https://pymupdf.readthedocs.io/) | Der PDF-Lese- und -Schreibmotor; Textebene, Typografie, Bildextraktion, Redaktion, Zeichnen von HTML-Boxen | AGPL-3.0 |
| [Qt / PySide6](https://doc.qt.io/qtforpython/) | Die Desktop-Oberfläche: Fenster, schwebende Leiste, Willkommen, Tabellen, Thema | LGPL-3.0 |
| [pytest](https://pytest.org/) | Der Läufer für 1.256 Tests | MIT |
| [PyInstaller](https://pyinstaller.org/) | Das Erzeugen der Einzeldatei-`.exe` | GPL-2.0 (mit der üblichen Ausnahme) |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) (PP-OCR-Modelle) | OCR auf gescannten Seiten; liefert einen Vertrauenswert | Apache-2.0 |

## 8.2 Das Layoutmodell (IBM Docling)

| Quelle | Ihre Rolle hier | Lizenz |
|---|---|---|
| [IBM Docling — das Heron-Layoutmodell](https://huggingface.co/docling-project/docling-layout-heron-onnx) | Regionsklassifikation auf gescannten und komplexen Seiten (Überschrift, Absatz, Tabelle, Abbildung, Fußnote). Läuft lokal als ONNX | MIT |
| [Docling (das Projekt)](https://github.com/docling-project/docling) | Das Framework, aus dem das Modell kommt; seine Architekturideen (Struktur aus einem Seitenbild zurückgewinnen) | MIT |

Begründung und Messung stehen in Abschnitt 5.3: In einem vierteiligen Vergleich über 10 Buchseiten
ging „noch englische Prosa" von 6/82 auf 1/82. Die Ausgabe des Modells **allein** wurde ebenfalls
aufgezeichnet (`tests/layout_eval/2026-09-16_heron_pure/`), damit jede später hinzugefügte Regel
gegen einen gemessenen Boden gestellt wurde.

## 8.3 Übersetzungsmodelle

| Quelle | Ihre Rolle hier | Lizenz |
|---|---|---|
| [google/gemma-4-e4b](https://huggingface.co/google/gemma-4-e4b) (über LM Studio) | Das standardmäßige lokale Übersetzungsmodell | Gemma Terms of Use |
| [LM Studio](https://lmstudio.ai/) | Der lokale Modellserver (OpenAI-kompatibler Endpunkt, parallele Slots, Kontexteinstellung) | Proprietär (kostenlos nutzbar) |
| [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | Das Basismodell der Feinabstimmungsspur (eine eigene Arbeit, Abschnitt 5.4) | Apache-2.0 |
| [Hugging Face Transformers](https://huggingface.co/docs/transformers/) + PEFT/QLoRA | Feinabstimmung (auf Kaggle, ohne Abhängigkeit von TRL) | Apache-2.0 |

## 8.4 Vergleichspunkte (kein Code genommen, Ideen und Maßstäbe genommen)

| Quelle | Was wir verglichen | Lizenz |
|---|---|---|
| [BabelDOC](https://github.com/funstory-ai/BabelDOC) | Parallele PDF-Übersetzung; seine „verlustfrei"-Behauptung und seine eigene Vergleichstabelle (arXiv 2605.10845) | AGPL-3.0 |
| [PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate) | PDF-Übersetzung; sein Umgang mit Formeln und Abbildungen | AGPL-3.0 |
| [MinerU](https://github.com/opendatalab/MinerU) / mineru-translate | Dokumentverstehens-Pipelines; zweisprachige Ausgabe, Caching | AGPL-3.0 |
| Kommerzielle Übersichten (Doclingo, Lara Translate, Doctranslate, Bluente) | Funktionsumfang und Preisgestaltung | — |

**Es wurde kein Code genommen.** Keine Zeile in diesem Projekt wurde aus den obigen Werkzeugen
kopiert; die Tabelle existiert nur, um die Frage „was gibt es draußen, was fehlt hier" messbar zu
machen (`docs/FEATURE-ROADMAP.md`).

## 8.5 Testquellen (das Held-out-Set)

Die für die Messung verwendeten Dokumente und ihr Lizenzstatus. Geschützte **kommen nicht ins
Repository** und werden nicht auf der Seite veröffentlicht (`NOT_PUBLISHABLE`); sie bleiben nur auf
der Platte des Nutzers.

| Quelle | Art | Status |
|---|---|---|
| NIST Journal of Research (Heftausgaben) | Digitales PDF | Gemeinfrei (US-Bundesbehörde) — veröffentlicht |
| NIST IR 6643 (Dampfdruck) | **Gescanntes** PDF | Gemeinfrei — veröffentlicht |
| Ein aus dem NIST-Journal erzeugtes DOCX | DOCX | Gemeinfrei (mit dem eigenen PDF→DOCX-Weg des Projekts erzeugt) — veröffentlicht |
| NASA-NTRS-Bericht + NASA-Grant-Formular | Digital + gescannt | Gemeinfrei — veröffentlicht |
| arXiv-Arbeiten (19113, 19145, 2510.03959, 2605.18014) | Digitales PDF | arXiv-Lizenz — veröffentlicht |
| IRS-Formulare (i1040gi, p505) | Formular-PDF | Gemeinfrei (US-Bundesbehörde) — veröffentlicht |
| Project Gutenberg #31061, Cajori — A History of Mathematics (556 Seiten) | PDF, formeldicht | Gemeinfrei — veröffentlicht |
| Project-Gutenberg-Bücher (The Time Machine, Think Python, cookbook) | EPUB/PDF | Gemeinfrei / offene Lizenz — veröffentlicht |
| Wikipedia-Seiten | PDF | CC BY-SA — veröffentlicht |
| Introductory Statistics (Sheldon M. Ross) | Buch-PDF | **Urheberrechtlich geschützt** — nur lokal |
| computer-systems-Architecture | Buch-PDF | **Urheberrechtlich geschützt** — nur lokal (seine Bilder wurden aus dem Repository entfernt) |

## 8.6 Methoden- und Ingenieurquellen

| Quelle | Was sie beeinflusst hat |
|---|---|
| Google DESIGN.md / Design-Tokens | Die Regel, dass die Oberflächenpalette aus Tokens kommt (kein fest verdrahtetes Hex) |
| Apple HIG, Material Design (allgemeine Prinzipien) | Der Aufbau von Willkommens- und Hilfebildschirm, die Abstände und die Typoskala |
| ISO-639-Sprachcodes | Sprachauswahl und -erkennung |
| Der Unicode Private Use Area (U+E000–U+E001) | Geschützte Werte unsichtbar zum Modell zu tragen |
| Die Portable-Document-Format-Spezifikation (ISO 32000) | Das Prüfen von PDF-Schreiben und Redaktionsverhalten |

## 8.7 Die Quellen dieses Dokuments

Diese Geschichte wurde nicht erfunden; sie wurde aus diesen Dateien und Messungen zusammengestellt:

- `docs/CONTRACT.md` — die Architekturinvarianten (D1–D7)
- `docs/campaign/JOURNAL.md` — das tageweise Messjournal (die Primärquelle der Fälle)
- `docs/MEASUREMENTS.md`, `docs/BENCHMARK.md` — die Zahlen
- `docs/KAYIPSIZ_MOD_DURUM.md`, `docs/LOSSLESS-REPORT.md` — der Verlustfreiheitsstand
- `docs/FEATURE-ROADMAP.md` — der Außenvergleich und die offene Arbeit
- `_artifacts/heldout/**/audit.json` — die Prüfzahlen jedes Laufs
- `git log` — Daten und Entscheidungen
