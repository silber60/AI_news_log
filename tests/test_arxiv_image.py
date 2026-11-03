"""arXiv HTML figure fallback: parsing, host rule and pick order (offline)."""

import httpx
import pytest
import respx
from conftest import mock_arxiv, mock_github

from newsletter.schema import ItemImage
from newsletter.stages.enrich import arxiv_candidates, pick_image

PID = "2610.31635"
BASE = "https://arxiv.org/html/"


def fig(src: str) -> str:
    return f'<figure class="ltx_figure" id="S1.F1"><img src="{src}" class="ltx_graphics"></figure>'


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (fig(f"{PID}v1/teaser.png"), [BASE + f"{PID}v1/teaser.png"]),
        (fig(f"{PID}v2/figures/html/overview.jpg"), [BASE + f"{PID}v2/figures/html/overview.jpg"]),
        # first two figures only, in order
        (
            fig(f"{PID}v1/a.png") + fig(f"{PID}v1/b.png") + fig(f"{PID}v1/c.png"),
            [BASE + f"{PID}v1/a.png", BASE + f"{PID}v1/b.png"],
        ),
        # a figure without an image (table, svg object) is skipped
        (
            '<figure class="ltx_figure"><svg></svg></figure>' + fig(f"{PID}v1/b.png"),
            [BASE + f"{PID}v1/b.png"],
        ),
        # absolute arxiv.org/html src is accepted when it is this paper's dir
        (fig(f"https://arxiv.org/html/{PID}v1/abs.png"), [BASE + f"{PID}v1/abs.png"]),
        # another paper, another host, traversal, query, svg, unversioned dir
        (fig("2610.99999v1/other.png"), []),
        (fig("https://example.com/x.png"), []),
        (fig(f"{PID}v1/../x.png"), []),
        (fig(f"{PID}v1/x.png?y=1"), []),
        (fig(f"{PID}v1/x.svg"), []),
        (fig("x1.png"), []),
        # images outside ltx_figure blocks are ignored
        (f'<img src="{PID}v1/logo-free.png">', []),
    ],
)
def test_arxiv_candidates(page, expected):
    assert arxiv_candidates(page, PID) == expected
    for url in expected:
        ItemImage(url=url, width=576, height=200)  # passes the schema host rule


def test_arxiv_figure_used_when_hf_and_readme_have_none():
    url = BASE + f"{PID}v1/teaser.png"
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        mock_github(router, readmes={}, images={})
        mock_arxiv(router, {PID: fig(f"{PID}v1/teaser.png")}, {url: (1152, 468)})
        image = pick_image(httpx.Client(), None, 4, "https://github.com/org/repo", paper_id=PID)
    assert image == ItemImage(url=url, width=576, height=234)


def test_readme_image_wins_over_arxiv():
    raw = "https://raw.githubusercontent.com/org/repo/HEAD/a.png"
    images = {
        raw: {
            "status": 206,
            "content_type": "image/png",
            "width": 1152,
            "height": 468,
            "total_bytes": 20000,
        }
    }
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        mock_github(router, readmes={"org/repo": "![a](a.png)"}, images=images)
        arxiv = mock_arxiv(router, {PID: fig(f"{PID}v1/teaser.png")})
        image = pick_image(httpx.Client(), None, 4, "https://github.com/org/repo", paper_id=PID)
    assert image is not None and image.url == raw
    assert not arxiv.called


def test_arxiv_redirect_and_errors_give_no_image():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.get(f"{BASE}{PID}").mock(
            return_value=httpx.Response(301, headers={"location": f"{BASE}{PID}v1"})
        )
        assert pick_image(httpx.Client(), None, 4, None, paper_id=PID) is None
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        mock_arxiv(router, fail=True)
        assert pick_image(httpx.Client(), None, 4, None, paper_id=PID) is None


def test_bad_paper_id_never_requests_arxiv():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        route = mock_arxiv(router)
        assert pick_image(httpx.Client(), None, 4, None, paper_id="../etc") is None
    assert not route.called


def test_narrow_arxiv_figure_is_skipped():
    url = BASE + f"{PID}v1/small.png"
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        mock_arxiv(router, {PID: fig(f"{PID}v1/small.png")}, {url: (354, 385)})
        assert pick_image(httpx.Client(), None, 1, None, paper_id=PID) is None
