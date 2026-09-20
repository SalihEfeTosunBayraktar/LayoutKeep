# 5. Die Modellwahl: welches, warum — und die IBM-Docling-Frage

In diesem Kapitel stecken zwei getrennte Modellentscheidungen, die oft verwechselt werden:

- **Das Modell, das übersetzt** (ein LLM): das lokale `google/gemma-4-e4b`, über LM Studio.
- **Das Modell, das das Layout der Seite findet**: IBMs Docling **Heron**-Layoutdetektor (ONNX).
- Dazu eine **dritte Spur**: eine projektspezifische Feinabstimmung (Qwen2.5-7B QLoRA), eine eigene
  Arbeit.

Die Antwort auf „warum sind wir zum IBM-Modell übergegangen" ist die **zweite** Zeile, nicht die
dritte: Das IBM-Modell übersetzt nicht; IBMs Modell *versteht die Seite*. Unten stehen Begründung und
Messung jeder Entscheidung.

## 5.1 Das Übersetzungsmodell: warum lokal

Die Voreinstellung des Projekts ist **lokal** zu laufen, und das ist keine Vorliebe, sondern eine
Designachse:

| | Lokal (LM Studio) | Cloud (OpenAI-kompatibel, DeepL) |
|---|---|---|
| Verlässt das Dokument die Maschine | **nein** | ja |
| Kosten | keine | meist welche |
| Geschwindigkeit | hängt an der GPU | Netz + Anbieter |
| Qualität | hängt am Modell (bei kleinen schwächer) | meist stärker |
| Parallelität | die Slotzahl des Servers | das Limit des Anbieters |

Cloud wird **unterstützt** (einen Endpunkt in den Provider-Einstellungen eintragen, mit „Test"
ausprobieren, bevor ein Schlüssel gespeichert wird) — aber sie ist nicht die Voreinstellung. Der
Grund ist einfach: Das ist ein Werkzeug für *Dokumente*, und das Dokument eines Nutzers (ein
geschütztes Buch, ein persönlicher Scan, ein Firmular) sollte die Maschine meist nicht verlassen.
Local-first zu sein ist ein zweites Versprechen, das neben der Behauptung „verlustfrei" steht.

Auf der lokalen Seite gilt die **Ein-Modell-Regel**: Es ist ein einziges Modell geladen und die
Anfragen laufen darüber (abgesehen von den parallelen Slots). Das vermeidet die Ladestrafe und die
Instabilität des Modelltauschs, während GPU-Speicher geteilt wird. Das gemessene Ergebnis: ein
220-seitiges Buch, 55 Teile, ~106 Minuten.

## 5.2 Die Qualitätsobergrenze und die Antwort der Pipeline

Die Sprachfähigkeit eines kleinen lokalen Modells ist begrenzt. Die Antwort des Projekts war nicht
„ein besseres Modell finden", sondern **Mechanismen unter das Modell zu legen statt darüber**:

- **Geschützte Werte** (Zahlen, Maße, DOIs/URLs, Teilenummern, römische Zahlen) werden dem Modell nie
  gezeigt — selbst wenn es sich irrt, können sie nicht verloren gehen.
- **Das Glossar** erzwingt Termine (im Prompt und in der Ausgabeprüfung): Das Modell kann
  „hypothesis" nicht an einer Stelle als „hipotez" und an einer anderen als „varsayım" ausgeben.
- **Das Gedächtnis** gibt demselben Text dieselbe Übersetzung (über Läufe hinweg, in SQLite).
- **Wiederholungen vereinheitlichen** gleicht abweichende Übersetzungen desselben Quelltexts an die
  Mehrheit an.
- **Der Prüfer** findet einen Verlust, fragt erneut und markiert den Rest mit seinem Grund.

Die gemessene Folge dieses Ansatzes: Die Schwäche des Modells bleibt in *der Flüssigkeit des Textes*,
nicht in *der Integrität des Dokuments*.

