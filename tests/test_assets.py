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
