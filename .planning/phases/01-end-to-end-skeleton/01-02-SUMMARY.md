---
phase: 01-end-to-end-skeleton
plan: 02
subsystem: collection
status: complete
tags: [hf-papers, fetch, iso-week, retries, selection]
requires: ["01-01"]
provides:
  - "fetch_week: week= paging with date= fallback (ISO W53, HTTP 400), KST in-week filter, dedupe, tenacity retries"
  - "fetch_by_dates(mon, sun, client) -> (entries, pages)"
  - "tests/fixtures/hf_tie_sample.json (stable 95/95 tie)"
affects: [newsletter/pipeline.py (consumer, unchanged)]
tech-stack:
  added: []
  patterns:
    - "tenacity Retrying built per GET; wait base read from module constant at call time"
    - "private FetchError subclass (_WeekRejected) signals HTTP 400 for the week= -> date= switch"
key-files:
  created:
    - tests/test_week.py
    - tests/test_select.py
    - tests/fixtures/hf_tie_sample.json
  modified:
    - newsletter/stages/fetch.py
    - tests/test_fetch.py (new in this plan; did not exist after 01-01)
decisions:
  - "Week 53 skips week= entirely; any HTTP 400 on week= is not retried and switches to the date= loop"
  - "A 400 on date= surfaces as FetchError (it is a FetchError subclass), no further fallback"
  - "Entries with missing or naive submittedOnDailyAt are dropped by the KST in-week filter"
  - "TransportError FetchError keeps exception chaining (no response body exists); status FetchError uses `from None`"
metrics:
  duration: "~25 min"
  completed: 2026-11-02
actuals:
  tokens: 5400
  tasks: 3
  commits: 3
plan_head_before: d927d0f2fb31048355f1942731f0072b0f31e135
plan_head_after: 18de63e54ed35df2f71be460d40c2cf8a2fa11ac
---

# Phase 1 Plan 02: Collection Hardening Summary

HF Papers fetch now survives ISO week 53 and HTTP 400 by switching to a 7-day `date=` loop. It filters to the KST week, dedupes by `paper.id`, retries only transport errors, 429 and 5xx (4 attempts), and fails closed on an empty week. Top N selection is pinned by tests.

## Tasks

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | W53 issue end to end through date= fallback (tracer) | 5bc10fb | newsletter/stages/fetch.py, tests/test_fetch.py |
| 2 | KST week tests, bounded retries, fail-closed empty fetch | 8627af8 | newsletter/stages/fetch.py, tests/test_fetch.py, tests/test_week.py |
| 3 | Deterministic Top N and selected.json snapshot | 18de63e | tests/test_select.py, tests/fixtures/hf_tie_sample.json |

## What changed

- `fetch_week(issue_id, *, client=None) -> FetchResult` keeps its signature. It pages `week=` for weeks 1..52. On week 53 or an HTTP 400 it calls `fetch_by_dates(mon, sun, client)`, which queries all 7 days (weekends included) and pages each day (limit 100, stop on a short page, 20-page cap).
- After merging, entries are deduped (first wins), filtered to `submittedOnDailyAt` in Mon..Sun KST, then passed through `trim_entry()`.
- The only log line is `method=… pages=… fetched=… kept=…`.
- Retries: `Retrying(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=RETRY_WAIT_MULTIPLIER, max=30))` on `httpx.TransportError`, 429 and 5xx. Other 4xx raise `FetchError("HTTP <code>")` after 1 call. Exhausted retries raise `FetchError("HTTP <code>")` or `FetchError("<ExceptionClass>")`, with no response bodies (T-01-08).
- Zero kept entries raise `EmptyFetchError` on both paths (COLL-04).

## Verification

- `uv run pytest -q tests/test_week.py tests/test_fetch.py tests/test_select.py tests/test_e2e.py tests/test_schema.py`: 54 passed.
- `uv run ruff check`: all checks passed. `ruff format --check` is clean on the touched files.
- `--durations=5`: slowest test 0.14 s, so the fetch suite runs well under 5 s (tests set `RETRY_WAIT_MULTIPLIER` to 0).
- Acceptance greps: `def fetch_by_dates` = 1, `run_build("2026-W53"` = 1, `stop_after_attempt(4)` = 1, `EmptyFetchError` >= 1 in fetch.py, `2026-W53` in test_week.py, `2610.37230` in the tie fixture = 1.

## Deviations from Plan

- **newsletter/week.py needed no change.** Plan 01 already rejects naive datetimes in `previous_iso_week` and validates overrides with regex plus `fromisocalendar`. All Task 2 week behaviors passed on the first run, so this plan only adds tests for them. The task's RED step therefore covered only the retry and fail-closed tests in test_fetch.py.
- **newsletter/stages/select.py needed no change.** `sort_key` already matches D-10. selected.json already carries rank, paper_id, upvotes, numComments and submittedOnDailyAt, so pipeline.py was not touched.
- No new dependencies. tenacity was already pinned in pyproject.toml.

## TDD Gate Compliance

- Task 2: RED was confirmed first (8 fetch retry/empty tests failed because `RETRY_WAIT_MULTIPLIER` was missing). GREEN followed in the same commit as the implementation (8627af8). The week tests passed without code changes; see Deviations.
- Task 3: the tests passed on first run against the 01-01 code. No production change was needed.

## Known Stubs

None.

## Threat Flags

None. No new surface. T-01-07 (20-page cap, 4 attempts, 30 s timeout, at most 7 dates) and T-01-08 (no bodies in errors) are implemented and tested.

## Self-Check: PASSED

- FOUND: newsletter/stages/fetch.py, tests/test_fetch.py, tests/test_week.py, tests/test_select.py, tests/fixtures/hf_tie_sample.json
- FOUND commits: 5bc10fb, 8627af8, 18de63e (ancestors of HEAD)
