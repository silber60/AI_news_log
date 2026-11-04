# Roadmap: AI 주간 모델 뉴스레터 (Weekly AI Model Brief)

## Overview

Vertical MVP. Phase 1 builds a thin pipeline that runs end to end: it resolves last week in KST, fetches HF Papers, picks the Top 10, runs a minimal Claude analysis into the frozen `Issue` schema, renders a plain table email, and sends a preview or test mail from a manual GitHub Actions run. Later phases deepen the content in this order: code-owned evidence and verdicts, then humanizer and the "이번 주 바로 써볼 만한 것" highlight, then the Figma-based design with the web archive. The last phase adds the Monday cron, idempotent re-runs and hardening, and ends with the first unattended live send.

## Phases

- [x] **Phase 1: End-to-End Skeleton** - Manual Actions run fetches last week's Top 10, analyzes minimally, renders a basic email, and previews or test-sends it
- [x] **Phase 1.1: Newsletter Design v2 & Model Detail Fields** (INSERTED) - The email follows the approved Figma v2 draft (otter mascot, Top 3 → explainer → 4-10 layout, headline-style subject) and each card shows one-line + multi-line summaries and a model info table
- [x] **Phase 1.2: GitHub-Star Selection & Friendly Content** (INSERTED) - Items are picked by GitHub stars (3-10, star ≥ 100 decides the count), each article carries its own image, empty model-info rows disappear, and every text reads in friendly 해요체 with a one-line use idea
- [x] **Phase 2: Evidence & Practical Verdicts** - Each item shows code-decided 상업적 사용 / PoC / GPU verdicts with evidence, plus Claude/GPT applicability and a weekly trend
- [x] **Phase 3: Humanizer, Highlight & Explainer** - All generated Korean text reads human, a top "이번 주 바로 써볼 만한 것" section promotes Claude Skill / GPTs candidates, and a weekly 기술 해설 코너 explains one technique in plain language
- [ ] **Phase 4: Figma Design, Email Template & Web Archive** - 640px Figma design implemented as the final email, verified in Naver/Gmail, with a GitHub Pages web version and archive
- [ ] **Phase 4.1: Public Subscribe & Instant Welcome Issue** (INSERTED) - Anyone can subscribe from a web page, lands on the subscriber list, and immediately receives the latest issue
- [x] **Phase 4.2: Domain Sending via Resend** (INSERTED) - Mail goes out from newsletter@modaklog.characterplanner.co.kr with SPF/DKIM/DMARC instead of a personal Gmail
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

### Phase 1.1: Newsletter Design v2 & Model Detail Fields (INSERTED)
**Goal**: The newsletter looks like the approved Figma v2 draft and each Top 10 card tells the reader what the model is, not how to use it.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: DSGN-06, DSGN-07, ANLY-07, ANLY-08, DLVR-07
**Design source**: Figma `qyJcGii2MLHTbi4W9mPZkx`, frame `Newsletter / Web 640 (draft)` (node 7:22), card component `Card / Top10 item` (node 7:2)
**Success Criteria** (what must be TRUE):
  1. The rendered email follows the Figma v2 section order: otter banner, header, issue headline, greeting, 이번 주 바로 써볼 만한 것 slot, 흐름 slot, Top 3, AI 기술 쉽게 보기 slot, 4위~10위, closing line + waving-otter banner, footer; empty Phase 3 slots are skipped cleanly
  2. Each card shows rank/type/upvotes, Korean + English titles, a bold one-line summary, a 3-line summary, a 모델 정보 table (유형, 구조, 크기, 학습 데이터, 공개 범위) with `확인 필요` for unknown facts, badges and links; 활용 아이디어 is gone
  3. Otter images and an optional single per-item image load from public HTTPS URLs with alt text; the email stays under 90 KB and reads fine with images blocked
  4. The subject is a headline-style line about the week's top topic (no fixed brand prefix), `[TEST]` still prefixes test mode, and nothing in the email says it is AI- or auto-generated
  5. `Issue` schema v2 is committed with a snapshot test, v1 fixtures are migrated, and the full test suite passes
**Plans**: 5 plans

