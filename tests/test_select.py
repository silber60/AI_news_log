"""Star Top N with upvote fill (COLL-05, D-02, D-03) and the selected.json snapshot (COLL-03)."""

import json
from pathlib import Path

import respx
from conftest import FakeAnthropic, mock_hf_week

from newsletter.schema import HfEntry, HfPaper
from newsletter.stages.select import STAR_MIN, has_repo, select_top, sort_key, star_key, stars

TIE = Path(__file__).parent / "fixtures" / "hf_tie_sample.json"


def _entry(
    pid: str,
    upvotes: int,
    comments: int,
    day: str = "2026-10-27",
    repo: str | None = None,
    stars: int | None = None,
) -> HfEntry:
    paper = {
        "id": pid,
        "title": f"Paper {pid}",
        "upvotes": upvotes,
        "submittedOnDailyAt": f"{day}T00:00:00.000Z",
    }
    if repo is not None:
        paper["githubRepo"] = repo
    if stars is not None:
        paper["githubStars"] = stars
    return HfEntry.model_validate({"paper": paper, "numComments": comments})


def _repo(pid: str, stars: int | None, upvotes: int = 1, comments: int = 0, **kw) -> HfEntry:
    return _entry(pid, upvotes, comments, repo=f"https://github.com/acme/{pid}", stars=stars, **kw)


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


# ------------------------------------------------- star rule edges (D-03, COLL-05)


def test_fill_zero_repos_among_25_gives_three_by_upvotes():
    entries = [_entry(f"p{i:02d}", i, i % 3) for i in range(25)]
    top = select_top(entries)
    assert _ids(top) == _ids(sorted(entries, key=sort_key)[:3]) == ["p24", "p23", "p22"]


def test_fill_two_low_star_repos_lead_then_top_upvote_paper():
    no_repo = [_entry(f"n{i:02d}", 100 + i, 0) for i in range(10)]
    entries = [*no_repo, _repo("zero", 0, upvotes=1), _repo("fifty", 50, upvotes=1)]
    top = select_top(entries)
    assert _ids(top) == ["fifty", "zero", "n09"]
    assert [stars(e) for e in top] == [50, 0, None]


def test_star_three_repos_below_min_give_those_three():
    entries = [_repo("a", 10), _repo("b", 99), _repo("c", 0), _entry("loud", 500, 9)]
    assert _ids(select_top(entries)) == ["b", "a", "c"]


def test_clamp_five_repos_at_min_give_five():
    high = [_repo(f"h{i}", STAR_MIN + i) for i in range(5)]
    low = [_repo(f"l{i:02d}", i) for i in range(20)]
    top = select_top([*low, *high])
    assert _ids(top) == ["h4", "h3", "h2", "h1", "h0"]


def test_clamp_exactly_star_min_counts():
    entries = [_repo(f"h{i}", 100) for i in range(4)] + [_repo("low", 99)]
    assert len(select_top(entries)) == 4
    assert "low" not in _ids(select_top(entries))


def test_clamp_seventeen_repos_at_min_give_top_ten_by_stars():
    entries = [_repo(f"s{i:02d}", 100 + 10 * i, upvotes=100 - i) for i in range(17)]
    top = select_top(entries)
    assert _ids(top) == [f"s{i:02d}" for i in range(16, 6, -1)]


def test_star_tie_breaks_on_upvotes_comments_day_then_id():
    entries = [
        _repo("e", 200, upvotes=5, comments=1, day="2026-10-27"),
        _repo("d", 200, upvotes=5, comments=1, day="2026-10-27"),
        _repo("c", 200, upvotes=5, comments=1, day="2026-10-26"),
        _repo("b", 200, upvotes=5, comments=2),
        _repo("a", 200, upvotes=6),
    ]
    assert _ids(select_top(entries)) == ["a", "b", "c", "d", "e"]
    assert _ids(sorted(entries, key=star_key)) == ["a", "b", "c", "d", "e"]


def test_repo_with_missing_stars_counts_and_sorts_after_zero_stars():
    missing = _repo("missing", None, upvotes=999)
    zero = _repo("zero", 0, upvotes=1)
    assert has_repo(missing) and stars(missing) is None
    top = select_top([missing, zero, _repo("one", 1), _entry("loud", 1000, 9)])
    assert _ids(top) == ["one", "zero", "missing"]


def test_star_negative_count_is_not_stars():
    neg = _repo("neg", -5)
    assert has_repo(neg) and stars(neg) is None
    assert _ids(select_top([neg, _repo("zero", 0), _repo("one", 1)])) == ["one", "zero", "neg"]


def test_star_bool_count_is_not_stars():
    # pydantic lax mode turns a JSON true into 1, so only a constructed entry carries a bool.
    paper = HfPaper.model_construct(
        id="flag",
        title="Paper flag",
        upvotes=1,
        submittedOnDailyAt=_entry("x", 0, 0).paper.submittedOnDailyAt,
        githubRepo="https://github.com/acme/flag",
        githubStars=True,
    )
    flag = HfEntry.model_construct(paper=paper, numComments=0, organization=None)
    assert stars(flag) is None
    assert _ids(select_top([flag, _repo("zero", 0), _repo("one", 1)])) == ["one", "zero", "flag"]


def test_repo_needs_https_url():
    plain = _entry("plain", 50, 0, repo="http://github.com/acme/plain", stars=9999)
    odd = _entry("odd", 40, 0, repo="github.com/acme/odd", stars=9999)
    assert not has_repo(plain) and not has_repo(odd)
    top = select_top([plain, odd, _repo("real", 1)])
    assert _ids(top) == ["real", "plain", "odd"]


def test_fill_fewer_than_three_papers_returns_all():
    assert _ids(select_top([_repo("r", 500), _entry("n", 3, 0)])) == ["r", "n"]
    assert _ids(select_top([_entry("only", 0, 0)])) == ["only"]
