---
phase: 02-evidence-practical-verdicts
plan: 03
subsystem: analysis
status: complete
tags: [claude, trend, verdict-reasons, guards, anly-04, anly-05]
requires: []
provides:
  - "trend.write_trend(items, client) -> str | None, trend.check_trend()"
  - "notes.write_notes(items, client) -> list[Item], notes.check_note(), notes.UNKNOWN_REASON"
  - "schema.TrendLLM, VerdictNoteLLM, VerdictNotesLLM (Claude output models, not Issue)"
  - "FakeAnthropic defaults for TrendLLM and VerdictNotesLLM"
affects: [02-05 pipeline wiring, test_e2e call counts once wired]
tech-stack:
  added: []
  patterns: ["headline-style two-attempt Claude call with code checks and non-fatal fallback"]
key-files:
  created:
    - newsletter/stages/trend.py
    - newsletter/stages/notes.py
    - prompts/trend.md
    - prompts/verdict_notes.md
    - tests/test_trend.py
    - tests/test_notes.py
  modified:
    - newsletter/schema.py
    - tests/conftest.py
decisions:
  - "Trend name regex widened to allow a leading digit so generic terms like 3D are not read as a stray capital D"
  - "Digits inside name tokens and rank mentions are excluded from the trend_number check (rank range is checked separately)"
  - "Grounding tokens match on ASCII word edges, so GPL never matches inside LGPL and RAIL never inside OpenRAIL"
  - "After the final attempt, reasons come from the last parsed output; a rank that is missing or duplicated there gets None"
  - "Only fields whose verdict is known are checked; a Claude text for a 확인 필요 field is ignored and UNKNOWN_REASON stays"
metrics:
  duration: "~25 min"
  completed: 2026-11-03
estimate:
  tokens: 85000
  tasks: 3
actuals:
  tokens: 11300
  tasks: 3
  commits: 3
plan_head_before: 1533ddc
plan_head_after: b42a884e39230fd2fd542a590b218f42569c18b0
---

# Phase 2 Plan 03: Trend and verdict-reason Claude calls Summary

Two guarded Claude calls on the headline pattern. The first writes a 2-3 sentence 해요체 trend checked against a name allowlist built from this week's items, rank range and input digits, and returns None on failure. The second is one batched call for 상업적 사용 / PoC reasons, checked for license grounding and verdict polarity. 확인 필요 verdicts get a fixed code reason without a call.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 | Trend call, TrendLLM, prompt, FakeAnthropic default, tracer render test | 9202b7b |
| 2 | check_trend full rule set (sentences, len, tone, URL, hype, authorship, unknown name, rank, number) | a9842a3 |
| 3 | notes.py, VerdictNote(s)LLM, verdict_notes prompt, default notes, tests | b42a884 |

## What was built

- `newsletter/stages/trend.py`: `items_block` sends rank, title_ko, title_en, ai_type and summary_ko for every item. Each value goes through `headline._clean`, and no verdicts are sent. `check_trend` returns the reason codes `trend_empty`, `trend_sentences`, `trend_len`, `trend_tone`, `trend_url`, `trend_hype`, `trend_authorship`, `trend_unknown_name`, `trend_rank` and `trend_number`. `write_trend` makes at most two attempts through `analyze._request` / `_with_feedback`. An APIError returns None. A schema error, refusal, max_tokens or a non-TrendLLM output triggers a retry.
- `newsletter/stages/notes.py`: `UNKNOWN_REASON` is the fixed reason for 확인 필요 verdicts. `items_block` lists only the items with a known verdict, as code facts with yes/no flags and no URL. `check_note` returns `note_empty`, `note_len`, `note_tone`, `note_url`, `note_hype`, `note_ungrounded` and `note_polarity`, and `note_ranks` is checked on the whole response. `write_notes` writes only `reason_ko` through `model_copy`, never changes a verdict and never raises.
- Both system prompts are `prompts/<name>.md` plus `humanizer_ko.md`. Logs carry attempt numbers, ranks and codes only.

## Verification

- `uv run pytest -q`: 538 passed. `tests/test_trend.py` has 25 tests, 20 of them selected by the Task 2 `-k` filter. `tests/test_notes.py` has 19 tests.
- `uv run ruff check`: all checks passed. `ruff format --check`: clean.
- `git diff --quiet 1533ddc -- schema/issue.schema.v3.json`: unchanged.
- The tracer gate was re-run end to end and passed. The default trend renders inside `data-section="trend"`. Render and templates were not edited, because 02-01 owns them.

## Deviations from Plan

**1. [Rule 1 - Bug] Trend name regex accepts a leading digit**
- **Found during:** Task 2
- **Issue:** The research regex `[A-Za-z][A-Za-z0-9]*...` reads "3D" as the token "D", which is uppercase and missing from the allowlist. That would flag a GENERIC_TERMS entry as an unknown name.
- **Fix:** Changed the pattern to `(?<![A-Za-z0-9])[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*(?:[-.+][A-Za-z0-9]+)*`. The allowlist also includes the -/./+ parts of each input token.
- **Commit:** a9842a3

No other deviations.

## Known Stubs

None. Neither call has a pipeline call site yet. Plan 02-05 adds them, as planned.

## Notes for 02-05

- Call order: verdicts → `notes.write_notes` → `trend.write_trend` → headline. With the default fakes, the normal path adds 2 calls (1 notes call only when some verdict is known, plus 1 trend call). On the W44 fixture every verdict is 확인 필요, so the notes stage makes no call unless 02-01 / 02-04 fill the verdicts.

## Self-Check: PASSED

- FOUND: newsletter/stages/trend.py, newsletter/stages/notes.py, prompts/trend.md, prompts/verdict_notes.md, tests/test_trend.py, tests/test_notes.py
- FOUND commits: 9202b7b, a9842a3, b42a884
