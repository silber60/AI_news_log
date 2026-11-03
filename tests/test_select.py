"""Star Top N with upvote fill (COLL-05, D-02, D-03) and the selected.json snapshot (COLL-03)."""

import json
from pathlib import Path

import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter.schema import HfEntry
from newsletter.stages.select import select_top, sort_key, star_key

TIE = Path(__file__).parent / "fixtures" / "hf_tie_sample.json"


def _entry(pid: str, upvotes: int, comments: int, day: str = "2026-10-27") -> HfEntry:
    return HfEntry.model_validate(
        {
            "paper": {
                "id": pid,
                "title": f"Paper {pid}",
                "upvotes": upvotes,
                "submittedOnDailyAt": f"{day}T00:00:00.000Z",
            },
            "numComments": comments,
        }
    )


def _ids(entries: list[HfEntry]) -> list[str]:
    return [e.paper.id for e in entries]


def test_tie_sample_fill_breaks_on_num_comments():
    entries = [HfEntry.model_validate(d) for d in json.loads(TIE.read_text(encoding="utf-8"))]
    # The one repo paper leads; the upvote fill breaks the 95-upvote tie on comments.
    assert _ids(select_top(entries)) == ["2610.35684", "2610.37381", "2610.37230"]
    # The upvote key on its own keeps the old order.
    assert _ids(sorted(entries, key=sort_key)) == [
        "2610.37381",
        "2610.35684",
        "2610.37230",
        "2610.34662",
    ]


def test_fill_equal_upvotes_and_comments_prefer_earlier_submission():
    late = _entry("b", 5, 3, "2026-10-29")
    early = _entry("z", 5, 3, "2026-10-26")
    assert _ids(select_top([late, early])) == ["z", "b"]


def test_fill_full_tie_orders_by_paper_id():
    entries = [_entry(pid, 5, 3) for pid in ("2610.3", "2610.1", "2610.2")]
    assert _ids(select_top(entries)) == ["2610.1", "2610.2", "2610.3"]
    assert _ids(select_top(entries[::-1])) == ["2610.1", "2610.2", "2610.3"]


def test_fill_no_repo_papers_give_three_by_upvotes():
    top = select_top([_entry(f"{i:02d}", i, 0) for i in range(25)])
    assert _ids(top) == ["24", "23", "22"]


def test_fill_zero_upvotes_is_eligible():
    assert _ids(select_top([_entry("only", 0, 0)])) == ["only"]


def test_selected_json_snapshot_lists_ranks_in_star_order(hf_pages, archive_tmp):
    from newsletter.pipeline import run_build

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        mock_hf_week(router, hf_pages, "2026-W44")
        run_build("2026-W44", claude_client=FakeAnthropic())

    path = archive_tmp / "archive" / "2026-W44" / "selected.json"
    selected = json.loads(path.read_text(encoding="utf-8"))
    items = selected["items"]
    assert selected["count"] == len(items) == 10
    assert [s["rank"] for s in items] == list(range(1, 11))

    entries = [HfEntry.model_validate(d) for page in hf_pages for d in page]
    expected = select_top(entries)
    assert [s["paper_id"] for s in items] == _ids(expected)
    assert items[0]["paper_id"] == "2610.35518"
    assert [s["upvotes"] for s in items] == [e.paper.upvotes for e in expected]
    assert [s["numComments"] for s in items] == [e.numComments for e in expected]
    assert [s["github_stars"] for s in items] == [e.paper.githubStars for e in expected]
    assert items[0]["github_stars"] == 5221
    assert [s["basis"] for s in items] == ["stars"] * 10
    assert [star_key(e) for e in expected] == sorted(star_key(e) for e in expected)
    stars = [s["github_stars"] for s in items]
    assert stars == sorted(stars, reverse=True)
