---
phase: 01-end-to-end-skeleton
plan: 01
subsystem: pipeline-skeleton
status: complete
tags: [uv, python3.14, pydantic, anthropic, jinja2, smtp, walking-skeleton]
requires: []
provides:
  - "Runnable newsletter package: run_build(issue_id) and run_deliver('test')"
  - "Frozen Issue v1 contract + schema/issue.schema.v1.json snapshot guard"
  - "tests/conftest.py fakes (FakeAnthropic, make_parsed, FakeSMTP) and fixtures for Wave 2"
  - "W44 HF fixtures (100/100/14) and tests/fixtures/issue_w44.json"
affects: [01-02, 01-03, 01-04, 01-05, 01-06]
tech-stack:
  added: [anthropic 2.3.0, pydantic 2.14.2, httpx 0.28.1, tenacity 9.2.1, jinja2 3.1.6, css-inline 0.23.1, pytest 9.2.0, respx 0.23.1, ruff 0.17.3]
  patterns: ["one messages.parse per paper into ItemAnalysisLLM, code merges into Item", "trim_entry whitelist before raw.json", "strip_urls on all paper text sent to Claude", "archive/<week>/ stage files + current.json handoff"]
key-files:
  created: [pyproject.toml, uv.lock, .python-version, .gitignore, newsletter/__init__.py, newsletter/__main__.py, newsletter/errors.py, newsletter/week.py, newsletter/schema.py, newsletter/store.py, newsletter/pipeline.py, newsletter/stages/__init__.py, newsletter/stages/fetch.py, newsletter/stages/select.py, newsletter/stages/analyze.py, newsletter/stages/render.py, newsletter/delivery/__init__.py, newsletter/delivery/send.py, newsletter/delivery/deliver.py, prompts/analyze_paper.md, templates/email.html.j2, templates/email.txt.j2, schema/issue.schema.v1.json, tests/conftest.py, tests/test_e2e.py, tests/test_schema.py, tests/fixtures/hf_w44_p0.json, tests/fixtures/hf_w44_p1.json, tests/fixtures/hf_w44_p2.json, tests/fixtures/issue_w44.json]
  modified: []
decisions:
  - "Issue v1 frozen with owner option-a: LocalRun = 가능 / 제한적 / 불가 / 확인 필요 (default 확인 필요)"
  - "ANLY-06 (A1) accepted: Claude fills only ItemAnalysisLLM; code merges HF facts and validates the whole Issue"
  - "uv.lock generated locally on macOS (uv 0.13.6, CPython 3.14.10); CI re-checks with uv sync --frozen"
metrics:
  duration: "~35 min"
  completed: 2026-11-02
estimate:
  tokens: 120000
  tasks: 3
actuals:
  tokens: 168870   # chars/4 over all added lines incl. uv.lock and fixtures; ~16000 excluding lock + fixtures
  tasks: 3
  commits: 5
plan_head_before: 5a357d9d60309298a6c0948b3ae068de1c5b2886
plan_head_after: 8092ad4d43ea4ad3e0554aecf6a40a93655bb073
---

# Phase 1 Plan 01: Walking Skeleton and Frozen Issue v1 Summary

A uv/Python 3.14 package now runs end to end offline. It takes the HF W44 week= pages, selects the Top 10 with the D-10 sort key, makes one `messages.parse` call per paper into `ItemAnalysisLLM` (URLs stripped), merges the results into the `Issue`, renders a 640px Jinja2 table email plus a text version, writes the archive files, and sends one multipart message over SMTP_SSL in test mode. Issue v1 is frozen with a committed JSON-schema snapshot.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1a | Scaffold, fixtures, errors/week/schema/store | 52cc9a4 |
| 1b | fetch/select/analyze/render + run_build + build e2e | 8fbe232 |
| 1c | send/deliver + CLI + issue_w44.json fixture | 10692e7 |
| 2 | Checkpoint: owner chose option-a | (no commit) |
| 3 RED | tests/test_schema.py (17 functions, snapshot test failing) | ebf4eae |
| 3 GREEN | schema/issue.schema.v1.json committed | 8092ad4 |

