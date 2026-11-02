---
phase: 01-end-to-end-skeleton
plan: 05
subsystem: delivery
status: complete
tags: [smtp, subscribers, redaction, cli, notify]
requires: ["01-01"]
provides:
  - "deliver --mode send (SUBSCRIBERS_CSV, personalized greeting, one message per recipient)"
  - "load_subscribers / parse_subscribers / display_name"
  - "top-level CLI failure handler + out/status.json"
  - "notify-failure --mode test|send (owner-only notice, D-13)"
affects: ["01-06 (workflow uses notify-failure and status.json)"]
tech-stack:
  added: []
  patterns:
    - "SMTP errors converted to DeliveryError(class + code) raised outside the except block, from None"
    - "CLI prints stage=<stage> error=<Class> only; traceback gated on NEWSLETTER_DEBUG=1"
key-files:
  created:
    - newsletter/delivery/subscribers.py
    - newsletter/delivery/notify.py
    - subscribers.example.csv
    - tests/test_delivery.py
    - tests/test_subscribers.py
    - tests/test_greeting.py
    - tests/test_redaction.py
    - tests/test_cli.py
  modified:
    - newsletter/delivery/deliver.py
    - newsletter/delivery/send.py
    - newsletter/__main__.py
decisions:
  - "Duplicate emails (case-insensitive) count toward skipped_rows along with invalid rows"
  - "notify-failure failures print stage=notify-failure and do not overwrite out/status.json, so the original failure status survives for the workflow"
  - "No ::add-mask:: lines are emitted; the code never prints addresses or names (plan discretion)"
  - "send_messages gained an optional pause kwarg (default 0); deliver passes SEND_PAUSE_SECONDS=1.0 in send mode"
metrics:
  duration: "~4 min"
  completed: 2026-11-02
actuals:
  tokens: 8700
  tasks: 3
  commits: 5
plan_head_before: d927d0f
plan_head_after: 4c1dfc4
---

# Phase 1 Plan 05: Delivery send mode, redaction and failure notice Summary

`deliver --mode send` now reads the SUBSCRIBERS_CSV secret (plain, BOM, or base64 of UTF-8/UTF-8-BOM/CP949), greets each subscriber as `<name>님` in the body only, and sends one multipart message per recipient over a single SMTP_SSL 465 connection. SMTP failures surface only as `stage=deliver error=DeliveryError` plus out/status.json. `notify-failure` mails the owner a plain-text notice with stage, error class and run URL.

## Tasks

| # | Task | Commits |
|---|------|---------|
| 1 | Send mode tracer: 홍길동 receives a mail greeting 홍길동님 | dfe693d |
| 2 | CSV decoding robustness + greeting normalization (TDD) | b78cd8f (RED), a1c0ab7 (GREEN) |
| 3 | Redaction, CLI failure handler, notify-failure, build secret isolation (TDD) | 5e325e5 (RED), 4c1dfc4 (GREEN) |

## Verification

- `uv run ruff check`: all checks passed. `ruff format` applied to touched files.
- Gate: `uv run pytest tests/test_delivery.py tests/test_subscribers.py tests/test_greeting.py tests/test_redaction.py tests/test_cli.py tests/test_e2e.py tests/test_schema.py` gave 69 passed. The full suite in this worktree also gave 69 passed.
- `grep -rn set_debuglevel newsletter/` finds nothing. Only `newsletter/delivery/` names SMTP_USER, SMTP_PASSWORD, SUBSCRIBERS_CSV or TEST_RECIPIENT.
- `subscribers.example.csv` is tracked through the `!subscribers.example.csv` rule, and `subscribers.csv` is ignored by `subscribers*.csv`.
- Tracer gate: Task 1's verify ran again end to end after Tasks 2 and 3 and passed.

## Behavior notes

- `run_deliver("send")` returns `{"recipients", "sent", "skipped_rows"}` and logs only those counts.
- Non-PipelineError exceptions report the subcommand name (`build`, `deliver`) as the stage, which the plan accepts for Phase 1.
- `KeyboardInterrupt` and `SystemExit` propagate. Argparse errors still exit 2.
- The env-guard test replaces `os.environ` with a dict subclass that raises on the four delivery secrets, then runs `run_build` on the W44 fixtures to completion.

## TDD Gate Compliance

- Task 2: RED commit b78cd8f had 5 failing tests (base64 x3, invalid-row validation, dedupe). GREEN commit a1c0ab7.
- Task 3: RED commit 5e325e5 had 12 failing tests. GREEN commit 4c1dfc4.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Delivery secret name appeared in a CLI help string**
- **Found during:** Task 3
- **Issue:** The `notify-failure` help text named `TEST_RECIPIENT` in `newsletter/__main__.py`, so the static secret-isolation check failed.
- **Fix:** Changed the help text to "the owner".
- **Commit:** 4c1dfc4

The DeliveryError is raised after the `except` block, not inside it. Combined with `from None`, this means not even `__context__` keeps the address-bearing SMTP exception. It is stricter than the plan's wording and has the same interface.

No dependencies were added, and pyproject.toml and uv.lock are unchanged.

## Known Stubs

None.

## Threat Flags

None. The new surface (the notify-failure SMTP send to the owner) is covered by D-13 and T-01-16..18.

## Self-Check: PASSED

- All created files exist: newsletter/delivery/subscribers.py, newsletter/delivery/notify.py, subscribers.example.csv, and the five test files.
- Commits dfe693d, b78cd8f, a1c0ab7, 5e325e5 and 4c1dfc4 are ancestors of HEAD.
