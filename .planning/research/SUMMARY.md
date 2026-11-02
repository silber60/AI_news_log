# Project Research Summary

**Project:** AI 주간 모델 뉴스레터 (Weekly AI Model Brief)
**Domain:** Unattended weekly batch pipeline: HF Papers fetch, metadata enrichment, Claude analysis, table-based HTML email, Gmail SMTP, scheduled on GitHub Actions. Korean recipients, Naver Mail first.
**Researched:** 2026-11-02
**Confidence:** MEDIUM-HIGH (HIGH on stack, HF API and pipeline shape, all probed live; MEDIUM on Claude API parameter combinations and Gmail limits; LOW on Naver Mail rendering and on the two requirements added after research: humanizer rules and the "이번 주 바로 써볼 만한 것" section)

> **User decisions made after synthesis (override the synthesizer's recommendations below):**
> - **Repo visibility: PUBLIC** (under `silber60`). Consequences: CSV only in `SUBSCRIBERS_CSV` secret; logs/artifacts are world-readable, so log counts/hashes only and upload only de-personalized HTML; weekly archive commit doubles as 60-day keepalive; GitHub Pages web version/archive is free.
> - **Cron: `cron: "0 8 * * 1"` + `timezone: "Asia/Seoul"`.** Verify exact YAML placement of `timezone:` in the automation phase; fall back to UTC cron if unsupported. Accept that Actions schedules can fire minutes late.

## Executive Summary

This is a small, linear, stage-gated batch job with no server, no database and no UI. Once a week it pulls the previous ISO week's papers from the HF `daily_papers` JSON API, ranks them by upvotes, gathers license and artifact evidence from the HF Hub and GitHub, asks Claude to turn that evidence into Korean practitioner fields, renders a hand-built table layout with inline CSS, and sends one message per subscriber over Gmail SMTP. Each stage writes a JSON checkpoint to `archive/<YYYY-Www>/`, so a re-run never re-bills Claude or regenerates different content. The repo doubles as the datastore and archive. All four researchers converged on Python (3.14, managed by uv), not Node: the author's Mac has no Node, and the Python stdlib already covers SMTP, MIME, CSV and timezones.

The product's only real differentiator is the per-item verdict on whether a team can use the model: commercial use, PoC readiness, Claude/GPT applicability, hardware. No competitor (AlphaSignal, TLDR AI, The Batch, Korean newsletters) offers it. That verdict is also the biggest risk. If Claude is asked to judge licenses from an abstract, it will write "Apache 2.0, 상업 가능" with full confidence about papers that have no weights yet. All researchers agree on one rule: **code decides the facts and Claude explains them.** License, PoC and VRAM verdicts come from HF/GitHub metadata through lookup tables in code. Every judgment field is an enum that includes `확인 필요`. A post-validator downgrades any positive verdict that has no evidence URL.

Two requirements were added after research and are not covered in depth by any research file: (1) every Claude-generated sentence must follow the humanizer skill's rules, and (2) a top section, "이번 주 바로 써볼 만한 것", must pick items that would make a good Claude Skill or custom GPT. Both belong in the analysis phase and both change the `Issue` schema, so they have to be designed before the schema freezes. The other main risks are operational: picking the wrong week because the runner clock is UTC, sending twice on re-runs, the cron silently stopping or firing late, PII and secrets leaking through logs in a public repo, and Naver/Gmail mangling the HTML. Each has a cheap, known fix, listed below.

## Key Findings

### Recommended Stack

Python 3.14 on `ubuntu-latest` with uv (`uv sync --frozen`). No build step, no second toolchain. Details in STACK.md.

**Core technologies:**
- **Python 3.14 + uv 0.13**: runtime and lockfile. 3.15 too new for wheels.
- **httpx 0.28 + tenacity 9.2**: HF Hub and GitHub REST calls with retry/backoff. Do not wrap Anthropic calls in tenacity; the SDK already retries.
- **`anthropic>=2.3,<3`, model `claude-sonnet-5-5`** (via `CLAUDE_MODEL` env, `claude-opus-5-5` drop-in upgrade): `messages.parse(output_format=Model)`. Do not send `temperature`/`top_p`/`top_k`, assistant prefill or forced `tool_choice` (API version `2026-10-21` returns 400). Check `stop_reason == "refusal"`.
- **Pydantic 2.14**: the single `Issue` schema, contract between every stage.
- **Jinja2 3.1.6 (autoescape on) + css-inline 0.23**: hand-written table template, inlined at build time. Not MJML, not premailer.
- **stdlib `smtplib.SMTP_SSL` + `email.message.EmailMessage`**: RFC 2047 Korean subjects, multipart text + HTML.
- **stdlib `csv` with `encoding="utf-8-sig"`** (fallback `cp949`).
- **GitHub Actions**: `actions/checkout@v7`, `astral-sh/setup-uv@v10`, `actions/upload-artifact@v7`, pinned by SHA.

**Verified data-source endpoints (live probe 2026-11-02):**
- `GET /api/daily_papers?week=YYYY-Www&limit=100&p=N`: paginate until empty, sort by `paper.upvotes` client-side. Never `sort=trending`.
- `GET /api/arxiv/{id}/repos` and `GET /api/papers/{id}`: linked models, datasets, Spaces.
- `GET /api/models/{repo}`: `cardData.license`, `license_name`, `gated`, `safetensors.total`.
- `GET api.github.com/repos/{o}/{r}/license` with `GITHUB_TOKEN`.

### Expected Features

**Must have (table stakes):**
- English title plus Korean gloss, 한줄 요약 (~80 chars, enforced in code), rank and upvotes, links (HF, arXiv, code, model/Space)
- AI 종류 as a closed enum
- One reusable card component; badges are colored `<td>` text, never images
- Week range in subject and header ("10/26(월) ~ 11/1(일)")
- Personalized greeting with "구독자님" fallback, HTML-escaped
- Plain-text alternative generated from data
- Footer: sender, contact, license disclaimer, mailto unsubscribe line, `List-Unsubscribe` header. No "(광고)" in subject.
- Fail-closed sending: empty fetch or invalid issue sends nothing; job fails; GitHub emails the owner.

**Should have (differentiators, all P1 here):**
- 상업적 사용 verdict + license name via SPDX lookup table
- PoC verdict from weights/code/demo presence
- Claude/GPT applicability enum + one sentence
- 활용 아이디어 (max 2), 라이선스·공개 badges, 실행 난이도·GPU from parameter count
- 이번 주 트렌드 총평 (second pass over the 10 results)
- **"이번 주 바로 써볼 만한 것" highlight section**
- At-a-glance summary table at top (P2, or v1 if Figma design includes it)

**Defer (v1.x / v2+):**
- Web version + GitHub Pages archive (free now that repo is public)
- Subscribe form, per-subscriber filtering, trend history, reply feedback
- Never: open/click tracking, per-paper thumbnails, LLM-written HTML, sponsor content

### Requirements Added After Research (synthesizer analysis, LOW-MEDIUM confidence)

**Humanizer rules on all Claude-generated text**
- Port rules from `~/.claude/skills/humanizer/SKILL.md` into `prompts/humanizer_ko.md`.
- Write Korean equivalents explicitly: "단순히 ~가 아니라 ~", "~를 넘어", "~뿐만 아니라 ~까지", forced three-item lists, 혁신적/획기적/주목할 만한/게임 체인저 hype, connector dashes, one-line closing summaries, bold label prefixes.
- Layers:
  1. Korean rules in the system prompt of every analysis call (cacheable).
  2. Deterministic post-parse fixes: dashes, bold markers, length caps.
  3. Banned-pattern lint over free-text fields; on a hit, one schema-constrained polish call on free-text only, enums/URLs untouched and re-validated.
  4. Still failing → warn and send. Style never blocks; only data validity fails closed.
- Pattern list in a file with unit tests.

**"이번 주 바로 써볼 만한 것" (Claude Skill / GPTs highlight)**
- Generate in the trend second-pass call (needs all 10 analyses).
- Per-item `skill_gpt_fit: Literal["Claude Skill", "GPTs", "둘 다", "해당 없음"]` + short reason. Issue-level `highlights: list[Highlight]` (1–3), each with `paper_id`, `왜 좋은지`, `어떻게 만들지`.
- Validate every `paper_id` is in this week's Top 10.
- Empty state: hide section or show "이번 주는 해당 항목 없음". Never force a pick.
- Section sits above Top 10 — Figma and template include it from the start.

### Architecture Approach

Linear pipeline: `issue_id` resolver (previous ISO week, Asia/Seoul) → fetch → select → enrich → analyze → render → personalize → send → ledger. Each stage reads/writes a JSON checkpoint in `archive/<YYYY-Www>/` and skips when output exists unless `--force-stage`. Content stages never touch subscriber/SMTP secrets. One CLI + one workflow with `mode = preview | test | send`; schedule uses `send`, manual dispatch defaults to `preview`.

**Major components:**
1. **`schema.py` (`Issue`)**: hub contract; freeze early with highlight/humanizer fields.
2. **Fetcher / Selector**: paginated fetch, dedupe by arXiv id, sort by upvotes, Top 10; snapshot raw JSON.
3. **Enricher + verdict rules**: evidence only, then deterministic license→상업적 사용, artifacts→PoC, params→VRAM.
4. **Analyzer**: 10 `messages.parse` calls + trend-and-highlight call + optional humanizer polish; validate, retry once.
5. **Renderer**: Jinja2 → inlined HTML + text, size assert (< 90 KB), de-personalized copy archived as web version.
6. **Delivery**: CSV from `SUBSCRIBERS_CSV`, one `EmailMessage` per recipient over one SMTP connection, ~1 s throttle, SHA-256 email-hash ledger flushed per send.
7. **Workflow**: cron + `workflow_dispatch(mode, week)`, `concurrency: newsletter` / `cancel-in-progress: false`, `archive/` commit-back with `if: always()`, artifact upload of non-personalized HTML only.

### Critical Pitfalls

1. **LLM invents license/commercial-use claims.** SPDX mapping in code (Apache/MIT/BSD = 가능; Llama/Gemma/OpenRAIL/`other` = 조건부; NC/research-only = 불가; missing = 확인 필요), code and weights licenses separate, Claude writes only the reason. Golden set of ~10 papers.
2. **Wrong week (UTC runner).** `datetime.now(ZoneInfo("Asia/Seoul"))`, previous ISO week, `--week` override, frozen-time tests.
3. **Double sends.** Ledger keyed `(week, email_hash)` committed to repo, preview default, concurrency group, re-runs reuse snapshots.
4. **Cron late or stopped.** Public repo → 60-day auto-disable; weekly archive commit + run-report email to owner as dead man's switch.
5. **Secrets/PII leak (public repo: logs are world-readable).** Never `smtplib.set_debuglevel` in CI (base64 AUTH bypasses masking). Log counts/hashes only, CSV in secret, de-personalized artifacts only, SHA-pinned actions, dedicated Gmail sender.
6. **Email rendering.** Gmail clips ~102 KB; Naver strips `<head>` `<style>`; no web fonts; Figma div/flex markup breaks. 600–640 px, nested tables, inline styles, system Korean font stack on every element, < 90 KB assert, real sends to Naver + Gmail (web, mobile, light, dark).

Also: Korean header encoding (`EmailMessage` only, strip CR/LF from names), app password revoked on password change, trend drift beyond the 10 items, prompt injection via abstracts (delimiters; license label is code-owned).

## Reconciled Disagreements

| Topic | Resolution |
|-------|------------|
| **Cron** | **User chose `cron: "0 8 * * 1"` + `timezone: "Asia/Seoul"`.** Verify YAML syntax in automation phase; UTC fallback `0 23 * * 0`. Week computed in code regardless. |
| **Fetch method** | `week=` primary; filter by `paper.submittedOnDailyAt` in KST; dedupe by `paper.id`; cross-check once vs `date=` loop; keep loop as fallback. |
| **Enums** | Commercial `가능 / 조건부 / 불가 / 확인 필요`. PoC `바로 가능 / 코드만 / 논문만 / 확인 필요`. Claude/GPT `직접 사용 / 기법 적용 가능 / 해당 없음 / 확인 필요`. Freeze in schema phase. |
| **Dispatch inputs** | `mode: preview / test / send` (default `preview`) + `week`. Test recipient from `TEST_RECIPIENT` secret. |
| **Permissions** | `contents: write` scoped to the commit job only. |
| **Versions** | Python 3.14, uv, `@v7/@v10`, SHA-pinned. |
| **Headline fonts** | No text images; design to look right in Apple SD Gothic Neo / Malgun Gothic. |
| **Figma width** | 640 px email canvas, single column. Confirm with user. |

## Repo Visibility: PUBLIC (decided)

| Concern | Handling |
|---------|----------|
| Subscriber CSV | `SUBSCRIBERS_CSV` secret only; commit `subscribers.example.csv`; `.gitignore` `subscribers*.csv` |
| Actions logs/artifacts | World-readable → counts/hashes only, de-personalized HTML artifact only |
| 60-day schedule auto-disable | Weekly archive commit + `gh workflow enable` backup step |
| GitHub Pages web version/archive | Free — candidate for v1.x |
| Hosted images | `raw.githubusercontent.com` works |
| Actions minutes | Unlimited |

## Implications for Roadmap

Six phases suggested (user chose Coarse granularity — roadmapper may merge). Phase 4 can run in parallel once Phase 1 freezes the schema.

1. **Foundation, Schema and Paper Collection** — repo (public, `.gitignore` for CSV), uv project, CLI `--mode/--week/--force-stage`, KST `issue_id` resolver + frozen-time tests, full `Issue` schema with frozen enums (`skill_gpt_fit`, `highlights`, separate code/weights licenses), paginated HF fetch, select/dedupe, checkpoint store, fixture week.
2. **Evidence Enrichment and Deterministic Verdicts** — HF arxiv→repos, model detail, GitHub license; SPDX table; PoC rules; VRAM estimate; golden-set tests.
3. **Claude Analysis, Humanizer and Highlight Selection** — prompts (`analyze_paper.md`, `weekly_trend.md`, `humanizer_ko.md`); 10 parse calls + trend/highlight call; post-validator; lint + polish; refusal handling.
4. **Figma Web Design and Email Template** (parallel with 2–3) — 640 px frame in `qyJcGii2MLHTbi4W9mPZkx` from mobile tokens; sections: header/week, greeting, 이번 주 바로 써볼 만한 것, trend, optional summary table, 10 cards, footer; `email.html.j2` + `email.txt.j2`, css-inline, < 90 KB assert, preview artifact.
5. **Delivery** — CSV from secret (BOM/CP949-safe), personalization, `EmailMessage`, `List-Unsubscribe`, `SMTP_SSL` + throttle, `test` mode, hashed ledger, count-only logging.
6. **Automation, Hardening, First Live Send** — `weekly.yml` (tz cron, dispatch inputs, concurrency, scoped write, SHA pins, commit-back), stale-issue guard, run-report email, keepalive, README runbook, Gmail/Naver test sends, first live Monday.

**Ordering rationale:** schema is the hub; evidence before judgment; content before delivery (phases 1–4 in `preview`, no secrets); scheduling last, after idempotency exists.

### Research Flags

- **Phase 3:** Korean humanizer port; `messages.parse` + `effort` and refusal fallback unverified; highlight criteria new.
- **Phase 4:** Naver rendering (one 2016 source); Figma MCP token workflow; mobile design fonts; Naver app dark mode.
- **Phase 6 (light):** `timezone:` YAML syntax; whether `GITHUB_TOKEN` push counts as activity.
- Standard (skip research): Phases 1, 2, 5.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyPI/GitHub versions today; HF probed live; Claude rules from official docs. Two param combos MEDIUM. |
| Features | MEDIUM | Conventions solid; 제50조 reading is interpretation; two new requirements unresearched. |
| Architecture | HIGH | All researchers agree on checkpoints, evidence-first, mode switch, ledger. |
| Pitfalls | MEDIUM | HIGH for UTC, clipping, encoding, secrets, Actions. MEDIUM Gmail/HF semantics. LOW Naver. |

**Overall:** MEDIUM-HIGH.

### Gaps to Address

- Korean humanizer rule set (phase 3 planning).
- Highlight criteria (repeatable task, no self-hosting, clear I/O) + empty-state rule; review first 2–3 weeks via `preview`.
- Figma canvas width (640 px vs "desktop") + fonts of existing mobile design.
- Naver rendering and spam placement (real sends; ask subscriber to whitelist sender).
- Dedicated Gmail sender account with 2SV + app password before phase 5.
- HF `week=` weekend coverage (probe returned Mon–Fri only) → `date=` fallback.
- Claude API combinations smoke test at start of phase 3.

## Sources

### Primary (HIGH)
- Live probes 2026-11-02: `huggingface.co/api/daily_papers?week=2026-W44`, `/api/papers/{id}`, `/api/arxiv/{id}/repos`, `/api/models/{id}`, `/api/models?filter=arxiv:{id}`
- HF Hub OpenAPI spec, HF Hub API docs, model-card license docs; `huggingface_hub` `list_daily_papers` source
- PyPI JSON API, GitHub Releases API (2026-11-02)
- Anthropic docs: API migration 2026-10-21, structured outputs, model table; anthropic-sdk-python CHANGELOG (2.3.0)
- GitHub changelog 2026-03-26 (IANA `timezone` on schedules); GitHub docs on 60-day disable
- Gmail CSS support docs

### Secondary (MEDIUM)
- GitHub community discussions on schedule delays; cronuru; keepalive-workflow
- Gmail SMTP app-password/limit guides (n8n, nylas, nodemailer, serversmtp)
- Email CSS inlining guides; velog Korean email template; Adobe CJK web fonts in email
- Competitors: AlphaSignal, TLDR AI, The Batch, HF upvote digests, gpters.org roundup
- 정보통신망법 제50조 + secondary 광고성 guidance

### Tertiary (LOW)
- Naver Mail rendering: Email on Acid 2016
- Naver app dark mode: undocumented
- Humanizer and highlight recommendations: synthesizer inference

---
*Research completed: 2026-11-02 · user decisions (public repo, tz cron) applied by orchestrator*
*Ready for roadmap: yes*
