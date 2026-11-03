"""Humanizer lint, cleanup and prompt port (HUMN-01, HUMN-02, D-07)."""

import logging

from newsletter.schema import Explainer, Highlight, Issue
from newsletter.stages import humanize, notes


def _with(issue: Issue, path: str, text: str) -> Issue:
    data = issue.model_dump(mode="json")
    keys = path.split(".")
    node = data
    for k in keys[:-1]:
        node = node[int(k)] if isinstance(node, list) else node[k]
    last = keys[-1]
    if isinstance(node, list):
        node[int(last)] = text
    else:
        node[last] = text
    return Issue.model_validate(data)


def _phase3(issue: Issue) -> Issue:
    return issue.model_copy(
        update={
            "highlights": [
                Highlight(
                    rank=2,
                    tag="Claude Skill",
                    why_ko="요약 규칙을 Skill로 정리해 두면 같은 형식으로 받을 수 있어요.",
                    how_ko="논문 요약 지시문과 예시 두 개를 Skill 파일에 넣어요.",
                )
            ],
            "explainer": Explainer(
                topic="Mixture of Experts",
                body_ko="입력마다 일부 전문가 층만 골라 계산해요.",
                related_ranks=[1],
                point_ko="필요한 부분만 계산해요.",
                example_ko="질문에 맞는 담당자에게만 전화를 돌리는 것과 같아요.",
            ),
        }
    )


# ---- Task 1: field collection and issue lint ----


def test_w44_fixture_lints_clean(issue_w44):
    assert humanize.lint_issue(issue_w44) == {}


def test_injected_tells_flag_exactly_their_paths(issue_w44):
    line = issue_w44.items[1].summary_lines_ko[1]
    issue = _with(issue_w44, "items.1.summary_lines_ko.1", "혁신적인 " + line)
    issue = _with(issue, "trend_ko", "이번 주는 로봇 모델이 많았어요 — 영상 모델도 있었어요.")
    assert humanize.lint_issue(issue) == {
        "items.1.summary_lines_ko.1": ["hype"],
        "trend_ko": ["dash"],
    }


def test_phase3_slots_are_collected(issue_w44):
    paths = {f.path: f.kind for f in humanize.collect_fields(_phase3(issue_w44))}
    assert {p: k for p, k in paths.items() if p.startswith(("highlights", "explainer"))} == {
        "highlights.0.why_ko": "sentence",
        "highlights.0.how_ko": "sentence",
        "explainer.topic": "name",
        "explainer.point_ko": "sentence",
        "explainer.body_ko": "sentence",
        "explainer.example_ko": "sentence",
    }


def test_field_order_kinds_and_limits(issue_w44):
    refs = humanize.collect_fields(issue_w44)
    first = [(f.path, f.kind, f.limit) for f in refs[:8]]
    assert first == [
        ("items.0.title_ko", "name", None),
        ("items.0.summary_ko", "sentence", 80),
        ("items.0.summary_lines_ko.0", "sentence", 70),
        ("items.0.summary_lines_ko.1", "sentence", 70),
        ("items.0.summary_lines_ko.2", "sentence", 70),
        ("items.0.use_idea_ko", "sentence", 50),
        ("items.0.model_info.kind_ko", "name", 30),
        ("items.0.model_info.architecture_ko", "name", 60),
    ]
    dump = issue_w44.model_dump(mode="json")
    for f in refs:
        node = dump
        for k in f.path.split("."):
            node = node[int(k)] if isinstance(node, list) else node[k]
        assert node == f.text, f.path


def test_unknown_reason_is_not_collected(issue_w44):
    issue = _with(issue_w44, "items.0.commercial.reason_ko", notes.UNKNOWN_REASON)
    issue = _with(issue, "items.0.poc.reason_ko", "코드와 가중치가 모두 공개돼 있어요.")
    paths = [f.path for f in humanize.collect_fields(issue)]
    assert "items.0.commercial.reason_ko" not in paths
    assert "items.0.poc.reason_ko" in paths


def test_headline_and_code_fields_are_never_collected(issue_w44):
    issue = _with(issue_w44, "headline_ko", "혁신적인 — 헤드라인")
    paths = [f.path for f in humanize.collect_fields(_phase3(issue))]
    assert "headline_ko" not in paths
    assert humanize.lint_issue(issue) == {}
    for bad in ("url", "rank", "verdict", "image", "ai_type", "upvotes", "title_en", "tag"):
        assert not any(p.split(".")[-1].startswith(bad) for p in paths), bad


def test_lint_log_line_carries_counts_and_codes_only(issue_w44, caplog):
    secret = "혁신적인 비밀문장이에요."
    issue = _with(issue_w44, "items.0.use_idea_ko", secret)
    with caplog.at_level(logging.INFO, logger="newsletter.stages.humanize"):
        flagged = humanize.lint_issue(issue)
    assert flagged == {"items.0.use_idea_ko": ["hype"]}
    lines = [r.getMessage() for r in caplog.records]
    assert any(line.startswith("humanizer=lint fields=") for line in lines)
    assert any("flagged=1 codes=hype" in line for line in lines)
    assert not any("비밀" in line or "items.0" in line for line in lines)


def test_needs_polish_scoring():
    assert humanize.needs_polish(["dash"])
    assert not humanize.needs_polish([])
