# 2. Architektur: jedes Teil der Pipeline

Dieses Kapitel beschreibt, wie der Code im Repository zusammensetzt ist — was jedes Modul tut, warum
es an dieser Grenze endet und welchen Fehler das Ziehen dieser Grenze verhindert hat. Die Zahlen
stammen aus diesem Repository (`wc -l`, 2026-09-20).

![Die Übersetzungs-Pipeline von LayoutKeep](architecture.png)

## 2.1 Der Gesamtfluss

```
lesen → DocIR → segmentieren → Provider-Kette → einpassen → schreiben → prüfen → markieren
```

Jede Stufe erzeugt die Eingabe der nächsten und **keine tut die Arbeit einer anderen**. Die Trennung
ist nicht theoretisch: jede Grenze wurde beim Beheben eines Fehlers gezogen. Die Regel „das Einpassen
muss eine eigene Stufe sein" (D3) etwa wurde geschrieben, nachdem das Modell beim Beantworten der
Bitte „mach diesen Satz kürzer" die Übersetzungsqualität beschädigt hatte — das Modell sieht eine
Kürzungsbitte jetzt nur im *zweiten* Durchgang und nur in der Einpass-Stufe.

## 2.2 Module und ihre Größen

| Modul | Zeilen | Verantwortung | Die Grenzregel |
|---|---|---|---|
| `readers/` | 3.819 | PDF-, EPUB-, DOCX- und Bildleser | Die Ausgabe ist nur DocIR; ein Leser schreibt nichts |
| `core/` | 2.519 | DocIR, Schutz, Zahlwörter, Einstellungen, Seitenbereiche | Kennt kein Format; nur Daten |
| `providers/` | 2.718 | Die Provider-Kette: dedupe, Gedächtnis, Glossar, Schutz, Aufteilen, Wiederholen | Kennt kein Layout (D2) |
| `fitting/` | 1.881 | Einpassen in eine Box, Wachsen, Abbildungskollisionen, Text-über-Bild | Fragt nicht nach Übersetzungen; es misst |
| `writers/` | 3.196 | PDF-, DOCX- und EPUB-Schreiber + Konverter | Entscheidet nichts; es zeichnet |
| `ocr/` | 726 | Gescannte Seiten lesen, der Layoutdetektor (IBM Docling Heron) | Liefert dem Leser Daten |
| `ui/` | 7.864 | Die PySide6-Oberfläche, der Arbeiter, die schwebende Leiste, Willkommen, Hilfe, der Glossar-Editor | Ruft den Motor, kopiert ihn nie |
| `verify.py` | 576 | Die Prüfungen L1–L10 und D1–D3 + Reparatur | CLI und Oberfläche führen dieselbe Datei aus |
| `cli.py` | 703 | Die Kommandozeile | Derselbe Motor, eine andere Tür |

Dass die Oberfläche größer ist als der Motor, ist kein Zufall: jeder Komfort, den der Nutzer sieht
(der Willkommensbildschirm, die Hilfe, die Glossartabelle, die schwebende Leiste, die Prüfliste),
lebt dort. Der Motor wurde klein gehalten — weil seine Korrektheit davon abhängt, wie testbar er ist.

## 2.3 DocIR: warum ein formatunabhängiges Zwischenmodell

`core/docir.py` trägt diese Kette:

```
Document → Page → Block → Line → Span
```

- **Block** ist eine übersetzbare Einheit: `text`, `bbox`, `role` (title/paragraph/table/caption/…),
  `align`, `direction`, `rotation`, `source_ref` (von welcher Seite er kam), `table_id/row/col`.
- **Line/Span** tragen die Typografie: Schriftfamilie, Größe, fett/kursiv, Farbe.
- **Segment** ist die Übersetzungseinheit: `source` (Text mit maskierten geschützten Werten),
  `target`, `block_id`, Marken und Gründe.

