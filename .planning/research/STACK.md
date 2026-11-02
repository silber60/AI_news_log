# Stack Research

**Domain:** Automated weekly AI-paper/model email newsletter (HF Papers -> Claude analysis -> HTML email via Gmail SMTP, scheduled on GitHub Actions)
**Researched:** 2026-11-02
**Confidence:** HIGH overall (HF API probed live, package versions read from PyPI/GitHub today, Claude API facts from official docs). MEDIUM on a few combinations flagged inline.

## TL;DR (prescriptive)

- **Language: Python 3.14** on `ubuntu-latest`, dependencies managed by **uv**. Not Node.
- **Data source:** `GET https://huggingface.co/api/daily_papers?week=YYYY-Www&limit=100&p=N` (verified live) -> sort by `paper.upvotes` client-side -> Top 10 -> enrich with `GET /api/papers/{id}` (linkedModels), `GET /api/arxiv/{id}/repos`, `GET /api/models/{repo}` (license tag), GitHub `/repos/{o}/{r}/license`.
- **LLM:** `anthropic==2.3.x` (sends API version `2026-10-21`), model **`claude-sonnet-5-5`** via `client.messages.parse(output_format=PydanticModel)`. Model id from env var so it can be switched to `claude-opus-5-5` without a code change.
- **HTML:** **Jinja2** table-based template + **css-inline** (Rust-backed inliner). No MJML, no premailer.
- **Mail:** stdlib `smtplib.SMTP_SSL("smtp.gmail.com", 465)` + `email.message.EmailMessage` (HTML + plain-text alternative), Gmail app password from GitHub Secrets.
- **CSV:** stdlib `csv` with `encoding="utf-8-sig"`. Subscriber CSV comes from a GitHub Secret (`SUBSCRIBERS_CSV`), never committed.
- **Schedule:** GitHub Actions `schedule` with `cron: "0 8 * * 1"` + `timezone: "Asia/Seoul"` (IANA timezone support shipped March 2026), plus `workflow_dispatch`.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Python | 3.14 (3.14.10 latest patch) | Runtime | Every library here is Python-native: Anthropic SDK with Pydantic `messages.parse`, Jinja2, stdlib `smtplib`/`email`/`csv`, `zoneinfo`. No build step. 3.15 shipped 2026-10-09 and is too new for guaranteed wheels (css-inline, pydantic-core). Python 3.10+ is the floor for `anthropic` 2.x, pydantic 2.14, css-inline 0.23. | HIGH |
| uv | 0.13.6 | Dependency + venv management, lockfile | One `uv.lock`, `uv sync --frozen` in CI, fast installs on cold runners. `astral-sh/setup-uv` caches the store. | HIGH |
| anthropic (Python SDK) | 2.3.0 (released 2026-10-23); pin `anthropic>=2.3,<3` | Claude API client | 2.0.0+ is the first release that sends `anthropic-version: 2026-10-21`. Provides `client.messages.parse(output_format=Model)` -> validated `response.parsed_output`. Built-in retries (default 2) for 408/409/429/5xx. | HIGH |
| Claude model | `claude-sonnet-5-5` ($2 / $10 per MTok, 1M context, 128K output) | Per-paper analysis + weekly trend summary | Current Sonnet. At ~11 calls/week cost is cents either way, so Sonnet 5.5 is chosen for latency and price headroom. Keep `CLAUDE_MODEL` as an env var; `claude-opus-5-5` ($4 / $20) is the drop-in upgrade if license/PoC judgments are too shallow. Use exact ids only, no date suffixes. | HIGH (id/pricing from Anthropic docs cache dated 2026-10-06) |
| Pydantic | 2.14.2 | Output schema for Claude, plus validation of HF API responses | `messages.parse` takes a Pydantic model directly. The same models validate HF JSON (`model_config = ConfigDict(extra="ignore")`), so HF field drift fails loudly in one place. | HIGH |
| httpx | 0.28.1 | HTTP client for HF Hub + GitHub REST | Timeouts on by default, simple sync API. Three endpoints do not justify `huggingface_hub`'s `PaperInfo` abstraction (see Alternatives). | HIGH |
| Jinja2 | 3.1.6 | HTML email templating | Industry default. Autoescaping (`select_autoescape(["html"])`) protects against HTML injection from paper titles/abstracts and LLM output. Loops/conditionals cover 10 cards + trend block + per-subscriber greeting. | HIGH |
| css-inline | 0.23.1 (released 2026-10-27) | Move `<style>` rules into `style=""` attributes | Actively maintained, Rust core, fast, handles `<style>` + `<link>`, keeps `@media` blocks in `<head>` when `keep_style_tags=True`. Naver Mail and the Gmail app with non-Gmail accounts do not reliably honor `<head>` CSS, so inline is mandatory. | HIGH |
| GitHub Actions | `actions/checkout@v7`, `astral-sh/setup-uv@v10` (or `actions/setup-python@v7`) | Free scheduled runner | Runs while the user's Mac is off. Secrets store for API key, app password, subscriber CSV. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | 9.2.1 | Retry with backoff for HF/GitHub calls and the SMTP send | Wrap HF/GitHub GETs (transient 5xx/429) and per-recipient SMTP sends. Do NOT wrap Anthropic calls; the SDK already retries. |
| `smtplib`, `email.message.EmailMessage`, `email.utils` (stdlib) | Python 3.14 | Build and send MIME mail | Always. `EmailMessage` with default policy encodes Korean subject/display names (RFC 2047) and UTF-8 bodies correctly. Use `set_content(plain)` then `add_alternative(html, subtype="html")`. `email.utils.formataddr(("AI 주간 모델 브리프", sender))`, `make_msgid()`, `formatdate(localtime=True)`. |
| `csv` (stdlib) | Python 3.14 | Read `email,name` subscriber list | Always. Open with `encoding="utf-8-sig"`: Excel on Korean Windows/Mac saves a BOM that otherwise corrupts the first header (`﻿email`). |
| `zoneinfo` (stdlib) | Python 3.14 | KST date math | Compute the target ISO week in `Asia/Seoul`, never runner-local UTC. Needs no `tzdata` package on ubuntu runners. |
| python-dotenv | 1.2.4 | Load `.env` for local runs | Dev-only convenience. In Actions, secrets arrive as env vars. |
| respx | latest | Mock httpx in tests | Unit-test the HF fetch/rank/enrich logic against saved JSON fixtures (no network in CI tests). |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| ruff 0.17.3 | Lint + format | Single tool; `ruff check` + `ruff format` in CI. |
| pytest 9.2.0 | Tests | Fixture-driven: saved `daily_papers` JSON, saved Claude parsed outputs, golden rendered HTML. |
| pyright (or mypy) | Type check | Catches anthropic 2.x type changes (`MessageParam` is now a union; `MessageParam(...)` call raises `TypeError`). |
| `--dry-run` / `--to` CLI flags (build yourself) | Safe manual testing | `workflow_dispatch` inputs: `dry_run` (render HTML as artifact, no send), `week` override, `to` override (send only to the author). Essential because the user chose no human review step. |
| Litmus/Email on Acid (optional) or real sends | Rendering QA | No Korean-client coverage in those tools for Naver; send real test mails to a Naver and a Gmail inbox. |

