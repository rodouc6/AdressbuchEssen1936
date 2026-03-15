#!/usr/bin/env python3
"""
Schichtenkarte – Soziale Schichtung nach Straßen (Essen 1936)

Erzeugt docs/data/schichten.geojson:
  - Klassifiziert Personen in arm/mittel/reich anhand ihres Berufs
  - Lädt Straßengeometrien via Overpass API (gecacht)
  - Aggregiert pro Straße und erzeugt GeoJSON mit LineStrings
"""

import csv
import json
import os
import re
import statistics
import urllib.request
import urllib.parse
import time
import sys

# ── Pfade ──────────────────────────────────────────────────────────────────

GEOJSON_INPUT = "docs/data/essen1936.geojson"
OSM_CACHE = "strassen_essen_osm.json"
GEOJSON_OUTPUT = "docs/data/schichten.geojson"

# ── Berufs-Klassifikation ─────────────────────────────────────────────────

RE_ARM = re.compile(
    r'\b('
    r'Bergm\.|Hauer|Bergarbeiter|Berginval'
    r'|Arbeiter|Arb\.|Fabrikarb|Fabr\.arb|Hilfsarb'
    r'|Inval\.|Invalide|Rentner|Rentnerin'
    r'|Tagelöhn|Kutscher|Fuhrm\.'
    r')\b', re.IGNORECASE
)

RE_MITTEL = re.compile(
    r'\b('
    r'Schlosser|Dreher|Maurer|Schreiner|Anstreicher|Schmied|Monteur|Former|Friseur'
    r'|Klempner|Tischler|Elektriker|Elektro\-Mont|Installateur|Bäcker|Fleischer|Metzger'
    r'|Kaufm\.|Kfm\.|Vertreter|Buchhalter|Handlungsgeh'
    r'|Bürobeamt|Postbeamt|Polizeibeamt|Beamt\.|Zollbeamt'
    r'|Steiger|Werkmeister|Vorarbeiter|Meister'
    r'|Kraftw|Lokführer|Schaffner|Straßenbahnf'
    r'|Pensionär|Schankw|Gastwirt|Wirt'
    r')\b', re.IGNORECASE
)

RE_REICH = re.compile(
    r'\b('
    r'Dr\.|Prof\.|Dipl\.'
    r'|Ingenieur|Ingen\.|Architekt'
    r'|Direktor|Dir\.|Fabrikant|Prokurist|Konsul|Kommerzienrat|Generaldirektor'
    r'|Lehrer|Lehrerin|Studienrat|Pfarrer|Pastor|Vikar'
    r'|Arzt|Ärztin|Zahnarzt|Tierarzt|Rechtsanwalt|Rechtsanw\.|Notar|Apotheker'
    r'|Bankdir|Oberingenieur|Regierungsrat|Oberregierungsrat|Oberstudienrat'
    r')\b', re.IGNORECASE
)

# Berufsgruppen-Fallback
BG_ARM = {"Rohstoffgewinnung"}
BG_MITTEL = {"Kaufm. Dienstleistungen", "Bau", "Verkehr"}
BG_REICH = {"Gesundheit", "Geisteswiss. & Kunst", "Naturwissenschaft", "Unternehmensorganisation"}


def classify_person(beruf, berufsgruppe, akademiker):
    """Gibt Score zurück: 1=arm, 2=mittel, 3=reich, 1.5=sonstige/unbekannt."""
    if not beruf and not berufsgruppe:
        return 1.5

    beruf_str = beruf or ""

    # Spezifische Regex-Matches haben Vorrang
    if RE_REICH.search(beruf_str) or akademiker:
        return 3
    if RE_ARM.search(beruf_str):
        return 1
    if RE_MITTEL.search(beruf_str):
        return 2

    # Fallback: Berufsgruppe
    bg = berufsgruppe or ""
    if bg in BG_REICH:
        return 3
    if bg in BG_ARM:
        return 1
    if bg in BG_MITTEL:
        return 2

    # Sonstige / unbekannt
    return 1.5


# ── Straßenname aus Adresse extrahieren ───────────────────────────────────

def extract_street(adresse):
    """Extrahiert den Straßennamen aus 'Straße 42, Stadtteil, Essen'."""
    if not adresse:
        return None
    # Erster Teil vor dem Komma
    teil = adresse.split(",")[0].strip()
    # Hausnummer entfernen (letzte Zahl(en) am Ende, ggf. mit Buchstabe/Leerzeichen)
    teil = re.sub(r'\s+\d+\s*[a-zA-Z]?\s*$', '', teil)
    return teil if teil else None


def normalize_street(name):
    """Normalisiert Straßenabkürzungen für den OSM-Abgleich."""
    s = name
    s = re.sub(r'str\.$', 'straße', s)
    s = re.sub(r'Str\.$', 'Straße', s)
    s = re.sub(r'pl\.$', 'platz', s)
    s = re.sub(r'Pl\.$', 'Platz', s)
    return s


# ── Aggregation pro Straße ────────────────────────────────────────────────

def aggregate_streets(geojson_path):
    """Liest das GeoJSON und aggregiert Scores pro Straßenname."""
    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)

    streets = {}  # straßenname → Liste von Scores

    for feat in data["features"]:
        props = feat["properties"]
        adresse = props.get("adresse", "")
        strasse = extract_street(adresse)
        if not strasse:
            continue

        personen = props.get("personen", [])
        if isinstance(personen, str):
            personen = json.loads(personen)

        for p in personen:
            score = classify_person(
                p.get("beruf", ""),
                p.get("berufsgruppe", ""),
                p.get("akademiker", False)
            )
            streets.setdefault(strasse, []).append(score)

    return streets


