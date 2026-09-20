# 1. Das Problem: was „verlustfreie Übersetzung" genau bedeutet

Dieses Kapitel definiert das Problem, das sich das Projekt gestellt hat, zeigt mit Messungen, warum
es schwer ist, und vergleicht es mit dem, was außerhalb existiert. Die folgenden Kapitel beschreiben
die Architektur, die um dieses Problem gebaut wurde, die Messungen und die Fehler.

## 1.1 Die Definition

Ein PDF zu übersetzen ist nicht dasselbe, wie seinen Text in einer anderen Sprache neu zu schreiben —
das ist der leichte Teil: das Dokument lesen, den Text extrahieren, ihn einem Modell geben, ein neues
Dokument erzeugen. Der schwere Teil ist, **die Seite selbst zu erhalten**: dieselbe Seitengröße,
dasselbe Spaltenlayout, Text in derselben Box an derselben Stelle, dieselbe Überschriftenhierarchie,
dasselbe Tabellenraster, dieselben Abbildungen, dieselben Fußnoten. Legt ein Leser die beiden
Dokumente nebeneinander, soll er „dasselbe Buch in einer anderen Sprache" sehen, nicht „eine
Zusammenfassung, die neu gesetzt wurde".

Dieses Projekt formuliert das Ziel so: **jeder übersetzbare Block wird in seiner Quellbox gezeichnet,
in Typografie nahe der Quelle, an der Position der Quelle; nichts Unübersetzbares verschwindet
still — es wird entweder erhalten oder markiert.**

## 1.2 Warum es schwer ist: vier gemessene Tatsachen

**1) Die Textlänge ändert sich, die Boxen nicht.** Englisch→Türkisch wurde in diesem Projekt mit
**0,93x** gemessen (das Verhältnis der Zeichenzahlen über dieselben Segmente) — die Übersetzung ist
also im Mittel etwas kürzer als die Quelle. Mittelwerte täuschen: eine Überschrift wird von
`Introduction` zu `Giriş` halb so lang, während ein Satz um 60% wachsen kann (`state of the art` →
`son teknoloji ürünü`). Text, der in einer festen Box wächst, läuft entweder über oder wird
verkleinert, und das Verkleinern hat eine Lesbarkeitsschwelle (in diesem Projekt **0,85** — Blöcke
darunter werden als D1 markiert).

**2) PDF ist kein umbrechbares Format.** PDF ist ein *Druckformat*: jedes Glyph hat eine feste
Position, und der Begriff „Absatz" existiert in der Datei nicht. Übersetzten Text hineinzuschreiben
verlangt zuerst, die *Struktur* der Seite zurückzugewinnen — welcher Textlauf ein Absatz ist, welcher
eine Überschrift, welcher eine Tabellenzelle, welcher eine Seitenzahl. Diese Rückgewinnung
(Lesereihenfolge, Blockzusammenführung, Spaltentrennung) ist der am stärksten getestete Teil des
Projekts, und die meisten Fehler kommen von dort.

**3) Die Art des Quelldokuments bestimmt die Qualität direkt.** Die gemessenen Unterschiede:

| Quellenart | Was passiert | Messung |
|---|---|---|
| Digitales PDF (mit Textebene) | Der beste Fall; Typografie, Schriftname, Größe und Farbe sind lesbar | NIST-Journal: 4 Teile, 114 Blöcke, D1 **52** → 0 mit reflow |
| Gescanntes PDF (ein Bild) | Braucht OCR; Zeichenfehler und ein Vertrauenswert kommen ins Spiel | NASA-Scan: der Block mit geringem Vertrauen wird mit „low OCR confidence (0.62)" **markiert** |
| Gemischt (Text + Bild) | Seite für Seite entschieden; die Falle Text-über-Abbildung | Gescannte Seiten werden ausgenommen (die L10-Regel, siehe Kapitel 3) |
| EPUB | Das Layout lebt in CSS; umbrechbar, aber erhaltbar | Über 95% Treue auf dem Rich-Fixture |
| DOCX | OOXML wird direkt verarbeitet (`python-docx` wird bewusst nicht benutzt) | Ein gemeinfreies NIST-DOCX kam zu den Testquellen |
| PNG/JPG | Nur der OCR-Pfad; das Seitenlayout wird aus der Zeichnung zurückgewonnen | Seitenbild → PDF → dieselbe Pipeline |

**4) Die Sprachfähigkeit des Modells setzt die Obergrenze.** So gut die Pipeline auch ist — das Modell
schreibt den Satz. Ergebnisse des lokalen `google/gemma-4-e4b` (LM Studio) sind bei
Terminologie-Konsistenz schwächer als die von Cloud-Modellen, weshalb das Glossar (Termine erzwingen)
und das Gedächtnis (gleicher Text, gleiche Übersetzung) *unter* das Modell gelegt wurden statt
darüber: selbst wenn das Modell sich irrt, sind Terminologie und Konsistenz von der Pipeline
garantiert.

## 1.3 Was es außerhalb gibt

Die folgende Differenztabelle ist aus BabelDOCs eigener Vergleichstabelle (arXiv 2605.10845,
Tabellen 1–2), der Funktionsliste von mineru-translate und kommerziellen Werkzeugen (Doclingo, Lara
Translate, Doctranslate, Bluente) zusammengestellt. Die Spalte „hier" ist gegen den Code in diesem
Repository geprüft.

