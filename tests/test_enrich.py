"""Code-decided model facts from the HF paper/model APIs (ANLY-08, D-07)."""

import json
from pathlib import Path

import pytest
import respx
from conftest import FakeAnthropic, mock_enrich, mock_hf_week

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


def test_w44_coverage_and_verdicts_untouched(items, hf_pages):
    out, _ = _run(items, _entries(hf_pages, items))
    assert sum(it.model_info.size != UNKNOWN for it in out) == 0
    assert sum(it.model_info.training_data != UNKNOWN for it in out) == 1
    assert sum(it.model_info.release != UNKNOWN for it in out) == 6
    for before, after in zip(items, out, strict=True):
        assert after.commercial == before.commercial
        assert after.poc.verdict == before.poc.verdict == "확인 필요"
        assert after.hardware.local_run == "확인 필요"
        assert after.claude_gpt == before.claude_gpt
        assert after.model_info.kind_ko == before.model_info.kind_ko


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
