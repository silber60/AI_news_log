"""Shape and privacy guards for the trimmed W44 HF paper/model captures."""

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The old upvote Top 10 (unit tests) plus the star Top 10 (D-02, run_build).
UPVOTE_TOP10 = {
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
STAR_TOP10 = {
    "2610.35518",
    "2610.40599",
    "2610.36729",
    "2610.31635",
    "2610.30006",
    "2610.32253",
    "2610.33106",
    "2610.14018",
    "2610.33005",
    "2610.33845",
}
TOP10 = UPVOTE_TOP10 | STAR_TOP10
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}")
RETINA_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def _emails(text: str) -> list[str]:
    """Email-shaped strings, except retina image names such as x@2x.png."""
    return [m for m in EMAIL_RE.findall(text) if not m.lower().endswith(RETINA_EXTS)]


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


def test_papers_fixture_has_exactly_both_top10s():
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


def test_readme_capture_holds_image_lines_only():
    text = (FIXTURES / "readme_w44.json").read_text(encoding="utf-8")
    assert _emails(text) == []
    assert "avatars.githubusercontent" not in text
    data = json.loads(text)
    assert set(data["readmes"]) == {
        p["githubRepo"].removeprefix("https://github.com/")
        for pid, p in _load("hf_papers_w44.json").items()
        if pid in STAR_TOP10
    }
    for body in data["readmes"].values():
        for line in body.splitlines():
            assert line.startswith(("<img ", "![img]("))
            assert 'alt="img"' in line or line.startswith("![img](")
    for meta in data["images"].values():
        assert set(meta) == {"status", "content_type", "width", "height", "total_bytes"}


def test_email_guard_allows_retina_names():
    assert _emails("assets/x@2x.png") == []
    assert _emails("mail someone@example.com") == ["someone@example.com"]


# Research §1 live probe: where each W44 model states its license (D-15 recapture).
CARD_LICENSES = {
    "JusperLee/Falcon": "apache-2.0",
    "JusperLee/Falcon-Big": "apache-2.0",
    "tencent/Hy-Nomas": "apache-2.0",
    "hyz317/HairDeck": "apache-2.0",
    "liamdugan/detector-scope": "gemma",
    "liamdugan/detector-scope-peer-review-gpt4o": "gemma",
    "liamdugan/detector-scope-peer-review-llama": "gemma",
}
CARD_KEYS = {"datasets", "license", "license_name", "license_link"}
MODEL_KEYS = {"id", "cardData", "gated", "tags", "safetensors"}


def test_model_capture_carries_license_fields():
    models = _load("hf_models_w44.json")
    for mid, lic in CARD_LICENSES.items():
        assert models[mid]["cardData"]["license"] == lic, mid
        assert f"license:{lic}" in models[mid]["tags"], mid
    assert models["tencent/Hy-Nomas"]["cardData"]["license_link"] == (
        "https://huggingface.co/tencent/Hy-Nomas/blob/main/LICENSE"
    )
    for mid in ("liamdugan/detector-scope", "liamdugan/detector-scope-peer-review-llama"):
        assert models[mid]["safetensors"] == {"parameters": {"F32": 302130176}, "total": 302130176}
    for m in models.values():
        assert set(m) <= MODEL_KEYS
        assert set(m["cardData"]) <= CARD_KEYS
