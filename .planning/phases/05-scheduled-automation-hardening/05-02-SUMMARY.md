---
phase: 05-scheduled-automation-hardening
plan: 02
subsystem: pipeline
status: complete
tags: [checkpoints, force-stage, reuse, billing, github-actions]
requires:
  - 05-01 (publish job commits archive/ on every test or send run; tip checkouts)
provides:
  - store.write_json_atomic, store.checkpoint_path, store.CHECKPOINT_VERSION = 1
  - pipeline.STAGES and run_build(issue_id, *, http_client, claude_client, force_stage)
  - archive/<week>/checkpoints/<stage>.json for analyze, enrich, notes, trend, highlight, explainer, headline
  - build --force-stage; newsletter.yml force_stage dispatch input and FORCE_STAGE env
affects: [05-04 (run report can read the checkpoint log lines), 05-05 (live proof: 08:00 send reuses the 06:00 build)]
tech-stack:
  added: []
  patterns:
    - "One _Checkpoints object per build: step(stage, load, compute, save) with a cascade flag; force_stage sets the cascade at its index"
    - "raw.json is the fetch checkpoint and issue.json the polish checkpoint; the rest use {version, issue_id, stage, data}"
    - "Lazy Claude client: analyze.make_client() is called only when a Claude stage recomputes"
key-files:
  created:
    - tests/test_checkpoints.py
  modified:
    - newsletter/store.py
    - newsletter/pipeline.py
    - newsletter/__main__.py
    - .github/workflows/newsletter.yml
    - tests/test_workflow_static.py
    - tests/test_e2e.py
decisions:
  - "enrich checkpoint stores the pre-finalize items plus the EVID-01 records; verdicts.finalize runs exactly once per build on both paths"
  - "The CLI duplicates STAGES as FORCE_STAGES so the parser stays import-light; a test asserts both match"
  - "A reused polish checkpoint is not rewritten; email.html/email.txt are re-rendered from it and come out byte-identical"
  - "A checkpoint that fails to load logs checkpoint=<stage> invalid reason=<code> (no content) before the computed line"
metrics:
  duration: ~30 min
  completed: 2026-11-04
  tasks: 3 of 3
  files: 7
commits: 4
plan_head_before: 999d671cf2f75c3785b481bd90ea15e00107ab11
plan_head_after: cf78414b014fae7a3926c2bc7e5feead4722dfab
actuals:
  tokens: 8500   # chars/4 over the realized diff (git diff 999d671..cf78414 = 34092 chars)
  tasks: 3
  commits: 4
---

# Phase 5 Plan 02: Per-stage checkpoints and --force-stage Summary

Every paid build stage now saves its output to `archive/<week>/` atomically right after it succeeds. A second build of the same week makes zero HF/GitHub HTTP calls and zero Claude calls, never creates an Anthropic client, and writes byte-identical `issue.json`, `email.html` and `email.txt`. `--force-stage X` (CLI and Actions dispatch) is the deliberate way to recompute X and every later stage.

## Task 1 (tracer): fetch and analyze reuse (fbfb6f1)

- `store.py`: `CHECKPOINT_VERSION = 1`, `checkpoint_path(issue_id, stage)` returning `week_dir/checkpoints/<stage>.json`, and `write_json_atomic` (sibling `.tmp` file plus `os.replace`, same formatting as `write_json`, and the tmp file is removed on failure).
- `pipeline.py`: `STAGES`, a checkpoint loader/saver with the cascade, and a lazy Claude accessor. `raw.json` is reused when its issue_id, method, entries (as `HfEntry`) and tz-aware `fetched_at` are valid.
- Tracer gate: `tests/test_checkpoints.py` and the full suite were both green, so expansion continued.

## Task 2 (TDD): every paid stage (RED cd16240, GREEN 840ff79)

- RED: 10 new tests failed (`force_stage` unknown kwarg, notes through polish still calling Claude).
- enrich `{items (pre-finalize), records}`. `enriched.json` is rewritten from the records on both paths, then `finalize` runs once. notes, trend, highlight, explainer and headline are checkpointed. polish uses `issue.json` (validated as `Issue` with a matching issue_id). Reusing it skips both Issue assembly and `polish_issue`.
- `force_stage`: `None`, `""` and `"none"` mean no force, a `STAGES` name cascades from that stage, and anything else raises `ValueError`.
- Tests cover full reuse (`fake.calls == []`, 0 HTTP, `make_client` patched to raise, plus a build with no injected client), `force_stage="notes"`/`"fetch"`/`"none"`/`""`, a truncated and a foreign-week `highlight.json`, the enrich payload and finalize spy, and `None`/`[]`/`None` reused as valid trend/highlight/explainer payloads.

## Task 3: CLI, dispatch input, leak scan (cf78414)

- `build --force-stage` (default `""`, choices `""`, `none`, the nine stages). The module docstring now documents it.
- `newsletter.yml`: `force_stage` choice input (default `none`), run-job env `FORCE_STAGE: ${{ inputs.force_stage }}`, and Build run line `build --week "$WEEK_INPUT" --force-stage "$FORCE_STAGE"`. The Build step still has exactly one `secrets.` reference.
- Static tests: options and default, `inputs.force_stage` exactly once (run job env), the run line, and no `${{` in the Build run line.
- Leak scan: every file under a built `archive/2026-W44/` (checkpoints included) has no `_EMAIL_RE` match outside asset names and no `?t=<32 hex>`. A filter test confirms `logo@2x.png` is ignored and `reader@example.com` is caught.

## Verification

- `uv run pytest -q`: 1464 passed. `uv run ruff check .` and `uv run ruff format --check newsletter tests` are clean.
- Acceptance greps: `def checkpoint_path` 1, `def write_json_atomic` 1, `checkpoint=` present, `force_stage` in pipeline 10, quoted stage names 16, `inputs.force_stage` 1, `--force-stage "$FORCE_STAGE"` 1, `force-stage` in `__main__.py` 3.

## Deviations from Plan

**1. [Rule 1 - Test intent] test_flagged_line_gets_one_polish_call builds its clean twin in a separate archive dir**
- Found during: Task 1. The second (dirty) build reused the clean analyze checkpoint, so the dirty rank-2 analysis never ran.
- Fix: the clean build writes to `archive_tmp/clean` and the dirty build to `archive_tmp/archive`. All assertions are unchanged (16 calls, the leaf comparison with the clean build).
- Commit: fbfb6f1.

The plan also named `test_trend_api_error_keeps_the_build`, `test_paper_invalid_twice_stops_the_build` and tests in `tests/test_render.py` as double builds. Each of them builds once per archive dir, so they needed no change and still pass unmodified.

## Threat Flags

None. No new network surface. Checkpoints hold only trimmed HF data, public evidence records and Claude text already published in `issue.json`, and the leak-scan test covers T-05-07.

## Self-Check: PASSED

- FOUND: tests/test_checkpoints.py, newsletter/store.py, newsletter/pipeline.py
- FOUND commits: fbfb6f1, cd16240, 840ff79, cf78414 (ancestors of HEAD)