def classify_street(scores):
    """Klassifiziert eine Straße anhand der Scores ihrer Bewohner."""
    if len(scores) < 10:
        return None

    avg = statistics.mean(scores)
    std = statistics.stdev(scores) if len(scores) > 1 else 0

    # Gemischt: hohe Standardabweichung
    if std > 0.7:
        schicht = "gemischt"
    elif avg <= 1.45:
        schicht = "arm"
    elif avg <= 1.9:
        schicht = "mittel"
    else:
        schicht = "reich"

    count_arm = sum(1 for s in scores if s <= 1)
    count_mittel = sum(1 for s in scores if 1 < s <= 2)
    count_reich = sum(1 for s in scores if s > 2)

    return {
        "schicht": schicht,
        "score": round(avg, 2),
        "std": round(std, 2),
        "anzahl_personen": len(scores),
        "anzahl_arm": count_arm,
        "anzahl_mittel": count_mittel,
        "anzahl_reich": count_reich,
    }


# ── Overpass API ──────────────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OVERPASS_QUERY = """
[out:json][timeout:120];
area["name"="Essen"]["admin_level"="6"]->.a;
way["highway"]["name"](area.a);
out geom;
"""


def fetch_osm_streets(cache_path):
    """Lädt alle Straßen-Ways aus Essen via Overpass API (mit Caching)."""
    if os.path.exists(cache_path):
        print(f"  OSM-Cache gefunden: {cache_path}")
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    print("  Lade Straßengeometrien von Overpass API ...")
    data = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, method="POST")
    req.add_header("User-Agent", "AdressbuchEssen1936/1.0")

    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    print(f"  Gespeichert: {cache_path} ({len(result.get('elements', []))} Ways)")

    return result


def build_street_geometries(osm_data):
    """Baut ein Dict: Straßenname → Liste von Koordinaten-Listen (MultiLineString)."""
    streets = {}
    for el in osm_data.get("elements", []):
        if el.get("type") != "way":
            continue
        name = el.get("tags", {}).get("name")
        if not name:
            continue
        geom = el.get("geometry", [])
        if not geom:
            continue
        coords = [[pt["lon"], pt["lat"]] for pt in geom]
        streets.setdefault(name, []).append(coords)
    return streets


# ── GeoJSON erzeugen ──────────────────────────────────────────────────────

def create_geojson(street_scores, street_geometries, output_path):
    """Kombiniert Scores und Geometrien zu einem GeoJSON."""
    features = []
    matched = 0
    unmatched = []

    for strasse, scores in sorted(street_scores.items()):
        info = classify_street(scores)
        if info is None:
            continue  # zu wenige Personen

        # Versuche exakten Match, dann normalisierten Match
        norm = normalize_street(strasse)
        if strasse in street_geometries:
            coords = street_geometries[strasse]
        elif norm in street_geometries:
            coords = street_geometries[norm]
        else:
            unmatched.append(strasse)
            continue
        geometry = {
            "type": "MultiLineString" if len(coords) > 1 else "LineString",
            "coordinates": coords if len(coords) > 1 else coords[0],
        }

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "strasse": strasse,
                **info,
            },
        })
        matched += 1

    geojson = {"type": "FeatureCollection", "features": features}

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False)

    return matched, unmatched


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=== Schichtenkarte: Datenaufbereitung ===\n")

    # 1. Berufe klassifizieren und pro Straße aggregieren
    print("1. Berufe klassifizieren und aggregieren ...")
    street_scores = aggregate_streets(GEOJSON_INPUT)
    total_streets = len(street_scores)
    qualifying = sum(1 for s in street_scores.values() if len(s) >= 10)
    print(f"   {total_streets} Straßen gefunden, {qualifying} mit >= 10 Personen")

    # 2. Straßengeometrien laden
    print("\n2. Straßengeometrien laden ...")
    osm_data = fetch_osm_streets(OSM_CACHE)
    street_geometries = build_street_geometries(osm_data)
    print(f"   {len(street_geometries)} Straßen in OSM-Daten")

    # 3. GeoJSON erzeugen
    print("\n3. GeoJSON erzeugen ...")
    matched, unmatched = create_geojson(street_scores, street_geometries, GEOJSON_OUTPUT)
    print(f"   {matched} Straßen im GeoJSON")
    if unmatched:
        print(f"   {len(unmatched)} Straßen nicht in OSM gefunden")
        if len(unmatched) <= 30:
            for s in sorted(unmatched):
                print(f"     - {s}")
        else:
            for s in sorted(unmatched)[:20]:
                print(f"     - {s}")
            print(f"     ... und {len(unmatched) - 20} weitere")

    # 4. Statistik
    print("\n4. Verteilung:")
    with open(GEOJSON_OUTPUT, encoding="utf-8") as f:
        result = json.load(f)
    counts = {"arm": 0, "mittel": 0, "reich": 0, "gemischt": 0}
    for feat in result["features"]:
        counts[feat["properties"]["schicht"]] += 1
    for schicht, n in sorted(counts.items()):
        print(f"   {schicht}: {n} Straßen")

    print(f"\n=== Fertig: {GEOJSON_OUTPUT} ===")


if __name__ == "__main__":
    main()
