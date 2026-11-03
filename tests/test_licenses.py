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


# ------------------------------------------------------------ table and lookup

PERMISSIVE = (
    "apache-2.0 mit mit-0 bsd bsd-2-clause bsd-3-clause bsd-3-clause-clear 0bsd isc zlib"
    " bsl-1.0 unlicense cc0-1.0 cc-by-2.0 cc-by-2.5 cc-by-3.0 cc-by-4.0 postgresql ncsa"
    " wtfpl afl-3.0 ecl-2.0 ms-pl artistic-2.0 upl-1.0 odc-by pddl cdla-permissive-1.0"
    " cdla-permissive-2.0"
).split()
COPYLEFT = (
    "mpl-2.0 lgpl lgpl-2.1 lgpl-3.0 lgpl-lr gpl gpl-2.0 gpl-3.0 agpl-3.0 epl-1.0 epl-2.0"
    " eupl-1.1 eupl-1.2 osl-3.0 cc-by-sa-3.0 cc-by-sa-4.0 cc-by-nd-4.0 cdla-sharing-1.0"
    " odbl gfdl lppl-1.3c ofl-1.1"
).split()
COMMUNITY = (
    "openrail openrail++ bigscience-openrail-m creativeml-openrail-m"
    " bigscience-bloom-rail-1.0 bigcode-openrail-m llama2 llama3 llama3.1 llama3.2 llama3.3"
    " llama4 gemma grok2-community openmdw-1.0 openmdw-1.1 apple-ascl c-uda"
).split()
NON_COMMERCIAL = (
    "cc-by-nc-2.0 cc-by-nc-3.0 cc-by-nc-4.0 cc-by-nc-nd-3.0 cc-by-nc-nd-4.0"
    " cc-by-nc-sa-2.0 cc-by-nc-sa-3.0 cc-by-nc-sa-4.0 fair-noncommercial-research-license"
    " deepfloyd-if-license intel-research h-research apple-amlr"
).split()
TABLE_ROWS = (
    [(k, "가능") for k in PERMISSIVE]
    + [(k, "조건부") for k in COPYLEFT + COMMUNITY]
    + [(k, "불가") for k in NON_COMMERCIAL]
)


@pytest.mark.parametrize(("key", "verdict"), TABLE_ROWS)
def test_table_row_maps_to_its_verdict(key, verdict):
    assert licenses.LICENSE_TABLE[key] == verdict
    assert licenses.lookup(key, None) == verdict


def test_table_holds_only_the_research_rows():
    assert set(licenses.LICENSE_TABLE) == {k for k, _ in TABLE_ROWS}


@pytest.mark.parametrize(
    ("value", "verdict"),
    [
        ("Apache-2.0", "가능"),
        ("MIT", "가능"),
        ("GPL-3.0-or-later", "조건부"),
        ("LGPL-2.1-only", "조건부"),
        (" BSD-3-Clause ", "가능"),
        ("CC-BY-NC-4.0", "불가"),
    ],
)
def test_lookup_casefolds_and_strips_suffix(value, verdict):
    assert licenses.lookup(value, None) == verdict


@pytest.mark.parametrize(
    ("name", "verdict"),
    [
        ("qwen", "조건부"),
        ("tongyi-qianwen", "조건부"),
        ("deepseek", "조건부"),
        ("deepseek-license", "조건부"),
        ("flux-1-dev-non-commercial-license", "불가"),
        ("qwen-research", "불가"),
        ("some-noncommercial-terms", "불가"),
        ("model-nc-license", "불가"),
        ("my-custom-license", "확인 필요"),
        (None, "확인 필요"),
        ("", "확인 필요"),
    ],
)
def test_lookup_other_uses_license_name(name, verdict):
    assert licenses.lookup("other", name) == verdict


@pytest.mark.parametrize(
    "value", ["cc", "unknown", "noassertion", "NOASSERTION", None, "", "zzz-1.0", 7]
)
def test_lookup_unknown_ids(value):
    assert licenses.lookup(value, None) == "확인 필요"


def test_lookup_list_takes_strictest():
    assert licenses.lookup(["apache-2.0", "llama3.1"], None) == "조건부"
    assert licenses.lookup(["apache-2.0", "cc-by-nc-4.0", "zzz"], None) == "불가"
    assert licenses.lookup(["apache-2.0", "zzz"], None) == "확인 필요"
    assert licenses.lookup([], None) == "확인 필요"


# ------------------------------------------------------------------ weights side

MID = "org/model"
PAGE = "https://huggingface.co/org/model"


def _model(card=None, tags=(), gated=False):
    return {
        "id": MID,
        "cardData": card if card is not None else {},
        "gated": gated,
        "tags": list(tags),
    }


def test_weights_card_license_first():
    info, v = licenses.weights_license(
        _model({"license": "apache-2.0"}, ["license:cc-by-nc-4.0"]), MID
    )
    assert v == "가능"
    assert info.spdx_id == "apache-2.0"
    assert info.name is None
    assert info.source_url == PAGE


def test_weights_other_uses_license_name_and_link():
    card = {
        "license": "other",
        "license_name": "qwen",
        "license_link": "https://huggingface.co/org/model/blob/main/LICENSE",
    }
    info, v = licenses.weights_license(_model(card, ["license:other"]), MID)
    assert v == "조건부"
    assert (info.spdx_id, info.name) == ("other", "qwen")
    assert info.source_url == "https://huggingface.co/org/model/blob/main/LICENSE"


def test_weights_tag_fallback_on_trimmed_card():
    info, v = licenses.weights_license(_model({}, ["diffusers", "license:apache-2.0"]), MID)
    assert v == "가능"
    assert info.spdx_id == "apache-2.0"


