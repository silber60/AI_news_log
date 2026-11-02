"""Phase 1 email render: card content, email-safe markup, size gate, text part, subject."""

import html as html_lib

import httpx
import respx
from conftest import FakeAnthropic

from newsletter.week import week_label

ISSUE_ID = "2026-W44"


def _build(hf_pages):
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        for i, page in enumerate(hf_pages):
            router.get(
                "https://huggingface.co/api/daily_papers",
                params={"week": ISSUE_ID, "limit": "100", "p": str(i)},
            ).mock(return_value=httpx.Response(200, json=page))
        return run_build(ISSUE_ID, claude_client=FakeAnthropic())


# ---------------------------------------------------------------- Task 1 tracer


def test_build_renders_full_card_email(hf_pages, archive_tmp):
    issue = _build(hf_pages)
    out = (archive_tmp / "archive" / ISSUE_ID / "email.html").read_text(encoding="utf-8")

    assert out.count("data-card=") == 10
    for it in issue.items:
        assert html_lib.escape(it.title_ko, quote=False) in out
        assert f"#{it.rank}<" in out
        assert f"▲ {it.upvotes}<" in out
    assert "구독자님" in out
    assert week_label(issue.week_start, issue.week_end) in out
