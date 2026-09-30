"""Draw the app icon (an open book carrying a knight) and write it for every platform.

Run from the repository root: python3 packaging/icon/make_icon.py
Needs Pillow and the DejaVu Sans font (its knight glyph, U+265E).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 4096  # drawn large, then downsampled: Pillow has no antialiasing of its own
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

BG = (31, 58, 95)
PAGE = (246, 238, 220)
PAGE_SHADE = (222, 210, 185)
DARK_SQUARE = (181, 136, 99)
LIGHT_SQUARE = (240, 217, 181)
INK = (28, 28, 28)


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=S // 5, fill=BG)

    # Open book: two pages meeting at a spine, slightly lifted at the outer edges.
    top, bottom, spine = int(S * 0.50), int(S * 0.86), S // 2
    left, right = int(S * 0.12), int(S * 0.88)
    lift = int(S * 0.04)
    d.polygon([(left, top - lift), (spine, top), (spine, bottom), (left, bottom - lift)], fill=PAGE)
    d.polygon([(spine, top), (right, top - lift), (right, bottom - lift), (spine, bottom)], fill=PAGE)
    d.line([(spine, top), (spine, bottom)], fill=PAGE_SHADE, width=S // 80)

    # Left page: lines of text.
    for i in range(4):
        y = top + int(S * 0.07) + i * int(S * 0.07)
        x1 = int(S * 0.44) if i != 3 else int(S * 0.34)
        d.line([(left + int(S * 0.05), y), (x1, y)], fill=PAGE_SHADE, width=S // 60)

    # Right page: a small board.
    n, cell = 4, int(S * 0.064)
    bx, by = spine + int(S * 0.04), top + int(S * 0.04)
    for r in range(n):
        for c in range(n):
            color = LIGHT_SQUARE if (r + c) % 2 == 0 else DARK_SQUARE
            d.rectangle((bx + c * cell, by + r * cell, bx + (c + 1) * cell, by + (r + 1) * cell), fill=color)

    # The knight, standing on the spine.
    font = ImageFont.truetype(FONT, int(S * 0.46))
    glyph = "♞"
    x0, y0, x1, y1 = d.textbbox((0, 0), glyph, font=font)
    gx = (S - (x1 - x0)) // 2 - x0
    gy = top + S // 50 - (y1 - y0) - y0
    d.text((gx, gy), glyph, font=font, fill=INK, stroke_width=S // 90, stroke_fill=PAGE)
    return img


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    big = draw().resize((1024, 1024), Image.LANCZOS)
    big.save(root / "packaging/icon/icon.png")
    big.resize((512, 512), Image.LANCZOS).save(root / "packaging/icon/icon-512.png")

    for size in (16, 32, 64, 128, 256, 512, 1024):
        big.resize((size, size), Image.LANCZOS).save(
            root / f"macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_{size}.png")

    big.save(root / "windows/runner/resources/app_icon.ico",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    for name, size in (("Icon-192", 192), ("Icon-512", 512),
                       ("Icon-maskable-192", 192), ("Icon-maskable-512", 512)):
        big.resize((size, size), Image.LANCZOS).save(root / f"web/icons/{name}.png")
    big.resize((32, 32), Image.LANCZOS).save(root / "web/favicon.png")


if __name__ == "__main__":
    main()
