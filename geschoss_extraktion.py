#!/usr/bin/env python3
"""
Extrahiert Geschossangaben aus der Spalte 'Adresse' und schreibt
sie in eine neue Spalte 'Geschoss' (direkt nach 'Adresse').
Die Originalspalte 'Adresse' bleibt unverändert.
"""
import csv, re, shutil
from pathlib import Path

INPUT = Path("essen1936_bereinigt.csv")
BACKUP = Path("essen1936_bereinigt.csv.bak")

GESCHOSS_RE = re.compile(
    r'\s+(XV\.?|XIV\.?|XIII\.?|XII\.?|XI\.?|X\.?|IX\.?|VIII\.?|VII\.?|VI\.?|IV\.?|V\.?|III\.?|II\.?|I\.?'
    r'|Erdg\.?|Untg\.?|Part\.?|Hh\.?)$',
    re.IGNORECASE
)

def extract_geschoss(adresse: str) -> str:
    m = GESCHOSS_RE.search(adresse)
    return m.group(1) if m else ""

def main():
    shutil.copy(INPUT, BACKUP)
    print(f"Backup: {BACKUP}")

    with open(INPUT, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        # 'Geschoss' direkt nach 'Adresse' einfügen
        adresse_idx = fieldnames.index("Adresse")
        fieldnames.insert(adresse_idx + 1, "Geschoss")
        rows = list(reader)

    treffer = 0
    for row in rows:
        g = extract_geschoss(row["Adresse"])
        row["Geschoss"] = g
        if g:
            treffer += 1

    with open(INPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows):,} Zeilen verarbeitet, {treffer:,} Geschossangaben gefunden")
    print(f"Neue Spalte 'Geschoss' nach 'Adresse' eingefügt.")

if __name__ == "__main__":
    main()
