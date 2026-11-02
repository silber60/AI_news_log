# Phase 1: End-to-End Skeleton - Context

**Gathered:** 2026-11-02
**Status:** Ready for planning

<domain>
## Phase Boundary

One manual `workflow_dispatch` run resolves last week (KST), fetches HF Papers, picks the Top 10, runs a minimal Claude analysis into the frozen `Issue` schema, renders a plain table email, and either uploads a preview artifact (`mode=preview`), mails `TEST_RECIPIENT` (`mode=test`), or mails `SUBSCRIBERS_CSV` (`mode=send`). No secrets or PII leak into public logs/artifacts. Requirements: COLL-01..04, ANLY-01, ANLY-03, ANLY-06, DSGN-03, DSGN-04, DLVR-01..03, DLVR-06, AUTO-02.

Not in this phase: evidence verdicts (Phase 2), humanizer/highlight/explainer content (Phase 3), Figma design + web archive (Phase 4), cron/ledger/run report (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### Mail subject & sender
- **D-01:** Subject = brand + #1 paper: `[AI 주간 모델 브리프] 이번 주 1위: <1위 한글 제목> 외 {N-1}건`. Keep it short enough for mobile; truncate the title part in code if long (Claude decides the cap).
- **D-02:** Sender display name `AI 주간 모델 브리프` via `formataddr`; address is the owner's Gmail (`SMTP_USER` secret).
- **D-03:** `mode=test` prefixes the subject with `[TEST] `. `mode=send` has no prefix.

### Item card content
- **D-04:** Title line = Korean gloss, but model names and AI terms stay in English (e.g. "Qwen3-VL: long-context 멀티모달 추론 개선"). English original title shown below in smaller text.
- **D-05:** Same language rule for all generated body text (한줄 요약, 활용 아이디어, later sections): model names / AI terms (fine-tuning, RAG, diffusion, MoE ...) in English, everything else Korean. Put this rule in the analysis system prompt.
- **D-06:** Links per item: HF Papers page and arXiv (always); GitHub code and project page only when present in HF data. No empty link placeholders.
- **D-07:** 활용 아이디어 (max 2): plain "where it could be used" statements, not dev- or business-tuned. Not creative: ground them in what the paper abstract / project page / HF page says. If the source gives nothing usable, output fewer (0 allowed) rather than invent.
- **D-08:** Show major affiliation only (e.g. Google DeepMind, Meta) when available in HF data; omit otherwise. No author list.

### Top 10 selection
User did not answer these explicitly; recommended defaults applied and stated to the user (open to override):
- **D-09:** Week = papers whose `submittedOnDailyAt` falls in last Mon 00:00 – Sun 23:59 KST (weekend submissions included). `week=` primary + `date=` loop fallback per research.
- **D-10:** Sort by upvotes desc; tie-break by comment count desc, then earlier submission. Deterministic. (Verify the comment-count field name in the HF payload.)
- **D-11:** Fewer than 10 papers → send what exists (Top N, subject count follows N). Zero papers → fail per COLL-04.
- **D-12:** No minimum-upvote threshold.

### Failure & preview behavior
- **D-13:** On failure in `mode=test` / `mode=send`, mail a short failure notice (stage + error class, no PII) to `TEST_RECIPIENT`, then fail the job. Nothing is sent to subscribers. In `mode=preview` the job only fails (preview must not read SMTP secrets, per success criterion 1). This pulls a minimal slice of AUTO-04 forward; the full weekly run report stays in Phase 5.
- **D-14:** Preview artifact = de-personalized HTML (greeting "구독자님") + plain-text body + `Issue` JSON.
- **D-15:** Any item still invalid after one Claude retry fails the whole run (no partial Top 9 send), matching ANLY-06.

### Issue schema (frozen in this phase)
- **D-16:** Reserve an optional `explainer` block in `Issue` for the weekly 기술 해설 코너 (Phase 3): topic, plain-language explanation, related item rank(s). Empty in Phase 1; renderer skips it when empty. — **Reversibility:** costly — `Issue` is the frozen contract all later phases fill; adding fields later means a schema change outside a planned phase.
- **D-17:** Item schema needs fields for D-04/D-06/D-08: `title_ko`, `title_en`, `affiliation | None`, `github_url | None`, `project_url | None`, plus existing HF/arXiv URLs.

### Decisions after research (2026-11-02)
- **D-18:** Phase 1 ships a short core subset of humanizer rules in `prompts/humanizer_ko.md`, included in the analysis system prompt. Lint and the polish pass stay in Phase 3.
- **D-19:** If 한줄 요약 still exceeds ~80 chars after the one retry and length is the only error, trim in code at a sentence/phrase boundary and send. Any other validation error still fails the run (D-15).
- **D-20:** Phase 1 keeps `archive/<YYYY-Www>/` on the runner and in the uploaded artifact only. No commit-back (`contents: write`) until Phase 5.

### Claude's Discretion
- Subject title truncation length; exact table layout and font sizes for the plain Phase 1 email (final design comes in Phase 4).
- Failure-notice wording and format.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope
- `.planning/PROJECT.md` — goals, constraints (public repo, KST, Gmail SMTP), key decisions
- `.planning/REQUIREMENTS.md` — COLL/ANLY/DSGN/DLVR/AUTO IDs mapped to Phase 1
- `.planning/ROADMAP.md` §Phase 1 — goal and 5 success criteria
- `.planning/STATE.md` — blockers (secrets, `messages.parse` smoke test, HF weekend coverage)

### Research
- `.planning/research/SUMMARY.md` — stack, HF endpoints, schema-first approach
- `.planning/research/STACK.md` — versions, `messages.parse` API notes (no temperature/prefill, refusal check), HF probe results
- `.planning/research/ARCHITECTURE.md` — pipeline stages and archive layout
- `.planning/research/PITFALLS.md` — secrets/PII leakage, KST week math, email rendering
- `.planning/research/FEATURES.md` — item fields and email sections

### Project rules
- `.claude/CLAUDE.md` — hard rules (code owns verdicts, humanizer, no PII in logs, KST, <90 KB email, commit author)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None. Repo holds only `.planning/` and `.claude/`; this phase creates the codebase.

### Established Patterns
- None yet. Phase 1 sets them (Python 3.14 + uv, Pydantic models, Jinja2 templates, stage outputs under `archive/<YYYY-Www>/`).

### Integration Points
- GitHub Actions secrets: `ANTHROPIC_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD` (Gmail app password), `SUBSCRIBERS_CSV`, `TEST_RECIPIENT`.
- Local Mac has no Node.js; everything must run on Actions (Python runtime is fine).

</code_context>

<specifics>
## Specific Ideas

- Subject example: `[AI 주간 모델 브리프] 이번 주 1위: Qwen3-VL long-context 멀티모달 추론 개선 외 9건`
- Test subject example: `[TEST] [AI 주간 모델 브리프] ...`
- User wants a weekly easy-explainer corner like "어세스타 성장레터" (see Deferred).

</specifics>

<deferred>
## Deferred Ideas

- **Weekly 기술 해설 코너** — each issue explains one AI technique in plain language, like 어세스타 성장레터. Topic choice: prefer a technique from this week's Top 10 not covered in earlier issues; fall back to the #1 paper's core technique. Needs a record of past explainer topics. User chose to fold this into **Phase 3** (with humanizer/highlight); added to ROADMAP Phase 3 as EXPL-01, EXPL-02. Schema slot reserved now (D-16).

</deferred>

---

*Phase: 01-end-to-end-skeleton*
*Context gathered: 2026-11-02*
