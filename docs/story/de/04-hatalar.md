# 4. Der Fehlerkatalog: sechzehn Fälle, vom Symptom zum Test

Dieses Kapitel ist das Gedächtnis des Projekts. Jeder Fall hat dieselbe Form: **Symptom** (wer es
bemerkte und wie), **Untersuchung** (welche Messung gemacht wurde), **Ursache** (wo im Code, und
warum es so geschrieben war), **Lösung** (was sich änderte), **Beleg** (welcher Test oder welche
Messung). Bewusst nicht chronologisch, sondern nach Wichtigkeit.

## 4.1 „Modell nicht gefunden" — die Fehlermeldung log

**Symptom.** Das Modell war in LM Studio geladen und die Anwendung sagte „Modell nicht gefunden". Das
Modell wurde getauscht, der Server neu gestartet, nichts half.

**Untersuchung.** Der **Body** der Provider-Antwort wurde geöffnet (der erste Versuch sah nur den
HTTP-Statuscode an). Im Body stand: `Context size has been exceeded`.

**Ursache.** Zwei Einstellungen fraßen einander: LM Studio lief mit `-c 8192` (ein 8K-Kontext) und die
Anwendung schickte **7 parallele Anfragen**. Das Kontextfenster wird **auf die Slots aufgeteilt** — 7
Arbeiter auf einem 8192er Fenster bekommen ~1,2k Token pro Anfrage, und ein langer Absatz überschreitet
das. Der Server wies die überlaufende Anfrage mit „context exceeded" zurück; die Provider-Schicht
verpackte das als „Modell nicht gefunden".

**Lösung.** Drei Schichten: (a) der Fehler-Body wird gelesen und die Meldung sagt die Wahrheit, (b) ein
Überlauf ist nicht mehr tödlich — das Stück wird an einer Satzgrenze geschnitten und erneut gefragt,
(c) Hilfe und Willkommensbildschirm schreiben die Rechnung aus: *„das Kontextfenster wird auf die
Slots aufgeteilt; für 7 Arbeiter werden `-c 32768` empfohlen"*.

**Beleg.** `tests/test_providers_*` für die Auswertung des Fehler-Bodys; der Buchlauf schloss 220
Seiten mit 32768 ab. Dieser Fall ist auch der Grund, warum **die Standard-Parallelität auf 2
herunterkam** (Abschnitt 4.10).

## 4.2 Die schwebende Leiste: eine Heap-Korruption (0xc0000374)

**Symptom.** Bei langen Läufen schloss sich die Anwendung abrupt; das Windows-Ereignisprotokoll zeigte
`0xc0000374` (Heap-Korruption).

**Untersuchung.** Der Absturz geschah bei geöffneter schwebender Fortschrittsleiste. Die Leiste ist
ein von Hauptfenster unabhängiges Fenster; ein Zieh-Helfer (`WindowDrag`) hielt das Fenster.

**Ursache.** Das `WindowDrag`-Objekt wurde nur in einer lokalen Variablen gehalten; als Python es
einsammelte, zeigten die Signalverbindungen auf der Qt-Seite noch darauf — die C++-Seite berührte ein
freigegebenes Python-Objekt. Der klassische „wer besitzt das"-Fehler.

**Lösung.** Der Zieh-Helfer ist mit einer **starken Referenz** an das Fenster gebunden
(`self._drag = WindowDrag(...)`) — das Objekt lebt mit dem Fenster und stirbt mit ihm.

**Beleg.** `tests/test_ui_floating_progress.py` (11 Tests) + die Leiste kann jetzt einen ganzen
Buchlauf über geöffnet bleiben.

## 4.3 Derselbe Text wurde immer wieder übersetzt

**Symptom.** In einem langen Dokument ging derselbe Satz (ein Formularlabel, eine Überschrift)
dutzendfach zum Modell; der Lauf war unnötig langsam und derselbe Text konnte **verschieden** übersetzt
zurückkommen.

**Untersuchung.** Auf dem IRS-Formular hatte ein einzelnes Label über 40 Wiederholungen. Das
Anfrageprotokoll zeigte jede Wiederholung als eigene Anfrage.

