---
phase: 03-humanizer-highlight-explainer
plan: 02
subsystem: humanizer
status: complete
tags: [humanizer, lint, prompt, korean]
requires: []
provides:
  - "newsletter/stages/humanize.py: FieldRef, collect_fields, lint, needs_polish, lint_issue, cleanup, dash_fallback, HARD_CODES, WEAK_CODES"
  - "prompts/humanizer_ko.md humanizer-version 2 (full Korean port)"
affects: [03-06 polish pass, every Claude system prompt]
tech-stack:
  added: []
  patterns: ["stdlib re banned-pattern lint, hard vs weak scoring", "field paths = Issue.model_dump(mode=json) leaf paths"]
key-files:
  created:
    - newsletter/stages/humanize.py
    - tests/test_humanize.py
  modified:
    - prompts/humanizer_ko.md
decisions:
  - "Name-kind limits: title_ko None, kind_ko 30, architecture_ko 60, explainer.topic 40; highlight why/how 70; explainer point/body/example 40/360/140 (research A2)"
  - "Weak codes closer and same_opening are code rules on analyze._SENT_SPLIT sentences (3+ sentences)"
  - "Empty or None fields are not collected; lint log joins codes with ',' and prints '-' when none"
metrics:
  duration: "~25 min"
  completed: 2026-11-03
actuals:
  tokens: 8800
  tasks: 3
  commits: 4
plan_head_before: 7f243600598f586eaf0317541dd9a39412652fc3
plan_head_after: fe9570280a6f1f5d3fd6766864e6f067b1872f02
---

# Phase 3 Plan 02: Humanizer lint and Korean port Summary

Deterministic AI-tell lint over every Claude field of an `Issue` (12 hard and 10 weak codes from research §1, stdlib `re`), markdown/quote cleanup with a hyphen-safe dash fallback, and the full Korean port of the humanizer rules carried by all four system prompts.

## What was built

- `collect_fields(issue)` walks the research §2 table in fixed order and returns `FieldRef(path, kind, limit, text)`; paths match `model_dump(mode="json")` leaves (test checks every path resolves to the same text). Skips `headline_ko`, enums, URLs, ranks, images, None/empty fields and reasons equal to `notes.UNKNOWN_REASON`. Names (`title_ko`, `kind_ko`, `architecture_ko`, `explainer.topic`) are kind `name`.
- `lint(text, kind=)` returns one code per match. Hard: dash, markdown, hype, not_x_but_y, beyond, significance, chatbot, authority, run_up, double_passive, emoji, haeyo (`analyze.not_haeyo`). Weak: not_x_plain, saying, role_verb, rider, ai_words, triad, hedge_stack, subject_repeat, closer, same_opening. `emoji` and `haeyo` apply to sentence fields only.
- `needs_polish`: any hard hit or 2+ weak hits. `lint_issue` maps flagged sentence paths to sorted unique codes and logs `humanizer=lint fields=<n> flagged=<m> codes=<codes>` (no paths or text).
- `cleanup` strips `**`, `__`, backticks, leading `#`/`- `, straightens curly quotes, collapses whitespace; idempotent. `dash_fallback` turns `—`, `–`, ` -- ` into `, ` and keeps `GPT-5`, `Qwen3-VL`, `Vision-Language-Action`.
- `prompts/humanizer_ko.md` v2: rules 1-25 ported with one "대신" example each under six headings; rule 10 and 26 noted as not applicable; 해요체 rule and noun-phrase exception kept (now also naming `topic`).

## Test results

- `tests/test_humanize.py`: 111 tests. Lint positives: 27 crafted cases (25 flag, 2 weak-only) plus a coverage test that every one of the 22 codes has a case. Negatives: 56 (50 W44 sentence fields plus 6 legitimate lines, including `기존 기록을 넘어섰어요.`, `100자를 넘어가면 잘라요.`, `사람이 아니라 로봇이 직접 움직여요.`, `역량, 최적화, 평가 방법을 함께 다뤄요.`). W44 fixture: 0 flagged fields.
- Full suite: 961 passed. `ruff check` and `ruff format --check newsletter tests` clean. `tests/test_prompt.py` unchanged and passing. `analyze.py` untouched.

## Commits

- aaa10da feat(03-02): lint any Issue and report flagged field paths and codes
- 069af65 test(03-02): add failing lint positives, negatives and cleanup cases (RED)
- 0760b33 feat(03-02): add the full banned-pattern list, cleanup and dash fallback (GREEN)
- fe95702 feat(03-02): port the full humanizer rules to Korean (humanizer-version 2)

## TDD Gate Compliance

Task 2: RED commit 069af65 (34 new cases failing: missing codes, `cleanup`, `dash_fallback`), GREEN commit 0760b33 (all passing). No refactor commit needed.

## Deviations from Plan

None. The plan executed as written. Small choices are listed under decisions: name-field limits, the log format for an empty code set, and skipping empty fields.

## Known Stubs

None. `polish_issue` belongs to 03-06 by design.

## Self-Check: PASSED

- FOUND: newsletter/stages/humanize.py, tests/test_humanize.py, prompts/humanizer_ko.md
- FOUND commits: aaa10da, 069af65, 0760b33, fe95702
