"""Shared test doubles and fixtures.

This file is shared by every test module. Planned work may extend it (for
example plan 01.1-03 adds the enrich routes to `mock_hf_week`); unplanned edits
should not. Test modules can import helpers directly
(`from conftest import FakeAnthropic, make_parsed, FakeSMTP, mock_hf_week`) or
use the fixtures below.
"""

import functools
import io
import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from PIL import Image

from newsletter.schema import (
    ExplainerLLM,
    HeadlineLLM,
    HighlightPickLLM,
    HighlightsLLM,
    Issue,
    ItemAnalysisLLM,
    PolishFixLLM,
    PolishLLM,
    TrendLLM,
    VerdictNoteLLM,
    VerdictNotesLLM,
)

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
    in one place. The enrich routes (`mock_enrich`, including the
    raw.githubusercontent.com route from `mock_github` and the api.github.com
    license route from `mock_github_api`, which every W44 star build calls) are
    registered too;
    `enrich_fail=True` makes them all answer 500. The HF CDN route is not
    registered: the W44 star Top 10 has no HF image in the page capture (only
    .mp4 files), and an unused route would trip `assert_all_called`. Tests that
    need it call `mock_enrich`'s CDN route themselves.
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


@functools.lru_cache(maxsize=64)
def image_bytes(size: tuple[int, int] = (1152, 468), fmt: str = "PNG") -> bytes:
    """A small in-memory image of the given size and format (built with Pillow)."""
    buf = io.BytesIO()
    Image.new("RGB", size, (240, 120, 40)).save(buf, format=fmt)
    return buf.getvalue()


def partial(body: bytes, ctype: str = "image/png", total: int | None = None) -> httpx.Response:
    """A 206 answer to the enrich 64 KB Range request, with the content-range total."""
    total = len(body) if total is None else total
    headers = {"content-type": ctype, "content-range": f"bytes 0-{len(body) - 1}/{total}"}
    return httpx.Response(206, headers=headers, content=body)


_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/gif": "GIF"}


