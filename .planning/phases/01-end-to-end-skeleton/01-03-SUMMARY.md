---
phase: 01-end-to-end-skeleton
plan: 03
subsystem: claude-analysis
status: complete
tags: [anthropic, structured-outputs, retry, server-side-fallback, prompt-caching, humanizer]
requires:
  - "01-01: analyze_one/analyze_items/make_client signatures, AnalysisInvalid, FakeAnthropic/make_parsed, W44 fixtures"
provides:
  - "analyze_one(client, entry, *, rank=0): two attempts with <previous_output_problems> feedback"
  - "Server-side fallbacks (beta + fallbacks='default') with per-client downgrade to messages.parse"
  - "check() codes title_empty / summary_len / ideas_count / idea_empty; trim_summary() for D-19"
  - "prompts/analyze_paper.md v2 + prompts/humanizer_ko.md joined into one cached system block"
affects: [01-06]
tech-stack:
  added: []
  patterns:
    - "Downgrade state in weakref.WeakKeyDictionary keyed by client (no process-wide flag)"
    - "Retry feedback and AnalysisInvalid carry codes/counts only, never model or paper text"
    - "Real-SDK contract tests via httpx2.MockTransport (anthropic 2.3 uses httpx2, respx cannot see it)"
key-files:
  created: [prompts/humanizer_ko.md, tests/test_analyze.py, tests/test_prompt.py]
  modified: [newsletter/stages/analyze.py, prompts/analyze_paper.md]
decisions:
  - "fallbacks is passed as a real keyword: SDK 2.3 beta.messages.parse accepts fallbacks= (BetaFallbacksParam = list | 'default'); extra_body not needed"
  - "A downgrade (400 or TypeError on the beta call) re-issues the same attempt and does not consume the retry"
  - "D-19 trim applies only when the second attempt's sole error is summary_len; trim cuts at the last space/comma/period at or after half the limit within 79 chars, else hard cut, then appends an ellipsis"
  - "analyze_one gained a keyword-only rank argument for logs and error codes; positional contract analyze_one(client, entry) unchanged"
metrics:
  duration: "~35 min"
  completed: 2026-11-02
actuals:
  tokens: 8100
  tasks: 3
  commits: 5
plan_head_before: d927d0f2fb31048355f1942731f0072b0f31e135
plan_head_after: c1607fd067dcc519e0737f13696e632d64d348a4
---

# Phase 1 Plan 03: Claude Analysis Hardening Summary

Each paper now gets one `beta.messages.parse` call with Sonnet 5.5 server-side fallbacks. Refusal, `max_tokens`, empty output, schema errors and failed code checks get one retry that carries `<previous_output_problems>` feedback. A pure 80-char summary overrun is trimmed at a phrase boundary (D-19). Any other problem still present after the retry raises `AnalysisInvalid("rank=N reason=<codes>")`, and the build stops before `issue.json` exists. The system prompt is now one cached block that joins the v2 analysis prompt with a Korean humanizer core subset.

## What was built

- **Retry loop** (`newsletter/stages/analyze.py`): attempts 1 and 2. Feedback lists problem codes and counts, never model text. Each call logs `rank attempt stop_reason category input_tokens output_tokens cache_read_input_tokens` and nothing else. `analyze_items` stays sequential so the prompt cache stays warm, and it stops at the first invalid paper (D-15).
- **Fallback downgrade:** if the beta call raises `anthropic.BadRequestError` or `TypeError`, the client is recorded in a `WeakKeyDictionary` and logged once as `fallbacks=unsupported`. That call and every later call on the same client then go to plain `messages.parse` without betas or fallbacks.
- **Field checks:** `check()` returns `title_empty`, `summary_len` (>80 by `len()`), `ideas_count` (>2) and `idea_empty`. Before checking, CR/LF/tab in `title_ko`, `summary_ko` and the ideas are collapsed to single spaces (T-01-10).
- **Prompts:** `analyze_paper.md` v2 covers the `<paper>` data fence and ignore-instructions rule, `<previous_output_problems>` handling, the D-04/D-05 language rule with the CONTEXT example, the title gloss, the 80-char summary, D-07 grounded ideas (`[]` rather than invented ones), and all seven `ai_type` definitions with a primary-output tie rule. `humanizer_ko.md` is the D-18 core subset: no hype words, no 단순히/~를 넘어 contrasts, no dashes, no bold or markdown, no closing one-liners, no forced triads, and one consistent sentence ending. The paper block now writes the `has_github` and `has_project_page` flags as `yes`/`no`.

