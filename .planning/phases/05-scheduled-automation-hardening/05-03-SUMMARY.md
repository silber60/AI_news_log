---
phase: 05-scheduled-automation-hardening
plan: 03
subsystem: delivery
status: complete
tags: [ledger, dedupe, hmac, re-run-safety, DLVR-05]
requires:
  - 05-01 (always() ledger artifact upload and always-run publish commit of data/ledger/; out/report.json)
  - 04.2-01 (send_messages over Resend SMTP; connection code owned by 4.2)
provides:
  - newsletter/ledger.py (LEDGER_SCHEME hmac-sha256-ledger-v1, ledger_dir, key, load, save)
  - send_messages(..., on_sent=None) per-message hook
  - deliver send mode ledger skip filter, per-message ledger write, skipped_ledger in result, report.json and counts log
  - autouse NEWSLETTER_LEDGER_DIR redirect for every test
affects: [05-04 (run report can show skipped_ledger), 05-05 (live proof: second run sends 0)]
tech-stack:
  added: []
  patterns:
    - "Ledger key = HMAC-SHA256(UNSUBSCRIBE_TOKEN_SECRET, 'ledger-v1:' + email.strip().lower()) hex64"
    - "data/ledger/<week>.json = {version 1, issue_id, scheme, sent: sorted keys}, written atomically (.tmp + os.replace) after every message"
    - "Mismatched or unreadable ledger file raises DeliveryError before any message (fail closed)"
key-files:
  created:
    - newsletter/ledger.py
    - tests/test_ledger.py
  modified:
    - newsletter/delivery/send.py
    - newsletter/delivery/deliver.py
    - tests/conftest.py
    - tests/test_delivery.py
    - tests/test_redaction.py
    - tests/test_guards.py
    - .planning/REQUIREMENTS.md
decisions:
  - "Ledger key is keyed HMAC-SHA256 with the ledger-v1: domain prefix (owner A1), never equal to the unsubscribe token"
  - "Send mode always requires UNSUBSCRIBE_TOKEN_SECRET (even with no endpoint), read before any list fetch or SMTP connection"
  - "Ledger filter runs after the unsubscribe filter; skipped_ledger counted separately from unsubscribed"
  - "Ledger written per message via on_sent callback; commit to main rides 05-01's always() artifact and publish job"
metrics:
  duration: ~25m
  completed: 2026-11-04
estimate:
  tokens: 70000
  tasks: 2
actuals:
  tokens: 7200
  tasks: 2
  commits: 5
plan_head_before: 999d671
plan_head_after: d92d13be1bc6887957353b1c1d3aaf648de89f41  # last code commit; the SUMMARY docs commit follows
---

# Phase 5 Plan 03: Send Ledger Summary

Each reader who gets a week's issue is recorded in `data/ledger/<YYYY-Www>.json` as a 64-hex HMAC-SHA256 key, keyed with the unsubscribe secret. The file is rewritten atomically right after every successful message. A re-run skips everyone already recorded, so a re-run after a mid-send failure mails only the rest, and a re-run after a full send mails nobody and still ends with outcome `sent`.

## Tasks

| Task | Name | Commits |
|------|------|---------|
| 1 | Tracer: two readers, ledger with two keys, re-run sends nothing | 0cf7dad (RED), 21216f0 (feat) |
| 2 | Partial-failure resume, test-mode isolation, fail-closed secret, existing tests updated | 4b8a052 |

Tracer gate: `uv run pytest -q tests/test_ledger.py` re-run green after Task 1 before expanding.

## What changed

- `newsletter/ledger.py`: `key()` uses the same normalization as `unsubscribe.token` plus the `ledger-v1:` prefix. `load()` returns an empty set when the file is missing. It raises `DeliveryError` ("ledger unreadable" / "ledger mismatch") on another issue_id, scheme or version, or on bad JSON. `save()` writes sorted keys through the local `_write_atomic`; `store.write_json_atomic` from 05-02 is not used.
- `send.py`: adds only the `on_sent: Callable[[int], None] | None` keyword and one call after each successful `send_message`. Host, port, login and From are untouched; the acceptance grep is empty. If the ledger write raises OSError, the existing handler turns it into a redacted DeliveryError and sending stops.
- `deliver.py` `_run_send`: `_env("UNSUBSCRIBE_TOKEN_SECRET")` is read first, then the lists. `ledger.load` runs after the lists, and the skip filter comes after the unsubscribe filter. Keys are kept in a list parallel to the messages, and the `record(i)` callback adds a key and saves. The result and report.json get `skipped_ledger`. The log line is now `mode=send recipients=%d unsubscribed=%d skipped_ledger=%d sent=%d skipped_rows=%d`. Test mode never touches the ledger.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ledger.py docstring tripped test_cli secret-name guard**
- **Found during:** Task 1 full-suite run
- **Issue:** `test_only_delivery_package_names_delivery_secrets` forbids the literal `UNSUBSCRIBE_TOKEN_SECRET` outside `newsletter/delivery/`. The ledger.py docstring named it.
- **Fix:** Reworded the docstring to say "unsubscribe token secret; deliver passes the secret in". `tests/test_cli.py` was not edited, because 05-02 owns it in this wave.
- **Commit:** 21216f0 (docstring also reworded in d92d13b so `ledger-v1:` appears only in code)

**2. [Rule 3 - Blocking] tests/test_guards.py also needed the secret**
- **Found during:** Task 2
- **Issue:** The plan listed test_delivery, test_redaction and test_cli. The 05-01 `creds` fixture in test_guards.py also runs send mode, and its expected dicts lacked `skipped_ledger`.
- **Fix:** Added `UNSUBSCRIBE_TOKEN_SECRET` to the `creds` fixture and `"skipped_ledger": 0` to the two expected dicts. No assertion was removed. The file is not in 05-02's set.
- **Commit:** 4b8a052

### Test updates (planned)
- test_delivery.py: the `send_env` fixture sets the secret. `test_send_without_endpoint_fetches_nothing_and_mails_everyone` now sets the secret instead of deleting it, and still asserts no fetch, mail to everyone and a mailto-only header. Expected dicts and log strings gained `skipped_ledger`. The secret grep count went from 6 to 7.
- test_redaction.py: the `ready` fixture sets the secret, and the two log-string assertions gained `skipped_ledger=0`.
- test_cli.py: no change needed.

### TDD note
Task 2's new tests passed on first run because Task 1 already implemented the behavior (partial-failure resume, test-mode isolation, fail closed). They are regression tests for those paths.

## Verification

- `uv run pytest -q`: 1461 passed
- `uv run ruff check .` clean; `uv run ruff format --check newsletter tests`: 72 files already formatted
- `git status --porcelain data/ledger` is empty after the suite
- Acceptance greps: `ledger-v1:` 1 in ledger.py; `on_sent` 4 in send.py; `skipped_ledger` 5 in deliver.py; `NEWSLETTER_LEDGER_DIR` 1 in conftest; `HMAC-SHA256 email hash` 1 in REQUIREMENTS.md

## Threat Flags

None beyond the plan's threat register. T-05-11 to T-05-14 are mitigated and tested: keyed hash, key != token, mismatched ledger fails closed, and no address or hex64 in logs.

## Known Stubs

None.

## Self-Check: PASSED
- FOUND: newsletter/ledger.py, tests/test_ledger.py
- FOUND commits: 0cf7dad, 21216f0, 4b8a052, d92d13b
