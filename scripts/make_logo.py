"""Build the Wipecord logo assets from the source artwork.

Source art (a Discord message bubble shattering, and the "Wipecord" wordmark
bursting out of a cracked frame) lives in assets/source/. This turns it into:

    assets/wipecord.ico  - the app / taskbar / shortcut / exe icon
                           (the bubble art as a rounded app tile)
    assets/wordmark.png   - the header lockup (the wordmark with its black
                            background keyed out so it sits on the dark sidebar)

Run when the source art changes:

    python scripts/make_logo.py

Needs Pillow, which is a project dependency. The generated files are committed.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "source"

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
# Corner radius of the app tile, as a fraction of its size.
TILE_RADIUS = 0.22
# Luminance keying for the wordmark: pixels darker than LO become fully
# transparent, brighter than HI stay opaque, with a smooth ramp between so the
# black background dissolves into the sidebar without hard edges.
KEY_LO, KEY_HI = 24, 74
CROP_THRESHOLD = 34  # ignore JPEG noise darker than this when trimming


def build_icon() -> None:
    img = Image.open(SOURCE / "icon.jpg").convert("RGBA")
    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((1024, 1024), Image.LANCZOS)

    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.width - 1, img.height - 1], radius=int(img.width * TILE_RADIUS), fill=255
    )
    img.putalpha(mask)
    img.save(ASSETS / "wipecord.ico", format="ICO", sizes=[(n, n) for n in ICO_SIZES])


def build_wordmark() -> None:
    img = Image.open(SOURCE / "wordmark.jpg").convert("RGB")

    # Trim to the artwork, ignoring the near-black surround.
    luminance = img.convert("L")
    bbox = luminance.point(lambda p: 255 if p > CROP_THRESHOLD else 0).getbbox()
    if bbox:
        pad = 6
        l, t, r, b = bbox
        img = img.crop((max(0, l - pad), max(0, t - pad),
                        min(img.width, r + pad), min(img.height, b + pad)))

    # Key the black background to transparent via a luminance ramp.
    luminance = img.convert("L")
    alpha = luminance.point(
        lambda p: 0 if p <= KEY_LO else (255 if p >= KEY_HI else int((p - KEY_LO) / (KEY_HI - KEY_LO) * 255))
    )
    result = img.convert("RGBA")
    result.putalpha(alpha)
    result.save(ASSETS / "wordmark.png")


def main() -> None:
    build_icon()
    build_wordmark()
    print(f"Wrote {ASSETS / 'wipecord.ico'} and {ASSETS / 'wordmark.png'}")


if __name__ == "__main__":
    main()
