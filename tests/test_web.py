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
    assert data.is_file()
    assert set(written) == {page, home}
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
    assert "web=site pages=2" in caplog.text
    assert issue_w44.headline_ko not in caplog.text


def test_cli_site_regenerates_without_archive(site, issue_w44, caplog):
    web.publish(issue_w44)
    with caplog.at_level("INFO"):
        assert main(["site"]) == 0
    assert (site / "docs" / "issues" / ISSUE_ID / "index.html").is_file()
    assert "web=site pages=2" in caplog.text


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
    assert len(files) == 2
    for p in files:
        text = p.read_text(encoding="utf-8")
        assert not _EMAIL_RE.search(text), p
        assert not TOKEN_RE.search(text), p
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
    for path in web.build_site():
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
