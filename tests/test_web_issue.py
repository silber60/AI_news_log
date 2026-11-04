"""Web issue page (04-02): 판정 근거 rows built by code, web-only block, phone layout."""

import re
from html.parser import HTMLParser

from newsletter.schema import UNKNOWN, EvidenceLink, LicenseInfo
from newsletter.stages import humanize, render
from newsletter.stages.render import basis_links, basis_rows, render_html, render_web_issue

BASIS_TITLE = "판정 근거"
BACK_LINK = "← 지난 호 전체 보기"
LABELS = ["상업 이용", "코드 라이선스", "가중치 라이선스", "바로 써보기", "GPU", "Claude/GPT"]


def _item(issue, **update):
    it = issue.items[0]
    fields = {}
    for key, value in update.items():
        fields[key] = getattr(it, key).model_copy(update=value)
    return it.model_copy(update=fields)


def _rows(it) -> dict[str, dict]:
    return {r["label"]: r for r in basis_rows(it)}


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[dict, str]] = []
        self._open: dict | None = None
        self._text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._open, self._text = dict(attrs), ""

    def handle_data(self, data):
        if self._open is not None:
            self._text += data

    def handle_endtag(self, tag):
        if tag == "a" and self._open is not None:
            self.links.append((self._open, self._text.strip()))
            self._open = None


def _anchors(html: str) -> list[tuple[dict, str]]:
    p = _Anchors()
    p.feed(html)
    return p.links


# ---------------------------------------------------------------- Task 1: basis_rows


def test_rows_in_order_and_unknown_fallback(issue_w44):
    rows = basis_rows(issue_w44.items[0])
    assert [r["label"] for r in rows] == LABELS
    assert all(r["value"] == UNKNOWN and r["url"] is None for r in rows)


def test_code_and_weights_license_are_separate_rows(issue_w44):
    lic = LicenseInfo(spdx_id="Apache-2.0", source_url="https://github.com/o/r/blob/main/LICENSE")
    it = _item(issue_w44, commercial={"verdict": "가능", "code_license": lic})
    rows = _rows(it)
    assert rows["코드 라이선스"]["value"] == "Apache-2.0"
    assert rows["코드 라이선스"]["url"] == "https://github.com/o/r/blob/main/LICENSE"
    assert rows["가중치 라이선스"] == {"label": "가중치 라이선스", "value": UNKNOWN, "url": None}


def test_license_name_when_no_spdx_id(issue_w44):
    lic = LicenseInfo(name="Custom Research License")
    rows = _rows(_item(issue_w44, commercial={"weights_license": lic}))
    assert rows["가중치 라이선스"]["value"] == "Custom Research License"
    assert rows["가중치 라이선스"]["url"] is None


def test_commercial_and_poc_reason_appended_when_present(issue_w44):
    it = _item(
        issue_w44,
        commercial={"verdict": "조건부", "reason_ko": "월 사용자 수 제한이 있어요."},
        poc={"verdict": "코드만"},
    )
    rows = _rows(it)
    assert rows["상업 이용"]["value"] == "조건부 · 월 사용자 수 제한이 있어요."
    assert rows["바로 써보기"]["value"] == "코드만"
    it = _item(issue_w44, poc={"verdict": "바로 가능", "reason_ko": "가중치가 공개됐어요."})
    assert _rows(it)["바로 써보기"]["value"] == "바로 가능 · 가중치가 공개됐어요."


def test_claude_gpt_row_hidden_when_not_applicable(issue_w44):
    it = _item(issue_w44, claude_gpt={"verdict": "해당 없음", "reason_ko": "별도 모델이에요."})
    assert "Claude/GPT" not in _rows(it)
    it = _item(issue_w44, claude_gpt={"verdict": "직접 사용", "reason_ko": "API로 써요."})
    assert _rows(it)["Claude/GPT"]["value"] == "직접 사용 · API로 써요."


def test_gpu_row_uses_card_formats(issue_w44):
    it = _item(
        issue_w44,
        hardware={"local_run": "가능", "est_vram_gb": 13.2, "param_count": 7_000_000_000},
    )
    value = _rows(it)["GPU"]["value"]
    assert "가능" in value
    assert "14GB" in value
    assert "7B 파라미터" in value
    assert _rows(issue_w44.items[0])["GPU"]["value"] == UNKNOWN