## 5.3 Der IBM-Docling-(Heron-)Layoutdetektor — das eigentliche „IBM-Modell"

### Warum er nötig war

Die klassische Methode der Lesepipeline ist **XY-cut**: Sie findet Blöcke, indem sie die Seite entlang
horizontaler und vertikaler Lücken schneidet. Auf ausgerichteten, sauberen Seiten funktioniert das
gut, auf komplexen Seiten bricht es zusammen:

- eine Box in einer Box (Formularfelder), Bildunterschriften, zwischen zwei Spalten eingeklemmte
  Formeln, in den Rand laufende Fußnoten;
- gescannte Seiten (keine Linien, nur Pixel).

In diesen Fällen wird nicht der *Text* falsch gelesen, sondern die **Regionsgrenze**: Eine Überschrift
verschmilzt mit einem Absatz, eine Fußnote gerät in den Textkörper, eine Tabellenzeile wird ein
eigener Block. Das Ergebnis: Die Übersetzung stimmt und die Platzierung nicht — genau das, worüber
sich der Nutzer beschwert.

### Was getan wurde

Das Layoutmodell aus IBMs Research-Projekt **Docling** (`docling-layout-heron-onnx`) kam dazu. Das
Modell betrachtet die Seite als Bild und klassifiziert ihre Regionen: Überschrift, Absatz, Tabelle,
Abbildung, Liste, Fußnote. Es läuft als ONNX **lokal** (sogar auf der CPU) und bricht damit das
Local-first-Prinzip nicht.

- Auf der Kommandozeile wird es mit `--layout-detector` aktiviert; in der Oberfläche ist es
  standardmäßig an.
- Es läuft nur, wo es gebraucht wird: Lässt sich eine Seite über ihre Textebene lesen und ist die
  Struktur einfach, genügt XY-cut; das Modell kommt bei gescannten oder komplexen Seiten dazu.

### Die Messung: was sich wirklich geändert hat

Über 10 Buchseiten wurde ein **vierteiliger** Vergleich erzeugt: `Original | alter Lauf | XY-cut |
mit dem Detektor`. Gemessen wurden „in der Ausgabe noch englische Prosa" und „Wörter über den
Seitenrand hinaus".

| | Noch englische Prosa | Wörter über den Rand |
|---|---|---|
| Alter Lauf (524 Seiten, ohne Modell) | 6/82 (7%) | 0 |
| XY-cut | 6/82 (7%) | 0 |
| **Mit dem Detektor** | **1/82 (1%)** | 0 |

Was das Modell **allein** tut, wurde ebenfalls aufgezeichnet
(`tests/layout_eval/2026-09-16_heron_pure/`): jede Region genau so gezeichnet, wie das Modell sie
zurückgab — kein XY-cut, keine Absatzregeln, keine Reihenfolge. Diese „saubere Basis" ist es, die jede
später hinzugefügte Regel gegen einen **gemessenen** Boden stellen ließ; niemand nahm an, „das Modell
findet das wohl auch".

### Der V2-Plan: warum wir nicht neu geschrieben haben

Etwa zur selben Zeit wurde ein **V2-Plan** geschrieben: die Pipeline um Gemini herum neu aufbauen, das
Layoutmodell ins Zentrum. Das Plandokument liegt unter `docs/YENI_MIMARI_VE_GECIS_PLANI.md`. Es wurde
nie umgesetzt, weil:

1. Ein Neuschreiben die Verlustfreiheitsprüfung (L1–L10) und mehr als 1.000 Tests ungültig gemacht
   hätte.
2. Der laufende Motor hatte **genau eine Lücke**: Regionen auf komplexen Seiten finden. Das Modell zum
   *bestehenden* Leser hinzuzufügen reichte, um sie zu schließen — und das wurde getan.