## Verified Data-Source Details (HF Papers API)

Probed live on 2026-11-02 (`week=2026-W44`). These endpoints are unauthenticated and public.

**1. Weekly list**
```
GET https://huggingface.co/api/daily_papers?week=2026-W44&limit=100&p=0
```
- Params (confirmed in `huggingface_hub.HfApi.list_daily_papers` source + live): `date=YYYY-MM-DD`, `week=YYYY-Www` (ISO week), `month=YYYY-MM`, `sort=publishedAt|trending`, `p` (0-based page), `limit` (100 worked; library default 50), `submitter`.
- Observed: `week=2026-W44` returned items with `submittedOnDailyAt` 2026-10-26..2026-10-30 (Mon-Fri), 100 per page, a second page (`p=1`) existed. Default order came back upvotes-descending, but the library docstring says the default is `publishedAt`. **Paginate until an empty page and sort by `paper.upvotes` yourself.** `sort=trending` is NOT weekly upvotes (returned old papers), do not use it.
- Item shape: top-level `{paper, publishedAt, title, summary, thumbnail, numComments, submittedBy, organization?, mediaUrls?}`.
- `paper` fields: `id` (arXiv id, e.g. `2610.37381`), `title`, `summary` (abstract), `upvotes`, `publishedAt`, `submittedOnDailyAt`, `authors[]`, `ai_summary`, `ai_keywords[]` (99/100), `githubRepo` + `githubStars` (67/100), `projectPage` (63/100), `organization` (79/100), `discussionId`.
- Upvotes keep moving (153 -> 156 within minutes). Rank once at run time and record the snapshot.

