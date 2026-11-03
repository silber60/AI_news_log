"""Code-decided model facts from the HF paper/model APIs (ANLY-08, D-07)."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from conftest import FakeAnthropic, image_bytes, mock_enrich, mock_hf_week, partial

from newsletter.schema import UNKNOWN, HfEntry, Item, ModelInfo
from newsletter.stages import enrich

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ISSUE_ID = "2026-W44"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(enrich, "RETRY_WAIT_MULTIPLIER", 0)


@pytest.fixture
def items(issue_w44) -> list[Item]:
    """W44 items with every code-owned fact reset to its default."""
    out = []
    for it in issue_w44.items:
        info = ModelInfo(
            kind_ko=it.model_info.kind_ko, architecture_ko=it.model_info.architecture_ko
        )
        out.append(it.model_copy(update={"model_info": info, "image": None}))
    return out


def _entries(hf_pages, items: list[Item]) -> list[HfEntry]:
    by_id = {d["paper"]["id"]: d for page in hf_pages for d in page}
    return [HfEntry.model_validate(by_id[it.paper_id]) for it in items]


def _run(items, entries, **mock_kw) -> tuple[list[Item], dict]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        routes = mock_enrich(router, **mock_kw)
        out = enrich.enrich_items(items, entries)
    return out, routes


def _one(item: Item, paper: dict, models: dict | None = None) -> tuple[Item, dict]:
    out, routes = _run([item], [], papers={item.paper_id: paper}, models=models or {})
    return out[0], routes


def _facts(it: Item) -> tuple[str, str, str]:
    return it.model_info.size, it.model_info.training_data, it.model_info.release


# --------------------------------------------------------------- W44 captures


def test_w44_rank3_facts_and_release(items, hf_pages):
    out, _ = _run(items, _entries(hf_pages, items))
    r3 = out[2]
    assert r3.paper_id == "2610.32749"
    assert r3.model_info.training_data == "JusperLee/RealSSA-Real, JusperLee/RealSSA-Sim"
    assert r3.model_info.release == "가중치 · GitHub · 데모"
    assert r3.model_info.size == UNKNOWN  # no safetensors on Falcon
    assert r3.hardware.param_count is None
    assert (r3.poc.has_weights, r3.poc.has_code, r3.poc.has_demo) == (True, True, True)
    assert [e.url for e in r3.model_info.evidence] == [
        "https://huggingface.co/JusperLee/Falcon",
        "https://huggingface.co/spaces/JusperLee/Falcon-Studio",
    ]


def test_w44_rank4_release_and_benchmark_not_training_data(items, hf_pages):
    out, _ = _run(items, _entries(hf_pages, items))
    r4 = out[3]
    assert r4.paper_id == "2610.36729"
    assert r4.model_info.release == "가중치 · GitHub · 데모"
    # The paper links tencent/Hy-Nomas-Bench, a benchmark citing the paper (Pitfall 2).
    assert r4.model_info.training_data == UNKNOWN
    assert "Bench" not in r4.model_info.training_data


def test_w44_rank1_stays_unknown(items, hf_pages):
    out, _ = _run(items, _entries(hf_pages, items))
    r1 = out[0]
    assert _facts(r1) == (UNKNOWN, UNKNOWN, UNKNOWN)
    assert (r1.poc.has_weights, r1.poc.has_code, r1.poc.has_demo) == (None, None, None)
    assert r1.model_info.evidence == []


W44_POC = [
    "논문만",  # 1 2610.37381: no repo, no model, no Space
    "코드만",
    "바로 가능",  # 3 Falcon: Space first
    "바로 가능",
    "코드만",
    "코드만",
    "논문만",
    "논문만",
    "논문만",
    "코드만",
]


def test_w44_coverage_and_code_poc(items, hf_pages):
    out, _ = _run(items, _entries(hf_pages, items))
    assert sum(it.model_info.size != UNKNOWN for it in out) == 0
    assert sum(it.model_info.training_data != UNKNOWN for it in out) == 1
    assert sum(it.model_info.release != UNKNOWN for it in out) == 6
    assert [it.poc.verdict for it in out] == W44_POC
    assert out[0].paper_id == "2610.37381"
    assert [e.url for e in out[0].poc.evidence] == [out[0].hf_url]
    assert [e.label for e in out[2].poc.evidence] == ["HF 데모"]
    for before, after in zip(items, out, strict=True):
        assert after.commercial == before.commercial
        assert after.hardware.local_run == "확인 필요"
        assert after.claude_gpt == before.claude_gpt
        assert after.model_info.kind_ko == before.model_info.kind_ko


def test_failed_paper_fetch_keeps_poc_unknown(items):
    # D-15: 논문만 is a negative claim, so it needs a successful paper fetch.
    out, _ = _run(items[:1], [], fail=True)
    assert out[0].poc.verdict == UNKNOWN
    assert out[0].poc.evidence == []
    bad = items[0].model_copy(update={"paper_id": "not-a-paper"})
    out, routes = _run([bad], [])
    assert routes["papers"].call_count == 0
    assert out[0].poc.verdict == UNKNOWN


def test_absence_is_never_written_as_false(items, hf_pages):
    out, _ = _run(items, _entries(hf_pages, items))
    for it in out:
        for flag in (it.poc.has_weights, it.poc.has_code, it.poc.has_demo):
            assert flag in (True, None)
        assert it.hardware.param_count is None or it.hardware.param_count > 0


# ---------------------------------------------------------------- code rules


def _paper(**kw) -> dict:
    base = {"linkedModels": [], "linkedDatasets": [], "linkedSpaces": []}
    base.update(kw)
    return base


def _model(mid: str, **kw) -> dict:
    return {"linkedModels": [{"id": mid, "gated": False, "private": False, "downloads": 5, **kw}]}


def test_linked_datasets_on_paper_are_ignored(items):
    paper = _paper(
        **_model("org/m"),
        linkedDatasets=[{"id": "org/eval-bench"}, {"id": "org/other"}],
    )
    out, _ = _one(items[0], paper, {"org/m": {"id": "org/m", "cardData": {}, "tags": []}})
    assert out.model_info.training_data == UNKNOWN
    assert out.model_info.release == "가중치"


def test_gated_model_release(items):
    paper = _paper(**_model("org/m", gated="manual"))
    out, _ = _one(items[0], paper, {"org/m": {"id": "org/m"}})
    assert out.model_info.release == "가중치(승인 필요)"
    assert out.poc.has_weights is True
    assert out.poc.has_code is None and out.poc.has_demo is None


def test_safetensors_size_and_param_count(items):
    paper = _paper(**_model("org/m"))
    model = {"id": "org/m", "safetensors": {"parameters": {"BF16": 494032768}, "total": 494032768}}
    out, _ = _one(items[0], paper, {"org/m": model})
    assert out.model_info.size == "494M 파라미터"
    assert out.hardware.param_count == 494032768


def test_size_billions_and_extra_models(items):
    paper = _paper(
        linkedModels=[
            {"id": "org/big", "gated": False, "private": False, "downloads": 900},
            {"id": "org/small", "gated": False, "private": False, "downloads": 10},
            {"id": "org/secret", "gated": False, "private": True, "downloads": 10_000},
        ]
    )
    models = {"org/big": {"id": "org/big", "safetensors": {"total": 7_000_000_000}}}
    out, routes = _one(items[0], paper, models)
    assert out.model_info.size == "7B 파라미터 (외 1개 모델)"
    assert routes["models"].call_count == 1
    assert enrich.fmt_params(1_500_000_000) == "1.5B"


def test_training_data_from_tags_and_limits(items):
    long_id = "org/" + "x" * 60
    tags = [f"dataset:{long_id}", "dataset:org/b", "dataset:org/c", "dataset:org/d", "license:mit"]
    out, _ = _one(items[0], _paper(**_model("org/m")), {"org/m": {"id": "org/m", "tags": tags}})
    td = out.model_info.training_data
    first = td.split(", ")[0]
    assert len(first) == 40 and first.endswith("…")
    assert td.endswith("org/b, org/c 외 1개")
    assert len(td) <= 135


def test_card_datasets_string_is_accepted(items):
    model = {"id": "org/m", "cardData": {"datasets": "org/only"}}
    out, _ = _one(items[0], _paper(**_model("org/m")), {"org/m": model})
    assert out.model_info.training_data == "org/only"


def test_invalid_model_id_is_skipped_without_request(items):
    paper = _paper(**_model("../../etc/passwd"), linkedSpaces=[{"id": "bad id/with space"}])
    out, routes = _one(items[0], paper, {})
    assert routes["models"].call_count == 0
    # The model is still linked on the paper, so weights are public; no evidence link.
    assert out.model_info.release == "가중치"
    assert out.model_info.evidence == []
    assert out.poc.has_demo is None


def test_model_404_keeps_paper_facts(items, caplog):
    paper = _paper(**_model("org/missing"), githubRepo="https://github.com/o/r")
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _one(items[0], paper, {})
    assert routes["models"].call_count == 1  # 404 is not retried
    assert out.model_info.release == "가중치 · GitHub"
    assert out.model_info.training_data == UNKNOWN
    assert "enrich=partial rank=1 reason=http_404" in caplog.text


def test_server_error_is_retried_once_then_defaults(items, caplog):
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _run(items[:1], [], fail=True)
    assert routes["papers"].call_count == enrich.ATTEMPTS == 2
    assert _facts(out[0]) == (UNKNOWN, UNKNOWN, UNKNOWN)
    assert "enrich=partial rank=1 reason=http_500" in caplog.text


def test_logs_carry_no_ids_or_dataset_names(items, hf_pages, caplog):
    with caplog.at_level("DEBUG", logger="newsletter"):
        _run(items, _entries(hf_pages, items))
    text = caplog.text
    assert "enrich=ok rank=3" in text
    for needle in ("JusperLee", "Falcon", "RealSSA", "tencent", "Hy-Nomas", "2610."):
        assert needle not in text


# ---------------------------------------------------------------- run_build


def _build(hf_pages, **kw):
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        mock_hf_week(router, hf_pages, ISSUE_ID, **kw)
        return run_build(ISSUE_ID, claude_client=FakeAnthropic())


def test_build_survives_total_hf_enrich_outage(hf_pages, archive_tmp):
    issue = _build(hf_pages, enrich_fail=True)
    assert len(issue.items) == 10
    for it in issue.items:
        assert _facts(it) == (UNKNOWN, UNKNOWN, UNKNOWN)
        assert it.image is None
        assert (it.poc.has_weights, it.poc.has_code, it.poc.has_demo) == (None, None, None)
    assert (archive_tmp / "archive" / ISSUE_ID / "issue.json").is_file()


# ------------------------------------------------------------------- images

CDN = "https://cdn-uploads.huggingface.co/production/uploads/abc/"
RANK1_IMG = (
    "https://cdn-uploads.huggingface.co/production/uploads/"
    "6415947858a690df103af49f/TdENf5Pa8C0iPVuP164gl.png"
)


def _entry_with_media(hf_pages, item: Item, media: list[str] | None) -> HfEntry:
    entry = _entries(hf_pages, [item])[0]
    paper = entry.paper.model_copy(update={"mediaUrls": media})
    return entry.model_copy(update={"paper": paper})


def _img_run(hf_pages, item: Item, media, response=None) -> tuple[Item, dict]:
    entry = _entry_with_media(hf_pages, item, media)
    out, routes = _run([item], [entry], papers={}, models={}, image=response)
    return out[0], routes


def _resp(body: bytes, ctype: str = "image/png", status: int = 206) -> httpx.Response:
    if status == 206:
        return partial(body, ctype)
    return httpx.Response(status, headers={"content-type": ctype}, content=body)


@pytest.mark.parametrize(
    ("media", "picked"),
    [
        ([CDN + "a.mp4", CDN + "b.PNG", CDN + "c.png"], CDN + "b.PNG"),
        (["https://example.com/x.png", CDN + "d.jpeg"], CDN + "d.jpeg"),
        (["http://cdn-uploads.huggingface.co/x.png", CDN + "e.gif"], CDN + "e.gif"),
        (["https://cdn-uploads.huggingface.co.evil.com/x.png", CDN + "f.jpg"], CDN + "f.jpg"),
        ([CDN + "a.mp4", CDN + "b.webp"], None),
        ([], None),
        (None, None),
    ],
)
def test_image_candidate_selection(media, picked):
    assert enrich.pick_image_url(media) == picked


def test_png_is_sized_to_576_from_ranged_get(items, hf_pages):
    out, routes = _img_run(hf_pages, items[0], [CDN + "a.mp4", CDN + "wide.png"])
    assert out.image is not None
    assert (out.image.url, out.image.width, out.image.height) == (CDN + "wide.png", 576, 234)
    req = routes["cdn"].calls.last.request
    assert req.headers["range"] == "bytes=0-65535"
    assert routes["cdn"].call_count == 1


def test_mp4_only_gives_no_image_and_no_request(items, hf_pages):
    out, routes = _img_run(hf_pages, items[0], [CDN + "clip.mp4"])
    assert out.image is None
    assert routes["cdn"].call_count == 0


@pytest.mark.parametrize(
    ("fmt", "ctype", "name"), [("GIF", "image/gif", "x.gif"), ("JPEG", "image/jpeg", "x.jpg")]
)
def test_gif_and_jpeg_accepted(items, hf_pages, fmt, ctype, name):
    resp = _resp(image_bytes((1000, 500), fmt), ctype, status=200)
    out, _ = _img_run(hf_pages, items[0], [CDN + name], resp)
    assert out.image is not None
    assert (out.image.width, out.image.height) == (576, 288)


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (_resp(image_bytes((400, 400))), "width"),
        (_resp(image_bytes((4800, 600))), "ratio"),
        (_resp(image_bytes((1000, 1000))), "ratio"),
        (_resp(image_bytes((1152, 468)), "text/html"), "content_type"),
        (_resp(image_bytes((1152, 468)), status=404), "http_404"),
        (_resp(b"\x89PNG\r\n\x1a\n garbage"), "decode"),
        (
            httpx.Response(200, headers={"content-type": "image/png", "content-length": "0"}),
            "decode",
        ),
        (_resp(image_bytes((575, 300))), "width"),
        (partial(image_bytes((1152, 468)), total=1_000_001), "bytes"),
        (partial(image_bytes((1152, 468)), "image/gif", total=3_990_000), "bytes"),
        (
            httpx.Response(
                200,
                headers={"content-type": "image/png", "content-length": "1000001"},
                content=image_bytes((1152, 468)),
            ),
            "bytes",
        ),
        (
            httpx.Response(
                206, headers={"content-type": "image/png"}, content=image_bytes((1152, 468))
            ),
            "bytes_unknown",
        ),
        (
            httpx.Response(
                206,
                headers={"content-type": "image/png", "content-range": "bytes 0-65535/*"},
                content=image_bytes((1152, 468)),
            ),
            "bytes_unknown",
        ),
        (httpx.Response(302, headers={"location": CDN + "elsewhere.png"}), "redirect"),
        (httpx.Response(301, headers={"location": CDN + "elsewhere.png"}), "redirect"),
    ],
)
def test_bad_images_are_rejected_without_raising(items, hf_pages, caplog, response, reason):
    with caplog.at_level("INFO", logger="newsletter"):
        out, _ = _img_run(hf_pages, items[0], [CDN + "x.png"], response)
    assert out.image is None
    assert f"image=none rank=1 reason={reason}" in caplog.text
    assert "cdn-uploads" not in caplog.text


@pytest.mark.parametrize(
    ("size", "height"),
    [
        ((1200, 1000), 480),  # ratio 1.2, inclusive
        ((1190, 1000), None),
        ((4000, 1000), 144),  # ratio 4.0, inclusive
        ((4010, 1000), None),
        ((576, 288), 288),  # exactly the card width
        ((575, 288), None),
    ],
)
def test_ratio_and_width_bounds(items, hf_pages, size, height):
    out, _ = _img_run(hf_pages, items[0], [CDN + "x.png"], _resp(image_bytes(size)))
    if height is None:
        assert out.image is None
    else:
        assert out.image is not None
        assert (out.image.width, out.image.height) == (576, height)
    assert (enrich.RATIO_MIN, enrich.RATIO_MAX) == (1.2, 4.0)


@pytest.mark.parametrize(("total", "ok"), [(1_000_000, True), (1_000_001, False)])
def test_total_byte_cap_is_inclusive(items, hf_pages, total, ok):
    out, _ = _img_run(hf_pages, items[0], [CDN + "x.png"], partial(image_bytes(), total=total))
    assert (out.image is not None) is ok
    assert enrich.IMAGE_MAX_TOTAL_BYTES == 1_000_000


def test_redirect_is_not_followed(items, hf_pages, caplog):
    resp = httpx.Response(302, headers={"location": CDN + "elsewhere.png"})
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _img_run(hf_pages, items[0], [CDN + "x.png"], resp)
    assert out.image is None
    assert routes["cdn"].call_count == 1
    assert str(routes["cdn"].calls.last.request.url) == CDN + "x.png"
    assert "image=none rank=1 reason=redirect" in caplog.text


def test_image_never_reads_more_than_64k(items, hf_pages):
    big = image_bytes((1152, 468)) + b"\0" * 300_000  # server ignored Range
    out, _ = _img_run(hf_pages, items[0], [CDN + "x.png"], _resp(big, status=200))
    assert out.image is not None
    assert enrich.IMAGE_MAX_BYTES == 65536


RAW = "https://raw.githubusercontent.com/"
# D-08, D-18: README images the W44 capture supports, by fixture rank (captured
# 2026-11-03). Rank 5 skips a 7.6 MB demo GIF, rank 7 has only 480 px thumbnails
# and WebP, rank 10 has only a 2.75 MB banner; ranks 1-4 have badges, logos, SVG
# or redirecting hosts only.
README_IMAGES = {
    5: (RAW + "google-deepmind/detectorscope/HEAD/assets/overview.png", 245),
    6: (RAW + "simple-agent-lab/RSIHub/HEAD/docs/assets/paper-poster-lora-gen0.png", 360),
    8: (RAW + "BinceQu/RoboHarness/HEAD/docs/assets/overview.png", 468),
    9: (RAW + "datamllab/OpenEBFM/HEAD/figs/dclm_pretrain.png", 429),
}


def _images(issue) -> dict[int, tuple[str, int]]:
    out = {}
    for it in issue.items:
        if it.image is not None:
            assert it.image.width == 576
            out[it.rank] = (it.image.url, it.image.height)
    return out


def test_build_gives_star_cards_their_readme_images(hf_pages, archive_tmp, caplog):
    from newsletter.pipeline import run_build

    with (
        caplog.at_level("DEBUG", logger="newsletter"),
        respx.mock(assert_all_mocked=True, assert_all_called=True) as router,
    ):
        mock_hf_week(router, hf_pages, ISSUE_ID)
        issue = run_build(ISSUE_ID, claude_client=FakeAnthropic())
        paths = [c.request.url.path for c in router.calls]
    assert _images(issue) == README_IMAGES
    readmes = [p for p in paths if p.endswith("/README.md")]
    assert len(readmes) == 10
    text = caplog.text
    assert "raw.githubusercontent" not in text and "cdn-uploads" not in text
    assert "image=ok rank=5" in text
    assert "image=none rank=7 reason=width" in text
    assert "image=none rank=10 reason=bytes" in text
    assert "image=none rank=1 reason=no_candidate" in text


def test_build_uses_hf_image_first_and_skips_its_readme(hf_pages, archive_tmp):
    from newsletter.pipeline import run_build

    # The star rank-1 paper (2610.35518) has no HF image in the W44 capture, so a
    # test-local copy gives it the old rank-1 PNG.
    pages = json.loads(json.dumps(hf_pages))
    hits = [d for page in pages for d in page if d["paper"]["id"] == "2610.35518"]
    assert len(hits) == 1
    hits[0]["paper"]["mediaUrls"] = [RANK1_IMG]
    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        mock_hf_week(router, pages, ISSUE_ID)
        cdn = router.get(url__regex=r"^https://cdn-uploads\.huggingface\.co/").mock(
            return_value=partial(image_bytes())
        )
        issue = run_build(ISSUE_ID, claude_client=FakeAnthropic())
        paths = [c.request.url.path for c in router.calls]
    assert cdn.call_count == 1
    assert issue.items[0].paper_id == "2610.35518"
    first = issue.items[0].image
    assert first is not None
    assert (first.url, first.width, first.height) == (RANK1_IMG, 576, 234)
    assert _images(issue) == {1: (RANK1_IMG, 234), **README_IMAGES}
    assert "/InternLM/xtuner/HEAD/README.md" not in paths
    assert "/hyz317/HairDeck/HEAD/README.md" in paths


# ------------------------------------------------- HF -> README fall-through

REPO = "https://github.com/o/r"
README_PNG = "https://raw.githubusercontent.com/o/r/HEAD/docs/wide.png"
README_TEXT = "SECRET-README-TEXT ![a](docs/wide.png)"
WIDE = {"status": 206, "content_type": "image/png", "width": 1200, "height": 600}


def _repo_run(hf_pages, item, media, response=None, readme=README_TEXT, images=None):
    entry = _entry_with_media(hf_pages, item, media)
    paper = entry.paper.model_copy(update={"githubRepo": REPO})
    entry = entry.model_copy(update={"paper": paper})
    images = {README_PNG: {**WIDE, "total_bytes": 200_000}} if images is None else images
    out, routes = _run(
        [item],
        [entry],
        papers={},
        models={},
        image=response,
        readmes={"o/r": readme},
        readme_images=images,
    )
    return out[0], routes


def _github_paths(routes) -> list[str]:
    return [c.request.url.path for c in routes["github"].calls]


def test_heavy_hf_gif_falls_through_to_readme(items, hf_pages, caplog):
    gif = partial(image_bytes((1000, 500), "GIF"), "image/gif", total=3_990_000)
    with caplog.at_level("DEBUG", logger="newsletter"):
        out, routes = _repo_run(hf_pages, items[0], [CDN + "anim.gif"], gif)
    assert out.image is not None
    assert (out.image.url, out.image.width, out.image.height) == (README_PNG, 576, 288)
    assert routes["cdn"].call_count == 1
    assert _github_paths(routes) == ["/o/r/HEAD/README.md", "/o/r/HEAD/docs/wide.png"]
    assert routes["github"].calls[1].request.headers["range"] == "bytes=0-65535"
    text = caplog.text
    assert "image=skip rank=1 reason=bytes" in text and "image=ok rank=1" in text
    for needle in ("SECRET-README-TEXT", "raw.githubusercontent", "cdn-uploads", "wide.png"):
        assert needle not in text


def test_readme_is_not_requested_when_hf_image_passes(items, hf_pages):
    out, routes = _repo_run(hf_pages, items[0], [CDN + "wide.png"])
    assert out.image is not None and out.image.url == CDN + "wide.png"
    assert routes["github"].call_count == 0


def test_missing_readme_means_no_image(items, hf_pages, caplog):
    entry = _entry_with_media(hf_pages, items[0], None)
    entry = entry.model_copy(update={"paper": entry.paper.model_copy(update={"githubRepo": REPO})})
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _run([items[0]], [entry], papers={}, models={}, readmes={})
    assert out[0].image is None
    assert routes["github"].call_count == 1
    assert "readme=none rank=1 reason=http_404" in caplog.text
    assert "image=none rank=1 reason=no_candidate" in caplog.text


def test_readme_server_error_is_non_fatal(items, hf_pages, caplog):
    entry = _entry_with_media(hf_pages, items[0], None)
    entry = entry.model_copy(update={"paper": entry.paper.model_copy(update={"githubRepo": REPO})})
    with caplog.at_level("INFO", logger="newsletter"):
        out, _ = _run([items[0]], [entry], fail=True)
    assert out[0].image is None
    assert "readme=none rank=1 reason=http_500" in caplog.text


def test_bad_repo_url_makes_no_readme_request(items, hf_pages, caplog):
    entry = _entry_with_media(hf_pages, items[0], None)
    bad = entry.paper.model_copy(update={"githubRepo": "https://github.com/o/r/tree/../x"})
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _run(
            [items[0]], [entry.model_copy(update={"paper": bad})], papers={}, models={}
        )
    assert out[0].image is None
    assert routes["github"].call_count == 0
    assert "readme=none rank=1 reason=bad_repo" in caplog.text


def test_readme_read_is_capped(items, hf_pages):
    # The image tag sits past the 256 KB cap, so it is never seen.
    readme = "x" * enrich.README_MAX_BYTES + " ![a](docs/wide.png)"
    out, routes = _repo_run(hf_pages, items[0], None, readme=readme)
    assert out.image is None
    assert _github_paths(routes) == ["/o/r/HEAD/README.md"]


def test_probe_limit_counts_hf_and_readme_together(items, hf_pages, caplog):
    narrow = {"status": 206, "content_type": "image/png", "width": 400, "height": 200}
    names = [f"docs/n{i}.png" for i in range(4)]
    readme = " ".join(f"![a]({n})" for n in names)
    images = {
        f"https://raw.githubusercontent.com/o/r/HEAD/{n}": {**narrow, "total_bytes": 9}
        for n in names
    }
    media = [CDN + f"h{i}.png" for i in range(3)]
    small = _resp(image_bytes((400, 200)))
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _repo_run(hf_pages, items[0], media, small, readme=readme, images=images)
    assert out.image is None
    probes = routes["cdn"].call_count + routes["github"].call_count - 1  # minus README
    assert probes == enrich.MAX_PROBES == 6
    assert routes["cdn"].call_count == 3
    assert "image=none rank=1 reason=probe_limit" in caplog.text


def test_probe_limit_on_hf_media_skips_the_readme(items, hf_pages, caplog):
    media = [CDN + f"h{i}.png" for i in range(7)]
    small = _resp(image_bytes((400, 200)))
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _repo_run(hf_pages, items[0], media, small)
    assert out.image is None
    assert routes["cdn"].call_count == 6
    assert routes["github"].call_count == 0
    assert "image=none rank=1 reason=probe_limit" in caplog.text
