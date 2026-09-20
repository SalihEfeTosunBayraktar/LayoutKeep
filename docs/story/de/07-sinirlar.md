# 7. Ehrliche Grenzen, offene Arbeit und Lehren

Der wertvollste Teil eines Ingenieurdokuments ist der Teil, der aufschreibt, was nicht funktioniert.
Dieses Kapitel ist nicht geglättet.

## 7.1 Die heutigen Grenzen (gemessen)

**Literaturverzeichnisse und nummerierte Überschriften.** Im Buchlauf ist L2 = 2: Literaturzeilen und
manche nummerierten Überschriften bleiben in der Ausgangssprache. Sie sind *markiert* (nicht stumm),
aber nicht übersetzt — weil diese Zeilen als „nicht übersetzbar" gelten: Die meisten bestehen aus einem
Autorennamen, einem Zeitschriftentitel, einem Jahr und einem Seitenbereich, und sie zu übersetzen
widerspricht der akademischen Zitierkonvention. Die Entscheidung ist bewusst, aber der Nutzer liest
sie manchmal als „fehlende Übersetzung"; das muss in der Oberfläche besser erklärt werden.

**Blöcke unter der Lesbarkeitsschwelle (D1).** Lange Übersetzungen werden verkleinert; im Buch liegen
801 Blöcke unter der Schwelle. `--fit-mode reflow` beseitigt einen großen Teil dieser Klasse (D1 52 →
0 im NIST-Journal), kann aber in festen Layouts Text über Text zeichnen (L7 0 → 1 im IRS-Formular).
Deshalb ist er standardmäßig **aus**: Ein bewiesener Verlust wiegt schwerer als ein gemessener Gewinn.

**Gescannte Seiten hängen an der OCR-Qualität.** Blöcke mit geringem Vertrauen werden markiert, nicht
korrigiert. Saubere Scans mit 300 dpi sind verlässlich; schiefe, fleckige oder niedrig aufgelöste
nicht. Der NASA-Scan und NISTs gescannter Dampfdruckbericht testen diesen Weg.

**Zahlenreihen.** Läufe blanker Zahlen über eine Tabellenüberschrift (zum Beispiel
`11 34 56 79 101 124`) können zu einem linksbündigen Block zusammenfallen: Die Zahlen überleben, aber
ihre **Anordnung** geht verloren. Das passiert, wo die Tabellenstruktur zu reinem Text wird; die
Lösung führt über eine breitere Tabellenerkennung.

**Rechts-nach-links-Schriften sind nicht umgesetzt.** Das Schema trägt ein `direction`-Feld (D4); der
Schreiber nutzt es nicht. Ein arabisches oder hebräisches Dokument wird heute nicht korrekt übersetzt
— und die Oberfläche sagt das nicht, weil diese Sprachen nicht in der unterstützten Liste stehen.

**Qualität ist die Fähigkeit des Modells.** Die Pipeline verhindert Verlust; sie erzeugt keine
Flüssigkeit. Text aus einem kleinen lokalen Modell ist schwächer als der eines Cloud-Modells; Glossar
und Gedächtnis verkleinern diese Lücke, beseitigen sie nicht.

**Die Prüfliste kann gelesen, nicht bearbeitet werden.** Marken tragen ihren Grund, aber der Nutzer
kann eine Übersetzung nicht im Programm korrigieren und neu schreiben. Das ist der aufwändigste Punkt
der Roadmap.

## 7.2 Die Roadmap (nach Wirkung / Aufwand)

Die Punkte 1, 3 und 7 der früheren Roadmap sind inzwischen **ausgeliefert** — das zweisprachige PDF,
Terminvorschläge aus dem Dokument und die Einstellungsprofile. Was bleibt, mit dem heutigen Stand:

1. **Die Überlappungsleiter** (verkleinern → Zeilenabstand enger setzen → nach unten schieben). Der
   Zeilenabstandsschritt allein wurde am 20.09.2026 gebaut, gemessen und **zurückgenommen**: Mit der
   eigenen Ersatzschrift des Durchlaufs rettete er keinen Block, und das A/B auf der geschriebenen
   Seite war in beiden Armen identisch. Die Messung zeigte auch, wo die eigentliche Arbeit liegt: Den
   meisten markierten Blöcken fehlt nicht die Zeile, sondern die **Box** (`room_below` kann eine
   gemessene Box auf sechs Punkte kürzen). Aufwand: mittel bis hoch. Messung: D1 und die Zahl
   „unlesbare Größe", zusammen mit L7 gelesen.