## Recorded facts

- Fixture page counts: p0 = 100, p1 = 100, p2 = 14 (214 unique papers), captured live on 2026-11-02 and trimmed to the whitelisted keys.
- Toolchain: uv 0.13.6 (official installer, `~/.local/bin`) and CPython 3.14.10, which uv downloaded.
- Top 10 from the fixture: 37381, 35684, 32749, 36729, 35845, 36671, 37230, 34662, 36068, 34283. Ranks 7 and 8 are tied at 95 upvotes and ordered by numComments (4 before 2).
- Rank 1 (2610.37381) has no GitHub link, project link or affiliation, so issue_w44.json covers the "omit" path without hand edits.
- Rank 3 (2610.32749) has a URL in its abstract; `strip_urls` removes it (tested).
- Preview email.html is 40,832 bytes, under the 90 KB limit.
- Task 2 answer: **option-a**. LocalRun is `가능 / 제한적 / 불가 / 확인 필요` with default `확인 필요`. A1 is accepted.

## Verification

`uv sync --frozen && uv run ruff check && uv run pytest -q`: all checks passed, 22 tests passed (4 e2e, 18 schema). All acceptance greps for Task 1 and Task 3 pass.

## TDD Gate Compliance

- RED: ebf4eae. `test_schema_snapshot_matches` failed because the snapshot file did not exist. The other validator tests passed at RED because Task 1 had already written the validators from the RESEARCH proposal; Task 3 only adds the guard.
- GREEN: 8092ad4. The snapshot was generated once with `ensure_ascii=False, indent=2, sort_keys=True` and the full suite passes.
- REFACTOR: none needed.

## Deviations from Plan

### Auto-fixed Issues

1. **[Rule 2 - Security] `strip_urls` also removes `<paper>`/`</paper>` tags** from untrusted text, so an abstract cannot close the data delimiter early. File: newsletter/stages/analyze.py. Commit: 8fbe232.
2. **[Rule 1 - Bug] `to_item` wraps Pydantic `ValidationError` in `AnalysisInvalid`.** This applies when, for example, Claude returns more than 2 ideas. The error then keeps the `analyze` stage and does not surface as a bare exception. Commit: 8fbe232.
3. **[Rule 3 - Blocking] Ruff 0.17 default rules** (UP037, RUF012, PLR0402) required unquoted annotations, `ClassVar` on `FakeSMTP.instances`, and a `from` import. `ruff format` was applied to Python files only, because it also flags code blocks in .planning markdown, which were left untouched. Commits: 52cc9a4, 8fbe232.
4. **Conftest additions beyond the Interfaces list:** the `fake_anthropic` and `fake_smtp` fixtures. `fake_smtp` patches `newsletter.delivery.send.smtplib.SMTP_SSL` and resets `FakeSMTP.instances`. `FakeSMTP.set_debuglevel` raises if anything calls it. These are additive only.

The `deliver --mode` argparse choice is `["test"]` only. Plan 05 extends it to `send`.

## Known Stubs

These are intentional tracer-depth stubs, each owned by a later plan in this phase:
- fetch.py has no `date=` fallback, retries or KST filter (Plan 02).
- analyze.py has no retry-once, no length check and no humanizer subset (Plan 03).
- render.py has no size gate or subject truncation (Plan 04).
- deliver.py supports test mode only, and there is no top-level redaction handler in `__main__` (Plan 05).
- tests/fixtures/issue_w44.json holds FakeAnthropic text ("…: 테스트 제목", "테스트용 한줄 요약입니다."), not real Claude output. It is a test fixture and never reaches readers.

The broken-windows ledger was not appended because node and gsd-tools are unavailable.

## Self-Check: PASSED

- All 30 files listed in key-files exist.
- Commits 52cc9a4, 8fbe232, 10692e7, ebf4eae and 8092ad4 are ancestors of HEAD.
