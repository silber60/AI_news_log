"""Welcome mail payload (04.1-01): render_welcome, docs/welcome/latest.json, the fill."""

import html
import json
from pathlib import Path

import pytest

from newsletter import web
from newsletter.stages import render

ISSUE_ID = "2026-W44"
GREETING = "홍길동님"
WELCOME_LINE = "구독해 주셔서 고마워요. 매주 월요일 오전 8시에 보내드려요."
NOT_ME_LINE = "직접 신청하지 않으셨다면 아래 구독 해지를 눌러 주세요."
# Apps Script re-checks this after the fill (04.1-02).
FILLED_LIMIT = 92_160


@pytest.fixture
def site(archive_tmp, monkeypatch) -> Path:
    monkeypatch.setenv("NEWSLETTER_ISSUES_DIR", str(archive_tmp / "data" / "issues"))
    monkeypatch.setenv("NEWSLETTER_DOCS_DIR", str(archive_tmp / "docs"))
    return archive_tmp


def _latest(root: Path) -> dict:
    return json.loads((root / "docs" / "welcome" / "latest.json").read_text(encoding="utf-8"))


def _fill(payload: dict, name: str, link: str) -> tuple[str, str]:
    """Python port of the Apps Script fill: split/join, the name HTML-escaped in html."""
    g, u = payload["slots"]["greeting"], payload["slots"]["unsubscribe_url"]
    filled_html = html.escape(name).join(payload["html"].split(g))
    filled_html = html.escape(link).join(filled_html.split(u))
    filled_text = link.join(name.join(payload["text"].split(g)).split(u))
    return filled_html, filled_text


def test_tracer_latest_json_fills_like_apps_script(site, issue_w44):
    web.publish(issue_w44)
    written = web.build_site()
    assert site / "docs" / "welcome" / "latest.json" in written
    payload = _latest(site)
    assert payload["version"] == 1
    assert payload["issue_id"] == ISSUE_ID
    assert payload["subject"].startswith("[환영] ")
    assert payload["subject"] == "[환영] " + issue_w44.headline_ko
    assert payload["from_name"] == render.BRAND
    assert payload["unsubscribe_page"] == render.SITE_URL + "unsubscribe/?t="
    assert payload["endpoint"] is None
    assert payload["slots"] == {
        "greeting": "__MODAK_GREETING__",
        "unsubscribe_url": "__MODAK_UNSUB_URL__",
    }
    for slot in payload["slots"].values():
        assert payload["html"].count(slot) == 1, slot
        assert payload["text"].count(slot) == 1, slot

    link = payload["unsubscribe_page"] + "a" * 32
    filled_html, filled_text = _fill(payload, GREETING, link)
    for slot in payload["slots"].values():
        assert slot not in filled_html
        assert slot not in filled_text
    assert 'data-section="welcome"' in filled_html
    assert WELCOME_LINE in filled_html
    assert NOT_ME_LINE in filled_html
    assert WELCOME_LINE in filled_text
    assert NOT_ME_LINE in filled_text
    assert f'href="{link}"' in filled_html
    assert link in filled_text
    assert f"{GREETING}, 안녕하세요." in filled_html
    assert f"{GREETING}, 안녕하세요." in filled_text
    assert len(filled_html.encode("utf-8")) < render.MAX_EMAIL_BYTES


def test_welcome_row_comes_before_hero(issue_w44):
    out = render.render_welcome(issue_w44)
    h = out["html"]
    assert h.count('data-section="welcome"') == 1
    assert h.index('data-section="welcome"') < h.index('data-section="hero"')
    t = out["text"]
    assert t.index(WELCOME_LINE) < t.index(issue_w44.headline_ko)


def test_no_issue_writes_null_payload(site):
    web.build_site()
    path = site / "docs" / "welcome" / "latest.json"
    assert path.read_text(encoding="utf-8") == '{"issue_id": null, "version": 1}\n'


def test_oversized_welcome_writes_null_payload(site, issue_w44, monkeypatch, caplog):
    web.publish(issue_w44)
    monkeypatch.setattr(render, "WELCOME_MAX_BYTES", 1)
    with caplog.at_level("INFO"):
        written = web.build_site()
    assert _latest(site) == {"issue_id": None, "version": 1}
    lines = [r.getMessage() for r in caplog.records if "welcome=" in r.getMessage()]
    assert len(lines) == 1
    assert lines[0].startswith("welcome=too_large bytes=")
    assert lines[0].removeprefix("welcome=too_large bytes=").isdigit()
    assert site / "docs" / "index.html" in written
    assert site / "docs" / "issues" / ISSUE_ID / "index.html" in written
    assert (site / "docs" / "index.html").is_file()
    assert (site / "docs" / "issues" / ISSUE_ID / "index.html").is_file()


def test_render_welcome_refuses_at_limit(issue_w44, monkeypatch):
    monkeypatch.setattr(render, "WELCOME_MAX_BYTES", 1)
    with pytest.raises(render.RenderTooLarge, match=r"^bytes=\d+$"):
        render.render_welcome(issue_w44)
