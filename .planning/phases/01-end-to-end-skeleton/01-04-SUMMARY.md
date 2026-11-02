---
phase: 01-end-to-end-skeleton
plan: 04
subsystem: render
status: complete
tags: [jinja2, css-inline, email-html, plain-text, subject, size-gate]
requires: ["01-01"]
provides:
  - "Phase 1 640px table card email (template v2) with AI_TYPE_COLORS badges"
  - "90 KB UTF-8 byte gate raising RenderTooLarge(bytes=N)"
  - "Plain-text alternative v2 that mirrors every card field"
  - "D-01/D-03 subject with SUBJECT_TITLE_MAX = 32 and CR/LF stripping"
affects: [01-05, 01-06]
tech-stack:
  added: []
  patterns:
    - "Font stack passed as Markup and written on every text <td>, plus a <style> block that css_inline inlines and drops"
    - "data-card=\"{rank}\" marker on each card table for tests"
key-files:
  created: [tests/test_render.py]
  modified: [newsletter/stages/render.py, templates/email.html.j2, templates/email.txt.j2]
decisions:
  - "Subject title cap is 32 chars. A cut title gets rstrip() and then '…'."
  - "No class= attributes in the template. All layout styles are inline, and the style block holds only element defaults."
  - "AI 종류 badge palette: LLM blue, 비전 green, 멀티모달 violet, 음성 amber, 에이전트 rose, 이미지/비디오 생성 pink, 기타 grey"
metrics:
  duration: "~20 min"
  completed: 2026-11-02
estimate:
  tokens: 60000
  tasks: 3
actuals:
  tokens: 5200   # chars/4 over the 20,856-char diff of the 4 changed files
  tasks: 3
  commits: 5
plan_head_before: d927d0f2fb31048355f1942731f0072b0f31e135
plan_head_after: 92877c2
---

# Phase 1 Plan 04: Phase 1 Card Email, Size Gate, Text Part and Subject Summary

The build now renders the full Phase 1 card email (DSGN-03). It has a 640px tables-only layout and a header with the KST week label. Each of the N cards shows rank, upvotes, a colored AI 종류 text badge, title_ko, title_en, affiliation when present, 한줄 요약, up to 2 ideas, and only the links that exist. Every text cell carries the Korean system font stack inline. Rendering raises `RenderTooLarge("bytes=N")` at 90 KB (UTF-8 bytes). The plain-text part mirrors every field (DSGN-04). The subject follows D-01/D-03 and caps the title at 32 characters.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 (tracer) | Full Phase 1 card email from a built week | 8ed7892 |
| 2 RED | Email-safe markup, link omission, escaping tests | b66c2df |
| 2 GREEN | Drop class attributes, styles inline | 9bf1057 |
| 3 RED | 90 KB gate, text part, subject tests | c4acaf1 |
| 3 GREEN | Byte gate, text template v2, capped subject | 92877c2 |

## Recorded facts

- W44 fixture `email.html` is **33,629 bytes** (UTF-8), under the 92,160-byte limit. Plan 01's tracer version was 40,832 bytes.
- W44 test subject: `[TEST] [AI 주간 모델 브리프] 이번 주 1위: PDRVLA: A Vision-Language-Action… 외 9건`. The fixture titles are 48 characters, so the cap applies.
- Render signatures are unchanged: `render_html(issue, greeting)`, `render_text(issue, greeting)`, `build_subject(issue, mode)`.

## Verification

- `uv run pytest -q tests/test_render.py tests/test_e2e.py tests/test_schema.py`: 41 passed, exit 0. That is 19 render, 4 e2e and 18 schema tests.
- `uv run ruff check` and `uv run ruff format --check newsletter tests` both pass.
- All acceptance greps pass. Both templates contain `template-version: 2` once. `render.py` has `AI_TYPE_COLORS` and `select_autoescape`, and `90 \* 1024`, `encode("utf-8")` and `SUBJECT_TITLE_MAX = 32` once each. `RenderTooLarge` is present. The HTML template has 0 `<div`. The tests import `HTMLParser`.

## TDD Gate Compliance

- Task 2: Task 1's tracer already satisfied most of the behaviors, so the first test run was green. I added a `class=`-free assertion, which gave a real RED in b66c2df (`assert 'class=' not in out` failed). GREEN followed in 9bf1057.
- Task 3: RED in c4acaf1 (ImportError: `MAX_EMAIL_BYTES` did not exist). GREEN in 92877c2. Refactor: none.

## Deviations from Plan

1. **[Rule 2 - Correctness] No `class=` attributes in the HTML.** This makes the "no class= dependence for layout" behavior checkable. The muted and card styles moved inline. Commit 9bf1057.
2. **`markupsafe.Markup` import in render.py.** The font stack is a trusted constant. Wrapping it in Markup stops autoescape from turning its quotes into `&#39;` inside `style=`. markupsafe is already a locked transitive dependency of jinja2, so pyproject.toml and uv.lock are unchanged.
3. The tracer test asserts the `data-card=` marker count, which I added as a card attribute. It does not count `#N` text.

No package installs. No changes to the schema, errors, week, pipeline, delivery or conftest.

## Threat Model Coverage

- T-01-13: autoescape stays on (`select_autoescape`). Tests inject `<script>` into title_ko and `<b>` into the greeting, and both come out escaped.
- T-01-14: only schema-validated https URLs are rendered. Links that are absent are omitted, and the tests check this.
- T-01-15: the byte gate raises before send. The message is `bytes=N` only.
- Subject CR/LF is stripped (header injection guard), and this is tested.

## Known Stubs

None. Verdicts, trend, highlights and explainer are deliberately not rendered in Phase 1. The explainer `{% if %}` slot renders nothing (D-16).

## Self-Check: PASSED

- All 4 files exist: newsletter/stages/render.py, templates/email.html.j2, templates/email.txt.j2 and tests/test_render.py.
- Commits 8ed7892, b66c2df, 9bf1057, c4acaf1 and 92877c2 are ancestors of HEAD.
