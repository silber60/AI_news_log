"""README image candidate rules (D-08, D-09, D-18): pure functions, no network."""

import pytest

from newsletter.schema import IMAGE_HOSTS, IMAGE_URL_MAX, ItemImage
from newsletter.stages.enrich import parse_repo, readme_candidates

O, R = "org", "repo"
RAW = f"https://raw.githubusercontent.com/{O}/{R}/HEAD/"
RAW_MAIN = f"https://raw.githubusercontent.com/{O}/{R}/main/"


@pytest.mark.parametrize(
    ("md", "expected"),
    [
        # markdown and <img>, document order
        (
            '![a](img/x.png "t")\ntext\n<img width="600" src="./img/y.jpg">',
            [RAW + "img/x.png", RAW + "img/y.jpg"],
        ),
        ('<img src="b.png">\n![a](a.png)', [RAW + "b.png", RAW + "a.png"]),
        ("<IMG SRC='single.gif' alt=x>", [RAW + "single.gif"]),
        ("<img src=bare.jpeg>", [RAW + "bare.jpeg"]),
        ("![a](<img/angle.png>)", [RAW + "img/angle.png"]),
        # duplicates are kept once
        ("![a](a.png) ![b](a.png)", [RAW + "a.png"]),
        # &amp; is unescaped before the checks (the result has a query, so it goes)
        ('<img src="a.png?x=1&amp;y=2">', []),
        ('<img src="dir&amp;more/a.png">', [RAW + "dir&more/a.png"]),
        # relative, rooted and ./ paths
        ("![a](img/x.png)", [RAW + "img/x.png"]),
        ("![a](/img/x.png)", [RAW + "img/x.png"]),
        ("![a](./img/x.png)", [RAW + "img/x.png"]),
        ("![a](.github/banner.png)", [RAW + ".github/banner.png"]),
        # github.com blob / raw links become raw.githubusercontent.com
        (f"![a](https://github.com/{O}/{R}/blob/main/a.png)", [RAW_MAIN + "a.png"]),
        (f"![a](https://github.com/{O}/{R}/raw/main/a.png)", [RAW_MAIN + "a.png"]),
        (
            f'<img src="https://github.com/{O}/{R}/blob/v1.2/docs/b.jpg">',
            [f"https://raw.githubusercontent.com/{O}/{R}/v1.2/docs/b.jpg"],
        ),
        # scheme-relative gets https; http is rejected
        (
            "![a](//raw.githubusercontent.com/o/r/main/a.png)",
            ["https://raw.githubusercontent.com/o/r/main/a.png"],
        ),
        ("![a](http://raw.githubusercontent.com/o/r/main/a.png)", []),
        # direct hosts are kept as they are
        (
            "![a](https://cdn-uploads.huggingface.co/production/uploads/x/y.png)",
            ["https://cdn-uploads.huggingface.co/production/uploads/x/y.png"],
        ),
        # .. anywhere, query strings and fragments are rejected
        ("![a](../up.png)", []),
        ("![a](img/../../up.png)", []),
        ("![a](https://raw.githubusercontent.com/o/r/main/../x.png)", []),
        ("![a](a.png?raw=true)", []),
        ("![a](a.png#frag)", []),
        # extensions: case-insensitive, only png/jpg/jpeg/gif
        ("![a](A.PNG) ![b](b.JpEg)", [RAW + "A.PNG", RAW + "b.JpEg"]),
        ("![a](a.svg) ![b](b.webp) ![c](c.mp4) ![d](d.mov) ![e](e.bmp)", []),
        # badges
        (
            (
                "![s](https://img.shields.io/badge/x-y-blue.png)"
                f" ![w](https://github.com/{O}/{R}/actions/workflows/ci.yml/badge.png)"
                " ![p](https://static.pepy.tech/badge/x.png)"
                " ![c](https://codecov.io/gh/o/r/graph/x.png)"
                " ![b](https://badgen.net/x.png)"
                " ![h](https://api.star-history.com/x.png)"
                " ![k](https://komarev.com/x.png)"
            ),
            [],
        ),
        ("![a](docs/badge-ci.png) ![b](docs/codecov.png)", []),
        # logo-like file names
        (
            (
                "![a](logo.png) ![b](a/Wordmark-dark.png) ![c](lockup.jpg)"
                " ![d](emblem.gif) ![e](app_icon.png) ![f](avatar.jpg)"
            ),
            [],
        ),
        ("![a](logos/overview.png)", [RAW + "logos/overview.png"]),
        # redirecting, expiring or unknown hosts (D-18)
        (
            (
                "![a](https://github.com/user-attachments/assets/fa42d587-068d.png)"
                f" ![b](https://github.com/{O}/{R}/assets/123/abc.png)"
                f" ![c](https://huggingface.co/{O}/{R}/resolve/main/a.png)"
                " ![d](https://private-user-images.githubusercontent.com/1/a.png)"
                " ![e](https://camo.githubusercontent.com/abc/a.png)"
                " ![f](https://user-images.githubusercontent.com/1/a.png)"
                " ![g](https://example.com/a.png)"
            ),
            [],
        ),
        # HTML comments and fenced code blocks are ignored
        ("<!-- ![a](hidden.png) -->\n![b](shown.png)", [RAW + "shown.png"]),
        ("<!--\n<img src='hidden.png'>\n-->", []),
        ("```md\n![a](code.png)\n```\n![b](after.png)", [RAW + "after.png"]),
        ("~~~\n<img src='tilde.png'>\n~~~", []),
        # too long for the schema
        ("![a](" + "d/" * 200 + "a.png)", []),
        ("no images here", []),
    ],
)
def test_readme_candidates(md, expected):
    got = readme_candidates(md, O, R)
    assert got == expected
    for url in got:
        assert url.startswith(IMAGE_HOSTS) and len(url) <= IMAGE_URL_MAX
        assert "?" not in url and "#" not in url
        assert ItemImage(url=url, width=576, height=300).url == url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/o/r", ("o", "r")),
        ("https://github.com/o/r/", ("o", "r")),
        ("https://github.com/o/r.git", ("o", "r")),
        ("https://github.com/Tencent-Hunyuan/Hy-Nomas", ("Tencent-Hunyuan", "Hy-Nomas")),
        ("https://github.com/o/my.repo_x", ("o", "my.repo_x")),
        ("http://github.com/o/r", None),
        ("https://gitlab.com/o/r", None),
        ("https://github.com.evil.com/o/r", None),
        ("https://github.com/o/r/tree/main", None),
        ("https://github.com/o", None),
        ("https://github.com/o/..", None),
        ("https://github.com/o/a..b", None),
        ("https://github.com/o_x/r", None),
        ("https://github.com/o/r?tab=x", None),
        (None, None),
        (123, None),
    ],
)
def test_parse_repo(url, expected):
    assert parse_repo(url) == expected
