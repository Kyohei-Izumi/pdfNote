"""Build every icon and logo file pdfNote ships from two pieces of artwork.

  store/icon-source/*.png  ->  pdfNote.ico, pdfNote-512.png, store/Assets/*
  store/logo-source/*.png  ->  pdfNote-logo.png (and pdfNote-logo-dark.png
                               when a *-dark.png is there)

Nothing is drawn by hand, so the files cannot drift apart, and anyone with
the source can rebuild them. Run it whenever either piece of artwork
changes; functional_qa.py fails while the files are out of date.

  python tools/make_icons.py

Sizes and names follow Microsoft Learn, "Construct your Windows app's
icon" (updated 2026-08):

  * the .ico carries every size Windows asks for at the scale factors in
    its table (16 to 96, and 256), plus 128 for Explorer's large icons;
  * the MSIX app icon comes in each target size three times -- plain,
    `altform-unplated` (dark theme) and `altform-lightunplated` (light
    theme). Without the unplated ones Windows shrinks the icon and puts a
    plate behind it on the taskbar and Start;
  * the tiles and the Store logo come at 100, 125, 150, 200 and 400%.
    Windows 11 uses no tiles, but Windows 10 does, and the Store requires
    the medium one.

The icon artwork is drawn on a square canvas with its own margin -- the
document and its shadow take 91% of the height -- so the icon sizes use
the canvas as drawn.
Tiles centre the artwork itself, trimmed, at half the tile's height: the
documentation asks for at least 16% margin on each side.

The logo is trimmed to its lettering, because the start screen gives it a
width and the margin would only make it smaller.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ICO_SIZES = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 128, 256)
TARGET_SIZES = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256)
SCALES = (100, 125, 150, 200, 400)
# Below this the white "p" blurs into the red disc behind it; a light
# unsharp mask keeps it readable. Larger sizes have the pixels already.
SHARPEN_UP_TO = 32
# Height of the trimmed artwork in a tile, as a share of the tile.
TILE_SHARE = 0.5
# The start screen draws the logo 280pt wide (PDFReaderWindow.
# WELCOME_LOGO_WIDTH); 400% is the largest scale in Microsoft's table.
LOGO_WIDTH = 280 * 4

# Manifest name -> base size in pixels, and whether it is a tile.
SCALED_ASSETS: dict[str, tuple[int, int, bool]] = {
    "Square44x44Logo": (44, 44, False),
    "StoreLogo": (50, 50, False),
    "Square71x71Logo": (71, 71, True),
    "Square150x150Logo": (150, 150, True),
    "Wide310x150Logo": (310, 150, True),
    "Square310x310Logo": (310, 310, True),
}
UNPLATED = ("", "_altform-unplated", "_altform-lightunplated")


def scaled(base: int, scale: int) -> int:
    """Microsoft's table rounds halves up: 150 at 125% is 188."""
    return math.floor(base * scale / 100 + 0.5)


def asset_sizes() -> dict[str, tuple[int, int]]:
    """Every file in store/Assets, with its size in pixels."""
    sizes: dict[str, tuple[int, int]] = {}
    for name, (width, height, _) in SCALED_ASSETS.items():
        for scale in SCALES:
            sizes[f"{name}.scale-{scale}.png"] = (scaled(width, scale), scaled(height, scale))
    for size in TARGET_SIZES:
        for form in UNPLATED:
            sizes[f"Square44x44Logo.targetsize-{size}{form}.png"] = (size, size)
    return sizes


def source(folder: Path, dark: bool = False) -> Path | None:
    """The one PNG in `folder`: the one ending in -dark, or the other."""
    if not folder.is_dir():
        return None
    return next(
        (p for p in sorted(folder.glob("*.png")) if p.stem.endswith("-dark") == dark), None
    )


def build(root: Path = ROOT, out: Path | None = None) -> list[Path]:
    """Write every file under `out` (the checkout itself by default)."""
    from PIL import Image, ImageFilter

    out = out or root
    out.mkdir(parents=True, exist_ok=True)

    def squared(art: Image.Image) -> Image.Image:
        side = max(art.size)
        if art.width == art.height:
            return art
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(art, ((side - art.width) // 2, (side - art.height) // 2))
        return canvas

    def trimmed(art: Image.Image) -> Image.Image:
        box = art.getchannel("A").getbbox()
        if box is None:
            raise SystemExit("the artwork is fully transparent")
        return art.crop(box)

    def resized(art: Image.Image, width: int, height: int) -> Image.Image:
        # Pillow premultiplies RGBA before resampling, so no dark fringe
        # comes in from the transparent pixels.
        small = art.resize((width, height), Image.LANCZOS)
        if max(width, height) <= SHARPEN_UP_TO:
            # Sharpen the colour only: sharpening the alpha would ring
            # around the outline.
            alpha = small.getchannel("A")
            small = small.convert("RGB").filter(
                ImageFilter.UnsharpMask(radius=0.6, percent=70, threshold=0)
            )
            small.putalpha(alpha)
        return small

    def icon(side: int) -> Image.Image:
        return resized(canvas, side, side)

    def tile(width: int, height: int) -> Image.Image:
        tall = max(1, round(height * TILE_SHARE))
        wide = max(1, round(content.width * tall / content.height))
        picture = resized(content, wide, tall)
        result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        result.paste(picture, ((width - wide) // 2, (height - tall) // 2), picture)
        return result

    icon_source = source(root / "store" / "icon-source")
    if icon_source is None:
        raise SystemExit("no artwork in store/icon-source")
    canvas = squared(Image.open(icon_source).convert("RGBA"))
    content = trimmed(canvas)
    written: list[Path] = []

    frames = [icon(size) for size in ICO_SIZES]
    ico = out / "pdfNote.ico"
    # Each frame is resampled from the artwork, not from the next size up:
    # handed the frames, Pillow stores them instead of resizing its own.
    frames[-1].save(
        ico, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=frames[:-1]
    )
    written.append(ico)
    large = out / "pdfNote-512.png"
    icon(512).save(large, format="PNG", optimize=True)
    written.append(large)

    assets = out / "store" / "Assets"
    assets.mkdir(parents=True, exist_ok=True)
    for old in assets.glob("*.png"):
        old.unlink()
    for name, (width, height) in asset_sizes().items():
        base = name.split(".", 1)[0]
        is_tile = SCALED_ASSETS[base][2]
        picture = tile(width, height) if is_tile else icon(width)
        path = assets / name
        picture.save(path, format="PNG", optimize=True)
        written.append(path)

    for dark, name in ((False, "pdfNote-logo.png"), (True, "pdfNote-logo-dark.png")):
        logo_source = source(root / "store" / "logo-source", dark)
        path = out / name
        if logo_source is None:
            # Nothing drawn for a dark background, so the one logo is used
            # on both. One left over from an earlier run would go on being
            # shown.
            path.unlink(missing_ok=True)
            continue
        art = trimmed(Image.open(logo_source).convert("RGBA"))
        if art.width > LOGO_WIDTH:
            art = art.resize(
                (LOGO_WIDTH, max(1, round(art.height * LOGO_WIDTH / art.width))), Image.LANCZOS
            )
        art.save(path, format="PNG", optimize=True)
        written.append(path)
    return written


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    written = build()
    for path in written:
        print(" ", path.relative_to(ROOT).as_posix())
    print(f"{len(written)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
