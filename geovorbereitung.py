#!/usr/bin/env python3
"""
Geocodierungsvorbereitung für essen1936_bereinigt.csv.

Aufgaben:
  1. Lädt die Straßennamenkokordanz aus Essener_Strassennamen_Konkordanz.xlsx
     (historische → heutige Straßennamen) und baut ein Lookup-Dict auf.
  2. Erzeugt für jede Zeile eine neue Spalte `geoadresse` aus Adresse + Essen.
     Liegt der Straßenname in der Konkordanz, wird der heutige Name verwendet.
  3. Schreibt essen1936_geovorbereitung.csv (volles Dataset + geoadresse).
  4. Schreibt unique_geoadresses.csv (nur eindeutige, nicht-leere geoadresses)
     für den QGIS-Batch-Geocoder (Nominatim).
"""

import csv
import re
from pathlib import Path

import openpyxl

INPUT_FILE      = Path("essen1936_bereinigt.csv")
OUTPUT_FILE     = Path("essen1936_geovorbereitung.csv")
UNIQUE_FILE     = Path("unique_geoadresses.csv")
KONKORDANZ_FILE = Path("Konkordanz/Essener_Strassennamen_Konkordanz.xlsx")


# ---------------------------------------------------------------------------
# Normalisierung & Hilfsfunktionen
# ---------------------------------------------------------------------------

def expand_str_kuerzel(s: str) -> str:
    """Ersetzt 'Str.' und 'Str ' → 'Straße' vor der Normalisierung."""
    s = re.sub(r"(?i)\bstr\.\s*$", "Straße", s)
    s = re.sub(r"(?i)\bstr\.\s", "Straße ", s)
    # 'Str ' (ohne Punkt) vor Hausnummer oder Zeilenende
    s = re.sub(r"(?i)\bstr\s+(?=\d)", "Straße ", s)
    s = re.sub(r"(?i)\bstr\s*$", "Straße", s)
    return s


def norm(s: str) -> str:
    """Kleinschreibung + nur Buchstaben/Ziffern/Umlaute – analog bereinigung.py."""
    return re.sub(r"[^a-z0-9äöüß]", "", s.strip().lower())


def parse_adresse(s: str) -> tuple[str, str]:
    """
    Trennt Straßenname und Hausnummer.
    Hausnummer = alles ab dem ersten ' \\d'-Vorkommen (von hinten gesucht).
    Beispiele:
      'Borbecker Str. 105'  → ('Borbecker Str.', '105')
      'Am krausen Bäumchen 18' → ('Am krausen Bäumchen', '18')
      'Vogtei 27'           → ('Vogtei', '27')
      'Achenbachhang 9b'    → ('Achenbachhang', '9b')
    """
    m = re.search(r"\s+\d", s)
    if m:
        return s[: m.start()].strip(), s[m.start() :].strip()
    return s.strip(), ""


def ist_geographisch(ortsname: str) -> bool:
    """True, wenn Ortsname eine geocodierbare geografische Angabe ist."""
    o = ortsname.strip()
    return o == "Essen" or o.startswith("Essen-")


# ---------------------------------------------------------------------------
# Konkordanz laden
# ---------------------------------------------------------------------------

def load_konkordanz(path: Path) -> dict[str, str]:
    """
    Gibt {norm(expand(ehem_strassenname)): heutiger_strassenname} zurück.

    Regeln:
    - Einträge mit 'aufgehoben' werden übersprungen (Straße nicht mehr existent).
    - Bei ' → '-Ketten (Mehrfachumbenennung) wird der letzte Name verwendet.
    """
    konkordanz: dict[str, str] = {}
    wb = openpyxl.load_workbook(path)
    ws = wb["Ehemalige Straßennamen"]
    skipped = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        ehem, heute = row[1], row[2]
        if not ehem or not heute:
            continue
        heute_str = str(heute).strip()
        if "aufgehoben" in heute_str.lower():
            skipped += 1
            continue
        # Mehrfach-Umbenennungen: letzten (aktuellsten) Namen nehmen
        if "→" in heute_str:
            heute_str = heute_str.split("→")[-1].strip()
        key = norm(expand_str_kuerzel(str(ehem)))
        if key:
            konkordanz[key] = heute_str
    print(f"Konkordanz geladen: {len(konkordanz)} nutzbare Einträge "
          f"({skipped} 'aufgehoben'-Einträge übersprungen)")
    return konkordanz


