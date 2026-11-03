# Phase 2: Evidence & Practical Verdicts - Research

**Researched:** 2026-11-03
**Domain:** Deterministic license/PoC/VRAM verdicts from HF + GitHub metadata, Claude-written reasons and weekly trend, email size budget
**Confidence:** HIGH for data sources and the size budget (probed live and measured this session). MEDIUM for the license table entries that rest on HF ids alone. LOW for the font-inheritance trim, which is not needed this phase.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Display (email size)
- **D-01:** Verdicts render as one short line per card. Only known verdicts are shown, e.g. "💼 상업 가능 · 🧪 바로 써볼 수 있어요 · 🖥️ GPU 16GB · 🤖 Claude/GPT 기법 적용". `확인 필요` verdicts are omitted; if all are unknown, the line is dropped. This replaces the colored pill badges from Phase 1.1 (D-17 hide rule). Reason: the email has only about 1.5 KB of headroom under 90 KB (01.2-02 worst case 90,668 B). The planner must still trim repeated per-card markup if the new line would cross the cap.
- **D-02:** The email shows the one line plus at most one license evidence link per card. Detailed per-verdict reasons (ANLY-04) are stored in the Issue and shown in the Phase 4 web version, not in the email. ANLY-04 is still satisfied, because Claude writes the reasons from evidence and they are stored and published on the web.

#### 상업적 사용 (EVID-02)
- **D-03:** Conservative rule. Take the stricter of the code license (GitHub) and the weights license (HF model card), and list both separately in the Issue.
  - permissive SPDX (Apache-2.0, MIT, BSD, …) → `가능`
  - custom or community licenses (Llama, Gemma, OpenRAIL, …) and gated models → `조건부`
  - non-commercial (CC-BY-NC*, research-only) → `불가`
  - missing or unrecognized → `확인 필요`

  The SPDX lookup table lives in code (EVID-02). A positive verdict without an evidence URL is downgraded to `확인 필요` (EVID-05).

#### 실행 난이도·필요 GPU (EVID-04)
- **D-04:** Estimated VRAM is derived from the parameter count by code; the researcher proposes the formula, e.g. fp16 ≈ 2 bytes/param × overhead.
  - ≤ 24 GB → `가능` (consumer GPU, RTX 4090 class)
  - ≤ 80 GB → `제한적` (one server GPU)
  - larger → `불가`
  - unknown size → `확인 필요`

  These are the `LocalRun` labels frozen in Phase 1.

#### PoC (EVID-03)
- **D-05:** Decided by code from weights, code, and demo availability, using the roadmap labels `바로 가능 / 코드만 / 논문만 / 확인 필요`. The email wording is friendly, e.g. `바로 가능` → "바로 써볼 수 있어요". The researcher maps each label to a short phrase.

#### Claude/GPT 사용 가능 (ANLY-02)
- **D-06:** The meaning is "can I use this in my own work with Claude/ChatGPT?":
  - `직접 사용`: usable directly in Claude or ChatGPT, or callable from them via API/tool
  - `기법 적용 가능`: the idea can be imitated with prompts or workflows
  - `해당 없음`: a separate model unrelated to these assistants
  - `확인 필요`: unclear

  Claude proposes the label with a one-sentence reason from the abstract. Code validates the enum.

#### 트렌드 총평 (ANLY-05)
- **D-07:** 2-3 sentences of 해요체 placed right under the greeting (the Figma "이번 주 흐름 한눈에" slot). It mentions only this week's N items, and code checks that every model it names is in the Top N.

### Claude's Discretion
- SPDX table contents, the VRAM formula, the exact one-line format and emojis, the golden-set (~10 papers) composition, and how the trend call fits in the call budget.

### Deferred Ideas (OUT OF SCOPE)
- Per-verdict detailed reasons in the email body: web version only (Phase 4).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVID-01 | Collect linked HF models/Spaces/datasets, model license tags, gated flag, parameter count, and GitHub repo license, saved as `enriched.json` with evidence URLs | §1 data sources (HF `cardData.license`/`license_name`/`license_link`, `gated`, `safetensors.parameters`; GitHub `/repos/{o}/{r}/license`), §9 `enriched.json` record |
| EVID-02 | 상업적 사용 verdict from a code-owned SPDX table, code and weights licenses shown separately | §1 SPDX table, stricter-of rule, gated rule; stored in `CommercialUse.code_license` / `weights_license` |
| EVID-03 | PoC verdict from weights/code/demo availability | §2 rule table and phrases |
| EVID-04 | Size, estimated VRAM, local-run feasibility from parameter count, or `확인 필요` | §3 formula, dtype/adapter guards, thresholds |
| EVID-05 | Positive verdict without evidence URL → `확인 필요`; golden set of ~10 papers | §7 `enforce_evidence`, 15-case golden set with expected values |
| ANLY-02 | Claude/GPT label + one-sentence reason | §4 fold into the per-paper analyze call, plus the `직접 사용` guard |
| ANLY-04 | Claude writes 상업적 사용/PoC reasons from code-supplied evidence | §5 one batched post-verdict call, contradiction/grounding checks |
| ANLY-05 | 2-3 sentence trend, only this week's items | §6 a separate call, name allowlist check, placement |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Code decides license / PoC / GPU verdicts from HF/GitHub evidence. Claude only explains. Unknown → `확인 필요`.
- All Claude-generated text follows the humanizer rules (`prompts/humanizer_ko.md` is appended to every system prompt; see `analyze.system_prompt()` and `headline.headline_system_prompt()`).
- Public repo: never log emails, names or credentials, and never enable `smtplib` debug. This phase adds a `GITHUB_TOKEN`, which must never be logged or put in a URL.
- Compute weeks in `Asia/Seoul` (no change this phase).
- Email HTML: tables + inline CSS, system Korean font stack, < 90 KB.
- Do not change the frozen `Issue` schema contract outside a planned phase. This phase needs no change (§9).
- Commit author `silber60 <81203897+silber60@users.noreply.github.com>`.

## Summary

All the evidence needed is already reachable without new packages. HF `/api/models/{id}` with the current `MODEL_EXPAND` returns `cardData.license`, `license_name`, `license_link`, `gated` and `safetensors.parameters`/`total`; all were probed live on 14 models. GitHub `/repos/{o}/{r}/license` returns an SPDX id (or `NOASSERTION`) and an `html_url` that can serve as the evidence link. On the W44 star Top 10, all 10 repos have a LICENSE file, and the API agrees with the file header on the 3 repos checked. The API returned `NOASSERTION` for Tencent's Hy-Nomas preamble license, which the conservative rule needs. With `GITHUB_TOKEN` the limit is 1,000 req/h per repo, against about 10 calls per week.