| Funktion | Wer sie hat | Hier |
|---|---|---|
| Zweisprachige Ausgabe (Quelle + Übersetzung) | BabelDOC, mineru-translate, Doclingo, Lara | **in der PDF-Ausgabe** (nebeneinander oder abwechselnde Seiten) und auf der Seite |
| Glossar-Zwang | BabelDOC (`--glossary` CSV), DeepL, Lara | **ja** (JSON oder CSV/TSV, im Prompt und in der Ausgabeprüfung, im Programm editierbar) |
| Automatische Terminologie-Extraktion | BabelDOC | **ja** — „aus dem Dokument vorschlagen" im Glossar-Editor |
| Kontext über Seitengrenzen | BabelDOC | teilweise (`context_before/after`) |
| Überlappungsleiter (verkleinern → enger setzen → nach unten schieben) | mineru-translate | teilweise (`--fit-mode reflow`, experimentell, standardmäßig aus) |
| Übersetzungs-Cache über Läufe hinweg | mineru-translate | **ja** (ein SQLite-Gedächtnis, an einem echten Lauf mit 2.555 Segmenten geprüft) |
| Text in Abbildungen und Tabellen übersetzen | BabelDOC | nein (bewusst) |
| Ein Editor / Nachbearbeitung | Doclingo, Lara | nein (es gibt eine Prüfliste, keine Bearbeitung) |
| Ein Plugin-Ökosystem (Zotero, Word) | BabelDOC/PDFMathTranslate | nein (bewusst) |
| **Seite-für-Seite-Verlustprüfung (L1–L10)** | **nirgends gesehen** | **ja** — gegen die Quelle, bei jedem Lauf |
| Prüfmarke mit Begründung | teilweise | **ja** — für jede Marke ist der Grund geschrieben (der Buchlauf) |
| Eine Vergleichsseite aus echten Held-out-Dokumenten | nein | **ja** — 24 Dokumente, mit Schieberegler und ihren Prüfzahlen |
| Laufzeiteinstellungen (Kontextfenster, Schwellen) | teilweise | **ja** — 30 Einstellungen, alle an Code gebunden (Kapitel 4, Fall 11) |

Der entscheidende Unterschied: Werkzeuge draußen zielen auf **eine Ausgabe, die gut aussieht**;
dieses Projekt zielt darauf, **zu zählen, was verloren geht**. Ohne das Zweite ist die Behauptung
„verlustfrei" ein nicht messbarer Werbesatz.

## 1.4 Der Vertrag: sieben Entscheidungen, die nicht verhandelbar sind

Die Datei `docs/CONTRACT.md` schreibt sieben Architekturregeln fest. Sie sind nicht willkürlich —
jede wurde nach einem Fehler geschrieben:

- **D1 — DocIR ist die einzige Wahrheitsquelle.** Ein formatunabhängiges Zwischendokumentmodell;
  Leser erzeugen es, Schreiber verbrauchen es. Die Übersetzungsschicht kennt PDF nicht.
- **D2 — Die Übersetzungsschicht kennt kein Layout.** Ein Provider sieht nur Text; Box, Schriftgröße
  und Position gelangen nie hinein. Das macht das Modell austauschbar und die Provider parallelisierbar.
- **D3 — Das Einpassen ist eine eigene Stufe.** Es läuft *nach* der Übersetzung; die Entscheidungen,
  die Text passend machen (verkleinern, um eine kürzere Fassung bitten, nach unten schieben),
  beeinflussen die Übersetzungsqualität nicht.
- **D4 — Lateinische Schrift, aber bereit für RTL.** Rechts-nach-links-Schriften sind *nicht
  umgesetzt*; das Schema trägt ein `direction`-Feld.
- **D5 — Alles muss fortsetzbar sein.** Ein unterbrochener Lauf macht dort weiter, wo er aufhörte;
  beim Anwenden eines Seitenbereichs wird das Dokument *nicht* verkleinert (diese Regel wurde zweimal
  falsch umgesetzt, siehe Kapitel 4, Fall 12).
- **D6 — Übersetzungsqualität wird mit Segmentmarken verfolgt.** Jeder Block ist entweder übersetzt
  oder hat einen geschriebenen *Grund*, warum nicht.
- **D7 — Eine Konvertierung wird erst angeboten, wenn sie gemessen ist.** Ungemessene Formatpaare
  sind in der Oberfläche deaktiviert.

## 1.5 Die operative Definition von „verlustfrei"

Die Definition, die das Wort messbar macht, steht am Anfang von `docs/campaign/JOURNAL.md` und hat
drei Teile:

1. **Kein übersetzbarer Block verschwindet.** Jeder Block erscheint entweder übersetzt in der Ausgabe
   oder bleibt wie in der Quelle; keines von beiden ist ein L3/L4-Verstoß.
2. **Kein unübersetzter Block bleibt stumm.** Jeder Block, der nicht übersetzt werden konnte, wird
   *mit einem Grund* markiert (L2, D1, D2, OCR-Vertrauen, ein verlorener geschützter Wert, ein
   verlorener Stil…).
3. **Quelle und Ausgabe sind Seite für Seite vergleichbar.** Genau das zählen die Regeln L1–L10; die
   Prüfausgabe (`audit.json`) liegt neben jedem Lauf und wird auf der Vergleichsseite veröffentlicht.

Die praktische Folge: Der Erfolg des Projekts wird nicht an „es sieht gut aus" gemessen, sondern an
**der Zahl der Marken, die bleiben** — und diese Zahl wird für jeden Lauf geschrieben, auch für die,
in denen sie schlecht ausfällt.
