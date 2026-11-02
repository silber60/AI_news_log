# Roadmap: AI 주간 모델 뉴스레터 (Weekly AI Model Brief)

## Overview

Vertical MVP. Phase 1 builds a thin pipeline that runs end to end: it resolves last week in KST, fetches HF Papers, picks the Top 10, runs a minimal Claude analysis into the frozen `Issue` schema, renders a plain table email, and sends a preview or test mail from a manual GitHub Actions run. Later phases deepen the content in this order: code-owned evidence and verdicts, then humanizer and the "이번 주 바로 써볼 만한 것" highlight, then the Figma-based design with the web archive. The last phase adds the Monday cron, idempotent re-runs and hardening, and ends with the first unattended live send.

## Phases

- [ ] **Phase 1: End-to-End Skeleton** - Manual Actions run fetches last week's Top 10, analyzes minimally, renders a basic email, and previews or test-sends it
- [ ] **Phase 2: Evidence & Practical Verdicts** - Each item shows code-decided 상업적 사용 / PoC / GPU verdicts with evidence, plus Claude/GPT applicability and a weekly trend
- [ ] **Phase 3: Humanizer, Highlight & Explainer** - All generated Korean text reads human, a top "이번 주 바로 써볼 만한 것" section promotes Claude Skill / GPTs candidates, and a weekly 기술 해설 코너 explains one technique in plain language
- [ ] **Phase 4: Figma Design, Email Template & Web Archive** - 640px Figma design implemented as the final email, verified in Naver/Gmail, with a GitHub Pages web version and archive
- [ ] **Phase 5: Scheduled Automation & Hardening** - Mail arrives every Monday 08:00 KST unattended, re-runs never double-send, and the owner gets a run report

## Phase Details

### Phase 1: End-to-End Skeleton
**Goal**: The owner can trigger one manual GitHub Actions run that produces last week's Top 10 issue and either previews it as an artifact or mails it to a test recipient, with no secrets or PII leaking in the public repo.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: COLL-01, COLL-02, COLL-03, COLL-04, ANLY-01, ANLY-03, ANLY-06, DSGN-03, DSGN-04, DLVR-01, DLVR-02, DLVR-03, DLVR-06, AUTO-02
**Success Criteria** (what must be TRUE):
  1. A `workflow_dispatch` run with `mode=preview` (default) resolves the previous ISO week in KST (or the given `week`), saves raw and Top 10 JSON under `archive/<YYYY-Www>/`, and uploads a de-personalized HTML artifact without reading SMTP or subscriber secrets
  2. A `mode=test` run delivers a Korean-subject multipart email to `TEST_RECIPIENT` via Gmail SMTP showing 10 items with rank, upvotes, AI 종류, Korean title gloss, 한줄 요약 and up to 2 활용 아이디어
  3. A `mode=send` run reads subscribers from the `SUBSCRIBERS_CSV` secret (BOM/CP949 safe) and 홍길동 receives a mail greeting "홍길동님" (fallback "구독자님")
  4. An empty or unreachable HF fetch, or Claude output that is still invalid after one retry, fails the job and sends nothing
  5. Public Actions logs and artifacts show only counts/hashes: no addresses, names, credentials or SMTP debug output; rendered HTML stays under 90 KB and has a plain-text alternative
**Plans**: 6 plans

Plans:
- [ ] 01-01-PLAN.md — Walking skeleton: uv project, offline end-to-end build + test send, frozen Issue v1 (owner checkpoint)
- [ ] 01-02-PLAN.md — Collection hardening: KST week math, week=/date= fallback (W53), retries, empty-fail, Top N tie-break
- [ ] 01-03-PLAN.md — Analysis hardening: retry-once, refusal + fallbacks downgrade, field checks + summary trim, full prompt + humanizer core
- [ ] 01-04-PLAN.md — Render: full Phase 1 card email, inline CSS + KR fonts, 90 KB gate, plain text, D-01/D-03 subject
- [ ] 01-05-PLAN.md — Delivery: send mode + CSV secret, greeting, redaction handler, failure notice, build secret isolation
- [ ] 01-06-PLAN.md — Actions workflow + CI, push/secrets (owner), live preview/test/send/failure runs and log audit