Projected W44 coverage: 상업적 사용 known on 9/10 (8 `가능`, 1 `조건부`, 1 `확인 필요`). PoC known on 10/10. VRAM known on only 1/10: just 3 W44 papers link models, and 2 of those 3 have no safetensors total. No safe fallback raises that number; parsing the model name adds 0 on W44.

Size: the IBM Plex stack lowered the current worst case to **84,582 B** (re-measured, headroom 7,578 B). A prototype verdict line was rendered on all 10 cards at maximum length, each with a 200-char license link. It measured **90,652 B** (headroom 1,508 B). That fits under the cap with no trim, but the margin is thin. A tested contingency trim saves 7,650 B: move `{{ ff }}` from the 10 info-row cells to the 모델 정보 table.

**Primary recommendation:** Add a pure `newsletter/stages/verdicts.py` (SPDX table, stricter-of, PoC, VRAM, evidence enforcement) that runs on enrich output. Extend enrich to keep the raw license/dtype fields and call the GitHub license API. Add `claude_gpt` + reason to the existing per-paper analyze call. Add two small post-verdict Claude calls (reasons, trend) that follow the `headline.py` pattern: 2 attempts, code checks, non-fatal fallback. Issue schema v3 stays as it is.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| License/gated/param/dtype collection | enrich stage (HTTP, code) | `enriched.json` archive | Facts from HF/GitHub only, non-fatal |
| 상업적 사용 / PoC / VRAM verdicts | `verdicts.py` (pure code) | — | Hard rule: code decides |
| Evidence downgrade (EVID-05) | `verdicts.enforce_evidence` (last code step) | schema has evidence lists | Must run after every verdict writer |
| Claude/GPT label + reason | analyze call (Claude proposes) | `verdicts.py` guard (code validates/downgrades) | D-06: from the abstract |
| Commercial/PoC reasons | new Claude call (`notes.py`) | code checks | Claude explains code labels only |
| Trend | new Claude call (`trend.py`) | code name check | ANLY-05 |
| Verdict line + license link | `render.py` helpers (code phrases) | templates | Phrases are code constants, not Claude text |

## Standard Stack

No new dependencies. Everything uses what is already locked: `httpx` (HTTP), `tenacity` (retry), `pydantic` (models), `anthropic` (`messages.parse` with `output_format`), `respx` (HTTP mocks), `jinja2` + `css_inline` (render), `pytest`. [VERIFIED: newsletter/stages/enrich.py:28-30 imports `httpx`, `tenacity`; analyze.py:15 `anthropic`; render.py:10-11 `css_inline`, `jinja2`]

## Package Legitimacy Audit

Not applicable. This phase installs no external packages.

## 1. License evidence (EVID-01/02, D-03)

### Where the weights license lives (HF model API)

Live probe this session, `GET https://huggingface.co/api/models/{id}?expand[]=safetensors&expand[]=cardData&expand[]=gated&expand[]=tags` (the existing `MODEL_EXPAND`, [VERIFIED: enrich.py:54 `MODEL_EXPAND = "expand[]=safetensors&expand[]=cardData&expand[]=gated&expand[]=tags"`]):

| Model | `cardData.license` | `license_name` | `license_link` | `license:` tag | `gated` | `safetensors.total` / `parameters` |
|---|---|---|---|---|---|---|
| meta-llama/Llama-3.1-8B | `llama3.1` | – | – | `license:llama3.1` | `manual` | 8030261248 / `{'BF16': …}` |
| google/gemma-2-2b | `gemma` | – | – | `license:gemma` | `manual` | 2614341888 / `{'F32': …}` |
| Qwen/Qwen2.5-7B-Instruct | `apache-2.0` | – | `https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/main/LICENSE` | `license:apache-2.0` | `False` | 7615616512 BF16 |
| Qwen/Qwen2.5-72B-Instruct | `other` | `qwen` | `https://huggingface.co/…/blob/main/LICENSE` | `license:other` | `False` | 72706203648 BF16 |
| deepseek-ai/DeepSeek-V3 | – | – | – | none | `False` | 684489845504 (`BF16`, `F8_E4M3`, `F32`) |
| stabilityai/stable-diffusion-xl-base-1.0 | `openrail++` | – | – | `license:openrail++` | `False` | 2567463684 F32 |
| black-forest-labs/FLUX.1-dev | `other` | `flux-1-dev-non-commercial-license` | `LICENSE.md` (relative) | `license:other` | `auto` | 11901408320 BF16 |
| bigscience/bloom | `bigscience-bloom-rail-1.0` | – | – | same | `False` | 176247271424 BF16 |
| CohereLabs/c4ai-command-r-v01 | `cc-by-nc-4.0` | – | – | same | `auto` | 34980831232 F16 |
| mistralai/Mistral-7B-v0.1 | `apache-2.0` | – | – | same | `False` | 7241732096 BF16 |
| TheBloke/Llama-2-7B-GPTQ | `llama2` | – | – | `license:llama2`, `base_model:quantized:meta-llama/Llama-2-7b-hf` | `False` | 6739777536 (`F32`, `I32`: 6476005376, `F16`) |
| tencent/Hy-Nomas (W44) | `apache-2.0` | – | `https://huggingface.co/tencent/Hy-Nomas/blob/main/LICENSE` | `license:apache-2.0` | `False` | none |
| hyz317/HairDeck (W44) | `apache-2.0` | – | – | `license:apache-2.0` | `False` | none |
| liamdugan/detector-scope (W44) | `gemma` | – | – | `license:gemma`, `base_model:finetune:google/gemma-2-2b` | `False` | 302130176 F32 |

[VERIFIED: live HF API probe, 2026-11-03]

Findings:
- **Read order:** `cardData.license` (str, or list → take the strictest), then the `license:` tags. If the value is `other`, look up `cardData.license_name`. The W44 fixture `hf_models_w44.json` has `cardData: {}` for Hy-Nomas and HairDeck, but live data has `cardData.license`. The fixture was trimmed, so the planner must recapture `cardData.license/license_name/license_link` and `safetensors.parameters`. The tags are already in the fixture and give the same answer.
- `gated` values seen: `False`, `"manual"`, `"auto"`. Treat anything other than `False`/`None` as gated. This matches the existing check at enrich.py:195: `gated = any(m.get("gated") not in (False, None) for m in models)`.
- `license_link` can be relative (`LICENSE.md`), on HF, or (in principle) an arbitrary external URL. **Evidence URL rule:** accept it only if it starts with `https://huggingface.co/` or `https://github.com/` and has no `?`, `#` or `..`. Resolve a relative value to `https://huggingface.co/{model_id}/blob/main/{link}` (same rules). Otherwise use the model page `https://huggingface.co/{model_id}`. This keeps every rendered link on two known hosts.
- DeepSeek-V3 has no license metadata at all. Its README prose states the license, and prose is never read (PITFALLS). The weights side is `확인 필요`.

### Where the code license comes from