# ---------------------------------------------------------------------------
# Haupt-Verarbeitungslogik
# ---------------------------------------------------------------------------

GESCHOSS_SUFFIX_RE = re.compile(
    r'\s+(?:XV|XIV|XIII|XII|XI|X|IX|VIII|VII|VI|IV|V|III|II|I|Erdg|Untg|Part|Hh)\.?$',
    re.IGNORECASE
)


def make_geoadresse(adresse: str, konkordanz: dict[str, str]) -> tuple[str, bool]:
    """
    Baut den geoadresse-String.
    Gibt (geoadresse, konkordanz_treffer) zurück.
    """
    # 'Str. Nr. 15' → 'Str. 15' (Nr. ist kein Teil des Straßennamens)
    adresse_clean = re.sub(r"(?i)\bNr\.\s+", "", adresse)
    # Geschoss-Zusatz entfernen (z. B. 'Hauptstr. 5 II' → 'Hauptstr. 5')
    adresse_clean = GESCHOSS_SUFFIX_RE.sub("", adresse_clean)
    street, hausnr = parse_adresse(adresse_clean)
    key = norm(expand_str_kuerzel(street))
    if key in konkordanz:
        modern = konkordanz[key]
        geoadr = f"{modern} {hausnr}".strip() + ", Essen"
        return geoadr, True
    else:
        geoadr = adresse.strip() + ", Essen"
        return geoadr, False


def main() -> None:
    konkordanz = load_konkordanz(KONKORDANZ_FILE)

    count_total      = 0
    count_geo        = 0
    count_konkordanz = 0
    count_kein_hit   = 0
    count_nicht_geo  = 0

    unique_geoadresses: set[str] = set()

    with (
        open(INPUT_FILE,  newline="", encoding="utf-8") as infile,
        open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as outfile,
    ):
        reader = csv.reader(infile)
        writer = csv.writer(outfile)

        header = next(reader)
        # geoadresse nur anhängen, wenn Spalte noch nicht existiert
        if "geoadresse" not in header:
            header_out = header + ["geoadresse"]
        else:
            header_out = header
        writer.writerow(header_out)

        adresse_idx  = header.index("Adresse")
        ortsname_idx = header.index("Ortsname")
        hat_geo_spalte = "geoadresse" in header

        for row in reader:
            count_total += 1

            adresse  = row[adresse_idx].strip()  if len(row) > adresse_idx  else ""
            ortsname = row[ortsname_idx].strip() if len(row) > ortsname_idx else ""

            if adresse and ist_geographisch(ortsname):
                geoadresse, hit = make_geoadresse(adresse, konkordanz)
                count_geo += 1
                if hit:
                    count_konkordanz += 1
                else:
                    count_kein_hit += 1
                unique_geoadresses.add(geoadresse)
            else:
                geoadresse = ""
                count_nicht_geo += 1

            if hat_geo_spalte:
                writer.writerow(row)
            else:
                writer.writerow(row + [geoadresse])

    with open(UNIQUE_FILE, "w", newline="", encoding="utf-8") as f:
        w2 = csv.writer(f)
        w2.writerow(["geoadresse"])
        for g in sorted(unique_geoadresses):
            w2.writerow([g])

    print()
    print(f"Gesamtzeilen           : {count_total:>8}")
    print(f"Geocodierbar           : {count_geo:>8}")
    print(f"  Konkordanz-Treffer   : {count_konkordanz:>8}  (historischer Name ersetzt)")
    print(f"  kein Treffer         : {count_kein_hit:>8}  (Name unverändert)")
    print(f"Nicht geocodierbar     : {count_nicht_geo:>8}  (institutionell / leer)")
    print(f"Unique geoadresses     : {len(unique_geoadresses):>8}")
    print(f"\nAusgabe  : {OUTPUT_FILE}")
    print(f"QGIS-CSV : {UNIQUE_FILE}")


if __name__ == "__main__":
    main()
