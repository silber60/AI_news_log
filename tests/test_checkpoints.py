"""05-02, D-04, AUTO-05: per-stage checkpoints in archive/<week>/ and --force-stage."""

import json
import logging

import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter import store
from newsletter.schema import Item, ItemAnalysisLLM

ISSUE_ID = "2026-W44"


def _build(hf_pages, fake, **kw):
    """One build under respx. Returns (issue, HF daily_papers calls, all HTTP calls)."""
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        mock_hf_week(router, hf_pages, ISSUE_ID)
        issue = run_build(ISSUE_ID, claude_client=fake, **kw)
        urls = [str(c.request.url) for c in router.calls]
    hf = sum("huggingface.co/api/daily_papers" in u for u in urls)
    return issue, hf, len(urls)


def _analyze_calls(fake: FakeAnthropic) -> int:
    return sum(c["kw"].get("output_format") is ItemAnalysisLLM for c in fake.calls)


def _stage_lines(caplog) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in caplog.records:
        msg = r.getMessage()
        if msg.startswith("checkpoint="):
            stage, verdict = msg.removeprefix("checkpoint=").split(" ", 1)
            out.setdefault(stage, []).append(verdict)
    return out


# ---------------------------------------------------------------- Task 1 tracer


def test_write_json_atomic_replaces_and_leaves_no_tmp(tmp_path):
    path = tmp_path / "a" / "x.json"
    store.write_json_atomic(path, {"v": 1})
    store.write_json_atomic(path, {"v": 2, "s": "한글"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 2, "s": "한글"}
    assert path.read_text(encoding="utf-8").endswith("}\n")
    assert sorted(p.name for p in path.parent.iterdir()) == ["x.json"]


def test_checkpoint_path_layout(archive_tmp):
    p = store.checkpoint_path(ISSUE_ID, "analyze")
    assert p == archive_tmp / "archive" / ISSUE_ID / "checkpoints" / "analyze.json"
    assert store.CHECKPOINT_VERSION == 1


def test_second_build_reuses_fetch_and_analyze(hf_pages, archive_tmp, caplog):
    caplog.set_level(logging.INFO, logger="newsletter.pipeline")
    first = FakeAnthropic()
    _, hf1, _ = _build(hf_pages, first)
    assert _analyze_calls(first) == 10
    assert hf1 == 3
    lines = _stage_lines(caplog)
    assert lines["fetch"] == ["computed"] and lines["analyze"] == ["computed"]

    caplog.clear()
    second = FakeAnthropic()
    _, hf2, _ = _build(hf_pages, second)
    assert _analyze_calls(second) == 0
    assert hf2 == 0
    lines = _stage_lines(caplog)
    assert lines["fetch"] == ["reused"] and lines["analyze"] == ["reused"]

    cp = json.loads(store.checkpoint_path(ISSUE_ID, "analyze").read_text(encoding="utf-8"))
    assert (cp["version"], cp["issue_id"], cp["stage"]) == (1, ISSUE_ID, "analyze")
    items = [Item.model_validate(d) for d in cp["data"]]
    assert [it.rank for it in items] == list(range(1, 11))
    assert not list((archive_tmp / "archive").rglob("*.tmp"))
