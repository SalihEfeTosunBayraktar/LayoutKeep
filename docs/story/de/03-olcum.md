# 3. Messdisziplin: wie die Zahlen entstehen, und wie die Messung selbst falsch lag

Die Lehre, die dieses Projekt am häufigsten wiederholt: **eine falsche Messung ist schlimmer als
keine Messung.** Eine falsche Zahl wird nicht ignoriert — sie erzeugt eine Korrektur, die korrigiert
werden muss, verbrennt Arbeitsstunden und macht nach einer Weile die Behauptung „verlustfrei"
unglaubwürdig. Dieses Kapitel beschreibt zuerst, was Messung hier bedeutet, dann die vier Male, in
denen sie falsch lag.

## 3.1 Zehn Verlustarten, drei Qualitätsschwellen

`verify.py` zählt diese Kriterien bei jedem Lauf. Die Regel: **jedes Kriterium ist entweder null oder
hat einen geschriebenen Grund.**

| Code | Was gezählt wird | Wie es gemessen wird |
|---|---|---|
| **L1** | Seitenzahl weicht ab | Die Seitenzahlen von Quell- und Ausgabe-PDF |
| **L2** | Nicht übersetzt oder in anderer Sprache | Die Wörter der Ausgabeseite werden mit der Sprache der Quelle verglichen |
| **L3** | Text nicht auf der Seite | Ein Block der DocIR ist in der Ausgabe nicht zu finden |
| **L4** | Text über den Seitenrand hinaus | Eine Wortbox außerhalb des Seitenrechtecks |
| **L5** | Auszeichnung durchgesickert | Ein `<…>`-Muster in der Ausgabe |
| **L6** | Zahlen in der Übersetzung verloren | Die Zahlenmenge der Quelle wird in der Ausgabe gesucht |
| **L7** | Text über anderen Text gezeichnet | Wortboxen, die sich überlappen |
| **L8** | Unberührter Text verschoben | Ein Block, der wie in der Quelle blieb, steht in der Ausgabe woanders |
| **L9** | Buchstaben einer anderen Schrift eingemischt | Beispiel: `Việt語` — Latein und CJK in einem Wort |
| **L10** | Text über eine Abbildung gezeichnet | Eine Wortbox schneidet eine Bildbox |
| **D1** | Unter der Lesbarkeitsschwelle | Blöcke, deren Schriftgröße unter die 0,85-Skala fiel |
| **D2** | Kurze Blöcke unverändert gelassen | Blöcke kürzer als drei Wörter, die nicht übersetzt wurden |
| **D3** | Text in seiner Box zusammengedrückt | Der Abstand zwischen Wörtern ist auf null gefallen |

L-Kriterien sind **Verluste**, D-Kriterien sind **Qualität**: ein L-Verstoß heißt „etwas ist verloren"
und ist nicht akzeptabel; ein D-Befund heißt „etwas ist schlechter geworden" und wird gezählt,
berichtet und nach Möglichkeit behoben. Die Abschlusstabelle des Buchlaufs (220 Seiten, 4.491
übersetzbare Blöcke): **L1=1, L2=2, L3=0, L4=0, L5=0, L6=4, L7=1, L8=1, L9=0, L10=0, D1=801, D2=163,
D3=0.** Das einzelne L1 ist beabsichtigt (die Literaturseite am Ende des Buchs blieb aus der Ausgabe
heraus), die zwei L2 sind Literaturzeilen, und die 801 D1 sind verkleinerte lange Übersetzungen —
alle mit einem Grund.

## 3.2 Die Prüfwerkzeuge

`tools/audit/` enthält 56 Werkzeuge; die meistgenutzten:

- `lossless_audit.py` — durchsucht ein Laufverzeichnis und erzeugt die Tabelle L1–L10 + D1–D3
  (`audit.json`).
- `type_drift.py` — vergleicht die **Typografie** der geschriebenen Seite mit dem Stil, den der Leser
  aufgezeichnet hat: gewachsene Blöcke (wurde eine Überschrift größer), verkleinerte Blöcke (die
  Einpass-Leiter), Blöcke mit geänderter Ausrichtung, Blöcke in unlesbarer Größe.
- `text_over_image.py` — vertieft nur L10 (siehe 3.3, die erste falsche Messung).
- `side_by_side.py` — erzeugt den vierteiligen visuellen Vergleich (Original | alt | neu | Modell).
- `comparison_site.py` — verwandelt jeden Lauf in eine Seite mit Schieberegler (das ist die
  veröffentlichte Seite).
- `translate_book.py` / `translate_epub.py` — Treiber für geteilte, mehrmals parallel laufende
  Live-Läufe.
- `rewrite_run.py`, `repair_book.py` — eine vorhandene Ausgabe mit dem aktuellen Motor neu schreiben
  oder heilen.