def test_weights_tag_other_uses_card_license_name():
    card = {"license_name": "flux-1-dev-non-commercial-license"}
    _, v = licenses.weights_license(_model(card, ["license:other"]), MID)
    assert v == "불가"


def test_weights_list_license():
    info, v = licenses.weights_license(_model({"license": ["mit", "gemma"]}), MID)
    assert v == "조건부"
    assert info.spdx_id == "mit, gemma"


def test_weights_missing_everything():
    info, v = licenses.weights_license(_model({}, ["safetensors"]), MID)
    assert v == "확인 필요"
    assert info.spdx_id is None
    assert info.source_url == PAGE
    info, v = licenses.weights_license(None, MID)
    assert v == "확인 필요"


@pytest.mark.parametrize("gated", ["manual", "auto", True])
def test_gated_moves_possible_to_conditional(gated):
    _, v = licenses.weights_license(_model({"license": "apache-2.0"}, gated=gated), MID)
    assert v == "조건부"


@pytest.mark.parametrize("gated", [False, None])
def test_not_gated_unchanged(gated):
    _, v = licenses.weights_license(_model({"license": "apache-2.0"}, gated=gated), MID)
    assert v == "가능"


def test_gated_never_loosens_non_commercial():
    _, v = licenses.weights_license(_model({"license": "cc-by-nc-4.0"}, gated="auto"), MID)
    assert v == "불가"


@pytest.mark.parametrize(
    "tag",
    [
        "base_model:finetune:meta-llama/Llama-3.1-8B",
        "base_model:adapter:google/gemma-2-2b",
        "base_model:meta-llama/Llama-2-7b-hf",
    ],
)
def test_base_model_guard(tag):
    _, v = licenses.weights_license(_model({"license": "mit"}, [tag]), MID)
    assert v == "조건부"


def test_base_model_guard_ignores_other_families():
    _, v = licenses.weights_license(
        _model({"license": "mit"}, ["base_model:finetune:Qwen/Qwen2.5-7B"]), MID
    )
    assert v == "가능"


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        (
            "https://huggingface.co/org/model/blob/main/LICENSE",
            "https://huggingface.co/org/model/blob/main/LICENSE",
        ),
        (
            "https://github.com/org/repo/blob/main/LICENSE",
            "https://github.com/org/repo/blob/main/LICENSE",
        ),
        ("LICENSE.md", "https://huggingface.co/org/model/blob/main/LICENSE.md"),
        ("./LICENSE", "https://huggingface.co/org/model/blob/main/LICENSE"),
        ("https://evil.example/LICENSE", PAGE),
        ("http://huggingface.co/org/model/LICENSE", PAGE),
        ("https://huggingface.co/org/model/LICENSE?x=1", PAGE),
        ("https://huggingface.co/org/model/LICENSE#a", PAGE),
        ("https://huggingface.co/org/../x/LICENSE", PAGE),
        ("../LICENSE", PAGE),
        ("javascript:alert(1)", PAGE),
        ("/abs/LICENSE", PAGE),
        ("LICENSE file.md", PAGE),
        ("https://huggingface.co.evil.example/x", PAGE),
        (None, PAGE),
        ("", PAGE),
    ],
)
def test_resolve_license_link(link, expected):
    assert licenses.resolve_license_link(link, MID) == expected


def test_resolve_license_link_bad_model_id():
    assert licenses.resolve_license_link(None, "../x") == "https://huggingface.co/models"


def test_repo_id_regex_matches_enrich():
    assert licenses.REPO_ID_RE.pattern == enrich.REPO_ID_RE.pattern


# --------------------------------------------------------------- stricter-of

CODE_URL = "https://github.com/o/r/blob/main/LICENSE"


def _side(verdict, url=None):
    return LicenseInfo(spdx_id="x", source_url=url), verdict


@pytest.mark.parametrize(
    ("code", "weights", "expected"),
    [
        ("가능", None, "가능"),
        (None, "가능", "가능"),
        ("가능", "조건부", "조건부"),
        ("확인 필요", "가능", "확인 필요"),  # Hy-Nomas: unreadable side caps it
        ("확인 필요", "불가", "불가"),
        ("불가", "가능", "불가"),
        ("조건부", "조건부", "조건부"),
        (None, None, "확인 필요"),
    ],
)
def test_commercial_stricter_of(code, weights, expected):
    c = _side(code, CODE_URL) if code else None
    w = _side(weights, PAGE) if weights else None
    use = licenses.commercial_use(c, w)
    assert use.verdict == expected
    assert use.reason_ko is None
    assert (use.code_license is None) == (code is None)
    assert (use.weights_license is None) == (weights is None)


def test_commercial_decisive_evidence_first():
    use = licenses.commercial_use(_side("조건부", CODE_URL), _side("가능", PAGE))
    assert [e.url for e in use.evidence] == [CODE_URL, PAGE]
    assert [e.label for e in use.evidence] == ["코드 라이선스", "가중치 라이선스"]
    use = licenses.commercial_use(_side("가능", CODE_URL), _side("가능", PAGE))
    assert [e.url for e in use.evidence] == [PAGE, CODE_URL]  # tie: weights side
    use = licenses.commercial_use(_side("가능", None), _side("조건부", PAGE))
    assert [e.url for e in use.evidence] == [PAGE]


def test_commercial_skips_sides_without_link():
    use = licenses.commercial_use(_side("확인 필요"), _side("가능", PAGE))
    assert use.verdict == "확인 필요"
    assert [e.url for e in use.evidence] == [PAGE]
