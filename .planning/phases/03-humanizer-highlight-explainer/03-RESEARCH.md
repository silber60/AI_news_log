# Phase 3: Humanizer, Highlight & Explainer - Research

**Researched:** 2026-11-03
**Domain:** Korean LLM text quality (lint + polish), two new guarded Claude calls, GitHub Actions write-scoped commit, email byte budget
**Confidence:** HIGH for code and size facts (measured in this repo). MEDIUM for the workflow design. LOW for client font inheritance, which the owner will test.

## Summary

Everything this phase needs already exists in the repo. Phase 3 adds no package. The v3 `Issue` already reserves `highlights`, `explainer` and `Item.skill_gpt`, so the frozen schema does not change. The Claude-side models (`ItemAnalysisLLM` plus three new `*LLM` models) live outside the snapshot and may grow. Every new Claude call should copy the existing headline/trend/notes pattern: `analyze._request`, at most 2 attempts, code checks, retry feedback that carries problem codes only, and a non-fatal fallback.

I measured the font-family consolidation. With `font-family` on every `<table>` and removed from every cell, the Phase 2 worst case drops from 91,089 B to 76,988 B, a saving of 14.1 KB. That is almost twice the 7.6 KB estimate. With the explainer image added, the new worst case is 77,607 B, which leaves 14,553 B under the 92,160 B cap. The visible text is byte-identical.

I prototyped the lint and ran it on every free-text field in the three real issue files on disk. Apart from the expected 하다체 in pre-1.2 runs, it triggers on 0 of 190 fields, and on 23 of 24 crafted AI-tell sentences, with 0 of 20 false positives. So the polish call will rarely fire, and it costs about 0 to 1 call per week.

**Primary recommendation:**
- **Highlight:** add `skill_gpt_fit` and `skill_gpt_reason_ko` to the per-paper analyze call, which costs no extra call. Then make one `highlight` call that picks 1-3 of the items Claude labelled as fitting.
- **Explainer:** make one `explainer` call that receives the list of past topics.
- **Polish:** run one lint-gated `polish` pass over the assembled `Issue`, protected by a full-dump diff guard.
- **Topic record:** write the topic record in a separate `record-topic` job that has `contents: write`, depends on `run`, and runs only on send to main.
- **Fonts:** put the font stack on every `<table>`, not on every `<td>`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
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

