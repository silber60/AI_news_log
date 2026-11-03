---
phase: 03-humanizer-highlight-explainer
plan: 01
subsystem: content-pipeline
status: complete
tags: [highlight, analyze, claude, templates, HILT]
requires: [02-05]
provides:
  - ItemAnalysisLLM.skill_gpt_fit / skill_gpt_reason_ko
  - HighlightPickLLM / HighlightsLLM
  - newsletter/stages/highlight.py (candidates, items_block, check_text, review, write_highlights)
  - prompts/highlight.md, prompts/analyze_paper.md v6
  - headline.WRITTEN_BY_RE
  - always-on highlight section with fallback line
affects: [03-02, 03-04, 03-05, 03-06]
tech-stack:
  added: []
  patterns: [guarded Claude call copied from trend.write_trend, code-copied tag, non-fatal downgrade codes]
key-files:
  created:
    - newsletter/stages/highlight.py
    - prompts/highlight.md
    - tests/test_highlight.py
  modified:
    - newsletter/schema.py
    - newsletter/stages/analyze.py
    - newsletter/stages/headline.py
    - newsletter/pipeline.py
    - prompts/analyze_paper.md
    - templates/email.html.j2
    - templates/email.txt.j2
    - tests/conftest.py
    - tests/test_analyze.py
    - tests/test_e2e.py
    - tests/test_prompt.py
    - tests/test_render.py
decisions:
  - "A highlight APIError on attempt 2 keeps attempt 1's passing picks (same rule as an unusable retry); on attempt 1 it returns []"
  - "WRITTEN_BY_RE needs a space in '이 메일' / '이 뉴스레터' so 이메일 passes, and '이번 호' skips 호출/호환/호스팅"
  - "sg_label_in_reason checks Claude Skill, GPTs and 해당 없음 only; 둘 다 is ordinary Korean"
metrics:
  duration: ~35 min
  completed: 2026-11-03
estimate:
  tokens: 110000
  tasks: 3
actuals:
  tokens: 10200
  tasks: 3
  commits: 3
plan_head_before: 7f243600598f586eaf0317541dd9a39412652fc3
plan_head_after: 24980b2a0b3d0e34d59287929b6768744299babf
---

# Phase 3 Plan 01: Skill/GPTs highlight end to end Summary

Analyze now labels each paper's Claude Skill / GPTs fit with a 60-char 해요체 reason. One extra pick call chooses 0-3 of the labelled items, and code checks it: candidate ranks only, no duplicates, at most 3, and short 해요체 why/how text. Code copies each tag from the item's own label. The "이번 주 바로 써볼 만한 것" section always renders above the Top 3 and shows "이번 주는 해당 항목 없음" when there are no picks.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 | Tracer: fit label, highlight stage, pipeline wiring, always-on section | e395df7 |
| 2 | sg_* checks, non-fatal downgrade to 해당 없음, analyze prompt v6 | 40a2ec1 |
| 3 | check_text / review, two-attempt loop, WRITTEN_BY_RE, highlight.md v2 | 24980b2 |

## Verification

- `uv run pytest -q`: 918 passed (baseline 852 before the plan)
- `tests/test_highlight.py`: 47 tests passed
- `uv run ruff check`: clean. `ruff format --check newsletter tests`: clean.
- W44 e2e: 14 Claude calls (10 analyze, notes, trend, highlight, headline). 3 highlights stored with ranks [1, 2, 3] and tag "Claude Skill". The highlight section sits between the trend and the top 3.
- Empty highlights: the HTML and text parts both show exactly one fallback line and no pill.
- `git diff --quiet 7f24360 -- schema/issue.schema.v3.json`: unchanged (D-10)
- Tracer gate: auto-mode re-run of `<verify>` passed before Tasks 2-3

## Deviations from Plan

None in behavior. Notes:

- Task 1 wrote a short `prompts/highlight.md` and a one-attempt stage, as the plan said. Task 3 replaced both. Two Task 1 tests (rank filtering, cap at 3) now script the same answer for both attempts, because a dropped pick triggers the retry.
- Task 2 and Task 3 are `tdd="true"`. The tests and the implementation landed in the same commit, with no separate RED commit. Every new test was run green before its commit.
- `tests/test_highlight.py` was written in Task 1 and extended in Task 3. It is in Task 3's file list, so this stays within the plan.

## Known Stubs

None. The section always has a data source (`issue.highlights`) and a defined empty state.

## Threat Flags

None. No new surface beyond the threat model. T-03-01 is mitigated: the `<items>` data fence, candidate/unique/max-3 rank checks, and code-copied tags. T-03-02 is mitigated: logs carry attempt numbers, counts and codes only, and a caplog test checks this.

## Self-Check: PASSED

- FOUND: newsletter/stages/highlight.py, prompts/highlight.md, tests/test_highlight.py
- FOUND: e395df7, 40a2ec1, 24980b2 (ancestors of HEAD)
