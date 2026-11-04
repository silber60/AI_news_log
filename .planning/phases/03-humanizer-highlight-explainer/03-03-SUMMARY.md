---
phase: 03-humanizer-highlight-explainer
plan: 03
subsystem: explainer-topic-record
status: complete
tags: [explainer, topics, cli, workflow, permissions]
requires: []
provides:
  - "newsletter/topics.py: topics_path(), load_past(path=None), record(issue, path=None) -> bool"
  - "data/explainer_topics.json (empty version-1 record)"
  - "python -m newsletter record-topic --mode preview|test|send"
  - "record-topic workflow job (the only contents: write job)"
affects: [newsletter/__main__.py, .github/workflows/newsletter.yml, tests/test_workflow_static.py]
tech-stack:
  added: ["actions/download-artifact v8.0.2 (SHA-pinned)"]
  patterns: ["write scope isolated in its own job", "job-aware text-level workflow tests"]
key-files:
  created: [newsletter/topics.py, data/explainer_topics.json, tests/test_topics.py]
  modified: [newsletter/__main__.py, tests/test_cli.py, .github/workflows/newsletter.yml, tests/test_workflow_static.py]
decisions:
  - "Owner approved the record-topic job (2026-11-04), silber60 noreply identity"
  - "main is not branch-protected (owner checked GET /repos/silber60/AI_news_log/branches/main: protected false)"
  - "topics.record() raises on a corrupt existing record instead of overwriting history"
requirements: [EXPL-02]
metrics:
  completed: 2026-11-04
actuals:
  tokens: 9000
  tasks: 3
  commits: 4
plan_head_before: 7f243600598f586eaf0317541dd9a39412652fc3
plan_head_after: ebd00c4
---

# Phase 3 Plan 03: Explainer Topic Record Summary

The explainer now has a topic history. `data/explainer_topics.json` is committed, and the build reads it through `topics.load_past()`. A send-only `record-topic` command appends to it once per issue. A separate write-scoped workflow job commits the file after a real send on main.

## Completed Tasks

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | Send-mode record-topic appends the explainer topic | dfe1f38 |
| 2 | Owner decision on the write-scoped job | (decision only; progress doc 7aaabdf) |
| 3 | record-topic job and job-aware static tests | ebd00c4 |

## What was built

- **topics.py:**
  - `load_past()` returns topics newest issue first, at most 52. It returns `[]` and logs `topics=unreadable` when the file is missing, not JSON, or not the version-1 shape.
  - `record()` does nothing when the issue has no explainer or its issue_id is already recorded. Otherwise it writes the entry (issue_id, date, topic) and keeps the list sorted by issue_id. The date is `week_end + 1 day`.
  - The file is UTF-8 with indent 2, Korean left unescaped, and a trailing newline.
  - A `# similarity rule: plan 03-04` placeholder marks where 03-04's code goes.
- **CLI:** `record-topic --mode preview|test|send`.
  - Preview and test log `topic=skipped mode=<mode>` and write nothing.
  - Send logs one of `topic=recorded|exists|none issue=<id>`. Logs never include the topic text.
  - A missing current.json or issue.json reports `stage=record-topic error=<Class>` and exits 1.
- **Workflow:** the record-topic job is added exactly as approved. The workflow-level comment now says the default token is read-only and only record-topic gets write scope.
- **Static tests:**
  - New `_jobs()` splits the workflow at `^  [\w-]+:$` under `jobs:`. `_split()` still returns the run job (workflow header plus run header, and run steps), so the existing tests keep their meaning.
  - New checks: exactly one non-comment `contents: write`, and it is in record-topic. The run job has no permissions override. The `if:` holds send, main and `needs.run.result == 'success'`. The job has no `secrets.` or delivery/Anthropic secret names. Its checkout uses `persist-credentials: false`. `github.token` appears only in the Build and "Commit topic record" steps.
  - The three new job tests fail against the HEAD workflow.

## Task 2 decision

- **Owner choice:** approve (2026-11-04). The job is added exactly as shown at the checkpoint, with the silber60 noreply identity.
- **Branch protection:** `main` is NOT protected. The owner checked with `GET https://api.github.com/repos/silber60/AI_news_log/branches/main`, which returned `protected: false`. The bot push should therefore succeed.
- Two assumptions are still unverified until the first real send. A4: download-artifact v8 reads upload-artifact v7 artifacts. A5: pushing with the token in the URL works.

## Verification

- `uv run pytest -q`: all pass. test_topics.py has 11 tests, test_cli.py has 4 new record-topic tests, and the workflow static tests pass.
- `uv run ruff check`: clean.
- Acceptance greps:
  - non-comment `contents: write` in newsletter.yml: 1
  - `record-topic --mode` in newsletter.yml: 1
  - `def _jobs` in tests/test_workflow_static.py: 1
  - `contents: write` in ci.yml: 0
- `ruff format --check` over the whole repo flags code blocks in older `.planning/**/*.md` files. Those files were already like that and are out of scope. Every Python file touched here is formatted.

## Deviations from Plan

None. The plan executed as written. One choice the plan left open: `record()` raises `ValueError` on a corrupt existing record file rather than overwriting it, so the CLI fails red instead of losing history.

## Threat Flags

None beyond the plan's threat model. T-03-06 to T-03-09 are mitigated as planned and pinned by the static and CLI tests.

## Self-Check: PASSED

- FOUND: newsletter/topics.py, data/explainer_topics.json, tests/test_topics.py
- FOUND commits: dfe1f38, 7aaabdf, ebd00c4 (ancestors of HEAD)
