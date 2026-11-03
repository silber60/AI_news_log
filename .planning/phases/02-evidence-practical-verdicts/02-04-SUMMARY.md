---
phase: 02-evidence-practical-verdicts
plan: 04
subsystem: enrich, pipeline, verdicts
status: complete
tags: [license, github-api, commercial-use, enriched-json, golden-set]
requires:
  - 02-01 (verdicts.py, enrich PoC/GPU path, render verdict line)
  - 02-02 (licenses.py, github_license_w44.json, golden_verdicts.json)
  - 02-03 (conftest only)
provides:
  - "enrich: per-item GitHub code license + HF weights license, item.commercial via licenses.commercial_use"
  - "enrich.enrich_items_with_records(items, entries, *, client=None) -> (items, records); enrich_items is a wrapper"
  - "archive/{week}/enriched.json written by run_build right after enrich"
  - "conftest.mock_github_api, registered in mock_enrich as routes['github_api']; autouse no_github_token fixture"
  - "tests/test_golden_verdicts.py (15 cases through enrich + finalize)"
affects: [02-05 pipeline wiring of notes/trend, 02-06 e2e]
tech-stack:
  added: []
  patterns: ["side absent (None) vs side unreadable (LicenseInfo(), 확인 필요)", "enrich returns (Item, record) internally; the archive record never fails the build"]
key-files:
  created:
    - tests/test_golden_verdicts.py
  modified:
    - newsletter/stages/enrich.py
    - newsletter/pipeline.py
    - tests/conftest.py
    - tests/fixtures/hf_models_w44.json
    - tests/test_enrich.py
    - tests/test_e2e.py
    - tests/test_hf_fixtures.py
decisions:
  - "A failed or invalid-id model fetch gives a weights side of LicenseInfo() (no source_url) and 확인 필요, as the plan states, rather than weights_license(None)'s model-page link."
  - "A bad repo URL gives a code side of 확인 필요 with no request; the record stores github_license.status 'bad_repo'."
  - "NOASSERTION keeps the GitHub LICENSE html_url as evidence (the file exists, a human can read it); the verdict is still 확인 필요."
  - "The golden test drives each case through enrich._enrich_one (respx answers built from the fixture) and verdicts.finalize, so it checks the wired path; no verdicts.decide() entry point was needed."
  - "Record evidence lists every URL from model_info, commercial, poc and hardware before finalize (deduplicated)."
metrics:
  duration: ~25 min
  completed: 2026-11-03
estimate:
  tokens: 95000
  tasks: 3
actuals:
  tokens: 10700
  tasks: 3
  commits: 5
plan_head_before: caebcee67cb1bd45a04787b42ff9071e108f3ba1
plan_head_after: bea589cf7bc03e21db88792b45ebcbfd331f1480
---

# Phase 2 Plan 04: License wiring, enriched.json and golden set Summary

Each build now reads the GitHub `/license` API and the primary HF model's license metadata per item. It sets 상업적 사용 to the stricter of the two sides, with both licenses stored separately. The build archives the raw public evidence for each rank in `archive/{week}/enriched.json`. A 15-case golden set checks commercial, PoC and GPU verdicts offline through the real enrich path.

## Tasks

| # | Task | Commits |
|---|------|---------|
| 1 | W44 build shows 상업적 사용 from GitHub + HF licenses (tracer) | e043009, bea589c (outage assert) |
| 2 | Live recapture + enriched.json (TDD) | db1fbd2 (RED), 2c9c196 (GREEN) |
| 3 | Golden set, 15 cases (TDD) | ca66128 |

Tracer gate: the auto-mode re-run of `<verify>` passed (`pytest -q` exit 0, ruff clean) before Task 2 started.

## W44 star Top 10 commercial verdicts (e2e)

| Rank | Repo | Code | Weights | 상업적 사용 | Card phrase |
|---|---|---|---|---|---|
| 1 | InternLM/xtuner | Apache-2.0 | none | 가능 | 💼 코드 상업 이용 가능, 라이선스 link to github.com/InternLM/xtuner/blob/main/LICENSE |
| 2 | hyz317/HairDeck | Apache-2.0 | apache-2.0 | 가능 | 💼 상업 이용 가능 |
| 3 | Tencent-Hunyuan/Hy-Nomas | NOASSERTION | apache-2.0 | 확인 필요 | no 💼 phrase |
| 4 | HiP3Rs/HiP3R | Apache-2.0 | none | 가능 | code only |
| 5 | google-deepmind/detectorscope | Apache-2.0 | gemma | 조건부 | 💼 조건부 상업 이용 |
| 6-10 | RSIHub, VibeGame, RoboHarness, OpenEBFM, AutoTavern | Apache-2.0 / MIT | none | 가능 | code only |

