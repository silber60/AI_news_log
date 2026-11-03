---
phase: 02-evidence-practical-verdicts
plan: 05
subsystem: analysis
status: complete
tags: [claude, claude-gpt, verdict-reasons, trend, pipeline, anly-02, anly-04, anly-05]
requires:
  - 02-03 (trend.write_trend, notes.write_notes, FakeAnthropic defaults)
  - 02-04 (enrich wiring, W44 commercial verdicts)
provides:
  - "ItemAnalysisLLM.claude_gpt / claude_gpt_reason_ko, mapped into Item.claude_gpt"
  - "analyze.check codes cg_reason_empty, cg_reason_len, cg_label_in_reason (+ tone)"
  - "prompts/analyze_paper.md prompt-version 5 with the Claude/GPT sections"
  - "run_build: analyze -> enrich -> finalize -> notes -> trend -> headline -> Issue(trend_ko)"
affects: [02-06, Phase 4 web version (reads reason_ko and trend_ko from issue.json)]
tech-stack:
  added: []
  patterns: ["bad Claude/GPT reason after the retry downgrades the label instead of stopping the build"]
key-files:
  created: []
  modified:
    - newsletter/schema.py
    - newsletter/stages/analyze.py
    - newsletter/stages/verdicts.py
    - newsletter/pipeline.py
    - prompts/analyze_paper.md
    - tests/conftest.py
    - tests/test_analyze.py
    - tests/test_prompt.py
    - tests/test_e2e.py
    - tests/test_verdicts.py
decisions:
  - "cg_reason_empty and cg_label_in_reason left after the retry set claude_gpt to 확인 필요 with an empty reason (Item.reason_ko None) and log claude_gpt=downgraded rank=N codes=...; the build continues"
  - "claude_gpt_reason_ko joins HAEYO_FIELDS, so a wrong ending is the shared non-fatal tone code"
  - "The downgrade runs before trimming; trimming then works on the downgraded copy and logs only when a field was cut"
  - "finalize logs claude_gpt=direct_many count=N (count only) when more than 3 items stay 직접 사용 after enforce_evidence"
metrics:
  duration: "~25 min"
  completed: 2026-11-03
estimate:
  tokens: 90000
  tasks: 3
actuals:
  tokens: 8200
  tasks: 3
  commits: 4
plan_head_before: dbb5bb4
plan_head_after: 2ee70b796923f8160d5dd33c27a889ce7d817540
---

# Phase 2 Plan 05: Claude/GPT label, reasons and trend wired into the build Summary

The per-paper analyze call now also returns a Claude/GPT label from the closed enum plus a 60-character 해요체 reason. Code checks the reason and drops the label to 확인 필요 when the reason is still bad after the retry. The build runs the verdict-reason and trend calls after `verdicts.finalize`, so the W44 issue.json stores reasons for every 상업적 사용 and PoC verdict. The email shows the trend under the greeting.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 | Claude/GPT label and reason on every W44 card, finalize 직접 사용 warning (tracer) | d44ed5c |
| 2 | RED: cg checks, downgrade, prompt v5 tests | f569fa7 |
| 2 | GREEN: analyze.check cg codes, post-retry downgrade, prompt v5 | adc0e98 |
| 3 | Pipeline order with notes and trend, call counts, trend outage test | 2ee70b7 |

## Claude call counts (measured on the W44 fixture)

- Normal build: **13** calls (10 analyze, 1 notes, 1 trend, 1 headline). This matches the plan. After 02-04, 9 commercial and 10 PoC verdicts are known, so notes makes its one call.
- Refusal-retry build (`test_refusal_is_retried_once_and_week_builds`): **14** (11 analyze + notes + trend + headline).
- Invalid-twice build: still **6**. The build stops in analyze.
- Fallback downgrade tests: `["beta"] + ["messages"] * 13`. Notes and trend use `analyze._request`, so the per-client downgrade covers them too.

## W44 stored reasons (e2e)

- `commercial.reason_ko`: the default notes reason on the 9 known cards. Rank 3 (Hy-Nomas, 확인 필요) gets `notes.UNKNOWN_REASON`.
- `poc.reason_ko`: the default notes reason on all 10 cards.
- `claude_gpt`: 기법 적용 가능 with the default reason on all 10 cards. Every card shows "🤖 Claude/GPT 기법 적용".
- `trend_ko`: `DEFAULT_TREND`. It sits between `data-section="greeting"` and `top3`.
- W44 email.html is 46,033 bytes, under the 90 KB cap.

## Verification

- `uv run pytest`: **850 passed** (baseline 828).
- `uv run pytest tests/test_analyze.py -k "cg or claude_gpt"`: 18 tests, all passed.
- `uv run ruff check`: all checks passed. `ruff format --check newsletter tests`: clean. A plain `ruff format --check` also flags 6 `.planning/**/*.md` files, which was already true before this plan.
- `git diff --quiet dbb5bb4 -- schema/issue.schema.v3.json`: unchanged.
- Acceptance greps: `claude_gpt_reason_ko` in schema.py = 1; `ClaudeGptUse(` in analyze.py >= 1; prompt header `<!-- prompt-version: 5 -->`; `cg_label_in_reason` in analyze.py = 2; `write_notes|write_trend` in pipeline.py = 2; `len(fake.calls) == 13` in test_e2e = 1; `len(fake.calls) == 14` in test_analyze = 1; `["messages"] * 13` in test_analyze = 2.
- Tracer gate (Task 1): verify re-run end to end and passed before Task 2.

## Deviations from Plan

**1. [Rule 3 - Blocking] test_prompt field-count assert updated**
- **Found during:** Task 2
- **Issue:** `test_system_names_v3_fields_and_one_idea` asserted "아홉 필드". The plan requires the opening paragraph to list the new fields.
- **Fix:** The assert now expects "열한 필드" and rejects "아홉 필드" and "여덟 필드".
- **Commit:** adc0e98

**2. [Rule 2 - Correctness] verdicts.py docstring**
- The module docstring said "no logging". It now says the only log line is the weekly 직접 사용 count in `finalize`.
- **Commit:** d44ed5c

**3. Trend outage test placement**
- The plan lists the trend APIError test under Task 3 without naming a file. It lives in `tests/test_e2e.py` (`test_trend_api_error_keeps_the_build`) and uses `anthropic.APIConnectionError`, a subclass of `APIError`.

No other deviations. The call counts match the plan.

## Known Stubs

None.

## Threat Flags

None. No new network endpoints or trust boundaries were added. T-02-17 and T-02-18 are mitigated by the closed enum, the `enforce_evidence` 직접 사용 guard, the >3 warning, `cg_label_in_reason` and the post-retry downgrade.

## Self-Check: PASSED

- FOUND: newsletter/schema.py, newsletter/stages/analyze.py, newsletter/stages/verdicts.py, newsletter/pipeline.py, prompts/analyze_paper.md
- FOUND commits: d44ed5c, f569fa7, adc0e98, 2ee70b7
