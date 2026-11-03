---
phase: 02-evidence-practical-verdicts
plan: 01
subsystem: verdicts, enrich, render
status: complete
tags: [verdicts, poc, vram, evidence, email]
requires: []
provides:
  - newsletter/stages/verdicts.py (poc, hardware, enforce_evidence, finalize, POC_GATED_LABEL, EVIDENCE_HOSTS, HF_HOST, GITHUB_HOST, FLOAT_DTYPES)
  - render.verdict_line / render.license_link, verdict_lines + license_links in _context
  - template-version 6 (html + txt)
affects: [02-02, 02-04, 02-05]
tech-stack:
  added: []
  patterns: ["pure verdict module, enforce_evidence runs last in finalize", "render reads verdicts, never writes"]
key-files:
  created:
    - newsletter/stages/verdicts.py
    - tests/test_verdicts.py
  modified:
    - newsletter/stages/enrich.py
    - newsletter/pipeline.py
    - newsletter/stages/render.py
    - templates/email.html.j2
    - templates/email.txt.j2
    - tests/test_enrich.py
    - tests/test_e2e.py
    - tests/test_render.py
decisions:
  - "PoC with linked weights whose id fails the allowlist is 바로 가능 with no evidence, so finalize turns it into 확인 필요 (no fall-through to 코드만, which would deny existing weights)"
  - "enforce_evidence also clears est_vram_gb when it downgrades local_run; param_count is kept"
  - "license_link also requires the URL to be on huggingface.co or github.com (defense in depth for T-02-01)"
  - "Disclaimer row uses padding 0 0 6px 0 (same rhythm as the source row) instead of 6px 0 0 0"
metrics:
  duration: "~40 min"
  completed: 2026-11-03
actuals:
  tokens: 13200
  tasks: 3
  commits: 5
plan_head_before: 1533ddcfe4664ca77e88a2d2ae806f09a64b0cd4
plan_head_after: 2cde348
---

# Phase 2 Plan 01: Code verdicts tracer Summary

Code now decides PoC and GPU verdicts from the HF paper and model captures. `enforce_evidence` removes any positive verdict that lacks HF or GitHub evidence. Each card shows one line, such as "💼 … · 🧪 … · 🖥️ … · 🤖 …", with at most one 라이선스 link. The footer has the D-12 disclaimer, and the trend sits under the greeting. The worst-case email is 91,089 B.

## What was built

- **verdicts.py** (pure, no I/O): `poc()` uses the research §2 first-match table (Space, then open weights, then gated weights with `POC_GATED_LABEL`, then code, then 논문만). `hardware()` computes safetensors.total × 2 × 1.2 / 1e9, rounds to one decimal, and applies inclusive bands at 24 and 80 GB. A non-float dtype share above 1%, or a `base_model:adapter:` / `base_model:quantized:` tag, gives 확인 필요 but keeps the count. `enforce_evidence()` applies the full §7 table, and `finalize()` maps it over the items.
- **enrich**: `facts()` now also returns `gated` and `model_id`. `_enrich_one` sets PoC and hardware only on the success path after the paper fetch, so a failed fetch or a bad paper id leaves PoC at 확인 필요 (D-15).
- **pipeline**: `run_build` runs `verdicts.finalize` right after enrich.
- **render**: phrase constants (`COMMERCIAL_PHRASES`, `COMMERCIAL_CODE_ONLY_PHRASE`, `POC_PHRASES`, `POC_GATED_PHRASE`, `CLAUDE_GPT_PHRASES`) and `EVIDENCE_LINK_MAX = 200`. `verdict_line()` lists phrases in the order 💼, 🧪, 🖥️, 🤖. `license_link()` gives a link only when a 상업 phrase is shown.
- **templates (v6)**: one verdict row replaces the pill row (the `pill` macro stays for highlights). The text part gets a verdict line plus `라이선스: {url}`. The trend block now comes before highlight. Both footers carry the disclaimer.

## W44 results (e2e)

- PoC: [코드만, 바로 가능, 바로 가능, 코드만, 바로 가능, 코드만 ×5]. Card 1 shows "🧪 코드만 공개됐어요", and card 2 shows "🧪 바로 써볼 수 있어요".
- GPU: card 5 (detector-scope) stores est_vram_gb 0.7 with 가능 and shows "🖥️ 개인 GPU 약 1GB". The other nine cards are 확인 필요.
- Commercial and Claude/GPT stay at 확인 필요 until 02-02, 02-04 and 02-05 fill them.

## Byte budget

- Extended worst case: all four verdicts at their longest phrases (💼 코드 상업 이용 가능 · 🧪 승인 받고 써볼 수 있어요 · 🖥️ GPU 여러 장 필요 (약 999GB) · 🤖 Claude/GPT에서 바로 써요) plus a 200-char HF license link on all 10 cards and the disclaimer.
- **Result: 91,089 B. Headroom is 1,071 B against MAX_EMAIL_BYTES = 92,160.**
- No trim was needed. The stop rule did not fire, and the font-family inheritance trim was not applied.

## Tests

- `uv run pytest -q`: 557 tests collected, all pass (exit 0). `uv run ruff check` and `ruff format --check` are clean.
- `tests/test_verdicts.py`: 33 tests match `vram or hardware or enforce or evidence`, including the property test over all 54 positive combinations.

## Commits

- 01887c0 feat(02-01): code-decided PoC verdict on every card
- 5f0f4c7 test(02-01): add failing tests for VRAM verdict and evidence rule
- 188de7f feat(02-01): GPU verdict from safetensors and evidence rule for all verdicts
- 3416dfe test(02-01): add failing tests for full verdict line, license link and footer
- 2cde348 feat(02-01): full verdict line, license link, disclaimer and trend slot

## TDD Gate Compliance

- Task 2: RED 5f0f4c7, GREEN 188de7f. At RED, `verdicts.hardware` did not exist, so every `hardware`/`vram` test raised AttributeError. The extended enforce tests (commercial, hardware, 직접 사용, property) also failed, because enforce_evidence covered PoC only. The RED run was viewed through `tail -3`, so the exact failure count was not recorded.
- Task 3: RED 3416dfe (collection error: `COMMERCIAL_PHRASES`, `license_link` and `EVIDENCE_LINK_MAX` were missing from render), GREEN 2cde348.

## Deviations from Plan

1. **[Rule 1 - Bug] css_inline merges the global `a` rule into link styles.** The license link is rendered as `style="text-decoration: none;color: #A3A3A3"`. The test matches the color inside the style attribute instead of the exact string. No code change.
2. **[Rule 1 - Test scope] The disclaimer contains "상업적 사용" and "라이선스".** The tests that check "no 상업 or 라이선스 text" now look only at the cards, not the whole email.
3. **Disclaimer padding.** The plan asked for `padding: 6px 0 0 0`. I used `0 0 6px 0` so the row matches the source row above it and does not leave a 12 px gap followed by a 0 px gap. The text, size and color follow the plan.
4. **license_link host check.** Besides the 200-char cap, the link must be on huggingface.co or github.com. This adds to the T-02-01 mitigation.

## Known Stubs

None. Commercial and Claude/GPT verdicts stay at their schema default 확인 필요 until 02-02, 02-04 and 02-05 fill them. Render already handles every value.

## Threat Flags

None. No new endpoints or HTTP calls were added. Evidence links shown in the email are limited to HF and GitHub hosts, and Jinja autoescape stays on.

## Self-Check: PASSED

- newsletter/stages/verdicts.py and tests/test_verdicts.py exist.
- All 5 commits are ancestors of HEAD.