Plans:
- [ ] 01.1-01-PLAN.md — Issue v2 contract (owner checkpoint) + tracer: Claude 3-line summary and 유형/구조 to card, code fallback headline_ko, v1 tests rewritten, length caps, shared HF route helper (wave 1)
- [ ] 01.1-02-PLAN.md — Static inputs: keyed/compressed otter assets in docs/assets/email/v1, build script, Pillow, halo tests; trimmed HF paper/model fixtures (wave 1)
- [ ] 01.1-03-PLAN.md — Enrich stage (code-decided 크기/학습 데이터/공개 범위, one HF image per card) + Claude headline with fallback (wave 2)
- [ ] 01.1-04-PLAN.md — Figma v2 template: section order, otters, Top 3 / 4-10, full card, Phase 3 slots, headline subject, no AI wording, size/images-off guards (wave 2)
- [ ] 01.1-05-PLAN.md — Hosting choice, push, image URL check, live preview run; 01-06 live runs follow on v2 (D-20) (wave 3)

### Phase 1.2: GitHub-Star Selection & Friendly Content (INSERTED)
**Goal**: Readers get the week's most-starred models, explained so a non-specialist understands what each one is, with each article's own picture next to it.
**Mode:** mvp
**Depends on**: Phase 1.1
**Requirements**: COLL-05, DSGN-08, ANLY-09, ANLY-10
**Success Criteria** (what must be TRUE):
  1. For the target ISO week (Mon-Sun KST, unchanged), items are ranked by GitHub stars; the count N is the number of papers with ≥ 100 stars, clamped to 3..10; with fewer than 3 such papers the 3 most-starred are used, topped up by HF upvotes when fewer than 3 papers have a repo; ties break by upvotes
  2. The headline and greeting use N ("이번 주 AI 모델 {N}", "…GitHub star를 많이 받은 {N}개를 골랐어요!"), and there is no image under the headline
  3. Each article shows its own image at its position when one exists (HF media first, else the first image of its GitHub README), loaded from a public https URL with alt text, and the email stays under 90 KB
  4. 모델 정보 rows whose value would be `확인 필요` are omitted (the box disappears when all are unknown)
  5. All Claude text is friendly 해요체 like "…골랐어요!", explains what the model is for a non-specialist while keeping technical terms in English, and each article has a one-line 활용 아이디어
**Plans**: 5 plans

Plans:
- [ ] 01.2-01-PLAN.md — Issue v3 contract (owner checkpoint, github_stars + use_idea_ko) + tracer: HF githubStars ranking with the D-03 count rule into selected.json and the ★ card meta; broken tests rewritten (wave 1)
- [ ] 01.2-02-PLAN.md — Render: no hero image, per-card image, 💡 idea in the summary cell, hidden 확인 필요 rows, N-aware greeting and titles, 90 KB worst case (wave 2)
- [ ] 01.2-03-PLAN.md — Tone and idea: 해요체 prompt rules (humanizer fix), code sentence-ending check with one retry (non-fatal), use_idea_ko rules, empty-bracket strip, hook exempt, fixture in 해요체 (wave 2)
- [ ] 01.2-04-PLAN.md — README images: raw.githubusercontent.com README fetch, candidate rules, no-redirect probe with 1 MB / ratio policy, mock_github, star Top 10 fixtures (wave 2)
- [ ] 01.2-05-PLAN.md — Owner push + one live preview run, image check and log audit (no test/send; those stay in 01-06) (wave 3)

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
**Plans**: 6 plans

Plans:
- [ ] 02-01-PLAN.md — Tracer: code PoC verdict end to end (enrich → verdicts.py → finalize → card line), VRAM/GPU rule with guards, enforce_evidence property test, full one-line format + license link, D-12 footer disclaimer, trend under greeting, 90 KB worst case (wave 1)
- [ ] 02-02-PLAN.md — licenses.py: GitHub /license call with GITHUB_TOKEN from github.token, SPDX table, weights side + gated, stricter-of rule, link host allowlist, golden + W44 GitHub captures, httpx logs at WARNING (wave 1)
- [ ] 02-03-PLAN.md — Claude explanations: trend.py (name/rank/number checks, fallback None) and notes.py (batched reasons, grounding + polarity checks, fixed reason for 확인 필요), prompts, FakeAnthropic defaults (wave 1)
- [ ] 02-04-PLAN.md — Wire 상업적 사용 into enrich (code + weights licenses), conftest GitHub API route, hf_models_w44 recapture, enriched.json, 15-case golden test (wave 2)
- [ ] 02-05-PLAN.md — Claude/GPT label + reason in the analyze call with code guard, prompt v5, notes + trend wired into run_build, call counts 13/14 (wave 3)
- [ ] 02-06-PLAN.md — Owner push + live preview run, coverage and log audit, owner review, optional test send (no mode=send) (wave 4)

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
**Plans**: 7 plans

