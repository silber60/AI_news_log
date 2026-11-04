---
phase: 04-figma-design-email-template-web-archive
plan: 02
subsystem: web-archive
status: complete
tags: [web, render, verdicts, responsive]
requires: [04-01]
provides:
  - render.basis_rows(it) -> list[dict] (label, value, url)
  - render.basis_links(it) -> list[EvidenceLink]
  - email.html.j2 (v9) web-only basis macro, headline <title>, 680px media rule, wrap class, 지난 호 전체 보기 link
affects: [templates/email.html.j2, newsletter/stages/render.py]
tech-stack:
  added: []
  patterns: [code-built rows looped by the template, web-only context keys so the email pays no bytes]
key-files:
  created:
    - tests/test_web_issue.py
  modified:
    - newsletter/stages/render.py
    - templates/email.html.j2
decisions:
  - "class=\"wrap\" is written in web mode only (plan said email too, +13 B). The email's <style> is inlined and dropped, so the class does nothing there and test_no_style_block_and_tables_only keeps asserting no class= in the email"
  - "GPU basis value: '로컬 실행 <local_run> · 약 <ceil>GB · <fmt_params> 파라미터', known parts only, else 확인 필요; reuses enrich.fmt_params (the 모델 정보 size format)"
  - "License row links source_url only when it is on huggingface.co or github.com (T-04-05), same rule as the evidence line"
  - "Evidence line shows '근거 링크: 확인 필요' when a card has no HF/GitHub evidence"
  - "Web page adds a top data-section=\"back\" row with '← 지난 호 전체 보기' -> archive_url(); the existing footer '지난 호 보기' link stays"
metrics:
  duration: ~25 min
  completed: 2026-11-04
actuals:
  tokens: 4400   # chars/4 over the realized diff (17,592 chars)
  tasks: 3
  commits: 2
plan_head_before: 200607f9d02e411e9ad0ff05af1b2422391cac5b
plan_head_after: 72a52f231a2aec0c1a7d21d7177b19b6ee2c6fe6
---

# Phase 4 Plan 02: Web issue 판정 근거 Summary

The web issue page now shows an always-open 판정 근거 block under every card. Code builds the rows from Issue v4 fields: 상업 이용, 코드 라이선스, 가중치 라이선스, 바로 써보기, GPU and Claude/GPT (hidden on 해당 없음). Below the rows sit deduped HF/GitHub evidence links. The page has a headline title, a phone-width rule and a back link to the archive. The email does not change.

## What was built

- **render.py**: `basis_rows(it)` copies code verdicts and appends the stored `reason_ko` text ("<verdict> · <reason>"). Unknown values read 확인 필요, and Claude/GPT is omitted on 해당 없음. `basis_links(it)` merges commercial + poc + hardware evidence, dedupes by url in first-seen order and keeps only `verdicts.EVIDENCE_HOSTS`. `_context` passes both keyed by rank only when `web=True`; the email gets empty dicts.
- **email.html.j2 (v9, header note extended)**: a `basis(rank)` macro rendered inside `{% if web %}` after the verdict row and before the 논문 보기 links. One conditional `<title>` (`headline_ko · brand` on the web, `brand issue_id` in the email). The web-only `@media (max-width: 680px)` rule sits in the existing `<style>`, the 640 table gets `class="wrap"` on the web, and a top row adds `← 지난 호 전체 보기` linking to `archive_url`. No `|safe` and no script.
- Worst-case email: 78,098 B, unchanged (headroom 14,062 B).

## Tests

tests/test_web_issue.py has 15 tests. They cover row order and the 확인 필요 fallback, separate code and weights license rows with the source link, the name fallback, reason appending, the 해당 없음 hide, the GPU format (14GB ceil, 7B 파라미터), the evidence merge/dedupe/host filter, and a reason alone leaving the verdict 확인 필요. Web page tests check one block per card after the verdict, no block or back link in the email, title rules, a single back link to archive_url, the media rule and no script, humanize.lint on the fixed labels, every evidence href on HF/GitHub, and escaping of reason text. Full suite and ruff are green.

## Deviations from Plan

**1. [Rule 1 - Bug] wrap class is web-only**
- **Found during:** Task 2
- **Issue:** Adding `class="wrap"` to the email broke `test_no_style_block_and_tables_only` (no `class=` in email). The class has no effect in the inlined email anyway.
- **Fix:** `{% if web %} class="wrap"{% endif %}`. Acceptance grep still prints 1. The email bytes do not change, so tests/test_render.py needed no edit.
- **Commit:** 72a52f2

## Task 3: owner preview (done 2026-11-04)

Previews built (out/ is gitignored, docs/ and data/ untouched):
- Plan preview (W44 fixture, every verdict 확인 필요): out/web-preview/site/issues/2026-W44/index.html
- Extra preview with filled verdicts (odd ranks: 가능 + Apache-2.0 code license, 바로 가능, 7B / 17GB, Claude/GPT 해당 없음 hidden; even ranks: Claude/GPT 기법 적용 가능): out/web-preview-verdicts/site/issues/2026-W44/index.html

Owner answers: "Both ok" (2026-11-04). The orchestrator also checked the verdict preview at 375px: no sideways overflow, 판정 근거 in each of the 10 cards, the greeting is 구독자님, and there is no address on the page.

## Self-Check: PASSED

- FOUND: tests/test_web_issue.py, newsletter/stages/render.py (basis_rows, basis_links), templates/email.html.j2
- FOUND: f3e412b, 72a52f2
