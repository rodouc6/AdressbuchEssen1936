#!/usr/bin/env python3
"""
Transformiert essen1936.geojson (206k Einzel-Features) in:
  - website/data/essen1936.geojson   (adress-gruppiert, ~40-50k Features)
  - website/data/statistiken.json    (vorberechnete Aggregationen)
"""
import csv
import json
import re
from collections import defaultdict, Counter
from pathlib import Path

INPUT_GEOJSON = Path("essen1936.geojson")
ABKUERZUNGEN_FILE = Path("abkuerzungen_aufloesung.csv")
MAPPING_FILE = Path("berufe_mapping.csv")
OUT_DIR = Path("website/data")
OUT_GEOJSON = OUT_DIR / "essen1936.geojson"
OUT_STATISTIKEN = OUT_DIR / "statistiken.json"

AKADEMIKER_RE = re.compile(r'\b(Dr\.?|Prof\.?|Dipl\.?|Ing\.?|Mag\.?)\b', re.IGNORECASE)

GESCHOSS_RE = re.compile(
    r'\s+(XV\.?|XIV\.?|XIII\.?|XII\.?|XI\.?|X\.?|IX\.?|VIII\.?|VII\.?|VI\.?|IV\.?|V\.?|III\.?|II\.?|I\.?'
    r'|Erdg\.?|Untg\.?|Part\.?|Hh\.?)$',
    re.IGNORECASE
)


def extract_geschoss(adresse: str) -> str:
    m = GESCHOSS_RE.search(adresse or "")
    return m.group(1).rstrip(".") if m else ""


def is_akademiker(row: dict) -> bool:
    for field in ("lastname", "firstname", "Beruf o. ä."):
        val = row.get(field) or ""
        if AKADEMIKER_RE.search(val):
            return True
    return False