Plans:
- [x] 03-01-PLAN.md — Tracer: skill_gpt_fit + reason in analyze (prompt v6, non-fatal downgrade), one highlight pick call with code guards, always-on section with "이번 주는 해당 항목 없음", call count 14 (wave 1)
- [x] 03-02-PLAN.md — Humanizer: full Korean port of humanizer_ko.md, unit-tested banned-pattern lint over every Claude field, cleanup + dash fallback (wave 1)
- [x] 03-03-PLAN.md — Past-topics record: data/explainer_topics.json, topics.load_past/record, `record-topic` CLI, owner decision, then the send-on-main record-topic job with contents: write and job-aware static tests (wave 1)
- [x] 03-04-PLAN.md — Explainer: one call over this week's items + past topics, caps and grounding checks, alias-aware repeat rule with #1 fallback, image copied from a related item, call count 15 (wave 2)
- [x] 03-05-PLAN.md — Size: explainer image row, worst case with 3 picks + full explainer + image, per-table font stack (one revertable commit, about 14 KB saved) (wave 2)
- [x] 03-06-PLAN.md — Polish: lint-gated single polish pass at the end of the build with fact, stage and whole-dump diff guards, leftovers warn only, call counts 15 / 16 (wave 3)
- [x] 03-07-PLAN.md — Owner push, one live preview with lint and log audit, mode=test send to Gmail + Naver for the font checklist, owner review (no mode=send) (wave 4)

### Phase 4: Figma Design, Email Template & Web Archive
**Goal**: The newsletter looks like the designed brand in Naver Mail and Gmail, and every issue can also be read and browsed on the web.
**Mode:** mvp
**Depends on**: Phase 3 (Figma frame work can start after Phase 1)
**Requirements**: DSGN-01, DSGN-02, DSGN-05, DLVR-04, WEB-01, WEB-02
**Success Criteria** (what must be TRUE):
  1. Figma file `qyJcGii2MLHTbi4W9mPZkx` has a 640px web/email frame using the mobile design's fonts, colors and component styles; the email renders its sections in order: header + week range, greeting, 트렌드 총평, 이번 주 바로 써볼 만한 것, Top 3, AI 기술 쉽게 보기, 4위~10위, footer (Phase 2 D-13). Figma frame 7:22 is the earlier design reference with highlight before trend
  2. The email built from that design renders correctly in Naver Mail and Gmail (web and mobile app, light and dark), confirmed by real test sends
  3. The footer shows sender info and an unsubscribe line, and each message carries a `List-Unsubscribe: <mailto:>` header
  4. Clicking "웹에서 보기" opens a de-personalized copy of the issue on GitHub Pages, and an archive index lists past issues
  5. The web issue shows what the email leaves out (Phase 2 D-02): each verdict's `reason_ko`, the Claude/GPT reason, and the code and weights licenses listed separately, with their evidence links
**Plans**: 7 plans