### Deferred Ideas (OUT OF SCOPE)
- None.
(Phase boundary also excludes: web version and reason display (Phase 4), subscribe (Phase 4.1), cron and weekly archive commit-back (Phase 5); the topic-record commit is the one exception.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HUMN-01 | Humanizer rules ported to Korean in `prompts/humanizer_ko.md`, included in every analysis system prompt | §1 rule map. Every `*_system_prompt()` already appends `humanizer_ko.md`, and the new highlight/explainer/polish prompts do the same |
| HUMN-02 | Deterministic cleanup (dashes, bold, length caps) + unit-tested banned-pattern lint | §1 lint table with measured recall and false-positive rates; `humanize.cleanup()` + `humanize.lint()` |
| HUMN-03 | One schema-constrained polish pass on free-text fields; leftovers warn, never block | §2 polish design, diff guard, budget |
| HILT-01 | Each item carries `skill_gpt_fit` + short reason | §3: two new `ItemAnalysisLLM` fields map onto the existing `Item.skill_gpt` (`SkillGptFitInfo`) |
| HILT-02 | Top section with 1-3 picks, 왜 좋은지 + 어떻게 만들지 | §3 highlight call; the template already has the slot |
| HILT-03 | Picks only from this week's Top N; "이번 주는 해당 항목 없음" when none | §3 code checks. The section always renders and shows the fallback line when the list is empty |
| EXPL-01 | Weekly explainer in plain Korean tied to Top N items | §4 explainer call; the template needs one new image row |
| EXPL-02 | Topic chosen from Top N, avoiding past topics in a committed record, fallback #1 | §4 similarity rule, §5 `data/explainer_topics.json` + record job |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Code decides license / PoC / GPU verdicts; Claude only explains. Unknown → `확인 필요`. The polish pass must never touch verdict enums or code reasons such as `UNKNOWN_REASON`.
- All Claude-generated text follows the humanizer rules ported to `prompts/humanizer_ko.md`.
- Public repo: never commit the subscriber CSV, never log emails, names or credentials, and never enable `smtplib` debug output. Lint, polish and topic logs carry field paths and codes only, never text.
- Compute weeks in `Asia/Seoul`. The record date must come from the issue's KST week (`week_end + 1 day`), never from runner time.
- Email HTML: tables + inline CSS, system Korean font stack, < 90 KB.
- Commit author: `silber60 <81203897+silber60@users.noreply.github.com>`. This applies to the automated topic commit too (§5).
- Do not change the frozen `Issue` schema outside a planned phase. This phase needs no `Issue` change (§3, §4).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `skill_gpt_fit` label + reason | Claude (analyze call) | Code (enum, reason checks, downgrade) | Needs the abstract, which only the per-paper call sees |
| Highlight picks + why/how | Claude (highlight call) | Code (rank ⊂ candidates, ≤3, tag copied from item, caps, 해요체) | D-02: Claude judges and code guards |
| Explainer text | Claude (explainer call) | Code (caps, ranks, past-topic check, image copy) | D-04/D-05 |
| Explainer image | Code | — | D-04: copied from the related item, never chosen by Claude |
| Lint + cleanup | Code | — | HUMN-02 deterministic |
| Polish rewrite | Claude (polish call) | Code (id whitelist, fact guard, full diff guard) | D-08 |
| Past-topics read | Code (build, read-only) | — | From the checkout |
| Past-topics append + commit | CI `record-topic` job | Code (`record-topic` CLI) | D-06: write token is isolated from the build |
| Font consolidation | Template | Owner test send | D-09 |

## Standard Stack

No new dependency. The phase uses what is already locked [VERIFIED: pyproject.toml]: `anthropic>=2.3,<3` (structured `messages.parse` with `output_format`), `pydantic>=2.14,<3`, `jinja2`, `css-inline>=0.23,<0.24`, `pytest>=9.2`, `ruff>=0.17`. The regexes use the stdlib `re`.

New GitHub Action pin for the record job, if the artifact route is used (§5): `actions/download-artifact` v8.0.2 = `9000827ccba6bdab643e8b6fd33ac0654aef8333` [VERIFIED: api.github.com/repos/actions/download-artifact/git/refs/tags, published 2026-10-07]. The existing `upload-artifact@cf430e0…` is v7.0.2. Upload v7 to download v8 compatibility is [ASSUMED]. Both sit on the v4+ artifact backend, but I did not read the v8 release notes.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | No package is installed in this phase |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
(`gsd-tools` could not run because node is missing. No package needed checking.)

## Architecture Patterns

### System Architecture Diagram

```
workflow_dispatch(mode, week)
  └─ job run (contents: read)
      build: fetch → select → analyze[×N, +skill_gpt_fit] → enrich → verdicts.finalize
             → notes → trend → highlight(1 call or 0) → explainer(1 call; reads data/explainer_topics.json)
             → headline → Issue(...) → humanize.polish_issue (lint → 0/1 polish call → diff guard → cleanup)
             → issue.json / email.html / email.txt → archive/ (artifact issue-<run_id>)
      deliver (test|send) ── failure notice (test|send)
  └─ job record-topic (contents: write)   if: mode==send && ref==main && needs.run.result==success
      checkout(persist-credentials:false) → download artifact issue-<run_id> → uv run python -m newsletter record-topic
      → git commit (silber60 noreply) → push with token in this step's env only (rebase-retry once)
```

### Recommended file layout (new / changed)

```
newsletter/stages/humanize.py    # cleanup(), lint(), collect_fields(), polish_issue()
newsletter/stages/highlight.py   # write_highlights(items, client) -> list[Highlight]
newsletter/stages/explainer.py   # write_explainer(items, past, client) -> Explainer | None
newsletter/topics.py             # load_past(), normalize_key(), ALIASES, record(issue) (stdlib only)
prompts/humanizer_ko.md          # full port (v2), keeps "—" and "단순히" (test_prompt asserts them)
prompts/highlight.md, prompts/explainer.md, prompts/polish.md
data/explainer_topics.json       # {"version": 1, "topics": []} committed in this phase
schema.py                        # + ItemAnalysisLLM fields, HighlightPickLLM/HighlightsLLM, ExplainerLLM, PolishFixLLM/PolishLLM
```

### Pattern: guarded Claude call (copy exactly)
`newsletter/stages/trend.py:122-159` is the template: `analyze._request(client, analyze._with_feedback(block, problems), system=..., output_format=Model)`. It handles four failure cases the same way: `anthropic.APIError` → fallback, `ValueError` → schema retry, `stop_reason in ("refusal","max_tokens")` → retry, and an `isinstance` check on `parsed_output`. Check functions return `list[tuple[code, msg]]` and the messages never quote model text [VERIFIED: newsletter/stages/trend.py:122-159 read this session].

### Anti-Patterns to Avoid
- **Adding lint codes to `analyze.check()`.** A failure that survives the analyze retry is fatal unless the code is in `_NON_FATAL_CODES` (`analyze.py:221`). Lint belongs at the end, in one place.
- **Letting Claude emit `tag`, `image`, ranks it was not offered, or URLs.** Code copies `Highlight.tag` from `items[rank-1].skill_gpt.fit` and `Explainer.image` from the related item.
- **Making the build job `contents: write`.** The Build step receives `GITHUB_TOKEN: ${{ github.token }}` (`newsletter.yml:51`), so a job-level write would hand a write token to the step that processes untrusted paper text.

## 1. Humanizer port (D-07)

### Rule map: SKILL.md → `humanizer_ko.md` (Korean equivalents)
[VERIFIED: ~/.claude/skills/humanizer/SKILL.md v3.1.0 read this session; section numbers are the source's]

| § | Source rule | Korean rule for the prompt (example) | Lint code |
|---|-------------|--------------------------------------|-----------|
| 1 | Not X but Y | "단순히 ~가 아니라", "~뿐만 아니라", "~에 그치지 않고", 두 문장으로 나뉜 "~는 아니에요. ~예요." 금지. 바로 말하기 | `not_x_but_y` (hard), `not_x_plain` (weak) |
| 2 | One-line closers | 앞 문장을 되풀이하는 짧은 마무리("이게 핵심이에요.", "기억해 둘 만해요.") 금지. 마지막 사실에서 끝내기 | `closer` (weak) |
| 3 | Sayings that sound deep | "본질적으로", "결국 핵심은", "진정한 ~", "~의 언어" 금지 | `saying` (weak) |
| 4 | Staged run-up | "자,", "그럼", "결론부터 말하면", "솔직히", "핵심은 ~예요", "살펴볼까요" 금지 | `run_up`, `chatbot` (hard) |
| 5 | Arguing with no one | "오해하지 마세요", "~라고 생각할 수 있지만" 금지 | prompt only |
| 6 | Forced triads | 의미가 셋일 때만 셋. 세 개짜리 나열·세 문장 병렬 피하기 | `triad` (weak) |
| 7 | Repeated openings | 같은 말로 시작하는 문장 연속 금지("이 모델은 … 이 모델은 …") | `same_opening`, `subject_repeat` (weak) |
| 8 | Dashes | — – ` -- ` 금지(코드·URL·모델명 하이픈은 예외) | `dash` (hard, + cleanup fallback) |
| 9 | Stacked qualifiers | "~일 수도 있을 것 같아요", "어쩌면 아마도" 금지 | `hedge_stack` (weak) |
| 10 | Hyphenated pairs | Korean has no equivalent. Keep English model and term hyphens | none |
| 11 | Passive / missing subject | 이중 피동("되어지다", "보여지다") 금지, 능동으로 | `double_passive` (hard) |
| 12 | Overused AI words | "다양한", "효과적으로", "원활한", "극대화", "심층적", "면밀히", "핵심적인" 남용 금지 | `ai_words` (weak) |
| 13 | Inflated significance | "~의 중요성을 보여 줬어요", "새 기준을 세웠어요", "앞으로가 기대돼요", "이정표", "한 획을" 금지 | `significance` (hard) |
| 14 | Vague association | "~와 관련된", "~와 연관된" 대신 관계를 말하기 | prompt only |
| 15 | Shallow -ing riders | "~를 보여 주며", "~를 시사해요", "~를 강조해요" 덧붙이기 금지 | `rider` (weak) |
| 16 | Sales language | 혁신적, 획기적, 게임 체인저, 판도를 바꾸는, 놀라운, 강력한, 압도적, 혁명적, 차원이 다른, 역대급 | `hype` (hard) |
| 17 | Borrowed authority | "전문가들은", "업계에서는", "많은 연구자들이" 금지 | `authority` (hard) |
| 18 | Avoiding is/has | "~의 역할을 해요", "자리매김했어요" 대신 "~예요", "~가 있어요" | `role_verb` (weak) |
| 19 | Bold as decoration | 굵은 글씨, 마크다운, "라벨: 내용" 목록 금지 | `markdown` (hard, + cleanup) |
| 20 | Decorative headings / emoji | Claude 텍스트에 이모지·화살표 금지 (헤드라인 emoji 필드만 예외) | `emoji` (hard) |
| 21 | Curly quotes | 곧은 따옴표만 | `curly_quote` (cleanup only) |
| 22 | Chatbot residue | "도움이 되셨으면", "궁금한 점이 있으면", "물론이죠" 금지 | `chatbot` (hard) |
| 23 | Knowledge-limit disclaimers | "자세한 정보는 공개되지 않았지만 아마…" 금지. 모르면 쓰지 않기 (코드가 `확인 필요`) | prompt only (code reasons collide) |
| 24 | Heading repeated in first sentence | 소제목(`topic`)을 본문 첫 문장에서 되풀이하지 않기 | prompt only |
| 25 | Writing about the document | "이번 뉴스레터에서는", "아래 표는" 금지 (already `AUTHORSHIP_RE`) | prompt only |
| 26 | Wrong reader | Not applicable to a broadcast newsletter | none |
| (1.2) | 해요체 | 모든 문장 "~요"로 끝내기; 명사구 필드는 예외 | `haeyo` (hard) via `analyze.not_haeyo` |

Keep the literal strings `—` and `단순히` in the file. `tests/test_prompt.py` asserts `for word in ("혁신적", "획기적", "게임 체인저", "단순히", "—"): assert word in text` [VERIFIED: tests/test_prompt.py read this session]. Replace the header comment `<!-- humanizer core subset (D-18). Phase 3 replaces this ... -->` and add a version marker.

### Lint list (prototype run this session)

Scoring: one **hard** hit triggers polish. **Weak** hits trigger only when there are 2 or more in the same field, counted per match with `findall`. `haeyo` applies only to sentence fields.

| Code | Strength | Regex (Python `re`, `re.M`) | False-positive risk |
|------|----------|------------------------------|---------|
| `dash` | hard | `[—–]\|\s--\s` | Low. English hyphens ("Vision-Language-Action") do not match |
| `markdown` | hard | `\*\*\|__\|` `` ` `` `\|^#{1,6}\s\|^\s*[-*]\s` | Low |
| `hype` | hard | `혁신적\|획기적\|게임\s?체인저\|판도를\s?바(?:꾸\|꿀\|꿔\|꿨)\|패러다임\s?(?:전환\|변화\|시프트)\|새로운\s?지평\|놀라운\|강력한\|압도적\|혁명적\|차원이\s?다른\|역대급` | Low. A superset of `headline.HYPE_WORDS` |
| `not_x_but_y` | hard | `단순(?:히\|한)\s?[^.?!]{0,30}?(?:이\|가)?\s?아니(?:라\|고\|에요)\|(?:뿐\|뿐만)\s?(?:아니라\|아니고)\|에\s?그치지\s?않(?:고\|아요)` | Low |
| `beyond` | hard | `[을를]\s?넘어(?:서)?(?=[\s,])(?!\s?섰)` | Medium. Facts like "기존 기록을 넘어섰어요" and "100자를 넘어가면" do not match (tested) |
| `significance` | hard | `중요성을\s?(?:보여\|강조\|일깨)\|새(?:로운)?\s?기준을\s?(?:세웠\|제시)\|앞으로(?:가\|의)?\s?(?:더\s?)?기대\|주목할\s?만한\|눈여겨\s?볼\|꼭\s?알아야\s?할\|이정표\|한\s?획을\|시사하는\s?바가\|의미가\s?(?:커요\|크다\|있어요)` | Low |
| `chatbot` | hard | `도움이\s?되(?:셨\|었)으면\|궁금한\s?(?:점\|게)\s?있으\|물론이(?:죠\|에요)\|좋은\s?질문\|알려\s?드릴게요\|살펴볼까요\|알아볼까요\|함께\s?보시죠` | Low |
| `authority` | hard | `전문가들(?:은\|이)\|업계에서는\|많은\s?(?:연구자\|전문가)들\|평가를\s?받고\s?있` | Low |
| `run_up` | hard | `^(?:자,\|그럼\|결론부터\s?말하면\|솔직히\|사실,\|핵심은\|중요한\s?(?:건\|것은))` | Low (anchored) |
| `double_passive` | hard | `되어지\|되어져\|되어졌\|보여지\|보여져` | Low |
| `emoji` | hard | `[\U0001F300-\U0001FAFF☀-➿]` | Low. Do not apply it to `headline_ko` |
| `haeyo` | hard | `analyze.not_haeyo(text)` (reuse) | Low. It is the existing stage rule |
| `curly_quote` | cleanup | `[“”‘’]` → `"`/`'` | n/a |
| `not_x_plain` | weak | `(?:이\|가)\s아니라\s` | **High.** "사람이 아니라 로봇이…" is informative |
| `saying` | weak | `본질적으로\|근본적으로\|결국\s?(?:핵심\|중요한)\|진정한\|그\s?자체` | Medium |
| `role_verb` | weak | `역할을\s?(?:해요\|한다\|합니다\|하는)\|자리매김\|로서\s?기능` | Medium |
| `rider` | weak | `(?:을\|를)\s?보여\s?(?:줘요\|주며\|준다\|주고)\|(?:을\|를)\s?시사(?:해요\|한다\|하며)\|(?:을\|를)\s?강조(?:해요\|한다\|하며)` | Medium |
| `ai_words` | weak | `다양한\|효과적으로\|원활(?:한\|하게)\|극대화\|최적화된\|심층(?:적)?\|면밀(?:히\|한)\|핵심적인` | **High** if hard. Common Korean |
| `triad` | weak | `(?:[^\s,]{1,12},\s){2}(?:그리고\s)?[^\s,]{1,12}` | **High.** All 8 real hits were legitimate lists ("역량, 최적화, 평가 방법") |
| `hedge_stack` | weak | `수도\s?있을\s?(?:것\|수)\|일\s?수도\s?있\|어쩌면\|아마도` | Medium |
| `subject_repeat` | weak | `^(?:이\s?논문은\|본\s?연구는\|이\s?연구는\|이\s?모델은)` | Medium |
| `closer` | weak (code) | ≥3 sentences and last sentence ≤18 chars without a digit | High |
| `same_opening` | weak (code) | ≥3 sentences and ≥3 share their first token | Medium |

(`\|` above is the table escape for `|`.)

**Measured hit rates** (prototype at scratchpad `lint_proto.py`, run 2026-11-03) [VERIFIED: local run]:
- **`~/Downloads/개인/Newslettera/issue-41409445829/2026-W44/issue.json`:** schema v2, the pre-1.2 하다체 prompt, 70 fields. 39 trigger, and all of them only on `haeyo` (expected for that prompt era). **0 of 70 trigger without `haeyo`.** There are 4 `triad` weak hits, all legitimate.
- **`~/Downloads/개인/issue-41390889378/2026-W44/issue.json`:** v1, 40 fields. 30 on `haeyo` only. **0 of 40 without `haeyo`.** 2 legitimate `triad` hits.
- **`tests/fixtures/issue_w44.json`:** v3, 해요체, 80 fields. **0 of 80 trigger.**
- **Crafted set (24 AI-tell positives, 20 negatives including real 해요체 lines):** 23 of 24 positives trigger. The one miss is a lone `closer`, weak by design. **0 of 20 negatives trigger.**
- No 1.2+/Phase 2 live artifact was available locally. The 02-06 run 41589810089 needs a login and `gh` is not installed. So the real-world hit rate on current prompts is unmeasured: [ASSUMED] near 0. Owner action: download the next preview artifact and run the lint test on it.

### Deterministic cleanup (HUMN-02), applied to every Claude free-text field before lint
1. Strip `**`, `__`, backticks and a leading `#`/`- `.
2. Replace curly quotes with straight quotes.
3. Collapse whitespace with `analyze._one_line`.
4. **After** polish only, as a last resort: replace any remaining `\s*[—–]\s*|\s--\s` with `, `, so §8 always holds. This is logged as `cleanup=dash fields=N`.
5. Length caps stay owned by each stage (`trim_summary`).

## 2. Polish pass (D-08, HUMN-03)

**Placement:** once, at the end of the build, after `Issue(...)` is assembled with the highlights, explainer and headline, and before `store.write_json(out / "issue.json", issue)` (`pipeline.py:91`). Use `issue = humanize.polish_issue(issue, client)`. Running it at the end means one place, one diff guard, and coverage of every stage's text. The headline is excluded: it has its own checks and a code fallback.

**Field selection** (path id → kind → limit):

| Path | Kind | Limit / extra guard |
|------|------|---------------------|
| `items.{i}.summary_ko` | sentence | 80 (`SUMMARY_LIMIT`) |
| `items.{i}.summary_lines_ko.{0..2}` | sentence | 70 |
| `items.{i}.use_idea_ko` | sentence | 50 |
| `items.{i}.claude_gpt.reason_ko` | sentence | 60. No label from `_CG_LABELS` |
| `items.{i}.commercial.reason_ko`, `items.{i}.poc.reason_ko` | sentence | 60. **Skip when it equals `notes.UNKNOWN_REASON`**. Re-run `notes._field_errors` (polarity + license grounding) |
| `items.{i}.skill_gpt.reason_ko` (new) | sentence | 60 |
| `trend_ko` | sentence | 300. Re-run `trend.check_trend` |
| `highlights.{j}.why_ko` / `.how_ko` | sentence | caps from §3 |
| `explainer.point_ko` / `.body_ko` / `.example_ko` | sentence | caps from §4 |
| Excluded: `title_ko`, `kind_ko`, `architecture_ko`, `explainer.topic`, `headline_ko`, every enum, URL, number, rank and image | — | Cleanup only (dash/markdown). Names and hyphens are legitimate there |

**Call:** send only the fields whose lint triggered. Input:

```
<fields>
id: items.2.summary_lines_ko.1
kind: 문장
limit: 70
problems: not_x_but_y, hype
text: ...
</fields>
```

`PolishLLM = {fixes: list[PolishFixLLM{id: str, text: str}]}`. The system prompt is `polish.md` + `humanizer_ko.md`, with the same data-fence wording as the other prompts.

**Per-fix guards** (a fix that fails keeps the original text):
- `id` must be one that was requested, and each `id` may appear at most once.
- The text must be non-empty, within the limit, and 해요체 (`analyze.not_haeyo`). It must contain no URL (`headline._URL_RE`), no emoji, and no `AUTHORSHIP_RE` match.
- **Fact guard:**
  - Digit tokens (`trend._NUMBER_RE`) must be a subset of the original's.
  - Latin name tokens (`trend._NAME_RE`, name-like) must be a subset of the original's tokens ∪ `GENERIC_TERMS`.
  - No new `\d+위`.
  - Reason fields re-run their stage checks.
- Hard lint hits must be fewer than in the original, ideally zero. Weak hits must not increase.

**Diff guard (code-level invariant):**
1. Take `before = issue.model_dump(mode="json")`.
2. Apply the accepted fixes by path and rebuild with `Issue.model_validate(...)`. This re-runs `_check_contract`.
3. Flatten both dumps to leaf paths.
4. Assert that every leaf not in the accepted-id set is equal. On any mismatch, discard the whole polish and keep `before`, logging `polish=discarded reason=diff`.

This makes the "enums/URLs/facts unchanged" rule mechanical.

**Retry:** at most 2 attempts. Attempt 2 resends only the ids that failed a guard, with problem codes (never text) through `analyze._with_feedback`. An API error, refusal or schema error keeps the originals and never raises.

**Leftovers:** re-lint after polish and log `humanizer=unfixed fields=<n> codes=<sorted codes>`. Paths are allowed in that log; text is not. Then apply the cleanup dash fallback.

**Call budget** (Phase 2 baseline 13 [VERIFIED: 02-05-SUMMARY "Normal build: **13** calls (10 analyze, 1 notes, 1 trend, 1 headline)"]):

| Stage | Normal | Max |
|-------|--------|-----|
| analyze (N≤10) | 10 | 20 |
| notes | 1 (0 if all 확인 필요) | 2 |
| trend | 1 | 2 |
| highlight | 1 (0 if no candidate) | 2 |
| explainer | 1 | 2 |
| headline | 1 | 2 |
| polish | 0 (lint clean) / 1 | 2 |
| **Total** | **15** (16 with polish) | **32** |

Test updates: `tests/test_e2e.py:138` `== 13` → 15. `tests/test_analyze.py:64` `== 14` → 16, and lines 105/117 `["messages"] * 13` → `* 15`. `conftest.default_response` needs defaults for `HighlightsLLM`, `ExplainerLLM` and `PolishLLM`, and `default_analysis` needs the two new fields. The fake defaults must be lint-clean so the normal path makes 0 polish calls.

## 3. Highlight (D-01..D-03, HILT-01..03)

**Recommendation: fold `skill_gpt_fit` into analyze (A) and add one pick call.**

| Option | Calls | Quality | Risk |
|--------|-------|---------|------|
| **A: two fields in `ItemAnalysisLLM` + 1 pick call** | +1 (0 when no candidate) | Fit judged with the full abstract (best grounding for HILT-01's per-item reason); the pick call compares across items | Analyze is the fatal path. The new codes must join `_NON_FATAL_CODES` and downgrade to `해당 없음` (same as `_CG_DOWNGRADE_CODES`) |
| B: one call decides fit for all N + picks | +1 | Sees only summaries, not abstracts; one failure loses every fit | Non-fatal, but HILT-01 reasons are weaker |

Option A adds about 40 output tokens per analyze call. The system prompt grows by about 400 cached tokens. Option B adds one more large-output call. Both are cheap. A wins on quality, and it is exactly the precedent set by `claude_gpt` in 02-05.

- **`ItemAnalysisLLM` additions:**
  - `skill_gpt_fit: SkillGptFit`
  - `skill_gpt_reason_ko: str`, one 해요체 sentence of 60 characters or fewer that does not repeat the label
- **Mapping to `Item`:** `to_item` sets `skill_gpt=SkillGptFitInfo(fit=..., reason_ko=... or None)`.
- **New check codes:**
  - `sg_reason_len` is trimmed.
  - `sg_reason_empty` and `sg_label_in_reason` downgrade the label to `해당 없음` with no reason.
  - All of them are non-fatal.
- Prompt v6 in `analyze_paper.md` changes "열한 필드" to "열세 필드". `test_prompt` asserts the field count wording (`"열한 필드" in paper`) and must be updated.

**Highlight call** (`highlight.write_highlights(items, client) -> list[Highlight]`):
- **Candidates:** items with `skill_gpt.fit != "해당 없음"`. If there are none, there is no call and the stage returns `[]`.
- **Input:** `<items>` with rank, `title_ko`, `ai_type`, `summary_ko`, `does_ko`, `skill_gpt_fit`, `skill_gpt_reason_ko`, all cleaned with `headline._clean`. No verdicts, per D-02.
- **Output:** `HighlightsLLM{picks: list[HighlightPickLLM{rank:int, why_ko:str, how_ko:str}]}`. Claude may return 0 picks.
- **Code checks:**
  - Each `rank` is in the candidate ranks and unique, and there are at most 3 picks. HILT-03 is already enforced again by `Issue._check_contract` (schema.py:204-207).
  - `why_ko` and `how_ko` are each 1-2 sentences, 해요체, and 70 characters or fewer. I picked 70 because the line holds about 38 characters at 14px over the 532px content width, and two lines minus the label "왜 좋은지: " leaves about 70 [ASSUMED].
  - No step lists: `(?:^|\s)(?:\d+[.)]|[①-⑩]|첫째|둘째)`.
  - No URL, no hype word, no authorship wording.
- **Tag:** code copies `tag` from `items[rank-1].skill_gpt.fit`. That value is always in `Literal["Claude Skill","GPTs","둘 다"]` because candidates exclude `해당 없음`.
- **Failure:** on retry failure, keep the passing picks and drop the failing ones. An API error returns `[]`.
- **Template:** the highlight section **always renders**. When `issue.highlights` is empty, it shows one line, "이번 주는 해당 항목 없음", in both the HTML and text parts. A failed call also shows that line. This is acceptable for D-01/HILT-03 and avoids any schema flag.

**Schema sufficiency** [VERIFIED: newsletter/schema.py:33, 105-107, 163-167, 190 read this session]:
- `SkillGptFit = Literal["Claude Skill", "GPTs", "둘 다", "해당 없음"]`
- `class SkillGptFitInfo(Strict): fit: SkillGptFit = "해당 없음"; reason_ko: str | None = None`
- `class Highlight(Strict): rank: int; tag: Literal["Claude Skill", "GPTs", "둘 다"]; why_ko: str; how_ko: str`
- `highlights: list[Highlight] = []  # Phase 3 (HILT-02/03)`

These fields are sufficient. **No `Issue` change is needed.**

## 4. Explainer (D-04..D-06, EXPL-01/02)

**One call** (`explainer.write_explainer(items, past_topics, client) -> Explainer | None`).
- **Input:**
  - `<items>`: rank, `title_ko`, `title_en`, `ai_type`, `summary_ko`, three summary lines, `kind_ko`, `architecture_ko`
  - `<past_topics>`: newest first, at most 52 strings
  - Both are fenced as data.
- **Output:** `ExplainerLLM{topic:str, point_ko:str, body_ko:str, example_ko:str, related_ranks:list[int]}`.

**Field map** [VERIFIED: newsletter/schema.py:170-176]:
- Fields: `topic: str; body_ko: str; related_ranks: list[int]; point_ko: str | None = None; example_ko: str | None = None; image: ItemImage | None = None`.
- `topic` doubles as the rendered subheading (`email.html.j2:151`).
- Convention: `"<technique name>: <short Korean gloss>"`, for example `Mixture of Experts: 필요한 전문가만 불러 쓰는 구조`. This mirrors the `title_ko` "name before colon" rule. The **topic key** is `topic.split(":",1)[0]`, so no `topic_key` schema field is needed.
- Adding a separate key field would be a one-way `Issue` change. It is not needed, so I do not recommend it.

**Code checks** (caps are [ASSUMED] from the Figma layout. The box holds about 36 characters per line at 15px over 544px):
- `topic`: a noun phrase of 40 characters or fewer, using `analyze.bad_info_prose`.
- `point_ko`: 1 sentence, 40 characters or fewer.
- `body_ko`: 3-4 sentences, 360 characters or fewer.
- `example_ko`: 1-2 sentences, 140 characters or fewer.
- The three prose fields are 해요체.
- `related_ranks`: 1-3 unique ranks in `1..N`.
- No URL, hype word or authorship wording.
- **Names:** name-like tokens containing a digit or written in mixed case with a digit, such as `GPT-5` or `Qwen3`, must come from this week's items via `trend._allowed_names`. Plain technique words ("attention", "Transformer") are allowed. Using the full trend name check would produce false positives on legitimate technique vocabulary.
- **Numbers:** digits in `point_ko`/`body_ko` must appear in the input. `example_ko` is exempt, because an analogy may say "요리사 10명".

**Topic-similarity rule:** use both layers.
1. **Prompt:** Claude gets the past list and is told to avoid it. If every candidate technique this week was covered, it explains rank 1's core technique from a new angle and sets `related_ranks=[1]`. This implements the D-05 fallback.
2. **Code:**
   - Normalize the key: NFKC, casefold, then drop every character that is not alphanumeric or Hangul.
   - Compare it, after alias canonicalization, against the normalized past keys.
   - `ALIASES` in `topics.py` maps each alias set to one canonical key. Seed list [ASSUMED]:
     - {moe, mixtureofexperts}
     - {rag, retrievalaugmentedgeneration}
     - {cot, chainofthought}
     - {lora, lowrankadaptation}
     - {rlhf, reinforcementlearningfromhumanfeedback}
     - {dpo, directpreferenceoptimization}
     - {vla, visionlanguageaction}
     - {vlm, visionlanguagemodel}
     - {diffusion, diffusionmodel}
     - {distillation, knowledgedistillation}
     - {quantization, 양자화}
   - Also match when one normalized key contains the other and the shorter key is at least 4 characters long.
3. **Code action on a repeat:** a repeat is allowed without a retry only when `related_ranks == [1]` (the fallback). Any other repeat triggers a retry with the code `explainer_repeat`. If attempt 2 still repeats, accept it with `log.warning("explainer=repeat")`, because D-05 is a preference.

Asking Claude alone is unverifiable, and string matching alone misses aliases. The hybrid is cheap and testable.

**Image:** code sets `image = next((items[r-1].image for r in related_ranks if items[r-1].image), None)`.
- The template gains one row after `body_ko`: `<img ... width/height from ItemImage, alt="{{ ex.topic }} 관련 그림">`.
- Item images are already at the 576px display width (`enrich.py:72 IMAGE_WIDTH = 576`). That matches the explainer content width of 640 − 2×32.
- `test_worst_case_images_and_phase3_otters` must allow an 11th raw image (10 cards + explainer).

**Failure:** an API error, or a check failure after the retry, returns `None`. `{%- if issue.explainer %}` already skips the section (`email.html.j2:143`, `email.txt.j2:48`). The build never fails.

## 5. Topic record (D-06)

**File** `data/explainer_topics.json` (committed now as `{"version": 1, "topics": []}`):
```json
{"version": 1, "topics": [{"issue_id": "2026-W45", "date": "2026-11-09", "topic": "Mixture of Experts: 필요한 전문가만 불러 쓰는 구조"}]}
```
- The `date` is the send Monday, `issue.week_end + 1 day` in KST, the same as `render.date_line`. It is never runner time.
- The file holds topic, issue_id and date only.
- `topics.load_past()` returns `[]` when the file is missing or invalid, and logs `topics=unreadable`.
- `record(issue)` is idempotent on `issue_id`: when the id exists it is a no-op, so a send re-run does not duplicate. It is a no-op when `issue.explainer is None`. It keeps the list sorted by `issue_id` and writes UTF-8 with `indent=2`.

**Workflow: a separate job is required.** GitHub documents `permissions` only at workflow level and `jobs.<job_id>.permissions`. There is no step-level key. "If you specify the access for any of these permissions, all of those that are not specified are set to `none`" [CITED: docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax]. A job-level write in `run` would give the Build step a write token, because it reads `${{ github.token }}` (`newsletter.yml:50-51`). So add:

```yaml
  record-topic:
    needs: run
    if: ${{ inputs.mode == 'send' && github.ref == 'refs/heads/main' && needs.run.result == 'success' }}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2  # v10.3.3
        with:
          python-version: "3.14"
          enable-cache: true
      - name: Install locked dependencies (record)
        run: uv sync --frozen
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333  # v8.0.2
        with:
          name: issue-${{ github.run_id }}
          path: archive/
      - name: Append explainer topic
        run: uv run python -m newsletter record-topic
      - name: Commit topic record
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          git diff --quiet -- data/explainer_topics.json && exit 0
          git -c user.name=silber60 -c user.email=81203897+silber60@users.noreply.github.com \
            commit -m "chore(data): record explainer topic" -- data/explainer_topics.json
          for i in 1 2; do
            git pull --rebase "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" main \
              && git push "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:main && exit 0
          done
          exit 1
```

Notes on the job:
- The token appears only in the last step's env. No `secrets.` is used anywhere in the job. Run lines carry no `${{ }}`, so `test_no_expression_interpolation_in_run_lines` holds. `github.run_id` is only in `with:`.
- `persist-credentials: false` keeps the token out of `.git/config` while `uv sync` and our code run.
- Token-in-URL push is a common pattern [ASSUMED]. GitHub masks `github.token` in logs [ASSUMED].
- **Identity:** use silber60 noreply. The CLAUDE.md hard rule covers repo commits. The alternative `github-actions[bot]` gives clearer provenance but conflicts with that rule. Flag this for the owner only if they prefer the bot.
- **Concurrency:** the workflow-level `group: newsletter, cancel-in-progress: false` serializes whole runs, including this job. Only an owner push during a run can race, and the rebase-retry loop covers it. A conflict is possible only if the owner edited the same file.
- **Failure handling:** the send has already happened. The red `record-topic` job is the signal. It does not resend, and it adds no SMTP secrets, so the delivery-secret test stays intact. The cost of a missed record is a possible repeat topic next week. To recover manually, re-run only the failed job, which is idempotent.
- **No CI loop:** "events triggered by the `GITHUB_TOKEN` will not create a new workflow run" [CITED: docs.github.com/en/actions/concepts/security/github_token]. The data commit therefore does not trigger `ci.yml`.
- **60-day benefit:**
  - Docs: "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." The page does not define activity [CITED: docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows].
  - Keepalive actions make dummy commits for exactly this purpose, which suggests that commits count. Whether a `GITHUB_TOKEN`-pushed commit counts is **[ASSUMED]**.
  - Treat it as a probable side benefit for Phase 5, not a guarantee.

**`test_workflow_static` changes** [VERIFIED: tests/test_workflow_static.py:22-32, 109-114 read this session]:
- `_split` treats everything before the first `      - ` as the header and every later line as part of a step block. The second job's header (`permissions: contents: write`) would land inside the "Failure notice" block. Make `_split` job-aware: split on `^  [\w-]+:$` under `jobs:` first.
- `test_permissions_read_only` currently asserts `"contents: write" not in text`. Replace it with these checks:
  - The workflow level has `contents: read`.
  - Exactly one `contents: write` appears, inside the `record-topic` job.
  - That job has no `secrets.`.
  - Its `if` contains `inputs.mode == 'send'` and `refs/heads/main`.
  - `github.token` appears only in the Build step and the "Commit topic record" step.
- `test_build_step_gets_job_token_not_a_secret` asserts `holders == [build]` for `GITHUB_TOKEN`. That still holds because the record step uses `GH_TOKEN`. Extend it so the token holders are exactly {Build, Commit topic record}.
- `test_ci_runs_lint_and_tests_without_secrets`: `ci.yml` is unaffected.
- `_named(blocks, "Install")` collisions: give the second install step a distinct name.

## 6. Size (D-09)

**Implemented and measured in the scratchpad** (template copies; the repo is untouched) [VERIFIED: local render with `render._INLINER`, same contexts as tests]:

| Variant | W44 | full | worst (Phase 2) | headroom (worst) | `font-family` count |
|---------|-----|------|-----------------|------------------|----|
| Current template (per-cell) | 42,534 | 47,765 | 91,089 | 1,071 | 215 |
| A: only `<body>` + 640 table | 31,824 | 35,950 | 72,984 | 19,176 | 2 |
| **B: on every `<table>`, none on cells** | 34,433 | 39,582 | **76,988** | 15,172 | 46 |
| C: 640 table + each section `<td>` + each card table | 33,434 | 37,815 | 74,849 | 17,311 | 23 |
| **B + explainer image (new Phase 3 worst)** | — | — | **77,607** | **14,553** | — |

The stripped visible text is identical between the current template and B. Each occurrence costs 84 B, and 215 occurrences add up to about 18 KB.

**Recommend B.** Every nested table re-declares the stack, so inheritance only has to cross table → td/span. That is the most robust crossing. The CSS quirks-mode table reset affects font-size, weight and style; whether it also resets family is [ASSUMED]. B also does not depend on Gmail keeping `<body>` styles, and Gmail drops `<body>` [ASSUMED]. A is fragile. C relies on table → nested table inheritance.

Implementation:
- Add `style="{{ ff }} ..."` to every `<table role="presentation">`, including the `title_row`, `box_cell`, `card`, model-info and highlight-pick tables.
- Remove `{{ ff }}` from every `<td>` and `<span>`.
- Bump `template-version: 7`.

`test_every_text_cell_has_korean_font_stack` (`test_render.py:329-335`) must change: the font stack must appear on the cell **or its nearest ancestor `<table>`**. The `_cells` parser needs a table stack. Add one assertion that `font-family` appears 60 times or fewer, so per-cell creep is caught.

**Client inheritance (unverified):**
- Secondary sources still advise inlining on each `td`, and they report Gmail applying its own cell-level styles [web search, LOW].
- I found no caniemail or official data for Gmail or Naver Mail font inheritance from `table` [LOW, no observation].
- The real risk is a client stylesheet rule targeting `td`, which beats inheritance but not inline styles.
- Fallback if the test send fails: revert to per-cell and shorten the stack. Removing the spaces after commas saves about 645 B. Dropping `'IBM Plex Sans KR'` saves about 4.3 KB but loses Apple Mail's web font. The planner should keep the per-cell variant one revert away.

**New worst-case test:** `_worst_case` already includes 3 highlights (`why_ko="왜"*120, how_ko="어"*160`) and a full explainer (`body_ko="본"*800` and so on) [VERIFIED: tests/test_render.py:803-816]. Those are larger than the new caps, so they stay conservative. Add these to it:
- `explainer.image` (a 300-character raw URL, 576×260)
- 3 highlight picks
- the always-on highlight section
- a separate empty-highlights variant that asserts "이번 주는 해당 항목 없음"

Assert `n < MAX_EMAIL_BYTES` and print the headroom. Expect about 77.6 KB.

**Owner test-send checklist** (`mode=test` after B lands, before merge):
1. **Gmail web (Chrome):**
   - The body text is a Korean sans-serif, not serif/Times, in every section: header, greeting, trend, highlight pills and text, card titles, 모델 정보 rows, the verdict line, explainer boxes, the closing line and the footer.
   - "Show original" says the message is not clipped ("[Message clipped]" absent).
2. **Gmail Android/iOS app:** same font check. The highlight pills keep their padding, the explainer image is 576 wide or scales to the screen, and nothing overflows horizontally.
3. **Naver Mail web (PC):**
   - The font is not 굴림/바탕 serif. Naver CSS must not override the cell font.
   - Images load from `silber60.github.io`, `raw.githubusercontent.com` and `arxiv.org`.
4. **Naver Mail app (iOS/Android):** same checks, plus line breaks in why/how (2 lines max) and in 오늘의 포인트 (1 line).
5. **Images blocked (Gmail "ask before displaying"):** every section title and text is readable, and the alt text shows.
6. **Text part:** in Gmail "Show original", the plain-text part has the highlight block (or "이번 주는 해당 항목 없음") and the explainer block.
7. **Record:** note the client, version and pass/fail per item. Any serif fallback means reverting to per-cell for the affected cells.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured Claude output | JSON parsing of text | `analyze._request(..., output_format=Model)` | The fallback beta, schema retry and logging are already handled |
| 해요체 check | new regex | `analyze.not_haeyo`, `analyze.bad_info_prose` | Already tuned for `…` trims and noun phrases |
| Name/number grounding | new tokenizer | `trend._NAME_RE`, `_NUMBER_RE`, `_allowed_names`, `GENERIC_TERMS` | Tested |
| Reason polarity/licensing | new rules | `notes._field_errors` | Polish must re-run it on reason fields |
| CSS inlining | manual | `css_inline` (existing `_INLINER`) | — |
| YAML parsing in tests | PyYAML | line/step block parsing (extend `_split`) | The test is dependency-free by design |

## Common Pitfalls

1. **Analyze becoming fatal on the new fields.** Put the new codes in `_NON_FATAL_CODES` with a downgrade. Test: a bad `skill_gpt_reason_ko` twice gives `해당 없음` and the build passes.
2. **Polish changing facts.** The diff guard plus the fact guard catch it. Test: a fake polish that changes a digit, a name, a URL field or an id it was not asked about is rejected, and the issue dump outside the fixed paths is unchanged.
3. **Polish rewriting `UNKNOWN_REASON` or code phrases.** Exclude it by value. Test this case.
4. **Logs leaking text.** Every new log line carries paths and codes only. Extend `test_redaction` to the polish, highlight and explainer logs.
5. **Write token reaching the build.** Use the separate job (§5). The static test asserts it.
6. **Record on a non-main dispatch or on preview/test.** Guard the job with `if:`. Code should also refuse when the issue file is missing, and exit non-zero.
7. **Indirect prompt injection.** Paper text flows into analyze output and then into the highlight/explainer/polish inputs. Fence it with `<items>`/`<fields>` and the "data only" wording. Guards bound the output.
8. **Highlight section hidden by the current `{%- if issue.highlights %}`.** It must always render now. Update `test_w44_sections_in_figma_order_without_phase3_slots`, the `_otters` W44 set (add `otter-tool.png`) and `test_email_reads_with_images_blocked` titles.
9. **Fake defaults tripping lint.** If `DEFAULT_TREND` or a default analysis hits lint, every e2e count changes. Keep the defaults lint-clean and add a test asserting that.

## Code Examples

The existing guarded-call skeleton to copy is in `newsletter/stages/trend.py:122-159` (`write_trend`).

Diff guard sketch (all names are new; this is a design, not existing code):
```python
def _leaves(d, prefix=""):
    if isinstance(d, dict):
        for k, v in d.items(): yield from _leaves(v, f"{prefix}{k}.")
    elif isinstance(d, list):
        for i, v in enumerate(d): yield from _leaves(v, f"{prefix}{i}.")
    else:
        yield prefix.rstrip("."), d

def _unchanged_outside(before: dict, after: dict, allowed: set[str]) -> bool:
    a, b = dict(_leaves(before)), dict(_leaves(after))
    return a.keys() == b.keys() and all(a[k] == b[k] for k in a if k not in allowed)
```

## State of the Art

| Old | Current (this phase) | Impact |
|-----|----------------------|--------|
| `humanizer_ko.md` core subset (D-18) | Full 26-rule port + lint + polish | All Claude text is covered |
| Per-cell font stack (215×84 B) | Per-table stack (46×) | −14.1 KB worst case |
| `contents: read` only | + one write-scoped job | Partial pull-forward of Phase 5 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The real lint hit rate on current (1.2+/Phase 2) prompts is near 0 | §1 | More polish calls (≤2/week max); no correctness risk |
| A2 | Highlight why/how cap is 70; explainer caps are 40/360/140/40 | §3, §4 | Wrapping looks off; tune after preview |
| A3 | ALIASES seed list | §4 | A repeat topic slips through (soft preference) |
| A4 | download-artifact v8 reads upload-artifact v7 artifacts | §5 | Record job fails, which is visible. Fallback: pin download-artifact v7 or pass the topic via job outputs + env |
| A5 | The token-in-URL push works and `github.token` is masked | §5 | Push fails or the token shows in a log. Use the checkout `extraheader` pattern instead |
| A6 | A GITHUB_TOKEN-pushed commit counts as 60-day activity | §5 | No keepalive benefit; Phase 5 must handle it |
| A7 | Gmail and Naver (web+app) inherit `font-family` from `<table>` to `<td>` | §6 | Serif fallback; revert to per-cell (the owner checklist catches it) |
| A8 | The quirks-mode table reset does not include font-family, and Gmail drops `<body>` styles | §6 | Only relevant to variants A/C; B does not depend on it |
| A9 | A failed highlight call showing "이번 주는 해당 항목 없음" is acceptable | §3 | Owner may prefer hiding the section. Doing that needs a flag, which means a schema change |

## Open Questions (RESOLVED)

1. **Commit identity for the bot commit.** (RESOLVED: D-15, silber60 noreply) The recommendation is silber60 noreply, per CLAUDE.md. The owner may prefer `github-actions[bot]`. This is a one-line change.
2. **Is main branch-protected?** (RESOLVED: owner confirms at the 03-03 T2 and 03-07 T3 checkpoints) If it requires PRs, the push fails. Check the repo settings before the first send. I found no observation.
3. **Current-prompt lint rate.** (RESOLVED: measured in 03-07 T2 on the live preview) Run the lint test on the next preview artifact (A1).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv + Python 3.14 | tests, build | ✓ | uv 0.13.6 | — |
| pytest suite | validation | ✓ | 850 passed (baseline, 2026-11-03) | — |
| node / gsd-tools | research tooling | ✗ | — | read files directly (done) |
| gh CLI | artifact download | ✗ | — | owner downloads in the browser |
| GitHub runner python/uv | record job | ✓ (setup-uv pinned) | — | — |

## Validation Architecture

(`workflow.nyquist_validation` is `false` in `.planning/config.json`, so this is a short offline test map.)

| Area | Test | Type |
|------|------|------|
| Lint positives | one parametrized case per hard code, plus weak pairs, using the crafted set in §1 | unit `tests/test_humanize.py` |
| Lint negatives | 20+ real 해요체 lines from the fixture plus legitimate lists, `기존 기록을 넘어섰어요`, `사람이 아니라 로봇이…`, model names with hyphens | unit |
| Fixture clean | every field of `issue_w44.json` and all conftest defaults: `triggers == False` | unit |
| Cleanup | bold, curly quotes, dash fallback; idempotent | unit |
| Polish diff guard | a fake polish altering a non-requested id, a digit, a name or an enum is rejected; a valid fix is applied; the dump outside the paths is equal; `UNKNOWN_REASON` is never sent | unit with FakeAnthropic |
| Polish budget | clean issue → 0 calls; dirty → 1; failing guard → 2, original kept, warning logged with codes only | unit |
| Highlight constraints | rank outside candidates/duplicate/4 picks rejected; tag copied from fit; no candidates → 0 calls + fallback line; step-list regex; 해요체; caps | unit + render |
| Analyze new fields | bad `skill_gpt_reason_ko` twice → `해당 없음`, the build continues | unit |
| Explainer | past topic (alias) → retry; `related_ranks=[1]` repeat accepted; image copied from the first related item with an image; None on API error → section absent | unit + render |
| Topic record | append on a fresh file; idempotent on issue_id; no-op when explainer is None; date = week_end+1; `load_past` on missing/invalid → [] | unit `tests/test_topics.py` |
| CLI | `record-topic` reads archive/current.json and writes data/… (tmp path env) | unit `test_cli` |
| Workflow static | job-aware `_split`; one `contents: write` only in record-topic; `if` has send + main; no `secrets.` in that job; the token only in Build + Commit step; Build `secrets.` count still 1; no `${{` in run lines; download-artifact SHA-pinned | static |
| Size | new worst (3 picks + full explainer + image + all verdicts) < 92,160, printed headroom (~77.6 KB expected); font-on-ancestor test; `font-family` count ≤ 60 | render |
| Call counts | e2e normal = 15 | e2e |

Commands: `uv run pytest -q` (850 tests in about 6 s today) and `uv run ruff check`.

## Security Domain

| ASVS | Applies | Control |
|------|---------|---------|
| V4 Access Control | yes | Job-scoped `contents: write`; the token is exposed only in the commit step; `if:` guards send + main |
| V5 Input Validation | yes | Pydantic `extra="forbid"` LLM models; code guards on every field; data fences against injection |
| V7 Logging | yes | Logs carry paths and codes only (DLVR-06); extend the redaction tests |
| V6 Crypto | no | — |

| Threat | STRIDE | Mitigation |
|--------|--------|------------|
| Prompt injection via abstracts reaching polish/highlight | Tampering | Fences + id whitelist + fact and diff guards |
| Write token abused by dependency code | Elevation | `persist-credentials: false`; the token only in the last step's env |
| Topic record leaking PII | Info disclosure | The file holds topic/issue_id/date only; the build never writes it |

## Sources

### Primary (HIGH)
Repo files read this session:
- `newsletter/schema.py`, `newsletter/pipeline.py`
- `newsletter/stages/{analyze,notes,trend,headline,render}.py`
- `templates/email.{html,txt}.j2`
- `.github/workflows/newsletter.yml`
- `tests/{conftest,test_workflow_static,test_render,test_prompt,test_schema}.py`
- Phase 2 summaries
- `01.1-FIGMA-SPEC.md` lines 11-30

Other primary sources:
- `~/.claude/skills/humanizer/SKILL.md` v3.1.0
- Local measurements: lint prototype, template variants, pytest baseline
- api.github.com tags for actions/download-artifact

### Secondary (MEDIUM)
- [GitHub workflow syntax: permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GITHUB_TOKEN concept](https://docs.github.com/en/actions/concepts/security/github_token)
- [Disable and enable workflows (60-day rule)](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
- [Controlling GITHUB_TOKEN permissions](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token)

### Tertiary (LOW)
- [keepalive-workflow](https://github.com/MikasaEureka/keepalive-workflow) (dummy-commit approach)
- [gautamkrishnar on DEV](https://dev.to/gautamkrishnar/how-to-prevent-github-from-suspending-your-cronjob-based-triggers-knf)
- [Gmail font styling (SO mirror)](https://kiwix.lema.org/stackoverflow.com_en_all_2023-11/questions/10923263/font-color-in-html-email-gmail)
- [maillinter compatibility](https://maillinter.pages.dev/docs/compatibility)

## Metadata

**Confidence breakdown:**
- Stack and code integration: HIGH. Read and measured in the repo.
- Lint: MEDIUM. Measured, but no current-prompt real sample.
- Workflow: MEDIUM. Docs cited; the push and token masking are assumed.
- Client font inheritance: LOW. The owner test is required.

**Research date:** 2026-11-03
**Valid until:** 2026-12-03 (actions pins and client behavior can move)
