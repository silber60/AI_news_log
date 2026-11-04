---
phase: 03-humanizer-highlight-explainer
plan: 05
subsystem: render
status: complete
tags: [email-template, size-budget, fonts, explainer]
requires: ["03-01"]
provides:
  - "templates/email.html.j2 template-version 7 (explainer image row, per-table font stack)"
  - "ancestor-aware font tests, font-family count <= 60, visible-text identity test"
  - "Phase 3 worst case with explainer image (11 raw images) under the byte cap"
affects: ["03-07 (owner Gmail + Naver test send gates the font change)"]
tech-stack:
  added: []
  patterns: ["font-family inherited from the nearest presentation table"]
key-files:
  created: []
  modified:
    - templates/email.html.j2
    - newsletter/stages/render.py
    - tests/test_render.py
decisions:
  - "D-14 variant B: the font stack sits on all 19 presentation tables and on no td/span; one revertable commit f039b0d"
  - "Visible-text identity is pinned by sha256 hashes of the per-cell render taken at 4edc407 (fixture JSON is not touched by sibling plans)"
  - "templates/email.txt.j2 keeps template-version 6: it has no font markup and is outside files_modified"
metrics:
  duration: "~25 min"
  completed: 2026-11-04
estimate:
  tokens: 60000
  tasks: 2
actuals:
  tokens: 7800
  tasks: 2
  commits: 2
plan_head_before: 7bfaf8b
plan_head_after: f039b0d
---

# Phase 3 Plan 5: Explainer image and per-table font stack Summary

The explainer now shows its code-copied image after the body. The Korean font stack moved from every cell to every table, which cut the worst case from 91,709 B to 77,608 B with no visible-text change.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Explainer image row + Phase 3 worst case with image | 4edc407 | templates/email.html.j2, tests/test_render.py |
| 2 | Font stack consolidation (D-14), single revertable commit | **f039b0d** | templates/email.html.j2, newsletter/stages/render.py, tests/test_render.py |

## Measurements

| Render | Bytes before (per-cell, after Task 1) | Bytes after (per-table) | font-family before | font-family after |
|--------|------|------|------|------|
| W44 | 43,759 | 35,767 | 130 | 34 |
| full (all Phase 3 slots, no image) | 47,766 | 39,583 | 141 | 42 |
| worst (3 picks, full explainer with image, all verdicts, 10 card images) | **91,709** (headroom 451 to 92,160) | **77,608** (headroom 14,552) | 215 | 46 |

Visible-text sha256 (tags stripped, whitespace normalized) was identical before and after for all three renders:
- w44 `ceb2b473…d24c9d09`, full `5301ebeb…4bb4d4ac`, worst `ee2b1bae…164092dd`

## What changed

- Explainer section: one row after `body_ko` and before 예를 들어, only when `ex.image` is set. The img uses `ex.image.url`, `width`/`height` from `ItemImage`, alt `"{{ ex.topic }} 관련 그림"`, `img_style` plus `border-radius: 8px`, in a td with 14px top padding. The text part shows no image.
- Template-version 7: `{{ ff }}` is on all 19 `<table role="presentation">` tags, either prepended to an existing style or added as a new style attribute. It was removed from all 33 td uses and the 1 span use. The header comment now says cells inherit from their nearest table.
- render.py: the FONT_STACK comment now says the cost multiplies by the table count. FONT_STACK itself is unchanged.
- Tests: the `_Cells` parser tracks the open-table stack and records each cell's nearest table style. The font test checks the cell or its nearest table, across the w44, full and worst renders. New tests:
  - every table carries the stack, and no td or span has `font-family`
  - the worst case has at most 60 `font-family` declarations (measured 46)
  - visible-text hash identity for all three renders
  - an explainer without an image has only the otter img and no "관련 그림"
  - the explainer image sits between the body and 예를 들어 and is absent from the text part
  - `_worst_case` explainer carries a distinct 300-char raw.githubusercontent.com image, and the worst-case image test expects `len(raw) == 11`

## Verification

- `uv run pytest -q`: 1058 passed. `tests/test_render.py`: 94 passed, and 11 of them match `-k font`.
- `uv run ruff check`: all checks passed.
- Acceptance greps: `관련 그림` count 1, `len(raw) == 11` count 1, line 1 `{# template-version: 7 #}`, td/span `{{ ff }}` count 0/0.

## Revert path (T-03-15)

If the 03-07 Gmail/Naver owner send shows a serif fallback, run `git revert f039b0d`. That one commit restores per-cell fonts in the template, the render.py comment and the tests. The worst case then goes back to 91,709 B, which is still under the 92,160 cap. The font change must not reach subscribers until that 03-07 check passes.

## Deviations from Plan

- The plan says to bump "both template-version comments" to 7. `email.html.j2` has only one marker, and it is now 7. `email.txt.j2` also has a version marker, but it has no font markup and is outside `files_modified`, so it stays at 6.
- No other deviations. Task 1's per-cell worst case was under the cap at 91,709 B, so the two tasks were committed separately as planned.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: templates/email.html.j2, newsletter/stages/render.py, tests/test_render.py
- FOUND commits: 4edc407, f039b0d (both ancestors of HEAD)