2. **Ein kleiner Editor** — markierte Blöcke im Programm korrigieren und das Dokument neu schreiben.
   Aufwand: hoch.
3. **Kontext über Seitengrenzen** — an einer Teilgrenze die letzten Blöcke des vorigen Teils in die
   Anfrage aufnehmen; soll L2 und D2 senken.
4. **Ein visueller Seitenwähler für den Bereich** — den Bereich aus kleinen Vorschaubildern wählen.
5. **Die Grenzen in die Oberfläche tragen** — die Unterscheidung D1/Box steht jetzt auf dem
   Abschlussbildschirm (0.9.7); der Hinweis zum Literaturverzeichnis noch nicht.

## 7.3 Lehren

**1. Die Messung kommt vor der Funktion.** Die Behauptung „verlustfrei" ist nur sinnvoll, wenn sie
gezählt werden kann. In diesem Projekt kam jede Funktion mit einer *Zahl*: die L/D-Tabelle,
`type_drift`, der vierteilige visuelle Vergleich.

**2. Eine falsche Messung ist schlimmer als keine Messung.** Die Hälfte von L10, das ganze
„offensichtlich größere Schrift" und ein Teil der Ausrichtungsmarken waren **Messfehler**
(Abschnitt 3.3). Alle drei wurden nur gefunden, indem das Messwerkzeug selbst geprüft wurde. Die
Regel: Sieht eine Zahl zweifelhaft aus, schau zuerst auf das Werkzeug.

**3. Eine unbewiesene Korrektur wird nicht behalten — und ein unbewiesenes Neuschreiben ebenso
wenig.** Der Box-Verbreiterungsversuch wurde durch Messung widerlegt (12 → 12) und zurückgenommen.
Der V2-Neuschreibungsplan hätte für eine einzige Lücke 1.000+ Tests weggeworfen; stattdessen wurde
die Lücke dem bestehenden Motor hinzugefügt.

**4. Dieselbe Fähigkeit braucht zwei Türen: die Kommandozeile und die Oberfläche.** Wir haben
denselben Fehler zweimal gemacht: Glossar und Gedächtnis existierten in der CLI und nicht in der
Oberfläche (4.6); Parallelität existierte in der CLI und nicht in der Anwendung (4.8). Die Lehre: Wird
eine Fähigkeit hinzugefügt, müssen **beide Türen** angebunden werden, sonst gibt es sie für den Nutzer
nicht.

**5. Eine Einstellung, die man nicht sieht, ist eine Einstellung, die nicht wirkt.**
`timeout.first_batch_s` stand im Einstellungsbildschirm und änderte nichts (4.11). Es gibt jetzt einen
Test, der sagt: „jede erklärte Einstellung muss gelesen werden".

**6. Voreinstellungen müssen konservativ sein.** Die Parallelität kam von 7 auf 2: Eine aggressive
Voreinstellung verdirbt dem Nutzer den ersten Eindruck (und bei kleinen Modellen die Qualität). Der
Nutzer kann sie erhöhen; er sollte nicht daran denken müssen, sie zu senken.

**7. Nutzerfeedback ist das beste Testset.** Die meisten Fälle in diesem Dokument beginnen mit einem
Satz des Nutzers: *„obwohl 7 Slots eingestellt sind, schickt es 1"*, *„warum kam das ganze Buch"*,
*„offensichtlich größere Schrift"*, *„wenn ich die Pille schließe, kann ich sie nicht zurückholen."*
Keiner war von der Art, die die 1.256 Tests fangen — sie kamen alle im *Gebrauch* heraus. Die
Testsuite hält Regressionen fest; der Gebrauch findet den neuen Fehler.

**8. Urheberrecht und Privatsphäre sind Teil der Architektur.** Welche Inhalte veröffentlicht werden
(`NOT_PUBLISHABLE`), dass das Dokument die Maschine nicht verlässt (local-first), und dass das
Repository aufgeräumt wurde (36 MB → 12 MB) waren keine später hinzugefügten Funktionen; sie hätten
von Anfang an Teil des Designs sein sollen und sind es jetzt.
