"""Shared test doubles and fixtures.

This file is shared by every test module. Planned work may extend it (for
example plan 01.1-03 adds the enrich routes to `mock_hf_week`); unplanned edits
should not. Test modules can import helpers directly
(`from conftest import FakeAnthropic, make_parsed, FakeSMTP, mock_hf_week`) or
use the fixtures below.
"""

import io
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import httpx
import pytest
import respx
from PIL import Image

from newsletter.schema import HeadlineLLM, Issue, ItemAnalysisLLM

FIXTURES = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------ HF routes


def mock_hf_week(
    router: respx.MockRouter,
    pages: list[list[dict]],
    issue_id: str = "2026-W44",
    *,
    enrich_fail: bool = False,
) -> list[respx.Route]:
    """Register the daily_papers week routes (one per page) and return them.

    Every run_build test goes through here, so later plans add their HF routes
    in one place. The enrich routes (`mock_enrich`) are registered too;
    `enrich_fail=True` makes them all answer 500. The HF CDN route is not
    registered: the W44 star Top 10 has no HF image (only an .mp4), and an unused
    route would trip `assert_all_called`. Tests that need it call `mock_enrich`'s
    CDN route themselves.
    """
    routes = [
        router.get(
            "https://huggingface.co/api/daily_papers",
            params={"week": issue_id, "limit": "100", "p": str(i)},
        ).mock(return_value=httpx.Response(200, json=page))
        for i, page in enumerate(pages)
    ]
    mock_enrich(router, fail=enrich_fail, cdn=False)
    return routes


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def image_bytes(size: tuple[int, int] = (1152, 468), fmt: str = "PNG") -> bytes:
    """A small in-memory image of the given size and format (built with Pillow)."""
    buf = io.BytesIO()
    Image.new("RGB", size, (240, 120, 40)).save(buf, format=fmt)
    return buf.getvalue()


def mock_enrich(
    router: respx.MockRouter,
    *,
    fail: bool = False,
    papers: dict | None = None,
    models: dict | None = None,
    image: httpx.Response | None = None,
    cdn: bool = True,
) -> dict[str, respx.Route]:
    """Register the enrich routes (HF paper / model APIs, HF upload CDN) backed by
    the W44 captures.

    Unknown ids get 404. `fail=True` answers 500 everywhere. `papers` / `models`
    override the fixture dicts for single-case tests. CDN requests get a 1152x468
    PNG as a 206 partial response unless `image` gives another response.
    `cdn=False` skips the CDN route.
    """
    papers = _load_fixture("hf_papers_w44.json") if papers is None else papers
    models = _load_fixture("hf_models_w44.json") if models is None else models

    def lookup(table: dict, key: str) -> httpx.Response:
        if fail:
            return httpx.Response(500)
        if key in table:
            return httpx.Response(200, json=table[key])
        return httpx.Response(404, json={"error": "not found"})

    def paper_side(request: httpx.Request) -> httpx.Response:
        return lookup(papers, request.url.path.removeprefix("/api/papers/"))

    def model_side(request: httpx.Request) -> httpx.Response:
        return lookup(models, request.url.path.removeprefix("/api/models/"))

    def cdn_side(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(500)
        if image is not None:  # a fresh copy per request
            return httpx.Response(image.status_code, headers=image.headers, content=image.content)
        return httpx.Response(206, headers={"content-type": "image/png"}, content=image_bytes())

    routes = {
        "papers": router.get(url__regex=r"^https://huggingface\.co/api/papers/").mock(
            side_effect=paper_side
        ),
        "models": router.get(url__regex=r"^https://huggingface\.co/api/models/").mock(
            side_effect=model_side
        ),
    }
    if cdn:
        routes["cdn"] = router.get(url__regex=r"^https://cdn-uploads\.huggingface\.co/").mock(
            side_effect=cdn_side
        )
    return routes


# ---------------------------------------------------------------- Claude fakes


def make_parsed(
    parsed_output: Any = None,
    *,
    stop_reason: str = "end_turn",
    stop_details: Any = None,
    usage: Any = None,
) -> SimpleNamespace:
    """Build an object shaped like anthropic's ParsedMessage for the fields we read."""
    if usage is None:
        usage = SimpleNamespace(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
    return SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed_output,
        stop_details=stop_details,
        usage=usage,
    )


def _user_text(kw: dict) -> str:
    parts = []
    for m in kw.get("messages", []):
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(b.get("text", "") for b in content if isinstance(b, dict))
    return "\n".join(parts)


def default_analysis(kw: dict) -> ItemAnalysisLLM:
    """Deterministic valid analysis derived from the paper title in the user content."""
    m = re.search(r"^title: (.*)$", _user_text(kw), re.MULTILINE)
    title = (m.group(1).strip() if m else "Untitled")[:40]
    return ItemAnalysisLLM(
        title_ko=f"{title}: 테스트 제목",
        ai_type="멀티모달",
        summary_ko="테스트용 한줄 요약이에요.",
        does_ko="테스트 모델이 하는 일이에요.",
        new_ko="이전 방법과 다른 점이에요.",
        result_ko="논문이 보고한 결과예요.",
        kind_ko="테스트 모델",
        architecture_ko="확인 필요",
        use_idea_ko="테스트 업무에 쓸 수 있어요.",
    )


def default_headline(kw: dict) -> HeadlineLLM:
    """Deterministic valid headline (emoji from the closed list, hook <= 24 chars)."""
    return HeadlineLLM(emoji="🤖", hook_ko="말하면 로봇이 움직인다?")


def default_response(kw: dict) -> SimpleNamespace:
    """Valid default for either request type, chosen by the request's output_format."""
    if kw.get("output_format") is HeadlineLLM:
        return make_parsed(default_headline(kw))
    return make_parsed(default_analysis(kw))


class _Messages:
    def __init__(self, owner: FakeAnthropic, namespace: str):
        self._owner = owner
        self._ns = namespace

    def parse(self, **kw):
        return self._owner._handle(self._ns, kw)


class FakeAnthropic:
    """Scriptable stand-in for anthropic.Anthropic.

    `script` items are consumed one per call, in order. Each item may be:
      - a response object (e.g. from `make_parsed`), returned as is;
      - an Exception instance, raised;
      - a callable `f(kw) -> response`, called with the request kwargs.
    When the script is exhausted, calls return a valid default: an analysis, or a
    headline when `output_format` is HeadlineLLM.
    Every call is recorded in `calls` as `{"ns": "messages"|"beta", "kw": kw}`.
    """

    def __init__(self, script: list | None = None):
        self.script = list(script or [])
        self.calls: list[dict] = []
        self.messages = _Messages(self, "messages")
        self.beta = SimpleNamespace(messages=_Messages(self, "beta"))

    def _handle(self, ns: str, kw: dict):
        self.calls.append({"ns": ns, "kw": kw})
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, BaseException):
                raise step
            if callable(step):
                return step(kw)
            return step
        return default_response(kw)

    def user_texts(self) -> list[str]:
        return [_user_text(c["kw"]) for c in self.calls]


