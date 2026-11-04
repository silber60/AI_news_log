---
phase: 04-figma-design-email-template-web-archive
plan: 07
subsystem: email-template, planning
status: checkpoint   # Task 1 done; Task 2 (owner inbox check, checkpoint D) and Task 3 (owner send) pending
tags: [dsgn-01, dsgn-02, dsgn-05, dark-mode, color-scheme]
requires: ["04-01", "04-02", "04-03", "04-04", "04-05", "04-06"]
provides:
  - light-only color-scheme metas in templates/email.html.j2 (email and web variants)
  - test_color_scheme_is_light_only
  - DSGN-02 / ROADMAP Phase 4 SC1 amended to the Phase 2 D-13 email order
affects: [templates/email.html.j2, tests/test_render.py, .planning/REQUIREMENTS.md, .planning/ROADMAP.md]
tech-stack:
  added: []
  patterns: ["light-only color-scheme hint, no dark-mode CSS"]
key-files:
  created: []
  modified:
    - templates/email.html.j2
    - tests/test_render.py
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
decisions:
  - "DSGN-02 is amended to the owner's Phase 2 D-13 order (trend before highlight); Figma frame 7:22 stays the earlier design reference with highlight before trend. The two orders are recorded as separate facts."
  - "Dark mode: only the two light-only metas are added (research mitigations 1-3). The v3 outlined otter set is deferred unless checkpoint D fails."
metrics:
  completed: 2026-11-04 (Task 1 only)
actuals:
  tasks: 1
  commits: 1
plan_head_before: e886344
plan_head_after: d85b72b
---

# Phase 4 Plan 07: Close Phase 4 in real inboxes (partial) Summary

Task 1 is done. DSGN-01 is recorded against Figma frame 7:22. DSGN-02 and ROADMAP SC1 now state the email's Phase 2 D-13 order. The email head carries light-only `color-scheme` metas, and a test asserts them. Tasks 2 and 3 wait for the owner.

## Task 1: DSGN-01 / DSGN-02 record and color-scheme metas (commit d85b72b)

### DSGN-01 evidence

- Frame: file `qyJcGii2MLHTbi4W9mPZkx`, frame `Newsletter / Web 640 (draft)`, **node 7:22**, width 640. It was derived from the mobile design's fonts, colors and component styles and approved by the owner in Phase 1.1 (`01.1-FIGMA-SPEC.md` line 3 and "Global").
- Brand and banner update on 2026-11-04, **orchestrator-reported**. The executor had no Figma MCP access (the server needs `/mcp` auth), so it could not run `get_metadata` itself. The orchestrator reports these changes, made with `use_figma` and confirmed with `get_screenshot`:
  - The top banner fill on node 11:186 is now the image of **node 34:711** (모닥로그_해달).
  - Brand texts on nodes 7:27, 7:133 and 15:193 read 모닥로그 AI 리포트 / 이번 주 리포트는 여기까지.
- The same banner ships in the email as `docs/assets/email/v2/otter-banner.jpg` (commit 450e1c8, from Figma node 34:711). v1 stays live for mail already sent.
- No new Figma work was done in this plan (D-04).

### Section order: two separate facts

1. **Figma frame 7:22 order** (`01.1-FIGMA-SPEC.md:27-28`): §5 Highlight (이번 주 바로 써볼 만한 것) comes before §6 Trend. The frame was not changed and does not have the email order.
2. **Shipped email order** (Phase 2 D-13, owner): banner, header, hero, greeting, **trend (트렌드 총평)**, **highlight (이번 주 바로 써볼 만한 것)**, Top 3, explainer (AI 기술 쉽게 보기), 4위~10위, closing, footer.

Proof of the email order only: `tests/test_render.py::SECTION_ORDER` and `test_all_eleven_sections_render_in_order_when_filled`:

```
PASSED tests/test_render.py::test_all_eleven_sections_render_in_order_when_filled
PASSED tests/test_render.py::test_font_family_count_in_worst_case
PASSED tests/test_render.py::test_worst_case_images_and_phase3_otters
PASSED tests/test_render.py::test_worst_case_under_byte_limit
PASSED tests/test_render.py::test_color_scheme_is_light_only[False]
PASSED tests/test_render.py::test_color_scheme_is_light_only[True]
6 passed, 97 deselected
```

### Amended text

- `REQUIREMENTS.md` DSGN-02: "Email sections in order: header + week range, personalized greeting, 트렌드 총평, 이번 주 바로 써볼 만한 것, Top 3 cards, AI 기술 쉽게 보기, 4위~10위 cards (…), footer (order per Phase 2 D-13, owner; the Phase 1.1 Figma frame 7:22 is the earlier design reference with highlight before trend)".
- `ROADMAP.md` Phase 4 SC1: only the section-order clause changed. It now says the email renders trend before highlight (Phase 2 D-13), and that frame 7:22 is the earlier design reference with highlight before trend.
- The DSGN-01/02 checkboxes stay unchecked. The phase is not complete, so the orchestrator ticks them at phase close.

### Dark-mode hints (D-16, research mitigations 1-3)

- After the viewport meta: `<meta name="color-scheme" content="light">` and `<meta name="supported-color-schemes" content="light">`. Both email and web variants get them, because they share the head.
- No dark-mode CSS. `prefers-color-scheme` appears 0 times in the template.
- The template header note has one new line (still template-version 9).
- Worst-case email is 78,390 B, with 13,770 B headroom under 92,160 B.

### Verification

- `uv run pytest -q`: 1264 passed
- `uv run ruff check .`: All checks passed
- `uv run ruff format --check newsletter tests`: 63 files already formatted
- `grep -c 'name="color-scheme" content="light"' templates/email.html.j2`: 1 (baseline 0)
- The `트렌드 총평, 이번 주 바로 써볼 만한 것` grep count is 1 in REQUIREMENTS.md and 1 in ROADMAP.md. `Phase 2 D-13` appears 1 time in REQUIREMENTS.md.

## Task 2: owner inbox check, light/dark (checkpoint D): done 2026-11-04

- mode=test run 41762276100 (success, commit 78e3350).
- The owner checked the inboxes and reported "확인해봤는데 괜찮고": overall OK. No per-client failure was reported, so no v3 dark-mode asset set is needed. The owner gave one overall verdict, not the per-item header details (A4/A5). Those stay unrecorded.
- 구독 해지 round trip: deferred. The Google setup (04-04 Task 3) is not done, so D-10 and D-12 stay verification-pending.
- Follow-up changes the owner asked for:
  - 웹에서 보기 was removed from the email header and footer (commit b3c48dd). Issue pages are still published on send and linked from the archive. WEB-01's "email links to it" now means the archive link (지난 호 보기) leads to every issue page.
  - The owner wants a subscribe form on the 지난 호 page. That is Phase 4.1 scope (SUBS-01), so the form is not turned on here.

## Task 3: owner mode=send and live web page: PENDING

The owner has not run it. Only the owner dispatches mode=send.

## Deviations from Plan

None. Figma `get_metadata` was unavailable, so the 7:22 brand and banner fact is recorded as orchestrator-reported. The plan allows this.

## Phase status

**verification-pending**: DSGN-05 (checkpoint D), D-10/D-12 (04-04 Google setup deferred), and the live half of WEB-01/WEB-02 (owner send).

## Self-Check: PASSED

- FOUND: templates/email.html.j2 (color-scheme meta count 1)
- FOUND: tests/test_render.py::test_color_scheme_is_light_only
- FOUND: commit d85b72b on HEAD
