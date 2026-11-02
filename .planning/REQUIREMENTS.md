# Requirements: AI 주간 모델 뉴스레터 (Weekly AI Model Brief)

**Defined:** 2026-11-02
**Core Value:** 매주 월요일 아침, 이번 주 꼭 알아야 할 AI 모델이 "실무에 쓸 수 있는가" 기준으로 정리된 메일이 사람 손 없이 구독자 메일함에 도착한다.

## v1 Requirements

### Collection (COLL)

- [ ] **COLL-01**: Pipeline resolves the target issue as the previous ISO week in Asia/Seoul time, regardless of runner clock (UTC), and can be overridden with `--week YYYY-Www`
- [ ] **COLL-02**: Pipeline fetches all papers for the target week from HF `daily_papers` (paginated, `week=` primary with `date=` loop fallback, weekend days covered) and dedupes by paper id
- [ ] **COLL-03**: Pipeline selects the Top 10 papers by upvotes and snapshots raw and selected JSON to `archive/<YYYY-Www>/`
- [ ] **COLL-04**: Pipeline stops without sending (job fails) when the fetch returns no papers or HF is unreachable after retries

### Evidence & Verdicts (EVID)

- [ ] **EVID-01**: For each selected paper, pipeline collects linked HF models/Spaces/datasets, model license tags, gated flag, parameter count, and GitHub repo license, saved as `enriched.json` with evidence URLs
- [ ] **EVID-02**: Reader sees a 상업적 사용 verdict (`가능 / 조건부 / 불가 / 확인 필요`) decided by a code-owned SPDX lookup table, with code and weights licenses shown separately
- [ ] **EVID-03**: Reader sees a PoC verdict (`바로 가능 / 코드만 / 논문만 / 확인 필요`) decided by code from weights/code/demo availability
- [ ] **EVID-04**: Reader sees 실행 난이도·필요 GPU (model size, estimated VRAM, local-run feasibility) computed from parameter count, or `확인 필요` when unknown
- [ ] **EVID-05**: Any positive verdict without an evidence URL is downgraded to `확인 필요`; verdict rules pass a golden-set test of ~10 papers with known licenses

### Analysis (ANLY)

- [ ] **ANLY-01**: Reader sees AI 종류 for each item from a closed enum (LLM, 비전, 멀티모달, 음성, 에이전트, 이미지/비디오 생성, 기타)
- [ ] **ANLY-02**: Reader sees Claude/GPT 사용 가능 여부 (`직접 사용 / 기법 적용 가능 / 해당 없음 / 확인 필요`) with a one-sentence reason
- [ ] **ANLY-03**: Reader sees a Korean title gloss, 한줄 요약 (≤ ~80 chars, enforced in code), and up to 2 활용 아이디어 per item
- [ ] **ANLY-04**: Reader sees the verdict reasons for 상업적 사용/PoC written by Claude from code-supplied evidence (Claude never decides the verdict itself)
- [ ] **ANLY-05**: Reader sees a 이번 주 트렌드 총평 (2–3 sentences) that only references this week's 10 items
- [ ] **ANLY-06**: Claude output is produced via `messages.parse` into the frozen Pydantic `Issue` schema; invalid output is retried once, and a still-invalid issue fails the run without sending

### Humanizer (HUMN)

- [ ] **HUMN-01**: All Claude-generated text follows humanizer rules ported to Korean in `prompts/humanizer_ko.md` (from `~/.claude/skills/humanizer/SKILL.md`), included in every analysis system prompt
- [ ] **HUMN-02**: Generated text passes deterministic cleanup (dashes, bold markers, length caps) and a banned-pattern lint (e.g. "단순히 ~가 아니라", "~를 넘어", 혁신적/획기적/게임 체인저, forced triads, closing one-liners), with unit-tested pattern list
- [ ] **HUMN-03**: When lint finds AI tells, one schema-constrained polish pass rewrites only free-text fields; remaining style issues log a warning and do not block sending

### Highlight (HILT)

- [ ] **HILT-01**: Each item carries `skill_gpt_fit` (`Claude Skill / GPTs / 둘 다 / 해당 없음`) with a short reason
- [ ] **HILT-02**: Reader sees a top "이번 주 바로 써볼 만한 것" section above the Top 10 with 1–3 items good for building a Claude Skill or GPTs, each with 왜 좋은지 + 어떻게 만들지 (1–2 lines)
- [ ] **HILT-03**: Highlights only reference papers in this week's Top 10; when none qualify the section shows "이번 주는 해당 항목 없음" instead of forcing a pick

### Design & Template (DSGN)

