"""HF fetch: week= paging, date= fallback (ISO W53 / HTTP 400), KST filter, dedupe."""

import copy
import json
from datetime import date, timedelta

import httpx
import respx
from conftest import FakeAnthropic

HF_URL = "https://huggingface.co/api/daily_papers"
W53 = "2026-W53"
W53_MON = date(2026, 12, 28)


def _on_day(entry: dict, day: date) -> dict:
    """Copy a W44 fixture entry and move its daily date to `day`."""
    e = copy.deepcopy(entry)
    e["paper"]["submittedOnDailyAt"] = f"{day.isoformat()}T00:00:00.000Z"
    return e


def _w53_date_pages(hf_pages) -> dict[str, list[dict]]:
    """Mon..Fri get 6 W44 entries each (moved into W53); Sat/Sun return [] like HF does today."""
    src = hf_pages[0]
    pages: dict[str, list[dict]] = {}
    for i in range(7):
        day = W53_MON + timedelta(days=i)
        pages[day.isoformat()] = [_on_day(e, day) for e in src[i * 6 : i * 6 + 6]] if i < 5 else []
    return pages


def _mock_dates(router: respx.MockRouter, pages: dict[str, list[dict]]) -> list[respx.Route]:
    return [
        router.get(HF_URL, params={"date": day, "limit": "100", "p": "0"}).mock(
            return_value=httpx.Response(200, json=page)
        )
        for day, page in pages.items()
    ]


def test_w53_builds_end_to_end_via_date_loop(hf_pages, archive_tmp):
    from newsletter.pipeline import run_build

    pages = _w53_date_pages(hf_pages)
    # A duplicate on a later day and an out-of-week entry (Sunday before) on Monday's page.
    pages["2026-12-29"].append(copy.deepcopy(pages["2026-12-28"][0]))
    pages["2026-12-28"].append(_on_day(hf_pages[1][0], date(2026, 12, 27)))

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        week_route = router.get(HF_URL, params={"week": W53}).mock(
            return_value=httpx.Response(400, json={"error": "must match pattern"})
        )
        date_routes = _mock_dates(router, pages)
        issue = run_build(W53, claude_client=FakeAnthropic())

    assert week_route.call_count == 0
    assert [r.call_count for r in date_routes] == [1] * 7

    week = archive_tmp / "archive" / W53
    raw = json.loads((week / "raw.json").read_text(encoding="utf-8"))
    assert raw["method"] == "date"
    assert raw["count"] == len(raw["entries"]) == 30
    ids = [e["paper"]["id"] for e in raw["entries"]]
    assert len(set(ids)) == 30
    assert hf_pages[1][0]["paper"]["id"] not in ids
    assert '"authors"' not in json.dumps(raw)

    stored = json.loads((week / "issue.json").read_text(encoding="utf-8"))
    assert stored["fetch_method"] == "date"
    assert stored["week_start"] == "2026-12-28"
    assert stored["week_end"] == "2027-01-03"
    assert [it["rank"] for it in stored["items"]] == list(range(1, 11))
    assert issue.fetch_method == "date"


def test_week_400_falls_back_to_date_loop():
    from newsletter.stages.fetch import HF_BASE, fetch_week

    mon = date(2026, 10, 26)
    entry = {
        "paper": {
            "id": "2610.00001",
            "title": "T",
            "summary": "S",
            "upvotes": 3,
            "submittedOnDailyAt": "2026-10-26T00:00:00.000Z",
        },
        "numComments": 1,
    }
    pages = {(mon + timedelta(days=i)).isoformat(): [] for i in range(7)}
    pages["2026-10-26"] = [entry]

    with respx.mock(assert_all_mocked=True, assert_all_called=True) as router:
        week_route = router.get(HF_URL, params={"week": "2026-W44"}).mock(
            return_value=httpx.Response(400, json={"error": "bad"})
        )
        _mock_dates(router, pages)
        with httpx.Client(base_url=HF_BASE) as client:
            result = fetch_week("2026-W44", client=client)

    assert week_route.call_count == 1
    assert result.method == "date"
    assert [e.paper.id for e in result.entries] == ["2610.00001"]
