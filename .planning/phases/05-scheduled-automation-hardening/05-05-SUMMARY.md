---
phase: 05-scheduled-automation-hardening
plan: 05
subsystem: verification
status: checkpoint   # Task 3 (first unattended Monday 2026-11-09) pending
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
- SEND_PAUSED variable: not yet confirmed by the owner. If the variable is missing, `vars.SEND_PAUSED` is empty and the schedule sends, which is the intended default.

## Task 3: first unattended Monday 2026-11-09 (pending)
Expected sequence:
- 06:00 KST: `[TEST]` to the owner.
- 08:00 KST: send to the live list, reusing the 06:00 checkpoints, followed by a `[발송 완료]` report.
- Afterwards: check the committed data/ledger/2026-W45.json and data/issues/2026-W45.json, and that /issues/2026-W45/ returns 200. Check the Trigger line (A2).
- SC2 re-dispatch: send W45 again and expect skipped_ledger ≥ the first send's count.
- If no report arrives by 10:00, the owner dispatches mode=send by hand.