def test_basis_links_merge_dedupe_and_filter_hosts(issue_w44):
    hf = EvidenceLink(label="HF 모델", url="https://huggingface.co/o/m")
    gh = EvidenceLink(label="GitHub", url="https://github.com/o/r")
    off = EvidenceLink(label="블로그", url="https://example.com/post")
    it = _item(
        issue_w44,
        commercial={"evidence": [hf, off]},
        poc={"evidence": [gh, hf]},
        hardware={"evidence": [hf]},
    )
    assert basis_links(it) == [hf, gh]
    assert basis_links(issue_w44.items[0]) == []


def test_basis_rows_copy_code_fields_only(issue_w44):
    """Claude text never decides a verdict: a reason alone leaves the verdict 확인 필요."""
    it = _item(issue_w44, commercial={"reason_ko": "상업 이용이 가능해요."})
    assert _rows(it)["상업 이용"]["value"] == f"{UNKNOWN} · 상업 이용이 가능해요."


# ---------------------------------------------------------------- Task 2: web page


def test_web_page_has_one_basis_block_per_card_after_verdict(issue_w44):
    out = render_web_issue(issue_w44)
    assert out.count(BASIS_TITLE) == len(issue_w44.items)
    for it in issue_w44.items:
        card = out.split(f'data-card="{it.rank}"', 1)[1].split("data-card=", 1)[0]
        assert BASIS_TITLE in card
        assert card.index("논문 보기") > card.index(BASIS_TITLE)


def test_email_has_no_basis_block(issue_w44):
    assert BASIS_TITLE not in render_html(issue_w44, "구독자님")
    assert BACK_LINK not in render_html(issue_w44, "구독자님")


def test_titles(issue_w44):
    web = render_web_issue(issue_w44)
    assert web.count("<title") == 1
    title = re.search(r"<title>(.*?)</title>", web).group(1)
    assert title == f"{issue_w44.headline_ko} · {render.BRAND}"
    email = render_html(issue_w44, "구독자님")
    assert email.count("<title") == 1
    assert f"<title>{render.BRAND} {issue_w44.issue_id}</title>" in email


def test_web_back_link_media_rule_and_no_script(issue_w44):
    out = render_web_issue(issue_w44)
    back = [a for a, text in _anchors(out) if text == BACK_LINK]
    assert len(back) == 1
    assert back[0]["href"] == render.archive_url()
    assert "@media (max-width: 680px)" in out
    assert 'class="wrap"' in out
    assert "<script" not in out


def test_fixed_labels_pass_humanize_lint():
    for text in (BASIS_TITLE, BACK_LINK, *LABELS):
        codes = humanize.lint(text, kind="name")
        assert not any(c in humanize.HARD_CODES for c in codes), (text, codes)


def test_web_evidence_hrefs_stay_on_evidence_hosts(issue_w44):
    hf = EvidenceLink(label="HF 모델", url="https://huggingface.co/o/m")
    off = EvidenceLink(label="블로그", url="https://example.com/post")
    lic = LicenseInfo(spdx_id="MIT", source_url="https://github.com/o/r/blob/main/LICENSE")
    items = [
        it.model_copy(
            update={
                "commercial": it.commercial.model_copy(
                    update={"code_license": lic, "evidence": [hf, off]}
                )
            }
        )
        for it in issue_w44.items
    ]
    out = render_web_issue(issue_w44.model_copy(update={"items": items}))
    ev = [a["href"] for a, _ in _anchors(out) if "data-evidence" in a]
    assert len(ev) == len(items) * 2  # one license link + one evidence link per card
    assert all(h.startswith(("https://huggingface.co/", "https://github.com/")) for h in ev)
    assert "example.com" not in out


def test_reason_text_is_escaped(issue_w44):
    items = [
        it.model_copy(
            update={"commercial": it.commercial.model_copy(update={"reason_ko": "<b>x</b>"})}
        )
        for it in issue_w44.items
    ]
    out = render_web_issue(issue_w44.model_copy(update={"items": items}))
    assert "<b>x</b>" not in out
    assert "&lt;b&gt;x&lt;/b&gt;" in out
