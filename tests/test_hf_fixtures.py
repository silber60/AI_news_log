"""Shape and privacy guards for the trimmed W44 HF paper/model captures."""

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

TOP10 = {
    "2610.37381",
    "2610.35684",
    "2610.32749",
    "2610.36729",
    "2610.35845",
    "2610.36671",
    "2610.37230",
    "2610.34662",
    "2610.36068",
    "2610.34283",
}
RANK1 = "2610.37381"
FORBIDDEN_KEYS = {"authors", "avatarUrl", "submittedBy", "user", "fullname"}


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_papers_fixture_has_exactly_top10():
    papers = _load("hf_papers_w44.json")
    assert set(papers) == TOP10
    assert all(papers[pid]["id"] == pid for pid in papers)


def test_every_public_linked_model_is_captured():
    papers = _load("hf_papers_w44.json")
    models = _load("hf_models_w44.json")
    linked = {
        m["id"]
        for p in papers.values()
        for m in p.get("linkedModels", [])
        if m.get("private") is False
    }
    assert linked
    assert linked <= set(models)
    assert all(models[mid]["id"] == mid for mid in models)


def test_captures_carry_no_author_or_user_data():
    for name in ("hf_papers_w44.json", "hf_models_w44.json"):
        found = FORBIDDEN_KEYS & set(_keys(_load(name)))
        assert not found, f"{name}: {sorted(found)}"


def test_rank1_page_entry_has_cdn_media_url():
    entries = [e for i in range(3) for e in _load(f"hf_w44_p{i}.json")]
    rank1 = [e for e in entries if e["paper"]["id"] == RANK1]
    assert len(rank1) == 1
    media = rank1[0]["paper"]["mediaUrls"]
    assert isinstance(media, list) and media
    assert media[0].startswith("https://cdn-uploads.huggingface.co/")