- `live_check.py`, `format_matrix.py`, `translation_completeness.py` — Messungen für Formatpaare und
  Übersetzungsvollständigkeit.

Die Werkzeuge teilen eine Regel: **die Ausgabe ist maschinenlesbar** (JSON) und **trägt keine
Behauptung**, nur Zahlen.

## 3.3 Die Messung selbst lag viermal falsch

### Fall A: die Fehlalarme von L10 — die Hälfte der Zahlen war ein Messfehler

L10 heißt „Text über eine Abbildung gezeichnet". Die erste Umsetzung zählte einen Verlust, sobald
eine Wortbox eine Bildbox schnitt. Die Ergebnisse: cookbook **182**, mushrooms **124**, das Buch
**6**, arXiv **25** — es sah aus, als hätte jedes Dokument Text auf seinen Abbildungen.

Beim Nachsehen zeigten sich zwei Fehler:

1. **Ganzseitige und gekachelte Scan-Bilder.** In einem gescannten Dokument ist die ganze Seite ein
   Bild; jedes Wort darauf zählte als „über einer Abbildung". Die Regel wurde korrigiert: deckt die
   **Vereinigung** der Bildflächen praktisch die ganze Seite (≥100%), gilt L10 nicht.
2. **Die Grafikbeschriftungen der Quelle selbst.** Die Achsenbeschriftungen in der Grafik einer
   arXiv-Arbeit standen schon in der Quelle; die Übersetzung erhielt sie, und sie wurden als
   „verloren" gezählt. Die Regel wurde korrigiert: ein Wort, das **die Quelle auch geschrieben hat**,
   ist kein L10-Verlust.

Die korrigierte Messung: cookbook 182→**0**, mushrooms 124→**0**, Buch 6→**0**, arXiv 25→**0** (alles
Fehlalarme). Bei den Wikipedia-Läufen waren 13/13 **echt** — und die Neuübersetzung brachte sie auf
**0**. Die Korrektur beseitigte also die Fehlalarme und fing den echten Fall weiterhin. Dieselbe Regel
wanderte in den Kern (`verify.words_over_figures`); im NIST-Journal ging L10 von 8 auf 0.

### Fall B: „offensichtlich größere Schrift" — ein Messfehler, kein Codefehler

Der Nutzer meldete „in manchen Beispielen ist die Schrift offensichtlich größer". Die erste Messung
hatte jede geschriebene Zeile mit der Quellzeile **der nächstgelegenen Höhe** verglichen. In einem
Formular sitzt jedes Label in derselben Höhenlage wie sein Wert — ein 10-Punkt-Label wurde mit seinem
12-Punkt-Nachbarn „verglichen", und eine korrekte Seite sah aufgeblasen aus. Die Messung wurde neu
geschrieben, sodass sie gegen den Stil und die Geometrie prüft, die der Leser **für diesen Block
aufgezeichnet hat** (`type_drift.py`); das Ergebnis: **kein Block ist gewachsen.** Das Problem lag
nicht im Code, sondern in der Messung — und das wurde erst verstanden, als das Messwerkzeug selbst
geprüft wurde.

### Fall C: Ausrichtungsmarken — über die Spaltengrenze hinaus gelesen

Eine Zeit lang meldete `type_drift` für 4 Blöcke in arXiv „Ausrichtung geändert". Block für Block
betrachtet war die Quelle **im Blocksatz** (jede Zeile 72→540, letzte Zeile kurz), während die
Ausgabe linksbündig mit ausgefranstem rechten Rand war — ein echter Verlust, aber **seine Ursache lag
nicht dort, wo sie erwartet wurde**: der Schreiber unterstützte `text-align: justify` bereits (Blöcke
werden als HTML-Boxen gezeichnet), und was fehlte, war **der Leser, der nie „justify" erzeugte** (er
erzeugte nur left/right/center).

Die Korrektur brauchte zwei unterscheidende Regeln: gerade linke Ränder **und** eine kurze letzte
Zeile **und** die **linke Kante** der letzten Zeile auf Höhe des Textkörpers. Ohne die dritte las
auch eine zentrierte Überschrift als „justify" (ihre Zeilen werden ebenfalls kürzer, aber ihre letzte
Zeile beginnt in der Mitte) — die NASA-Titelüberschrift driftete genau deshalb aus der Mitte, und ein
Test fing es. Die in derselben Sitzung hinzugefügte Einrückungsregel war ebenfalls zu breit: die
erste Zeile eines zentrierten Blocks (seine längste) beginnt links und darf nicht als Einrückung
gelten.