3. Der V2-Zweig (`v2-vision-layout`) ließ sich nicht konfliktfrei zusammenführen (sechs Konflikte);
   ihn zu erzwingen hätte gemessenes Verhalten durch ungemessenes ersetzt.

Der „Umstieg auf das IBM-Modell" war also kein **Neuschreiben**, sondern eine **Lesefähigkeit**, die
zur bestehenden Pipeline hinzukam. Der nützliche Teil des Plans wurde genommen, der Rest liegt im
Archiv — und auch diese Entscheidung ist aufgeschrieben: *eine unbewiesene Korrektur wird nicht
behalten, und ein unbewiesenes Neuschreiben ebenso wenig.*

## 5.4 Die dritte Spur: eine projektspezifische Feinabstimmung (LayoutKeepLLM)

Eine eigene Arbeitsspur (in ihrem eigenen Ordner), die zwei Ziele zugleich verfolgt:

1. **Konformität mit dem Wire-Protokoll der Anwendung**: eine mehrsegmentige JSON-Antwort, `<0>…</0>`-
   Marker, Token für geschützte Werte im Bereich U+E000–U+E001, Kontext-/Längengrenzen. Das Ziel ist,
   dass das Modell ein **Protokoll** erzeugt, nicht freien Text.
2. **Akademisch konsistente EN↔TR-Übersetzung** — nicht nur korrekt, sondern terminologisch
   konsistent.

Die Designentscheidungen:

- Basismodell **Qwen2.5-7B-Instruct**; Training **QLoRA auf Kaggle** (nicht auf der lokalen GPU).
- Das Rückgrat des Datensatzes sind **handgeschriebene Fachexperten-Paare** (Generator:
  `01_Dataset/build_dataset.py`, Korpus: `_dataset_corpus.py`); insgesamt rund 6.000 Einträge.
- **OPUS-100 wurde abgelehnt**: Der EN-TR-Teil wurde gemessen und ist auf Nachrichten und Alltag
  gewichtet — während dieses Projekt akademische und technische Dokumente übersetzt. „Viele Daten"
  und „die richtigen Daten" sind nicht dasselbe.
- Das Trainingsskript **hängt nicht von TRL ab** (ein einfacher `transformers.Trainer` plus
  `apply_chat_template`), weil sich TRLs `SFTConfig`-API zwischen Versionen ändert und das Notebook
  auf Kaggle immer wieder brach.

Diese Spur wird vom Produkt in seinem heutigen Stand **nicht benutzt**: Das Laufzeitmodell ist gemma.
Die Feinabstimmung ist ein Weg, der bereitliegt, um die Qualitätsobergrenze zu heben; ihr Maßstab ist
derselbe: die L/D-Tabelle und die Terminologie-Konsistenz.

## 5.5 Zusammenfassung: welches Modell was tut

| Schicht | Modell/Werkzeug | Warum dieses |
|---|---|---|
| Seitenlayout (gescannt/komplex) | IBM Docling **Heron** ONNX | Funktioniert dort, wo XY-cut bei der Regionsklassifikation zusammenbricht; läuft lokal; gemessener Gewinn 6/82 → 1/82 |
| Textextraktion (digital) | PyMuPDF | Die genaueste Quelle, wenn eine Textebene existiert; trägt Typografie |
| OCR (gescannt) | RapidOCR (PP-OCR-Modelle) | Liefert einen Vertrauenswert; geringes Vertrauen wird markiert |
| Übersetzung | `google/gemma-4-e4b` (LM Studio) | Lokal, kostenlos, parallel über Slots; das Dokument verlässt die Maschine nicht |
| Cloud-Übersetzung (optional) | OpenAI-kompatible Endpunkte, DeepL | Stärkere Modelle; nur wenn der Nutzer sie wählt |
| Qualitätsgarantie | `verify.py` + Glossar + Gedächtnis | Lässt die Schwäche des Modells nicht bis zur Integrität des Dokuments durch |
