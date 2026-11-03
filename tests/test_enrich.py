"""Code-decided model facts from the HF paper/model APIs (ANLY-08, D-07)."""

import json
import re
from pathlib import Path

import httpx
import pytest
import respx
from conftest import FakeAnthropic, image_bytes, mock_enrich, mock_hf_week, partial

from newsletter.schema import UNKNOWN, HfEntry, Item, LicenseInfo, ModelInfo
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


def _one(item: Item, paper: dict, models: dict | None = None, **mock_kw) -> tuple[Item, dict]:
    out, routes = _run([item], [], papers={item.paper_id: paper}, models=models or {}, **mock_kw)
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


# D-03, D-09 on the upvote Top 10, from github_license_w44.json and hf_models_w44.json.
W44_COMMERCIAL = [
    "확인 필요",  # 1 no repo, no model: neither side exists
    "확인 필요",  # 2 justin4ai/OmniShowcase: GitHub 404 (no license file)
    "가능",  # 3 JusperLee/Falcon: Apache-2.0 code + apache-2.0 weights
    "확인 필요",  # 4 Hy-Nomas: code NOASSERTION
    "확인 필요",  # 5 awesome-working-agent: 404
    "확인 필요",  # 6 LOWN: 404
    "확인 필요",  # 7 no repo, no model
    "확인 필요",
    "확인 필요",
    "확인 필요",  # 10 ChronoReplay: 404
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
    assert [it.commercial.verdict for it in out] == W44_COMMERCIAL
    r3 = out[2].commercial
    assert (r3.code_license.spdx_id, r3.weights_license.spdx_id) == ("Apache-2.0", "apache-2.0")
    assert [e.label for e in r3.evidence] == ["가중치 라이선스", "코드 라이선스"]
    assert out[0].commercial == items[0].commercial  # no side at all
    assert out[1].commercial.code_license == LicenseInfo()
    assert out[1].commercial.weights_license is None
    for before, after in zip(items, out, strict=True):
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
    # D-10: 494M x 2 bytes x 1.2 = 1.2 GB, cited by the model page.
    assert (out.hardware.est_vram_gb, out.hardware.local_run) == (1.2, "가능")
    assert [e.url for e in out.hardware.evidence] == ["https://huggingface.co/org/m"]


def test_packed_quantized_safetensors_keep_count_but_no_vram(items):
    paper = _paper(**_model("org/m"))
    model = {
        "id": "org/m",
        "safetensors": {"parameters": {"I32": 6476005376, "F16": 263772160}, "total": 6739777536},
        "tags": ["base_model:quantized:meta-llama/Llama-2-7b-hf"],
    }
    out, _ = _one(items[0], paper, {"org/m": model})
    assert out.hardware.param_count == 6739777536
    assert (out.hardware.est_vram_gb, out.hardware.local_run) == (None, UNKNOWN)
    assert out.hardware.evidence == []


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


# ------------------------------------------------------------ GitHub license

REPO = "https://github.com/o/r"
APACHE = {
    "status_code": 200,
    "body": {
        "license": {"key": "apache-2.0", "name": "Apache License 2.0", "spdx_id": "Apache-2.0"},
        "html_url": "https://github.com/o/r/blob/main/LICENSE",
    },
}
NOASSERTION = {
    "status_code": 200,
    "body": {
        "license": {"key": "other", "name": "Other", "spdx_id": "NOASSERTION"},
        "html_url": "https://github.com/o/r/blob/main/LICENSE",
    },
}


def _code_item(items) -> Item:
    return items[0].model_copy(update={"github_url": REPO})


@pytest.mark.parametrize(
    ("entry", "verdict", "status"),
    [
        (APACHE, "가능", "ok"),
        (NOASSERTION, UNKNOWN, "ok"),
        ({"status_code": 404, "body": {}}, UNKNOWN, "none"),
        ({"status_code": 403, "body": {"message": "rate limit"}}, UNKNOWN, "http_403"),
        ({"status_code": 500, "body": {}}, UNKNOWN, "http_500"),
        ({"status_code": 301, "body": {}}, UNKNOWN, "http_301"),
    ],
)
def test_github_license_outcomes_are_non_fatal(items, caplog, entry, verdict, status):
    paper = _paper(githubRepo=REPO)
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _one(_code_item(items), paper, github_licenses={"o/r": entry})
    assert routes["github_api"].call_count == 1
    assert out.commercial.verdict == verdict
    assert out.commercial.weights_license is None
    assert out.poc.verdict == "코드만"  # the rest of enrich still ran
    assert f"license={status} rank=1" in caplog.text
    if verdict == "가능":
        assert [e.url for e in out.commercial.evidence] == [
            "https://github.com/o/r/blob/main/LICENSE"
        ]
        assert out.commercial.code_license.spdx_id == "Apache-2.0"
    elif entry is NOASSERTION:
        # The file exists, so it stays as evidence for a human to read.
        assert out.commercial.code_license.spdx_id is None
        assert [e.label for e in out.commercial.evidence] == ["코드 라이선스"]
    else:
        assert out.commercial.evidence == []


def test_github_transport_error_is_non_fatal(items, caplog):
    paper = _paper(githubRepo=REPO)
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        # Registered first, so it wins over mock_enrich's github_api route.
        api = router.get(url__regex=r"^https://api\.github\.com/").mock(
            side_effect=httpx.ConnectError("boom")
        )
        mock_enrich(router, papers={items[0].paper_id: paper}, models={})
        with caplog.at_level("INFO", logger="newsletter"):
            out = enrich.enrich_items([_code_item(items)], [])[0]
    assert api.call_count == 1
    assert out.commercial.verdict == UNKNOWN
    assert out.poc.verdict == "코드만"
    assert "license=error_ConnectError rank=1" in caplog.text


def test_bad_repo_url_gives_unknown_code_side_without_request(items, caplog):
    item = items[0].model_copy(update={"github_url": "https://github.com/o/r/tree/x"})
    with caplog.at_level("INFO", logger="newsletter"):
        out, routes = _one(item, _paper(githubRepo=item.github_url))
    assert routes["github_api"].call_count == 0
    assert out.commercial.verdict == UNKNOWN
    assert out.commercial.code_license == LicenseInfo()
    assert "license=bad_repo rank=1" in caplog.text


def test_weights_side_from_model_and_failed_model_fetch(items):
    paper = _paper(**_model("org/m"), githubRepo=REPO)
    model = {"id": "org/m", "cardData": {"license": "cc-by-nc-4.0"}, "tags": []}
    out, _ = _one(_code_item(items), paper, {"org/m": model}, github_licenses={"o/r": APACHE})
    # 불가 on the weights dominates the Apache code side.
    assert out.commercial.verdict == "불가"
    assert out.commercial.weights_license.spdx_id == "cc-by-nc-4.0"
    assert out.commercial.evidence[0].url == "https://huggingface.co/org/m"
    out, _ = _one(_code_item(items), paper, {}, github_licenses={"o/r": APACHE})
    # The weights exist but the model JSON could not be read: 확인 필요.
    assert out.commercial.verdict == UNKNOWN
    assert out.commercial.weights_license == LicenseInfo()
    assert out.commercial.code_license.spdx_id == "Apache-2.0"


def test_failed_paper_fetch_keeps_commercial_default(items):
    item = _code_item(items)
    out, routes = _run([item], [], fail=True)
    assert routes["github_api"].call_count == 0
    assert out[0].commercial == item.commercial


def test_license_logs_carry_no_repo_ids(items, hf_pages, caplog):
    # httpx's own request line is quieted in __main__ (02-02); only ours is checked.
    with caplog.at_level("DEBUG", logger="newsletter"):
        _run(items, _entries(hf_pages, items))
    text = caplog.text
    assert "license=" in text
    for needle in ("OmniShowcase", "justin4ai", "Hy-Nomas", "JusperLee", "api.github.com"):
        assert needle not in text


# ------------------------------------------------------------ enriched.json

TOKEN_RE = re.compile(r"gh[pousr]_[A-Za-z0-9]{10,}|github_pat_|Bearer ", re.IGNORECASE)
RECORD_KEYS = {
    "rank",
    "paper_id",
    "model_id",
    "linked_models",
    "spaces",
    "datasets",
    "weights_license",
    "gated",
    "safetensors",
    "base_model_tags",
    "github_license",
    "paper_fetch_ok",
    "evidence",
}


def _records(items, entries, **mock_kw) -> tuple[list[Item], list[dict]]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        mock_enrich(router, **mock_kw)
        return enrich.enrich_items_with_records(items, entries)


def test_records_one_per_rank_with_public_metadata(items, hf_pages):
    out, records = _records(items, _entries(hf_pages, items))
    assert [r["rank"] for r in records] == list(range(1, 11))
    assert all(set(r) == RECORD_KEYS for r in records)
    assert [r["paper_id"] for r in records] == [it.paper_id for it in items]
    assert all(r["paper_fetch_ok"] for r in records)

    r3 = records[2]  # JusperLee/Falcon
    assert r3["model_id"] == "JusperLee/Falcon"
    assert r3["linked_models"] == [
        {"id": "JusperLee/Falcon", "gated": False},
        {"id": "JusperLee/Falcon-Big", "gated": False},
    ]
    assert r3["spaces"] == ["JusperLee/Falcon-Studio"]
    assert r3["datasets"] == ["JusperLee/RealSSA-Real", "JusperLee/RealSSA-Sim"]
    assert r3["weights_license"] == {
        "license": "apache-2.0",
        "license_name": None,
        "license_link": None,
    }
    assert r3["gated"] is False
    assert r3["safetensors"] is None
    assert r3["github_license"] == {
        "status": "ok",
        "spdx_id": "Apache-2.0",
        "name": "Apache License 2.0",
        "html_url": "https://github.com/JusperLee/Falcon/blob/main/LICENSE",
    }
    assert "https://huggingface.co/JusperLee/Falcon" in r3["evidence"]
    assert "https://github.com/JusperLee/Falcon/blob/main/LICENSE" in r3["evidence"]

    r4 = records[3]  # Hy-Nomas: NOASSERTION code, apache-2.0 weights with a link
    assert r4["github_license"]["status"] == "ok"
    assert r4["github_license"]["spdx_id"] == "NOASSERTION"
    assert r4["weights_license"]["license"] == "apache-2.0"
    assert r4["weights_license"]["license_link"] == (
        "https://huggingface.co/tencent/Hy-Nomas/blob/main/LICENSE"
    )

    r2 = records[1]  # OmniShowcase: no model, GitHub 404
    assert r2["github_license"]["status"] == "none"
    assert (r2["model_id"], r2["weights_license"], r2["safetensors"]) == (None, None, None)
    assert records[0]["github_license"] is None  # no repo, no call
    # The items match the plain enrich_items output.
    plain, _ = _run(items, _entries(hf_pages, items))
    assert out == plain


def test_record_keeps_safetensors_and_base_model_tags(items):
    paper = _paper(**_model("org/m"))
    model = {
        "id": "org/m",
        "cardData": {"license": "gemma"},
        "tags": ["license:gemma", "base_model:google/gemma-2-2b", "base_model:finetune:x/y"],
        "safetensors": {"parameters": {"F32": 302130176}, "total": 302130176},
    }
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        mock_enrich(router, papers={items[0].paper_id: paper}, models={"org/m": model})
        _, (rec,) = enrich.enrich_items_with_records(items[:1], [])
    assert rec["safetensors"] == {"total": 302130176, "parameters": {"F32": 302130176}}
    assert rec["base_model_tags"] == ["base_model:google/gemma-2-2b", "base_model:finetune:x/y"]
    assert rec["weights_license"]["license"] == "gemma"


def test_record_for_failed_paper_fetch(items):
    _, records = _records(items[:2], [], fail=True)
    for rec in records:
        assert set(rec) == RECORD_KEYS
        assert rec["paper_fetch_ok"] is False
        assert rec["paper_id"] in (items[0].paper_id, items[1].paper_id)
        for key in ("model_id", "weights_license", "gated", "safetensors", "github_license"):
            assert rec[key] is None, key
        for key in ("linked_models", "spaces", "datasets", "base_model_tags", "evidence"):
            assert rec[key] == [], key
    bad = items[0].model_copy(update={"paper_id": "not-a-paper"})
    _, (rec,) = _records([bad], [])
    assert rec["paper_fetch_ok"] is False


def test_records_hold_no_authors_ko_or_tokens(items, hf_pages, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_" + "a" * 36)
    _, records = _records(items, _entries(hf_pages, items))
    text = json.dumps(records, ensure_ascii=False)
    assert '"authors"' not in text
    assert "_ko" not in text
    assert not TOKEN_RE.search(text)


@pytest.mark.parametrize(
    "model",
    [
        {"id": "org/m", "cardData": {"license": "apache-2.0"}, "tags": []},
        {"id": "org/m", "cardData": {}, "tags": ["license:apache-2.0"]},
    ],
    ids=["cardData", "tag-fallback"],
)
def test_weights_license_card_and_tag_paths_agree(items, model):
    out, _ = _one(items[0], _paper(**_model("org/m")), {"org/m": model})
    assert out.commercial.verdict == "가능"
    assert out.commercial.weights_license.spdx_id == "apache-2.0"
    assert out.commercial.code_license is None


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
        assert it.commercial.verdict == UNKNOWN
    week = archive_tmp / "archive" / ISSUE_ID
    assert (week / "issue.json").is_file()
    enriched = json.loads((week / "enriched.json").read_text(encoding="utf-8"))
    assert [r["paper_fetch_ok"] for r in enriched["items"]] == [False] * 10


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
