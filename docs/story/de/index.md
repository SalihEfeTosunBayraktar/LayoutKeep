# LayoutKeep, von null bis heute

**Eine gemessene Ingenieursgeschichte: was wir versucht, was gebrochen ist, was wir behoben und was
wir wieder zurückgenommen haben.**

> **English abstract.** LayoutKeep translates PDF, EPUB and DOCX documents without moving anything
> on the page: every text box keeps its position and its size, figures stay where they were, tables
> keep their rows. This document is the project's full record — how it started, what was tried and
> abandoned, which bugs were found and how each root cause was measured, why the runtime model is a
> local one and why the layout detector is IBM Docling's Heron, and what is still known to be broken.
> Every number comes from a command written down next to it. (English original: [`../en/`](../en/);
> Türkçe özgün: [`../`](../).)

---

## 0. Die Zusammenfassung, in Zahlen

| Was | Wert | Wie gemessen |
|---|---|---|
| Unterstützte Formate | PDF → PDF, EPUB, DOCX, PNG/JPG, LKPROJ | die `capabilities.py`-Matrix, in beide Richtungen getestet |
| Verlustfreiheits-Kriterium | **10 Verlustarten (L1–L10) + 3 Qualitätsschwellen (D1–D3)** | `verify.py`; die Kriterien werden aus dem Prüfer selbst gelesen |
| Veröffentlichtes Messset | **24 Dokumente**, 288 Bilder, 0 „veralteter Eintrag" | die Vergleichsseite (jedes Dokument mit seinen Prüfzahlen) |
| Größter echter Lauf | ein 220-seitiges Statistik-Lehrbuch, 55 Teile, ~106 Minuten | `translate_book.py`, `--workers 7` |
| Testsuite | **1.256 Tests**, 138 Dateien | `.venv/Scripts/python.exe -m pytest -q` |
| Quellcode | ~24.000 Zeilen (`src/`), 56 Prüfwerkzeuge | `wc -l`, `tools/audit/` |
| Die Anwendung | eine einzelne Windows-exe (ohne Installation), ~173 MB | PyInstaller onefile |
| Laufzeitmodell | `google/gemma-4-e4b`, LM Studio, standardmäßig 2 Arbeiter | lokal; das Dokument verlässt die Maschine nicht |
| Layoutmodell | IBM Docling **Heron** (ONNX, lokal) | Regionsklassifikation auf gescannten und komplexen Seiten |

---

## 1. Wie dieses Dokument zu lesen ist

Die Geschichte ist in acht Kapitel geteilt. Jedes steht für sich; in der Reihenfolge gelesen ergeben
sie die Logik des Projekts: zuerst das Problem, dann die Architektur, dann die **Messung** (denn
jede Entscheidung ruht auf einer Zahl), dann die Fehler, dann die Modellentscheidungen, dann das
Produkt, dann die ehrlichen Grenzen und die Quellen.