**Ursache.** Die Pipeline übersetzte jeden Block unabhängig; „Wiederholung" war kein Begriff.

**Lösung.** `providers/dedupe.py`: derselbe Quelltext wird einmal übersetzt und das Ergebnis an alle
Wiederholungen verteilt (abschaltbar mit `--no-repeats`). Zusätzlich gleicht `core/repeats.py`
**abweichende** Übersetzungen an die Mehrheit an — so bleibt „Chapter" nicht an einer Stelle „Bölüm"
und an einer anderen „Kısım".

**Beleg.** `tests/test_providers_dedupe.py`, `tests/test_core_repeats.py`; im IRS-Lauf sank die
Anfragenzahl spürbar und die Terminologie-Konsistenz stieg.

## 4.4 Gebrochene und verkleinerte Zeilen — und eine gemessene und zurückgenommene Korrektur

**Symptom.** Der Nutzer meldete, dass in den Ausgabeseiten Zeilen brechen und manche Blöcke viel
stärker verkleinert wurden als nötig.

**Untersuchung.** Die Hypothese war „wird die Box des Blocks verbreitert, brechen die Zeilen nicht".
Die Box wurde verbreitert: die Zahl gebrochener Zeilen ging **12 → 12** (keine Änderung). Die
Hypothese war durch Messung widerlegt.

**Ursache.** Die eigentliche Ursache lag in der Einpass-Leiter: Passte eine Übersetzung nicht, wurde
der Block sofort verkleinert — obwohl er zuerst das Recht hatte, **um eine kürzere Fassung zu bitten**
(eine kürzere Übersetzung vom Modell).

**Lösung.** Die Reihenfolge wurde umgestellt: verkleinern → um Kürzeres bitten → nach unten schieben →
markieren. Der Verbreiterungsversuch wurde **zurückgenommen**, mit dem Grund im Code (eine
unbewiesene Korrektur wird nicht behalten).

**Beleg.** Die Zahl „unlesbare Größe" von `type_drift` ging im IRS-Formular von 14 auf 2; für die
gebrochenen Zeilen dokumentiert `tests/test_pdf_writer_widen.py` die Rücknahme.

## 4.5 Der Willkommensbildschirm erschien nicht (wegen meiner eigenen Prüfläufe)

**Symptom.** Der Nutzer: „in der neuen 9.1-exe kam überhaupt kein Willkommensbildschirm."

**Untersuchung.** Die Einstellungs-Registry zeigte `welcome_shown = true`. Wer hatte das geschrieben?
**Meine eigenen automatisierten Läufe**, die den Willkommensbildschirm testen — sie setzten die Marke
am Ende nicht zurück.

**Ursache.** Das Willkommen wurde einmal gezeigt und dann markiert; Tests und der echte Nutzer teilten
dieselbe Marke. Hinzu kam: Wer eine neue Version herunterlud, konnte nicht sehen, was sich geändert
hatte.

**Lösung.** Zwei Änderungen: (a) automatisierte Tests laufen mit der Ausstiegsluke
`LAYOUTKEEP_NO_WELCOME`, (b) das Willkommen wird jetzt **pro Version** markiert — eine neue Version ist
ein neues Willkommen, der Nutzer sieht beim ersten Start, was sich geändert hat.

**Beleg.** `tests/test_ui_welcome*.py` + `welcome_shown_version = 0.9.3` in der Registry.

## 4.6 Glossar und Gedächtnis existierten nur auf der Kommandozeile

**Symptom.** Der Nutzer hörte von Glossar (Termine erzwingen) und Übersetzungsgedächtnis und fand sie
nicht in der Oberfläche: „wo ist das Glossar?"

**Untersuchung.** Ein Codescan: `providers/glossary.py` und `providers/memory.py` existierten, hatten
Tests und wurden **aus der Oberfläche nicht aufgerufen**. Für einen Nutzer gibt es keinen Unterschied
zwischen „eine Funktion, die es nicht gibt" und „eine Funktion, die man nicht sieht".

**Ursache.** Die Funktionen waren auf der Motor-Ebene hinzugefügt worden, die Anbindung an die
Oberfläche wurde auf später verschoben — und später kam nie.

