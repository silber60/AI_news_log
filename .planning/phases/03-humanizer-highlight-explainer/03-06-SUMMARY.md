---
phase: 03-humanizer-highlight-explainer
plan: 06
subsystem: humanizer
status: complete
tags: [humanizer, polish, claude, guards, redaction]
requires: [03-02, 03-04]
provides:
  - humanize.polish_issue(issue, client) -> Issue (cleanup, lint gate, guarded polish call, diff guard, dash fallback)
  - schema.PolishFixLLM / PolishLLM
  - prompts/polish.md (system = polish.md + humanizer_ko.md)
  - run_build order: ... headline -> Issue -> polish_issue -> write
affects: [newsletter/pipeline.py, tests/conftest.py]
tech-stack:
  added: []
  patterns: [guarded Claude call copied from trend/explainer, whole-dump leaf diff guard, per-path stage re-check registry]
key-files:
  created: [prompts/polish.md]
  modified:
    - newsletter/schema.py
    - newsletter/stages/humanize.py
    - newsletter/pipeline.py
    - tests/conftest.py
    - tests/test_humanize.py
    - tests/test_e2e.py
    - tests/test_redaction.py
decisions:
  - "Retry feedback lines are formatted '[code] <id>: <rule>' so attempt 2 carries problem codes and ids, never model text"
  - "Guard emoji check uses both headline._EMOJI_RE and humanize._EMOJI_RE; authorship uses headline.WRITTEN_BY_RE (allows 'Claude' in claude_gpt reasons), per the plan rather than research's AUTHORSHIP_RE"
  - "A stage-check failure is reported as fix_stage with the stage codes joined, e.g. [fix_stage] trend_ko: 필드 규칙 위반 (trend_sentences)"
  - "explainer/highlight are imported lazily inside stage_errors because explainer imports humanize"
  - "If the final dump differs from the original outside collected paths, polish_issue returns the original issue (polish=discarded reason=final_diff)"
metrics:
  duration: ~35 min
  completed: 2026-11-04
actuals:
  tokens: 9000
  tasks: 3
  commits: 4
plan_head_before: aed6fb144f1999af93cd14c37e5447b67ac85fe4
plan_head_after: 37d382b6a6f4b4bce68f1db43edf873530274efc
---

# Phase 3 Plan 06: Polish pass Summary

One lint-gated Claude polish call at the end of the build rewrites only flagged free-text fields; per-fix fact guards, stage re-checks and a whole-dump diff guard keep every fact, enum, URL and code reason unchanged, and leftovers log a warning without blocking.

## What was built

- `PolishFixLLM {id, text}` / `PolishLLM {fixes}` (extra="forbid") in schema.py. Issue and `schema/issue.schema.v3.json` unchanged.
- `humanize.polish_issue`:
  1. cleanup on every collected field (sentence and name), rebuilt via `Issue.model_validate`;
  2. `lint_issue`; no flagged field means no call;
  3. `<fields>` block with only flagged ids (`id`, `kind: 문장`, `limit`, `problems`, `text`; text has `<fields>` tags stripped);
  4. per-fix guards: requested id appearing once, non-empty, limit, 해요체, no URL, emoji, authorship wording (WRITTEN_BY_RE), no new digit, name-like Latin token or `N위`, hard lint hits lower, weak hits not higher, plus the owning stage check (trend.check_trend, notes polarity/grounding, _CG_LABELS, _SG_LABELS, highlight.check_text, explainer.check_field);
  5. at most 2 calls; attempt 2 resends only failed ids with `[code] id: rule` feedback;
  6. API error stops and keeps the cleaned originals; refusal, max_tokens, schema error and empty output retry once, then keep originals;
  7. diff guard over flattened leaves (`polish=discarded reason=diff`); re-lint leftovers log `humanizer=unfixed fields=<n> codes=<codes>`;
  8. dash fallback (`cleanup=dash fields=<n>`), then a final check against the original dump outside collected paths.
- `run_build` calls `humanize.polish_issue(issue, client)` before `issue.json`, so issue.json, email.html and email.txt carry the same text.
- `prompts/polish.md`: data fence, keep-facts rules, `<previous_output_problems>` handling, one hint line for each of the 22 lint codes (HARD_CODES + WEAK_CODES), one fix per id copied verbatim.
- conftest `default_polish` (drops "혁신적인 " / "획기적인 "), routed for PolishLLM in `default_response`.

## Call counts (measured)

- Clean W44 build: **15** calls (10 analyze, notes, trend, highlight, explainer, headline), 0 polish and no `<fields>` in any request.
- W44 build with "혁신적인" added to rank 2's `new_ko`: **16** calls. The last request starts with `<fields>` and holds only `items.1.summary_lines_ko.1`. The stored line is `이전 방법과 다른 점이에요.`, and the whole dump (minus `generated_at`) equals the clean build.

## Tests

- Full suite: **1136 passed** (1100 at aed6fb1, so 36 new tests), `ruff check` and `ruff format --check` on newsletter/tests clean.
- `tests/test_humanize.py -k "polish or guard"`: 34 tests (plan asks for at least 14): 11 parametrized fact/format guards, repeated id, 6 parametrized stage re-checks, UNKNOWN_REASON exclusion, second attempt resends only failed ids, 2-call cap plus unfixed warning, API error, 4 bad-response cases, unrequested id ignored, diff guard discard, clean issue makes no call, flagged-only fix, prompt composition, hint coverage, data fence.
- `test_default_fake_texts_are_lint_clean` (Pitfall 9): every conftest default text passes lint. No default needed changing.
- `tests/test_redaction.py`: 7 tests (baseline 6). The new test runs a dirty W44 build at INFO and finds no stored title, summary, line, idea, reason, trend, highlight or explainer text (and no "혁신적인") in any log message.
- `PER_CELL_VISIBLE_SHA256` hashes in tests/test_render.py were **not** recomputed: polish does not touch the `issue_w44` fixture and render tests do not call it (`git diff aed6fb1 -- tests/fixtures` is empty).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixture choice for the skill_gpt stage re-check**
- **Found during:** Task 2 GREEN
- **Issue:** The RED test's skill_gpt original contained "Claude Skill", so the default polish fix kept the label and failed the stage check in every stage case, and the bad fix tripped the name guard before the stage guard.
- **Fix:** Original now uses "Skill" alone; the rejected fix uses "해당 없음", so only `fix_stage` fires.
- **Files modified:** tests/test_humanize.py
- **Commit:** 7d42c39

**2. [Rule 1 - Bug] RED test helper wrapped a ready response twice**
- **Found during:** Task 2 RED
- **Fix:** `_run_twice_bad` wraps only string fixes. Committed with the RED tests (1e13e3a).

Stop rule did not trigger: the diff guard held for every e2e case on the first try.

## TDD Gate Compliance

Task 2: RED commit 1e13e3a (19 failing tests), GREEN commit 7d42c39 (all pass). No refactor commit.

## Known Stubs

None.

## Threat Flags

None. No new endpoint or file access. The polish call goes through the existing `analyze._request` path, and its logs carry ids, counts and codes only (T-03-19 test).

## Self-Check: PASSED

- FOUND: prompts/polish.md, newsletter/stages/humanize.py (polish_issue), newsletter/schema.py (PolishLLM)
- FOUND commits: 6e3c2cb, 1e13e3a, 7d42c39, 37d382b
- HUMN-02 and HUMN-03 met offline.
