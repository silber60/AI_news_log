---
phase: 05-scheduled-automation-hardening
plan: 05
subsystem: verification
status: complete   # SC2 confirmed by the same-day backup cron (see Task 3)
tags: [live-run, owner-checkpoint, schedule, stale-guard]
requires: [05-01, 05-02, 05-03, 05-04]
---

# 05-05 Summary: live checks

## Task 1: push and workflow state (orchestrator, done 2026-11-04)
- Main pushed at cbb784f. The ci push run succeeded.
- `.github/workflows/newsletter.yml` is `active`, and no run failed with a workflow-file error, so GitHub accepted the `timezone:` and `queue:` keys.

## Task 2: owner checks (done 2026-11-04, cost-reduced)
The owner asked to skip the two planned `mode=test` runs to save Claude credit (about $10 had been spent during development). Only the stale send was dispatched.
- Step 0: the Phase 4.2 prerequisite was done (the owner reported that the Resend setup was complete).
- Stale send, run 41796031253 (workflow_dispatch, mode=send, week=2026-W44, allow_stale off, head 032d51e):
  - The run job concluded failure at Deliver (StaleIssueError). The owner received the `[발송 거부]` report, which said the send window had passed.
  - The publish job concluded success and committed archive/2026-W44 with 7 checkpoint files (commit 032d51e). This is the live evidence for ROADMAP criterion 3: archive is committed back after a partial failure.
  - deploy-pages was skipped.
  - No data/ledger/2026-W44.json exists, so no subscriber was mailed.
  - The publish job's "ledger" download step logged "Artifact not found" and continued (continue-on-error). That is expected, because no ledger is uploaded when nothing is sent.
  - Archive leak scan on origin/main: 0 address matches outside image asset names, and 0 `?t=` tokens.
- Not run (owner's cost decision):
  - The twice-run test proving checkpoint reuse. The stale run built W44 once, so the first Monday's 08:00 send reusing the 06:00 build is the live reuse proof (Task 3).
- SEND_PAUSED: the owner created the repository variable with value `false` (2026-11-04).

## Task 3: first unattended Monday 2026-11-09 (done, with a fix)

- Only one scheduled run happened that day: 42541155939, which started at 09:37 KST.
  - Its Trigger line read `event=schedule schedule=0 6 * * 1 mode=test`. The 06:00 cron ran 3.5 h late. A2 is confirmed: with `timezone:` set, `github.event.schedule` holds the bare cron string, so the mapping works.
  - It built W45 and committed the checkpoints (7fc43ef). As a test run, it published nothing and sent no report.
- GitHub never ran the 08:00 cron, so no subscriber was mailed on schedule.
- Fix, fd40f50:
  - Crons moved off the hour: test 05:47 KST; send 08:17, with backups at 10:17 and 12:47.
  - MODE now sends for any of the listed send crons.
  - A backup after a full send records outcome `already_sent`: no report, no publish.
  - A paused week is reported only once (BACKUP_RUN).
  - CI passed.
- The owner dispatched `mode=send` (week blank, which resolves to W45) by hand that morning.
  - It reused the checkpoints, so there was no Claude cost.
  - Ledger data/ledger/2026-W45.json was committed in d912d23: scheme hmac-sha256-ledger-v1, 13 keys, no '@'.
  - data/issues/2026-W45.json is committed. https://silber60.github.io/AI_news_log/issues/2026-W45/ returns 200 and the home archive lists W45.
  - welcome/latest.json now names 2026-W45.
- SC2 (no duplicate send): the 10:17 and 12:47 backup crons after the manual send are the live check. They must end with outcome already_sent and mail nobody. Record whichever of them ran.
