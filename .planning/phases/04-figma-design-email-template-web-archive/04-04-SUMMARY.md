---
phase: 04-figma-design-email-template-web-archive
plan: 04
subsystem: delivery
status: checkpoint   # Task 3 (owner Google setup, checkpoint C) pending
tags: [unsubscribe, hmac, apps-script, dlvr-04]
requires: ["04-01"]
provides:
  - "newsletter/delivery/unsubscribe.py: TOKEN_LEN, TOKEN_RE, UNSUBSCRIBE_ENDPOINT (None), token(), fetch_unsubscribed()"
  - "apps_script/Code.gs: doGet (confirm only), doPost (button / one-click / action=list), unsubscribe, record_, list_, safeEq_, tokenFor_, setup, selfTest"
  - "apps_script/README.md: Korean owner setup steps 1-11 and the never-새-배포 rule"
affects: ["04-05 (headers, footer link, send-time filter)", "04-07"]
tech-stack:
  added: []
  patterns: ["fail-closed fetch with class-name-only error text", "shared cross-language test vector"]
key-files:
  created:
    - newsletter/delivery/unsubscribe.py
    - apps_script/Code.gs
    - apps_script/README.md
    - tests/test_unsubscribe.py
  modified: []
decisions:
  - "Token scheme: owner chose approve (32 hex), 2026-11-04. Link https://silber60.github.io/AI_news_log/unsubscribe/?t=<token>"
  - "CONFIRM_HTML passes the token through a quoted data-t attribute, not a scriptlet in a JS context"
  - "doPost merges the form-urlencoded body when e.parameter has no action (A9 fallback)"
metrics:
  completed: 2026-11-04
commits: 2
plan_head_before: 200607f
plan_head_after: e03ea68
actuals:
  tokens: 9000
  tasks: 2   # of 3; Task 3 is the owner checkpoint
  commits: 2
---

# Phase 4 Plan 04: Unsubscribe backend Summary

HMAC-SHA256 32-hex unsubscribe token implemented identically in Python and Apps Script (shared vector `f290b8e448576cf84f63ac2b465c3e65`), a fail-closed list fetch that follows the Apps Script 302, and a confirm-only Apps Script web app with a Korean owner setup guide. The endpoint stays `None` until the owner deploys.

## Task 1: Token scheme decision

Owner chose **approve (32 hex)**, 2026-11-04. `TOKEN_LEN = 32`, link `https://silber60.github.io/AI_news_log/unsubscribe/?t=<token>`. Test vectors unchanged from research.

## Task 2: Implementation (TDD)

- RED `dfde4d5`: tests/test_unsubscribe.py failed at collection (no `newsletter.delivery.unsubscribe`).
- GREEN `e03ea68`: module, Code.gs, README. Full suite and ruff green.

What the tests cover: both research vectors, normalization, TOKEN_RE strictness, `UNSUBSCRIBE_ENDPOINT is None`, POST→302→GET chain with only valid hex ids kept, key only in the POST body, fail closed on 500 / non-JSON / missing or null `ids` / forbidden / list body / 404 after redirect / ConnectError (error text has no key, URL or id, and the cause is suppressed), caplog clean, and static checks on Code.gs (same vector once, one `Logger.log`, no `console.`, doGet never writes, only example.com addresses, LockService, constant-time compare, form-body fallback) and README (brand Sheet name, 새 배포 rule, old brand absent). The fixed Korean sentences in Code.gs pass `humanize.lint` with no hard code.

## Task 3: Owner Google setup (checkpoint C)

Pending. The owner follows apps_script/README.md. Until the owner reports, D-10 and D-12 are verification-pending, and research assumptions A1, A2, A3 and A9 are unconfirmed.

## Deviations from Plan

**1. [Rule 1 - Bug] Token reaches the confirm script through an attribute.** The plan asked to quote `<?= t ?>` as a JS string inside `<script>`. HtmlService escapes printing scriptlets by context and may add its own quotes in a JS context, which would break a hand-quoted literal. The button now carries `data-t="<?= t ?>"` (HTML-attribute escaping) and the script calls `.unsubscribe(b.getAttribute("data-t"))`. A test asserts no scriptlet appears inside `<script>`. Commit e03ea68.

**2. [Rule 2 - Missing] Failure handler on the Apps Script confirm page.** `google.script.run` had no failure path, so the button stayed disabled with no message. Added `withFailureHandler` that re-enables it and shows "잠시 후 다시 눌러 주세요." (lint-checked). Commit e03ea68.

**3. [Rule 1 - Bug] doGet set no `site`.** The confirm page now has a home link, so `doGet` sets `tpl.site`. Commit e03ea68.

**4. Test adjustment.** Code.gs contains the reserved example.com test-vector address by design, so the "no address" test allows only `@example.com`. `TOKEN_SECRET` is named in the header comment but not yet read (Phase 4.1 welcome mail); the test checks the header lists all three property names.

## Threat Flags

None beyond the plan's threat model.

## Self-Check: PASSED

- FOUND: newsletter/delivery/unsubscribe.py, apps_script/Code.gs, apps_script/README.md, tests/test_unsubscribe.py
- FOUND: dfde4d5, e03ea68
