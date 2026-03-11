#!/usr/bin/env python3
"""
Batch-Geocodierung für essen1936_geovorbereitung.csv.

Ablauf:
  1. Alle unique geoadresses gegen lokalen Nominatim-Server abfragen.
  2. Ergebnisse in geocoding_cache.csv speichern (Resume-fähig).
  3. Koordinaten in essen1936_geovorbereitung.csv einjoinen.
  4. Alle Zeilen mit Koordinaten als GeoJSON exportieren.

Resume: Wird das Script unterbrochen und neu gestartet, überspringt es
bereits gecachte Adressen und macht nahtlos weiter.
"""

import csv
import json
import time
from pathlib import Path

import requests

NOMINATIM_URL  = "http://localhost:8080/search"
UNIQUE_FILE    = Path("unique_geoadresses.csv")
CACHE_FILE     = Path("geocoding_cache.csv")
INPUT_FILE     = Path("essen1936_geovorbereitung.csv")
GEOJSON_FILE   = Path("essen1936.geojson")

# Felder die ins GeoJSON übernommen werden
GEOJSON_FELDER = [
    "page", "lastname", "firstname", "Beruf o. ä.",
    "Adresse", "Ortsname", "geoadresse", "id"
]


# ---------------------------------------------------------------------------
# Schritt 1: Geocodierung
# ---------------------------------------------------------------------------

def geocode(adresse: str, session: requests.Session) -> tuple[float, float] | None:
    """Fragt Nominatim an und gibt (lat, lon) zurück, oder None bei keinem Treffer."""
    try:
        r = session.get(NOMINATIM_URL, params={
            "q":            adresse,
            "format":       "json",
            "limit":        1,
            "countrycodes": "de",
        }, timeout=10)
        hits = r.json()
        if hits:
            return float(hits[0]["lat"]), float(hits[0]["lon"])
    except Exception:
        pass
    return None


def load_cache(path: Path) -> dict[str, tuple[float, float] | None]:
    """Lädt bereits gecachte Ergebnisse: {geoadresse: (lat, lon) oder None}."""
    cache: dict[str, tuple[float, float] | None] = {}
    if not path.exists():
        return cache
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lat = row["lat"]
            lon = row["lon"]
            if lat and lon:
                cache[row["geoadresse"]] = (float(lat), float(lon))
            else:
                cache[row["geoadresse"]] = None
    return cache


def run_geocodierung() -> dict[str, tuple[float, float] | None]:
    """Geocodiert alle unique geoadresses, mit Resume-Unterstützung."""
    # Alle zu geocodierenden Adressen laden
    with open(UNIQUE_FILE, newline="", encoding="utf-8") as f:
        alle = [row[0] for row in csv.reader(f) if row][1:]  # Header überspringen

    # Cache laden (bereits abgearbeitete überspringen)
    cache = load_cache(CACHE_FILE)
    ausstehend = [a for a in alle if a not in cache]

    print(f"Gesamt unique geoadresses : {len(alle):>7}")
    print(f"Bereits im Cache          : {len(cache):>7}")
    print(f"Noch zu geocodieren       : {len(ausstehend):>7}")

    if not ausstehend:
        print("Alle Adressen bereits gecacht.")
        return cache

    # Cache-Datei zum Anhängen öffnen
    cache_neu = not CACHE_FILE.exists()
    with (
        open(CACHE_FILE, "a", newline="", encoding="utf-8") as cachefile,
        requests.Session() as session,
    ):
        writer = csv.writer(cachefile)
        if cache_neu:
            writer.writerow(["geoadresse", "lat", "lon"])

        treffer = 0
        kein_treffer = 0
        start = time.time()

        for i, adr in enumerate(ausstehend, 1):
            result = geocode(adr, session)

            if result:
                lat, lon = result
                writer.writerow([adr, lat, lon])
                cache[adr] = result
                treffer += 1
            else:
                writer.writerow([adr, "", ""])
                cache[adr] = None
                kein_treffer += 1

            # Fortschrittsanzeige alle 500 Adressen
            if i % 500 == 0 or i == len(ausstehend):
                elapsed = time.time() - start
                pro_sek = i / elapsed if elapsed > 0 else 0
                verbleibend = (len(ausstehend) - i) / pro_sek if pro_sek > 0 else 0
                print(
                    f"  {i:>6}/{len(ausstehend)}  |  "
                    f"Treffer: {treffer}  Kein Treffer: {kein_treffer}  |  "
                    f"{pro_sek:.0f} Adr/s  |  "
                    f"noch ~{verbleibend/60:.1f} min"
                )
            cachefile.flush()

    print(f"\nGeocodierung abgeschlossen.")
    print(f"  Treffer     : {treffer}")
    print(f"  Kein Treffer: {kein_treffer}")
    return cache


# ---------------------------------------------------------------------------
# Schritt 2: GeoJSON exportieren
# ---------------------------------------------------------------------------

def export_geojson(cache: dict[str, tuple[float, float] | None]) -> None:
    """Liest essen1936_geovorbereitung.csv und exportiert geocodierte Zeilen als GeoJSON."""

    features = []
    gesamt = 0
    mit_koordinaten = 0
    ohne_koordinaten = 0

    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gesamt += 1
            geoadresse = row.get("geoadresse", "").strip()

            if not geoadresse or geoadresse not in cache or cache[geoadresse] is None:
                ohne_koordinaten += 1
                continue

            lat, lon = cache[geoadresse]
            mit_koordinaten += 1

            properties = {feld: row.get(feld, "") for feld in GEOJSON_FELDER}

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],  # GeoJSON: [lon, lat]
                },
                "properties": properties,
            })

    geojson = {
        "type":     "FeatureCollection",
        "features": features,
    }

    with open(GEOJSON_FILE, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False)

    print(f"\nGeoJSON-Export:")
    print(f"  Gesamt Zeilen      : {gesamt:>7}")
    print(f"  Mit Koordinaten    : {mit_koordinaten:>7}")
    print(f"  Ohne Koordinaten   : {ohne_koordinaten:>7}")
    print(f"  Ausgabe            : {GEOJSON_FILE}  "
          f"({GEOJSON_FILE.stat().st_size / 1_000_000:.1f} MB)")


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Schritt 1: Geocodierung ===\n")
    cache = run_geocodierung()

    print("\n=== Schritt 2: GeoJSON-Export ===\n")
    export_geojson(cache)

    print("\nFertig.")


if __name__ == "__main__":
    main()