# ------------------------------------------------------------------ SMTP fake


class FakeSMTP:
    """Stand-in for smtplib.SMTP_SSL. Records logins and sent messages."""

    instances: ClassVar[list[FakeSMTP]] = []

    def __init__(self, host: str = "", port: int = 0, *args, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.login_calls: list[tuple[str, str]] = []
        self.sent: list = []
        self.closed = False
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.quit()
        return False

    def login(self, user: str, password: str):
        self.login_calls.append((user, password))
        return (235, b"ok")

    def send_message(self, msg, *args, **kwargs):
        self.sent.append(msg)
        return {}

    def quit(self):
        self.closed = True

    def close(self):
        self.closed = True

    def set_debuglevel(self, level):  # pragma: no cover - must never be called
        raise AssertionError("SMTP debug output must stay off")


# ------------------------------------------------------------------- fixtures


@pytest.fixture
def fake_anthropic() -> FakeAnthropic:
    return FakeAnthropic()


@pytest.fixture
def fake_smtp(monkeypatch) -> type[FakeSMTP]:
    """Patch newsletter.delivery.send.smtplib.SMTP_SSL with FakeSMTP."""
    from newsletter.delivery import send

    FakeSMTP.instances = []
    monkeypatch.setattr(send.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


@pytest.fixture
def hf_pages() -> list[list[dict]]:
    """The three captured HF W44 pages (trimmed), in page order p0, p1, p2."""
    return [
        json.loads((FIXTURES / f"hf_w44_p{i}.json").read_text(encoding="utf-8")) for i in range(3)
    ]


@pytest.fixture
def archive_tmp(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("NEWSLETTER_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("NEWSLETTER_OUT_DIR", str(tmp_path / "out"))
    return tmp_path


@pytest.fixture
def issue_w44() -> Issue:
    data = json.loads((FIXTURES / "issue_w44.json").read_text(encoding="utf-8"))
    return Issue.model_validate(data)
