"""Humanizer lint, cleanup and prompt port (HUMN-01, HUMN-02, D-07)."""

import json
import logging

import pytest
from conftest import (
    DEFAULT_TREND,
    FIXTURES,
    FakeAnthropic,
    default_analysis,
    default_explainer,
    default_highlights,
    default_notes,
    default_polish,
    make_parsed,
)

from newsletter.schema import Explainer, Highlight, Issue, PolishFixLLM, PolishLLM
from newsletter.stages import analyze, headline, humanize, notes, trend
from newsletter.store import PROMPTS_DIR


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


# ---- Task 3: every Claude prompt carries the full Korean port (HUMN-01) ----


def _humanizer() -> str:
    return (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8")


def test_humanizer_port_has_version_marker():
    first = _humanizer().splitlines()[0]
    assert first.startswith("<!-- humanizer-version: 2")
    assert "core subset" not in _humanizer()


def test_humanizer_port_names_rule_anchors():
    text = _humanizer()
    for anchor in (
        "단순히",
        "넘어",
        "혁신적",
        "획기적",
        "게임 체인저",
        "전문가들은",
        "되어지",
        "이정표",
        "도움이 되셨으면",
        "해요체",
        "—",
    ):
        assert anchor in text, anchor
    assert sum(1 for line in text.splitlines() if line.startswith("## ")) >= 6


def test_humanizer_port_is_plain_markdown_without_bold():
    assert "**" not in _humanizer()


def test_every_system_prompt_carries_the_port():
    port = _humanizer().strip()
    for prompt in (
        analyze.system_prompt(),
        headline.headline_system_prompt(),
        trend.trend_system_prompt(),
        notes.notes_system_prompt(),
    ):
        assert port in prompt


# ---- 03-06: polish pass (HUMN-03, D-08, D-13) ----

LINE_PATH = "items.1.summary_lines_ko.1"


def _dirty(issue_w44: Issue) -> tuple[Issue, str]:
    line = issue_w44.items[1].summary_lines_ko[1]
    return _with(issue_w44, LINE_PATH, "혁신적인 " + line), line


def _fixes(*pairs: tuple[str, str]):
    return make_parsed(PolishLLM(fixes=[PolishFixLLM(id=i, text=t) for i, t in pairs]))


def _same_outside(a: Issue, b: Issue, allowed: set[str]) -> bool:
    return humanize.unchanged_outside(a.model_dump(mode="json"), b.model_dump(mode="json"), allowed)


def test_polish_clean_issue_makes_no_call(issue_w44):
    fake = FakeAnthropic()
    assert humanize.polish_issue(issue_w44, fake) == issue_w44
    assert fake.calls == []


def test_polish_fixes_only_the_flagged_field(issue_w44):
    issue, line = _dirty(issue_w44)
    fake = FakeAnthropic()
    out = humanize.polish_issue(issue, fake)
    assert len(fake.calls) == 1
    sent = fake.user_texts()[0]
    assert sent.startswith("<fields>") and sent.count("id: ") == 1
    assert f"id: {LINE_PATH}\nkind: 문장\nlimit: 70\nproblems: hype\ntext: 혁신적인 " in sent
    assert out.items[1].summary_lines_ko[1] == line
    assert out == issue_w44


def test_polish_ignores_a_fix_for_an_unrequested_id(issue_w44):
    issue, line = _dirty(issue_w44)
    fake = FakeAnthropic(
        [_fixes((LINE_PATH, line), ("items.0.summary_ko", "다른 요약으로 바꿨어요."))]
    )
    out = humanize.polish_issue(issue, fake)
    assert len(fake.calls) == 1
    assert out.items[0].summary_ko == issue.items[0].summary_ko
    assert out == issue_w44


def test_polish_diff_guard_discards_an_outside_change(issue_w44, monkeypatch, caplog):
    issue, _ = _dirty(issue_w44)
    real = humanize.set_texts

    def leaky(base, texts):
        out = real(base, texts)
        if list(texts) == [LINE_PATH]:  # the fix step also moves a leaf nobody asked about
            out = real(out, {"items.0.summary_ko": "몰래 바뀐 요약이에요."})
        return out

    monkeypatch.setattr(humanize, "set_texts", leaky)
    with caplog.at_level(logging.INFO, logger="newsletter.stages.humanize"):
        out = humanize.polish_issue(issue, FakeAnthropic())
    assert out == issue
    assert _same_outside(out, issue, set())
    assert any("polish=discarded reason=diff" in r.getMessage() for r in caplog.records)
    assert any("humanizer=unfixed fields=1 codes=hype" in r.getMessage() for r in caplog.records)


# ---- 03-06 Task 2: per-fix guards, stage re-checks, retry and leftovers ----

LINE = "multi-view 입력을 써서 영상 내내 대상이 바뀌지 않게 해요."
DIRTY = "혁신적인 " + LINE


def _patch(issue: Issue, updates: dict) -> Issue:
    data = issue.model_dump(mode="json")
    for path, value in updates.items():
        keys = path.split(".")
        node = data
        for k in keys[:-1]:
            node = node[int(k)] if isinstance(node, list) else node[k]
        last = keys[-1]
        node[int(last) if isinstance(node, list) else last] = value
    return Issue.model_validate(data)


def _dirty_base(issue_w44: Issue) -> Issue:
    return _patch(_phase3(issue_w44), {LINE_PATH: DIRTY})


def _value(issue: Issue, path: str):
    node = issue.model_dump(mode="json")
    for k in path.split("."):
        node = node[int(k)] if isinstance(node, list) else node[k]
    return node


def _run_twice_bad(base: Issue, path: str, bad) -> tuple[Issue, FakeAnthropic]:
    """Polish where both attempts return the same rejected fix for path."""
    step = _fixes((path, bad)) if isinstance(bad, str) else bad
    fake = FakeAnthropic([step, step])
    return humanize.polish_issue(base, fake), fake


# (case id, original text, rejected fix text, guard code)
LINE_GUARDS = [
    ("empty", DIRTY, "", "fix_empty"),
    ("over_limit", DIRTY, "가" * 69 + "해요.", "fix_len"),
    ("not_haeyo", DIRTY, "multi-view 입력을 써서 영상 내내 대상이 바뀌지 않게 한다.", "fix_tone"),
    ("url", DIRTY, "https://x.io 처럼 multi-view 입력을 써서 대상이 안 바뀌어요.", "fix_url"),
    ("emoji", DIRTY, "multi-view 입력 🎉 으로 영상 내내 대상이 바뀌지 않게 해요.", "fix_emoji"),
    (
        "authorship",
        DIRTY,
        "이 뉴스레터처럼 multi-view 입력을 써서 대상이 안 바뀌어요.",
        "fix_authorship",
    ),
    ("digit", DIRTY, "multi-view 입력 3개를 써서 영상 내내 대상이 바뀌지 않게 해요.", "fix_digit"),
    (
        "name",
        DIRTY,
        "GPT처럼 multi-view 입력을 써서 영상 내내 대상이 바뀌지 않게 해요.",
        "fix_name",
    ),
    (
        "rank",
        "혁신적인 입력 3개를 써서 영상 내내 대상이 바뀌지 않게 해요.",
        "3위 입력을 써서 영상 내내 대상이 바뀌지 않게 해요.",
        "fix_rank",
    ),
    ("hard_not_lower", DIRTY, "놀라운 multi-view 입력을 써서 대상이 바뀌지 않게 해요.", "fix_lint"),
    (
        "weak_higher",
        DIRTY,
        "다양한 multi-view 입력을 효과적으로 써서 대상이 바뀌지 않게 해요.",
        "fix_weak",
    ),
]


@pytest.mark.parametrize(
    "original,bad,code", [c[1:] for c in LINE_GUARDS], ids=[c[0] for c in LINE_GUARDS]
)
def test_polish_guard_rejects_and_keeps_original(issue_w44, original, bad, code):
    base = _patch(_phase3(issue_w44), {LINE_PATH: original})
    out, fake = _run_twice_bad(base, LINE_PATH, bad)
    assert _value(out, LINE_PATH) == original
    assert out == base
    assert len(fake.calls) == 2
    retry = fake.user_texts()[1]
    assert "<previous_output_problems>" in retry
    assert f"[{code}]" in retry
    if bad:
        assert bad not in retry  # attempt 2 carries problem codes, never the model's text


def test_polish_guard_rejects_a_repeated_id(issue_w44):
    base = _dirty_base(issue_w44)
    out, fake = _run_twice_bad(base, LINE_PATH, _fixes((LINE_PATH, LINE), (LINE_PATH, LINE)))
    assert out == base
    assert "[fix_repeat]" in fake.user_texts()[1]


def _known_verdicts(issue_w44: Issue) -> Issue:
    return _patch(
        _phase3(issue_w44),
        {
            "items.1.commercial.verdict": "가능",
            "items.1.commercial.code_license": {"spdx_id": "MIT", "name": "MIT License"},
            "items.1.commercial.reason_ko": "MIT 라이선스라 혁신적인 조건 없이 쓸 수 있어요.",
            "items.1.claude_gpt.verdict": "기법 적용 가능",
            "items.1.claude_gpt.reason_ko": "혁신적인 질문 방식을 대화에서 따라 해 볼 수 있어요.",
            "items.1.skill_gpt.fit": "Claude Skill",
            "items.1.skill_gpt.reason_ko": "혁신적인 요약 규칙을 Skill로 정리해 두면 좋아요.",
            "trend_ko": "이번 주에는 로봇 연구가 많았어요. 혁신적인 영상 연구도 있었어요.",
            "highlights.0.why_ko": "혁신적인 요약 규칙을 Skill로 정리해 두면 같은 형식으로 받아요.",
            "explainer.point_ko": "혁신적인 필요한 부분만 계산해요.",
        },
    )


STAGE_GUARDS = [
    ("commercial", "items.1.commercial.reason_ko", "MIT 라이선스지만 상업 사용은 불가해요."),
    ("claude_gpt", "items.1.claude_gpt.reason_ko", "기법 적용 가능한 질문 방식이에요."),
    (
        "skill_gpt",
        "items.1.skill_gpt.reason_ko",
        "Skill로 요약 규칙을 정리하면 해당 없음이 줄어요.",
    ),
    ("trend", "trend_ko", "이번 주에는 로봇 연구와 영상 연구가 많았어요."),
    (
        "highlight",
        "highlights.0.why_ko",
        "첫째 요약 규칙을 Skill로 정리해 두면 같은 형식으로 받아요.",
    ),
    ("explainer", "explainer.point_ko", "필요한 부분만 계산해요. 그래서 빨라요."),
]


@pytest.mark.parametrize(
    "path,bad", [c[1:] for c in STAGE_GUARDS], ids=[c[0] for c in STAGE_GUARDS]
)
def test_polish_guard_reruns_the_stage_check(issue_w44, path, bad):
    base = _known_verdicts(issue_w44)
    original = _value(base, path)

    def script(kw):
        good = default_polish(kw)
        return make_parsed(
            PolishLLM(
                fixes=[
                    PolishFixLLM(id=f.id, text=bad if f.id == path else f.text) for f in good.fixes
                ]
            )
        )

    fake = FakeAnthropic([script, script])
    out = humanize.polish_issue(base, fake)
    assert _value(out, path) == original
    assert "[fix_stage]" in fake.user_texts()[1]
    # Every other flagged field was fixed on attempt 1 and is not resent.
    assert fake.user_texts()[1].count("id: ") == 1
    for other, *_ in (s[1:] for s in STAGE_GUARDS):
        if other != path:
            assert "혁신적인" not in _value(out, other)


def test_polish_never_sends_unknown_reason(issue_w44):
    base = _patch(
        _dirty_base(issue_w44),
        {
            "items.0.commercial.reason_ko": notes.UNKNOWN_REASON,
            "items.0.poc.reason_ko": notes.UNKNOWN_REASON,
        },
    )
    fake = FakeAnthropic()
    out = humanize.polish_issue(base, fake)
    assert len(fake.calls) == 1
    assert notes.UNKNOWN_REASON not in fake.user_texts()[0]
    assert out.items[0].commercial.reason_ko == notes.UNKNOWN_REASON
    assert out.items[0].poc.reason_ko == notes.UNKNOWN_REASON


def test_polish_second_attempt_resends_only_failed_ids(issue_w44):
    idea = "items.1.use_idea_ko"
    base = _patch(_dirty_base(issue_w44), {idea: "혁신적인 360도 영상에 쓸 수 있어요."})
    first = _fixes((LINE_PATH, LINE), (idea, "360도 영상 7개에 쓸 수 있어요."))
    fake = FakeAnthropic([first])
    out = humanize.polish_issue(base, fake)
    assert len(fake.calls) == 2
    retry = fake.user_texts()[1]
    assert retry.count("id: ") == 1 and f"id: {idea}\n" in retry
    assert "[fix_digit]" in retry and "7개" not in retry
    assert _value(out, LINE_PATH) == LINE
    assert _value(out, idea) == "360도 영상에 쓸 수 있어요."


def test_polish_makes_at_most_two_calls_and_warns(issue_w44, caplog):
    base = _dirty_base(issue_w44)
    bad = _fixes((LINE_PATH, "놀라운 " + LINE))
    fake = FakeAnthropic([bad, bad, bad])
    with caplog.at_level(logging.INFO, logger="newsletter.stages.humanize"):
        out = humanize.polish_issue(base, fake)
    assert len(fake.calls) == 2
    assert out == base
    msgs = [r.getMessage() for r in caplog.records]
    assert "humanizer=unfixed fields=1 codes=hype" in msgs


def test_polish_api_error_keeps_originals(issue_w44):
    import anthropic
    import httpx

    base = _dirty_base(issue_w44)
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake = FakeAnthropic([anthropic.APIConnectionError(request=req)])
    assert humanize.polish_issue(base, fake) == base
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "step",
    [
        make_parsed(None, stop_reason="refusal"),
        make_parsed(None, stop_reason="max_tokens"),
        ValueError("schema"),
        make_parsed(None),
    ],
    ids=["refusal", "max_tokens", "schema", "no_output"],
)
def test_polish_bad_response_keeps_originals(issue_w44, step):
    base = _dirty_base(issue_w44)
    fake = FakeAnthropic([step, step])
    assert humanize.polish_issue(base, fake) == base
    assert len(fake.calls) == 2


def test_default_fake_texts_are_lint_clean():
    """Pitfall 9: every conftest default is lint-clean, so a normal build makes 0
    polish calls."""
    kw = {"messages": [{"content": "<items>\nrank: 1\nrank: 2\n</items>\ntitle: X"}]}
    a = default_analysis(kw)
    n = default_notes(kw).notes[0]
    h = default_highlights(kw).picks[0]
    ex = default_explainer(kw)
    texts = [
        a.summary_ko, a.does_ko, a.new_ko, a.result_ko, a.use_idea_ko,
        a.claude_gpt_reason_ko, a.skill_gpt_reason_ko,
        n.commercial_reason_ko, n.poc_reason_ko,
        DEFAULT_TREND, h.why_ko, h.how_ko,
        ex.point_ko, ex.body_ko, ex.example_ko,
    ]  # fmt: skip
    for text in texts:
        assert not humanize.needs_polish(humanize.lint(text)), humanize.lint(text)
