"""Verdict reasons: fixed code reason for 확인 필요, one batched Claude call for the
rest, grounding and polarity checks, None on failure (ANLY-04, D-14)."""

import anthropic
import httpx2
import pytest
from conftest import FakeAnthropic, make_parsed

from newsletter.schema import (
    CommercialUse,
    Item,
    LicenseInfo,
    PocReadiness,
    VerdictNoteLLM,
    VerdictNotesLLM,
)
from newsletter.stages import analyze, notes
from newsletter.store import PROMPTS_DIR

MESSAGES_URL = "https://api.anthropic.com/v1/messages"
C_OK = "가중치에 apache-2.0 라이선스가 붙어 있어요."
P_OK = "가중치와 코드, 데모가 모두 공개돼 있어요."


@pytest.fixture(autouse=True)
def _clear_downgrade_registry():
    analyze._FALLBACKS_UNSUPPORTED.clear()
    yield
    analyze._FALLBACKS_UNSUPPORTED.clear()


def _set(it: Item, commercial: str, poc: str, *, code=None, weights=None, flags=(1, 1, 1)) -> Item:
    return it.model_copy(
        update={
            "commercial": CommercialUse(
                verdict=commercial,
                code_license=code,
                weights_license=weights,
            ),
            "poc": PocReadiness(
                verdict=poc,
                has_weights=bool(flags[0]),
                has_code=bool(flags[1]),
                has_demo=bool(flags[2]),
            ),
        }
    )


@pytest.fixture
def items(issue_w44) -> list[Item]:
    return list(issue_w44.items)


@pytest.fixture
def mixed(items) -> list[Item]:
    """rank 1 가능/바로 가능 (apache weights), rank 2 조건부/코드만 (MIT code),
    rank 3 확인 필요/논문만, the rest 확인 필요 on both sides."""
    out = list(items)
    out[0] = _set(out[0], "가능", "바로 가능", weights=LicenseInfo(spdx_id="apache-2.0"))
    out[1] = _set(
        out[1],
        "조건부",
        "코드만",
        code=LicenseInfo(spdx_id="MIT", name="MIT License"),
        flags=(0, 1, 0),
    )
    out[2] = _set(out[2], "확인 필요", "논문만", flags=(0, 0, 0))
    return out


def note(rank: int, c: str = C_OK, p: str = P_OK) -> VerdictNoteLLM:
    return VerdictNoteLLM(rank=rank, commercial_reason_ko=c, poc_reason_ko=p)


def resp(*ns: VerdictNoteLLM):
    return make_parsed(VerdictNotesLLM(notes=list(ns)))


def _codes(n: VerdictNoteLLM, it: Item) -> set[str]:
    return {code for code, _ in notes.check_note(n, it)}


# ---------------------------------------------------------------- routing


def test_all_unknown_makes_no_call(items):
    fake = FakeAnthropic()
    out = notes.write_notes(items, fake)
    assert fake.calls == []
    for it in out:
        assert it.commercial.reason_ko == notes.UNKNOWN_REASON
        assert it.poc.reason_ko == notes.UNKNOWN_REASON
        assert it.commercial.verdict == "확인 필요" and it.poc.verdict == "확인 필요"