**2. Paper detail (linked artifacts)**
```
GET https://huggingface.co/api/papers/{arxiv_id}
```
Adds `linkedModels[]`, `numTotalModels`, `linkedDatasets[]`, `linkedSpaces[]`, `numTotalSpaces`.

**3. Linked repos (compact)**
```
GET https://huggingface.co/api/arxiv/{arxiv_id}/repos   ->  {"models": [...], "datasets": [...], "spaces": [...]}
```
Each model entry includes `id`, `tags` (contains `license:apache-2.0`, `arxiv:...`), `pipeline_tag`, `library_name`, `downloads`, `likes`.

**4. Model detail (license, gating, size)**
```
GET https://huggingface.co/api/models/{repo_id}
```
Fields: `cardData.license`, `tags` (`license:*`), `gated` (false/"auto"/"manual"), `pipeline_tag`, `safetensors.total` (parameter count when present, may be null), `downloads`, `likes`.

**5. GitHub license (code repos)**
```
GET https://api.github.com/repos/{owner}/{repo}/license
```
Use `Authorization: Bearer ${{ github.token }}` in Actions (60 req/h unauthenticated vs 1,000+ authenticated).

**Target-week computation (Monday 08:00 KST run):**
```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
y, w, _ = (now_kst - timedelta(days=7)).isocalendar()
week_param = f"{y}-W{w:02d}"   # previous Mon-Sun ISO week
```
Allow a `WEEK` env/dispatch override for backfills and reruns.

## Claude API Usage Pattern

```python
import anthropic
from pydantic import BaseModel
from typing import Literal

class PaperAnalysis(BaseModel):
    ai_type: Literal["LLM", "비전", "멀티모달", "음성", "에이전트", "이미지/비디오 생성", "로보틱스", "기타"]
    commercial_use: Literal["가능", "불가", "확인 필요"]
    commercial_use_basis: str          # license evidence or "근거 없음"
    poc_ready: Literal["가능", "제한적", "불가", "확인 필요"]
    poc_basis: str                     # weights/code/demo evidence
    claude_gpt_applicable: Literal["가능", "부분 가능", "불가", "확인 필요"]
    claude_gpt_basis: str
    one_line_summary: str
    use_idea: str
    license: str | None
    weights_open: bool | None
    code_open: bool | None
    hf_model_url: str | None
    difficulty: Literal["낮음", "중간", "높음", "확인 필요"]
    gpu_requirement: str

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
resp = client.messages.parse(
    model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"),
    max_tokens=8000,
    system=SYSTEM_PROMPT,                       # stable -> cacheable
    messages=[{"role": "user", "content": evidence_block}],
    output_format=PaperAnalysis,
)
if resp.stop_reason == "refusal": ...          # check before reading output
analysis = resp.parsed_output
```

