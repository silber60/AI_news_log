---
phase: 03-humanizer-highlight-explainer
plan: 03
subsystem: explainer-topic-record
status: checkpoint
tags: [explainer, topics, cli, workflow]
requires: []
provides: [newsletter/topics.py, data/explainer_topics.json, "record-topic CLI"]
affects: [newsletter/__main__.py]
key-files:
  created: [newsletter/topics.py, data/explainer_topics.json, tests/test_topics.py]
  modified: [newsletter/__main__.py, tests/test_cli.py]
---

# Phase 3 Plan 03: Explainer Topic Record Summary (in progress, paused at Task 2)

A committed `data/explainer_topics.json` record, a `topics.load_past()` read API and an idempotent, send-only `python -m newsletter record-topic` command exist. The write-scoped workflow job waits on the owner decision at Task 2.

## Completed Tasks

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | Send-mode record-topic appends the explainer topic | dfe1f38 |

## Task 1 notes

- `topics.record()` raises `ValueError` when an existing record file is corrupt, instead of overwriting history. The CLI reports it as `stage=record-topic error=ValueError` and exits 1. `load_past()` still returns `[]` with `topics=unreadable` for the build.
- Tracer gate: the `<verify>` command re-ran green (full pytest, ruff), and `record-topic --help` works.

## Task 2: owner decision

Pending. Owner choice and branch-protection answer go here.

## Deviations from Plan

None so far.