**Lösung.** Beide wurden an die Oberfläche angebunden: eine Glossardatei (JSON **oder** CSV/TSV) kann
gewählt und **im Programm als Tabelle bearbeitet** werden (Zeilen hinzufügen/entfernen, aus Datei
laden, speichern unter), der Fingerabdruck des Glossars geht in den Gedächtnisschlüssel ein (ein
geändertes Glossar macht alte Übersetzungen ungültig), und der Abschlussbildschirm zeigt die
Trefferquote des Gedächtnisses.

**Beleg.** `tests/test_ui_glossary*.py`, `tests/test_ui_settings_memory*.py`.

## 4.7 Die schwebende Leiste hielt das Hauptfenster als Geisel

**Symptom.** Der Nutzer: „wenn ich die Pille schließe, kann ich sie nicht zurückholen" + „die Pille
und das Hauptfenster sind gleichzeitig sichtbar".

**Untersuchung.** Die Leiste war ein **besessenes** (owned) Fenster des Hauptfensters: Wurde das
Hauptfenster minimiert, verschwand die Leiste mit, aber war sie einmal geschlossen, gab es keinen Weg
zurück.

**Ursache.** Die Besitzbeziehung war falsch aufgesetzt: Die Leiste sollte unabhängig vom Hauptfenster
leben, aber **zusammen** mit ihm erscheinen, und der Wechsel musste in beide Richtungen gehen.

**Lösung.** Die Leiste wurde aus der Besitzbeziehung genommen; ein Knopf **▤ „zum kleinen Fenster
wechseln"** kam in die Titelleiste (aktiv, solange ein Lauf läuft), und „zurück zum Fenster" bringt
sie zurück. Das Minimieren des Fensters versteckt die Leiste nicht mehr.

**Beleg.** 7 Tests (`tests/test_ui_floating_pairing.py`), die Versionshinweise zu v0.9.2/v0.9.3.

## 4.8 Die Anwendung schickte ihre Anfragen eine nach der anderen

**Symptom (Nutzer).** *„obwohl 7 Slots eingestellt sind, schickt es immer nur 1 Slot auf einmal, das
muss ein Fehler sein."*

**Untersuchung.** Zwei Wege wurden verglichen: die Kommandozeile (`translate_book.py`) übersetzte
Teile mit einem `ThreadPoolExecutor` parallel; der Arbeiter der Anwendung (`ui/worker.py`) schickte
Anfragen **eine nach der anderen**. Die 7-Slot-Einstellung wirkte also nur auf der Kommandozeile —
Buchläufe waren schnell, Anwendungsläufe langsam.

**Ursache.** Die Parallelität war in der CLI hinzugefügt und nie in die Übersetzungsschleife der
Oberfläche übernommen worden. (Das ist der Bruder von 4.6: eine Motor-Fähigkeit, die die Oberfläche
nicht hat.)

**Lösung.** Die Schleife arbeitet jetzt in **Wellen**: jede Welle schickt `translation.workers`
Stapel parallel, am Wellenende wird Pause/Abbruch geprüft, und die Ergebnisse werden **in
Dokumentreihenfolge** zusammengeführt (nicht in der Reihenfolge, in der sie fertig wurden). Jedes
parallele Stück bekommt seine eigene Provider-Kette — ein geteilter dedupe-Cache und eine geteilte
Gedächtnisverbindung wären ein Wettlauf. Die Schleife zog von `worker.py` nach
`ui/translation_loop.py` um (eine Verantwortung pro Datei).

**Beleg.** `tests/test_ui_translation_parallel.py`: (a) die Nebenläufigkeit ist wirklich größer als 1,
(b) ein einzelner Arbeiter bleibt sequenziell, (c) die Ausgabe steht in Dokumentreihenfolge. Die Suite
ist grün.

## 4.9 OCR-Rauschen ist nicht stumm

**Symptom.** Im NASA-Scan wurde eine dekorative Überschrift als „Naga Merorautigs Frogrom Amerika"
gelesen.

