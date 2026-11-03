---
phase: 01-end-to-end-skeleton
plan: 06
subsystem: ci-deploy
status: checkpoint
tags: [github-actions, workflow_dispatch, ci, secrets-scoping]
requires: ["01-01", "01-02", "01-03", "01-04", "01-05"]
provides: [".github/workflows/newsletter.yml", ".github/workflows/ci.yml", "tests/test_workflow_static.py"]
affects: []
tech-stack:
  added: ["actions/checkout v7.0.1", "astral-sh/setup-uv v10.3.3", "actions/upload-artifact v7.0.2"]
  patterns: ["step-scoped secrets", "mode-gated secret values", "inputs via env only", "SHA-pinned actions"]
key-files:
  created: [".github/workflows/newsletter.yml", ".github/workflows/ci.yml", "tests/test_workflow_static.py"]
  modified: []
decisions:
  - "Actions pinned to commit SHAs now (setup-uv publishes no floating v10 tag, so @v10 would not resolve)"
  - "checkout uses persist-credentials: false (no git writes in Phase 1)"
metrics:
  completed: 2026-11-02
plan_head_before: cb92b06
actuals:
  tasks: 1
---

# Phase 1 Plan 06: Deploy skeleton to GitHub Actions Summary

Manual-dispatch workflow with step-scoped, mode-gated secrets, plus a secret-free CI workflow. 11 static tests guard both files. Live runs are pending the owner checkpoint.

## Status

- Task 1 (workflows + static tests): done, commit 05e25c0. Full suite 163 passed, ruff clean.
- Task 2 (push + secrets): waiting on the owner.
- Task 3 (four live runs + log/artifact audit): not started. The phase is not complete until this file records the four run IDs, the smoke-test result and a clean audit.

## Pinned actions (verified with git ls-remote, lightweight tags, commit SHAs)

| Action | Tag | SHA |
|---|---|---|
| actions/checkout | v7.0.1 (= v7) | 3d3c42e5aac5ba805825da76410c181273ba90b1 |
| astral-sh/setup-uv | v10.3.3 | 68559e99cc807c1eb7e9238fd43a15bba460eec2 |
| actions/upload-artifact | v7.0.2 (= v7) | cf430e030ddbb5b0abf93d22962f4752f3646cd9 |

## Deviations from Plan

1. **[Rule 3 - Blocking] setup-uv@v10 does not exist as a tag.** astral-sh/setup-uv stopped publishing floating major tags after v7, so only v10.x.y tags exist. All actions are pinned to verified commit SHAs with a version comment. The plan allowed tag pins; SHA pins are stricter and match the orchestrator's instruction. A static test enforces 40-hex SHA pins.
2. **[Rule 2 - Security] Workflow comments and descriptions avoid the literal secret names and `contents: write`.** That keeps the text-level guards strict, so a secret name anywhere outside Deliver/Failure-notice fails the test.
3. **[Rule 2 - Security] `persist-credentials: false` on checkout** in both workflows, because nothing pushes in Phase 1.

## Live-run evidence

Phase 1.1 D-20: runs happen on the v2 email after Phase 1.1.

| Run | Mode | Commit | Outcome |
|---|---|---|---|
| 41409445829 (#3) | preview | — | green; recorded in 01.1-05-SUMMARY.md (01.1-05 preview run) |
| (#4/#5) | test | 3533f70..492ff34 era | failed: DeliveryError in deliver and notify-failure (SMTP secrets); 492ff34 added a redacted `detail=` line |
| 41411211782 (#6) | test | 492ff34 (v2 email, pre-1.2) | green, 3m16s; owner confirmed the test email arrived in TEST_RECIPIENT |
| (owner, 2026-11-03) | send | post-1.2 main | green; owner confirmed the subscriber received the mail. Owner also confirmed test mode works on the 1.2 email |
| (owner, 2026-11-03) | test + week=2026-W54 (forced failure notice) | post-1.2 main | failed as designed: Build printed `stage=week error=InvalidWeekError`, exit 1. Failure-notice email arrival: awaiting owner confirmation |

Log audit (email/name grep on the test run log): not yet done; needs the owner's downloaded log archive.

## Self-Check: PASSED (Task 1 scope)

- FOUND: .github/workflows/newsletter.yml, .github/workflows/ci.yml, tests/test_workflow_static.py
- FOUND: commit 05e25c0