**Ergebnis:** 19 Ausrichtungstests + 218 Leser-/Layout-Tests grün; zwei alte Tests auf den neuen
Vertrag umgestellt, vier neue hinzugefügt (ausgefranst linksbündig bleibt „left", eine zentrierte
kurze Zeile ist kein Blocksatz, zwei rechtsbündige Zeilen bleiben rechts). **Im echten Lauf am selben
Tag:** in den neu übersetzten Teilen des Buchs wurden 26 von 70 langen Textblöcken als „justify"
gelesen, und die Ausrichtungsmarke von `type_drift` kam auf 0 — die Korrektur wurde von der Messung
bis zur gezeichneten Seite belegt.

### Fall D: die Sonde beantwortete eine Frage, die der Motor nie stellt (20.09.2026)

Die größte Prüfmarkenklasse des Buchs war „die Übersetzung passte nicht in ihre Box" (1.130 von 6.014
Blöcken in 42 Teilen). Der Leiter wurde ein **Zeilenabstandsschritt** hinzugefügt: passt die Box auch
an der Lesbarkeitsschwelle nicht, den Zeilenabstand enger setzen, bevor das Modell gefragt wird. Der
Schritt funktionierte — er bestand seine Tests in einer synthetischen Box.

Die Messung wurde zweimal gemacht und **die beiden widersprachen sich**:

- *Die Sonde* (Messung über die Übersetzungen eines aufgezeichneten Laufs): **20** von 158
  überlaufenden Blöcken werden gerettet.
- *Der instrumentierte Durchlauf* (die Funktion umhüllt und gezählt): über 6 Teile wurde der Schritt
  **14 Mal aufgerufen und passte 0 Mal**.
- *Das A/B auf der geschriebenen Seite* (20 Teile, zwei Arme): **identisch** — D1=627, D3=0, jedes L
  gleich.

Der Unterschied war eine Zeile: die Sonde maß mit `block.dominant_style()`, während der Durchlauf mit
`_as_drawn(…)` misst — dem Stil, in dem die **Ersatzschrift** der Zielsprache bereits aufgelöst ist.
Die beiden Schriften haben verschiedene Metriken, und die Sonde beantwortete eine Frage, die der
Motor nie stellt.

**Ergebnis:** der Schritt wurde zurückgenommen (der Zweig wurde nie zusammengeführt; der Versuch
bleibt als `bbf5958` im Journal). Die Regel „eine Änderung, die die Messung nicht zeigt, kommt
heraus" rettete hier eine *Idee*, nicht nur eine Sonde. Die beiden Instrumente (`fit_probe.py`,
`fit_ab.py`) blieben; keines kostet einen Modellaufruf.

**Der nächste Hebel kam aus derselben Messung:** Den 138 Blöcken, die kein Zeilenabstand rettet,
fehlen keine Zeilen, sondern **Box** — `room_below` drückt die gemessene Box eines Blocks auf 6pt, um
ihn vom nächsten freizuhalten, und in 6pt passt nichts. Die eigentliche Arbeit ist also der Umgang mit
Überlappungen und Platz (Roadmap Punkt 4), nicht die Leiter.

## 3.4 Die Regeln der Messinfrastruktur

Was diese vier Fälle hervorgebracht haben und was nun geschrieben steht:

1. **Das Messwerkzeug wird selbst getestet.** Die Korrektur von `text_over_image.py` wurde geprüft,
   indem sie über alte Läufe erneut lief: sie fing den echten Fall weiter (Wikipedia 13/13) und ließ
   die Fehlalarme fallen (cookbook, mushrooms, Buch, arXiv).
2. **Eine Messung wird gegen die eigenen Daten der Quelle geprüft.** Etwas als „Verlust" zu
   bezeichnen, das die Quelle selbst geschrieben hat, ist kein Verlust (die arXiv-Grafikbeschriftungen).
3. **Eine Zahl, die falsch herauskam, wird zusammen mit der korrigierten geschrieben.** Formulierungen
   wie „182 → 0" sind in diesem Repository Absicht: zu verbergen, dass die alte Zahl falsch war, würde
   das Vertrauen kosten, das die neue braucht.
4. **Wenn Sonde und Pipeline sich widersprechen, wird die Pipeline instrumentiert.** Eine Sonde, die
   eine Änderung misst, muss die Eingaben des Motors benutzen (den Stil eingeschlossen: der Durchlauf
   misst mit `_as_drawn`, nicht mit dem Stil des Blocks). Der richtige Schritt bei einem Widerspruch
   ist, die getestete Funktion zu umhüllen und zu zählen — nicht, die Sonde zu reparieren.
5. **Eine Voreinstellung bleibt aus, wenn ein Verlust bewiesen ist.** `reflow` brachte D1 von 52 auf 0
   im NIST-Journal, aber L7 von 0 auf 1 im IRS-Formular; der Gewinn hängt vom Dokument ab, während der
   Verlust ein Verstoß gegen die Verlustfreiheit ist — deshalb existiert der Modus, ist aber nicht die
   Voreinstellung.
