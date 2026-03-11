#!/usr/bin/env python3
"""
Normalisiert die Spalte 'Beruf o. ä.' durch Auflösung bekannter Abkürzungen.
Ergebnis in neuer Spalte 'Beruf normiert' (direkt nach 'Beruf o. ä.').
Die Originalspalte bleibt unverändert.

Input:  essen1936_bereinigt.csv + abkuerzungen_aufloesung.csv
Output: essen1936_bereinigt.csv (in-place, Backup unter .bak2)
"""
import csv, shutil
from pathlib import Path

MAPPING_FILE = Path("abkuerzungen_aufloesung.csv")
INPUT        = Path("essen1936_bereinigt.csv")
BACKUP       = Path("essen1936_bereinigt.csv.bak2")


def lade_mapping(pfad: Path) -> dict:
    mapping = {}
    with open(pfad, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            abk = row["Abkürzung"]
            afl = row["Auflösung"].strip()
            if abk and afl:
                mapping[abk] = afl
    return mapping


def normiere(beruf: str, mapping: dict) -> str:
    """Ersetzt Abkürzungs-Token durch ihre Vollformen."""
    if not beruf.strip():
        return beruf

    tokens = beruf.split()
    normiert = []
    for tok in tokens:
        # Führende und abschließende Satzzeichen (Komma, Klammern) ablösen
        pre, kern, suf = "", tok, ""
        while kern and kern[0] in "([":
            pre += kern[0]; kern = kern[1:]
        while kern and kern[-1] in ")],:;":
            suf = kern[-1] + suf; kern = kern[:-1]

        ersatz = mapping.get(kern)
        normiert.append(pre + (ersatz if ersatz else kern) + suf)

    return " ".join(normiert)


def main():
    mapping = lade_mapping(MAPPING_FILE)
    print(f"Mapping geladen: {len(mapping)} Einträge")

    shutil.copy(INPUT, BACKUP)
    print(f"Backup: {BACKUP}")

    with open(INPUT, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # 'Beruf normiert' direkt nach 'Beruf o. ä.' einfügen (nur einmal)
    ziel = "Beruf normiert"
    if ziel not in fieldnames:
        idx = fieldnames.index("Beruf o. ä.")
        fieldnames.insert(idx + 1, ziel)

    veraendert = 0
    for row in rows:
        original = row["Beruf o. ä."]
        norm = normiere(original, mapping)
        row[ziel] = norm
        if norm != original:
            veraendert += 1

    with open(INPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows):,} Zeilen verarbeitet")
    print(f"{veraendert:,} Berufsangaben normiert")


if __name__ == "__main__":
    main()