Plans:
- [x] 04-01-PLAN.md — Tracer: owner fixes the 지난 호 anchor; SITE_URL/issue_url, render_web_issue, `publish`/`site` CLI writing data/issues + docs/, merged publish + deploy-pages jobs, pages.yml, live footer links; owner switches Pages to GitHub Actions (checkpoint A) (wave 1) — done (918cb87, 139eb53; Pages run 41759646720)
- [x] 04-02-PLAN.md — Web issue: code-built 판정 근거 rows (reasons, code vs weights license, HF/GitHub evidence, 해당 없음 hidden), responsive web page, owner preview (wave 2)
- [x] 04-03-PLAN.md — Home page per Figma 25:356 with 지난 호 cards newest first, subscribe forms hidden by SUBSCRIBE_URL = None, owner preview (checkpoint B) (wave 2)
- [ ] 04-04-PLAN.md — Unsubscribe backend: owner approves token scheme; HMAC token + fail-closed list fetch, apps_script/Code.gs + Korean setup guide; owner Google setup and /exec URL (checkpoint C) (wave 2)
- [x] 04-05-PLAN.md — Delivery: per-recipient 구독 해지 link, List-Unsubscribe (+Post) headers with the folding fix, send-mode filter that fails closed, new secrets in Deliver only (wave 3)
- [x] 04-06-PLAN.md — Pages confirm page /unsubscribe/ (button-only POST, token regex, noscript fallback), committed and freshness-guarded (wave 3)
- [ ] 04-07-PLAN.md — DSGN-01 recorded as met (frame 7:22, rebrand banner 34:711), DSGN-02 / SC1 wording amended to the Phase 2 D-13 order, color-scheme metas, owner mode=test inbox check light/dark Gmail + Naver (checkpoint D), owner's own send proves the live issue page (wave 4)
**UI hint**: yes

### Phase 4.1: Public Subscribe & Instant Welcome Issue (INSERTED)
**Goal**: A reader who signs up on the subscribe page is on the list right away and gets the most recent issue within minutes, without the owner touching anything.
**Mode:** mvp
**Depends on**: Phase 4 (needs the web archive of past issues and the unsubscribe line)
**Requirements**: SUBS-01, SUBS-03, SUBS-04
**Direction** (amended 2026-11-04 by Phase 4 discuss, 04-CONTEXT D-01/D-09/D-10): the subscribe page is a section of the one GitHub Pages site built in Phase 4 (home = subscribe hero + 지난 호 cards); **Netlify is dropped**. Phase 4 already builds the Google Sheet + Apps Script unsubscribe backend and the hidden form; 4.1 wires subscribing to it. Original note: the owner wanted the subscribe page hosted on Netlify. It is designed in Figma as frame `Website / Subscribe landing (desktop 1280)` (node 25:356): nav, hero with a form (이름, 이메일, 동의), 매주 이런 걸 받아요, a sample issue preview, a bottom CTA with a form, and a footer with a privacy-policy link. Backend (owner chose 2026-11-03): the Netlify page posts to a Google Apps Script web app. A Google Sheet holds the subscriber list, and Apps Script sends the welcome issue through the owner's Gmail. Netlify Forms was rejected. Either way the weekly Actions run reads the live list instead of `SUBSCRIBERS_CSV`, and addresses never enter the public repo or its logs.
**Success Criteria** (what must be TRUE):
  1. A subscribe page (linked from the email footer and the web archive) collects email, name and consent; a submission appears on the subscriber list without owner action
  2. Within minutes of confirming, the new subscriber receives the latest published issue with a personalized greeting
  3. The weekly send reads the live subscriber list, skips unsubscribed or unconfirmed rows, and never sends twice to the same address
  4. Unsubscribing removes the reader from future sends; no address or name appears in the public repo, Actions logs or artifacts
**Plans**: 6 plans

Plans:
- [x] 04.1-01-PLAN.md — Tracer: welcome payload docs/welcome/latest.json from render.py (welcome row, [환영] subject, slots, size gate), email-footer 구독하기 link gated on the endpoint, weekly-bytes pin (wave 1)
- [x] 04.1-02-PLAN.md — Apps Script: schema/key-name decision checkpoint, subscribe/members/import routes, re-subscribe and D-05 delete, oracle-free replies with a welcome queue drained by a 1-minute trigger, Gmail advanced-service welcome sender, appsscript.json, combined Korean README (wave 1)
- [x] 04.1-03-PLAN.md — Live list: fetch_subscribers (fail closed, dedupe, D-13 filter), deliver switch, import-subscribers command + workflow, send-gated SUBSCRIBER_LIST_KEY (wave 2)
- [x] 04.1-04-PLAN.md — Site: live forms behind the endpoint switch (fetch + no-JS fallback, honeypot, consent line), /privacy/ page, footer and sub-page nav (wave 2)
- [x] 04.1-05-PLAN.md — Owner Google + GitHub setup (first 새 배포), cut-over commit, import run, phone round trip sign-up → welcome → unsubscribe → re-subscribe; closes 04-04 Task 3 and D-10/D-12 (wave 3)
- [ ] 04.1-06-PLAN.md — Cleanup after one live-list send: remove the CSV path and import job; owner deletes SUBSCRIBERS_CSV (wave 4)