| # | Kapitel | Was darin steht |
|---|---|---|
| 1 | [Das Problem: was „verlustfreie Übersetzung" genau bedeutet](../en/01-problem.html) | Eine Definition, vier gemessene Schwierigkeiten, ein Vergleich mit anderen Werkzeugen, der Vertrag (D1–D7) |
| 2 | [Architektur: jedes Teil der Pipeline](../en/02-mimari.html) | Module und Zeilenzahlen, DocIR, Leser, die Provider-Kette, das Einpassen, die Schreiber, der Prüfer |
| 3 | [Messdisziplin](../en/03-olcum.html) | Die Tabelle L1–L10 + D1–D3, 56 Prüfwerkzeuge, **die vier Male, in denen die Messung selbst falsch lag** |
| 4 | [Der Fehlerkatalog: sechzehn Fälle](../en/04-hatalar.html) | Jeder Fall: Symptom → Untersuchung → Ursache → Lösung → Beleg |
| 5 | [Die Modellwahl und die IBM-Docling-Frage](../en/05-model.html) | Die Local-first-Entscheidung, das Heron-Layoutmodell (warum, gemessen), warum der V2-Plan nie gebaut wurde, die Feinabstimmung |
| 6 | [Vom Motor zum Produkt](../en/06-urun.html) | Willkommen, Hilfe, Glossar/Gedächtnis, die schwebende Leiste, der Seitenbereich, **das zweisprachige PDF**, Versionen, die Vergleichsseite |
| 7 | [Ehrliche Grenzen und Lehren](../en/07-sinirlar.html) | Was heute nicht funktioniert, die Roadmap, acht Lehren |
| 8 | [Externe Quellen und Zitate](../en/08-kaynaklar.html) | Rolle und Lizenz jeder Abhängigkeit, der rechtliche Status der Testquellen |

Die Kapitel 1–8 liegen auf Englisch vor; die türkischen Originale stehen unter [`../`](../). Eine
Übersetzung ins Deutsche entsteht nach und nach — ein Kapitel ohne Übersetzung zeigt an dieser Stelle
sichtbar das englische Original.

Die Markdown-Dateien liegen im Repository: `docs/story/01-problem.md` … `docs/story/08-kaynaklar.md`
(Englisch unter `docs/story/en/`).

---

## 2. Eine kurze Chronologie

Das Projekt begann am **10. September 2026** mit einem einzigen Satz: *„translate a document without
moving anything on the page"*.

| Datum | Was geschah |
|---|---|
| 10. Sep | Die erste funktionierende Pipeline: PDF → PDF, DocIR entstand, der Vertrag wurde geschrieben; der erste „verlustfreie" Bericht erwies sich als falsch (er sah nur den Textfluss an) und die **Rich-Fixture**-Regel kam |
| 11.–13. Sep | EPUB/DOCX-Pfade, Tests für Text-über-Bild und Tabellen, die ersten Messungen an echten Dokumenten |
| 14. Sep | Der Einpass-Durchlauf, die Kürzungsleiter, die ersten Messungen der `reflow`-Idee |
| 15.–16. Sep | Die Desktop-Anwendung (PySide6): Einrichtung, Fortschritt, Abschluss; Provider-Einstellungen; das **IBM-Docling-Heron**-Layoutmodell |
| 17. Sep | Klassifikation der Quellenart (digital/gescannt/gemischt), die OCR-Vertrauensschwelle, der vierteilige visuelle Vergleich |
| 18. Sep | Die Verlustfreiheits-Kampagne: Erweiterung der L-Kriterien, `lossless_audit`, das Held-out-Set |
| 19. Sep | Übersetzung in Teilen mit mehreren Arbeitern (`--workers`), `--resume`, Glossar- und Gedächtnis-Provider, die erste Version der Vergleichsseite |
| 19.–20. Sep (Nacht) | Das 220-seitige Buch (55 Teile, ~106 Min.); der Messfehler bei L10; zwei Messungen zu reflow; Glossar/Gedächtnis in der Oberfläche; Hilfe und Willkommen; die schwebende Leiste |
| 20. Sep | Produktreife und Korrekturen: **Parallelität in der Anwendung**, das Verhalten des Seitenbereichs, Ausrichtung (Blocksatz), ein toter Einstellungsschlüssel, die Urheberrechts-Bereinigung, Versionen **v0.9.1 → v0.9.7** |

---

## 3. Der heutige Stand, Dokument für Dokument

Jede Zahl stammt aus der `audit.json` des jeweiligen Laufs; die Vergleichsseite zeigt sie neben dem
Dokument.

| Dokument | Teile | Verbleibende echte Verluste |
|---|---|---|
| Wikipedia ×2 (neu übersetzt) | 19 / 33 | L2-Zeilen; **L10 = 0** |
| cookbook_1907 | 35 | L6=2, D1 (kleine Schrift) |
| mushrooms_1895_sample | 41 | L2=1, L6=1 |
| NIST-Journal / NISTIR-Scan | 8 / 6 | L1 Teillauf; **L2–L10 = 0** |
| IRS-Formular (48 Teile) | 48 | L7 (ein dichtes Formular; mit ausgeschaltetem reflow gemessen) |
| Das 220-seitige Buch | 55 | L2=2, L6=4, L7=1, L8=1, L10=0, D1=801 (die Klasse der kleinen Schrift) |

![Die Vergleichsseite](site.png)

*Die veröffentlichte Vergleichsseite: links das Original, rechts die Übersetzung, darüber die
Prüfzahlen des Dokuments.*

**Bekannte Grenzen (kurz):** **Zahlenreihen** in Tabellenüberschriften können ihre Anordnung
verlieren; Literaturzeilen bleiben manchmal in der Ausgangssprache (L2, markiert); auf dichten
Formularen fallen manche Blöcke unter die Lesbarkeitsschwelle (D1); gescannte Seiten hängen von der
OCR-Qualität ab und werden bei geringem Vertrauen markiert; **Rechts-nach-links-Schriften sind nicht
umgesetzt**; die Qualität ist die Fähigkeit des Modells. Die ausführliche Liste und die Roadmap:
[Kapitel 7](../en/07-sinirlar.html).

---

## 4. Die Zusammenfassung in einem Satz

Ein Dokument in eine andere Sprache zu übersetzen ist einfach; es zu übersetzen **und dabei die Seite
dort zu lassen, wo sie ist**, ist schwer — und dieses Projekt tut das Zweite und beweist es, **indem
es die Verluste zählt**: jeder Lauf wird Seite für Seite gegen die Quelle geprüft, jeder Verlust wird
entweder behoben oder mit seinem Grund markiert, und keine Zahl wird verborgen.

---

*Dieses Dokument wurde aus `docs/CONTRACT.md`, `docs/campaign/JOURNAL.md`, `docs/MEASUREMENTS.md`,
`docs/KAYIPSIZ_MOD_DURUM.md`, `docs/LOSSLESS-REPORT.md`, `docs/FEATURE-ROADMAP.md`, den
`_artifacts/heldout/**/audit.json`-Aufzeichnungen und der Git-Historie zusammengestellt.*