def test_mixed_sends_one_call_with_known_items_only(mixed):
    fake = FakeAnthropic()
    out = notes.write_notes(mixed, fake)
    assert len(fake.calls) == 1
    kw = fake.calls[0]["kw"]
    assert kw["output_format"] is VerdictNotesLLM
    humanizer = (PROMPTS_DIR / "humanizer_ko.md").read_text(encoding="utf-8").strip()
    assert kw["system"][0]["text"].endswith(humanizer)
    user = fake.user_texts()[0]
    assert user.startswith("<items>") and "http" not in user
    assert user.count("rank: ") == 3
    for key in (
        "commercial: 가능",
        "weights_license: apache-2.0",
        "code_license: 없음",
        "poc: 바로 가능",
        "code_license: MIT / MIT License",
        "poc: 코드만",
        "has_weights: no",
        "has_code: yes",
        "has_demo: no",
        "commercial: 확인 필요",
        "poc: 논문만",
    ):
        assert key in user
    assert "rank: 4" not in user
    # default fake notes are grounded and neutral
    assert out[0].commercial.reason_ko == "공개된 라이선스 정보를 근거로 판단했어요."
    assert out[0].poc.reason_ko == "공개된 자료 범위를 근거로 판단했어요."
    # rank 3: commercial unknown keeps the code reason, PoC gets Claude's
    assert out[2].commercial.reason_ko == notes.UNKNOWN_REASON
    assert out[2].poc.reason_ko == "공개된 자료 범위를 근거로 판단했어요."
    assert out[3].commercial.reason_ko == notes.UNKNOWN_REASON


def test_verdicts_are_never_changed(mixed):
    out = notes.write_notes(mixed, FakeAnthropic())
    for before, after in zip(mixed, out, strict=True):
        assert after.commercial.model_dump(exclude={"reason_ko"}) == before.commercial.model_dump(
            exclude={"reason_ko"}
        )
        assert after.poc.model_dump(exclude={"reason_ko"}) == before.poc.model_dump(
            exclude={"reason_ko"}
        )


def test_prompt_version_and_rules():
    text = (PROMPTS_DIR / "verdict_notes.md").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "<!-- prompt-version: 1 -->"
    assert "판정은 코드가 정했어요. 판정을 다시 쓰지 말고 근거만 써요" in text
    assert "<items>" in text and "60자" in text


# ---------------------------------------------------------------- check_note


def test_check_good_notes_pass(mixed):
    assert notes.check_note(note(1), mixed[0]) == []
    n2 = note(2, "코드에 MIT 라이선스가 붙어 있어요.", "코드만 공개돼 있어요.")
    assert notes.check_note(n2, mixed[1]) == []


def test_check_length_tone_url_hype(mixed):
    it = mixed[0]
    assert "note_len" in _codes(note(1, "가" * 60 + "요."), it)
    assert "note_tone" in _codes(note(1, "가중치 라이선스가 있다."), it)
    assert "note_url" in _codes(note(1, "https://x.y 에 있어요."), it)
    assert "note_hype" in _codes(note(1, p="혁신적인 데모가 있어요."), it)


def test_check_ungrounded_license(mixed):
    assert "note_ungrounded" in _codes(note(1, "MIT 라이선스라서 쓸 수 있어요."), mixed[0])
    assert "note_ungrounded" in _codes(note(1, "비상업 조건이 붙어 있어요."), mixed[0])
    assert "note_ungrounded" not in _codes(note(1, "Apache 라이선스가 붙어 있어요."), mixed[0])
    # GPL does not match inside LGPL, and the input's MIT grounds rank 2
    lg = mixed[1].model_copy(
        update={
            "commercial": mixed[1].commercial.model_copy(
                update={"code_license": LicenseInfo(spdx_id="LGPL-3.0")}
            )
        }
    )
    assert "note_ungrounded" not in _codes(
        note(2, "LGPL-3.0 조건을 따라야 해요.", "코드만 있어요."), lg
    )


@pytest.mark.parametrize(
    ("commercial", "poc", "c_text", "p_text"),
    [
        ("가능", "바로 가능", "상업적으로 쓸 수 없어요.", P_OK),
        ("불가", "바로 가능", "상업적으로 쓸 수 있어요.", P_OK),
        ("조건부", "바로 가능", "자유롭게 쓸 수 있는 라이선스예요.", P_OK),
        ("확인 필요", "논문만", C_OK, "데모가 공개돼 있어요."),
        ("가능", "코드만", C_OK, "바로 써 볼 수 있어요."),
    ],
)
def test_check_polarity(items, commercial, poc, c_text, p_text):
    it = _set(items[0], commercial, poc, weights=LicenseInfo(spdx_id="apache-2.0"))
    assert "note_polarity" in _codes(note(1, c_text, p_text), it)


