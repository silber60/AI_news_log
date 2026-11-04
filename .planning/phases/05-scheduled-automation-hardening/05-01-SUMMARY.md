---
phase: 05-scheduled-automation-hardening
plan: 01
subsystem: automation
status: complete
tags: [github-actions, schedule, concurrency, pause, stale-guard, commit-back]
requires:
  - 04.2-01 (Resend sender; send_messages(messages, *, password, pause); Deliver env names unchanged)
provides:
  - newsletter.yml two Asia/Seoul crons (06:00 test, 08:00 send) and the MODE mapping
  - run job outputs mode and outcome (steps.deliver.outputs.outcome)
  - deliver pause switch (SEND_PAUSED, schedule only), stale-week guard, out/report.json, GITHUB_OUTPUT outcome
  - week.send_day / week.is_sendable, errors.StaleIssueError, deliver --allow-stale
  - always() publish job that commits archive/, data/ledger/, topic record and pages; outcome-gated publish and deploy
  - concurrency queue: max in both workflows of the newsletter group; tip checkouts
  - tests/conftest.py real_clock marker plus autouse w44_send_day and no_runner_outputs fixtures
affects: [05-02 (checkpoints ride the archive commit), 05-03 (ledger fills data/ledger/), 05-04 (run report reads out/report.json and outcome), 05-05 (live proof)]
tech-stack:
  added: []
  patterns:
    - "Guards decide in Python before any secret read or network call: pause, then stale, then secrets, then lists, then SMTP"
    - "deliver writes outcome=<paused|tested|sent> to $GITHUB_OUTPUT; workflow gates on needs.run.outputs.outcome"
    - "autouse fixture pins deliver._now to W44's send day; tests opt out with @pytest.mark.real_clock"
key-files:
  created:
    - tests/test_guards.py
    - data/ledger/.gitkeep
  modified:
    - .github/workflows/newsletter.yml
    - .github/workflows/import-subscribers.yml
    - .gitignore
    - newsletter/week.py
    - newsletter/errors.py
    - newsletter/delivery/deliver.py
    - newsletter/__main__.py
    - tests/conftest.py
    - tests/test_workflow_static.py
    - tests/test_cli.py
decisions:
  - "timezone: \"Asia/Seoul\" crons used directly; the UTC fallback strings (0 21 * * 0 / 0 23 * * 0) live only in a YAML comment"
  - "Only the exact '0 8 * * 1' schedule maps to send; any other schedule resolves to test (fail safe)"
  - "Credential reads moved below the pause and stale checks; a paused send needs no credential at all"
  - "No actions: write and no re-enable step (owner A3); the weekly content commit is the keepalive, recovery via Actions tab"
  - "Failure notice step keeps its inputs.mode != 'preview' gate (true on a schedule, where inputs.mode is ''); 05-04 owns the report step"
metrics:
  duration: ~35 min
  completed: 2026-11-04
  tasks: 3 of 3
  files: 12
commits: 4
plan_head_before: f2a2196d62150c21fe955671cd7354726076c877
plan_head_after: ec6dee5c4060223bedb90d9bc272655e3095c6ea
actuals:
  tokens: 10600   # chars/4 over the realized diff (git diff f2a2196..HEAD = 42458 chars)
  tasks: 3
  commits: 4
---

# Phase 5 Plan 01: Schedule, guards and commit path Summary

The Monday 08:00 KST cron now resolves to `mode=send`, a scheduled send honours the `SEND_PAUSED` repository variable, any send outside the issue's KST send day is refused before any secret or network use unless `--allow-stale` is given on purpose, deliver reports its outcome to the workflow, and an always-run publish job commits `archive/` and `data/ledger/` back to main while publishing web pages only for a sent issue.

## Task 1 (tracer): crons, MODE mapping, pause, outcome (7ee41be)

- `on.schedule`: `cron: "0 6 * * 1"` and `cron: "0 8 * * 1"`, each followed by `timezone: "Asia/Seoul"`.
- Run job `MODE`: `github.event_name == 'schedule' && (github.event.schedule == '0 8 * * 1' && 'send' || 'test') || inputs.mode`.
- New `Trigger` step logs event, cron and mode through shell variables only.
- Deliver: `id: deliver`, `if` and every credential gate now read `env.MODE`, plus `SEND_PAUSED: ${{ github.event_name == 'schedule' && vars.SEND_PAUSED || '' }}`.
- Run job outputs `mode` and `outcome`. In the publish job, the topic, pages and Pages-artifact steps are gated on `env.OUTCOME == 'sent'`. `deploy-pages` uses `needs: [run, publish]` with `!cancelled() && needs.run.outputs.outcome == 'sent' && needs.publish.result == 'success'`.
- deliver.py: `_paused()` (strip/lower == "true", send only), `_finish(report)` writes `out/report.json` and appends `outcome=<x>` to `$GITHUB_OUTPUT`. Test and send still return the same counts dict. Paused returns `{"outcome": "paused", "issue_id": ...}`.
- Tracer gate: re-ran `uv run pytest -q tests/test_guards.py tests/test_workflow_static.py` and the full suite. Both were green, so the plan continued to Task 2.

