---
phase: 04-figma-design-email-template-web-archive
plan: 05
subsystem: delivery
status: complete
tags: [unsubscribe, list-unsubscribe, rfc8058, dlvr-04, fail-closed]
requires: ["04-02", "04-04"]
provides:
  - "render_html / render_text keyword-only unsubscribe_url; footer 구독 해지 link (HTML and text)"
  - "send.build_message(list_unsubscribe=None, one_click=False) with policy.clone(max_line_length=998)"
  - "deliver._unsubscribe_parts(addr, user, secret) -> (token, link, header); _token_secret()"
  - "send-mode fail-closed list filter and counts-only log line"
  - "Deliver step env UNSUBSCRIBE_TOKEN_SECRET and send-gated UNSUBSCRIBE_LIST_KEY"
affects: ["04-07 (inbox check of headers)", "04-04 Task 3 (setting UNSUBSCRIBE_ENDPOINT turns the link and https header on)"]
tech-stack:
  added: []
  patterns: ["raw-bytes header assertions", "fail closed before SMTP", "endpoint-None gate"]
key-files:
  created: []
  modified:
    - newsletter/stages/render.py
    - templates/email.html.j2
    - templates/email.txt.j2
    - newsletter/delivery/send.py
    - newsletter/delivery/deliver.py
    - .github/workflows/newsletter.yml
    - tests/test_render.py
    - tests/test_delivery.py
    - tests/test_workflow_static.py
    - tests/test_cli.py
    - tests/test_redaction.py
decisions:
  - "run_deliver('send') result dict gains an unsubscribed count"
  - "Endpoint None: no token secret, no list key and no list fetch are required; header is mailto only"
  - "Text template keeps the None-case output byte-identical (구독 해지 line added only when a link exists)"
metrics:
  completed: 2026-11-04
commits: 6
plan_head_before: d6c9f0f
plan_head_after: db8c40a
actuals:
  tokens: 14000
  tasks: 3
  commits: 6
---

# Phase 4 Plan 05: Unsubscribe in every message Summary

Every test and send message now carries an unfolded `List-Unsubscribe` header (mailto always, the Apps Script https target plus `List-Unsubscribe-Post` once the endpoint exists), each reader's footer gets a personal 구독 해지 link, and send mode skips unsubscribed tokens and fails closed before SMTP if the list cannot be read.

## Tasks

| Task | RED | GREEN | What |
|------|-----|-------|------|
| 1 Footer link | 3c32e95 | e2173b0 | `unsubscribe_url` kwarg; link after 웹에서 보기 · 지난 호 보기; 수신거부 line kept; web copy forced to None |
| 2 Headers | b84d0de | 9fbe5ca | `build_message` headers + CR/LF strip + `max_line_length=998`; test mode uses TEST_RECIPIENT's token, no list fetch |
| 3 Filter + secrets | 116a953 | db8c40a | fetch list first when endpoint set; skip by token; counts log; Deliver-only secrets, list key send-gated |

## Behavior with UNSUBSCRIBE_ENDPOINT = None (current state)

- Header: `List-Unsubscribe: <mailto:SMTP_USER?subject=unsubscribe>` only, no `-Post`.
- No 구독 해지 link in either part; 수신거부 reply line stays.
- `UNSUBSCRIBE_TOKEN_SECRET` / `UNSUBSCRIBE_LIST_KEY` are not read; no HTTP request (respx asserts zero calls).

With the endpoint set (tests monkeypatch a 120-char URL): header `<mailto:…>, <ENDPOINT?t=token>` on one raw line with no `=?utf-8?`, `List-Unsubscribe-Post: List-Unsubscribe=One-Click`, footer link `https://silber60.github.io/AI_news_log/unsubscribe/?t=<32 hex>`. Missing token secret (test or send) or list key (send), list status 500, non-JSON body or connect error all raise `DeliveryError` with zero SMTP connections; through the CLI this writes `status.json {"stage":"deliver","error_class":"DeliveryError"}`, so the Failure notice step runs.

## Size

Worst case with a 64-hex link (longest token option): **78,293 B**, headroom 13,867 B under 92,160.

## Deviations from Plan

**1. [Rule 1 - Bug in plan/research] Body encoding expectation.** The plan said "HTML part still base64 and text part 8bit as before". At HEAD the W44 message is text `base64`, HTML `quoted-printable` (lines exceed 78 bytes under policy.default). The test instead asserts the real invariant: encodings equal those of the same parts built without the header, and no raw line exceeds 998. Commit 9fbe5ca.

**2. [Rule 3 - Blocking] tests/test_redaction.py updated.** Its counts-only test asserted the old log line `recipients=1 sent=1 skipped_rows=0`; now `recipients=1 unsubscribed=0 sent=1 skipped_rows=0`. File not in the plan's list. Commit 116a953.

**3. Result dict.** `run_deliver("send")` returns `unsubscribed` too; the existing one-message-per-recipient test was updated. Zero remaining recipients also logs `mode=send nothing to send after unsubscribe filter` (no data).

**4. Text template trailing newline.** The 구독 해지 line is prefixed with its newline inside the `if`, so the None-case text output is unchanged byte for byte.

## Known Stubs

- `newsletter/delivery/unsubscribe.py` `UNSUBSCRIBE_ENDPOINT = None` (from 04-04): intentional until the owner finishes 04-04 Task 3; setting it enables the link, https header and list filter with no other code change.

## Threat Flags

None beyond the plan's threat model (T-04-12..15 mitigated and tested).

## Self-Check: PASSED

- FOUND: all modified files; commits 3c32e95, e2173b0, b84d0de, 9fbe5ca, 116a953, db8c40a on exec-04-05
- `uv run pytest -q` green; `uv run ruff check .` and `uv run ruff format --check newsletter tests` clean