def test_check_unknown_field_is_not_checked(mixed):
    # rank 3 commercial is 확인 필요, so its commercial text is ignored
    assert notes.check_note(note(3, "MIT 라이선스예요", "논문만 공개돼 있어요."), mixed[2]) == []


def test_check_messages_never_carry_model_text(mixed):
    bad = note(1, "MIT 라이선스라 쓸 수 없다 https://x.y 혁신적", "가" * 70)
    for _, msg in notes.check_note(bad, mixed[0]):
        assert "MIT" not in msg and "혁신적" not in msg and "x.y" not in msg


# ---------------------------------------------------------------- retry / fallback


def test_wrong_ranks_retry(mixed):
    fake = FakeAnthropic([resp(note(1), note(1), note(3))])
    out = notes.write_notes(mixed, fake)
    assert len(fake.calls) == 2
    assert "note_ranks" not in fake.user_texts()[0]
    retry = fake.user_texts()[1]
    assert "<previous_output_problems>" in retry and "rank" in retry
    assert out[1].commercial.reason_ko == "공개된 라이선스 정보를 근거로 판단했어요."


def test_missing_rank_retry_then_still_missing_is_none(mixed):
    fake = FakeAnthropic(
        [resp(note(1), note(3)), resp(note(1), note(3, p="논문만 공개돼 있어요."))]
    )
    out = notes.write_notes(mixed, fake)
    assert len(fake.calls) == 2
    assert out[0].commercial.reason_ko == C_OK
    assert out[1].commercial.reason_ko is None and out[1].poc.reason_ko is None
    assert out[2].poc.reason_ko == "논문만 공개돼 있어요."


def test_after_second_attempt_passing_kept_failing_none(mixed, caplog):
    bad = note(2, "MIT라서 제한 없이 쓸 수 있어요.", "코드만 공개돼 있어요.")
    fake = FakeAnthropic(
        [
            resp(note(1), bad, note(3, p="논문만 있어요.")),
            resp(note(1), bad, note(3, p="논문만 있어요.")),
        ]
    )
    with caplog.at_level("DEBUG", logger="newsletter"):
        out = notes.write_notes(mixed, fake)
    assert len(fake.calls) == 2
    assert "rank 2 commercial_reason_ko" in fake.user_texts()[1]
    assert out[0].commercial.reason_ko == C_OK and out[0].poc.reason_ko == P_OK
    assert out[1].commercial.reason_ko is None
    assert out[1].poc.reason_ko == "코드만 공개돼 있어요."
    assert out[1].commercial.verdict == "조건부"
    assert "note_polarity" in caplog.text and "제한 없이" not in caplog.text
    assert "MIT" not in caplog.text


def test_api_error_sets_none_for_claude_targets(mixed):
    req = httpx2.Request("POST", MESSAGES_URL)
    fake = FakeAnthropic([anthropic.APIConnectionError(request=req)])
    out = notes.write_notes(mixed, fake)
    assert len(fake.calls) == 1
    assert out[0].commercial.reason_ko is None and out[0].poc.reason_ko is None
    assert out[2].commercial.reason_ko == notes.UNKNOWN_REASON
    assert out[2].poc.reason_ko is None
    assert out[5].poc.reason_ko == notes.UNKNOWN_REASON
    assert [it.commercial.verdict for it in out] == [it.commercial.verdict for it in mixed]


def test_refusal_and_schema_error_give_none(mixed):
    try:
        VerdictNotesLLM.model_validate({"notes": [{"rank": "x"}]})
    except ValueError as e:
        err = e
    fake = FakeAnthropic([err, make_parsed(None, stop_reason="refusal")])
    out = notes.write_notes(mixed, fake)
    assert len(fake.calls) == 2
    assert out[0].commercial.reason_ko is None
    assert out[3].poc.reason_ko == notes.UNKNOWN_REASON
