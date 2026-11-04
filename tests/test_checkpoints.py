"""05-02, D-04, AUTO-05: per-stage checkpoints in archive/<week>/ and --force-stage."""

import json
import logging

import pytest
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
            if verdict in ("reused", "computed"):
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


# ---------------------------------------------------------------- Task 2

WEEK_OUTPUTS = ("issue.json", "email.html", "email.txt")


def _week(archive_tmp):
    return archive_tmp / "archive" / ISSUE_ID


def _formats(fake: FakeAnthropic, model) -> int:
    return sum(c["kw"].get("output_format") is model for c in fake.calls)


def test_full_reuse_makes_no_call_and_identical_output(hf_pages, archive_tmp, monkeypatch, caplog):
    from newsletter.stages import analyze

    caplog.set_level(logging.INFO, logger="newsletter.pipeline")
    _build(hf_pages, FakeAnthropic())
    week = _week(archive_tmp)
    before = {n: (week / n).read_bytes() for n in WEEK_OUTPUTS}

    def no_client():
        raise AssertionError("make_client called on a full-reuse build")

    monkeypatch.setattr(analyze, "make_client", no_client)
    caplog.clear()
    fake = FakeAnthropic()
    _, hf, http = _build(hf_pages, fake)
    assert fake.calls == []
    assert (hf, http) == (0, 0)
    assert {n: (week / n).read_bytes() for n in WEEK_OUTPUTS} == before
    assert _stage_lines(caplog) == {s: ["reused"] for s in _stages()}

    # No injected client at all: still no make_client call.
    _, hf, http = _build(hf_pages, None)
    assert (hf, http) == (0, 0)
    assert {n: (week / n).read_bytes() for n in WEEK_OUTPUTS} == before


def _stages():
    from newsletter.pipeline import STAGES

    return STAGES


def test_force_stage_notes_recomputes_notes_onward(hf_pages, archive_tmp, caplog):
    from newsletter.schema import HeadlineLLM, VerdictNotesLLM

    caplog.set_level(logging.INFO, logger="newsletter.pipeline")
    _build(hf_pages, FakeAnthropic())
    caplog.clear()
    fake = FakeAnthropic()
    _, hf, http = _build(hf_pages, fake, force_stage="notes")
    assert _analyze_calls(fake) == 0
    assert (hf, http) == (0, 0)  # fetch and enrich reused
    assert _formats(fake, VerdictNotesLLM) >= 1
    assert _formats(fake, HeadlineLLM) == 1
    lines = _stage_lines(caplog)
    stages = _stages()
    cut = stages.index("notes")
    assert lines == {s: ["reused"] if i < cut else ["computed"] for i, s in enumerate(stages)}


def test_force_stage_fetch_recomputes_everything(hf_pages, archive_tmp, caplog):
    caplog.set_level(logging.INFO, logger="newsletter.pipeline")
    _build(hf_pages, FakeAnthropic())
    caplog.clear()
    fake = FakeAnthropic()
    _, hf, _ = _build(hf_pages, fake, force_stage="fetch")
    assert hf == 3
    assert _analyze_calls(fake) == 10
    assert _stage_lines(caplog) == {s: ["computed"] for s in _stages()}


@pytest.mark.parametrize("value", ["none", ""])
def test_force_stage_none_reuses_everything(hf_pages, archive_tmp, value):
    _build(hf_pages, FakeAnthropic())
    fake = FakeAnthropic()
    _, hf, http = _build(hf_pages, fake, force_stage=value)
    assert fake.calls == [] and (hf, http) == (0, 0)


def test_unknown_force_stage_raises(archive_tmp):
    from newsletter.pipeline import run_build

    with pytest.raises(ValueError):
        run_build(ISSUE_ID, claude_client=FakeAnthropic(), force_stage="render")


def _truncate(path):
    path.write_text('{"version": 1, "issue_id": "2026-W', encoding="utf-8")


def _other_week(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["issue_id"] = "2026-W43"
    path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize("damage", [_truncate, _other_week])
def test_bad_checkpoint_is_recomputed_with_later_stages(hf_pages, archive_tmp, caplog, damage):
    from newsletter.schema import HighlightsLLM

    caplog.set_level(logging.INFO, logger="newsletter.pipeline")
    _build(hf_pages, FakeAnthropic())
    damage(store.checkpoint_path(ISSUE_ID, "highlight"))
    caplog.clear()
    fake = FakeAnthropic()
    issue, hf, http = _build(hf_pages, fake)
    assert (hf, http) == (0, 0)
    assert _analyze_calls(fake) == 0
    assert _formats(fake, HighlightsLLM) == 1
    stages = _stages()
    cut = stages.index("highlight")
    assert _stage_lines(caplog) == {
        s: ["reused"] if i < cut else ["computed"] for i, s in enumerate(stages)
    }
    assert any("checkpoint=highlight invalid" in r.getMessage() for r in caplog.records)
    cp = json.loads(store.checkpoint_path(ISSUE_ID, "highlight").read_text(encoding="utf-8"))
    assert cp["issue_id"] == ISSUE_ID
    assert len(issue.highlights) == 3


def test_enrich_checkpoint_holds_prefinalize_items_and_records(hf_pages, archive_tmp, monkeypatch):
    from newsletter.stages import verdicts

    real = verdicts.finalize
    seen: list[int] = []

    def spy(items):
        seen.append(len(items))
        return real(items)

    monkeypatch.setattr(verdicts, "finalize", spy)
    _build(hf_pages, FakeAnthropic())
    assert seen == [10]

    week = _week(archive_tmp)
    cp = json.loads(store.checkpoint_path(ISSUE_ID, "enrich").read_text(encoding="utf-8"))
    assert set(cp["data"]) == {"items", "records"}
    assert [Item.model_validate(d).rank for d in cp["data"]["items"]] == list(range(1, 11))
    enriched = json.loads((week / "enriched.json").read_text(encoding="utf-8"))
    assert enriched["items"] == cp["data"]["records"]

    (week / "enriched.json").unlink()
    seen.clear()
    _build(hf_pages, FakeAnthropic(), force_stage="notes")
    assert seen == [10]  # finalize once on the reuse path too
    again = json.loads((week / "enriched.json").read_text(encoding="utf-8"))
    assert again == enriched


def test_empty_results_are_valid_checkpoints(hf_pages, archive_tmp):
    import anthropic
    import httpx2

    from newsletter.schema import ExplainerLLM, HighlightsLLM, TrendLLM

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    class Down(FakeAnthropic):
        def _handle(self, ns, kw):
            if kw.get("output_format") in (TrendLLM, HighlightsLLM, ExplainerLLM):
                self.calls.append({"ns": ns, "kw": kw})
                raise anthropic.APIConnectionError(request=req)
            return super()._handle(ns, kw)

    first, _, _ = _build(hf_pages, Down())
    assert (first.trend_ko, first.highlights, first.explainer) == (None, [], None)
    for stage, want in (("trend", None), ("highlight", []), ("explainer", None)):
        cp = json.loads(store.checkpoint_path(ISSUE_ID, stage).read_text(encoding="utf-8"))
        assert cp["data"] == want

    fake = FakeAnthropic()
    second, _, _ = _build(hf_pages, fake, force_stage="headline")
    # trend, highlight and explainer reused as empty; only headline and polish ran.
    assert _formats(fake, TrendLLM) == _formats(fake, HighlightsLLM) == 0
    assert _formats(fake, ExplainerLLM) == 0
    assert (second.trend_ko, second.highlights, second.explainer) == (None, [], None)
