---
phase: 04-figma-design-email-template-web-archive
plan: 06
subsystem: web
status: complete
tags: [unsubscribe, web, dlvr-04, d-12]
requires: ["04-03", "04-04"]
provides:
  - "templates/web/unsubscribe.html.j2: /unsubscribe/?t=<token> confirm page"
  - "web.build_site writes docs/unsubscribe/index.html every run (endpoint + TOKEN_LEN)"
  - "docs/unsubscribe/index.html committed; freshness test covers it"
affects: ["04-05 (footer link lands here)", "04-07"]
tech-stack:
  added: []
  patterns: ["endpoint passed to inline JS via autoescaped data- attribute", "token regex built from TOKEN_LEN"]
key-files:
  created:
    - templates/web/unsubscribe.html.j2
    - docs/unsubscribe/index.html
  modified:
    - newsletter/web.py
    - templates/web/_base.html.j2
    - tests/test_web.py
decisions:
  - "Endpoint None: page shows only 메일에 '수신거부'라고 회신해 주세요. (no form, no script, no noscript)"
  - "_base gets home_href (default ./) and a head block so the page one level down links ../ and ../#archive and can add noindex"
  - "Unsubscribe page carries no subscribe CTA (subscribe_url forced None)"
metrics:
  completed: 2026-11-04
commits: 3
plan_head_before: d6c9f0f6bb93fadbf25e266ca6b058667c2cc93e
plan_head_after: d9ca565c13ebb4468a46f769410363898e1d0b68
actuals:
  tokens: 4500   # chars/4 over the realized diff (~18 KB)
  tasks: 2
  commits: 3
---

# Phase 4 Plan 06: /unsubscribe/ confirm page Summary

Branded `/unsubscribe/` page on the one site: loading it writes nothing, and only the 구독 해지 button POSTs to the Apps Script endpoint with `?t=<token>` in the action URL. While `UNSUBSCRIBE_ENDPOINT` is `None` (owner Google setup pending) the page shows only the 수신거부 reply line.

## What was built

- `templates/web/unsubscribe.html.j2` extends `_base.html.j2` (same nav and footer, brand from `render.BRAND`, `noindex`).
  - With an endpoint, it renders a hidden POST form with heading 구독을 해지할까요?, the line 버튼을 누르면 다음 주부터 메일이 가지 않아요., a hidden `t` input and a 구독 해지 button. It also renders a hidden error line 링크가 올바르지 않아요. 받으신 메일의 링크를 다시 눌러 주세요. and a `<noscript>` reply line.
  - The inline script lowercases `t` from `URLSearchParams(location.search)`. If it matches `^[0-9a-f]{32}$` (built from `TOKEN_LEN`), the script sets the input with `.value`, sets `form.action = data-endpoint + "?t=" + t` and reveals the form. Otherwise it reveals the error line. The script has no `innerHTML` and no `.submit(`.
  - Without an endpoint, the page shows only the reply line.
- `web.build_site` renders the page to `docs/unsubscribe/index.html` on every run and returns it with the written paths. With an empty archive, the CLI now logs `pages=2`; with one issue, it logs `pages=3`.
- `docs/unsubscribe/index.html` is generated and committed. `pages.yml` redeploys `docs/` when the owner pushes, so the page goes live without a send. After the owner sets `UNSUBSCRIBE_ENDPOINT`, run `uv run python -m newsletter site` and commit. `test_committed_site_is_fresh` fails CI until that is done.

## Commits

- `a2841b2` test(04-06): failing tests (RED: 8 new tests failed, no template)
- `e0920f0` feat(04-06): confirm page, base tweaks, build_site wiring (GREEN)
- `d9ca565` chore(04-06): generated docs/unsubscribe/index.html

## Verification

`uv run pytest -q` all passed; `uv run ruff check .` and `uv run ruff format --check newsletter tests` clean. Acceptance greps: heading count 1, `innerHTML` 0, `unsubscribe/index.html` in web.py 1, no 32-hex run in the committed page, `docs/assets` unchanged.

## Deviations from Plan

**1. [Rule 1 - Bug] Nav links from a page one level down.** `_base.html.j2` hard-coded `href="./"` for the logo, and home passes `#archive`. On `/unsubscribe/` these would point back at the page itself. I added `home_href` (default `./`) and passed `../` and `../#archive` from `_unsubscribe_context`. Home bytes are unchanged, and the freshness test still passes.

**2. [Rule 2 - Missing] `head` block in `_base.html.j2`.** It holds the plan's `meta robots noindex`. The base header comment no longer says the site has no JavaScript at all: the confirm page adds the only script.

**3. Existing test updates (test_web.py).** `build_site` now writes 3 pages, so `set(written)`, `len(files)` and the `web=site pages=N` log asserts moved from 2 to 3. In the old PII scan, the "no 구독 해지 button / no 수신거부" checks skip the confirm page, because that page holds both by design. The email-address and token checks still cover every page. `unsubscribe.html.j2` joined the no-literal-brand template check.

**4. Extra tests beyond the plan's behavior list.** One test checks that a hostile endpoint string is autoescaped. Another checks that the endpoint never appears inside `<script>`.

## Known Stubs

None. The `None` endpoint branch is the intended interim state until the 04-04 owner checkpoint is done.

## Threat Flags

None beyond the plan's threat model. T-04-16 and T-04-17 are mitigated and tested.

## Self-Check: PASSED

- FOUND: templates/web/unsubscribe.html.j2, docs/unsubscribe/index.html
- FOUND: a2841b2, e0920f0, d9ca565
