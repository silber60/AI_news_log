"""Claude stage: retry-once, fallback downgrade, field checks (ANLY-01/03/06, D-15, D-19)."""

import json

import anthropic
import httpx
import httpx2
import pytest
import respx
from conftest import FakeAnthropic, default_analysis, make_parsed

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
        for i, page in enumerate(hf_pages):
            router.get(
                "https://huggingface.co/api/daily_papers",
                params={"week": ISSUE_ID, "limit": "100", "p": str(i)},
            ).mock(return_value=httpx.Response(200, json=page))
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
    assert len(fake.calls) == 11
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
    assert len(fake.calls) == 6
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
    assert [c["ns"] for c in fake.calls] == ["beta"] + ["messages"] * 10
    for c in fake.calls[1:]:
        assert "fallbacks" not in c["kw"] and "betas" not in c["kw"]
    assert "previous_output_problems" not in fake.user_texts()[1]


def test_sdk_type_error_downgrades_to_plain_parse(hf_pages, archive_tmp):
    fake = FakeAnthropic([TypeError("unexpected keyword argument 'fallbacks'")])
    issue = _build(hf_pages, fake)

    assert len(issue.items) == 10
    assert [c["ns"] for c in fake.calls] == ["beta"] + ["messages"] * 10


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
    "use_ideas_ko": ["긴 회의 영상 요약"],
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
