"""Web archive (04-01): publish, build_site, CLI, PII and brand scans, committed-site freshness."""

import re
from pathlib import Path

import pytest

from newsletter import store, web
from newsletter.__main__ import _EMAIL_RE, main
from newsletter.stages import humanize, render

ISSUE_ID = "2026-W44"
REPO = Path(__file__).resolve().parent.parent
OLD_BRAND = "해달 브리프"
WEB_FOOTER = "구독 해지는 받으신 메일 아래쪽 링크에서 할 수 있어요."
TOKEN_RE = re.compile(r"\?t=[0-9a-f]{32}")


@pytest.fixture
def site(archive_tmp, monkeypatch) -> Path:
    monkeypatch.setenv("NEWSLETTER_ISSUES_DIR", str(archive_tmp / "data" / "issues"))
    monkeypatch.setenv("NEWSLETTER_DOCS_DIR", str(archive_tmp / "docs"))
    return archive_tmp


def _stage(issue) -> None:
    store.write_json(store.week_dir(issue.issue_id) / "issue.json", issue)
    store.write_current(issue.issue_id)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for sub in ("data", "docs")
        for p in sorted((root / sub).rglob("*"))
        if p.is_file()
    }


def _html_files(root: Path) -> list[Path]:
    return sorted((root / "docs").rglob("*.html"))


def test_publish_writes_data_and_both_pages(site, issue_w44):
    assert web.publish(issue_w44) is True
    written = web.build_site()
    data = site / "data" / "issues" / f"{ISSUE_ID}.json"
    page = site / "docs" / "issues" / ISSUE_ID / "index.html"
    home = site / "docs" / "index.html"
    unsub = site / "docs" / "unsubscribe" / "index.html"
    welcome = site / "docs" / "welcome" / "latest.json"
    assert data.is_file()
    assert set(written) == {page, home, unsub, welcome}
    assert issue_w44.headline_ko in page.read_text(encoding="utf-8")
    assert web.load_issues() == [issue_w44]


def test_second_publish_changes_no_byte(site, issue_w44):
    web.publish(issue_w44)
    web.build_site()
    before = _snapshot(site)
    changed = issue_w44.model_copy(update={"headline_ko": "다른 제목"})
    assert web.publish(changed) is False  # first send wins
    web.build_site()
    assert _snapshot(site) == before


@pytest.mark.parametrize("mode", ["preview", "test"])
def test_cli_non_send_writes_nothing(site, issue_w44, mode, caplog):
    _stage(issue_w44)
    with caplog.at_level("INFO"):
        assert main(["publish", "--mode", mode]) == 0
    assert f"web=skipped mode={mode}" in caplog.text
    assert not (site / "data").exists()
    assert not (site / "docs").exists()


def test_cli_send_end_to_end(site, issue_w44, caplog):
    _stage(issue_w44)
    with caplog.at_level("INFO"):
        assert main(["publish", "--mode", "send"]) == 0
        assert main(["publish", "--mode", "send"]) == 0
    page = (site / "docs" / "issues" / ISSUE_ID / "index.html").read_text(encoding="utf-8")
    home = (site / "docs" / "index.html").read_text(encoding="utf-8")
    assert issue_w44.headline_ko in page
    assert home.count('id="archive"') == 1
    assert f'href="issues/{ISSUE_ID}/"' in home
    assert render.date_line(issue_w44) in home
    assert f"web=published issue={ISSUE_ID}" in caplog.text
    assert f"web=exists issue={ISSUE_ID}" in caplog.text
    assert "web=site pages=4" in caplog.text
    assert issue_w44.headline_ko not in caplog.text


def test_cli_site_regenerates_without_archive(site, issue_w44, caplog):
    web.publish(issue_w44)
    with caplog.at_level("INFO"):
        assert main(["site"]) == 0
    assert (site / "docs" / "issues" / ISSUE_ID / "index.html").is_file()
    assert "web=site pages=4" in caplog.text


