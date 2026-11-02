"""Build the compressed email assets from the Figma exports.

Run from the repo root:

    uv run python scripts/build_email_assets.py [--force]

Reads the five PNGs in the phase 1.1 figma-assets directory and writes
docs/assets/email/v1/. Banners become JPEGs flattened on white. The tool,
magnifier and chalkboard otters were exported on an opaque (30, 30, 30) Figma
canvas, so the background is keyed out with a border flood-fill and the result
is saved as a quantized PNG with real alpha.

Published files are immutable: an existing output is left alone unless
--force is given. Only use --force before the first push; new art goes to v2/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SRC_DIR = Path(".planning/phases/01.1-newsletter-design-v2/figma-assets")
OUT_DIR = Path("docs/assets/email/v1")

CANVAS = (30, 30, 30)
KEY = (255, 0, 255)
FLOOD_THRESH = 12
JPEG_QUALITY = 72

BANNERS = {
    "otter-banner.png": "otter-banner.jpg",
    "otter-wave.png": "otter-wave.jpg",
}
OTTERS = {
    "otter-tool.png": ("otter-tool.png", 300),
    "otter-magnifier.png": ("otter-magnifier.png", 300),
    "otter-chalkboard.png": ("otter-chalkboard.png", 340),
}


def _border_pixels(width: int, height: int):
    for x in range(width):
        yield x, 0
        yield x, height - 1
    for y in range(1, height - 1):
        yield 0, y
        yield width - 1, y


def key_background(im: Image.Image) -> Image.Image:
    """Return an RGBA image with the border-connected canvas color made transparent."""
    rgb = im.convert("RGB")
    mask = rgb.copy()
    for xy in _border_pixels(*rgb.size):
        if mask.getpixel(xy) == CANVAS:
            ImageDraw.floodfill(mask, xy, KEY, thresh=FLOOD_THRESH)
    keyed = ImageChops.difference(mask, Image.new("RGB", mask.size, KEY)).convert("L")
    alpha = keyed.point(lambda v: 0 if v == 0 else 255)
    # Grow the transparent area by one pixel so the anti-aliased dark fringe
    # left between the canvas and the drawing does not show as a halo.
    alpha = alpha.filter(ImageFilter.MinFilter(3))
    rgba = rgb.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba


def build_otter(src: Path, out: Path, size: int) -> None:
    rgba = key_background(Image.open(src))
    small = rgba.resize((size, size), Image.Resampling.LANCZOS)
    small.quantize(256, method=Image.Quantize.FASTOCTREE).save(out, "PNG", optimize=True)


def build_banner(src: Path, out: Path) -> None:
    im = Image.open(src).convert("RGBA")
    flat = Image.new("RGB", im.size, "white")
    flat.paste(im, mask=im.getchannel("A"))
    flat.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="rewrite existing outputs")
    args = parser.parse_args(argv)

    if not SRC_DIR.is_dir():
        print(f"missing source dir {SRC_DIR}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = [(name, out, None) for name, out in BANNERS.items()]
    jobs += [(name, out, size) for name, (out, size) in OTTERS.items()]
    for name, out_name, size in jobs:
        src = SRC_DIR / name
        out = OUT_DIR / out_name
        if out.exists() and not args.force:
            print(f"exists {out_name}")
            continue
        if size is None:
            build_banner(src, out)
        else:
            build_otter(src, out, size)
        print(f"wrote {out_name} {out.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
