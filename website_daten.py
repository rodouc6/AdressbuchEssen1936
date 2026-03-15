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
MAPPING_FILE = Path("berufe_ohdab_mapping.csv")

# OhdAB B-Kategorien: Volltitel → Kurzbezeichnung (als Filter-ID)
OHDAB_B_KURZ: dict[str, str] = {
    "B 0: Militär":                                                      "Militär",
    "B 1: Land-, Forst- und Tierwirtschaft und Gartenbau":               "Land- & Forstwirtschaft",
    "B 2: Rohstoffgewinnung, Produktion und Fertigung":                  "Rohstoffgewinnung",
    "B 3: Bau, Architektur, Vermessung und Gebäudetechnik":              "Bau",
    "B 4: Naturwissenschaft, Geografie und Informatik":                  "Naturwissenschaft",
    "B 5: Verkehr, Logistik, Schutz und Sicherheit":                     "Verkehr",
    "B 6: Kaufmännische Dienstleistungen, Warenhandel, Vertrieb, Hotel und Tourismus": "Kaufm. Dienstleistungen",
    "B 7: Unternehmensorganisation, Buchhaltung, Recht und Verwaltung":  "Unternehmensorganisation",
    "B 8: Gesundheit, Soziales, Lehre und Erziehung":                    "Gesundheit",
    "B 9: Sprach-, Literatur-, Geistes-, Gesellschafts- und Wirtschaftswissenschaften, Medien, Kunst, Kultur und Gestaltung": "Geisteswiss. & Kunst",
}
OUT_DIR = Path("docs/data")
OUT_GEOJSON = OUT_DIR / "essen1936.geojson"
OUT_STATISTIKEN = OUT_DIR / "statistiken.json"

AKADEMIKER_RE = re.compile(r'\b(Dr\.?|Prof\.?|Dipl\.?|Ing\.?|Mag\.?)\b', re.IGNORECASE)

# Bergbau-Klassifikation
# Filter A (eng): Bergmänner & Steiger
_BERGMANN_RE = re.compile(r'\bBergm\.?\b|\bBergmann\b', re.IGNORECASE)
_STEIGER_RE = re.compile(r'steig', re.IGNORECASE)
_STEIGER_AUSSCHLUSS_RE = re.compile(r'Bahnsteig|Versteig|Steigert', re.IGNORECASE)
# Filter B (breit): zusätzliche Bergbauberufe
_BERGBAU_BREIT_RE = re.compile(
    r'Berg(?:arb|ass|hau|ing|inv|bau|werk)|Zechen|Kokerei|Gruben|Schachtm',
    re.IGNORECASE
)


def classify_bergbau(beruf: str) -> str:
    """Klassifiziert einen Beruf nach Bergbau-Bezug.

    Rückgabe: 'b' (Bergmann), 's' (Steiger), 'x' (sonstiger Bergbau), '' (kein Bergbau)
    """
    if not beruf:
        return ""
    if _BERGMANN_RE.search(beruf):
        return "b"
    if _STEIGER_RE.search(beruf) and not _STEIGER_AUSSCHLUSS_RE.search(beruf):
        return "s"
    if _BERGBAU_BREIT_RE.search(beruf):
        return "x"
    return ""

# Gültige Essener Stadtteile – nur diese erscheinen im Stadtteil-Filter
GUELTIGE_STADTTEILE = {
    "Steele", "Kray", "Katernberg", "Kupferdreh", "Werden",
    "Stoppenberg", "Schonnebeck", "Karnap", "Heisingen",
    "Heidhausen", "Ueberruhr", "Frillendorf",
}