**Untersuchung.** Das OCR-Vertrauen für diesen Block lag bei 0,62 (die Schwelle ist 0,75).

**Ursache.** Rauschen gehört zur Natur von OCR; das Problem wäre nicht das Rauschen gewesen, sondern
die **Stille**.

**Lösung.** Blöcke mit geringem Vertrauen werden in die Ausgabe geschrieben, landen aber mit dem Grund
**„low OCR confidence (0.62)"** in der Prüfliste. Der Nutzer weiß, was zweifelhaft ist.

**Beleg.** `tests/test_ocr_confidence*.py`; der Journaleintrag (20.09.2026).

## 4.10 Die Standard-Parallelität war zu aggressiv

**Symptom (Nutzer).** *„die Standard-Parallelität kann 1 oder 2 sein."*

**Untersuchung.** Die Rechnung aus 4.1: Auf einer einzelnen lokalen GPU teilen 7 gleichzeitige
Anfragen das Kontextfenster, die Token pro Anfrage sinken, und bei kleinen Modellen steigt das Risiko
von Qualitätsverlust und Überlauf.

**Lösung.** `translation.workers` steht standardmäßig auf **2** (vorher 7). Auf einem Server mit
genug Slots (LM Studio `-c 32768 --parallel 7`) erhöht der Nutzer es; der Warntext der Einstellung
sagt das. Die Ausweichkonstante der Kommandozeilenwerkzeuge wurde ebenfalls auf 2 gebracht, damit es
eine Geschichte gibt.

**Beleg.** `tests/test_parallel_workers.py` + `tests/test_core_tunables_wired.py`.

## 4.11 Der tote Schlüssel im Einstellungsbildschirm

**Symptom (Nutzer).** *„finde die Einstellungen, die nicht an die Oberfläche angebunden sind, und
binde sie an."*

**Untersuchung.** Die Schlüssel aller 30 erklärten Einstellungen wurden mit den Schlüsseln verglichen,
die irgendwo in `src/` gelesen werden (ein statischer Scan, plus die Konstantennamen, über die
Einstellungen gelesen werden). Ergebnis: **ein** toter Schlüssel — `timeout.first_batch_s`: er stand
im Einstellungsbildschirm, wurde gespeichert, und **nichts las ihn** (der Timeout des ersten Stapels
kam aus einer Konstanten). Dass der Bildschirm 30/30 zeigt, wurde ebenfalls gemessen.

**Lösung.** Der Schlüssel wurde an den Arbeiter angebunden (die erste Antwort eines kalten Modells
kann Minuten dauern; das ist eine Eigenschaft dieser Maschine, nicht des Codes). Fünf Tests kamen
dazu: *jede erklärte Einstellung muss gelesen werden*, der Timeout des ersten Stapels erreicht den
Timeout, ein warmer Stapel wird davon nicht berührt, die Voreinstellung ist 2, und der
Einstellungsbildschirm zeigt jede erklärte Einstellung.

**Lehre.** Ein Schlüssel, der nichts tut, ist schlimmer als einer, den es nicht gibt — er verbraucht
das Vertrauen in die, die funktionieren.

## 4.12 Der Seitenbereich verengte die Ausgabe nicht

**Symptom (Nutzer).** In dem 841-seitigen Buch wurde ein Bereich gewählt; die Ausgabe war weiterhin
**das ganze Buch**: *„sollte es nicht nur den gewählten Bereich ausgeben, warum kam das ganze Buch."*

**Untersuchung.** Die Ausgabe-PDF: 841 Seiten, 194 davon auf Türkisch (23% — der gewählte Bereich),
der Rest auf Englisch. Der Motor wandte den Bereich **nur auf die Übersetzung** an; die Ausgabe war
eine Kopie der ganzen Quelle.

**Ursache 1 (historisch).** Das war eine bewusste, aufgeschriebene Entscheidung gewesen: Ein Bereich
war einmal durch **Löschen** von Seiten aus dem Dokument angewandt worden, und als das Projekt nur
die gewählten Seiten behielt, ging die Prüfung verloren und der erneute Export wurde still verkürzt
(CONTRACT.md, D5). Die richtige Lösung war, den Bereich **zu teilen**: auf die geschriebene Kopie
anwenden, im gespeicherten Projekt jede Seite behalten.

