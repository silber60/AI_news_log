# Phase 3: Humanizer, Highlight & Explainer - Context

**Gathered:** 2026-11-03
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase fills the two content slots that the email already renders but leaves empty, and tightens the writing style:

- **이번 주 바로 써볼 만한 것:** 1-3 picks for a Claude Skill or GPTs (HILT-01..03).
- **AI 기술 쉽게 보기:** one technique explained in plain language, avoiding topics covered in earlier issues (EXPL-01/02).
- **Humanizer:** the full rule set ported to Korean, a deterministic lint, and one polish pass (HUMN-01..03).

The email markup is trimmed so these sections fit under 90 KB.

Out of scope: the web version and the reason display (Phase 4), subscribe (Phase 4.1), cron and commit-back for weekly archives (Phase 5). The topic-record commit below is the one exception.

</domain>

<decisions>
## Implementation Decisions

### Highlight (HILT)
- **D-01:** Keep the "이번 주 바로 써볼 만한 것" section in the email. The owner removed it only from the subscribe-page feature list.
- **D-02:** Claude decides which of this week's Top N items fit a Claude Skill or GPTs (owner: "Claude 판단에 맡김"). There is no code filter on the commercial or Claude/GPT verdicts. Code still enforces three things: the picks are 1-3 items from this week's Top N only (HILT-03); the `skill_gpt_fit` label enum is valid; and when nothing fits, the section says "이번 주는 해당 항목 없음".
- **D-03:** For each pick, "왜 좋은지" and "어떻게 만들지" are each one or two lines giving the direction, written in 해요체 (e.g. "요약 규칙을 Skill로 정리해 두면 매번 같은 형식으로 받을 수 있어요"). No step-by-step lists.

### Explainer (EXPL)
- **D-04:** Follow the Figma structure: 오늘의 포인트 (1 line), a subheading, 3-4 body sentences, a "예를 들어" box (1-2 sentences of everyday analogy, 어세스타 style), and the related model's image when one exists (`Explainer.image`, code-filled from that item's image). Use the 해요체 voice with technical terms kept in English. Fill the reserved v2/v3 `Explainer` fields (`topic`, `body_ko`, `related_ranks`, `point_ko`, `example_ko`, `image`).
- **D-05:** Pick one technique from this week's Top N, preferring a topic not in the committed past-topics record. Fall back to the #1 item's core technique.
- **D-06:** Past topics live in a committed repo file, e.g. `data/explainer_topics.json`. It holds topic, issue_id and date only, no personal data. It is appended only on `mode=send` runs (not preview or test). This needs `contents: write` scoped to that commit step only, which pulls a small slice of Phase 5's commit-back forward. Keep the build step's secrets rule intact.

### Humanizer (HUMN)
- **D-07:** Port the full humanizer rules from `~/.claude/skills/humanizer/SKILL.md` to Korean in `prompts/humanizer_ko.md`. Keep the Phase 1.2 해요체 rule. The deterministic lint is a unit-tested banned-pattern list, e.g. "단순히 ~가 아니라", "~를 넘어", 혁신적/획기적/게임 체인저, forced triads, dash connectors, bold labels, closing one-liners.
- **D-08:** When lint finds a pattern, run one schema-constrained polish pass that rewrites only the flagged free-text fields (owner: "한 번 다듬고 발송"). Enums, URLs and code facts stay unchanged. Anything left after that pass logs a warning and does not block the send (HUMN-03).

### Email size
- **D-09:** Trim repeated per-cell `font-family` by setting it on wrapper tables and cells. Research estimated about 7.6 KB saved. Because Gmail/Naver inheritance is unverified, the owner will check one test send in Gmail and Naver (web and mobile) before this ships. Add a worst-case size test with the highlight (3 picks) and the full explainer included.

### Claude's Discretion
- Exact prompts, the lint pattern list contents, the highlight/explainer call design (one call vs. folded into existing calls), the call budget, and the topic-similarity rule for "not covered before".

</decisions>

<canonical_refs>
## Canonical References

- `.planning/ROADMAP.md` §Phase 3; `.planning/REQUIREMENTS.md` HUMN-01..03, HILT-01..03, EXPL-01/02
- `~/.claude/skills/humanizer/SKILL.md` (source rules; outside the repo, read-only)
- `prompts/humanizer_ko.md`, `prompts/*.md`, `newsletter/stages/{analyze,notes,trend,headline,render,pipeline}.py`, `newsletter/schema.py` (v3 Highlight/Explainer models), `templates/email.*.j2`
- `.planning/phases/01.1-newsletter-design-v2/01.1-FIGMA-SPEC.md` (highlight and explainer layout)
- `.planning/phases/02-evidence-practical-verdicts/02-0*-SUMMARY.md` (current call budget, size worst case 91,089 B)
- `.claude/CLAUDE.md`

</canonical_refs>

<deferred>
## Deferred Ideas

- None.

</deferred>

---

*Phase: 03-humanizer-highlight-explainer*
*Context gathered: 2026-11-03*