def normiere_stadtteil(wert: str) -> str:
    """Normalisiert einen Stadtteil-Wert und prüft gegen die Whitelist.

    'Essen-Steele' → 'Steele', 'karnap' → 'Karnap', ungültige → ''
    """
    wert = wert.strip()
    if wert.lower().startswith("essen-"):
        wert = wert[6:]
    wert = wert.capitalize() if wert.islower() else wert
    # Manuelle Normalisierung bekannter Varianten
    varianten = {"karnap": "Karnap", "ueberruhr": "Ueberruhr",
                 "schonnebeck": "Schonnebeck", "schönebeck": "Schonnebeck"}
    wert = varianten.get(wert.lower(), wert)
    return wert if wert in GUELTIGE_STADTTEILE else ""

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
    """Lädt berufe_ohdab_mapping.csv: Beruf → OhdAB-Kurzbezeichnung.
    A-Kategorien und kein-Treffer werden auf '' gesetzt (→ 'sonstige').
    """
    mapping = {}
    with open(pfad, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["match_typ"] == "kein":
                continue
            kurz = OHDAB_B_KURZ.get(row["label_grob"], "")
            mapping[row["Beruf"]] = kurz  # "" für A-Kategorien → sonstige
    return mapping


def get_berufsgruppe(beruf: str, abk_mapping: dict, bg_mapping: dict) -> str:
    if not beruf.strip():
        return "sonstige"
    norm = normiere(beruf, abk_mapping)
    kurz = bg_mapping.get(norm, "")
    return kurz if kurz else "sonstige"


OUT_FIRMEN = OUT_DIR / "firmen.json"
OUT_EINWOHNER = OUT_DIR / "einwohner.json"


def export_firmen(features):
    """Exportiert alle Sektion-III-Einträge als flaches Array nach firmen.json."""
    eintraege = []
    for feat in features:
        props = feat["properties"]
        seite = (props.get("page") or "").strip()
        sektion = seite.split("-")[0] if "-" in seite else ""
        if sektion != "III":
            continue
        eintraege.append({
            "firmenname": (props.get("Firmenname") or "").strip(),
            "branche": (props.get("Familienstand") or "").strip(),
            "nachname": (props.get("lastname") or "").strip(),
            "vorname": (props.get("firstname") or "").strip(),
            "adresse": (props.get("Adresse") or "").strip(),
            "seite": seite,
            "id": (props.get("id") or "").strip(),
        })

    with open(OUT_FIRMEN, "w", encoding="utf-8") as f:
        json.dump(eintraege, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = OUT_FIRMEN.stat().st_size / 1_000_000
    print(f"  → {OUT_FIRMEN} geschrieben ({size_mb:.1f} MB, {len(eintraege):,} Einträge)")


def export_einwohner(features):
    """Exportiert alle Sektion-I-Einträge als flaches Array nach einwohner.json."""
    eintraege = []
    for feat in features:
        props = feat["properties"]
        seite = (props.get("page") or "").strip()
        sektion = seite.split("-")[0] if "-" in seite else ""
        if sektion != "I":
            continue
        eintraege.append({
            "nachname": (props.get("lastname") or "").strip(),
            "vorname": (props.get("firstname") or "").strip(),
            "beruf": (props.get("Beruf o. ä.") or "").strip(),
            "adresse": (props.get("Adresse") or "").strip(),
            "seite": seite,
            "id": (props.get("id") or "").strip(),
        })

    with open(OUT_EINWOHNER, "w", encoding="utf-8") as f:
        json.dump(eintraege, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = OUT_EINWOHNER.stat().st_size / 1_000_000
    print(f"  → {OUT_EINWOHNER} geschrieben ({size_mb:.1f} MB, {len(eintraege):,} Einträge)")


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
        vorort = (props.get("Vorort") or "").strip()

        # Stadtteil: Vorort bevorzugen, Ortsname als Fallback – beide gegen Whitelist prüfen
        stadtteil = normiere_stadtteil(vorort) or normiere_stadtteil(ortsname)

        # Statistiken
        if beruf:
            berufe_counter[beruf] += 1
        if nachname:
            nachnamen_counter[nachname] += 1
        if stadtteil:
            stadtteile_counter[stadtteil] += 1

        berufsgruppe = get_berufsgruppe(beruf, abk_mapping, bg_mapping)
        geschoss = extract_geschoss(props.get("Adresse") or "")

        bergbau_typ = classify_bergbau(beruf)

        firmenname = (props.get("Firmenname") or "").strip()
        branche = (props.get("Familienstand") or "").strip()

        person = {
            "nachname": nachname,
            "vorname": (props.get("firstname") or "").strip(),
            "beruf": beruf,
            "seite": (props.get("page") or "").strip(),
            "akademiker": is_akademiker(props),
            "berufsgruppe": berufsgruppe,
            "geschoss": geschoss,
            "bergbau_typ": bergbau_typ,
            "firmenname": firmenname,
            "branche": branche,
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
                "bergbau_narrow_count": 0,
                "bergbau_broad_count": 0,
                "hat_firma": False,
            }

        g = groups[geoadresse]
        g["personen"].append(person)
        if beruf:
            g["berufe_set"].add(beruf)
        g["berufsgruppen_set"].add(berufsgruppe)
        if stadtteil:
            g["stadtteile_set"].add(stadtteil)
        if sektion:
            g["sektionen_set"].add(sektion)
        if person["akademiker"]:
            g["akademiker_count"] += 1
        if bergbau_typ in ("b", "s"):
            g["bergbau_narrow_count"] += 1
        if bergbau_typ:
            g["bergbau_broad_count"] += 1
        if sektion == "III":
            g["hat_firma"] = True

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
                "hat_bergbau": g["bergbau_broad_count"] > 0,
                "hat_firma": g["hat_firma"],
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

    # Datenbank-JSONs exportieren (aus Roh-Features)
    print(f"\n=== Datenbank-Export ===")
    export_firmen(features)
    export_einwohner(features)


if __name__ == "__main__":
    main()