This is the research §1 projection exactly. 8 cards are 가능 (7 of them code only), 1 is 조건부 and 1 is 확인 필요, so 9 of 10 cards show a 상업 verdict. No expectation changed.

Upvote W44 set (test_enrich): Falcon (rank 3) is 가능 with both sides apache. Hy-Nomas, OmniShowcase, awesome-working-agent, LOWN and ChronoReplay are 확인 필요 (NOASSERTION or GitHub 404). The four papers with no repo and no model keep the default.

## Fixture recapture (D-15)

**Live, 2026-11-03.** I made 7 HF calls with the current `MODEL_EXPAND`. Kept fields: `id`, `cardData` (datasets/license/license_name/license_link), `gated`, `tags`, `safetensors` (parameters/total). I used no offline fallback.
- New: `cardData.license` on all 7 models. That is apache-2.0 for Falcon, Falcon-Big, Hy-Nomas and HairDeck, and gemma for the three detector-scope models. Hy-Nomas also gained `license_link` `https://huggingface.co/tencent/Hy-Nomas/blob/main/LICENSE`.
- Unchanged: tags, gated, datasets, and safetensors `{"F32": 302130176}`. No enrich expectation (size, datasets, release) changed.
- `test_model_capture_carries_license_fields` asserts these keys and limits each entry to the allowed key set.

## enriched.json record

Per rank: `rank, paper_id, model_id, linked_models [{id, gated}], spaces, datasets, weights_license {license, license_name, license_link}, gated, safetensors {total, parameters}, base_model_tags, github_license {status, spdx_id, name, html_url}, paper_fetch_ok, evidence [urls]`. A failed or bad paper fetch gives `paper_fetch_ok: false`, nulls and empty lists. Tests check that there are no `authors`, no `_ko` and no token-like strings, even with `GITHUB_TOKEN` set.

## Verification

- `uv run pytest -q`: exit 0, 828 tests pass. This includes 19 in test_golden_verdicts.py: 15 parametrized cases plus 4 checks.
- `uv run ruff check` and `ruff format --check newsletter tests`: clean.
- Acceptance greps: `licenses.commercial_use` in enrich.py = 1; `api.github.com` in conftest.py = 2; `delenv("GITHUB_TOKEN"` = 1; `enriched.json` in pipeline.py = 1; `def enrich_items_with_records` = 1. Hy-Nomas `cardData.license` prints apache-2.0.
- Mutation check (reverted, never committed): VRAM_OVERHEAD 1.2 to 1.3 failed 11 golden cases. Dropping `cc-by-nc-4.0` from the table failed G8.

## TDD Gate Compliance

- Task 2: RED db1fbd2. The 4 record tests failed with AttributeError because `enrich_items_with_records` was missing, and the e2e test failed because enriched.json was missing. The recaptured-fixture and card-vs-tag tests already passed at RED, since the fixture is in the same commit. GREEN 2c9c196.
- Task 3: there is no RED/GREEN split. At HEAD the test file did not exist (the plan's fail condition). Every case passed against the existing rules, so the plan's "fix the rule in code" step found nothing to fix, and there is a single test commit. The mutation check above shows the test can fail.

## Deviations from Plan

1. **[Rule 1 - Test name] Plan names `test_w44_coverage_and_verdicts_untouched`.** At HEAD the test is called `test_w44_coverage_and_code_poc`. I rewrote that test: it now asserts the per-rank W44 commercial list and keeps the PoC and claude_gpt asserts.
2. **[Rule 2 - Coverage] Extra non-fatal tests.** Added: a 301 redirect (T-02-15), a bad repo URL with no request, weights 불가 dominating Apache code, a failed model fetch giving 확인 필요, a failed paper fetch making no GitHub call, a check that license logs carry no repo ids, and the total-outage assert in `test_build_survives_total_hf_enrich_outage` (bea589c).
3. **Log test scope.** httpx's own INFO request line carries the GitHub URL under a root-level caplog. In production, `__main__` sets httpx to WARNING (02-02). The repo-id log test checks only the `newsletter` logger.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-02-13 is covered by the record privacy test. T-02-14 and T-02-15 are covered by the 403/500/301/transport tests, all non-fatal. T-02-16 is covered by the `license=<status> rank=<n>` logs and the autouse `no_github_token` fixture. T-02-SC holds: no new packages, and uv.lock is untouched.

## Self-Check: PASSED

- FOUND: tests/test_golden_verdicts.py, newsletter/stages/enrich.py, newsletter/pipeline.py, tests/fixtures/hf_models_w44.json
- FOUND commits (ancestors of HEAD): e043009, db1fbd2, 2c9c196, ca66128, bea589c