### Phase 4.2: Domain Sending via Resend (INSERTED)
**Goal**: Weekly, test, failure and welcome mails come from the owner's domain so they stop landing in spam.
**Depends on**: Phase 4.1
**Success Criteria**: (1) send.py and the Apps Script welcome send through Resend from newsletter@modaklog.characterplanner.co.kr with the owner's Gmail as Reply-To; (2) DKIM/SPF/DMARC records live; (3) an owner mode=test lands in the inbox with SPF, DKIM and DMARC PASS
**Plans**: 1 quick plan, done as code (commit cd3f780); owner steps pending. See .planning/phases/04.2-domain-sending-resend/04.2-01-SUMMARY.md

### Phase 5: Scheduled Automation & Hardening
**Goal**: The newsletter reaches subscribers every Monday 08:00 KST with nobody touching it, re-runs are safe, and the owner learns about every outcome.
**Mode:** mvp
**Depends on**: Phase 4.1
**Requirements**: AUTO-01, AUTO-03, AUTO-04, AUTO-05, DLVR-05
**Success Criteria** (what must be TRUE):
  1. The workflow fires on Monday 08:00 KST from `cron: "0 8 * * 1"` + `timezone: "Asia/Seoul"` (UTC `0 23 * * 0` fallback), and the first unattended Monday issue lands in the subscriber's inbox
  2. Re-running a week reuses stage checkpoints (no re-fetch, no new Claude billing) unless `--force-stage` is given, and the committed hash ledger stops any duplicate send to the same person
  3. A late or stale run refuses to mail an old week; runs never overlap (concurrency group), actions are SHA-pinned, and `archive/` is committed back even after a partial failure
  4. The owner gets a run-report email each week with success counts or the failure, and the weekly archive commit keeps the schedule clear of the 60-day auto-disable
**Plans**: 5 plans (runs after Phase 4.2, which owns send.py connection code)

Plans:
- [x] 05-01-PLAN.md — Tracer: 06:00/08:00 Asia/Seoul crons, fail-safe MODE mapping, SEND_PAUSED pause and KST stale guard (--allow-stale), deliver outcome output, queue: max, tip checkouts, always() archive/ledger commit job, outcome-gated publish (wave 1)
- [ ] 05-02-PLAN.md — Per-stage checkpoints in archive/<week>/, lazy Claude client, --force-stage + dispatch input, archive leak scan (wave 2)
- [ ] 05-03-PLAN.md — Send ledger data/ledger/<week>.json, HMAC-SHA256 keys (owner A1), per-message write via on_sent, re-run skip (wave 2)
- [ ] 05-04-PLAN.md — Weekly run report: report command (notify-failure alias), decision table, 해요체 lint-clean copy, always() Report step (wave 3)
- [ ] 05-05-PLAN.md — Owner live proof: push, SEND_PAUSED variable, twice-run test reuse, refused W44 send, first unattended Monday 2026-11-09 (wave 4, checkpoints)

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. End-to-End Skeleton | 6/6 | Complete | 2026-11-03 |
| 1.1. Newsletter Design v2 & Model Detail Fields (INSERTED) | 5/5 | Complete | 2026-11-03 |
| 1.2. GitHub-Star Selection & Friendly Content (INSERTED) | 5/5 | Complete | 2026-11-03 |
| 2. Evidence & Practical Verdicts | 6/6 | Complete | 2026-11-03 |
| 3. Humanizer, Highlight & Explainer | 7/7 | Complete | 2026-11-04 |
| 4. Figma Design, Email Template & Web Archive | 0/TBD | Not started | - |
| 4.1. Public Subscribe & Instant Welcome Issue (INSERTED) | 0/TBD | Not started | - |
| 5. Scheduled Automation & Hardening | 0/TBD | Not started | - |
