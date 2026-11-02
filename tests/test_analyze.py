"""Claude stage: retry-once, fallback downgrade, field checks (ANLY-01/03/06, D-15, D-19)."""

import json

import anthropic
import httpx2
import pytest
import respx
from conftest import FakeAnthropic, default_analysis, make_parsed, mock_hf_week

from newsletter.errors import AnalysisInvalid
from newsletter.schema import HfEntry, ItemAnalysisLLM
from newsletter.stages import analyze

ISSUE_ID = "2026-W44"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"


@pytest.fixture(autouse=True)
def _clear_downgrade_registry():
    analyze._FALLBACKS_UNSUPPORTED.clear()
    yield
    analyze._FALLBACKS_UNSUPPORTED.clear()


def ok(kw):
    return make_parsed(default_analysis(kw))


def refusal(kw=None):
    return make_parsed(None, stop_reason="refusal")


def _build(hf_pages, fake):
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True) as router:
        mock_hf_week(router, hf_pages, ISSUE_ID)
        return run_build(ISSUE_ID, claude_client=fake)


def _bad_request() -> anthropic.BadRequestError:
    req = httpx2.Request("POST", MESSAGES_URL)
    resp = httpx2.Response(400, request=req)
    return anthropic.BadRequestError("fallbacks not supported", response=resp, body=None)


def _entry(hf_pages, paper_id=None) -> HfEntry:
    raw = [d for page in hf_pages for d in page]
    if paper_id:
        raw = [d for d in raw if d["paper"]["id"] == paper_id]
    return HfEntry.model_validate(raw[0])


# ------------------------------------------------------------ retry / D-15


def test_refusal_is_retried_once_and_week_builds(hf_pages, archive_tmp):
    fake = FakeAnthropic([ok, ok, refusal, ok])
    issue = _build(hf_pages, fake)

    assert len(issue.items) == 10
    assert len(fake.calls) == 12  # 11 analysis calls + 1 headline call
    assert all(c["ns"] == "beta" for c in fake.calls)
    texts = fake.user_texts()
    assert "previous_output_problems" not in texts[2]
    assert "previous_output_problems" in texts[3]
    assert "refusal" in texts[3]
    assert (archive_tmp / "archive" / ISSUE_ID / "issue.json").is_file()


def test_paper_invalid_twice_stops_the_build(hf_pages, archive_tmp):
    fake = FakeAnthropic([ok, ok, ok, ok, refusal, make_parsed(None)])
    with pytest.raises(AnalysisInvalid) as exc:
        _build(hf_pages, fake)

    assert str(exc.value).startswith("rank=5 reason=")
    assert len(fake.calls) == 6  # the build stops before the headline call
    week = archive_tmp / "archive" / ISSUE_ID
    assert not (week / "issue.json").exists()
    assert not (week / "email.html").exists()


def test_max_tokens_and_schema_error_use_the_retry(hf_pages):
    entry = _entry(hf_pages)
    fake = FakeAnthropic([make_parsed(None, stop_reason="max_tokens"), ok])
    assert isinstance(analyze.analyze_one(fake, entry, rank=1), ItemAnalysisLLM)

    try:
        ItemAnalysisLLM.model_validate({"title_ko": "x"})
    except ValueError as e:
        schema_error = e
    fake = FakeAnthropic([schema_error, ok])
    assert isinstance(analyze.analyze_one(fake, entry, rank=1), ItemAnalysisLLM)
    assert "previous_output_problems" in fake.user_texts()[1]


def test_bad_request_downgrades_to_plain_parse(hf_pages, archive_tmp):
    fake = FakeAnthropic([_bad_request()])
    issue = _build(hf_pages, fake)

    assert len(issue.items) == 10
    # 10 analysis calls + 1 headline call; the downgrade covers the headline too.
    assert [c["ns"] for c in fake.calls] == ["beta"] + ["messages"] * 11
    for c in fake.calls[1:]:
        assert "fallbacks" not in c["kw"] and "betas" not in c["kw"]
    assert "previous_output_problems" not in fake.user_texts()[1]