**Ursache 2 (durch Messen gefunden).** Der erste Versuch — Seiten aus dem Dokument zu werfen — reichte
nicht: Die Ausgabe kam weiterhin mit 841 Seiten heraus, weil der PDF-Schreiber Seiten **aus der
Quelldatei** zeichnet. Dem Schreiber wurde ein **Ausschnitt** der Quelle übergeben; die Seiten im
Ausschnitt wurden auf 0..n umnummeriert, damit die Prüfung Seite N mit N vergleicht, während das
Projekt die ursprünglichen Nummern behält (durch Kopieren der Seiten — geteilte Objekte an Ort und
Stelle zu verändern würde das Projekt beschädigen).

**Lösung.** `_output_document` + `_source_slice`; die Oberfläche sagt, was ein Bereich tun wird
(RANGE_HINT, tr/en/de). **Beleg:** 11 neue Tests plus der alte D5-Test auf den neuen Vertrag
umgestellt — auf einer echten 15-seitigen Corpus-PDF ergab der Bereich „1-2" eine 2-seitige Ausgabe
und ein 15-seitiges Projekt.

## 4.13 Blocksatz-Absätze kamen linksbündig heraus

**Symptom (Nutzer).** *„Zahlen- und Überschriftenausrichtungen gehen in den Übersetzungen verloren."*

**Untersuchung.** `type_drift` markierte in arXiv 19113 vier Textabsätze als `right → left`. Zeile für
Zeile war die Quelle im Blocksatz (jede Zeile 72→540, letzte Zeile kurz), die Ausgabe linksbündig mit
ausgefranstem rechten Rand.

**Ursache.** Der Schreiber zeichnet Blöcke als HTML-Boxen, in denen `text-align: justify` bereits
unterstützt wurde; was fehlte, war **der Leser, der nie „justify" erzeugte** (nur left/right/center).

**Lösung.** Eine Regel mit drei Bedingungen: gerade linke Ränder, eine kurze letzte Zeile, und die
**linke Kante** der letzten Zeile auf Höhe des Textkörpers. Die dritte ist entscheidend — die Zeilen
einer zentrierten Überschrift werden ebenfalls kürzer, aber ihre letzte Zeile beginnt in der Mitte;
ohne diese Bedingung driftete die NASA-Titelüberschrift aus der Mitte (ein Test fing es).

**Beleg.** 19 Ausrichtungstests plus 218 Leser-/Layout-Tests; zwei alte Tests auf den neuen Vertrag
umgestellt, vier neue hinzugefügt. **Im echten Lauf geprüft (am selben Tag):** in den ersten neu
übersetzten Teilen des 220-seitigen Buchs las der Leser **26 von 70** langen Textblöcken als
„justify", und die Ausrichtungsmarke von `type_drift` kam auf **0** (vor der Korrektur gab dieselbe
Messung 4 Marken in arXiv). Die Entscheidung trug vom Leser zum Schreiber und vom Schreiber zur
gezeichneten Seite.

## 4.14 Ordnerhygiene: urheberrechtlich geschützte Seitenbilder im Repository

**Symptom (ein Nutzerkriterium).** *„veröffentliche die offen lizenzierten Inhalte auf GitHub, der
Rest bleibt lokal."*

**Untersuchung.** Ein Scan der verfolgten Dateien: `tests/layout_eval/` enthielt 62 JPEGs; zwei davon
waren Seiten eines urheberrechtlich geschützten Lehrbuchs
(`computer-systems-Architecture.pdf`), eines ein persönlicher Scan (`Notes_...`), dazu ein `run.log`.
Das verfolgte Repository umfasste **36 MB**.

**Lösung.** Die geschützten und persönlichen Bilder wurden **entfernt aus der Verfolgung** (die
Dateien blieben auf der Platte, mit einem Hinweis in ihrem README, dass sie aus Urheberrechtsgründen
aus der Veröffentlichung entfernt wurden und mit den Befehlen neu erzeugt werden können).
Gemeinfreie NASA-Bilder blieben. `.gitignore`-Regeln kamen dazu. Ein zweiter Durchgang entfernte
Zooms in einem verschachtelten Ordner (vom ersten Scan übersehen). **Verfolgtes Repository:
36 MB → 12 MB.**