**Recommend: GitHub REST `GET https://api.github.com/repos/{owner}/{repo}/license`**, authenticated with `GITHUB_TOKEN` when set and unauthenticated otherwise.

- Rate limits: "The primary rate limit for unauthenticated requests is 60 requests per hour." and "The rate limit for `GITHUB_TOKEN` is 1,000 requests per hour per repository." [CITED: docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api]. Hosted runners share egress IPs, so the token matters in Actions [ASSUMED]. Locally, 10 calls per build fit in 60/h.
- Response shape (live this session):
  - `InternLM/xtuner`: `license.spdx_id = "Apache-2.0"`, `html_url = "https://github.com/InternLM/xtuner/blob/main/LICENSE"`
  - `tettethu/VibeGame`: `Apache-2.0` (the LICENSE has a third-party notice appended, and the API still detects it)
  - `Tencent-Hunyuan/Hy-Nomas`: `{'key': 'other', 'name': 'Other', 'spdx_id': 'NOASSERTION'}`, `path: LICENSE`
  - `deepseek-ai/DeepSeek-V3`: `MIT`, `html_url .../blob/main/LICENSE-CODE`
  - `justin4ai/OmniShowcase`: HTTP 404 `{"message": "Not Found"}` (no license file)

  [VERIFIED: live GitHub API, 2026-11-03]
- Mapping: `spdx_id` in the SPDX table (casefolded). `NOASSERTION`, missing, 404, 403/429 (rate limit) or 3xx (renamed repo) → code side `확인 필요` plus a log reason code. Evidence = `html_url` if it starts with `https://github.com/`.
- Headers: `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `Authorization: Bearer <token>` only when the env var is non-empty [ASSUMED: standard GitHub REST headers].
- Repo parsing: reuse `enrich.parse_repo` (allowlist regex, [VERIFIED: enrich.py:79-81 `GITHUB_REPO_RE = re.compile(r"^https://github\.com/([A-Za-z0-9-]{1,39})/([\w.-]{1,100}?)(?:\.git)?/?$")`]).
- Rejected alternatives:
  - Raw `LICENSE` text matching: 10/10 W44 repos answered `raw.githubusercontent.com/{o}/{r}/HEAD/LICENSE` with 200. That works, but it would mean hand-rolling licensee, and a 4 KB substring match would wrongly call Hy-Nomas "Apache" (its text says Apache-2.0 "except for the third-party components"). If used at all, keep it as a fallback only, matching the canonical header only at the start of the file. Not recommended for this phase.
  - The HF paper `githubRepo` gives only the URL, not the license.

**Workflow change:** add `GITHUB_TOKEN: ${{ github.token }}` to the build step env. Use `github.token`, not `secrets.GITHUB_TOKEN`, because `tests/test_workflow_static.py:74-75` asserts `build.count("secrets.") == 1` [VERIFIED: tests/test_workflow_static.py:74-75 `assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in build` / `assert build.count("secrets.") == 1`]. `permissions: contents: read` is enough for public-repo metadata [ASSUMED].

### SPDX → verdict table (code constant in `verdicts.py`)

Keys are casefolded HF ids (the full HF list was fetched [CITED: huggingface.co/docs/hub/repositories-licenses]) and GitHub SPDX ids. Normalize by casefolding and stripping a trailing `-only` / `-or-later`.

| Verdict | Keys |
|---|---|
| `가능` (permissive) | `apache-2.0`, `mit`, `mit-0`, `bsd`, `bsd-2-clause`, `bsd-3-clause`, `bsd-3-clause-clear`, `0bsd`, `isc`, `zlib`, `bsl-1.0`, `unlicense`, `cc0-1.0`, `cc-by-2.0`, `cc-by-2.5`, `cc-by-3.0`, `cc-by-4.0`, `postgresql`, `ncsa`, `wtfpl`, `afl-3.0`, `ecl-2.0`, `ms-pl`, `artistic-2.0`, `upl-1.0`, `odc-by`, `pddl`, `cdla-permissive-1.0`, `cdla-permissive-2.0` |
| `조건부` (copyleft: commercial use allowed with share/notice duties) | `mpl-2.0`, `lgpl`, `lgpl-2.1`, `lgpl-3.0`, `lgpl-lr`, `gpl`, `gpl-2.0`, `gpl-3.0`, `agpl-3.0`, `epl-1.0`, `epl-2.0`, `eupl-1.1`, `eupl-1.2`, `osl-3.0`, `cc-by-sa-3.0`, `cc-by-sa-4.0`, `cc-by-nd-4.0`, `cdla-sharing-1.0`, `odbl`, `gfdl`, `lppl-1.3c`, `ofl-1.1` |
| `조건부` (custom/community, D-03) | `openrail`, `openrail++`, `bigscience-openrail-m`, `creativeml-openrail-m`, `bigscience-bloom-rail-1.0`, `bigcode-openrail-m`, `llama2`, `llama3`, `llama3.1`, `llama3.2`, `llama3.3`, `llama4`, `gemma`, `grok2-community`, `openmdw-1.0`, `openmdw-1.1`, `apple-ascl`, `c-uda` |
| `조건부` (`other` + known `license_name`) | `qwen` [VERIFIED: Qwen2.5-72B `license_name`], `tongyi-qianwen`, `deepseek`, `deepseek-license` [ASSUMED names] |
| `불가` (non-commercial / research-only) | `cc-by-nc-2.0`, `cc-by-nc-3.0`, `cc-by-nc-4.0`, `cc-by-nc-nd-3.0`, `cc-by-nc-nd-4.0`, `cc-by-nc-sa-2.0`, `cc-by-nc-sa-3.0`, `cc-by-nc-sa-4.0`, `fair-noncommercial-research-license`, `deepfloyd-if-license`, `intel-research`, `h-research`, `apple-amlr` |
| `불가` (keyword on `license_name` when `license == "other"`) | name contains `non-commercial`, `noncommercial`, `-nc-` or `research` (e.g. `flux-1-dev-non-commercial-license`, `qwen-research`) |
| `확인 필요` | `other` with an unknown/missing name, `unknown`, `cc` (family, ambiguous), `noassertion`, `None`, anything not listed |

Classifying copyleft as `조건부` is my reading of D-03. D-03 names only permissive, custom, NC and unknown [ASSUMED: owner confirmation].

### Stricter-of rule and gated handling

```python
# verdicts.py (sketch). Strictness order: 가능 < 조건부 < 확인 필요 < 불가
_RANK = {"가능": 0, "조건부": 1, "확인 필요": 2, "불가": 3}

def weights_side(lic: str | None, name: str | None, gated: bool) -> CommercialVerdict:
    v = lookup(lic, name)                  # table above
    if gated and v == "가능":
        v = "조건부"                        # D-03: gated -> 조건부
    return v