def test_sdk_type_error_downgrades_to_plain_parse(hf_pages, archive_tmp):
    fake = FakeAnthropic([TypeError("unexpected keyword argument 'fallbacks'")])
    issue = _build(hf_pages, fake)

    assert len(issue.items) == 10
    # 10 analysis calls + 1 headline call; the downgrade covers the headline too.
    assert [c["ns"] for c in fake.calls] == ["beta"] + ["messages"] * 11


def test_downgrade_is_per_client(hf_pages):
    entry = _entry(hf_pages)
    first = FakeAnthropic([_bad_request()])
    analyze.analyze_one(first, entry, rank=1)
    second = FakeAnthropic()
    analyze.analyze_one(second, entry, rank=1)
    assert [c["ns"] for c in second.calls] == ["beta"]


def test_logs_carry_no_paper_or_output_text(hf_pages, caplog):
    entry = _entry(hf_pages)
    fake = FakeAnthropic([refusal, ok])
    with caplog.at_level("DEBUG", logger="newsletter"):
        result = analyze.analyze_one(fake, entry, rank=4)
    text = caplog.text
    assert "rank=4 attempt=1 stop_reason=refusal" in text
    assert "input_tokens=100" in text
    assert entry.paper.title not in text
    assert result.title_ko not in text


# ------------------------------------------------------ real SDK contract


def _message_body(analysis: dict) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": [{"type": "text", "text": json.dumps(analysis, ensure_ascii=False)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 7},
    }


VALID = {
    "title_ko": "Qwen3-VL: long-context 멀티모달 추론 개선",
    "ai_type": "멀티모달",
    "summary_ko": "긴 영상과 문서를 함께 읽는 멀티모달 모델을 공개했다.",
    "does_ko": "긴 영상과 문서를 함께 읽고 답한다.",
    "new_ko": "long-context 처리 방식을 바꿔 더 긴 입력을 다룬다.",
    "result_ko": "공개 benchmark에서 기존 공개 모델보다 높은 점수를 보고했다.",
    "kind_ko": "Vision-Language 모델",
    "architecture_ko": "확인 필요",
}


def _real_client(handler) -> tuple[anthropic.Anthropic, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request, len(seen))

    http = httpx2.Client(transport=httpx2.MockTransport(record))
    client = anthropic.Anthropic(api_key="test-key", max_retries=0, http_client=http)
    return client, seen


def test_real_sdk_sends_fallbacks_and_parses(hf_pages):
    """respx cannot see anthropic 2.3 traffic (it uses httpx2), so a MockTransport stands in."""
    client, seen = _real_client(lambda req, n: httpx2.Response(200, json=_message_body(VALID)))
    result = analyze.analyze_one(client, _entry(hf_pages), rank=1)

    assert ItemAnalysisLLM.model_validate(result.model_dump()) == ItemAnalysisLLM(**VALID)
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url).startswith(MESSAGES_URL)
    assert "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]
    body = json.loads(req.content)
    assert body["fallbacks"] == "default"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "schema" in body["output_config"]["format"]


def test_real_sdk_400_downgrades_without_fallbacks(hf_pages):
    def handler(req, n):
        if n == 1:
            return httpx2.Response(
                400,
                json={
                    "type": "error",
                    "error": {"type": "invalid_request_error", "message": "fallbacks"},
                },
            )
        return httpx2.Response(200, json=_message_body(VALID))

    client, seen = _real_client(handler)
    result = analyze.analyze_one(client, _entry(hf_pages), rank=1)

    assert result.title_ko == VALID["title_ko"]
    assert len(seen) == 2
    second = seen[1]
    assert "server-side-fallback" not in second.headers.get("anthropic-beta", "")
    assert "fallbacks" not in json.loads(second.content)
    assert analyze._fallbacks_supported(client) is False


# ------------------------------------------------- field checks / D-19 trim


def _analysis(**over) -> ItemAnalysisLLM:
    base = dict(VALID)
    base.update(over)
    return ItemAnalysisLLM(**base)


