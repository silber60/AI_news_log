---
phase: 03-humanizer-highlight-explainer
plan: 04
subsystem: content-pipeline
status: complete
tags: [explainer, topics, claude, EXPL]
requires: [03-01, 03-03]
provides:
  - ExplainerLLM
  - newsletter/stages/explainer.py (items_block, check_field, check, write_explainer, explainer_system_prompt)
  - topics.normalize_key / ALIASES / is_repeat
  - prompts/explainer.md v2
  - run_build order trend -> highlight -> explainer -> headline (15 Claude calls)
affects: [03-05, 03-06]
tech-stack:
  added: []
  patterns: [guarded Claude call copied from highlight/trend, code-copied image, alias + containment repeat key]
key-files:
  created:
    - newsletter/stages/explainer.py
    - prompts/explainer.md
    - tests/test_explainer.py
  modified:
    - newsletter/schema.py
    - newsletter/topics.py
    - newsletter/pipeline.py
    - tests/conftest.py
    - tests/test_e2e.py
    - tests/test_analyze.py
    - tests/test_topics.py
decisions:
  - "If attempt 1 failed only on ex_repeat and attempt 2 is unusable (API error, refusal, other check failures), attempt 1 is kept and logged explainer=repeat, so a repeat alone never empties the section"
  - "An APIError on attempt 1 returns None at once (no retry), same as trend"
  - "ex_unknown_name only flags name tokens that contain a digit; allowed names are trend._allowed_names plus name tokens from the does/new/result/kind/architecture lines the explainer also sees"
  - "Field caps reuse humanize.EXPLAINER_*_LIMIT from 03-02 so the polish pass and the stage share one source"
  - "topic is exempt from the number check (spec: point_ko and body_ko only); digit names in topic are still caught by ex_unknown_name"
metrics:
  duration: ~30 min
  completed: 2026-11-04
estimate:
  tokens: 95000
  tasks: 3
actuals:
  tokens: 9400
  tasks: 3
  commits: 4
plan_head_before: 7bfaf8b
plan_head_after: 617ce8e2c6c4623ee0320b645f4c4f903f415a79
---

# Phase 3 Plan 04: AI 기술 쉽게 보기 explainer end to end Summary

Each build now makes one explainer call over this week's items and the past-topic record. Code checks every field: length, sentence count, 해요체, URL, hype words, authorship wording, unknown digit names, and invented numbers (the analogy is exempt). It also checks related_ranks: 1-3 unique ranks in 1..N. Code copies the image from the first related item that has one. Repeats follow the amended D-12: a repeat on attempt 1 is accepted only for the rank-1 fallback, any other repeat gets one retry, and a repeat on attempt 2 is accepted and logged as `explainer=repeat`. The W44 build stores the explainer, the email shows it between the Top 3 and the rest, and the build makes 15 Claude calls.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 | Tracer: ExplainerLLM, explainer stage, pipeline wiring, conftest default, call counts 15 | 279a9d8 |
| 2 (RED) | Failing tests for check_field and the topic repeat rule | 265bcec |
| 2 (GREEN) | normalize_key / ALIASES / is_repeat, check_field, amended D-12 loop | 066ab05 |
| 3 | prompts/explainer.md v2 and prompt tests | 617ce8e |

## Verification

- `uv run pytest`: 1089 passed (1061 after Task 1; baseline before the plan was all green at 7bfaf8b)
- `tests/test_explainer.py`: 36 passed. `-k repeat`: 4 collected. `-k prompt`: 3 collected.
- `tests/test_topics.py`: 17 passed
- `uv run ruff check`: clean. `ruff format --check newsletter tests`: clean.
- W44 e2e: 15 Claude calls (10 analyze, notes, trend, highlight, explainer, headline). texts[10:15] start with `<items>`. The explainer text holds `<past_topics>`. The stored explainer has the default topic and related_ranks [1, 2]. `data-section="explainer"` sits between top3 and rest.
- `data/explainer_topics.json` bytes are identical before and after run_build (D-06)
- `git diff --quiet 7bfaf8b -- schema/issue.schema.v3.json`: unchanged (D-10)
- Tracer gate: the Task 1 `<verify>` passed again (1061 passed) before Tasks 2-3
- Only the 10 files in `files_modified` changed. No templates were touched (03-05 owns them).

## TDD Gate Compliance (Task 2)

- RED 265bcec: 21 new tests failed with AttributeError (normalize_key, ALIASES, is_repeat and check_field did not exist).
- GREEN 066ab05: all passed. No refactor commit was needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Correctness] A repeat alone could still empty the section**
- **Found during:** Task 2
- **Issue:** Suppose attempt 1 passes every check except ex_repeat, and attempt 2 then fails (API error, refusal, or a different check failure). The plain loop would return None, so the repeat would be the reason the section disappeared. The behavior list forbids that ("a repeat is never the reason for returning None").
- **Fix:** Attempt 1's repeat-only result is held. If attempt 2 does not yield an explainer, the stage returns attempt 1's result and logs `explainer=repeat attempt=1 retry=<codes>`.
- **Files modified:** newsletter/stages/explainer.py, tests/test_explainer.py (3 tests)
- **Commit:** 066ab05

**2. [Rule 2 - Correctness] Wider allowed-name set for ex_unknown_name**
- **Issue:** trend._allowed_names covers only titles and summary_ko. The explainer also sees the does/new/result/kind/architecture lines, so a digit name from those lines would be falsely rejected.
- **Fix:** The explainer's allowed set adds the name tokens from those lines.
- **Commit:** 066ab05

## Known Stubs

None. The explainer image row in the template is 03-05's job. Until it lands, `Explainer.image` is stored in issue.json but not rendered.

## Threat Flags

None. No new network, auth or file-write surface. The build only reads the topic record. Logs carry codes and attempt numbers only (tested).

## Self-Check: PASSED
