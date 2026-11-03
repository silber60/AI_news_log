---
phase: 02-evidence-practical-verdicts
plan: 02
subsystem: verdicts
tags: [license, github-api, spdx, commercial-use, golden-set]
status: complete
requires: []
provides:
  - newsletter/stages/licenses.py (RANK, LICENSE_TABLE, OTHER_NAMES, lookup, resolve_license_link, weights_license, github_license, code_license, commercial_use)
  - tests/fixtures/golden_verdicts.json (15 live-captured cases)
  - tests/fixtures/github_license_w44.json (15 W44 repos)
  - GITHUB_TOKEN from github.token in the build step
affects: [02-04 enrich wiring, 02-05/02-06 render and e2e]
tech-stack:
  added: []
  patterns: [code-owned license table, stricter-of verdict, reason-code-only logging]
key-files:
  created:
    - newsletter/stages/licenses.py
    - tests/test_licenses.py
    - tests/fixtures/golden_verdicts.json
    - tests/fixtures/github_license_w44.json
  modified:
    - .github/workflows/newsletter.yml
    - newsletter/__main__.py
    - tests/test_workflow_static.py
decisions:
  - "Copyleft (GPL/LGPL/MPL/CC-BY-SA/ND, ...) maps to 조건부 (research A1). Owner review item."
  - "licenses.TIMEOUT and REPO_ID_RE are copies of the enrich values, guarded by tests, not imported: 02-04 imports licenses from enrich, and a top-level import back would be a cycle."
  - "weights_license always returns a source_url (resolved license_link or the model page), so a weights-side verdict always has an HF evidence link."
  - "lookup('other', name) checks non-commercial keywords before the known-name table, so 'qwen-research' is 불가."
metrics:
  duration: ~35 min
  completed: 2026-11-03
actuals:
  tokens: 12350
  tasks: 3
  commits: 4
plan_head_before: 1533ddcfe4664ca77e88a2d2ae806f09a64b0cd4
plan_head_after: ba4bf340c630bc5345aaa7ed27f1fa171d12a6de
---

# Phase 2 Plan 02: License Rules and GitHub License Read Summary

A code-owned SPDX/HF license table now drives 상업적 사용. It reads the weights license from `cardData.license`, then `license_name`, then the `license:` tags, with gated and base-model guards. The code license comes from GitHub `/repos/{o}/{r}/license`, with the Actions job token sent only in the Authorization header. The overall verdict is the stricter of the two sides. A live-captured 15-case golden set checks it offline.

## Tasks

| # | Task | Commits |
|---|------|---------|
| 1 | GitHub license read, code_license, commercial_use, workflow token | 4f97acf |
| 2 | Full table, weights side, gated/base-model guards, link resolver (TDD) | c79f8eb (RED), f0db165 (GREEN) |
| 3 | Golden set + W44 GitHub captures, httpx logger at WARNING | ba4bf34 |

## Fixture capture source

**Live, on 2026-11-03.** No fallback entries.
- HF: 12 `api/models/{id}?expand[]=safetensors&expand[]=cardData&expand[]=gated&expand[]=tags` calls. Stored fields: only `cardData.license/license_name/license_link`, `gated`, the `license:`/`base_model:` tags and `safetensors.total/parameters`.
- GitHub: 16 unauthenticated `/license` calls (15 W44 repos + DeepSeek-V3). Stored fields: only `license.{key,name,spdx_id}` and `html_url`. A 404 is stored with an empty body.
- Every live value matched the research §1/§7 tables. Every expectation is the research value. There are no differences to report.
- The 7 W44 repos that research classified only by file header returned the matching SPDX id from the API (A6 confirmed): Apache-2.0 for HairDeck, HiP3R, detectorscope and RSIHub, and MIT for RoboHarness, OpenEBFM and AutoTavern. JusperLee/Falcon is Apache-2.0. OmniShowcase, awesome-working-agent, LOWN and ChronoReplay are 404 (no license file).
- `expect.poc`, `expect.local_run` and `expect.est_vram_gb` follow the research §2/§3 rules (×2 bytes ×1.2, dtype and quantized guards). Only `expect.commercial` is checked here. 02-04 checks the rest.

## Verification

- `uv run pytest`: 684 passed (189 in tests/test_licenses.py, plus the new workflow test).
- `uv run ruff check`: clean. The new files pass `ruff format --check`. The pre-existing `.planning` markdown files are not ruff-formatted; I left them alone because they are out of scope.
- Acceptance greps: `GITHUB_TOKEN: ${{ github.token }}` appears once, `secrets.GITHUB_TOKEN` appears 0 times, `api.github.com/repos` appears once, `getLogger("httpx")` appears once, and the fixtures contain no Bearer/ghs_/ghp_. golden has 15 cases and w44 has 15 entries.
- `test_build_step_gets_only_anthropic_key` is unchanged and green. The build step still has exactly one `secrets.`.

## Deviations from Plan

**1. [Rule 3 - Blocking] TIMEOUT and REPO_ID_RE are copied, not imported from enrich.**
- The plan says to use "the enrich TIMEOUT". 02-04 will import licenses from enrich, so a top-level `from newsletter.stages.enrich import TIMEOUT` in licenses.py would create an import cycle.
- Fix: local constants with equality tests (`test_timeout_matches_enrich`, `test_repo_id_regex_matches_enrich`).
- Commits: 4f97acf, f0db165.

**2. [Rule 2 - Security] More hardening in github_license and resolve_license_link.**
- A ValueError from bad JSON is caught (status `error_JSONDecodeError`).
- An off-host `html_url` is dropped.
- Links with whitespace, backslash, a scheme (`javascript:`) or an absolute path fall back to the model page.
- An invalid model_id falls back to `https://huggingface.co/models`.

**3. Test note.** Task 1's log test checks only records from the licenses logger for repo ids. httpx's own INFO line carries the URL until Task 3 quiets it. The token never appears in any record.

## Owner review items

- A1: copyleft licenses map to 조건부, not 가능.
- A2: assumed `license_name` strings `tongyi-qianwen`, `deepseek` and `deepseek-license`. If one is wrong, that model falls to 확인 필요, which is safe.
- A11: fine-tunes whose `base_model` tags name meta-llama/ or google/gemma are moved from 가능 to 조건부.

## Known Stubs

None. Nothing calls licenses.py until 02-04, as planned.

## Threat Flags

None beyond the plan's threat model (T-02-05 to T-02-08 mitigated and tested).

## Self-Check: PASSED

- FOUND: newsletter/stages/licenses.py, tests/test_licenses.py, tests/fixtures/golden_verdicts.json, tests/fixtures/github_license_w44.json
- FOUND commits: 4f97acf, c79f8eb, f0db165, ba4bf34 (ancestors of HEAD)
