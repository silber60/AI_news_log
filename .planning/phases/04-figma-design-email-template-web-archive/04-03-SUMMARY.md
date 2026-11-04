---
phase: 04-figma-design-email-template-web-archive
plan: 03
subsystem: web-archive
status: complete
tags: [web, github-pages, home, figma, archive]
requires: [04-01]
provides:
  - web.SUBSCRIBE_URL = None, web.PRIVACY_URL = None (D-09; Phase 4.1 sets them)
  - web.card(issue) -> {url, date, headline, top3, image, image_alt}
  - templates/web/_base.html.j2 (head, nav, footer) and templates/web/home.html.j2 (Figma 25:356)
  - regenerated docs/index.html
affects: [tests/test_web.py]
tech-stack:
  added: []
  patterns: [Jinja template inheritance for web pages, URL-gated hidden sections, data-section markers for order tests]
key-files:
  created:
    - templates/web/_base.html.j2
  modified:
    - newsletter/web.py
    - templates/web/home.html.j2
    - docs/index.html
    - tests/test_web.py
decisions:
  - "Hero image is v2 otter-banner.jpg (campfire otter, Figma node 34:711) via ASSET_BASE_URL; the frame's reading-otter hero is not exported and adding assets is out of scope"
  - "While SUBSCRIBE_URL is None the hero is a two-column copy + image row (no empty form card); with a URL the image moves under the copy and the form takes the right column, as in the frame"
  - "Footer is brand + '매주 월요일 오전 8시 발송 · 출처: Hugging Face Papers' only; the frame's 수신거부 clause is dropped (D-15, and the 04-01 PII scan forbids 수신거부 on web pages)"
  - "Archive section (eyebrow 지난 호, title 지금까지 보낸 메일) sits right after the sample section; cards in a 3-column grid, one column under 768px"
  - "Form email placeholder is '이메일 주소', not an address, so the PII email regex stays clean once forms turn on"
metrics:
  duration: ~35 min
  completed: 2026-11-04
actuals:
  tokens: 9000   # chars/4 over the realized diff
  tasks: 3
  commits: 3
plan_head_before: 200607f
plan_head_after: 1c51522
---

# Phase 4 Plan 03: Home page (Figma 25:356) Summary

The home page is now the Figma subscribe landing: nav (otter-tool logo + render.BRAND, 지난 호 → `#archive`), hero (tags, title, body, campfire otter), 매주 이런 걸 받아요 with two cards, a bannerless sample preview of the latest issue, the 지난 호 archive cards (newest first, date, headline, Top 3, #1 image when present), the wave-otter CTA and the footer. Subscribe forms, the nav 구독하기 button and the privacy link render only once `web.SUBSCRIBE_URL` / `web.PRIVACY_URL` are set.

## What was built

- **newsletter/web.py**: `SUBSCRIBE_URL`, `PRIVACY_URL` constants; public `card()` replaces `_card()` (`url` key, still relative `issues/<id>/`); `_home_context()` passes brand, cards, latest card, subscribe/privacy URLs, archive id/href (from `render.ARCHIVE_ANCHOR`), asset base, font link and `Markup(FONT_STACK)`.
- **templates/web/_base.html.j2**: `lang="ko"`, viewport, IBM Plex Sans KR link (`render.WEB_FONT_URL`), one `<style>` block (FONT_STACK, 1040px content column, brand colors #FF6B00 / #FFF6F0 / #EDF6FF / #303A83 / #F5F5F5), nav and footer. No JavaScript, no contact address.
- **templates/web/home.html.j2**: sections with `data-section` markers nav, hero, what-you-get, sample, archive, cta, footer. `subscribe_form()` macro used twice (hero, bottom CTA). `@media (max-width: 767px)` stacks every row; all grid tracks use `minmax(0, 1fr)` so images and long titles do not widen a column.
- **docs/index.html**: regenerated with `uv run python -m newsletter site` (zero committed issues, so the sample shows its static copy and the archive shows the empty state).

## Copy

Taken from frame 25:356 (read off figma-25-356.png; Figma MCP was not authorized in this session): tags, hero title and body, 매주 이런 걸 받아요 / sub, both card titles and bodies, sample eyebrow / title / body / 전체 지난 호 보기 →, form title, CTA title. Written here: archive heading 지금까지 보낸 메일, sample empty state (첫 호를 준비하고 있어요 / 첫 메일이 나가면 그 호를 여기에서 바로 읽을 수 있어요.), preview link 이번 호 읽어 보기 →, consent and note lines of the hidden form. All pass humanize.lint with no hard code. Exempt as owner Figma copy: the hero title (lint flags `significance` on 꼭 알아야 할) and the CTA line with 👋.

## Tests (tests/test_web.py)

Task 1: card fields; archive newest first with Top 3 and date; image only when items[0].image exists; no form / 구독하기 / 개인정보 처리방침 while URLs are None; two forms posting to the URL plus nav CTA and privacy link when set; empty state inside the archive. Task 2: section order, exactly two what-you-get cards and no 바로 써볼 만한 것, sample has no otter-banner and links the latest issue and the anchor, nav 지난 호 → anchor, no `<script`, 767px media rule, font link and FONT_STACK, one otter-banner.jpg, no mailto, footer content, no literal brand in templates, no old brand in any committed docs html, copy rendered, humanizer on sentences and labels. `uv run pytest -q` green; ruff check and format clean; `git diff --quiet HEAD -- docs/assets` holds.

## Commits

- 4f9ba97 feat(04-03): home archive cards newest first, subscribe slots hidden
- 176c89f feat(04-03): home page follows the Figma 25:356 subscribe landing
- 1c51522 fix(04-03): keep home grid columns inside narrow screens

## Task 3: owner preview, checkpoint B (done 2026-11-04)

Preview built at out/home-preview/site/index.html (gitignored) from 2026-W44 (fixture) and a 2026-W43 copy (dates one week back, new headline, #1 image removed to show the no-image card). docs/ and data/ unchanged. Owner answers: "Both ok" (2026-11-04), all six checklist items accepted. The orchestrator checked the preview at 375px: no element wider than the viewport, #archive present with 2 cards, no form or input, and no old brand.

## Deviations from Plan

- [Rule 1 - Bug] Narrow-screen overflow risk: grid tracks `1fr` let a 544px image or a long title widen a column; switched to `minmax(0, 1fr)` and capped the solo CTA column (commit 1c51522).
- `_card` renamed to public `card` with key `url` (the plan's name); the href stays relative, so the 04-01 tests are unchanged.

## Known Stubs

None. Hidden subscribe slots are intentional (D-09, Phase 4.1).

## Threat Flags

None. T-04-06: autoescape on; image src only from ItemImage HttpsUrl. T-04-07: no `<form>` while SUBSCRIBE_URL is None (tested).

## Self-Check: PASSED

All files exist; commits 4f9ba97, 176c89f, 1c51522 are on exec-04-03.