def test_home_lists_newest_first(site, issue_w44):
    newer = issue_w44.model_copy(update={"issue_id": "2026-W45", "headline_ko": "다음 주 제목"})
    web.publish(issue_w44)
    web.publish(newer)
    web.build_site()
    home = (site / "docs" / "index.html").read_text(encoding="utf-8")
    assert home.index('href="issues/2026-W45/"') < home.index('href="issues/2026-W44/"')
    assert [i.issue_id for i in web.load_issues()] == ["2026-W45", "2026-W44"]


def test_home_empty_state(site):
    web.build_site()
    home = (site / "docs" / "index.html").read_text(encoding="utf-8")
    assert 'id="archive"' in home
    assert "아직 발행된 호가 없어요." in home


def test_invalid_issue_file_raises(site):
    d = site / "data" / "issues"
    d.mkdir(parents=True)
    (d / "2026-W44.json").write_text('{"issue_id": "2026-W44"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        web.build_site()


def test_generated_pages_carry_no_personal_data(site, issue_w44):
    web.publish(issue_w44)
    web.build_site()
    files = _html_files(site)
    assert len(files) == 3
    for p in files:
        text = p.read_text(encoding="utf-8")
        assert not _EMAIL_RE.search(text), p
        assert not TOKEN_RE.search(text), p
        if p.parent.name == "unsubscribe":
            continue  # the confirm page carries the button and the reply line by design
        assert not re.search(r">\s*구독 해지\s*<", text), p
        assert "수신거부" not in text, p
    page = (site / "docs" / "issues" / ISSUE_ID / "index.html").read_text(encoding="utf-8")
    assert "구독자님, 안녕하세요." in page
    assert WEB_FOOTER in page


def test_generated_pages_use_current_brand_only(site, issue_w44):
    web.publish(issue_w44)
    web.build_site()
    for p in _html_files(site):
        text = p.read_text(encoding="utf-8")
        assert render.BRAND in text, p
        assert OLD_BRAND not in text, p


def test_build_site_never_writes_assets(site, issue_w44):
    web.publish(issue_w44)
    web.build_site()
    assert not (site / "docs" / "assets").exists()


def test_web_footer_copy_passes_humanizer():
    assert not [c for c in humanize.lint(WEB_FOOTER) if c in humanize.HARD_CODES]


def test_committed_site_is_fresh(tmp_path, monkeypatch):
    """docs/ must match a regeneration from the committed data/issues (run `site`)."""
    monkeypatch.setenv("NEWSLETTER_ISSUES_DIR", str(REPO / "data" / "issues"))
    monkeypatch.setenv("NEWSLETTER_DOCS_DIR", str(tmp_path / "docs"))
    written = web.build_site()
    assert tmp_path / "docs" / "unsubscribe" / "index.html" in written
    for path in written:
        rel = path.relative_to(tmp_path / "docs")
        assert (REPO / "docs" / rel).read_bytes() == path.read_bytes(), rel
    for p in (REPO / "docs").rglob("*.html"):
        text = p.read_text(encoding="utf-8")
        assert OLD_BRAND not in text, p


# --- 04-03 Task 1: archive cards and hidden subscribe slots (D-07, D-08, D-09) ---


def _two_issues(issue):
    older = issue.model_copy(update={"issue_id": "2026-W43", "headline_ko": "지난주 제목"})
    return issue, older


def _home(site) -> str:
    return (site / "docs" / "index.html").read_text(encoding="utf-8")


def _archive(home: str) -> str:
    start = home.index('id="archive"')
    return home[start : home.index("</section>", start)]


def test_card_holds_date_headline_top3_and_image(issue_w44):
    c = web.card(issue_w44)
    assert c["url"] == f"issues/{ISSUE_ID}/"
    assert c["date"] == render.date_line(issue_w44)
    assert c["headline"] == issue_w44.headline_ko
    assert c["top3"] == [it.title_ko for it in issue_w44.items[:3]]
    assert c["image"] == issue_w44.items[0].image


def test_archive_cards_newest_first_with_top3(site, issue_w44):
    for i in _two_issues(issue_w44):
        web.publish(i)
    web.build_site()
    archive = _archive(_home(site))
    assert archive.index('href="issues/2026-W44/"') < archive.index('href="issues/2026-W43/"')
    assert archive.index(issue_w44.headline_ko) < archive.index("지난주 제목")
    for it in issue_w44.items[:3]:
        assert it.title_ko in archive
    assert render.date_line(issue_w44) in archive


def test_archive_card_image_only_when_present(site, issue_w44):
    first = issue_w44.items[0]
    assert first.image is not None
    no_image = issue_w44.model_copy(
        update={
            "issue_id": "2026-W43",
            "items": [first.model_copy(update={"image": None}), *issue_w44.items[1:]],
        }
    )
    web.publish(issue_w44)
    web.publish(no_image)
    web.build_site()
    archive = _archive(_home(site))
    w44, w43 = archive.split('href="issues/2026-W43/"', 1)
    assert w44.count("<img") == 1
    assert f'src="{first.image.url}"' in w44
    assert f'alt="{first.title_ko}"' in w44
    assert "<img" not in w43


def test_subscribe_hidden_while_url_is_none(site, issue_w44):
    assert web.SUBSCRIBE_URL is None
    assert web.PRIVACY_URL is None
    web.publish(issue_w44)
    web.build_site()
    home = _home(site)
    assert "<form" not in home
    assert "무료로 구독하기" not in home
    assert "구독하기" not in home
    assert "개인정보 처리방침" not in home


def test_subscribe_forms_appear_once_url_is_set(site, issue_w44, monkeypatch):
    url = "https://script.google.com/macros/s/example/exec"
    monkeypatch.setattr(web, "SUBSCRIBE_URL", url)
    monkeypatch.setattr(web, "PRIVACY_URL", "https://example.org/privacy")
    web.publish(issue_w44)
    web.build_site()
    home = _home(site)
    assert home.count("<form") == 2
    assert home.count(f'action="{url}"') == 2
    assert home.count("무료로 구독하기") == 2
    assert 'class="nav-cta"' in home
    assert "개인정보 처리방침" in home


def test_archive_empty_state_line(site):
    web.build_site()
    assert "아직 발행된 호가 없어요." in _archive(_home(site))


# --- 04-03 Task 2: Figma 25:356 landing (D-04, D-15) ---

SECTIONS = ["nav", "hero", "what-you-get", "sample", "archive", "cta", "footer"]
# Sentences written for the page; each must appear in the home and pass the humanizer.
HOME_SENTENCES = [
    (
        "Hugging Face Papers에 올라온 모델 중 GitHub star를 많이 받은 것만 골라, 무엇을 하는 "
        "모델인지 비전공자도 이해하게 풀어 써요. 상업적으로 써도 되는지, 바로 돌려볼 수 "
        "있는지도 함께 알려 드려요."
    ),
    "지난주 올라온 모델 중 개발자들이 실제로 관심 갖는 것만 골라요.",
    "이번 주 새로 나온 기술 하나를 예시와 함께 쉽게 풀어 설명해요.",
    (
        "카드마다 한 줄 요약, 쉬운 설명 세 줄, 모델 정보와 활용 아이디어가 들어가요. 스크롤 몇 "
        "번이면 이번 주 Top 10을 다 볼 수 있어요."
    ),
    "첫 메일이 나가면 그 호를 여기에서 바로 읽을 수 있어요.",
]
# Labels and noun phrases (lint kind="name").
HOME_NAMES = [
    "한 번 읽으면 이번 주 AI 흐름이 정리돼요",
    "이런 메일이 매주 도착해요",
    "지금까지 보낸 메일",
    "첫 호를 준비하고 있어요",
    "매주 월요일 오전 8시 발송 · 출처: Hugging Face Papers",
]
# Only rendered once SUBSCRIBE_URL is set (Phase 4.1).
FORM_SENTENCES = [
    "뉴스레터 수신과 이메일 수집에 동의해요. 언제든 그만 받을 수 있어요.",
    "메일 아래쪽 링크로 언제든 해지할 수 있어요.",
]
# Owner-approved copy taken verbatim from Figma 25:356: exempt from the lint (D-04).
OWNER_FIGMA_COPY = [
    "AI 모델, 해달이 골라 드려요",  # hero title, second line
    "다음 주 월요일, 해달이 기다릴게요 👋",  # bottom CTA, same emoji as the email closing
]


@pytest.fixture
def home_html(site, issue_w44) -> str:
    web.publish(issue_w44)
    web.build_site()
    return _home(site)


def test_home_sections_follow_figma_order(home_html):
    marks = [home_html.index(f'data-section="{s}"') for s in SECTIONS]
    assert marks == sorted(marks)


def test_what_you_get_has_exactly_two_cards(home_html):
    assert home_html.count('data-card="what-you-get"') == 2
    assert "GitHub star Top 10" in home_html
    assert "AI 기술 쉽게 보기" in home_html
    assert "바로 써볼 만한 것" not in home_html


def test_sample_preview_has_no_banner_and_shows_latest(home_html, issue_w44):
    sample = home_html[home_html.index('data-section="sample"') : home_html.index('id="archive"')]
    assert "otter-banner" not in sample
    assert issue_w44.headline_ko in sample
    assert f'href="issues/{ISSUE_ID}/"' in sample
    assert sample.count(f'href="{render.ARCHIVE_ANCHOR}"') == 1


def test_nav_archive_link_uses_anchor(home_html):
    nav = home_html[: home_html.index('data-section="hero"')]
    assert f'href="{render.ARCHIVE_ANCHOR}">지난 호<' in nav


def test_home_static_font_and_responsive(home_html):
    assert "<script" not in home_html.lower()
    assert "@media (max-width: 767px)" in home_html
    assert f'href="{render.WEB_FONT_URL.replace("&", "&amp;")}"' in home_html
    assert "IBM+Plex+Sans+KR" in home_html
    assert render.FONT_STACK in home_html
    assert home_html.count(f"{render.ASSET_BASE_URL}/otter-banner.jpg") == 1
    assert '<html lang="ko">' in home_html
    assert "mailto:" not in home_html


def test_home_footer_is_brand_and_send_note_only(home_html):
    footer = home_html[home_html.index('data-section="footer"') :]
    assert render.BRAND in footer
    assert "매주 월요일 오전 8시 발송 · 출처: Hugging Face Papers" in footer
    assert not _EMAIL_RE.search(footer)


def test_templates_hold_no_literal_brand():
    for name in ("_base.html.j2", "home.html.j2", "unsubscribe.html.j2"):
        text = (store.TEMPLATES_DIR / "web" / name).read_text(encoding="utf-8")
        assert render.BRAND not in text, name
        assert OLD_BRAND not in text, name


def test_no_page_uses_old_brand(home_html):
    assert render.BRAND in home_html
    assert home_html.count(render.BRAND) >= 3  # title, nav, footer
    for p in (REPO / "docs").rglob("*.html"):
        assert OLD_BRAND not in p.read_text(encoding="utf-8"), p


def test_home_copy_is_rendered(home_html, site, issue_w44, monkeypatch):
    for text in HOME_SENTENCES[:4] + HOME_NAMES[:3] + HOME_NAMES[4:] + OWNER_FIGMA_COPY:
        assert text in home_html, text
    # empty-state preview copy
    for p in (site / "data" / "issues").glob("*.json"):
        p.unlink()
    monkeypatch.setattr(web, "SUBSCRIBE_URL", "https://script.google.com/macros/s/x/exec")
    web.build_site()
    empty = _home(site)
    assert HOME_SENTENCES[4] in empty
    assert HOME_NAMES[3] in empty
    for text in FORM_SENTENCES:
        assert text in empty, text


@pytest.mark.parametrize("text", HOME_SENTENCES + FORM_SENTENCES)
def test_home_sentences_pass_humanizer(text):
    assert not [c for c in humanize.lint(text) if c in humanize.HARD_CODES]


@pytest.mark.parametrize("text", HOME_NAMES)
def test_home_labels_pass_humanizer(text):
    assert not [c for c in humanize.lint(text, kind="name") if c in humanize.HARD_CODES]


# --- 04-06: /unsubscribe/ confirm page (D-12) ---

ENDPOINT = "https://script.google.com/macros/s/X/exec"
UNSUB_HEADING = "구독을 해지할까요?"
UNSUB_SENTENCES = [
    "버튼을 누르면 다음 주부터 메일이 가지 않아요.",
    "링크가 올바르지 않아요. 받으신 메일의 링크를 다시 눌러 주세요.",
    "메일에 '수신거부'라고 회신해 주세요.",
]


def _unsub(site, monkeypatch, endpoint: str | None) -> str:
    monkeypatch.setattr(web.unsubscribe, "UNSUBSCRIBE_ENDPOINT", endpoint)
    web.build_site()
    return (site / "docs" / "unsubscribe" / "index.html").read_text(encoding="utf-8")


def _script(html: str) -> str:
    start = html.index("<script>")
    return html[start : html.index("</script>", start)]


def test_unsubscribe_page_written_every_run(site, monkeypatch):
    path = site / "docs" / "unsubscribe" / "index.html"
    assert path in web.build_site()
    path.unlink()
    web.build_site()
    assert path.is_file()


def test_unsubscribe_page_with_endpoint_posts_only_from_button(site, monkeypatch):
    html = _unsub(site, monkeypatch, ENDPOINT)
    assert html.count("<form") == 1
    form = html[html.index("<form") : html.index("</form>")]
    assert 'method="post"' in form
    assert f'action="{ENDPOINT}"' in form
    assert f'data-endpoint="{ENDPOINT}"' in form
    assert re.search(r'<input type="hidden" name="t"', form)
    assert re.search(r"<button[^>]*>구독 해지</button>", form)
    assert " hidden" in form[: form.index(">")]  # revealed by JS only
    assert UNSUB_HEADING in html
    assert UNSUB_SENTENCES[0] in html
    js = _script(html)
    assert f"^[0-9a-f]{{{web.unsubscribe.TOKEN_LEN}}}$" in js
    assert ".value" in js
    assert "innerHTML" not in js
    assert ".submit(" not in html
    assert '"?t=" + t' in js
    assert ENDPOINT not in js  # endpoint only via the autoescaped data- attribute


def test_unsubscribe_page_bad_link_and_noscript_lines(site, monkeypatch):
    html = _unsub(site, monkeypatch, ENDPOINT)
    assert UNSUB_SENTENCES[1] in html
    bad = html[html.index('<p id="unsub-bad"') :]
    assert " hidden" in bad[: bad.index(">")]
    noscript = html[html.index("<noscript>") : html.index("</noscript>")]
    assert "수신거부" in noscript
    assert UNSUB_SENTENCES[2] in noscript


def test_unsubscribe_page_without_endpoint_shows_reply_only(site, monkeypatch):
    html = _unsub(site, monkeypatch, None)
    assert "<form" not in html
    assert "<script" not in html.lower()
    assert ">구독 해지<" not in html
    assert UNSUB_SENTENCES[2] in html
    assert "<noscript>" not in html


def test_unsubscribe_endpoint_is_autoescaped(site, monkeypatch):
    html = _unsub(site, monkeypatch, 'https://x.example/"><script>alert(1)</script>')
    assert "<script>alert(1)" not in html
    assert "&#34;&gt;&lt;script&gt;" in html


@pytest.mark.parametrize("endpoint", [ENDPOINT, None])
def test_unsubscribe_page_carries_no_personal_data(site, monkeypatch, endpoint):
    html = _unsub(site, monkeypatch, endpoint)
    assert not re.search(r"[0-9a-f]{32}", html)
    assert not _EMAIL_RE.search(html)
    assert "LIST_KEY" not in html
    assert "mailto:" not in html
    assert render.BRAND in html
    assert OLD_BRAND not in html
    assert '<meta name="robots" content="noindex">' in html
    assert 'href="../"' in html  # logo goes home from /unsubscribe/
    assert f'href="../{render.ARCHIVE_ANCHOR}"' in html
    assert "무료로 구독하기" not in html


@pytest.mark.parametrize("text", UNSUB_SENTENCES)
def test_unsubscribe_sentences_pass_humanizer(text):
    assert not [c for c in humanize.lint(text) if c in humanize.HARD_CODES]


def test_unsubscribe_heading_passes_humanizer():
    assert not [c for c in humanize.lint(UNSUB_HEADING, kind="name") if c in humanize.HARD_CODES]
