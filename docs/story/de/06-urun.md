# 6. Vom Motor zum Produkt

Ein Motor, der korrekt, aber unbenutzbar ist, ist kein fertiges Projekt. Dieses Kapitel beschreibt
die Schritte von „einer Bibliothek" zu „einer Anwendung, die jeder herunterladen und starten kann",
und aus welcher Nutzerbeschwerde jeder Schritt geboren wurde.

## 6.1 Der Willkommensbildschirm

**Die Beschwerde:** *„beim ersten Start sollte es einen Willkommens- und Erklärungsbildschirm geben:
wie man eine erste Übersetzung macht, wofür welche Einstellung gut ist, der lokale Anbieter und so
weiter — recht ausführlich, mit Sprache und Thema gleich dort wählbar."*

Das Willkommen hat vier Seiten und öffnet beim **ersten Lauf**:

1. **Was es tut** — es übersetzt ein Dokument in seinen eigenen Boxen; eine Zusammenfassung in drei
   Sätzen und die Definition von „verlustfrei".
2. **Wie man es startet** — Ziehen und Ablegen, Sprachwahl, Anbieterwahl; lokal gegen Cloud.
3. **Welche Einstellung was tut** — die Rechnung von Kontextfenster und Slotzahl (7 Arbeiter + ein
   8192er Fenster = ~1,2k Token pro Anfrage), die Einpass-Schwellen, geschützte Werte.
4. **Sprache und Thema** — die Oberflächensprache (TR/EN/DE) und das helle/dunkle Thema werden hier
   gewählt.