## Tests

- `tests/test_analyze.py` (27): refusal retried and the week builds (11 calls); rank 5 invalid twice leads to `AnalysisInvalid` with no `issue.json`/`email.html`; `max_tokens` and schema-error retries; `BadRequestError` and `TypeError` downgrades through `run_build`; downgrade is scoped to one client; logs contain no paper or output text; real-SDK contract (beta header, `"fallbacks": "default"`, `output_config.format` json_schema, parsed output); real-SDK 400 leads to a second request without fallbacks or the beta header; check codes; D-19 trim (≤80, ellipsis, log `trimmed=summary rank=6`); length plus another error fails; 3 ideas then valid; unknown `ai_type` goes through the retry; CR/LF normalization; `trim_summary` edge cases.
- `tests/test_prompt.py` (5): one cached block containing both files (≥1500 chars, version line first); all AiType labels, language rule, grounding, fence and humanizer words present; rank-3 `2610.32749` user block has no `http` and keeps the rest of the abstract; synthetic URLs stripped from title, summary, ai_summary and keywords; yes/no flags.
- Gate: `uv run pytest -q tests/test_analyze.py tests/test_prompt.py tests/test_e2e.py tests/test_schema.py` gives 54 passed. `uv run ruff check` passes. The full suite in this worktree also passes (54).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] respx cannot intercept the Anthropic SDK**
- **Found during:** Task 1
- **Issue:** anthropic 2.3.0 sends requests through `httpx2`, not `httpx`, and rejects `httpx` objects. respx only patches `httpx`, so the planned respx mock of `POST https://api.anthropic.com/v1/messages` would never fire. Building `anthropic.BadRequestError` with an `httpx.Response` would also give the wrong type.
- **Fix:** The real-SDK tests (e) and (f) pass `anthropic.Anthropic(api_key="test-key", max_retries=0, http_client=httpx2.Client(transport=httpx2.MockTransport(...)))` and assert the same request properties: URL `api.anthropic.com/v1/messages`, the `anthropic-beta` header, and the `fallbacks` and `output_config` body fields. `_bad_request()` builds the exception with `httpx2.Request`/`httpx2.Response`. respx is still used for the HF pages. No dependency changes: `httpx2` is already installed as an anthropic dependency.
- **Files modified:** tests/test_analyze.py
- **Commit:** 732a621

**2. [Formatting] ruff format on py314 target**
- `ruff format` rewrote `except (anthropic.BadRequestError, TypeError):` to the PEP 758 form `except anthropic.BadRequestError, TypeError:`. This is valid on Python 3.14, which the project pins.

No other deviations. No changes were made to `pyproject.toml`, `uv.lock`, the frozen schema, errors.py, pipeline.py, `__main__.py` or conftest.py.

## TDD Gate Compliance

- Task 2: RED `395dfba` (test) then GREEN `772757e` (feat).
- Task 3: RED `1df590c` (test) then GREEN `c1607fd` (feat). `test_synthetic_urls_are_stripped_everywhere` passed at RED because `strip_urls` from Plan 01 already handled it, so `strip_urls` was not changed.
- Task 1 (tracer): implementation and tests were committed together in `732a621`. The tracer gate re-ran the verify command (13 passed) before expansion.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 732a621 | feat(01-03): retry each paper once and drop server-side fallbacks per client on rejection |
| 2 RED | 395dfba | test(01-03): add failing tests for field checks and D-19 summary trim |
| 2 | 772757e | feat(01-03): enforce analysis field limits in code with D-19 summary trim |
| 3 RED | 1df590c | test(01-03): add failing tests for system prompt and URL-free paper block |
| 3 | c1607fd | feat(01-03): full analysis system prompt with humanizer core subset |

## For Plan 06 (live smoke test)

- To see which path ran, look in the log: `fallbacks=unsupported` means the API returned 400 and the client was downgraded. With no such line, the beta path with fallbacks served every call.
- Confirm prompt caching with `cache_read_input_tokens` > 0 on calls 2 to 10. The system text is about 3.3K characters, which should be over the 512-token minimum. Confirm this live.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: prompts/humanizer_ko.md, tests/test_analyze.py, tests/test_prompt.py, newsletter/stages/analyze.py, prompts/analyze_paper.md
- FOUND commits: 732a621, 395dfba, 772757e, 1df590c, c1607fd (all ancestors of HEAD)