Warum ein eigenes Modell? Weil die Umwandlung zwischen Lesern und Schreibern in **beide Richtungen**
geht: PDF→DOCX, DOCX→EPUB, EPUB→PDF laufen alle durch dasselbe Zwischenmodell und dieselbe Prüfung.
Ohne es bräuchte jedes Formatpaar eine eigene Pipeline, und jede hätte ihre eigenen Fehler.

**Geschützte Werte.** Zahlen, Maße, DOIs/URLs, Teilenummern, Datumsangaben und (umschaltbar) römische
Zahlen werden dem Modell **nie gezeigt**: sie werden aus dem Text gehoben und durch unsichtbare
Platzhalter im Bereich U+E000–U+E001 ersetzt, danach wieder eingesetzt. Damit ist es strukturell
unmöglich, dass das Modell eine Zahl erfindet oder verliert. Im Buchlauf brachte diese Regel die
Marke „Zahlen verloren" auf 49 Fälle herunter — was bleibt, sind meist Zahlengruppen in Tabellen.

## 2.4 Leser

**Der PDF-Leser** (`readers/pdf_reader.py`) nutzt zwei Wege: die Textebene, wenn es eine gibt, OCR,
wenn nicht. Entschieden wird Seite für Seite — zwei der 841 Seiten eines Buchs können Scans sein
(gemessen), und nur diese zwei gehen durch OCR. Für die Lesereihenfolge laufen XY-cut
(horizontales/vertikales Schneiden) mit Spaltentrennung, dann Zeilenzusammenführung und Absatzregeln.

**Der Layoutdetektor (IBM Docling Heron).** XY-cut schaut auf die *Linien* der Seite: es findet
ausgerichtete Blöcke. Auf komplexen Seiten (eine Box in einer Box, eine Bildunterschrift unter einem
Bild, eine zwischen zwei Spalten eingeklemmte Formel) reicht das nicht. Deshalb kam das Modell
`docling-project/docling-layout-heron-onnx` dazu: es betrachtet die Seite als Bild und klassifiziert
sie Region für Region (Überschrift, Absatz, Tabelle, Abbildung, Fußnote). Das Modell läuft als ONNX
**lokal** (sogar auf der CPU) und bricht damit das Local-first-Prinzip nicht.

- Auf der Kommandozeile wird es mit `--layout-detector` aktiviert; in der Oberfläche ist es
  standardmäßig an.
- Es läuft nur, wo es nötig ist: lässt sich eine Seite über ihre Textebene lesen und ist die Struktur
  einfach, genügt XY-cut; das Modell kommt bei gescannten oder komplexen Seiten dazu.

## 2.5 Die Provider-Kette

Die Reihenfolge zählt — jedes Glied macht das darüber überflüssig:

```
Schutz (mask)  →  dedupe (denselben Text einmal übersetzen)  →  Gedächtnis (über Läufe)  →
Glossar (Termine erzwingen)  →  der Modellaufruf  →  Aufteilen (Satz für Satz, wenn es echot)  →
Wiederholen (erneut fragen, was leer zurückkam)  →  Wiederholungen vereinheitlichen
```

- **dedupe**: derselbe Text erscheint dutzendfach in einem Dokument (Überschriften, Tabellenlabels,
  Formularfelder). Er wird einmal übersetzt; auf dem IRS-Formular senkt das die Anfragenzahl spürbar.
- **Gedächtnis** (`providers/memory.py`): SQLite, über Läufe hinweg. Ein echter Lauf sammelte 2.555
  Segmente, und als der Nutzer dasselbe Buch neu startete, gingen diese Segmente nie zum Modell.
- **Aufteilen** (`providers/split.py`): Manchmal gibt das Modell den Absatz unverändert zurück. Dann
  wird der Absatz in Sätze geschnitten und jeder einzeln gefragt — das Problem ist nicht „das Modell
  ist faul", sondern die über einen langen Kontext driftende Aufmerksamkeit, und Satz für Satz zu
  fragen kommt daran vorbei.