- [ ] **DSGN-01**: Figma file `qyJcGii2MLHTbi4W9mPZkx` contains a new 640px web/email newsletter frame derived from the existing mobile design's fonts, colors, and component styles
- [ ] **DSGN-02**: Design sections in order: header + week range, personalized greeting, 이번 주 바로 써볼 만한 것, 트렌드 총평, Top 10 cards (rank, upvotes, badges, summary, links), footer
- [ ] **DSGN-03**: Email HTML is a hand-written Jinja2 table layout with all CSS inlined (no `<head>` style dependence), system Korean font fallback stack on every element, badges as colored text cells (no text images)
- [ ] **DSGN-04**: Rendered HTML is under 90 KB (asserted at render time) and a plain-text alternative is generated from the same data
- [ ] **DSGN-05**: Email renders correctly in Naver Mail and Gmail (web + mobile app, light + dark) — verified by real test sends

### Delivery (DLVR)

- [ ] **DLVR-01**: Pipeline reads subscribers (email, name) from the `SUBSCRIBERS_CSV` GitHub Secret (UTF-8-BOM / CP949 safe); only `subscribers.example.csv` is committed; initial list is subscriber@example.com / 홍길동
- [ ] **DLVR-02**: Each subscriber receives a personalized greeting ("홍길동님", fallback "구독자님") with the name HTML-escaped and CR/LF stripped
- [ ] **DLVR-03**: Mail is sent via Gmail SMTP (`SMTP_SSL` 465, personal Gmail with app password from secrets) as one multipart `EmailMessage` per recipient with correct Korean subject encoding
- [ ] **DLVR-04**: Footer shows sender info and an unsubscribe line, and messages carry a `List-Unsubscribe: <mailto:>` header
- [ ] **DLVR-05**: A send ledger keyed by (week, SHA-256 email hash) is committed to the repo so a re-run never sends the same issue twice to the same person
- [ ] **DLVR-06**: Logs and artifacts never contain addresses, names, or credentials (counts/hashes only, no SMTP debug output) — repo is public

### Web Archive (WEB)

- [ ] **WEB-01**: Each issue is published as a de-personalized web version on GitHub Pages, and the email links to it ("웹에서 보기")
- [ ] **WEB-02**: Reader can browse past issues on an archive index page

### Automation (AUTO)

- [ ] **AUTO-01**: GitHub Actions workflow runs every Monday 08:00 KST via `cron: "0 8 * * 1"` + `timezone: "Asia/Seoul"` (UTC fallback `0 23 * * 0` if the key is unsupported)
- [ ] **AUTO-02**: Manual `workflow_dispatch` supports `mode = preview | test | send` (default `preview`) and `week`; preview uploads the de-personalized HTML as an artifact without touching SMTP or subscriber secrets; test sends only to `TEST_RECIPIENT`
- [ ] **AUTO-03**: Workflow uses a concurrency group (no overlapping runs), SHA-pinned actions, `contents: write` scoped to the commit step, and commits `archive/` back even on partial failure
- [ ] **AUTO-04**: Owner receives a weekly run-report email (success counts or failure), and the weekly archive commit keeps the public repo's schedule from the 60-day auto-disable
- [ ] **AUTO-05**: Re-runs reuse stage checkpoints (no re-fetch, no re-billing Claude) unless `--force-stage` is passed; a stale-issue guard prevents a late run from mailing an old week

## v2 Requirements

### Content

- **CONT-01**: At-a-glance summary table at the top of the email
- **CONT-02**: Week-over-week trend history

### Subscribers

- **SUBS-01**: Subscribe / unsubscribe web form
- **SUBS-02**: Per-subscriber topic filtering

### Feedback

- **FDBK-01**: Reply-based feedback collection

## Out of Scope

| Feature | Reason |
|---------|--------|
| Manual review/approval before send | User chose full automation; fail-closed validation replaces it |
| Open/click tracking | Not needed for a tiny list; hurts deliverability and privacy |
| Per-paper thumbnails / text-as-image headings | Size budget, image blocking, Naver/Gmail rendering |
| LLM-written HTML | Breaks email-safe markup; Claude only returns JSON |
| Sources other than HF Papers | HF Papers is the fixed reference source |
| ESP / domain authentication / bulk sending | Gmail SMTP sufficient for current list size |
| "(광고)" subject prefix | Informational digest, not 영리목적 광고성 정보 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| (filled by roadmap) | | |

**Coverage:**
- v1 requirements: 39 total
- Mapped to phases: 0
- Unmapped: 39 ⚠️

---
*Requirements defined: 2026-11-02*
*Last updated: 2026-11-02 after initial definition*