def mock_github(
    router: respx.MockRouter,
    readmes: dict | None = None,
    images: dict | None = None,
    *,
    fail: bool = False,
) -> respx.Route:
    """Register one route for https://raw.githubusercontent.com/ backed by
    readme_w44.json.

    `/{owner}/{repo}/HEAD/README.md` serves the captured image lines for that repo
    (unknown repo: 404). Any other path is an image probe: a Pillow image of the
    captured width and height, status 206, the captured content type and
    `content-range: bytes 0-N/<total_bytes>` (unknown image: 404). `readmes` /
    `images` override the fixture maps. `fail=True` answers 500.
    """
    data = _load_fixture("readme_w44.json")
    readmes = data["readmes"] if readmes is None else readmes
    images = data["images"] if images is None else images

    def side(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(500)
        parts = request.url.path.strip("/").split("/")
        if len(parts) == 4 and parts[2:] == ["HEAD", "README.md"]:
            key = "/".join(parts[:2])
            if key in readmes:
                return httpx.Response(200, text=readmes[key])
            return httpx.Response(404, text="404: Not Found")
        meta = images.get(str(request.url))
        if meta is None:
            return httpx.Response(404, text="404: Not Found")
        if meta["status"] not in (200, 206):
            return httpx.Response(meta["status"])
        ctype = meta["content_type"]
        body = image_bytes((meta["width"], meta["height"]), _FORMATS.get(ctype, "PNG"))
        return partial(body[:65536], ctype, meta["total_bytes"])

    return router.get(url__regex=r"^https://raw\.githubusercontent\.com/").mock(side_effect=side)


def mock_arxiv(
    router: respx.MockRouter,
    pages: dict | None = None,
    images: dict | None = None,
    *,
    fail: bool = False,
) -> respx.Route:
    """Register one route for https://arxiv.org/html/.

    `/html/{paper_id}` serves `pages[paper_id]` (default: none, so 404). Any other
    path is a figure probe answered from `images[url] = (width, height)` as a 206
    PNG (unknown: 404). `fail=True` answers 500.
    """
    pages = pages or {}
    images = images or {}

    def side(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(500)
        key = request.url.path.removeprefix("/html/")
        if key in pages:
            return httpx.Response(200, text=pages[key])
        size = images.get(str(request.url))
        if size is None:
            return httpx.Response(404, text="Not Found")
        return partial(image_bytes(tuple(size))[:65536])

    return router.get(url__regex=r"^https://arxiv\.org/html/").mock(side_effect=side)


def mock_github_api(
    router: respx.MockRouter, licenses: dict | None = None, *, fail: bool = False
) -> respx.Route:
    """Register one route for https://api.github.com/repos/{owner}/{repo}/license
    backed by github_license_w44.json.

    Each entry is `{"status_code": int, "body": dict}`. An unknown repo gets 404.
    `licenses` overrides the fixture map, and `fail=True` answers 500.
    """
    data = _load_fixture("github_license_w44.json") if licenses is None else licenses

    def side(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(500)
        parts = request.url.path.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "repos" and parts[3] == "license":
            entry = data.get("/".join(parts[1:3]))
            if entry is not None:
                return httpx.Response(entry["status_code"], json=entry["body"])
        return httpx.Response(404, json={"message": "Not Found"})

    return router.get(url__regex=r"^https://api\.github\.com/repos/").mock(side_effect=side)


def mock_enrich(
    router: respx.MockRouter,
    *,
    fail: bool = False,
    papers: dict | None = None,
    models: dict | None = None,
    image: httpx.Response | None = None,
    cdn: bool = True,
    readmes: dict | None = None,
    readme_images: dict | None = None,
    arxiv_pages: dict | None = None,
    arxiv_images: dict | None = None,
    github_licenses: dict | None = None,
) -> dict[str, respx.Route]:
    """Register the enrich routes (HF paper / model APIs, HF upload CDN,
    raw.githubusercontent.com via `mock_github`, the GitHub license API via
    `mock_github_api` as routes["github_api"]) backed by the W44 captures.

    Unknown ids get 404. `fail=True` answers 500 everywhere. `papers` / `models`
    override the fixture dicts for single-case tests, `readmes` / `readme_images`
    the README fixture maps, `github_licenses` the GitHub license map. CDN requests get a 1152x468 PNG as a 206 partial
    response with its content-range total unless `image` gives another response.
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
        return partial(image_bytes())

    routes = {
        "papers": router.get(url__regex=r"^https://huggingface\.co/api/papers/").mock(
            side_effect=paper_side
        ),
        "models": router.get(url__regex=r"^https://huggingface\.co/api/models/").mock(
            side_effect=model_side
        ),
    }
    routes["github"] = mock_github(router, readmes, readme_images, fail=fail)
    routes["github_api"] = mock_github_api(router, github_licenses, fail=fail)
    routes["arxiv"] = mock_arxiv(router, arxiv_pages, arxiv_images, fail=fail)
    if cdn:
        routes["cdn"] = router.get(url__regex=r"^https://cdn-uploads\.huggingface\.co/").mock(
            side_effect=cdn_side
        )
    return routes


# ------------------------------------------------------ Apps Script routes

APPS_ECHO = "https://script.googleusercontent.com/macros/echo"


def mock_apps_script(
    router: respx.MockRouter,
    endpoint: str,
    rows: list | None = None,
    *,
    ids: tuple[str, ...] | list[str] = (),
    members_reply: httpx.Response | Exception | None = None,
    list_reply: httpx.Response | Exception | None = None,
) -> respx.Route:
    """Register the one Apps Script POST route and return it (04.1-03, reused by 04.1-06).

    The POST is dispatched on its form `action`: `members` answers 302 to a
    googleusercontent GET that serves `{"version": 1, "subscribers": rows}` (or
    `members_reply`), `list` answers `{"version": 1, "ids": ids}` (or `list_reply`),
    anything else `{"error": "forbidden"}`. A reply that is an exception is raised.
    """
    members_url = APPS_ECHO + "?user_content_key=members"

    def _reply(value: httpx.Response | Exception) -> httpx.Response:
        if isinstance(value, Exception):
            raise value
        return value

    def post(request: httpx.Request) -> httpx.Response:
        action = parse_qs(request.content.decode()).get("action", [""])[0]
        if action == "members":
            return httpx.Response(302, headers={"Location": members_url})
        if action == "list":
            if list_reply is not None:
                return _reply(list_reply)
            return httpx.Response(200, json={"version": 1, "ids": list(ids)})
        return httpx.Response(200, json={"error": "forbidden"})

    def get(request: httpx.Request) -> httpx.Response:
        if members_reply is not None:
            return _reply(members_reply)
        return httpx.Response(200, json={"version": 1, "subscribers": list(rows or [])})

    route = router.post(endpoint).mock(side_effect=post)
    router.get(members_url).mock(side_effect=get)
    return route


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


DEFAULT_CLAUDE_GPT_REASON = "대화에서 단계를 나눠 묻는 방식으로 따라 해 볼 수 있어요."
DEFAULT_SKILL_GPT_REASON = "요약 규칙을 Skill로 정리해 두면 같은 형식으로 받을 수 있어요."


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
        claude_gpt="기법 적용 가능",
        claude_gpt_reason_ko=DEFAULT_CLAUDE_GPT_REASON,
        skill_gpt_fit="Claude Skill",
        skill_gpt_reason_ko=DEFAULT_SKILL_GPT_REASON,
    )


def default_headline(kw: dict) -> HeadlineLLM:
    """Deterministic valid headline (emoji from the closed list, hook <= 24 chars)."""
    return HeadlineLLM(emoji="🤖", hook_ko="말하면 로봇이 움직인다?")


DEFAULT_TREND = "이번 주에는 로봇과 멀티모달 연구가 많았어요. 코드를 함께 공개한 연구도 많았어요."


def default_trend(kw: dict) -> TrendLLM:
    """Deterministic valid trend: two plain 해요체 sentences, no names or digits."""
    return TrendLLM(trend_ko=DEFAULT_TREND)


def default_notes(kw: dict) -> VerdictNotesLLM:
    """One neutral, grounded note per `rank: N` line in the user content."""
    ranks = [int(r) for r in re.findall(r"^rank: (\d+)$", _user_text(kw), re.MULTILINE)]
    return VerdictNotesLLM(
        notes=[
            VerdictNoteLLM(
                rank=r,
                commercial_reason_ko="공개된 라이선스 정보를 근거로 판단했어요.",
                poc_reason_ko="공개된 자료 범위를 근거로 판단했어요.",
            )
            for r in ranks
        ]
    )


DEFAULT_HIGHLIGHT_WHY = "같은 형식의 정리를 매주 손으로 다시 하지 않아도 돼요."
DEFAULT_HIGHLIGHT_HOW = "요약 규칙과 예시를 Skill 지시문에 넣어 두면 돼요."


def default_highlights(kw: dict) -> HighlightsLLM:
    """Picks for the first three `rank: N` lines in the user content, with one
    해요체 sentence each (under 70 chars, no digits, no label words)."""
    ranks = [int(r) for r in re.findall(r"^rank: (\d+)$", _user_text(kw), re.MULTILINE)]
    return HighlightsLLM(
        picks=[
            HighlightPickLLM(rank=r, why_ko=DEFAULT_HIGHLIGHT_WHY, how_ko=DEFAULT_HIGHLIGHT_HOW)
            for r in ranks[:3]
        ]
    )


DEFAULT_EXPLAINER_TOPIC = "Mixture of Experts: 필요한 전문가만 불러 쓰는 구조"
DEFAULT_EXPLAINER_POINT = "필요한 부분만 골라 계산하면 큰 모델도 가볍게 돌릴 수 있어요."
DEFAULT_EXPLAINER_BODY = (
    "큰 모델이 입력마다 모든 부분을 다 쓰면 계산이 너무 많아져요. "
    "그래서 여러 expert 네트워크를 나눠 두고 router가 입력마다 몇 개만 골라 써요. "
    "고른 expert만 계산하니 모델 전체가 커도 한 번에 드는 비용은 줄어들어요."
)
DEFAULT_EXPLAINER_EXAMPLE = (
    "수업 중에 질문이 나오면 그 과목 선생님만 답하고 나머지 선생님은 쉬는 학교와 비슷해요."
)


def default_explainer(kw: dict) -> ExplainerLLM:
    """A lint-clean, digit-free 해요체 explainer tied to the first two `rank: N`
    lines inside `<items>` in the user content."""
    text = _user_text(kw)
    m = re.search(r"<items>(.*?)</items>", text, re.DOTALL)
    ranks = [int(r) for r in re.findall(r"^rank: (\d+)$", m.group(1) if m else "", re.MULTILINE)]
    t = re.search(r"<target_rank>(\d+)</target_rank>", text)
    if t:  # rank-order explainer (2026-11-09): related_ranks starts with the target
        target = int(t.group(1))
        ranks = [target] + [r for r in ranks if r != target]
    return ExplainerLLM(
        topic=DEFAULT_EXPLAINER_TOPIC,
        point_ko=DEFAULT_EXPLAINER_POINT,
        body_ko=DEFAULT_EXPLAINER_BODY,
        example_ko=DEFAULT_EXPLAINER_EXAMPLE,
        related_ranks=ranks[:2] or [1],
    )


POLISH_DROP_WORDS = ("혁신적인 ", "획기적인 ")


def default_polish(kw: dict) -> PolishLLM:
    """One fix per `id:` / `text:` pair inside `<fields>`: the text with the words
    "혁신적인 " and "획기적인 " removed, which keeps every fact."""
    m = re.search(r"<fields>(.*?)</fields>", _user_text(kw), re.DOTALL)
    body = m.group(1) if m else ""
    fixes, fid = [], None
    for line in body.splitlines():
        if line.startswith("id: "):
            fid = line[4:].strip()
        elif line.startswith("text: ") and fid is not None:
            text = line[6:]
            for word in POLISH_DROP_WORDS:
                text = text.replace(word, "")
            fixes.append(PolishFixLLM(id=fid, text=text.strip()))
            fid = None
    return PolishLLM(fixes=fixes)


def default_response(kw: dict) -> SimpleNamespace:
    """Valid default for any request type, chosen by the request's output_format."""
    if kw.get("output_format") is HeadlineLLM:
        return make_parsed(default_headline(kw))
    if kw.get("output_format") is TrendLLM:
        return make_parsed(default_trend(kw))
    if kw.get("output_format") is VerdictNotesLLM:
        return make_parsed(default_notes(kw))
    if kw.get("output_format") is HighlightsLLM:
        return make_parsed(default_highlights(kw))
    if kw.get("output_format") is ExplainerLLM:
        return make_parsed(default_explainer(kw))
    if kw.get("output_format") is PolishLLM:
        return make_parsed(default_polish(kw))
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
    When the script is exhausted, calls return a valid default chosen by
    `output_format`: a headline (HeadlineLLM), a trend (TrendLLM), one note per
    input rank (VerdictNotesLLM), picks for the first three input ranks
    (HighlightsLLM), an explainer tied to the first two input ranks
    (ExplainerLLM), one fix per requested field (PolishLLM), or else an analysis.
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


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_endpoint: keep the committed UNSUBSCRIBE_ENDPOINT instead of forcing it to None",
    )
    config.addinivalue_line(
        "markers",
        "real_clock: keep deliver._now unpatched (the test sets its own clock)",
    )


W44_SEND_TIME = datetime(2026, 11, 2, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))


@pytest.fixture(autouse=True)
def w44_send_day(request, monkeypatch):
    """05-01: deliver's clock reads 2026-11-02 09:00 KST (W44's send day) unless the test
    is marked real_clock, so the W44 send tests keep their meaning under the stale guard."""
    if request.node.get_closest_marker("real_clock") is None:
        from newsletter.delivery import deliver

        monkeypatch.setattr(deliver, "_now", lambda: W44_SEND_TIME)


@pytest.fixture(autouse=True)
def endpoint_neutral(request, monkeypatch):
    """04.1-05: tests run with UNSUBSCRIBE_ENDPOINT = None unless marked live_endpoint.

    The committed constant is the live /exec URL. Tests that need an endpoint
    set their own with monkeypatch, which still wins over this default.
    """
    if request.node.get_closest_marker("live_endpoint") is None:
        from newsletter.delivery import unsubscribe

        monkeypatch.setattr(unsubscribe, "UNSUBSCRIBE_ENDPOINT", None)


@pytest.fixture(autouse=True)
def no_github_token(monkeypatch):
    """T-02-16: a token in the local shell must never reach a test request."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


@pytest.fixture(autouse=True)
def no_runner_outputs(monkeypatch):
    """05-01: a CI runner's GITHUB_OUTPUT or a shell SEND_PAUSED must not leak into tests."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("SEND_PAUSED", raising=False)


@pytest.fixture(autouse=True)
def ledger_tmp(tmp_path, monkeypatch):
    """05-03: every test writes its send ledger under tmp_path, never the repo's data/ledger/."""
    monkeypatch.setenv("NEWSLETTER_LEDGER_DIR", str(tmp_path / "ledger"))


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
def members_api():
    """`mock_apps_script` as a fixture: members_api(router, endpoint, rows, ids=...)."""
    return mock_apps_script


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