- **Wiederholungen vereinheitlichen** (`core/repeats.py`): Wurde derselbe Quelltext an verschiedenen
  Stellen verschieden übersetzt, wird er an die Mehrheitsfassung angeglichen. So wird „Chapter" nicht
  an einer Stelle „Bölüm" und an einer anderen „Kısım".

## 2.6 Das Einpassen

Passt eine Übersetzung nicht in ihre Box, wird in dieser Reihenfolge versucht: **verkleinern** (bis
zur 0,85-Schwelle) → **um eine kürzere Fassung bitten** (eine kürzere Übersetzung vom Modell) →
**nach unten schieben** (den Block wachsen lassen, wenn darunter Platz ist) → **markieren**.
`--fit-mode reflow` fügt einen Schritt hinzu (den Zeilenabstand enger setzen und nach unten schieben),
ist aber standardmäßig **aus**: im NIST-Journal brachte es D1 von 52 auf 0, aber im IRS-Formular
stießen die nach unten geschobenen Blöcke auf unberührten Text (L7 0→1). Der Gewinn hängt vom Dokument
ab, der Verlust ist ein Verstoß gegen die Verlustfreiheit — die Regel lautet: *ein bewiesener Verlust
heißt, die Voreinstellung bleibt aus.*

Ein **Zeilenabstandsschritt** (den Zeilenabstand enger setzen, bevor das Modell um eine kürzere
Fassung gebeten wird) wurde am 20.09.2026 gebaut, gemessen und **zurückgenommen**: mit der eigenen
Ersatzschrift des Einpass-Durchlaufs rettete er im Buch keinen Block, und das A/B auf der
geschriebenen Seite kam in beiden Armen identisch heraus. Die Messung beantwortete auch die größere
Frage: Den meisten markierten Blöcken fehlen keine Zeilen, sondern **Box** — `room_below` kann die
gemessene Box eines Blocks auf sechs Punkte kürzen, um ihn vom nächsten freizuhalten, und in sechs
Punkte passt nichts. Siehe Kapitel 3 und `docs/campaign/JOURNAL.md`.

## 2.7 Schreiber, und die Entscheidung zu schreiben

Der PDF-Schreiber zeichnet die Seite **aus der Quelldatei**: jeder Block wird in seiner eigenen Box
redigiert und neu geschrieben. Blöcke, die sich nicht geändert haben, bleiben unberührt (ein Name,
ein Dokumentcode, eine Kopfzeile bleibt genau wie sie war — löschen und neu zeichnen verlöre ihre
Typografie). Blöcke werden mit einer HTML-Box plus CSS gezeichnet, das heißt: die Arbeit der
Browser-Engine für Ausrichtung (zentriert, rechts, Blocksatz) und Schriftzuordnung wird genutzt.

Die DOCX- und EPUB-Schreiber gießen dieselbe DocIR in ihre Formate. `writers/converter.py` verwaltet
die Formatpaare und bietet nach D7 **nur gemessene** Paare an.

## 2.8 Der Prüfer: das Teil, das das Projekt unterscheidet

`verify.py` vergleicht die Ausgabe mit der Quelle und zählt zehn Verlustarten (L1–L10) und drei
Qualitätsschwellen (D1–D3). Die Prüfung läuft auf **beiden Seiten**: auf der DocIR vor dem Schreiben
und auf der geschriebenen PDF selbst. Das Zweite ist entscheidend — manche Fehler entstehen nur
*beim Zeichnen* (Text über Text, ein Wort über den Seitenrand hinaus, Text auf einer Abbildung).

Die Prüfung berichtet nicht nur: findet sie einen Verlust, **fragt sie erneut** (`ask_again`), heilt,
was zu heilen ist, und markiert den Rest mit seinem Grund. Die „Prüfliste", die der Nutzer in der
Oberfläche sieht, ist genau diese Marken — jede Zeile hat einen Grund, und der Grund steht in der
Sprache der Oberfläche.
