"""Рисует иконки и заставки запуска для iPhone. Запуск: python tools/make_icons.py

Нужен Pillow (только для разработки, на сервере не нужен). Иконка — своя:
четыре круга цветов квадрантов.
"""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "icons"
QUADS = json.loads((ROOT / "data" / "emotions.json").read_text(encoding="utf-8"))["quadrants"]
COLORS = [q["color"] for q in QUADS]  # red, yellow, blue, green → по часовой: ↖ ↗ ↙ ↘
LIGHT_BG = "#F7F5F2"
DARK_BG = "#111110"

# Логические размеры экрана (pt) и масштаб — iPhone SE … 16 Pro Max.
DEVICES = [
    (375, 667, 2), (414, 896, 2), (375, 812, 3), (414, 896, 3), (390, 844, 3),
    (428, 926, 3), (393, 852, 3), (430, 932, 3), (402, 874, 3), (440, 956, 3), (360, 780, 3),
]


def draw_mark(img: Image.Image, cx: float, cy: float, size: float) -> None:
    """Четыре круга 2×2 с небольшим зазором, вписанные в квадрат size."""
    d = ImageDraw.Draw(img)
    gap = size * 0.06
    r = (size - gap) / 4
    centers = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
    for (sx, sy), color in zip(centers, COLORS):
        x = cx + sx * (r + gap / 2)
        y = cy + sy * (r + gap / 2)
        d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def icon(size: int, bg: str, mark_ratio: float) -> Image.Image:
    scale = 4  # рисуем крупнее и уменьшаем — гладкие края
    big = Image.new("RGB", (size * scale, size * scale), bg)
    draw_mark(big, size * scale / 2, size * scale / 2, size * scale * mark_ratio)
    return big.resize((size, size), Image.LANCZOS)


def splash(w: int, h: int, bg: str) -> Image.Image:
    img = Image.new("RGB", (w, h), bg)
    big = Image.new("RGB", (w // 2 * 2, h // 2 * 2), bg)
    draw_mark(big, big.width / 2, big.height / 2, min(w, h) * 0.26)
    return big.resize((w, h), Image.LANCZOS) if big.size != img.size else big


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon(180, LIGHT_BG, 0.62).save(OUT / "apple-touch-icon.png", optimize=True)
    icon(192, LIGHT_BG, 0.62).save(OUT / "icon-192.png", optimize=True)
    icon(512, LIGHT_BG, 0.62).save(OUT / "icon-512.png", optimize=True)
    icon(512, LIGHT_BG, 0.48).save(OUT / "icon-maskable-512.png", optimize=True)

    links = []
    for w, h, s in DEVICES:
        pw, ph = w * s, h * s
        for scheme, bg in (("light", LIGHT_BG), ("dark", DARK_BG)):
            name = f"splash-{pw}x{ph}-{scheme}.png"
            splash(pw, ph, bg).save(OUT / name, optimize=True)
            media = (f"(device-width: {w}px) and (device-height: {h}px) and "
                     f"(-webkit-device-pixel-ratio: {s}) and (orientation: portrait) and "
                     f"(prefers-color-scheme: {scheme})")
            links.append(f'  <link rel="apple-touch-startup-image" media="{media}" href="/icons/{name}">')

    index = ROOT / "static" / "index.html"
    html = index.read_text(encoding="utf-8")
    block = "<!-- SPLASH:START (генерирует tools/make_icons.py) -->\n" + "\n".join(links) + "\n  <!-- SPLASH:END -->"
    html = re.sub(r"<!-- SPLASH:START.*?<!-- SPLASH:END -->", block, html, flags=re.S)
    index.write_text(html, encoding="utf-8")
    print(f"ok: {len(links)} splash screens")


if __name__ == "__main__":
    main()
