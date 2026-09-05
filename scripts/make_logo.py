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
# The mark fills ~95% of the icon so it reads as large as neighbouring app
# icons in the taskbar rather than sitting small with padding.
ICON_FILL = 0.95
# Columns/rows carrying less than this share of the peak coverage are treated as
# stray shards and trimmed, so the crop (and thus the centring) is driven by the
# solid bubble, not by specks flung far to the left.
ICON_DENSITY = 0.06
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
    rgba = rgba.crop(_dense_bbox(alpha))

    w, h = rgba.size
    side = int(max(w, h) / ICON_FILL)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(rgba, ((side - w) // 2, (side - h) // 2))
    canvas.save(ASSETS / "wipecord.ico", format="ICO", sizes=[(n, n) for n in ICO_SIZES])


def _dense_bbox(alpha: Image.Image, scale: int = 4):
    """Bounding box of the solid mark, ignoring sparse stray shards.

    A plain getbbox() would include specks flung far from the bubble, pushing
    its centre off and shrinking it. This keeps only the columns and rows whose
    coverage clears ICON_DENSITY of the peak, so the box hugs the bubble itself.
    """
    small = alpha.resize((max(1, alpha.width // scale), max(1, alpha.height // scale)))
    w, h = small.size
    data = small.tobytes()
    cols = [0] * w
    rows = [0] * h
    for y in range(h):
        base = y * w
        for x in range(w):
            v = data[base + x]
            cols[x] += v
            rows[y] += v
    col_min = max(cols) * ICON_DENSITY
    row_min = max(rows) * ICON_DENSITY
    xs = [x for x in range(w) if cols[x] > col_min]
    ys = [y for y in range(h) if rows[y] > row_min]
    if not xs or not ys:
        return alpha.getbbox()
    return (min(xs) * scale, min(ys) * scale, (max(xs) + 1) * scale, (max(ys) + 1) * scale)


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