### Phase 2: Evidence & Practical Verdicts
**Goal**: Readers can tell at a glance whether each model is usable in practice, with verdicts decided by code from real HF/GitHub evidence and explained by Claude.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: EVID-01, EVID-02, EVID-03, EVID-04, EVID-05, ANLY-02, ANLY-04, ANLY-05
**Success Criteria** (what must be TRUE):
  1. Each item shows a 상업적 사용 verdict (`가능 / 조건부 / 불가 / 확인 필요`) with code and weights licenses listed separately and evidence links
  2. Each item shows a PoC verdict (`바로 가능 / 코드만 / 논문만 / 확인 필요`) and 실행 난이도·필요 GPU (size, estimated VRAM, local-run feasibility) or `확인 필요`
  3. Each item shows Claude/GPT 사용 가능 여부 (`직접 사용 / 기법 적용 가능 / 해당 없음 / 확인 필요`) with a one-sentence reason, and verdict reasons written by Claude from code-supplied evidence
  4. No positive verdict appears without an evidence URL, and the verdict rules pass a golden-set test of about 10 papers with known licenses
  5. The issue opens with a 2-3 sentence 이번 주 트렌드 총평 that mentions only this week's 10 items
**Plans**: TBD

### Phase 3: Humanizer, Highlight & Explainer
**Goal**: Every Claude-written sentence reads like a person wrote it, readers see up to 3 items worth turning into a Claude Skill or GPTs right away, and each issue explains one AI technique in plain language.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: HUMN-01, HUMN-02, HUMN-03, HILT-01, HILT-02, HILT-03, EXPL-01, EXPL-02
**Success Criteria** (what must be TRUE):
  1. Generated text in a preview issue contains no banned AI tells (e.g. "단순히 ~가 아니라", "~를 넘어", 혁신적/획기적/게임 체인저, connector dashes, bold labels, closing one-liners); the pattern list is unit-tested
  2. When lint finds AI tells, one polish pass rewrites only free-text fields; enums and URLs stay unchanged, and leftover style issues log a warning without blocking the send
  3. Above the Top 10, an "이번 주 바로 써볼 만한 것" section shows 1-3 items, each with 왜 좋은지 and 어떻게 만들지 in 1-2 lines and a Claude Skill / GPTs / 둘 다 tag
  4. Highlights only point at this week's Top 10; in a week with no fit the section shows "이번 주는 해당 항목 없음"
  5. Each issue has a 기술 해설 코너 filling the `Issue.explainer` slot reserved in Phase 1: one technique from this week's Top 10, explained in plain Korean, preferring a topic absent from the committed past-topics record (fallback: the #1 paper's core technique)
**Plans**: TBD

### Phase 4: Figma Design, Email Template & Web Archive
**Goal**: The newsletter looks like the designed brand in Naver Mail and Gmail, and every issue can also be read and browsed on the web.
**Mode:** mvp
**Depends on**: Phase 3 (Figma frame work can start after Phase 1)
**Requirements**: DSGN-01, DSGN-02, DSGN-05, DLVR-04, WEB-01, WEB-02
**Success Criteria** (what must be TRUE):
  1. Figma file `qyJcGii2MLHTbi4W9mPZkx` has a 640px web/email frame using the mobile design's fonts, colors and component styles, with sections in order: header + week range, greeting, 이번 주 바로 써볼 만한 것, 트렌드 총평, Top 10 cards, footer
  2. The email built from that design renders correctly in Naver Mail and Gmail (web and mobile app, light and dark), confirmed by real test sends
  3. The footer shows sender info and an unsubscribe line, and each message carries a `List-Unsubscribe: <mailto:>` header
  4. Clicking "웹에서 보기" opens a de-personalized copy of the issue on GitHub Pages, and an archive index lists past issues
**Plans**: TBD
**UI hint**: yes

### Phase 5: Scheduled Automation & Hardening
**Goal**: The newsletter reaches subscribers every Monday 08:00 KST with nobody touching it, re-runs are safe, and the owner learns about every outcome.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: AUTO-01, AUTO-03, AUTO-04, AUTO-05, DLVR-05
**Success Criteria** (what must be TRUE):
  1. The workflow fires on Monday 08:00 KST from `cron: "0 8 * * 1"` + `timezone: "Asia/Seoul"` (UTC `0 23 * * 0` fallback), and the first unattended Monday issue lands in the subscriber's inbox
  2. Re-running a week reuses stage checkpoints (no re-fetch, no new Claude billing) unless `--force-stage` is given, and the committed hash ledger stops any duplicate send to the same person
  3. A late or stale run refuses to mail an old week; runs never overlap (concurrency group), actions are SHA-pinned, and `archive/` is committed back even after a partial failure
  4. The owner gets a run-report email each week with success counts or the failure, and the weekly archive commit keeps the schedule clear of the 60-day auto-disable
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. End-to-End Skeleton | 0/6 | Planned | - |
| 2. Evidence & Practical Verdicts | 0/TBD | Not started | - |
| 3. Humanizer, Highlight & Explainer | 0/TBD | Not started | - |
| 4. Figma Design, Email Template & Web Archive | 0/TBD | Not started | - |
| 5. Scheduled Automation & Hardening | 0/TBD | Not started | - |