def lade_abkuerzungen(pfad: Path) -> dict:
    mapping = {}
    with open(pfad, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            abk = row["Abkürzung"]
            afl = row["Auflösung"].strip()
            if abk and afl:
                mapping[abk] = afl
    return mapping


def normiere(beruf: str, abk_mapping: dict) -> str:
    if not beruf.strip():
        return beruf
    tokens = beruf.split()
    normiert = []
    for tok in tokens:
        pre, kern, suf = "", tok, ""
        while kern and kern[0] in "([":
            pre += kern[0]; kern = kern[1:]
        while kern and kern[-1] in ")],:;":
            suf = kern[-1] + suf; kern = kern[:-1]
        ersatz = abk_mapping.get(kern)
        normiert.append(pre + (ersatz if ersatz else kern) + suf)
    return " ".join(normiert)


def lade_berufsgruppen(pfad: Path) -> dict:
    mapping = {}
    with open(pfad, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mapping[row["Beruf"]] = row["Berufsgruppe"]
    return mapping


def get_berufsgruppe(beruf: str, abk_mapping: dict, bg_mapping: dict) -> str:
    if not beruf.strip():
        return "sonstige"
    norm = normiere(beruf, abk_mapping)
    return bg_mapping.get(norm, "sonstige")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    abk_mapping = lade_abkuerzungen(ABKUERZUNGEN_FILE)
    print(f"Abkürzungen geladen: {len(abk_mapping)} Einträge")
    bg_mapping = lade_berufsgruppen(MAPPING_FILE)
    print(f"Berufsgruppen-Mapping geladen: {len(bg_mapping)} Einträge")

    print(f"Lese {INPUT_GEOJSON} …")
    with open(INPUT_GEOJSON, encoding="utf-8") as f:
        data = json.load(f)

    features = data["features"]
    print(f"  {len(features):,} Einzel-Features geladen")

    # Gruppiere nach geoadresse (= eindeutige Adresse mit Koordinate)
    groups: dict[str, dict] = {}  # geoadresse → group dict

    berufe_counter: Counter = Counter()
    nachnamen_counter: Counter = Counter()
    stadtteile_counter: Counter = Counter()

    for feat in features:
        props = feat["properties"]
        geo = feat["geometry"]
        geoadresse = props.get("geoadresse") or ""
        if not geoadresse or geo is None:
            continue

        beruf = (props.get("Beruf o. ä.") or "").strip()
        nachname = (props.get("lastname") or "").strip()
        ortsname = (props.get("Ortsname") or "").strip()

        # Statistiken
        if beruf:
            berufe_counter[beruf] += 1
        if nachname:
            nachnamen_counter[nachname] += 1
        if ortsname:
            stadtteile_counter[ortsname] += 1

        berufsgruppe = get_berufsgruppe(beruf, abk_mapping, bg_mapping)
        geschoss = extract_geschoss(props.get("Adresse") or "")

        person = {
            "nachname": nachname,
            "vorname": (props.get("firstname") or "").strip(),
            "beruf": beruf,
            "seite": (props.get("page") or "").strip(),
            "akademiker": is_akademiker(props),
            "berufsgruppe": berufsgruppe,
            "geschoss": geschoss,
        }

        sektion = person["seite"].split("-")[0] if "-" in person["seite"] else ""

        if geoadresse not in groups:
            groups[geoadresse] = {
                "coords": geo["coordinates"],
                "adresse": geoadresse,
                "personen": [],
                "berufe_set": set(),
                "berufsgruppen_set": set(),
                "stadtteile_set": set(),
                "sektionen_set": set(),
                "akademiker_count": 0,
            }

        g = groups[geoadresse]
        g["personen"].append(person)
        if beruf:
            g["berufe_set"].add(beruf)
        g["berufsgruppen_set"].add(berufsgruppe)
        if ortsname:
            g["stadtteile_set"].add(ortsname)
        if sektion:
            g["sektionen_set"].add(sektion)
        if person["akademiker"]:
            g["akademiker_count"] += 1

    print(f"  {len(groups):,} eindeutige Adressen")

    # Baue GeoJSON-Features
    out_features = []
    for geoadresse, g in groups.items():
        out_features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": g["coords"],
            },
            "properties": {
                "adresse": g["adresse"],
                "anzahl": len(g["personen"]),
                "personen": g["personen"],
                "stadtteile": sorted(g["stadtteile_set"]),
                "berufe": sorted(g["berufe_set"]),
                "berufsgruppen": sorted(g["berufsgruppen_set"]),
                "sektionen": sorted(g["sektionen_set"]),
                "hat_akademiker": g["akademiker_count"] > 0,
            },
        })

    out_geojson = {"type": "FeatureCollection", "features": out_features}
    with open(OUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(out_geojson, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = OUT_GEOJSON.stat().st_size / 1_000_000
    print(f"  → {OUT_GEOJSON} geschrieben ({size_mb:.1f} MB, {len(out_features):,} Features)")

    # Statistiken
    statistiken = {
        "gesamt_eintraege": len(features),
        "geocodierte_eintraege": sum(1 for f in features if f["geometry"]),
        "eindeutige_adressen": len(groups),
        "top_berufe": berufe_counter.most_common(20),
        "top_nachnamen": nachnamen_counter.most_common(20),
        "stadtteile": sorted(stadtteile_counter.items(), key=lambda x: -x[1]),
    }

    with open(OUT_STATISTIKEN, "w", encoding="utf-8") as f:
        json.dump(statistiken, f, ensure_ascii=False, indent=2)

    print(f"  → {OUT_STATISTIKEN} geschrieben")
    print(f"\nTop 5 Berufe:")
    for beruf, n in statistiken["top_berufe"][:5]:
        print(f"  {beruf}: {n:,}")
    print(f"\nTop 5 Nachnamen:")
    for name, n in statistiken["top_nachnamen"][:5]:
        print(f"  {name}: {n:,}")


if __name__ == "__main__":
    main()
