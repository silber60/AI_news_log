"""Code verdicts (EVID-03..05): PoC table, VRAM rules, evidence enforcement."""

import pytest

from newsletter.schema import UNKNOWN, EvidenceLink, Item
from newsletter.stages import verdicts
from newsletter.stages.verdicts import POC_GATED_LABEL


@pytest.fixture
def item(issue_w44) -> Item:
    """W44 rank 1 with a repo, every verdict at its default."""
    return issue_w44.items[0].model_copy(update={"github_url": "https://github.com/acme/repo"})


def _f(**kw) -> dict:
    base = {
        "has_weights": False,
        "has_code": False,
        "has_demo": False,
        "spaces": [],
        "gated": False,
        "model_id": None,
    }
    base.update(kw)
    return base


# ------------------------------------------------------------------------ PoC


def test_poc_demo_gives_ready_with_space_evidence(item):
    out = verdicts.poc(item, _f(has_demo=True, spaces=["org/demo"]))
    assert out.verdict == "바로 가능"
    assert [(e.label, e.url) for e in out.evidence] == [
        ("HF 데모", "https://huggingface.co/spaces/org/demo")
    ]


def test_poc_demo_outranks_weights(item):
    f = _f(has_demo=True, spaces=["org/demo"], has_weights=True, model_id="org/m", has_code=True)
    out = verdicts.poc(item, f)
    assert out.evidence[0].label == "HF 데모"


def test_poc_open_weights_cite_model_page(item):
    out = verdicts.poc(item, _f(has_weights=True, model_id="org/m", has_code=True))
    assert out.verdict == "바로 가능"
    assert [(e.label, e.url) for e in out.evidence] == [("HF 모델", "https://huggingface.co/org/m")]


def test_poc_gated_weights_use_gated_label(item):
    out = verdicts.poc(item, _f(has_weights=True, gated=True, model_id="org/m"))
    assert out.verdict == "바로 가능"
    assert out.evidence[0].label == POC_GATED_LABEL
    assert out.evidence[0].url == "https://huggingface.co/org/m"


def test_poc_code_only_cites_repo(item):
    out = verdicts.poc(item, _f(has_code=True))
    assert out.verdict == "코드만"
    assert [(e.label, e.url) for e in out.evidence] == [("GitHub", "https://github.com/acme/repo")]


def test_poc_code_only_without_github_url_has_no_evidence(item):
    out = verdicts.poc(item.model_copy(update={"github_url": None}), _f(has_code=True))
    assert out.verdict == "코드만"
    assert out.evidence == []


def test_poc_paper_only_cites_hf_paper(item):
    out = verdicts.poc(item, _f())
    assert out.verdict == "논문만"
    assert [(e.label, e.url) for e in out.evidence] == [("논문", item.hf_url)]


def test_poc_keeps_has_flags_never_false(item):
    flagged = item.model_copy(update={"poc": item.poc.model_copy(update={"has_code": True})})
    out = verdicts.poc(flagged, _f(has_code=True))
    assert (out.has_weights, out.has_code, out.has_demo) == (None, True, None)
    out = verdicts.poc(item, _f())
    assert (out.has_weights, out.has_code, out.has_demo) == (None, None, None)


# -------------------------------------------------------- evidence enforcement


def _with_poc(item: Item, verdict: str, evidence: list[EvidenceLink]) -> Item:
    return item.model_copy(
        update={"poc": item.poc.model_copy(update={"verdict": verdict, "evidence": evidence})}
    )


@pytest.mark.parametrize("verdict", ["바로 가능", "코드만"])
def test_enforce_evidence_drops_poc_without_evidence(item, verdict):
    out = verdicts.enforce_evidence(_with_poc(item, verdict, []))
    assert out.poc.verdict == UNKNOWN


def test_enforce_evidence_drops_poc_off_allowed_hosts(item):
    ev = [EvidenceLink(label="GitHub", url="https://gitlab.com/acme/repo")]
    assert verdicts.enforce_evidence(_with_poc(item, "코드만", ev)).poc.verdict == UNKNOWN


def test_enforce_evidence_keeps_backed_poc_and_negatives(item):
    ev = [EvidenceLink(label="GitHub", url="https://github.com/acme/repo")]
    assert verdicts.enforce_evidence(_with_poc(item, "코드만", ev)).poc.verdict == "코드만"
    assert verdicts.enforce_evidence(_with_poc(item, "논문만", [])).poc.verdict == "논문만"


def test_finalize_maps_every_item(issue_w44):
    items = [_with_poc(it, "바로 가능", []) for it in issue_w44.items]
    assert all(it.poc.verdict == UNKNOWN for it in verdicts.finalize(items))
