"""Past explainer topics record (EXPL-02, D-06)."""

import json
import logging
from pathlib import Path

import pytest

from newsletter import topics
from newsletter.schema import Explainer

REPO = Path(__file__).parent.parent


def _write(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps({"version": 1, "topics": entries}), encoding="utf-8")


def _with_explainer(issue, topic: str = "Mixture of Experts"):
    return issue.model_copy(
        update={"explainer": Explainer(topic=topic, body_ko="본문", related_ranks=[1])}
    )


def test_committed_file_is_empty_version_1():
    d = json.loads((REPO / "data" / "explainer_topics.json").read_text(encoding="utf-8"))
    assert d == {"version": 1, "topics": []}


def test_load_past_on_committed_file_is_empty(monkeypatch):
    monkeypatch.delenv("NEWSLETTER_TOPICS_PATH", raising=False)
    assert topics.topics_path() == REPO / "data" / "explainer_topics.json"
    assert topics.load_past() == []


def test_missing_file_returns_empty_and_warns(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert topics.load_past(tmp_path / "nope.json") == []
    assert "topics=unreadable" in caplog.text


@pytest.mark.parametrize(
    "text",
    ["{not json", '{"version": 2, "topics": []}', '{"version": 1, "topics": [{"x": 1}]}', "[]"],
)
def test_invalid_file_returns_empty_and_warns(tmp_path, caplog, text):
    p = tmp_path / "t.json"
    p.write_text(text, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert topics.load_past(p) == []
    assert "topics=unreadable" in caplog.text


def test_load_past_caps_at_52_newest_first(tmp_path):
    p = tmp_path / "t.json"
    entries = [
        {"issue_id": f"{2025 + i // 50}-W{i % 50 + 1:02d}", "date": "2026-01-01", "topic": f"t{i}"}
        for i in range(60)
    ]
    _write(p, list(reversed(entries)))
    past = topics.load_past(p)
    assert len(past) == 52
    assert past[0] == "t59"
    assert past == [f"t{i}" for i in range(59, 7, -1)]


def test_record_appends_once_and_keeps_sorted(tmp_path, issue_w44):
    p = tmp_path / "t.json"
    _write(p, [{"issue_id": "2026-W45", "date": "2026-11-09", "topic": "later"}])
    assert topics.record(_with_explainer(issue_w44), p) is True
    assert topics.record(_with_explainer(issue_w44, "other"), p) is False
    d = json.loads(p.read_text(encoding="utf-8"))
    assert [e["issue_id"] for e in d["topics"]] == ["2026-W44", "2026-W45"]
    assert d["topics"][0] == {
        "issue_id": "2026-W44",
        "date": "2026-11-02",
        "topic": "Mixture of Experts",
    }
    assert p.read_text(encoding="utf-8").endswith("}\n")


def test_record_without_explainer_writes_nothing(tmp_path, issue_w44):
    p = tmp_path / "t.json"
    assert topics.record(issue_w44, p) is False
    assert not p.exists()


def test_record_keeps_korean_unescaped(tmp_path, issue_w44):
    p = tmp_path / "t.json"
    topics.record(_with_explainer(issue_w44, "전문가 혼합"), p)
    assert "전문가 혼합" in p.read_text(encoding="utf-8")


# ------------------------------------------------------------ similarity (D-12)


def test_normalize_key_uses_text_before_colon_and_aliases():
    assert topics.normalize_key("Mixture of Experts: 필요한 전문가만") == "moe"
    assert topics.normalize_key("MoE: 다른 설명") == "moe"
    assert topics.normalize_key("Mixture of Experts: 필요한 전문가만") == topics.normalize_key(
        "MoE: 다른 설명"
    )


def test_normalize_key_nfkc_casefold_and_symbols():
    assert topics.normalize_key("Ｌｏｗ-Rank Adaptation：가볍게 고치기") == "lora"
    assert topics.normalize_key("  Graph  RAG! ") == "graphrag"
    assert topics.normalize_key("양자화: 숫자를 줄이기") == "quantization"
    assert topics.normalize_key("Flow Matching") == "flowmatching"


def test_aliases_hold_the_eleven_seed_sets():
    canon = set(topics.ALIASES.values())
    assert canon == {
        "moe", "rag", "cot", "lora", "rlhf", "dpo", "vla", "vlm",
        "diffusion", "distillation", "quantization",
    }  # fmt: skip
    for alias, key in (
        ("mixtureofexperts", "moe"),
        ("retrievalaugmentedgeneration", "rag"),
        ("chainofthought", "cot"),
        ("lowrankadaptation", "lora"),
        ("reinforcementlearningfromhumanfeedback", "rlhf"),
        ("directpreferenceoptimization", "dpo"),
        ("visionlanguageaction", "vla"),
        ("visionlanguagemodel", "vlm"),
        ("diffusionmodel", "diffusion"),
        ("knowledgedistillation", "distillation"),
        ("양자화", "quantization"),
    ):
        assert topics.ALIASES[alias] == key


def test_is_repeat_on_equal_key_or_alias():
    assert topics.is_repeat("MoE: 새 각도", ["Mixture of Experts: 전문가 구조"])
    assert topics.is_repeat("LoRA: 가볍게 고치기", ["주제", "lora"])
    assert not topics.is_repeat("LoRA: 가볍게 고치기", ["RAG: 찾아서 답하기"])
    assert not topics.is_repeat("LoRA", [])


def test_is_repeat_by_containment_needs_four_chars():
    assert topics.is_repeat("Flow Matching Policy: 설명", ["Flow Matching: 설명"])
    assert topics.is_repeat("Speculative Decoding", ["Decoding: 설명"])
    # the shorter key "rag" is 3 chars, so containment does not count
    assert not topics.is_repeat("Graph RAG: 그래프로 찾기", ["RAG: 찾아서 답하기"])
    assert not topics.is_repeat("RAG: 찾아서 답하기", ["Graph RAG: 그래프로 찾기"])


def test_is_repeat_ignores_empty_keys():
    assert not topics.is_repeat("!!!: 설명", ["???"])
