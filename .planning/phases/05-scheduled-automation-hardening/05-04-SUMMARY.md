---
phase: 05-scheduled-automation-hardening
plan: 04
subsystem: delivery
tags: [report, notify, github-actions, humanizer, privacy]
status: complete
requires: ["05-01", "05-02", "05-03"]
provides:
  - "newsletter.delivery.notify.build_report(mode, issue_id, status, report) -> (subject, text) | None"
  - "newsletter.delivery.notify.send_report(mode); send_failure_notice kept as wrapper"
  - "`python -m newsletter report --mode test|send`; notify-failure alias"
  - "workflow step `Report (test/send, D-06)` under always() && env.MODE != 'preview'"
affects: [newsletter.yml run job, tests/test_workflow_static.py]
tech-stack:
  added: []
  patterns: ["decision table over out/status.json + out/report.json", "counts-only owner mail"]
key-files:
  created: [tests/test_report.py]
  modified:
    - newsletter/delivery/notify.py
    - newsletter/__main__.py
    - .github/workflows/newsletter.yml
    - tests/test_workflow_static.py
decisions:
  - "status.json wins over report.json; send + StaleIssueError -> [발송 거부], any other status -> [실패]"
  - "Successful test run (outcome tested, no status) mails nothing and touches no credential"
  - "Unknown outcome or neither file -> [실패] with stage unknown"
  - "Body prints only the five known count keys from report.json; unknown keys never reach the mail"
  - "Refused body carries stage and error_class only (no run URL), as the plan's behavior list says"
metrics:
  duration: "~15 min"
  completed: 2026-11-04
estimate:
  tokens: 65000
actuals:
  tokens: 9000
  tasks: 2
  commits: 2
plan_head_before: 6f7174bd5f888d3266b5926c1bfd298d4d74b689
plan_head_after: 0654b60fe3f706444350978e5a53096626aa5b70
---

# Phase 5 Plan 04: Weekly Run Report Summary

One owner mail per run from an always() Report step: [발송 완료] with counts and the web link, [일시정지], [발송 거부] for a stale issue, or [실패] with stage, class and run URL. All copy is 해요체, passes humanize.lint, and carries no personal data.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (tracer) | report command, sent row, always() Report step | ffc34a1 | notify.py, __main__.py, newsletter.yml, test_workflow_static.py, test_report.py |
| 2 (tdd) | full decision table, 해요체 copy, leak scan | 0654b60 | notify.py, test_report.py |

Tracer gate: `uv run pytest -q tests/test_report.py tests/test_workflow_static.py` re-run green before Task 2.

## Decision table as built

| mode | status.json | report.json outcome | Mail |
|------|-------------|---------------------|------|
| send | none | sent | `[발송 완료]` recipients, sent, skipped_ledger, unsubscribed, skipped_rows, web |
| send | none | paused | `[일시정지]` |
| send | StaleIssueError | any | `[발송 거부]` stage + error_class |
| any | other | any | `[실패]` mode, stage, error_class, run URL |
| test | none | tested | none (0, no secret read) |
| any | none | none/other | `[실패]` stage unknown |

## Verification

- `uv run pytest -q`: 1496 passed
- `uv run ruff check .` and `uv run ruff format --check newsletter tests`: clean
- Acceptance greps: `newsletter report --mode "$MODE"` 1 (via `grep -F`; BSD grep with a plain pattern printed 0 because of `$`), `Failure notice` 0, `def send_report` 1, `always() && env.MODE != 'preview'` 1, `실행이 실패했습니다` 0, `발송 거부` 1, `일시정지` 1
- Every Hangul line of every body passes `humanize.lint(..., kind="sentence") == []`

## Deviations from Plan

None in behavior. Notes:
- tests/test_cli.py needed no change: its notify-failure tests assert the `[실패]` subject, stage, class and run URL, never the old 합쇼체 line. The 05-01 `actions: write` absence check already existed (`test_no_actions_write_and_two_crons_in_code`); added `test_no_failure_notice_step_remains` (no Failure notice step, no `notify-failure` in workflow code lines).
- Static test `test_delivery_secret_values_are_mode_gated` now also pins the Report step's secrets to exactly SMTP_PASSWORD, SMTP_USER, TEST_RECIPIENT (T-05-17).

## Threat Flags

None. No new endpoint or secret; the Report step holds the same three credentials the Failure notice step held.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: tests/test_report.py, newsletter/delivery/notify.py
- FOUND: ffc34a1, 0654b60 (ancestors of HEAD)