**Lehre.** Der erste Scan reichte nicht; das Muster erreichte Unterordner nicht. Erneut zu scannen war
keine „unnötige Pedanterie", sondern Teil fertiger Arbeit.

## 4.15 Messung und Zeichnung nutzten verschiedene Zeilenhöhen (ein schlafender Fehler)

**Symptom.** Keines — der Fehler schlief. Er fiel auf, als der Leiter ein Schritt „Zeilenabstand enger
setzen" hinzugefügt wurde.

**Untersuchung.** `fitting/measure.py` **liest** `style.line_height`, wenn entschieden wird, ob ein
Text in seine Box passt; das CSS von `pdf_writer` **schrieb dieses Feld nie**. Ein Block mit einer
benannten Zeilenhöhe wurde also mit *dieser* Höhe *gemessen* und mit der eigenen des Motors
*gezeichnet*. Der einzige Grund, warum das heute unsichtbar ist: Die Leser füllen das Feld nie
(`None`), beide Seiten fallen auf ihre Voreinstellungen zurück.

**Warum es jetzt zählt.** In den ersten 12 fertigen Teilen des Buchs war die größte Prüfmarkenklasse
„die Übersetzung passte nicht in ihre Box, Verkleinern reichte nicht" (352 von 6.570 Blöcken). Der
Schritt, der diese Klasse auflösen würde — den Zeilenabstand enger setzen — nutzt genau dieses Feld;
ohne die Schließung dieser Lücke würde der Schritt falsch messen.

**Lösung.** `_css_for_block` schreibt `line-height: …pt`, wenn der Stil des Blocks eine hat. Drei
Tests: sieht die Messung das Feld (mit der Anmerkung, dass ein Test mit kurzem Text fälschlich besteht
— ein einzeiliger Text „passt" bei jeder Zeilenhöhe), trägt das CSS das Feld, und bleibt das CSS
unberührt, wenn das Feld leer ist (damit die kalibrierte Voreinstellung des Motors nicht für jeden
Absatz überschrieben wird).

## 4.16 Die gepackte Anwendung konnte ihren eigenen Hilfebildschirm nicht öffnen

**Symptom.** Keines — niemand hatte es bemerkt. Die eigene Spec-Prüfung des Projekts
(`tools/audit/check_spec.py`) fand es: **sechs** Module fehlten in der Liste, die PyInstaller packt.

**Untersuchung.** `check_spec.py` führt die statische Analyse aus und vergleicht sie mit der
`hiddenimports`-Liste der Spec. Fehlend: `ui.help_dialog` und `ui.glossary_dialog` (beide aus einem
Menühandler geöffnet, was die statische Analyse nicht sieht), `fitting.figures` und die drei in 0.9.5
hinzugefügten Module — `core.terms`, `core.profiles`, `writers.dual_pdf` (alle drei innerhalb der
Funktionen importiert, die sie benutzen).

**Warum es ernst war.** Drei davon fehlten seit **mehreren Versionen**: In der veröffentlichten exe
bekam ein Nutzer, der den Hilfebildschirm oder den Glossar-Editor berührte, einen `ImportError`. Die
Tests liefen aus dem Quellbaum und waren grün; die Screenshots kamen ebenfalls aus dem Quellbaum. Es
ist die „zwei Türen"-Lehre in einer dritten Form: **Quellbaum und Paket sind zwei verschiedene
Produkte.**

**Lösung.** Die sechs Module kamen in die Spec; die Prüfung sagt nun „every lazy import is reachable,
no stale names". Die Version wurde als 0.9.6 neu gebaut und veröffentlicht.

**Lehre.** Der Pfad des gepackten Produkts ist nicht der des Quellbaums. `check_spec.py` existiert
genau deshalb — und ein Prüfwerkzeug beweist seinen Wert, wenn es einen Fehler findet, über den sich
niemand beschwert hat.
