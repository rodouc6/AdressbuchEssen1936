#!/usr/bin/env python3
"""
Zechen-Scraper: Extrahiert Essener Bergwerke aus Wikipedia
==========================================================
Scrapet die Liste von Bergwerken in Essen und extrahiert Koordinaten
aus den individuellen Wikipedia-Artikeln der Zechen.

Nur Zechen die 1936 aktiv waren werden aufgenommen.

Ergebnis:
    docs/data/zechen.geojson
"""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── Konfiguration ───────────────────────────────────────────────────────────

HAUPTSEITE = "https://de.wikipedia.org/wiki/Liste_von_Bergwerken_in_Essen"
PAUSE_SEKUNDEN = 1.5

HEADERS = {
    "User-Agent": "EssenerZechenScraper/1.0 (Historische Forschung; Python/requests)"
}

OUT_DIR = Path("docs/data")
OUT_FILE = OUT_DIR / "zechen.geojson"


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

def clean_text(text):
    """Bereinigt extrahierten Text von Whitespace und Fußnoten-Markern."""
    if not text:
        return ""
    text = re.sub(r'\[[\d\w]+\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_page(url):
    """Ruft eine Wikipedia-Seite ab und gibt BeautifulSoup-Objekt zurück."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_betriebszeit(text):
    """Parst Betriebszeit-Angaben und gibt (von, bis) als Integers zurück.

    Unterstützt Formate wie:
    - '1847–1966', '1847-1966'
    - 'ab 1850', 'seit 1850'
    - 'bis 1920'
    - '1850' (einzelnes Jahr)
    """
    text = clean_text(text)
    if not text:
        return None, None

    # Bereich: 1847–1966 oder 1847-1966
    m = re.search(r'(\d{4})\s*[–\-–—]\s*(\d{4})', text)
    if m:
        return int(m.group(1)), int(m.group(2))

    # "ab 1850" oder "seit 1850"
    m = re.search(r'(?:ab|seit)\s+(\d{4})', text, re.IGNORECASE)
    if m:
        return int(m.group(1)), None

    # "bis 1920"
    m = re.search(r'bis\s+(\d{4})', text, re.IGNORECASE)
    if m:
        return None, int(m.group(1))

    # Einzelnes Jahr
    m = re.search(r'(\d{4})', text)
    if m:
        return int(m.group(1)), int(m.group(1))

    return None, None


def war_1936_aktiv(von, bis):
    """Prüft ob eine Zeche 1936 in Betrieb war."""
    if von is None and bis is None:
        return False
    if von is not None and von > 1936:
        return False
    if bis is not None and bis < 1936:
        return False
    return True


def extract_coords_from_article(url):
    """Extrahiert Koordinaten aus einem individuellen Wikipedia-Artikel.

    Sucht nach <span class="geo"> in der Infobox.
    """
    try:
        soup = fetch_page(url)

        # Methode 1: <span class="latitude"> + <span class="longitude">
        lat_el = soup.find("span", class_="latitude")
        lon_el = soup.find("span", class_="longitude")
        if lat_el and lon_el:
            lat = float(lat_el.get_text().strip())
            lon = float(lon_el.get_text().strip())
            return lon, lat

        # Methode 2: <span class="geo"> mit Separator
        geo_span = soup.find("span", class_="geo")
        if geo_span:
            text = geo_span.get_text().strip()
            parts = re.split(r'[;,]\s*', text)
            if len(parts) == 2:
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                return lon, lat

        # Methode 3: data-lat / data-lon Attribute
        geo_el = soup.find(attrs={"data-lat": True, "data-lon": True})
        if geo_el:
            lat = float(geo_el["data-lat"])
            lon = float(geo_el["data-lon"])
            return lon, lat

    except Exception as e:
        print(f"    Fehler bei Koordinaten-Extraktion: {e}")

    return None, None


def parse_bergwerke_tabelle(soup):
    """Parst die Haupttabelle der Bergwerksliste."""
    zechen = []

    tables = soup.find_all("table", class_="wikitable")
    if not tables:
        print("Keine wikitable gefunden!")
        return zechen

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Header analysieren
        headers = [clean_text(th.get_text()).lower()
                    for th in rows[0].find_all(["th", "td"])]

        idx_name = None
        idx_beginn = None
        idx_ende = None
        idx_betrieb = None
        idx_stadtteil = None

        for i, h in enumerate(headers):
            if "name" in h or "bergwerk" in h or "zeche" in h:
                if idx_name is None:
                    idx_name = i
            elif "beginn" in h:
                idx_beginn = i
            elif "ende" in h:
                idx_ende = i
            elif "betrieb" in h or "zeit" in h or "förder" in h or "aktiv" in h:
                idx_betrieb = i
            elif "stadtteil" in h or "lage" in h or "ort" in h:
                idx_stadtteil = i

        if idx_name is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells or len(cells) <= idx_name:
                continue

            # Name und Link extrahieren
            name_cell = cells[idx_name]
            name = clean_text(name_cell.get_text())
            if not name or name == '–' or name == '—':
                continue

            link = name_cell.find("a", href=True)
            article_url = None
            if link and link["href"].startswith("/wiki/"):
                article_url = "https://de.wikipedia.org" + link["href"]

            # Betriebszeit: separate Beginn/Ende-Spalten oder kombinierte Spalte
            von, bis = None, None
            betriebszeit_text = ""
            if idx_beginn is not None and idx_ende is not None:
                beginn_text = clean_text(cells[idx_beginn].get_text()) if idx_beginn < len(cells) else ""
                ende_text = clean_text(cells[idx_ende].get_text()) if idx_ende < len(cells) else ""
                betriebszeit_text = f"{beginn_text}–{ende_text}" if beginn_text or ende_text else ""
                von, _ = parse_betriebszeit(beginn_text)
                _, bis = parse_betriebszeit(ende_text)
                # Fallback: wenn Ende "nach XXXX" oder leer ist
                if bis is None and ende_text:
                    m = re.search(r'(\d{4})', ende_text)
                    if m:
                        bis = int(m.group(1))
                    elif 'nach' in ende_text.lower() or 'heute' in ende_text.lower():
                        bis = 9999  # noch aktiv
                if von is None and beginn_text:
                    m = re.search(r'(\d{4})', beginn_text)
                    if m:
                        von = int(m.group(1))
            elif idx_betrieb is not None and idx_betrieb < len(cells):
                betriebszeit_text = clean_text(cells[idx_betrieb].get_text())
                von, bis = parse_betriebszeit(betriebszeit_text)

            # Stadtteil
            stadtteil = ""
            if idx_stadtteil is not None and idx_stadtteil < len(cells):
                stadtteil = clean_text(cells[idx_stadtteil].get_text())

            zechen.append({
                "name": name,
                "betriebszeit": betriebszeit_text,
                "von": von,
                "bis": bis,
                "stadtteil": stadtteil,
                "article_url": article_url,
            })

    return zechen


# ─── Hauptprogramm ───────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Zechen-Scraper: Bergwerke in Essen")
    print("=" * 70)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nLade Hauptseite: {HAUPTSEITE}")
    soup = fetch_page(HAUPTSEITE)

    zechen = parse_bergwerke_tabelle(soup)
    print(f"\n{len(zechen)} Bergwerke in Tabelle gefunden")

    # Filtern: nur 1936 aktive
    aktive = [z for z in zechen if war_1936_aktiv(z["von"], z["bis"])]
    print(f"{len(aktive)} waren 1936 aktiv")

    # Koordinaten aus individuellen Artikeln holen
    features = []
    for i, z in enumerate(aktive, 1):
        print(f"[{i:2d}/{len(aktive)}] {z['name']:40s} ", end="", flush=True)

        if z["article_url"]:
            time.sleep(PAUSE_SEKUNDEN)
            lon, lat = extract_coords_from_article(z["article_url"])
            if lon is not None:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat],
                    },
                    "properties": {
                        "name": z["name"],
                        "betriebszeit": z["betriebszeit"],
                        "stadtteil": z["stadtteil"],
                    },
                })
                print(f"✓ [{lon:.4f}, {lat:.4f}]")
            else:
                print("– Keine Koordinaten gefunden")
        else:
            print("– Kein Wikipedia-Artikel verlinkt")

    # GeoJSON schreiben
    geojson = {"type": "FeatureCollection", "features": features}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 70}")
    print(f"Ergebnis: {len(features)} Zechen mit Koordinaten")
    print(f"  → {OUT_FILE}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