## Task 2 (TDD): stale-week guard (RED 8d71384, GREEN 7d0e515)

- RED: the new tests failed with `AttributeError` (no `week.send_day`, no `deliver._now`).
- `week.send_day` returns the Monday after the week's Sunday. `week.is_sendable` compares KST dates and raises `ValueError` on a naive datetime.
- `StaleIssueError(PipelineError)` has `stage = "deliver"`. It is raised after the pause check and before `_env("SMTP_USER")`.
- `deliver --allow-stale` (store_true) passes through as `allow_stale`. A CLI stale send exits 1 and writes `status.json` `{"stage": "deliver", "error_class": "StaleIssueError"}`.
- conftest gained `real_clock` marker registration and an autouse `w44_send_day` fixture (2026-11-02 09:00 KST). In test_cli.py, `boom(mode)` became `boom(mode, **k)`.

## Task 3: queue, tip checkouts, allow_stale input, always-run commit (ec6dee5)

- The concurrency block in both workflows is now `group: newsletter`, `cancel-in-progress: false` and `queue: max`.
- Both checkouts in newsletter.yml have `ref: ${{ github.ref }}` and `persist-credentials: false`.
- The dispatch input `allow_stale` (boolean, default false) maps to env `ALLOW_STALE`. The Deliver run line adds `--allow-stale` only when `"$ALLOW_STALE" = "true"`.
- The issue upload now runs on `always()` with `overwrite: true`. A new step, "Ledger artifact (send only)", runs on `always() && env.MODE == 'send'` and uploads `data/ledger/`.
- Publish job:
  - `if: always() && github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || inputs.mode != 'preview')`.
  - Both downloads use `continue-on-error: true`.
  - The commit step is "Commit archive, ledger, record and pages". It adds each existing path, commits `chore(newsletter): archive, ledger and publish`, and retries rebase plus push 3 times with `sleep $((i * 5))`.
  - The job comment documents the keepalive and the recovery path.
- `.gitignore` now ignores only `archive/current.json`, and `data/ledger/.gitkeep` was added. Checked: `archive/current.json` is ignored and `archive/2026-W45/issue.json` is not.

## Verification

- `uv run pytest -q`: 1445 passed (27 in tests/test_guards.py).
- `uv run ruff check . && uv run ruff format --check newsletter tests`: clean.
- All plan acceptance greps match. On non-comment lines: 2 crons, 2 timezones, 1 send literal, 1 `vars.SEND_PAUSED`, 1 `queue: max` per workflow, tip ref count 2 equals checkout count 2, 0 `actions: write`, 1 `contents: write`, 0 `needs.run.result == 'success'`.
- `git diff --stat -- newsletter/delivery/send.py` is empty.
- Both workflows parse with PyYAML. The schedule list holds the two cron/timezone pairs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Runner env isolation for tests**
- **Found during:** Task 1
- **Issue:** `_finish` appends to `$GITHUB_OUTPUT`. In ci.yml's pytest step that variable is set, so every existing send test would write `outcome=...` into the CI step's output file. A `SEND_PAUSED` in a local shell would also silently pause tests.
- **Fix:** Added an autouse `no_runner_outputs` fixture in tests/conftest.py that unsets `GITHUB_OUTPUT` and `SEND_PAUSED`. Tests that need them set them explicitly (`gh_output` fixture in test_guards.py).
- **Files modified:** tests/conftest.py (Task 1 commit; conftest was planned for Task 2 only)
- **Commit:** 7ee41be

Otherwise the plan ran as written.

## Known Stubs

None. `data/ledger/` holds only `.gitkeep` until 05-03 writes the ledger, as the plan intends.

## Self-Check: PASSED

- FOUND: tests/test_guards.py, data/ledger/.gitkeep, .planning/phases/05-scheduled-automation-hardening/05-01-SUMMARY.md
- FOUND commits: 7ee41be, 8d71384, 7d0e515, ec6dee5 (all ancestors of HEAD)