def _parsed(**over):
    return make_parsed(_analysis(**over))


LONG_SUMMARY = (
    "이 논문은 긴 영상과 문서를 함께 읽는 멀티모달 모델을 공개했고, "
    "여러 벤치마크에서 기존 공개 모델보다 높은 점수를 기록했으며 학습 데이터 구성도 함께 설명했다."
)


def test_long_summary_fixture_exceeds_limit():
    assert len(LONG_SUMMARY) > 80


@pytest.mark.parametrize(
    ("over", "codes"),
    [
        ({}, []),
        ({"title_ko": "   "}, ["title_empty"]),
        ({"summary_ko": LONG_SUMMARY}, ["summary_len"]),
        ({"does_ko": "가" * 71}, ["line_len"]),
        ({"new_ko": "가" * 71}, ["line_len"]),
        ({"result_ko": "가" * 71}, ["line_len"]),
        ({"does_ko": " "}, ["line_empty"]),
        ({"result_ko": ""}, ["line_empty"]),
        ({"kind_ko": "가" * 31}, ["kind_len"]),
        ({"kind_ko": " "}, ["kind_empty"]),
        ({"architecture_ko": "가" * 61}, ["arch_len"]),
    ],
)
def test_check_codes(over, codes):
    assert [code for code, _ in analyze.check(_analysis(**over))] == codes


def test_summary_exactly_80_chars_passes():
    assert analyze.check(_analysis(summary_ko="가" * 80)) == []
    assert [c for c, _ in analyze.check(_analysis(summary_ko="가" * 81))] == ["summary_len"]


def test_new_fields_exactly_at_limit_pass():
    at_limit = {
        "does_ko": "가" * 70,
        "new_ko": "가" * 70,
        "result_ko": "가" * 70,
        "kind_ko": "가" * 30,
        "architecture_ko": "가" * 60,
    }
    assert analyze.LINE_LIMIT == 70
    assert analyze.KIND_LIMIT == 30
    assert analyze.ARCH_LIMIT == 60
    assert analyze.check(_analysis(**at_limit)) == []


def test_check_messages_name_field_and_count_only():
    text = "모델 본문 " * 20
    msgs = [m for _, m in analyze.check(_analysis(new_ko=text))]
    assert len(msgs) == 1
    assert "new_ko" in msgs[0] and str(len(text)) in msgs[0] and "70" in msgs[0]
    assert "모델 본문" not in msgs[0]


def test_line_only_overrun_is_trimmed_after_retry(hf_pages, caplog):
    long_line = "긴 영상과 문서를 함께 읽고 답하는 모델이다. " * 4
    over = {"does_ko": long_line, "architecture_ko": "가" * 65}
    fake = FakeAnthropic([_parsed(**over), _parsed(**over)])
    with caplog.at_level("INFO", logger="newsletter"):
        result = analyze.analyze_one(fake, _entry(hf_pages), rank=4)

    assert len(fake.calls) == 2
    assert "does_ko" in fake.user_texts()[1]
    assert len(result.does_ko) <= 70 and result.does_ko.endswith("…")
    assert len(result.architecture_ko) <= 60 and result.architecture_ko.endswith("…")
    assert result.new_ko == VALID["new_ko"]
    assert "trimmed=does_ko,architecture_ko rank=4" in caplog.text
    assert long_line.strip() not in caplog.text


def test_line_overrun_with_empty_kind_fails(hf_pages):
    bad = {"result_ko": "가" * 80, "kind_ko": " "}
    fake = FakeAnthropic([_parsed(**bad), _parsed(**bad)])
    with pytest.raises(AnalysisInvalid) as exc:
        analyze.analyze_one(fake, _entry(hf_pages), rank=5)
    assert "line_len" in str(exc.value) and "kind_empty" in str(exc.value)


