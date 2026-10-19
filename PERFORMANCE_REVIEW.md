# Performance-Prüfung – 16.10.2026

Referenz: main `dfb6d75b7f50391499d366aa37be6a0bfdbf1cb8`.
Geprüfter Anwendungscode: Blob `60d24761ec8d4820a06a3520c669de6f283b6b82`.

## Kontrollierter Browservergleich

Chromium, 1365 × 936 Pixel. Beide Versionen verwenden identische lokale Antworten für die unveränderten Daten und Bibliotheken. OSM-Bildkacheln sind durch ein Ein-Pixel-Testbild ersetzt. Erfasst wird die vollständige aktuelle Bedarfs-Kacheldarstellung nach Ende der Kartenanimation, nicht nur das erste Suchergebnis. Die öffentliche Netzwerkübertragung ist ausdrücklich nicht enthalten. Einzelmessungen sind keine garantierten Produktions-Ladezeiten.

| Vorgang | Bisher | Optimiert | Längste Blockade bisher / optimiert |
|---|---:|---:|---:|
| Kartenaufbau inkl. Regionaldaten | 5.007 ms | 3.934 ms | 2.998 / 377 ms |
| Mixed-Standortfilter aus | 1.613 ms | 76 ms | 1.529 / keine ≥50 ms |
| Roter Bedarfsfilter aus | 1.544 ms | 480 ms | 1.456 / 78 ms |
| Zoom 6 → 7 | 2.709 ms | 1.696 ms | 2.359 / 84 ms |
| Verschieben um 160 Pixel | 688 ms | 514 ms | keine ≥50 ms |
| Frankfurt-Suche, vollständige Flächen | 17.998 ms | 12.547 ms | 14.142 / 174 ms |

Die vollständige Suchzeichnung bleibt rechenintensiv. Die Oberfläche bleibt während der inkrementellen Zeichnung deutlich besser bedienbar. Der frühere vorläufige Suchwert von etwa 0,6 Sekunden erfasste nicht alle fertigen Flächen und ist kein End-to-End-Ergebnis. Es traten keine JavaScript-Seitenfehler auf; Frankfurt-Popup und Liste der 13 erreichbaren Fahrzeitgebiete sind exakt identisch.

## Ergebnisgleichheit und Funktionen

- 19.319 Abdeckungspunkte: identische Light-/Heavy-Abdeckung, Bedarfskategorie und geordnete Isochronenliste.
- 249.572 Ländergrenzenpunkte: keine Abweichung, einschließlich Rastergrenzen, Polygonpunkte, Kantenmittelpunkte, Inseln und Löchern.
- 15 Canvas-Vergleiche: identische Zeichenbefehle über drei Ausschnitte und fünf Bedarfsfilterzustände.
- 10.754 Regionaldatensätze: identische 1.334 Hotspots einschließlich Geometrien, Darstellung und Beschriftung.
- Absichtlich verspätete Suchantworten, Abbruch, Leeren, lokale Suche, externe Suche und Netzwerkfehler geprüft.
- Cloud-Browser: alle BU- und Bedarfsfilter, Standort-Hauptschalter, Zoom, Verschieben, Ort/PLZ/KST-Suche, externe Ortssuche, Standortklicks und Regional-KPIs geprüft.
- Interner Modus nach Nutzeranmeldung: Hotspot-Ebene ein/aus und Klick auf Brilon geprüft. Tooltip und Popup zeigen 70/100, ohne Light-/Heavy-Abdeckung.
- `daten.csv`, `isochronen.json` und `regionaldaten.json` unverändert.
- JavaScript-Syntax und Whitespace-Prüfung erfolgreich. Im Repository sind keine PR-Prüfworkflows eingerichtet.

## Reproduzieren

Die Node-Regressionsskripte unter `tests/` dokumentieren ihre Aufrufe in der ersten Zeile. `browser-performance.cjs` benötigt Playwright, Chromium und lokale Fixtures: Turf v7, Leaflet 1.9.4 JS/CSS, PapaParse 5.3.2 sowie die unveränderte Deutschland-GeoJSON-Datei des bisherigen Codes. `BROWSER_EXECUTABLE` und `RESULT_PATH` sind optional.

Die ursprüngliche Cloud-Vorschau erlaubte keinen verlässlichen Netzwerk-Ladevergleich; deshalb wurde dieser kontrollierte lokale Browservergleich ergänzt. Die früher dokumentierte Browser-Blockade ist damit aufgelöst, ohne eine Verbesserung öffentlicher Übertragungszeiten zu behaupten.


## Nachoptimierung – 19.10.2026

Vergleich gegen main `ecb3bad` mit identischen aktuellen Daten (389 Standorte, 385 Fahrzeitgebiete, 10.754 Regionen). Chromium 153, lokale identische Antworten einschließlich Worker-Abhängigkeit, keine Produktions-Netzwerklatenz. Messwerte sind Einzelmessungen.

| Vorgang | Vorher | Nachher |
|---|---:|---:|
| Kartenaufbau | 3.292 ms | 2.746 ms |
| Zoom 6 → 7 | 1.593 ms | 483 ms |
| Verschieben | 480 ms | 441 ms |
| Frankfurt-Suche inkl. fertiger Bedarfsflächen | 552 ms | 489 ms |
| Erster roter Bedarfsfilter aus | 123 ms | 171 ms |
| Erneuter Bedarfsfilter | 248 ms | 235 ms |
| Erstmaliges Anzeigen interner Hotspots | 111 ms | 570 ms |

Die schnellere zeilenweise Flächenklassifikation wird jetzt auch für große Kartenausschnitte genutzt. Vollständig berechnete Kacheln umgehen den Worker bei erneuter Anzeige. Regionale Popup-Abfragen überspringen Polygone nach exakter Bounding-Box-Prüfung. Die interne Hotspot-Geometrie wird erst bei Bedarf aufgebaut: Dadurch entfällt die Arbeit im normalen Betrieb, beim ersten Freischalten entsteht dafür zusätzlicher Aufwand. Die automatische Aktivierung des Hotspot-Schalters nach Login bleibt erhalten. Nicht jeder Filtervorgang ist schneller; der deutlichste Gewinn liegt beim Zoomen.

Validiert: 19.305 exakte Abdeckungspunkte, 10.620 Zeilenklassifikationen einschließlich Polygonkanten und angrenzender Punkte, 96 unveränderte Regional-Popups, 1.334 identische Hotspot-Geometrien samt Stil und Labels, Suchabbruch und veraltete Suchantworten, kompletter Kachelcache ohne Worker-Aufruf. Kontrollierter Browservergleich inklusive Standortfilter, Bedarfsfilter, Zoom, Verschieben, Frankfurt-Popup, interner Ebene und Abschalten erfolgreich; keine Seitenfehler. Syntax und Whitespace geprüft. Daten und fachliche Regeln unverändert.

Reproduzierbare aktuelle Vergleichsreferenz: `BASELINE_REF=ecb3bad`; die aktualisierten Browser- und Coverage-Skripte verwenden andernfalls HEAD. Ergebnisdatei: `tests/browser-performance-results-2026-10-19.json`.