Das Willkommen wird **pro Version** markiert: eine neue Version ist ein neues Willkommen. (Das ist die
dauerhafte Lösung für die Beschwerde „es kam kein Willkommensbildschirm" — Abschnitt 4.5.)

## 6.2 Hilfe: die Kriterien, dem Nutzer erklärt

**Die Beschwerde:** *„es sollte reichlich Hilfe und Erklärung geben, damit jeder Nutzer zurechtkommt."*

Der Hilfebildschirm hat sieben Abschnitte und erklärt **die Kriterien des Motors selbst**: die erste
Übersetzung, die Anbieterwahl, was die Einstellungen bedeuten, die Prüfmarken (was jede Marke heißt),
die Verlustfreiheitskriterien (L1–L10 + D1–D3, mit ihren Namen), wo die Ausgaben liegen (`.lkproj`,
das Gedächtnis, die Protokolle, der portable Modus) und die Fehlersuche.

Die Regel: Die Hilfe verspricht nie etwas, was der Code nicht tut. Jeder Abschnitt beschreibt ein
Verhalten, das in dieser Version wirklich funktioniert — und wenn sich ein Verhalten ändert, ändert
sich der Hilfetext mit (sichtbar in den Versionshinweisen: als die Standard-Parallelität von 7 auf 2
ging, wurden drei getrennte Texte aktualisiert).

## 6.3 Glossar und Gedächtnis in der Oberfläche

**Die Beschwerde:** *„wo ist das Glossar?"* (Abschnitt 4.6)

- **Glossar**: eine Datei wählen (JSON oder CSV/TSV), sie **im Programm als Tabelle bearbeiten**
  (Zeilen hinzufügen und entfernen, aus einer Datei laden, speichern unter), und sie wird sowohl im
  Prompt als auch in der Ausgabeprüfung angewandt. Der Fingerabdruck des Glossars geht in den
  Gedächtnisschlüssel ein — ändert man das Glossar, werden alte Übersetzungen nicht still
  wiederverwendet.
- **Gedächtnis**: SQLite, über Läufe hinweg. Der Abschlussbildschirm zeigt die **Trefferquote**. Ein
  echter Lauf sammelte 2.555 Segmente; ein Neustart desselben Dokuments ruft das Modell für diese nie.

## 6.4 Die schwebende Leiste und der Fensterwechsel

**Die Beschwerden:** *„die Pille und das Hauptfenster sind gleichzeitig sichtbar, und das Verstecken
des großen Fensters versteckt das kleine — behebe das"* + *„wenn ich die Pille schließe, kann ich sie
nicht zurückholen."*

Bei langen Läufen muss das Fenster nach hinten können. Die Antwort ist ein Wechsel in beide
Richtungen:

- Der Knopf **▤ „zum kleinen Fenster wechseln"** in der Titelleiste versteckt das Fenster, und der
  Fortschritt läuft in der schwebenden Leiste weiter (aktiv, solange ein Lauf läuft).
- **„Zurück zum Fenster"** auf der Leiste bringt es zurück; das Minimieren des Fensters versteckt die
  Leiste **nicht** (die Besitzbeziehung wurde entfernt — Abschnitt 4.7).
- Die Leiste zeigt Prozent, Phase, Segmentzähler und den Dateinamen. Passt der Name nicht, wird er
  gekürzt, aber der **volle Name bleibt im Tooltip** (ein Name, den man nicht prüfen kann, ist kein
  hilfreicher Name).

## 6.5 Der Seitenbereich hält, was er verspricht

**Die Beschwerde:** *„sollte es nicht nur den gewählten Bereich ausgeben?"* (Abschnitt 4.12)

Wird ein Bereich gewählt:

- **Übersetzt**: nur die gewählten Seiten.
- **Ausgabe**: nur die gewählten Seiten (dem Schreiber wird ein Ausschnitt der Quelle übergeben).
- **Projekt (`.lkproj`)**: das **ganze** Dokument — der Prüfbildschirm zeigt auch den Rest, und ein
  erneuter Export verkürzt das Dokument nie still.

Die Oberfläche sagt in dem Moment, in dem ein Bereich gewählt wird, was passieren wird (TR/EN/DE).
Dieses Verhalten ist mit 11 Tests festgenagelt und wurde auf einer echten 15-seitigen Corpus-PDF
gemessen: der Bereich „1-2" → eine 2-seitige Ausgabe, ein 15-seitiges Projekt.

## 6.6 Das zweisprachige PDF

**Was gewünscht war:** Die Vergleichsseite zeigt Quelle und Übersetzung nebeneinander, die PDF-Ausgabe
tut das nicht.

`--dual side|alternate` (und ein Kästchen in der Oberfläche): `side` setzt auf jeder Seite die Quelle
nach links und die Übersetzung nach rechts (die Seitenbreite verdoppelt sich), `alternate` setzt die
Übersetzung hinter jede Quellseite (die Seitenzahl verdoppelt sich). Die Designentscheidung war, **die
Pipeline nicht anzufassen**: Die Zusammenstellung geschieht danach, aus zwei fertigen Dateien, weil
die Prüfung Quellseite N mit Ausgabeseite N paart und ein zweisprachiges Dokument diese Paarung
bräche. Die übersetzte PDF und `audit.json` bleiben also genau wie sie waren; die zweisprachige Datei
wird daneben geschrieben. Bei einem unterbrochenen Lauf werden nur die Seiten zusammengestellt, die
beide Dokumente haben, und die Zahl wird berichtet. Plan und Messung: `docs/DUAL-OUTPUT-PLAN.md`.

## 6.7 Das Glossar: Terminvorschläge aus dem Dokument

**Roadmap-Punkt 5.** Das Glossar ist der stärkste Qualitätshebel der Pipeline (ein Term wird im Prompt
erzwungen und in der Ausgabe geprüft), aber es von Hand zu füllen heißt, das Dokument zu lesen und die
Wiederholungen zu bemerken — eine Arbeit für eine Maschine. `core/terms.py` findet die Wendungen, die
sich im Dokument **wiederholen**: ein bis drei Wörter, nicht mit einem Funktionswort beginnend oder
endend, mindestens N-mal vorkommend, keine Zahl. Die Rangfolge ist Häufigkeit × Länge.

Das ist eine **Häufigkeitsregel**, kein Verständnis von Bedeutung — der Docstring sagt das deutlich.
Das Ergebnis ist eine Liste, die im Editor mit **leeren Zielzellen** aufgeht; ein Mensch schreibt die
Übersetzungen, und nichts geht in einen Lauf, bevor der Nutzer speichert. Ein Term, der schon im
Glossar steht, wird nicht vorgeschlagen. 9 Tests; zwei davon sprechen über eine echte PDF-Seite mit
dem Editor.

## 6.8 Einstellungsprofile

Der Einstellungsbildschirm zeigt dreißig Werte; die ehrliche Antwort auf „welche sollte ich für einen
schnellen Entwurf ändern" ist „die wenigen, die gemeinsam Sinn tragen". Es gibt zwei Profile:

| Profil | Was sich ändert | Für wen |
|---|---|---|
| **Schneller Entwurf** | 7 parallele Anfragen, Lesbarkeitsschwelle 0,80, Bitten um Kürzeres aus | Ein erster Durchgang zum Lesen; in engen Boxen schrumpft die Schrift |
| **Publikationsqualität** | 2 Anfragen, Schwelle 0,85, Kürzungsschwelle 0,95 (die gemessenen Voreinstellungen) | Eine Ausgabe zum Behalten; eine kurze Fassung kostet eine zusätzliche Modellrunde |

Die Werte werden über denselben geprüften Weg geschrieben und die Editoren aktualisieren sich sofort;
`current()` nennt ein Profil nur, wenn **jeder** Wert passt, und sagt „benutzerdefiniert", sobald einer
von Hand geändert wurde. Die Standardinstallation ist bereits „Publikationsqualität". Der Hinweis in
der Oberfläche sagt deutlich, dass geteilte Kommandozeilen-Läufe die Werte bei jedem neuen Teil neu
lesen.

## 6.9 Versionen und der Veröffentlichungsweg

Die Anwendung wird als **einzelne Datei** veröffentlicht (`LayoutKeep.exe`, ~173 MB, onefile) über
GitHub Releases. Der Weg:

1. Die Version in `pyproject.toml` + `__init__.py` wird erhöht.
2. Gebaut wird mit `PyInstaller packaging/layoutkeep_onefile.spec --noconfirm --clean`.
3. Die vollständige Testsuite läuft.
4. Tag + Release; **die SHA-256 der heruntergeladenen Datei wird mit dem lokalen Build verglichen**.

Die veröffentlichten Versionen und was jede brachte:

| Version | Was sie brachte |
|---|---|
| 0.9.1 | Die erste öffentliche Version: Willkommen, Hilfe, die Glossar-/Gedächtnis-Oberfläche, die Prüfliste |
| 0.9.2 | Der Wechsel Leiste ↔ Fenster; das Willkommen pro Version; Schutz römischer Zahlen (umschaltbar) |
| 0.9.3 | Der ▤-Knopf + Hilfetexte |
| 0.9.4 | **Die Anwendung schickt ihre Anfragen parallel** (in Wellen, in Dokumentreihenfolge zusammengeführt) |
| 0.9.5 | Der tote Einstellungsschlüssel angebunden; die Standard-Parallelität auf 2; der Tooltip der Leiste; ein Bereich verengt die Ausgabe |
| 0.9.6 | **Die gepackte Anwendung kann ihre eigenen Dialoge öffnen** — 0.9.5 warf auf dem Hilfe- und dem Glossarbildschirm `ImportError`, weil `help_dialog` und `glossary_dialog` in der PyInstaller-Liste fehlten (gefunden von der eigenen `check_spec.py`-Prüfung des Projekts; drei Module fehlten seit mehreren Versionen) |
| 0.9.7 | Der Abschlussbildschirm unterscheidet zwei Arten von Prüfmarken: wie viele **gekürzte Boxen** sind (ein Layoutproblem, das Neuübersetzen nicht löst). Der Hilfebildschirm erklärt, was eine Marke heißt |

## 6.10 Die Vergleichsseite

**Was gewünscht war:** *„eine Slider-Website, auf der ich die Originalquellen und ihre Übersetzungen
nebeneinander vergleichen kann, für alle Beispiele."*

Die Seite wird unter `docs/comparison/` erzeugt und auf GitHub Pages veröffentlicht:

- **Ein Einzeldokument-Betrachter**: Original links, Übersetzung rechts, ein ziehbarer Trenner in der
  Mitte; Zoom mit dem Rad; Seitennavigation mit der Tastatur.
- **Eine Prüfzusammenfassung pro Dokument**: die L- und D-Zahlen, die Seitenzahl, das Modell, das
  Datum.
- **24 Dokumente**: arXiv-Arbeiten, das NIST-Journal und -Formular, IRS-Formulare, ein NASA-Bericht
  (digital und gescannt), Project-Gutenberg-Bücher, ein gemeinfreies DOCX, zwei gescannte Seiten.
- **Entwicklungsläufe** sind standardmäßig verborgen und ein Kästchen entfernt — die veröffentlichte
  Liste besteht aus echten Dokumenten.
- **Die Urheberrechtsregel**: Nur offen lizenzierte oder gemeinfreie Quellen werden veröffentlicht;
  geschützte (`NOT_PUBLISHABLE`) bleiben nur auf der Platte des Nutzers.

Die Bilder werden pro Dokument geladen (faul): Das gesamte Archiv ist ~49 MB, was ~1 MB Verkehr pro
Besucher bedeutet. Die 6997×3163-Renderings des NASA-Dokuments wurden auf 3200px begrenzt
(10,4 MB → 1,9 MB) — mehr als genug zum Zoomen und die Hälfte der Daten pro Dokument.

## 6.11 GitHub Pages: die Startseite und die Links

- **Die Wurzel** (`/LayoutKeep/`): die Startseite — der Download, die Vergleichsseite und die
  Geschichte.
- **`/docs/comparison/`**: die Vergleichsseite.
- **`/docs/story/`**: dieses Dokument (mehrseitig), **in drei Sprachen** mit einem Umschalter; ein
  Kapitel ohne Übersetzung zeigt hinter einem sichtbaren Hinweis das Englische (oder, wenn auch das
  fehlt, das türkische Original).
- **Die alte Adresse** (`docs/comparison.html`): die alte 4,4-MB-Einseiterdatei, in eine
  **Weiterleitung** verwandelt, damit geteilte Links nicht brechen.
- **Die READMEs** (EN/TR): Der Download-Link läuft über `releases/latest`; die Schaltflächen zeigen
  auf die aktuelle Seite; der Hinweis „wo der Code in diesem Zweig steht" ist in beiden Sprachen
  dauerhaft (ein Push löschte ihn einmal; er wurde zurückgeholt und wird nun auf beiden Seiten
  gehalten).

## 6.12 Maßstab: die heutigen Zahlen

| | Wert |
|---|---|
| Quellcode | ~24.000 Zeilen (`src/`), 133 Dateien |
| Tests | **1.256 Tests**, 138 Testdateien |
| Prüfwerkzeuge | 56 (`tools/audit/`) |
| Größter echter Lauf | ein 220-seitiges Buch, 55 Teile, ~106 Minuten |
| Größtes einzelnes Dokument | 841 Seiten (vollständig übersetzt ~23% in einem Lauf) |
| Vergleichsseite | 25 Dokumente, 304 Bilder |
| Einstellungen | 30, alle an Code gebunden und getestet |
