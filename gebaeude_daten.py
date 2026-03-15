#!/usr/bin/env python3
"""
Gebäude-Schichtenkarte – Spatial Join: OSM-Gebäude × Straßen-Schichten

1. Lädt ~150k Gebäudepolygone aus Essen via Overpass API (gecacht)
2. Lädt schichten.geojson (klassifizierte Straßen)
3. Spatial Join: Jedes Gebäude → nächste klassifizierte Straße (cKDTree)
4. Erzeugt gebaeude_schichten_raw.geojson für tippecanoe
"""

import json
import math
import os
import sys
import urllib.request
import urllib.parse

try:
    import numpy as np
    from scipy.spatial import cKDTree
except ImportError:
    print("Fehler: numpy und scipy müssen installiert sein.")
    print("  pip install numpy scipy")
    sys.exit(1)

# ── Pfade ──────────────────────────────────────────────────────────────────

SCHICHTEN_GEOJSON = "docs/data/schichten.geojson"
OSM_CACHE = "gebaeude_essen_osm.json"
OUTPUT_GEOJSON = "gebaeude_schichten_raw.geojson"

# ── Overpass: Gebäude laden ────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OVERPASS_QUERY = """
[out:json][timeout:300];
area["name"="Essen"]["admin_level"="6"]->.a;
way["building"](area.a);
out geom;
"""


def fetch_buildings(cache_path):
    """Lädt alle Gebäude-Ways aus Essen via Overpass API (mit Caching)."""
    if os.path.exists(cache_path):
        print(f"  Cache gefunden: {cache_path}")
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    print("  Lade Gebäude von Overpass API (kann 30-60s dauern) ...")
    data = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, method="POST")
    req.add_header("User-Agent", "AdressbuchEssen1936/1.0")

    with urllib.request.urlopen(req, timeout=600) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f)

    n = len(result.get("elements", []))
    print(f"  Gespeichert: {cache_path} ({n} Gebäude)")
    return result


# ── Straßen-Punkte samplen ─────────────────────────────────────────────────

# Umrechnung Grad → Meter bei ~51.45° Breite
LAT_TO_M = 111320.0
LON_TO_M = 111320.0 * math.cos(math.radians(51.45))
MAX_DIST_M = 150.0  # Max. Zuordnungsdistanz in Metern
SAMPLE_STEP_M = 20.0  # Abstand der Sample-Punkte entlang der Straße


def sample_line_points(coords, step_m):
    """Samplet Punkte entlang einer Linie alle ~step_m Meter."""
    points = []
    for i in range(len(coords) - 1):
        x0, y0 = coords[i]
        x1, y1 = coords[i + 1]
        dx = (x1 - x0) * LON_TO_M
        dy = (y1 - y0) * LAT_TO_M
        seg_len = math.sqrt(dx * dx + dy * dy)
        if seg_len < 1:
            continue
        n_steps = max(1, int(seg_len / step_m))
        for j in range(n_steps + 1):
            t = j / n_steps
            points.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    return points


def build_street_index(schichten_path):
    """Baut einen cKDTree aus gesampelten Straßenpunkten.

    Returns: (tree, street_props) wobei street_props[i] die Properties
    der Straße enthält, die zum i-ten Punkt gehört.
    """
    with open(schichten_path, encoding="utf-8") as f:
        data = json.load(f)

    all_points = []  # [(x_m, y_m), ...]
    point_to_street = []  # Index → Feature-Properties

    for feat in data["features"]:
        props = feat["properties"]
        geom = feat["geometry"]

        # Koordinaten extrahieren (LineString oder MultiLineString)
        if geom["type"] == "LineString":
            lines = [geom["coordinates"]]
        elif geom["type"] == "MultiLineString":
            lines = geom["coordinates"]
        else:
            continue

        street_info = {
            "strasse": props.get("strasse", ""),
            "schicht": props.get("schicht", ""),
            "score": props.get("score", 0),
        }

        for line in lines:
            pts = sample_line_points(line, SAMPLE_STEP_M)
            for lon, lat in pts:
                all_points.append((lon * LON_TO_M, lat * LAT_TO_M))
                point_to_street.append(street_info)

    print(f"  {len(data['features'])} Straßen → {len(all_points)} Sample-Punkte")

    arr = np.array(all_points)
    tree = cKDTree(arr)
    return tree, point_to_street


# ── Spatial Join ───────────────────────────────────────────────────────────

def process_buildings(osm_data, tree, point_to_street):
    """Ordnet jedes Gebäude der nächsten klassifizierten Straße zu."""
    features = []
    total = 0
    matched = 0
    unmatched = 0

    elements = osm_data.get("elements", [])

    for el in elements:
        if el.get("type") != "way":
            continue
        geom_pts = el.get("geometry", [])
        if len(geom_pts) < 3:
            continue

        total += 1

        # Polygon-Koordinaten
        coords = [[pt["lon"], pt["lat"]] for pt in geom_pts]
        # Ring schließen falls nötig
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        # Centroid (Mittelwert, reicht für die Zuordnung)
        n_pts = len(coords) - 1  # ohne doppelten Schlusspunkt
        cx = sum(c[0] for c in coords[:n_pts]) / n_pts
        cy = sum(c[1] for c in coords[:n_pts]) / n_pts

        # KDTree-Query
        query_pt = np.array([cx * LON_TO_M, cy * LAT_TO_M])
        dist, idx = tree.query(query_pt)

        props = {}
        if dist <= MAX_DIST_M:
            street_info = point_to_street[idx]
            props["schicht"] = street_info["schicht"]
            props["score"] = street_info["score"]
            props["strasse"] = street_info["strasse"]
            matched += 1
        else:
            props["schicht"] = ""
            props["score"] = 0
            props["strasse"] = ""
            unmatched += 1

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
            "properties": props,
        })

        if total % 25000 == 0:
            print(f"    {total} Gebäude verarbeitet ...")

    return features, total, matched, unmatched


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("=== Gebäude-Schichtenkarte: Datenaufbereitung ===\n")

    # 1. Gebäude laden
    print("1. Gebäudepolygone laden ...")
    osm_data = fetch_buildings(OSM_CACHE)
    n_elements = len(osm_data.get("elements", []))
    print(f"   {n_elements} Elemente geladen")

    # 2. Straßen-Index aufbauen
    print("\n2. Straßen-Index aufbauen ...")
    tree, point_to_street = build_street_index(SCHICHTEN_GEOJSON)

    # 3. Spatial Join
    print("\n3. Spatial Join: Gebäude → nächste Straße ...")
    features, total, matched, unmatched = process_buildings(
        osm_data, tree, point_to_street
    )
    pct = round(matched / total * 100, 1) if total else 0
    print(f"   {total} Gebäude gesamt")
    print(f"   {matched} zugeordnet ({pct}%)")
    print(f"   {unmatched} nicht zugeordnet (> {MAX_DIST_M}m)")

    # 4. GeoJSON schreiben
    print(f"\n4. GeoJSON schreiben → {OUTPUT_GEOJSON} ...")
    geojson = {"type": "FeatureCollection", "features": features}
    with open(OUTPUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False)

    size_mb = os.path.getsize(OUTPUT_GEOJSON) / (1024 * 1024)
    print(f"   {size_mb:.1f} MB geschrieben")

    print(f"\n=== Fertig! Nächster Schritt: ===")
    print(f"tippecanoe \\")
    print(f"  -o docs/data/gebaeude_schichten.pmtiles \\")
    print(f"  -Z 10 -z 16 \\")
    print(f"  --no-feature-limit --no-tile-size-limit \\")
    print(f"  -l gebaeude \\")
    print(f"  --coalesce-densest-as-needed \\")
    print(f"  --extend-zooms-if-still-dropping \\")
    print(f"  {OUTPUT_GEOJSON}")


if __name__ == "__main__":
    main()
