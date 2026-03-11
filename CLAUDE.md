# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Dieses Projekt macht das historische Adressbuch der Stadt Essen von 1936 (`essen1936.csv`) der Öffentlichkeit zugänglich – als interaktive Karte und statistische Auswertung auf einer Website.

**Arbeitsschritte (in dieser Reihenfolge):**
1. **CSV-Bereinigung:** In einigen Zeilen sind Angaben um eine oder mehrere Spalten nach rechts gerutscht – diese Verschiebungen müssen erkannt und korrigiert werden.
2. **Geocodierung:** Historische Adressen müssen heutigen Straßennamen zugeordnet und dann geocodiert werden.
3. **Kartierung & Statistik:** Auf Basis der geocodierten Daten wird eine öffentliche Website mit Karte und statistischen Auswertungen erstellt.

## Struktur der Spalte `page`

Die Spalte `page` kodiert den Abschnitt und die Seitenzahl im gedruckten Adressbuch (römische Zahl – arabische Zahl):

| Abschnitt | Inhalt |
|-----------|--------|
| I | Einwohnerverzeichnis Stadt Essen |
| II | Einwohner und Firmen, geordnet nach Straßen und Hausnummern |
| III | Branchen-Verzeichnis: Handel- und Gewerbetreibende alphabetisch nach Erwerbs-/Berufszweigen |
| IV | Behörden, Kirchen, Schulen, öffentliche Einrichtungen, Handels- und Genossenschaftsregister, Verbände, Vereine, Zeitungen und Zeitschriften |

## Running the Scraper

```bash
# Activate virtual environment first
source Konkordanz/venv/bin/activate

# Run the Wikipedia scraper (scrapes 48 district pages, ~2 min due to rate limiting)
python Konkordanz/essen_strassennamen_scraper.py
```

Output: `Konkordanz/Essener_Strassennamen_Konkordanz.xlsx`

## Key Data Files

| File | Size | Description |
|------|------|-------------|
| `essen1936.csv` | 24 MB, 242.605 Zeilen | Historische Adressen. Spalten: `page`, `lastname`, `firstname`, `Beruf o. ä.`, `Adresse`, `Ortsname`, `Ortskennung`, `Firmenname`, `Familienstand`, `Vorname Bezugsperson`, `Beruf Bezugsperson`, `Eigentümer`, `Funktionsträger`, `abweichender Wohnort`, `Vorort`, `Verwalter`, `id` |
| `2024_01_01 Straßenabschnittsverzeichnis Stadt Essen.CSV` | 340 KB, 6.689 Zeilen | Aktuelles Straßenverzeichnis (Straßenname, Stadtbezirk, Stadtteil, Hausnummernbereiche) |
| `ausnahmen_verschiebungen` | 4 KB | Namensvarianten für den Abgleich: Titel (Dr., Prof.), Präpositionen (von, van, v.d.), Qualifier (sen., jun.) |
| `Konkordanz/Essener_Strassennamen_Konkordanz.xlsx` | generiert | Konkordanz ehemaliger/heutiger Straßennamen je Stadtteil (aus Wikipedia gescrapt) |

## Scraper-Konfiguration (in Script eingebettet)

- `STADTTEILE`: Liste der 48 Essener Stadtteile
- `BASE_URL`: `https://de.wikipedia.org/wiki/Liste_der_Straßen_in_Essen-{stadtteil}`
- `PAUSE_SEKUNDEN`: 1,5 s Pause zwischen Requests
- Excel-Ausgabe: Sheet 1 = „Ehemalige Straßennamen" (Spalten: Stadtteil, Ehem. Straßenname, Heutiger Straßenname, Zeitraum von/bis, Bemerkungen), Sheet 2 = „Hinweise" (Metadaten)

## Primärquelle

Erwin Dickhoff: *Essener Straßen* (2015, Klartext-Verlag, ISBN 978-3-8375-1231-1)
