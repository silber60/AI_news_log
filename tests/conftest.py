"""Shared test doubles and fixtures.

Wave 2 plans use these; they must not edit this file. Test modules can import
the classes directly (`from conftest import FakeAnthropic, make_parsed, FakeSMTP`)
or use the fixtures below.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from newsletter.schema import Issue, ItemAnalysisLLM

FIXTURES = Path(__file__).parent / "fixtures"


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
        summary_ko="테스트용 한줄 요약입니다.",
        does_ko="테스트 모델이 하는 일이다.",
        new_ko="이전 방법과 다른 점이다.",
        result_ko="논문이 보고한 결과다.",
        kind_ko="테스트 모델",
        architecture_ko="확인 필요",
    )


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
    When the script is exhausted, calls return a valid default analysis.
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
        return make_parsed(default_analysis(kw))

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
