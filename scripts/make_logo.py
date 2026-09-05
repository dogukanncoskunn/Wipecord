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

from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "source"

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
# The mark is cropped to ~88% of the icon so it fills the canvas like a normal
# app icon rather than sitting small inside a tile.
ICON_FILL = 0.88
# Luminance keying for the wordmark: pixels darker than LO become fully
# transparent, brighter than HI stay opaque, with a smooth ramp between so the
# black background dissolves into the sidebar without hard edges.
KEY_LO, KEY_HI = 24, 74
CROP_THRESHOLD = 34  # ignore JPEG noise darker than this when trimming


def build_icon() -> None:
    """The app icon: just the bubble mark, its dark background keyed out.

    The source art sits on a dark rounded card. Other apps' icons fill their
    square with the glyph and no surround, so the neutral-grey background is
    removed (keeping the saturated blue bubble, shards and crack, plus the
    bright white dots) and the mark is cropped tight and centred on a
    transparent square.
    """
    src = Image.open(SOURCE / "icon.jpg").convert("RGB")
    hsv = src.convert("HSV")
    _, saturation, value = hsv.split()
    # Foreground = saturated (the blue/green art) OR bright (the white dots);
    # the neutral, dark background falls outside both and becomes transparent.
    sat_mask = saturation.point(lambda p: 0 if p < 50 else (255 if p > 95 else int((p - 50) / 45 * 255)))
    val_mask = value.point(lambda p: 0 if p < 95 else (255 if p > 140 else int((p - 95) / 45 * 255)))
    alpha = ImageChops.lighter(sat_mask, val_mask).filter(ImageFilter.GaussianBlur(radius=2))

    rgba = src.convert("RGBA")
    rgba.putalpha(alpha)
    bbox = alpha.point(lambda p: 255 if p > 24 else 0).getbbox()
    if bbox:
        rgba = rgba.crop(bbox)

    w, h = rgba.size
    side = int(max(w, h) / ICON_FILL)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(rgba, ((side - w) // 2, (side - h) // 2))
    canvas.save(ASSETS / "wipecord.ico", format="ICO", sizes=[(n, n) for n in ICO_SIZES])


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