def commercial(code: CommercialVerdict | None, weights: CommercialVerdict | None) -> CommercialVerdict:
    sides = [v for v in (code, weights) if v is not None]   # None = side does not exist
    return max(sides, key=_RANK.__getitem__) if sides else "확인 필요"
```

- A side **exists** when there is something to license. The code side exists when `item.github_url` is set; the weights side exists when the paper has a public linked model (`poc.has_weights`). If the side exists but its license could not be read, it is `확인 필요` and the overall result is then at best `확인 필요`. Example: Hy-Nomas, code `NOASSERTION` + weights `apache-2.0` → `확인 필요`.
- `불가` dominates even an unknown side: one known non-commercial side is enough.
- Fine-tunes inheriting a base license (PITFALLS Pitfall 3): optional guard. If the weights card says permissive but the tags carry `base_model:*:meta-llama/…` or `base_model:*:google/gemma…`, use `조건부` [ASSUMED heuristic; the W44 detector-scope card already says `gemma`, so it changes nothing on W44].
- Only the primary model (highest downloads, the existing `primary_model`) is read. Other linked models are not fetched; this is a known limit.

### W44 star Top 10 coverage (projected)

| # | Paper / repo | Code side | Weights side | 상업적 사용 | PoC | VRAM |
|---|---|---|---|---|---|---|
| 1 | 2610.35518 InternLM/xtuner | Apache-2.0 (API) | none | 가능 | 코드만 | 확인 필요 |
| 2 | 2610.40599 hyz317/HairDeck | Apache (file header) | apache-2.0 | 가능 | 바로 가능 (model + 1 Space) | 확인 필요 (no total) |
| 3 | 2610.36729 Tencent-Hunyuan/Hy-Nomas | NOASSERTION (API) | apache-2.0 | **확인 필요** | 바로 가능 (3 Spaces) | 확인 필요 (no total) |
| 4 | 2610.31635 HiP3Rs/HiP3R | Apache (header) | none | 가능 | 코드만 | 확인 필요 |
| 5 | 2610.30006 google-deepmind/detectorscope | Apache (header) | gemma | 조건부 | 바로 가능 (2 Spaces) | 0.7 GB → 가능 |
| 6 | 2610.32253 simple-agent-lab/RSIHub | Apache (header) | none | 가능 | 코드만 | 확인 필요 |
| 7 | 2610.33106 tettethu/VibeGame | Apache-2.0 (API) | none | 가능 | 코드만 | 확인 필요 |
| 8 | 2610.14018 BinceQu/RoboHarness | MIT (header) | none | 가능 | 코드만 | 확인 필요 |
| 9 | 2610.33005 datamllab/OpenEBFM | MIT (header) | none | 가능 | 코드만 | 확인 필요 |
| 10 | 2610.33845 MCG-NJU/AutoTavern | MIT (header) | none | 가능 | 코드만 | 확인 필요 |

[VERIFIED: raw LICENSE probes for all 10, GitHub API for 3, fixture `hf_papers_w44.json` linkedModels/linkedSpaces]. The 7 "header" rows assume the API returns the SPDX id that matches the file header [ASSUMED; the capture task confirms].

Seven of 10 are `가능` on code only. The phrase must say so, or readers will think the model is commercially usable when no weights exist (§8 uses "💼 코드 상업 이용 가능").

## 2. PoC (EVID-03, D-05)

Inputs exist: [VERIFIED: schema.py:84-90 `class PocReadiness(Strict): verdict: PocVerdict = "확인 필요"; has_weights: bool | None = None; has_code: bool | None = None; has_demo: bool | None = None; evidence: list[EvidenceLink] = []; reason_ko: str | None = None`]. Enrich sets `has_*` only to True [VERIFIED: enrich.py:242 `poc_update = {k: True for k in ("has_weights", "has_code", "has_demo") if f[k]}`].

| Condition (first match) | Verdict | Evidence | Email phrase |
|---|---|---|---|
| `has_demo` (HF Space) | `바로 가능` | `HF 데모` Space URL | 🧪 바로 써볼 수 있어요 |
| `has_weights` and not gated | `바로 가능` | `HF 모델` URL | 🧪 바로 써볼 수 있어요 |
| `has_weights` gated only | `바로 가능` | `HF 모델` URL | 🧪 승인 받고 써볼 수 있어요 |
| `has_code` | `코드만` | `item.github_url` | 🧪 코드만 공개됐어요 |
| paper API fetched OK and none of the above | `논문만` | `item.hf_url` | 🧪 아직 논문만 있어요 |
| paper API failed / bad id | `확인 필요` | – | (omitted) |

`논문만` is a negative fact, so it is set only when the paper API call succeeded. The verdict must be computed inside or right after `_enrich_one`, where success is known (`has_*` stays `None`, never `False`, as today). A demo outranks weights because a Space needs no setup.

## 3. VRAM (EVID-04, D-04)

**Formula:** `est_vram_gb = round(params × 2 bytes × 1.2 / 1e9, 1)`. That is fp16/bf16 weights plus 20% for activations, KV cache and CUDA context [ASSUMED rule of thumb; conservative for quantized checkpoints, which are excluded anyway]. Labels: `≤ 24.0 → 가능`, `≤ 80.0 → 제한적`, `> 80.0 → 불가`. The boundaries are inclusive per D-04. So 가능 ⇔ params ≤ 10.0 B, and 제한적 ⇔ params ≤ 33.3 B.

| Model | params | est GB | label |
|---|---|---|---|
| detector-scope | 0.302 B | 0.7 | 가능 |
| gemma-2-2b | 2.61 B | 6.3 | 가능 |
| Mistral-7B | 7.24 B | 17.4 | 가능 |
| Llama-3.1-8B | 8.03 B | 19.3 | 가능 |
| FLUX.1-dev | 11.9 B | 28.6 | 제한적 |
| Command-R | 35.0 B | 84.0 | 불가 |
| Qwen2.5-72B | 72.7 B | 174.5 | 불가 |

**Parameter source: `safetensors.total` only, with guards.** Each guard below → `확인 필요`.
- `safetensors` missing or `total` not a positive int (the existing `param_total`, [VERIFIED: enrich.py:173-180]).
- `safetensors.parameters` contains a non-float dtype (`I8`, `U8`, `I16`, `I32`, `I64`, `BOOL`) with more than 1% of total. Packed quantization (GPTQ `I32`: 6476005376 of 6739777536) makes `total` meaningless. Allowed float keys: `F64`, `F32`, `F16`, `BF16`, `F8_E4M3`, `F8_E5M2`.
- Tags contain `base_model:adapter:` (a LoRA count is not the runtime size) or `base_model:quantized:`.

Rejected sources:
- `config.json`: needs per-architecture math and is not code-verifiable.
- A model-name token like "7B": unsafe with `A3B` (MoE active), `8x7B` and fine-tunes, and it adds 0 coverage on W44, because none of the 3 linked W44 models has a size in its name.

Coverage stays 1/10 on W44. Most W44 papers link no model at all, so this is the honest result.

Evidence: `EvidenceLink(label="HF 모델", url=f"https://huggingface.co/{model_id}")`. Schema fields exist [VERIFIED: schema.py:93-97 `class Hardware(Strict): param_count: int | None = None; est_vram_gb: float | None = None; local_run: LocalRun = "확인 필요"; evidence: list[EvidenceLink] = []`, and :35 `LocalRun = Literal["가능", "제한적", "불가", "확인 필요"]`]. `Hardware` has no `reason_ko`, which is fine: ANLY-04 covers only 상업적 사용/PoC.

Email phrase (GB = `ceil(est_vram_gb)`): `가능` → "🖥️ 개인 GPU 약 {n}GB"; `제한적` → "🖥️ 서버 GPU 약 {n}GB"; `불가` → "🖥️ GPU 여러 장 필요 (약 {n}GB)".

## 4. Claude/GPT (ANLY-02, D-06)

**Fold into the existing per-paper analyze call** (D-06 says "from the abstract", and the abstract is already in `paper_block`). Add to `ItemAnalysisLLM`, which is not covered by the Issue snapshot (the test compares `Issue.model_json_schema()` only [VERIFIED: tests/test_schema.py:254-261]):

```python
claude_gpt: ClaudeGptVerdict        # Literal enforced by structured outputs + pydantic
claude_gpt_reason_ko: str           # one 해요체 sentence, <= 60 chars (code check)
```

Enum [VERIFIED: schema.py:32 `ClaudeGptVerdict = Literal["직접 사용", "기법 적용 가능", "해당 없음", "확인 필요"]`].

Prompt section (`analyze_paper.md`, bump `prompt-version` to 5):
- Definitions, verbatim from D-06, plus the base rate: "대부분의 논문은 `기법 적용 가능` 또는 `해당 없음`이에요."
- `직접 사용` only when the abstract says the release is something Claude/ChatGPT can call or load as is: an MCP server, a plugin/GPT/Skill, a prompt or skill file, or a hosted API meant for tool calling. Weights you must host yourself are never `직접 사용`.
- `기법 적용 가능` when the method is a prompting, agent, RAG or workflow pattern a user could imitate in a chat.
- `해당 없음` for vision/audio/robotics/generation models with nothing to imitate in a chat.
- The reason names what in the abstract supports the label and does not repeat the label.

Code checks (in `analyze.check`): `claude_gpt_reason_ko` non-empty, ≤ 60, 해요체 (`not_haeyo`), no other label string (`직접 사용`/`기법 적용 가능`/`해당 없음`) inside the reason.

Code guard after enrich (`verdicts.claude_gpt_guard`): `직접 사용` requires an artifact URL (`item.github_url`, `item.project_url` or a Space). Otherwise → `확인 필요` and `reason_ko=None` (EVID-05, since `ClaudeGptUse` has no evidence list). If more than 3 items in a week get `직접 사용`, log a warning (reason code only).

`test_claude_absent_while_claude_gpt_verdicts_unknown` stays green only while `issue_w44.json` keeps `확인 필요`. Tests built on enriched issues must expect "Claude/GPT" in the line (Pitfall 5 note in test_render.py).

## 5. Reasons (ANLY-04, D-02)

Storage exists: `CommercialUse.reason_ko`, `PocReadiness.reason_ko`, `ClaudeGptUse.reason_ko` [VERIFIED: schema.py:76-102]. Reasons are not rendered in the email this phase (D-02). They go to `issue.json` for Phase 4.

**One batched call after verdicts** (`newsletter/stages/notes.py`, prompt `prompts/verdict_notes.md` + humanizer). Input is code facts only, no URLs:

```
<items>
rank: 3
commercial: 확인 필요
code_license: Other (NOASSERTION)
weights_license: apache-2.0
weights_gated: no
poc: 바로 가능
has_weights: yes
has_code: yes
has_demo: yes
</items>
```

Output model (not part of Issue):

```python
class VerdictNoteLLM(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rank: int
    commercial_reason_ko: str   # <= 60
    poc_reason_ko: str          # <= 60

class VerdictNotesLLM(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: list[VerdictNoteLLM]
```

Code checks per note. A failing note gets `reason_ko=None`; the build never fails.
- Ranks are exactly the input ranks, with no duplicates.
- Length ≤ 60, `not_haeyo` false, no URL (`_URL_RE`), no hype words (`headline.HYPE_WORDS`).
- **Grounding:** every license token the reason mentions must appear in that item's input. Use a code list of license words: `MIT`, `Apache`, `BSD`, `GPL`, `LGPL`, `AGPL`, `MPL`, `CC`, `OpenRAIL`, `RAIL`, `Llama`, `Gemma`, `Qwen`, `DeepSeek`, `비상업`, `연구용`. A token absent from the input → `note_ungrounded`.
- **No contradiction (polarity table):** `가능` → forbid `불가|쓸 수 없|안 돼요|금지`. `불가` → forbid `쓸 수 있어요|가능해요|제한 없이`. `조건부`/`확인 필요` → forbid `제한 없이|자유롭게`. For PoC `논문만`, forbid `바로 써|데모`. For `코드만`, forbid `데모|바로 써` [ASSUMED list; tune with fixtures].
- The prompt rule "판정을 다시 쓰지 말고 근거만 써요" keeps the reason from restating labels, which makes the polarity check rarely fire.
- Verdict `확인 필요`: skip Claude and store the code constant `"공개된 근거를 찾지 못해 확인이 필요해요."`. This is an option [ASSUMED owner OK, since ANLY-04 says Claude writes reasons from evidence and here there is none]. Alternatively send it to Claude as well.

## 6. Trend (ANLY-05, D-07)

**Separate call** (`newsletter/stages/trend.py`, `prompts/trend.md` + humanizer), same shape as `write_headline`: 2 attempts, `_with_feedback`, then fallback `None`, so the section stays hidden. Folding it into the headline call is possible but couples failure modes. The headline input is also only the top 3 [VERIFIED: headline.py:34 `INPUT_RANKS = 3`].

Input: all N items as `rank`, `title_ko`, `title_en`, `ai_type`, `summary_ko`. No verdicts, so Claude never counts licenses.

Output: `TrendLLM { trend_ko: str }`.

Code checks:
- 2-3 sentences (`analyze._SENT_SPLIT`), ≤ 300 chars (matches the existing worst-case `trend_ko = "흐" * 300`), each sentence 해요체.
- No URL, no hype words, no `AUTHORSHIP_RE` (bans "Claude", "AI가", "자동").
- **Name allowlist:** collect name-like tokens with `re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[-.+][A-Za-z0-9]+)*", trend)`. Flag a token if it has an uppercase letter or a digit and its casefold is not in the allowlist: tokens from this week's `title_en`, `title_ko`, `summary_ko`, plus a fixed generic list (`AI, LLM, VLM, VLA, MoE, RAG, GPU, API, 3D, 2D, TTS, ASR, OCR, …`). Lowercase English terms (fine-tuning, diffusion) pass. Any flagged token → `trend_unknown_name`, then retry.
- `(\d+)위` must be within 1..N. Digits not present in the input → `trend_number` (blocks invented stats).

Placement: in the template, the trend `<tr data-section="trend">` sits after highlight [VERIFIED: templates/email.html.j2 order: greeting → highlight → trend]. The Figma spec has the same order (01.1-FIGMA-SPEC §5/§6). D-07 says right under the greeting, so move the trend block above highlight in both templates (template-version 6). In Phase 2 highlights are empty, so either order looks the same.

**Call budget:** normal path 10 analyze + 1 headline + 1 notes + 1 trend = **13** (today 11). Worst path 2× each = 26. `test_e2e`/`test_analyze` assert call counts (`== 11` / `== 12` per 01.1-03 SUMMARY), so those must be updated. `FakeAnthropic.default_response` dispatches on `output_format`, so it needs defaults for `VerdictNotesLLM` and `TrendLLM` [VERIFIED: tests/conftest.py:273-277].

## 7. EVID-05 downgrade and golden set

`verdicts.enforce_evidence(item) -> Item` runs **last** (after the code verdicts and the Claude/GPT guard). The positive sets:

| Field | Positive values | Required evidence | On missing |
|---|---|---|---|
| `commercial.verdict` | `가능`, `조건부` | `commercial.evidence` non-empty, every URL on `https://huggingface.co/` or `https://github.com/` | → `확인 필요`, `reason_ko=None` |
| `poc.verdict` | `바로 가능`, `코드만` | `poc.evidence` non-empty | → `확인 필요` |
| `hardware.local_run` | `가능`, `제한적` | `hardware.evidence` non-empty | → `확인 필요` (keep `param_count`) |
| `claude_gpt.verdict` | `직접 사용` | `github_url` / `project_url` / Space | → `확인 필요` |

Also run it as a property test: build items with random verdicts and empty evidence, and assert no positive survives.

**Golden set** (`tests/fixtures/golden_verdicts.json` plus `tests/test_golden_verdicts.py`; pure functions, offline). Each case holds the captured HF model JSON subset (cardData license fields, gated, tags, safetensors), the GitHub license JSON or a 404, paper flags, and the expected verdicts:

| # | Case | Code | Weights | Expect 상업 | Expect PoC | Expect GPU |
|---|---|---|---|---|---|---|
| G1 | Llama-3.1-8B | – | llama3.1, gated | 조건부 | 바로 가능 (gated) | 가능 19.3 |
| G2 | gemma-2-2b | – | gemma, gated | 조건부 | 바로 가능 | 가능 6.3 |
| G3 | Qwen2.5-7B-Instruct | – | apache-2.0 + HF link | 가능 | 바로 가능 | 가능 18.3 |
| G4 | Qwen2.5-72B-Instruct | – | other/qwen | 조건부 | 바로 가능 | 불가 174.5 |
| G5 | DeepSeek-V3 | MIT (LICENSE-CODE) | none | 확인 필요 | 바로 가능 | 불가 |
| G6 | FLUX.1-dev | – | other/flux-1-dev-non-commercial-license, relative link | 불가 | 바로 가능 (gated) | 제한적 28.6 |
| G7 | SDXL base | – | openrail++ | 조건부 | 바로 가능 | 가능 6.2 |
| G8 | Command-R | – | cc-by-nc-4.0, gated | 불가 | 바로 가능 | 불가 84.0 |
| G9 | Mistral-7B-v0.1 | – | apache-2.0 | 가능 | 바로 가능 | 가능 17.4 |
| G10 | Llama-2-7B-GPTQ | – | llama2, quantized | 조건부 | 바로 가능 | 확인 필요 |
| G11 | W44 xtuner | Apache-2.0 | – | 가능 | 코드만 | 확인 필요 |
| G12 | W44 Hy-Nomas | NOASSERTION | apache-2.0 | 확인 필요 | 바로 가능 | 확인 필요 |
| G13 | W44 detectorscope | Apache-2.0 | gemma | 조건부 | 바로 가능 | 가능 0.7 |
| G14 | W44 OmniShowcase | 404 | – | 확인 필요 | 코드만 | 확인 필요 |
| G15 | W44 PDRVLA (2610.37381) | – | – | 확인 필요 | 논문만 | 확인 필요 |

The set includes ≥ 1 `확인 필요` and ≥ 1 `불가` (PITFALLS checklist). The capture task needs about 10 HF calls (free) and ≤ 10 GitHub calls; store only the license-relevant keys, no READMEs.

## 8. Email line (D-01)

**Format.** Code-built phrases, joined by " · ". `확인 필요` is dropped, and the whole `<tr>` is dropped when the list is empty. This replaces the pill `<tr>` in the card macro [VERIFIED: templates/email.html.j2 card macro `{%- if it.commercial.verdict != "확인 필요" or … %}` pill row].

| Verdict | Phrase |
|---|---|
| 상업 가능 (both sides or weights only) | 💼 상업 이용 가능 |
| 상업 가능 (code side only) | 💼 코드 상업 이용 가능 |
| 조건부 | 💼 조건부 상업 이용 |
| 불가 | 💼 상업 이용 불가 |
| PoC | §2 phrases |
| GPU | §3 phrases |
| 직접 사용 | 🤖 Claude/GPT에서 바로 써요 |
| 기법 적용 가능 | 🤖 Claude/GPT 기법 적용 |
| 해당 없음 | 🤖 Claude/GPT와 별개 모델 |

Line plus link: `… · <a href="{license_url}" style="color: #A3A3A3;">라이선스</a>`. The link appears only when the 상업 phrase is shown. Use the evidence of the side that set the final verdict (on a tie, the weights side). Skip the link if the URL is longer than 200 chars (`EVIDENCE_LINK_MAX = 200`).

```jinja
{%- set vl = verdict_lines[it.rank] %}
{%- if vl %}
<tr><td style="{{ ff }} padding: 12px 0 0 0; font-size: 13px; line-height: 170%; color: #555555;">{{ vl|join(" · ") }}{% if license_links[it.rank] %} · <a href="{{ license_links[it.rank] }}" style="color: #A3A3A3;">라이선스</a>{% endif %}</td></tr>
{%- endif %}
```

`render._context` adds `verdict_lines: {rank: [str]}` and `license_links: {rank: str | None}`, the same pattern as `info_rows`. The text part gets one plain line: `{{ vl|join(" · ") }}` plus `라이선스: {url}`.

**Byte cost (measured).**
- Current worst case: **84,582 B**, headroom 7,578 against `MAX_EMAIL_BYTES = 90 * 1024` [VERIFIED: `uv run pytest tests/test_render.py -k worst_case_under -s` → `worst-case email.html bytes=84582 headroom=7578`; render.py:20 `MAX_EMAIL_BYTES = 90 * 1024`].
- Prototype (scratch template copy) with the longest phrases ("💼 조건부 상업 이용 · 🧪 승인 받고 써볼 수 있어요 · 🖥️ GPU 여러 장 필요 (약 999GB) · 🤖 Claude/GPT 기법 적용") and a 200-char link on all 10 cards: **90,652 B, headroom 1,508 B**, about 607 B per card. Under the cap, so no trim is required by D-01.
- `_worst_case` in test_render.py must be extended to set all four verdicts, the evidence and a 200-char license link. Keep the `n < MAX_EMAIL_BYTES` assertion.

**Contingency trim (tested, not required).** Move `{{ ff }}` from the label and value `<td>`s of the 모델 정보 rows onto the `data-model-info` `<table style>`. Measured result: **83,002 B** (saves 7,650 B; `font-family:` occurrences 214 → 124). The cells then inherit the font from their own table, not across a table boundary. No authoritative source confirms that Gmail and Naver keep a table-level inline `font-family` [ASSUMED]. Email on Acid's guidance is to declare the font on every text-holding element, usually the TD ([emailonacid.com](https://www.emailonacid.com/blog/article/email-development/custom-font-stacks-in-outlook/)). If the planner applies it, gate it behind a live Gmail + Naver test send (the 01-06 / 01.2-05 flow). Recommendation: do not trim now. Record the trim as the first lever if Phase 4 web links push past the cap.

Optional footer disclaimer from PITFALLS ("라이선스 정보는 공개 자료 기준이에요. 상업적으로 쓰기 전에 원문을 확인해 주세요."): about 150 B. It must avoid the phrases in `AUTHORSHIP_PHRASES` (no "자동 생성"). Owner choice.

## 9. Schema impact

**No v4 bump needed.** The v3 models cover every field [VERIFIED: schema.py:65-102, :189 `trend_ko: str | None = None  # Phase 2 (ANLY-05)`]:
- `CommercialUse.code_license` / `weights_license` are `LicenseInfo` (`spdx_id`, `name`, `source_url`), which holds both sides separately. Put the HF id or GitHub SPDX id in `spdx_id`, and `license_name` or the GitHub `name` in `name`.
- The gated flag has no Issue field. It is already visible in `model_info.release` (`가중치(승인 필요)`). Record it in `enriched.json` (below), which is not schema-frozen.
- `Hardware` has `param_count`, `est_vram_gb`, `local_run`, `evidence`. `ModelInfo.size` keeps the code string.
- `ClaudeGptUse` has no evidence list. EVID-05 for it uses the Item URLs (§7).
- Claude output models change, and these are not snapshot-guarded: `ItemAnalysisLLM` (+2 fields), new `VerdictNotesLLM`, `TrendLLM`.

**`enriched.json` (EVID-01):** write `archive/{week}/enriched.json` in `run_build` next to `raw.json`/`selected.json`. Per rank: `paper_id`, `model_id`, `linked_models` (ids, gated), `spaces`, `datasets`, `weights_license {license, license_name, license_link}`, `gated`, `safetensors {total, parameters}`, `base_model_tags`, `github_license {status, spdx_id, name, html_url}`, `paper_fetch_ok`, and every evidence URL. Only public HF/GitHub metadata goes in; no Claude text. `archive/` is gitignored until Phase 5 [VERIFIED: .gitignore `archive/`]. `enrich._enrich_one` must return this record alongside the Item, for example as `(Item, dict)`.

Pipeline order today: analyze → enrich → headline [VERIFIED: newsletter/pipeline.py:57-69]. New order: analyze (+claude_gpt) → enrich (+GitHub license, raw record) → `verdicts.apply` (commercial, PoC, hardware, claude_gpt guard, `enforce_evidence`) → notes → trend → headline → `Issue(trend_ko=…)` → write `enriched.json`, `issue.json`, render.

## Common Pitfalls

1. **Fixture trimmed vs live.** `hf_models_w44.json` lacks `cardData.license`/`safetensors.parameters`. Tests would pass on tags while live paths differ. Recapture, and test both the cardData path and the tag fallback.
2. **respx unmocked host.** The new `api.github.com` call fails every e2e/enrich test until `mock_enrich` registers a route. Add a `github_license_w44.json` fixture and a `mock_github_api(router, licenses, fail=)` helper.
3. **Token leakage.** The token goes only in the `Authorization` header, never in the URL. `__main__` sets `logging.basicConfig(level=logging.INFO)` [VERIFIED: newsletter/__main__.py:81], so httpx logs request URLs (repo ids) at INFO. Headers are not logged by default [ASSUMED]. Optionally set `logging.getLogger("httpx").setLevel(logging.WARNING)`, which also closes an existing gap: HF ids are logged today despite the enrich docstring's "never ids".
4. **"가능" for code-only papers misleads.** Use the code-only phrase (§8).
5. **Relative/external `license_link`.** Resolve or replace it with the model page; never render an arbitrary host.
6. **Packed quantization `total`.** Apply the dtype guard (§3).
7. **`논문만` from a failed fetch.** Set it only when the paper API succeeded.
8. **Claude restating verdicts.** Prompt "근거만" plus the polarity check. On failure store `None`; never fail the build.
9. **Trend names outside the Top N.** Allowlist check plus retry, then `None`.
10. **Size regression.** Extend `_worst_case` with the verdict line before changing the template.

## Code Examples

```python
# verdicts.py: VRAM (sketch)
FLOAT_DTYPES = {"F64", "F32", "F16", "BF16", "F8_E4M3", "F8_E5M2"}
def vram(total: int | None, params: dict | None, tags: list[str]) -> tuple[float | None, LocalRun]:
    if not total or any(t.startswith(("base_model:adapter:", "base_model:quantized:")) for t in tags):
        return None, "확인 필요"
    other = sum(v for k, v in (params or {}).items() if k not in FLOAT_DTYPES)
    if other > 0.01 * total:
        return None, "확인 필요"
    gb = round(total * 2 * 1.2 / 1e9, 1)
    return gb, "가능" if gb <= 24 else "제한적" if gb <= 80 else "불가"
```

```python
# enrich.py: GitHub license (sketch; non-fatal, reason codes only)
def github_license(client, owner, repo) -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if tok := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {tok}"
    resp = client.get(f"https://api.github.com/repos/{owner}/{repo}/license",
                      headers=headers, follow_redirects=False)
    if resp.status_code == 404: return {"status": "none"}
    if resp.status_code != 200: return {"status": f"http_{resp.status_code}"}
    d = resp.json(); lic = d.get("license") or {}
    return {"status": "ok", "spdx_id": lic.get("spdx_id"), "name": lic.get("name"),
            "html_url": d.get("html_url") if str(d.get("html_url", "")).startswith("https://github.com/") else None}
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Copyleft (GPL/LGPL/MPL/CC-BY-SA/ND) → `조건부` | §1 | Owner may want `가능` for LGPL/MPL. Table edit only |
| A2 | `deepseek`/`tongyi-qianwen` license_name strings | §1 | Falls to `확인 필요`, which is safe |
| A3 | ×2 bytes ×1.2 overhead, GB = 1e9 | §3 | Labels shift near 10 B / 33 B params |
| A4 | Hosted runner IP sharing makes the token necessary | §1 | Without it, 403 → code side `확인 필요`; still non-fatal |
| A5 | `contents: read` `github.token` can read public-repo license | §1 | Falls back to unauth behaviour |
| A6 | 7 W44 repos' API SPDX ids match the file headers | §1 coverage | Coverage numbers change slightly |
| A7 | Polarity word lists | §5 | False positives drop reasons to `None` (web-only) |
| A8 | Code constant reason for `확인 필요` acceptable under ANLY-04 | §5 | Send those to Claude too |
| A9 | Table-level `font-family` inherits in Gmail/Naver | §8 | Only matters if the contingency trim is used |
| A10 | httpx does not log headers | Pitfall 3 | Token leak; mitigate by silencing httpx INFO |
| A11 | base_model family guard (`meta-llama`, `google/gemma`) | §1 | Over-conservative on a mislabeled fine-tune only |

## Open Questions (RESOLVED)

1. **Trend above or below highlight in Phase 3?** (RESOLVED: D-13, above) D-07 says under the greeting, while the Figma order puts it after highlight. Recommendation: move it above highlight now (D-07 is the newer locked decision).
2. **Show `해당 없음` in the line?** (RESOLVED: D-11, hidden by owner) It is a known verdict, so D-01 implies showing it. It adds about 40 B per card. Recommendation: show it.
3. **Footer license disclaimer?** (RESOLVED: D-12, included) Owner choice, about 150 B.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv + Python | tests, build | ✓ | Python 3.14 via uv | — |
| huggingface.co API | enrich, captures | ✓ | — | non-fatal defaults |
| api.github.com | code license | ✓ (unauth, 60/h) | REST 2022-11-28 | `확인 필요` |
| raw.githubusercontent.com | (existing README images) | ✓ | — | — |
| `GITHUB_TOKEN` in Actions | rate limit | via `${{ github.token }}` | — | unauth |
| node / gsd-tools | planning tooling | ✗ | — | read files directly |

## Validation Architecture

`workflow.nyquist_validation` is `false` in `.planning/config.json`, so no Nyquist map is required. Offline tests to plan, all under `uv run pytest -q` with no network:
- `tests/test_verdicts.py`: the SPDX table (every key → expected label, casefold, `-only` strip, list-valued `cardData.license`, `other` + name lookup + NC keyword), gated upgrade, stricter-of matrix (including side-absent vs side-unknown), PoC table incl. `논문만` only on fetch OK, VRAM boundaries (24.0/24.1/80.0/80.1 GB), dtype and adapter/quantized guards, `license_link` resolution/host allowlist, `enforce_evidence` property test, `직접 사용` guard.
- `tests/test_golden_verdicts.py`: 15 cases from `golden_verdicts.json`.
- `tests/test_enrich.py`: GitHub license route (200, NOASSERTION, 404, 403, 500, transport error → non-fatal), the token header present only when the env var is set, the token never in URL or logs (caplog), `enriched.json` contents.
- `tests/test_notes.py` / `tests/test_trend.py`: FakeAnthropic scripts for the rank mismatch, ungrounded license, polarity, 해요체, URL, name-allowlist and number checks, retry then `None`.
- `tests/test_analyze.py`: new fields, length/해요체/label-in-reason checks.
- `tests/test_render.py`: line omission rules, code-only phrase, link selection and 200-char skip, text part line, the extended `_worst_case` < 92,160 B, trend placement under the greeting.
- `tests/test_workflow_static.py`: `GITHUB_TOKEN: ${{ github.token }}` in the build step, still exactly one `secrets.`.
- `tests/test_e2e.py`: updated call counts (13), W44 end-to-end verdicts as in the §1 coverage table.

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Repo/model id allowlists (`REPO_ID_RE`, `GITHUB_REPO_RE`); evidence URL host allowlist; pydantic `HttpsUrl` |
| V7 Logging | yes | Rank + reason codes only; token never logged; consider httpx at WARNING |
| V8 Data Protection / secrets | yes | `GITHUB_TOKEN` via env, header only, `contents: read` |
| V2/V3/V4/V6 | no | — |

| Threat | STRIDE | Mitigation |
|---|---|---|
| Model card injects a phishing `license_link` | Spoofing | Host allowlist, else the model page |
| Abstract prompt-injects "직접 사용" | Tampering | Enum + artifact guard + `<paper>` data framing |
| Claude invents a license in a reason | Repudiation/trust | Grounding token check |
| Token leak in public logs | Info disclosure | Header only, no URL, no debug logging |

## Sources

### Primary (HIGH)
- Live HF model API probes (14 models) and GitHub license API probes (5 repos), 2026-11-03
- huggingface.co/docs/hub/repositories-licenses: full license id list
- docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api: 60/h unauth, 1,000/h `GITHUB_TOKEN`
- Codebase: `newsletter/schema.py`, `stages/enrich.py`, `analyze.py`, `headline.py`, `render.py`, `pipeline.py`, `templates/email.*.j2`, `tests/conftest.py`, `tests/test_render.py`, `tests/test_workflow_static.py`, `tests/test_schema.py`
- Measured renders: current worst case 84,582 B; prototype with verdict line 90,652 B; trim 83,002 B

### Secondary (MEDIUM)
- `.planning/research/PITFALLS.md` Pitfalls 3 and 16; 01.2-02 / 01.2-04 summaries

### Tertiary (LOW)
- [Email on Acid: custom font stacks in Outlook](https://www.emailonacid.com/blog/article/email-development/custom-font-stacks-in-outlook/): per-TD font declaration advice (inheritance not directly tested)

## Metadata

**Confidence breakdown:**
- Data sources / coverage: HIGH (live probes)
- Verdict tables: MEDIUM (copyleft placement and some license names assumed)
- Size budget: HIGH (measured); trim inheritance: LOW
- Claude call design: MEDIUM (follows the proven headline pattern; polarity lists untested)

**Research date:** 2026-11-03
**Valid until:** 2026-12-03 (HF license list and GitHub API are stable)
