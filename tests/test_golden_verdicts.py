"""EVID-05 golden set: 15 known papers/models through the real enrich verdict path.

Each case in golden_verdicts.json holds a live-captured HF model subset, a GitHub
license record and the paper flags. The test only turns those into the HF/GitHub
API answers that enrich reads, runs enrich and then verdicts.finalize, and compares
the stored verdicts. No rule logic lives here.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from conftest import mock_enrich

from newsletter.schema import UNKNOWN, CommercialUse, Hardware, Item, ModelInfo, PocReadiness
from newsletter.stages import enrich, verdicts

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "golden_verdicts.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(enrich, "RETRY_WAIT_MULTIPLIER", 0)


def _paper_id(case: dict, i: int) -> str:
    return case["paper_id"] or f"2699.{i:05d}"


def _paper_json(case: dict, pid: str) -> dict:
    flags = case["paper"]
    paper: dict = {"id": pid, "linkedModels": [], "linkedDatasets": [], "linkedSpaces": []}
    if flags["has_weights"]:
        gated = (case["model"] or {}).get("gated", False)
        paper["linkedModels"] = [
            {"id": case["model_id"], "gated": gated, "private": False, "downloads": 1}
        ]
    if flags["has_demo"] and flags["space_id"]:
        paper["linkedSpaces"] = [{"id": flags["space_id"]}]
    if flags["github_url"]:
        paper["githubRepo"] = flags["github_url"]
    return paper


def _github_answer(record: dict | None) -> dict | None:
    """The API answer that github_license() parses back into `record`."""
    if record is None:
        return None
    if record["status"] == "none":
        return {"status_code": 404, "body": {}}
    assert record["status"] == "ok"
    return {
        "status_code": 200,
        "body": {
            "license": {"spdx_id": record["spdx_id"], "name": record["name"]},
            "html_url": record["html_url"],
        },
    }


def _repo_key(url: str | None) -> str | None:
    repo = enrich.parse_repo(url)
    return "/".join(repo) if repo else None


def _run_case(i: int, case: dict, base: Item) -> Item:
    pid = _paper_id(case, i)
    flags = case["paper"]
    item = base.model_copy(
        update={
            "rank": 1,
            "paper_id": pid,
            "hf_url": f"https://huggingface.co/papers/{pid}",
            "github_url": flags["github_url"],
        }
    )
    models = {}
    if case["model"] is not None:
        models[case["model_id"]] = {"id": case["model_id"], **case["model"]}
    licenses = {}
    answer = _github_answer(case["github"])
    if answer is not None:
        licenses[_repo_key(flags["github_url"])] = answer
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        routes = mock_enrich(
            router, papers={pid: _paper_json(case, pid)}, models=models, github_licenses=licenses
        )
        (out,) = enrich.enrich_items([item], [])
    assert routes["papers"].call_count == 1
    assert routes["github_api"].call_count == (1 if flags["github_url"] else 0)
    (final,) = verdicts.finalize([out])
    return final


@pytest.fixture
def base(issue_w44) -> Item:
    """A W44 item with every code-owned fact and verdict at its default."""
    it = issue_w44.items[0]
    info = ModelInfo(kind_ko=it.model_info.kind_ko, architecture_ko=it.model_info.architecture_ko)
    return it.model_copy(
        update={
            "model_info": info,
            "image": None,
            "commercial": CommercialUse(),
            "poc": PocReadiness(),
            "hardware": Hardware(),
            "project_url": None,
        }
    )


@pytest.mark.parametrize(("i", "case"), list(enumerate(GOLDEN)), ids=[c["id"] for c in GOLDEN])
def test_golden_case(i, case, base):
    out = _run_case(i, case, base)
    exp = case["expect"]
    assert out.commercial.verdict == exp["commercial"]
    assert out.poc.verdict == exp["poc"]
    assert out.hardware.local_run == exp["local_run"]
    assert out.hardware.est_vram_gb == exp["est_vram_gb"]
    # Every positive verdict that survived finalize carries HF/GitHub evidence.
    if out.commercial.verdict in verdicts.COMMERCIAL_POSITIVE:
        assert out.commercial.evidence
    if out.poc.verdict in verdicts.POC_POSITIVE:
        assert out.poc.evidence
    if out.hardware.local_run in verdicts.LOCAL_RUN_POSITIVE:
        assert out.hardware.evidence


def _case(cid: str) -> tuple[int, dict]:
    return next((i, c) for i, c in enumerate(GOLDEN) if c["id"] == cid)


def test_gated_weights_cite_the_gated_label(base):
    for cid in ("G1", "G6"):
        out = _run_case(*_case(cid), base)
        assert [e.label for e in out.poc.evidence] == [verdicts.POC_GATED_LABEL], cid


def test_named_cases(base):
    g1 = _run_case(*_case("G1"), base)
    assert (g1.commercial.verdict, g1.hardware.est_vram_gb) == ("조건부", 19.3)
    g6 = _run_case(*_case("G6"), base)
    assert (g6.commercial.verdict, g6.hardware.local_run) == ("불가", "제한적")
    # Relative license_link resolved on huggingface.co.
    assert g6.commercial.evidence[0].url == (
        "https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md"
    )
    g10 = _run_case(*_case("G10"), base)
    assert (g10.commercial.verdict, g10.hardware.local_run) == ("조건부", UNKNOWN)
    assert g10.hardware.param_count == 6739777536
    g15 = _run_case(*_case("G15"), base)
    assert (g15.commercial.verdict, g15.poc.verdict) == (UNKNOWN, "논문만")
    assert [e.url for e in g15.poc.evidence] == ["https://huggingface.co/papers/2610.37381"]


def test_golden_set_covers_every_commercial_outcome():
    seen = {c["expect"]["commercial"] for c in GOLDEN}
    assert {"가능", "조건부", "확인 필요", "불가"} <= seen
    assert len(GOLDEN) == 15
    assert len({c["id"] for c in GOLDEN}) == 15


def test_github_answers_round_trip():
    """The synthetic API answer parses back to the captured record."""
    from newsletter.stages import licenses

    for case in GOLDEN:
        answer = _github_answer(case["github"])
        if answer is None:
            continue
        with respx.mock(assert_all_mocked=True) as router:
            router.get(url__regex=r"^https://api\.github\.com/").mock(
                return_value=httpx.Response(answer["status_code"], json=answer["body"])
            )
            with httpx.Client() as client:
                got = licenses.github_license(client, "o", "r")
        assert got == case["github"], case["id"]
