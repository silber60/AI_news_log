"""Guards for the published email assets in docs/assets/email/v1/."""

from pathlib import Path

import pytest
from PIL import Image

ASSET_DIR = Path(__file__).resolve().parent.parent / "docs" / "assets" / "email" / "v1"
MAX_BYTES = 200 * 1024

BANNERS = ("otter-banner.jpg", "otter-wave.jpg")
OTTERS = {"otter-tool.png": 300, "otter-magnifier.png": 300, "otter-chalkboard.png": 340}
ALL_FILES = set(BANNERS) | set(OTTERS)


def test_exact_asset_set():
    assert {p.name for p in ASSET_DIR.iterdir()} == ALL_FILES


@pytest.mark.parametrize("name", sorted(ALL_FILES))
def test_asset_size_limit(name):
    path = ASSET_DIR / name
    assert path.is_file()
    assert path.stat().st_size <= MAX_BYTES


@pytest.mark.parametrize("name", BANNERS)
def test_banner_is_2x_jpeg(name):
    with Image.open(ASSET_DIR / name) as im:
        assert im.format == "JPEG"
        assert im.size == (1280, 719)


@pytest.mark.parametrize(("name", "side"), sorted(OTTERS.items()))
def test_otter_has_real_alpha(name, side):
    with Image.open(ASSET_DIR / name) as im:
        assert im.format == "PNG"
        assert im.size == (side, side)
        assert im.has_transparency_data
        rgba = im.convert("RGBA")
    assert rgba.getchannel("A").getextrema() == (0, 255)
    for xy in ((0, 0), (side - 1, 0), (0, side - 1), (side - 1, side - 1)):
        assert rgba.getpixel(xy)[3] == 0


DARK = 30
DARK_TOL = 12
NEUTRAL_SPREAD = 3
HALO_LIMIT = 0.01
MIN_EDGE = 20


def halo_stats(rgba: Image.Image) -> tuple[int, int]:
    """Count edge pixels and canvas-colored edge pixels.

    Edge pixel: alpha 255 with a 4-neighbor at alpha 0. Canvas-colored: every
    channel within 12 of 30 and the channels within 3 of each other. The Figma
    canvas is a neutral (30, 30, 30); the art's own dark strokes (the wrench
    outline is about (33, 35, 41)) are tinted, so they do not count as halo.
    """
    width, height = rgba.size
    px = rgba.load()
    edge = dark = 0
    for y in range(height):
        for x in range(width):
            r, g, b, a = px[x, y]
            if a != 255:
                continue
            neighbors = ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            if not any(
                0 <= nx < width and 0 <= ny < height and px[nx, ny][3] == 0 for nx, ny in neighbors
            ):
                continue
            edge += 1
            rgb = (r, g, b)
            if (
                all(abs(c - DARK) <= DARK_TOL for c in rgb)
                and max(rgb) - min(rgb) <= NEUTRAL_SPREAD
            ):
                dark += 1
    return edge, dark


def test_halo_check_flags_dark_ring():
    im = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    for y in range(10, 30):
        for x in range(10, 30):
            ring = x in (10, 29) or y in (10, 29)
            im.putpixel((x, y), (30, 30, 30, 255) if ring else (240, 200, 120, 255))
    edge, dark = halo_stats(im)
    assert edge > 0
    assert dark / edge >= HALO_LIMIT


@pytest.mark.parametrize("name", sorted(OTTERS))
def test_otter_has_no_dark_halo(name):
    with Image.open(ASSET_DIR / name) as im:
        rgba = im.convert("RGBA")
    edge, dark = halo_stats(rgba)
    assert edge >= MIN_EDGE, "no opaque pixel touches the keyed area; the check would be vacuous"
    assert dark / edge < HALO_LIMIT
