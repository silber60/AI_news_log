"""Frozen Issue v3 contract: validators and committed JSON-schema snapshot."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from newsletter.schema import UNKNOWN, Explainer, HfEntry, Issue, Item, ItemImage, ModelInfo

SNAPSHOT = Path(__file__).resolve().parent.parent / "schema" / "issue.schema.v4.json"
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
    assert issue_w44.schema_version == 4
    assert issue_w44.headline_ko
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


@pytest.mark.parametrize("lines", [["a", "b"], ["a", "b", "c", "d"], ["a", " ", "c"]])
def test_summary_lines_need_exactly_three_non_empty(lines):
    with pytest.raises(ValidationError):
        Item.model_validate(_item_data(summary_lines_ko=lines))


def test_three_summary_lines_accepted():
    item = Item.model_validate(_item_data(summary_lines_ko=["a", "b", "c"]))
    assert item.summary_lines_ko == ["a", "b", "c"]


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn-uploads.huggingface.co/x.png",
        "javascript:alert(1)",
        "https://example.com/x.png",
        "https://cdn-uploads.huggingface.co.evil.com/x.png",
        "https://raw.githubusercontent.com.evil.com/x.png",
        "http://raw.githubusercontent.com/a/b/main/x.png",
        "https://github.com/user-attachments/assets/abc",
        "https://huggingface.co/a/b/resolve/main/x.png",
        "https://cdn-uploads.huggingface.co/x.png?w=1",
        "https://raw.githubusercontent.com/a/b/main/x.png#top",
        "https://raw.githubusercontent.com/" + "a" * 263 + ".png",  # 301 chars
    ],
)
def test_item_image_rejects_other_schemes_and_hosts(url):
    with pytest.raises(ValidationError):
        ItemImage(url=url, width=576, height=234)


def test_item_image_accepts_raw_github_host_up_to_300_chars():
    url = "https://raw.githubusercontent.com/a/b/main/docs/teaser.png"
    assert ItemImage(url=url, width=576, height=234).url == url
    long_url = "https://raw.githubusercontent.com/" + "a" * 262 + ".pn"
    assert len(long_url) == 299
    assert ItemImage(url=long_url + "g", width=576, height=234).url == long_url + "g"
    with pytest.raises(ValidationError):
        ItemImage(url=long_url + "gg", width=576, height=234)  # 301 chars


def test_item_without_use_idea_rejected():
    data = _item_data()
    del data["use_idea_ko"]
    with pytest.raises(ValidationError):
        Item.model_validate(data)


def test_item_github_stars_defaults_to_none():
    data = _item_data()
    del data["github_stars"]
    assert Item.model_validate(data).github_stars is None
    assert Item.model_validate(_item_data(github_stars=5221)).github_stars == 5221


def test_item_image_needs_positive_size():
    url = "https://cdn-uploads.huggingface.co/x.png"
    assert ItemImage(url=url, width=576, height=234).width == 576
    with pytest.raises(ValidationError):
        ItemImage(url=url, width=0, height=234)


def test_model_info_facts_default_to_unknown():
    info = ModelInfo(kind_ko="VLA 모델", architecture_ko=UNKNOWN)
    assert UNKNOWN == "확인 필요"
    assert (info.size, info.training_data, info.release) == (UNKNOWN, UNKNOWN, UNKNOWN)
    assert info.evidence == []


def test_v1_ideas_key_rejected():
    with pytest.raises(ValidationError):
        Item.model_validate(_item_data(use_ideas_ko=["a"]))


@pytest.mark.parametrize("version", [1, 2, 3])
def test_older_issue_versions_rejected(version):
    data = _issue_data()
    data["schema_version"] = version
    with pytest.raises(ValidationError):
        Issue.model_validate(data)


def test_issue_requires_headline():
    data = _issue_data()
    del data["headline_ko"]
    with pytest.raises(ValidationError):
        Issue.model_validate(data)


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


def test_explainer_accepts_point_example_and_image():
    img = {"url": "https://cdn-uploads.huggingface.co/x.png", "width": 576, "height": 220}
    full = {
        "topic": "VLA",
        "body_ko": "설명",
        "related_ranks": [1],
        "point_ko": "포인트",
        "example_ko": "예시",
        "image": img,
    }
    issue = Issue.model_validate(_issue_with(5, explainer=full))
    assert issue.explainer.point_ko == "포인트"
    assert issue.explainer.example_ko == "예시"
    assert issue.explainer.image == ItemImage(**img)
    plain = Explainer(topic="VLA", body_ko="설명", related_ranks=[1])
    assert (plain.point_ko, plain.example_ko, plain.image) == (None, None, None)
    bad = {**full, "image": {**img, "url": "https://example.com/x.png"}}
    with pytest.raises(ValidationError):
        Issue.model_validate(_issue_with(5, explainer=bad))


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
        "Issue schema drifted from schema/issue.schema.v4.json. The v4 contract is frozen: "
        "change it only in a planned phase and bump schema_version (new snapshot file). "
        "Do not regenerate this snapshot silently."
    )
