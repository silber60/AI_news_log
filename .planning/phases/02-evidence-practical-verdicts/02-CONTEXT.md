# Phase 2: Evidence & Practical Verdicts - Context

**Gathered:** 2026-11-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Each card in the Phase 1.2 email gains code-decided practical verdicts: 상업적 사용, PoC, 실행 난이도·필요 GPU, and Claude/GPT 사용 가능. Each verdict comes with a short Claude-written reason built from code-supplied evidence. The issue also opens with a 2-3 sentence 이번 주 트렌드 총평.

Phase 1.1 / 1.2 already provide some of the inputs: `enrich.py` (HF paper/model facts, `poc.has_*`, `hardware.param_count`, `model_info.evidence`), schema v3 verdict fields that default to `확인 필요`, the README fetch, and the hidden badge row (01.1 D-17).

Not in this phase: highlight / Skill-GPTs picks and the explainer (Phase 3), the web version (Phase 4), subscribe (Phase 4.1), and cron (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### Display (email size)
- **D-01:** Verdicts render as one short line per card. Only known verdicts are shown, e.g. "💼 상업 가능 · 🧪 바로 써볼 수 있어요 · 🖥️ GPU 16GB · 🤖 Claude/GPT 기법 적용". `확인 필요` verdicts are omitted; if all are unknown, the line is dropped. This replaces the colored pill badges from Phase 1.1 (D-17 hide rule). Reason: the email has only about 1.5 KB of headroom under 90 KB (01.2-02 worst case 90,668 B). The planner must still trim repeated per-card markup if the new line would cross the cap.
- **D-02:** The email shows the one line plus at most one license evidence link per card. Detailed per-verdict reasons (ANLY-04) are stored in the Issue and shown in the Phase 4 web version, not in the email. ANLY-04 is still satisfied, because Claude writes the reasons from evidence and they are stored and published on the web.

### 상업적 사용 (EVID-02)
- **D-03:** Conservative rule. Take the stricter of the code license (GitHub) and the weights license (HF model card), and list both separately in the Issue.
  - permissive SPDX (Apache-2.0, MIT, BSD, …) → `가능`
  - custom or community licenses (Llama, Gemma, OpenRAIL, …) and gated models → `조건부`
  - non-commercial (CC-BY-NC*, research-only) → `불가`
  - missing or unrecognized → `확인 필요`
  
  The SPDX lookup table lives in code (EVID-02). A positive verdict without an evidence URL is downgraded to `확인 필요` (EVID-05).

### 실행 난이도·필요 GPU (EVID-04)
- **D-04:** Estimated VRAM is derived from the parameter count by code; the researcher proposes the formula, e.g. fp16 ≈ 2 bytes/param × overhead.
  - ≤ 24 GB → `가능` (consumer GPU, RTX 4090 class)
  - ≤ 80 GB → `제한적` (one server GPU)
  - larger → `불가`
  - unknown size → `확인 필요`
  
  These are the `LocalRun` labels frozen in Phase 1.

### PoC (EVID-03)
- **D-05:** Decided by code from weights, code, and demo availability, using the roadmap labels `바로 가능 / 코드만 / 논문만 / 확인 필요`. The email wording is friendly, e.g. `바로 가능` → "바로 써볼 수 있어요". The researcher maps each label to a short phrase.

### Claude/GPT 사용 가능 (ANLY-02)
- **D-06:** The meaning is "can I use this in my own work with Claude/ChatGPT?":
  - `직접 사용`: usable directly in Claude or ChatGPT, or callable from them via API/tool
  - `기법 적용 가능`: the idea can be imitated with prompts or workflows
  - `해당 없음`: a separate model unrelated to these assistants
  - `확인 필요`: unclear
  
  Claude proposes the label with a one-sentence reason from the abstract. Code validates the enum.

### 트렌드 총평 (ANLY-05)
- **D-07:** 2-3 sentences of 해요체 placed right under the greeting (the Figma "이번 주 흐름 한눈에" slot). It mentions only this week's N items, and code checks that every model it names is in the Top N.

### Claude's Discretion
- SPDX table contents, the VRAM formula, the exact one-line format and emojis, the golden-set (~10 papers) composition, and how the trend call fits in the call budget.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` §Phase 2; `.planning/REQUIREMENTS.md` EVID-01..05, ANLY-02, ANLY-04, ANLY-05
- `.planning/phases/01.2-star-selection-friendly-content/01.2-CONTEXT.md` and the 01.2 summaries (current pipeline, the size budget note in 01.2-02-SUMMARY)
- `.planning/phases/01.1-newsletter-design-v2/01.1-CONTEXT.md` and `01.1-FIGMA-SPEC.md` (the trend slot)
- `newsletter/schema.py` (v3 verdict models), `newsletter/stages/enrich.py`, `templates/email.*.j2`
- `.planning/research/PITFALLS.md` (license hallucination, evidence rules)
- `.claude/CLAUDE.md` (code decides verdicts; Claude only explains)

</canonical_refs>

<deferred>
## Deferred Ideas

- Per-verdict detailed reasons in the email body: web version only (Phase 4).

</deferred>

---

*Phase: 02-evidence-practical-verdicts*
*Context gathered: 2026-11-03*
