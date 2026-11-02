"""Frozen Issue v1 contract: validators and committed JSON-schema snapshot."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from newsletter.schema import Explainer, HfEntry, Issue, Item

SNAPSHOT = Path(__file__).resolve().parent.parent / "schema" / "issue.schema.v1.json"
FIXTURE = Path(__file__).parent / "fixtures" / "issue_w44.json"


def _issue_data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _item_data(rank: int = 1, **update) -> dict:
    data = dict(_issue_data()["items"][0])
    data.update(rank=rank, paper_id=f"2610.{rank:05d}", **update)
    return data


def _issue_with(n_items: int = 5, **update) -> dict:
    data = _issue_data()
    data["items"] = [_item_data(r) for r in range(1, n_items + 1)]
    data.update(update)
    return data


def test_fixture_issue_validates_with_phase1_defaults(issue_w44):
    assert issue_w44.schema_version == 1
    assert issue_w44.explainer is None
    assert issue_w44.highlights == []
    assert issue_w44.trend_ko is None
    assert len(issue_w44.items) == 10
    for it in issue_w44.items:
        assert it.commercial.verdict == "확인 필요"
        assert it.poc.verdict == "확인 필요"
        assert it.claude_gpt.verdict == "확인 필요"
        assert it.hardware.local_run == "확인 필요"


def test_ai_type_outside_requirements_enum_rejected():
    with pytest.raises(ValidationError):
        Item.model_validate(_item_data(ai_type="로보틱스"))


def test_commercial_verdict_outside_requirements_enum_rejected():
    with pytest.raises(ValidationError):
        Item.model_validate(_item_data(commercial={"verdict": "제한적"}))


def test_local_run_labels_confirmed_by_owner():
    for label in ("가능", "제한적", "불가", "확인 필요"):
        Item.model_validate(_item_data(hardware={"local_run": label}))
    with pytest.raises(ValidationError):
        Item.model_validate(_item_data(hardware={"local_run": "부분 가능"}))


def test_three_ideas_rejected_zero_accepted():
    with pytest.raises(ValidationError):
        Item.model_validate(_item_data(use_ideas_ko=["a", "b", "c"]))
    assert Item.model_validate(_item_data(use_ideas_ko=[])).use_ideas_ko == []


def test_non_contiguous_ranks_rejected():
    data = _issue_with(0)
    data["items"] = [_item_data(1), _item_data(3)]
    with pytest.raises(ValidationError):
        Issue.model_validate(data)


def test_zero_items_rejected():
    with pytest.raises(ValidationError):
        Issue.model_validate(_issue_with(0))


def test_eleven_items_rejected():
    with pytest.raises(ValidationError):
        Issue.model_validate(_issue_with(11))


def test_duplicate_paper_id_rejected():
    data = _issue_with(2)
    data["items"][1]["paper_id"] = data["items"][0]["paper_id"]
    with pytest.raises(ValidationError):
        Issue.model_validate(data)


def _highlight(rank: int) -> dict:
    return {"rank": rank, "tag": "둘 다", "why_ko": "이유", "how_ko": "방법"}


def test_highlight_rank_must_reference_item():
    with pytest.raises(ValidationError):
        Issue.model_validate(_issue_with(5, highlights=[_highlight(7)]))


def test_more_than_three_highlights_rejected():
    with pytest.raises(ValidationError):
        Issue.model_validate(_issue_with(5, highlights=[_highlight(r) for r in (1, 2, 3, 4)]))


def test_explainer_slot_validates_related_ranks():
    bad = {"topic": "MoE", "body_ko": "설명", "related_ranks": [99]}
    with pytest.raises(ValidationError):
        Issue.model_validate(_issue_with(5, explainer=bad))
    good = {"topic": "MoE", "body_ko": "설명", "related_ranks": [1]}
    issue = Issue.model_validate(_issue_with(5, explainer=good))
    assert issue.explainer == Explainer(**good)


@pytest.mark.parametrize("url", ["http://x", "javascript:alert(1)"])
def test_non_https_link_rejected(url):
    with pytest.raises(ValidationError):
        Item.model_validate(_item_data(github_url=url))


def test_https_link_accepted():
    item = Item.model_validate(_item_data(github_url="https://github.com/a/b"))
    assert item.github_url == "https://github.com/a/b"


def test_unknown_key_on_item_rejected():
    with pytest.raises(ValidationError):
        Item.model_validate(_item_data(surprise="x"))


def test_unknown_key_on_hf_entry_ignored():
    entry = HfEntry.model_validate(
        {
            "paper": {
                "id": "2610.00001",
                "title": "T",
                "submittedOnDailyAt": "2026-10-27T00:00:00.000Z",
                "authors": [{"name": "someone"}],
            },
            "numComments": 1,
            "submittedBy": {"user": "someone"},
        }
    )
    assert entry.paper.id == "2610.00001"
    assert not hasattr(entry, "submittedBy")


def test_schema_snapshot_matches():
    assert SNAPSHOT.is_file(), f"missing {SNAPSHOT}"
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert Issue.model_json_schema() == committed, (
        "Issue schema drifted from schema/issue.schema.v1.json. The v1 contract is frozen: "
        "change it only in a planned phase and bump schema_version (new snapshot file). "
        "Do not regenerate this snapshot silently."
    )
