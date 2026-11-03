"""Code-owned 상업적 사용 rules and the GitHub license read (EVID-01/02/05, D-03, D-09)."""

import httpx
import pytest
import respx

from newsletter.schema import LicenseInfo
from newsletter.stages import enrich, licenses

TOKEN = "ghs_testtoken"
XTUNER_URL = "https://api.github.com/repos/InternLM/xtuner/license"
XTUNER_HTML = "https://github.com/InternLM/xtuner/blob/main/LICENSE"
XTUNER_BODY = {
    "license": {"key": "apache-2.0", "name": "Apache License 2.0", "spdx_id": "Apache-2.0"},
    "html_url": XTUNER_HTML,
}


def _call(status: int = 200, body: dict | None = None, **kw) -> tuple[dict, respx.Route]:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(XTUNER_URL).mock(
            return_value=httpx.Response(status, json=body if body is not None else {}), **kw
        )
        with httpx.Client() as client:
            rec = licenses.github_license(client, "InternLM", "xtuner")
    return rec, route


def test_timeout_matches_enrich():
    assert licenses.TIMEOUT == enrich.TIMEOUT


def test_xtuner_apache_gives_code_side_possible(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    rec, _ = _call(200, XTUNER_BODY)
    assert rec == {
        "status": "ok",
        "spdx_id": "Apache-2.0",
        "name": "Apache License 2.0",
        "html_url": XTUNER_HTML,
    }
    code = licenses.code_license(rec)
    assert code[1] == "가능"
    use = licenses.commercial_use(code, None)
    assert use.verdict == "가능"
    assert use.code_license.spdx_id == "Apache-2.0"
    assert use.weights_license is None
    assert use.evidence[0].url == XTUNER_HTML
    assert use.evidence[0].label == "코드 라이선스"
    assert use.reason_ko is None


def test_token_only_in_authorization_header(monkeypatch, caplog):
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    with caplog.at_level("DEBUG"):
        _, route = _call(200, XTUNER_BODY)
    req = route.calls.last.request
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"
    assert req.headers["Accept"] == "application/vnd.github+json"
    assert req.headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert TOKEN not in str(req.url)
    assert TOKEN not in caplog.text

    monkeypatch.delenv("GITHUB_TOKEN")
    _, route = _call(200, XTUNER_BODY)
    assert "Authorization" not in route.calls.last.request.headers


def test_empty_token_sends_no_header(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "")
    _, route = _call(200, XTUNER_BODY)
    assert "Authorization" not in route.calls.last.request.headers


@pytest.mark.parametrize(
    ("status", "expected"),
    [(404, "none"), (403, "http_403"), (429, "http_429"), (301, "http_301"), (500, "http_500")],
)
def test_non_200_gives_unknown_and_never_raises(monkeypatch, caplog, status, expected):
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    with caplog.at_level("INFO"):
        rec, _ = _call(status, {"message": "x"})
    assert rec["status"] == expected
    info, verdict = licenses.code_license(rec)
    assert verdict == "확인 필요"
    assert info == LicenseInfo()
    assert f"reason={expected}" in caplog.text
    assert TOKEN not in caplog.text
    # Our own lines carry the reason code only, never the repo id.
    ours = [r.getMessage() for r in caplog.records if r.name == licenses.__name__]
    assert ours and not any("xtuner" in m or "InternLM" in m for m in ours)


def test_transport_error_gives_unknown(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    rec, _ = _call(side_effect=httpx.ConnectTimeout("boom"))
    assert rec["status"] == "error_ConnectTimeout"
    assert licenses.code_license(rec)[1] == "확인 필요"


def test_bad_json_gives_unknown(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with respx.mock() as router:
        router.get(XTUNER_URL).mock(return_value=httpx.Response(200, text="not json"))
        with httpx.Client() as client:
            rec = licenses.github_license(client, "InternLM", "xtuner")
    assert rec["status"].startswith("error_")
    assert licenses.code_license(rec)[1] == "확인 필요"


def test_noassertion_gives_unknown_but_keeps_link():
    rec = {
        "status": "ok",
        "spdx_id": "NOASSERTION",
        "name": "Other",
        "html_url": "https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/main/LICENSE",
    }
    info, verdict = licenses.code_license(rec)
    assert verdict == "확인 필요"
    assert info.spdx_id is None
    assert info.name == "Other"


def test_off_host_html_url_dropped(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    body = dict(XTUNER_BODY, html_url="https://evil.example/LICENSE")
    rec, _ = _call(200, body)
    assert rec["html_url"] is None
    use = licenses.commercial_use(licenses.code_license(rec), None)
    assert use.evidence == []


def test_no_redirect_follow(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with respx.mock(assert_all_called=False) as router:
        router.get(XTUNER_URL).mock(
            return_value=httpx.Response(301, headers={"Location": "https://api.github.com/x"})
        )
        other = router.get("https://api.github.com/x").mock(
            return_value=httpx.Response(200, json=XTUNER_BODY)
        )
        with httpx.Client() as client:
            rec = licenses.github_license(client, "InternLM", "xtuner")
    assert rec["status"] == "http_301"
    assert not other.called