def test_summary_only_overrun_is_trimmed_after_retry(hf_pages, caplog):
    fake = FakeAnthropic([_parsed(summary_ko=LONG_SUMMARY), _parsed(summary_ko=LONG_SUMMARY)])
    with caplog.at_level("INFO", logger="newsletter"):
        result = analyze.analyze_one(fake, _entry(hf_pages), rank=6)

    assert len(fake.calls) == 2
    assert "previous_output_problems" in fake.user_texts()[1]
    assert len(result.summary_ko) <= 80
    assert result.summary_ko.endswith("…")
    body = result.summary_ko[:-1]
    assert LONG_SUMMARY.startswith(body)
    assert LONG_SUMMARY[len(body)] in " ,." or LONG_SUMMARY[len(body) - 1] in ",."
    assert "trimmed=summary_ko rank=6" in caplog.text
    assert LONG_SUMMARY not in caplog.text


def test_summary_overrun_with_other_error_fails(hf_pages):
    bad = {"summary_ko": LONG_SUMMARY, "title_ko": " "}
    fake = FakeAnthropic([_parsed(**bad), _parsed(**bad)])
    with pytest.raises(AnalysisInvalid) as exc:
        analyze.analyze_one(fake, _entry(hf_pages), rank=2)
    assert "summary_len" in str(exc.value) and "title_empty" in str(exc.value)


def test_empty_title_then_valid_returns_second(hf_pages):
    fake = FakeAnthropic([_parsed(title_ko=" "), _parsed()])
    result = analyze.analyze_one(fake, _entry(hf_pages), rank=1)
    assert len(fake.calls) == 2
    assert result.title_ko == VALID["title_ko"]
    assert "title_ko" in fake.user_texts()[1]


def test_unknown_ai_type_goes_through_retry(hf_pages):
    with pytest.raises(ValueError):
        ItemAnalysisLLM(**{**VALID, "ai_type": "로보틱스"})
    try:
        ItemAnalysisLLM.model_validate({**VALID, "ai_type": "로보틱스"})
    except ValueError as e:
        err = e
    fake = FakeAnthropic([err, ok])
    analyze.analyze_one(fake, _entry(hf_pages), rank=1)
    assert len(fake.calls) == 2


def test_free_text_newlines_are_normalized(hf_pages):
    fake = FakeAnthropic(
        [
            _parsed(
                title_ko="Qwen3-VL:\r\nlong-context 개선",
                summary_ko="첫 줄\n둘째 줄\t끝.",
                does_ko="긴 영상을\r\n읽는다.",
                new_ko="입력\t처리를 바꾼다.",
                result_ko="점수가\n올랐다.",
            )
        ]
    )
    result = analyze.analyze_one(fake, _entry(hf_pages), rank=1)
    assert result.title_ko == "Qwen3-VL: long-context 개선"
    assert result.summary_ko == "첫 줄 둘째 줄 끝."
    assert result.does_ko == "긴 영상을 읽는다."
    assert result.new_ko == "입력 처리를 바꾼다."
    assert result.result_ko == "점수가 올랐다."


@pytest.mark.parametrize(
    "text",
    [
        LONG_SUMMARY,
        "가" * 120,
        "모델을 공개했다. " * 12,
        "a,b," * 40,
    ],
)
def test_trim_summary_limits(text):
    out = analyze.trim_summary(text, limit=80)
    assert len(out) <= 80
    assert out.endswith("…")
    assert text.startswith(out[:-1])


def test_trim_summary_keeps_short_text():
    assert analyze.trim_summary("짧은 요약.", limit=80) == "짧은 요약."


def test_api_error_log_carries_type_and_message_without_emails(caplog):
    class FakeBadRequest(Exception):
        status_code = 400

        def __init__(self):
            super().__init__()
            self.body = {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Your credit balance is too low (owner: someone@example.com)",
                },
            }

    with caplog.at_level("ERROR", logger="newsletter.stages.analyze"):
        analyze._log_api_error("plain", FakeBadRequest())
    line = caplog.text
    assert "status=400" in line
    assert "type=invalid_request_error" in line
    assert "credit balance is too low" in line
    assert "@" not in line