Rules that matter (from the Anthropic docs, API version 2026-10-21):
- **Do not send `temperature`, `top_p`, `top_k`.** They return 400 on API version `2026-10-21`, which `anthropic` 2.x sends by default.
- **No `thinking: {"type": "disabled"}`** on Sonnet 5.5 (400). Leave thinking default (adaptive). Control cost/depth with `output_config={"effort": "medium"}`; Sonnet 5.5 default effort is `high`.
- **No assistant prefill, no forced `tool_choice`** (both 400). Structured outputs replace both.
- **Check `stop_reason == "refusal"`** before reading content. Optionally enable server-side fallback (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`); this needs the beta namespace. Whether `client.beta.messages.parse` accepts it alongside `output_format` is **unverified** (MEDIUM): verify in the LLM phase, or catch refusal and retry once on `claude-opus-5-5`.
- Combining `output_format=` with `output_config={"effort": ...}` in one `parse()` call is MEDIUM confidence; verify in the LLM phase.
- **Feed evidence, do not let the model guess.** Pre-fetch HF/GitHub license, `gated`, `safetensors.total`, linked repos, abstract, and pass them in the prompt. The model judges from evidence and outputs `"확인 필요"` when evidence is missing. This is cheaper and more deterministic than giving Claude `web_fetch_20260209`. Add web fetch later only if evidence gaps are common.
- Call pattern: 10 per-paper calls (sequential is fine, ~1-2 min) + 1 trend call over the 10 parsed results. Message Batches (50% off, async up to 24h) is not worth the complexity at this volume.

## GitHub Actions Workflow Skeleton

```yaml
name: weekly-newsletter
on:
  schedule:
    - cron: "0 8 * * 1"
      timezone: "Asia/Seoul"        # IANA tz support, GitHub changelog 2026-03-26
  workflow_dispatch:
    inputs:
      dry_run: { type: boolean, default: true }
      week:    { type: string, required: false }   # e.g. 2026-W44
      to:      { type: string, required: false }   # override recipients
concurrency: { group: newsletter, cancel-in-progress: false }
permissions: { contents: read }
jobs:
  send:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10
        with: { python-version: "3.14", enable-cache: true }
      - run: uv sync --frozen
      - run: uv run python -m newsletter
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          SUBSCRIBERS_CSV: ${{ secrets.SUBSCRIBERS_CSV }}
          GITHUB_TOKEN: ${{ github.token }}
          DRY_RUN: ${{ inputs.dry_run || 'false' }}
          WEEK: ${{ inputs.week }}
          TO_OVERRIDE: ${{ inputs.to }}
      - uses: actions/upload-artifact@v7     # rendered HTML + JSON snapshot for audit
        if: always()
        with: { name: newsletter, path: out/ }
```
Fallback if the `timezone:` key misbehaves: `cron: "0 23 * * 0"` (UTC Sunday 23:00 = Monday 08:00 KST; Korea has no DST).

## Installation

```bash
# Core
uv init --python 3.14
uv add "anthropic>=2.3,<3" "pydantic>=2.14,<3" "httpx>=0.28,<0.29" "jinja2>=3.1.6,<4" "css-inline>=0.23,<0.24" "tenacity>=9.2,<10"

# Dev
uv add --dev ruff pytest respx pyright python-dotenv
```

Note: Node.js is not installed on the author's Mac. The Python choice means local dev needs only `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`), and uv installs Python 3.14 itself.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Python | Node.js/TypeScript (`@anthropic-ai/sdk` 1.x, `nodemailer`, `mjml`) | If the team wants real MJML (Node-only reference implementation) or already lives in TS. Downside here: author has no Node locally; Python stdlib already covers SMTP/CSV/MIME. |
| httpx + own Pydantic models | `huggingface_hub` 2.4.0 `HfApi.list_daily_papers(week=...)` / `paper_info()` | If you also need authenticated Hub calls. It wraps the same endpoint but returns `PaperInfo` objects whose fields may lag the raw JSON (e.g. `githubRepo`, `linkedModels`); raw JSON is easier to fixture-test. |
| `claude-sonnet-5-5` | `claude-opus-5-5` | If license/PoC/applicability judgments are shallow. Cost difference at 11 calls/week is under ~$1. |
| `claude-sonnet-5-5` | `claude-haiku-5-5` ($0.10 / $0.50) | Not recommended for the analytical fields; acceptable only for the trend summary if cost ever matters. |
| Jinja2 hand-built tables + css-inline | MJML (Node CLI via `npx mjml` on the runner, or `mjml` 0.12 Python port) | If the design needs complex responsive columns. The Python port (`mjml-python`) supports a subset of MJML; the Node CLI adds a second toolchain. For a single-column newsletter with cards, hand-written tables are simpler and fully controllable. |
| css-inline | premailer 3.10.0 | Never for new code: last release 2021-08-02, unmaintained, slower (lxml + cssutils). |
| stdlib smtplib | `yagmail`, `redmail` | Only for convenience. They add dependencies over a ~30-line stdlib function and hide MIME details you need for Korean headers. |
| Gmail SMTP + app password | Gmail API (OAuth2), Resend/SES/Postmark | When list grows past Gmail limits (~500 recipients/day for consumer accounts), or deliverability to Naver suffers. Out of scope for v1 per PROJECT.md. |
| `schedule` + `timezone: Asia/Seoul` | UTC cron `0 23 * * 0` | If the newer `timezone` key causes validation issues. Equivalent because KST has no DST. |
| GitHub Secret for subscriber CSV | Private repo with `subscribers.csv` committed | If the subscriber list grows beyond a comfortable secret size (secrets max 48 KB) or must be edited often. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `anthropic` 0.x / 1.x | Send API version `2023-06-01`; 1.x->2.x changed `MessageParam` typing and auth header (`Authorization: Bearer`). Starting fresh on 2.x avoids a migration. | `anthropic>=2.3,<3` |
| `temperature=0` for "consistency" | 400 error on API version `2026-10-21` (SDK 2.x). | Structured outputs + explicit rubric in the system prompt. |
| `output_format={...}` raw dict on `messages.create`, or the old `output_format` request param | Deprecated; use `output_config={"format": {...}}` for raw schemas. | `messages.parse(output_format=PydanticModel)` |
| Assistant prefill (`{"role":"assistant","content":"{"}`) or forced `tool_choice` to get JSON | Both return 400 on current models. | Structured outputs. |
| Date-suffixed model ids (`claude-sonnet-5-5-2026xxxx`) or hardcoded old ids | Invalid / stale. | Exact `claude-sonnet-5-5`, configurable by env. |
| `sort=trending` on daily_papers | Returns papers from other weeks; not the weekly upvote ranking. | `week=` + client-side sort by `paper.upvotes`. |
| Scraping `huggingface.co/papers/week/...` HTML | Fragile; JSON API exists and is what the HF client library uses. | `/api/daily_papers?week=` |
| premailer | Unmaintained since 2021. | css-inline |
| Web fonts as the primary font (`@font-face` Pretendard etc.) | Gmail and Naver strip/ignore `@font-face`; text falls back unpredictably. | `font-family: Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', '맑은 고딕', sans-serif;` inline; images for any headline lettering that must match Figma exactly. |
| Flexbox/grid, `<div>` layout, CSS variables, external CSS | Unsupported or stripped in Gmail/Naver. | Nested `<table role="presentation">`, fixed width 600-680px, inline styles. |
| Account password for SMTP / "less secure apps" | Google no longer accepts plain account passwords for SMTP. | 2-Step Verification + 16-char app password in `GMAIL_APP_PASSWORD` secret. |
| One email with all subscribers in `To:`/`Cc:` | Leaks addresses; breaks personalized greeting. | One message per subscriber, same SMTP connection, short sleep between sends. |
| Committing `subscribers.csv` to a public repo | PII exposure. | `SUBSCRIBERS_CSV` secret (or private repo). Never `print` the CSV or addresses in logs. |
| Wrapping Anthropic calls in tenacity | Double retry storms; SDK already retries 429/5xx. | Tune `anthropic.Anthropic(max_retries=4, timeout=120)`. |

## Stack Patterns by Variant

**If the repo is public:**
- Store subscriber CSV in `SUBSCRIBERS_CSV` secret (multi-line value works; base64 if quoting gets awkward).
- Note: public repo scheduled workflows are auto-disabled after 60 days without repo activity. Add a keepalive (e.g. commit the weekly JSON snapshot, or a keepalive action) or use a private repo.

**If the repo is private:**
- `subscribers.csv` may live in the repo. Free-tier Actions minutes (2,000/month) far exceed a ~5 min weekly job.

**If the Figma design depends on a custom Korean font for headings:**
- Render those headings as images (PNG, hosted via raw GitHub/Pages URL) with `alt` text; keep body text as live text with system font fallbacks.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| anthropic 2.3.0 | Python >=3.10, pydantic 2.x | Uses `httpx2` (fork) internally; no conflict with app-level `httpx` 0.28. Sends `anthropic-version: 2026-10-21`. Licensed Apache-2.0 from 2.0. |
| anthropic 2.x | `claude-sonnet-5-5`, `claude-opus-5-5` | Sampling params removed from SDK types. `MessageParam(...)` constructor raises `TypeError`; write messages as dicts. |
| css-inline 0.23.1 | Python >=3.10 | Prebuilt wheels; confirm 3.14 wheel resolves in `uv lock` (expected). |
| pydantic 2.14.2 | Python >=3.10 | Required by anthropic `messages.parse`. |
| huggingface_hub 2.4.0 | Python >=3.10 | Only if chosen over raw httpx. |
| actions/checkout v7.0.1, actions/setup-python v7.1.0, astral-sh/setup-uv v10.3.3, actions/upload-artifact v7.0.2 | ubuntu-latest | Latest major tags as of 2026-11-02. |

## Sources

- Live probe of `https://huggingface.co/api/daily_papers?week=2026-W44` (pages 0-1, `sort=trending`, `date=`), `/api/papers/{id}`, `/api/arxiv/{id}/repos`, `/api/models/{id}` on 2026-11-02 — field names, pagination, ordering (HIGH).
- `huggingface_hub` main `hf_api.py` `list_daily_papers` source — params `date/week/month/sort/p/limit/submitter` (HIGH).
- PyPI JSON API, 2026-11-02 — versions: anthropic 2.3.0, jinja2 3.1.6, css-inline 0.23.1, premailer 3.10.0 (2021), pydantic 2.14.2, httpx 0.28.1, tenacity 9.2.1, huggingface_hub 2.4.0, python-dotenv 1.2.4, uv 0.13.6, ruff 0.17.3, pytest 9.2.0, mjml 0.12.0 (HIGH).
- GitHub Releases API — actions/checkout v7.0.1, actions/setup-python v7.1.0, astral-sh/setup-uv v10.3.3 (HIGH).
- endoflife.date — Python 3.14.10 / 3.15.2 status (HIGH).
- Anthropic `claude-api` skill reference (model table cached 2026-10-06; Python structured outputs) — model ids/pricing, `messages.parse`, thinking/effort rules, refusal fallbacks (HIGH).
- https://platform.claude.com/docs/en/api/migration-2026-10-21 (Python) — sampling params removed, SDK 2.0.0 sends 2026-10-21, `MessageParam` union, Bearer auth (HIGH).
- https://github.com/anthropics/anthropic-sdk-python CHANGELOG — 2.3.0 dated 2026-10-23 (HIGH).
- https://github.blog/changelog/2026-03-26-github-actions-late-march-2026-updates — IANA `timezone` field on cron schedules (HIGH; exact YAML placement confirmed only as "alongside your cron expression", so keep the UTC fallback).
- Gmail SMTP app password guides: https://docs.n8n.io/integrations/builtin/credentials/send-email/gmail , https://help.wpcompress.com/en-us/article/using-google-workspace-gmail-or-g-suite-for-smtp-p88evp/ — 2SV + app password, smtp.gmail.com 465/587 (MEDIUM; third-party, consistent).
- Email CSS: https://developers.google.cn/workspace/gmail/design/css?hl=ko , https://www.braze.com/docs/ko/user_guide/message_building_by_channel/email/css_inline/ , https://velog.io/@kimtaeil6/pub-email-template — inline CSS needed; Naver `<style>` support undocumented (MEDIUM; must be validated by real sends to Naver).

---
*Stack research for: automated weekly AI-paper newsletter (HF Papers -> Claude -> Gmail SMTP on GitHub Actions)*
*Researched: 2026-11-02*
