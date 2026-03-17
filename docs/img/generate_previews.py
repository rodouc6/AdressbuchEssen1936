"""Erzeugt Platzhalter-Vorschaubilder für die Hero-Cards der Startseite.

Generiert farbige Punktwolken auf einem Kartenumriss als Fallback,
bis echte Screenshots vorliegen.

Benötigt: pip install Pillow
"""

import random
from PIL import Image, ImageDraw

WIDTH, HEIGHT = 960, 540  # 16:9


def draw_dots(draw, color_base, n=800, seed=42):
    """Zeichnet n halbtransparente Punkte im Stadtbereich."""
    rng = random.Random(seed)
    # Essener Stadtgebiet grob im Bildbereich (zentriert)
    cx, cy = WIDTH // 2, HEIGHT // 2
    for _ in range(n):
        x = int(rng.gauss(cx, WIDTH * 0.18))
        y = int(rng.gauss(cy, HEIGHT * 0.2))
        r = rng.randint(2, 6)
        alpha = rng.randint(80, 200)
        color = (*color_base, alpha)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def generate_preview(filename, bg_colors, dot_color, seed):
    """Erstellt ein einzelnes Vorschaubild."""
    img = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    # Gradient-Hintergrund
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(bg_colors[0][0] * (1 - t) + bg_colors[1][0] * t)
        g = int(bg_colors[0][1] * (1 - t) + bg_colors[1][1] * t)
        b = int(bg_colors[0][2] * (1 - t) + bg_colors[1][2] * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b, 255))

    draw_dots(draw, dot_color, n=1200, seed=seed)

    # Als RGB speichern (PNG)
    img_rgb = img.convert("RGB")
    img_rgb.save(filename, "PNG", optimize=True)
    print(f"  ✓ {filename}")


if __name__ == "__main__":
    print("Generiere Platzhalter-Vorschaubilder …")

    # Karte: dunkles Blau mit blauen Punkten
    generate_preview(
        "preview-karte.png",
        bg_colors=[(26, 58, 92), (15, 35, 60)],
        dot_color=(100, 160, 255),
        seed=1936,
    )

    # Gewerbe: dunkles Blau-Gold mit orangefarbenen Punkten
    generate_preview(
        "preview-gewerbe.png",
        bg_colors=[(42, 90, 140), (160, 130, 50)],
        dot_color=(255, 160, 40),
        seed=2024,
    )

    print("Fertig.")
