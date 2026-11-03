"""Humanizer lint, cleanup and prompt port (HUMN-01, HUMN-02, D-07)."""

import json
import logging

import pytest
from conftest import FIXTURES

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


# ---- Task 2: the full banned-pattern list (research §1) ----

# (text, code that must appear, "flag" or "weak-only")
POSITIVES = [
    # hard codes: one hit flags
    ("로봇이 움직여요 — 손도 써요.", "dash", "flag"),
    ("로봇이 움직여요 -- 손도 써요.", "dash", "flag"),
    ("**핵심** 로봇이 움직여요.", "markdown", "flag"),
    ("혁신적인 방식으로 로봇을 움직여요.", "hype", "flag"),
    ("게임 체인저가 될 모델이에요.", "hype", "flag"),
    ("단순한 요약 모델이 아니라 추론까지 해요.", "not_x_but_y", "flag"),
    ("글뿐만 아니라 영상도 만들어요.", "not_x_but_y", "flag"),
    ("텍스트를 넘어 영상까지 다뤄요.", "beyond", "flag"),
    ("멀티모달 연구에 새 기준을 세웠어요.", "significance", "flag"),
    ("도움이 되셨으면 좋겠어요.", "chatbot", "flag"),
    ("전문가들은 이 방식을 높이 평가해요.", "authority", "flag"),
    ("결론부터 말하면 속도가 두 배예요.", "run_up", "flag"),
    ("새 데이터셋으로 학습되어졌어요.", "double_passive", "flag"),
    ("🤖 로봇이 물체를 집어요.", "emoji", "flag"),
    ("로봇 팔이 물체를 집는다.", "haeyo", "flag"),
    # weak codes: two hits in one field flag
    ("사람이 아니라 로봇이 움직이고, 글이 아니라 영상이 나와요.", "not_x_plain", "flag"),
    ("본질적으로 이 방식은 진정한 범용 모델을 노려요.", "saying", "flag"),
    ("이 모듈이 검색 역할을 해요. 업계 표준으로 자리매김했어요.", "role_verb", "flag"),
    ("정확도를 보여 주며 속도를 강조해요.", "rider", "flag"),
    ("다양한 데이터로 성능을 극대화해요.", "ai_words", "flag"),
    ("글, 그림, 소리를 넣고 표, 차트, 코드를 받아요.", "triad", "flag"),
    ("어쩌면 더 빨라질 수도 있을 것 같아요.", "hedge_stack", "flag"),
    ("이 모델은 다양한 문서를 읽어요.", "subject_repeat", "flag"),
    ("다양한 문서를 한 번에 읽어요. 표 안의 숫자도 뽑아요. 이게 핵심이에요.", "closer", "flag"),
    ("모델이 글을 읽어요. 모델이 표를 읽어요. 모델이 답을 써요.", "same_opening", "flag"),
    # a lone weak hit is reported but does not flag
    ("긴 문서를 한 번에 읽어요. 표 안의 숫자도 뽑아요. 이게 핵심이에요.", "closer", "weak-only"),
    ("사람이 아니라 로봇이 직접 물체를 옮겨요.", "not_x_plain", "weak-only"),
]


@pytest.mark.parametrize(("text", "code", "expect"), POSITIVES)
def test_lint_positive(text, code, expect):
    codes = humanize.lint(text)
    assert code in codes, codes
    if code in humanize.HARD_CODES:
        assert expect == "flag"
    else:
        assert code in humanize.WEAK_CODES
        assert not any(c in humanize.HARD_CODES for c in codes), codes
    assert humanize.needs_polish(codes) is (expect == "flag"), codes


def test_every_code_has_a_positive_case():
    covered = {code for _, code, _ in POSITIVES}
    assert covered == set(humanize.HARD_CODES) | set(humanize.WEAK_CODES)
    assert len(humanize.HARD_CODES) == 12
    assert len(humanize.WEAK_CODES) == 10


def _fixture_sentences() -> list[str]:
    data = json.loads((FIXTURES / "issue_w44.json").read_text(encoding="utf-8"))
    issue = Issue.model_validate(data)
    return [f.text for f in humanize.collect_fields(issue) if f.kind == "sentence"]


NEGATIVES = [
    *_fixture_sentences(),
    "기존 기록을 넘어섰어요.",
    "100자를 넘어가면 잘라요.",
    "사람이 아니라 로봇이 직접 움직여요.",
    "Vision-Language-Action 모델이에요.",
    "역량, 최적화, 평가 방법을 함께 다뤄요.",
    "GPT-5와 Qwen3-VL을 비교했어요.",
]


@pytest.mark.parametrize("text", NEGATIVES)
def test_lint_negative(text):
    codes = humanize.lint(text)
    assert not humanize.needs_polish(codes), codes


def test_negative_set_is_large_enough():
    assert len(NEGATIVES) >= 20


def test_emoji_and_haeyo_apply_to_sentences_only():
    assert "emoji" in humanize.lint("🤖 로봇 모델이에요.")
    assert "emoji" not in humanize.lint("🤖 로봇 모델", kind="name")
    assert "haeyo" in humanize.lint("VLM backbone에 dynamics 표현 모듈 결합")
    assert humanize.lint("VLM backbone에 dynamics 표현 모듈 결합", kind="name") == []
    assert "hype" in humanize.lint("혁신적 구조", kind="name")


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("**핵심** 로봇이 움직여요.", "핵심 로봇이 움직여요."),
        ("__굵게__ 써요.", "굵게 써요."),
        ("`code` 블록이에요.", "code 블록이에요."),
        ("# 제목이에요.", "제목이에요."),
        ("- 목록이에요.", "목록이에요."),
        ("“곧은” ‘따옴표’예요.", "\"곧은\" '따옴표'예요."),
        ("줄이\n바뀌고\t탭도  있어요.", "줄이 바뀌고 탭도 있어요."),
        ("Vision-Language-Action 모델이에요.", "Vision-Language-Action 모델이에요."),
    ],
)
def test_cleanup(raw, clean):
    assert humanize.cleanup(raw) == clean
    assert humanize.cleanup(clean) == clean


@pytest.mark.parametrize(
    ("raw", "fixed"),
    [
        ("로봇이 움직여요 — 손도 써요.", "로봇이 움직여요, 손도 써요."),
        ("로봇이 움직여요–손도 써요.", "로봇이 움직여요, 손도 써요."),
        ("로봇이 움직여요 -- 손도 써요.", "로봇이 움직여요, 손도 써요."),
        ("GPT-5와 Qwen3-VL을 비교했어요.", "GPT-5와 Qwen3-VL을 비교했어요."),
        ("Vision-Language-Action 모델이에요.", "Vision-Language-Action 모델이에요."),
    ],
)
def test_dash_fallback(raw, fixed):
    assert humanize.dash_fallback(raw) == fixed
    assert "dash" not in humanize.lint(humanize.dash_fallback(raw))
