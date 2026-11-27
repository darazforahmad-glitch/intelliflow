"""Generates the PWA icons (run once; the PNGs are committed). Requires Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

BRAND = (79, 70, 229)
OUT = Path(__file__).resolve().parent.parent


def glyph(size: int, *, padding: float, background: tuple[int, int, int] | None, colour=(255, 255, 255)) -> Image.Image:
    scale = 4
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if background is not None:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=background)
    inner = big * (1 - 2 * padding)
    origin = big * padding
    nodes = [(0.22, 0.30), (0.50, 0.70), (0.78, 0.30)]
    points = [(origin + x * inner, origin + y * inner) for x, y in nodes]
    width = int(inner * 0.075)
    draw.line(points, fill=colour, width=width, joint="curve")
    radius = inner * 0.11
    for i, (x, y) in enumerate(points):
        fill = colour if i != 1 else (16, 185, 129, 255)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=colour, width=int(width * 0.6))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    icons = OUT / "public" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    glyph(192, padding=0.12, background=BRAND).save(icons / "icon-192.png")
    glyph(512, padding=0.12, background=BRAND).save(icons / "icon-512.png")
    maskable = Image.new("RGBA", (512, 512), BRAND + (255,))
    maskable.alpha_composite(glyph(512, padding=0.24, background=None))
    maskable.save(icons / "maskable-512.png")
    glyph(72, padding=0.08, background=None, colour=(255, 255, 255)).save(icons / "badge-72.png")
    glyph(180, padding=0.12, background=BRAND).save(OUT / "src" / "app" / "apple-icon.png")
    glyph(64, padding=0.08, background=BRAND).save(OUT / "src" / "app" / "icon.png")
    print("icons written")


if __name__ == "__main__":
    main()
