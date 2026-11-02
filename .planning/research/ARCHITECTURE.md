# Architecture Research

**Domain:** Scheduled batch pipeline: content fetch, LLM enrichment, HTML email render, SMTP send (weekly AI-model newsletter on GitHub Actions)
**Researched:** 2026-11-02
**Confidence:** HIGH for pipeline shape, HF API and Actions behavior (probed live / well documented); MEDIUM for email-client CSS rules; LOW for Naver Mail specifics (no authoritative source found; must be verified by test sends)

## Standard Architecture

This is a **linear, stage-gated batch pipeline** with no server, no database and no UI. Each stage reads the previous stage's JSON artifact and writes its own. The repo itself is the datastore (an `archive/` folder per issue). GitHub Actions is the scheduler and runtime. This is the standard shape for "cron newsletter" projects, and it is the right one here: one run per week, about 10 items, 1 to a few hundred recipients.

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│ TRIGGER  (GitHub Actions)                                            │
│   schedule: weekly cron          workflow_dispatch: mode=preview|test|send, week=YYYY-Www │
└───────────────┬──────────────────────────────────────────────────────┘
                │  resolve ISSUE ID = previous ISO week in KST (e.g. 2026-W44)
                v
┌──────────────────────────────────────────────────────────────────────┐
│ CONTENT PIPELINE  (pure, deterministic given inputs; no secrets except LLM key) │
│                                                                      │
│  [1 Fetch] ──> [2 Select] ──> [3 Enrich] ──> [4 Analyze] ──> [5 Render] │
│  HF daily_papers  Top10 by     HF arxiv->repos   Claude, schema-     Jinja2 + │
│  week=YYYY-Www    upvotes      licenses, GitHub  validated JSON,     CSS inline│
│                                repo license      + weekly trend               │
│     │              │              │                 │                 │      │
│     v              v              v                 v                 v      │
│  raw.json     selected.json   enriched.json     issue.json       email.html │
└───────────────┬──────────────────────────────────────────────────────┘
                │  all written to archive/<ISSUE ID>/  (cached: re-run skips done stages)
                v
┌──────────────────────────────────────────────────────────────────────┐
│ DELIVERY  (only in mode=test|send; needs SMTP + subscriber secrets)   │
│  [6 Personalize per recipient] ──> [7 SMTP send, one msg each] ──> [8 Ledger] │
│        name -> "홍길동님"                smtp.gmail.com:465             sent.json │
└───────────────┬──────────────────────────────────────────────────────┘
                v
┌──────────────────────────────────────────────────────────────────────┐
│ PERSISTENCE                                                          │
│   git commit archive/<ISSUE ID>/*  (snapshot + ledger)   │  upload-artifact email.html │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `issue_id` resolver | Turn "now" (or a `week` input) into the target issue key. Previous ISO week, computed in Asia/Seoul. Never derived from run start time alone, so a delayed cron still targets the right week. | `zoneinfo` + `date.isocalendar()` |
| Fetcher | Pull all papers for the week from HF. Paginate. Save raw response unmodified. | `GET https://huggingface.co/api/daily_papers?week=2026-W44&limit=100&p=N` (verified live: returns list; `paper.upvotes`, `paper.githubRepo`, `paper.projectPage`, `paper.ai_keywords`, `paper.githubStars`; pagination via `p`) |
| Selector | Dedupe by arXiv id, sort by `paper.upvotes` desc, take 10. Pure function. | Plain Python, unit-tested on fixture |
| Enricher | Collect *evidence* per paper: linked HF models/datasets/spaces, their `license:*` tags, `pipeline_tag`, param size hints, GitHub repo license and stars. No judgments here. | `GET /api/arxiv/{arxiv_id}/repos` (verified live: returns `{"models":[...]}` with `tags` incl. `license:apache-2.0`); GitHub `GET /repos/{owner}/{repo}/license` with `GITHUB_TOKEN` |
| Analyzer | Turn evidence into the newsletter fields (AI 종류, 상업적 사용, PoC, Claude/GPT 적용, 요약, 활용 아이디어, 난이도/GPU) plus 주간 트렌드 총평. Must output "확인 필요" when evidence is missing. | Anthropic SDK, one call per paper + one trend call, JSON-schema constrained output, Pydantic validation, retry on validation failure |
| Schema (`Issue` model) | The single contract between content pipeline and template. Every downstream piece depends on it. | Pydantic models; `issue.json` is the serialized form |
| Renderer | `issue.json` + template to email-safe HTML and a plain-text alternative. Inline CSS. Size check (Gmail clips at ~102 KB). | Jinja2 template, then a CSS inliner (Python `premailer` or `css-inline`) |
| Personalizer | Per-recipient render of the greeting only. HTML-escape the name. | Jinja2 variable `{{ recipient_name }}` rendered per recipient |
| Sender | Build MIME `multipart/alternative` (text + HTML), one message per recipient, send over SMTP SSL. Throttle. | `smtplib.SMTP_SSL("smtp.gmail.com", 465)` + `email.message.EmailMessage` |
| Ledger | Record which recipients received which issue; refuse to resend. | `archive/<ISSUE ID>/sent.json`, committed to repo |
| Workflow | Schedule, mode selection, secrets injection, artifact upload, commit-back, concurrency lock. | `.github/workflows/weekly.yml` |

## Recommended Project Structure

Python is recommended for this architecture (the stack researcher owns the final call). Reasons that matter architecturally: no local Node.js on the user's Mac, `actions/setup-python` is standard, and the whole pipeline needs only the standard library plus `anthropic`, `httpx`/`requests`, `pydantic`, `jinja2` and an inliner. Avoid MJML; it is Node-only and adds a toolchain for a single template.

```
.
├── .github/workflows/
│   └── weekly.yml              # cron + workflow_dispatch(mode, week), concurrency lock
├── newsletter/
│   ├── __main__.py             # CLI: python -m newsletter run --mode preview|test|send [--week 2026-W44] [--force-stage X]
│   ├── issue_id.py             # previous ISO week in KST
│   ├── schema.py               # Pydantic: Paper, Evidence, Analysis, Issue (THE contract)
│   ├── stages/
│   │   ├── fetch.py            # HF daily_papers -> raw.json
│   │   ├── select.py           # raw -> selected.json (Top 10)
│   │   ├── enrich.py           # selected -> enriched.json (HF repos, licenses, GitHub)
│   │   ├── analyze.py          # enriched -> issue.json (Claude)
│   │   └── render.py           # issue -> email.html + email.txt
│   ├── delivery/
│   │   ├── subscribers.py      # parse CSV from env/secret or file
│   │   ├── send.py             # SMTP, per-recipient MIME
│   │   └── ledger.py           # sent.json read/write, idempotency checks
│   └── store.py                # archive/<id>/ paths, "stage already done?" checks
├── prompts/
│   ├── analyze_paper.md        # system + instructions (Korean output, "확인 필요" rule)
│   └── weekly_trend.md
├── templates/
│   ├── email.html.j2           # table layout, written from Figma tokens
│   ├── email.txt.j2            # plain-text alternative
│   └── tokens.py / tokens.json # colors, font sizes, spacing pulled from Figma
├── archive/
│   └── 2026-W44/
│       ├── raw.json
│       ├── selected.json
│       ├── enriched.json
│       ├── issue.json
│       ├── email.html          # rendered with placeholder name, viewable "web version"
│       └── sent.json           # ledger (recipient hashes, timestamps, message ids)
├── tests/
│   ├── fixtures/               # one frozen week of raw/enriched/issue JSON
│   ├── test_select.py
│   ├── test_render.py          # snapshot + size + no-<style>-dependency checks
│   └── test_ledger.py
├── subscribers.example.csv     # email,name header only; real list never committed
└── pyproject.toml / requirements.txt
```

### Structure Rationale

- **`stages/` one file per stage, each `input JSON -> output JSON`:** any stage can be re-run alone, debugged from the archived input, and tested with fixtures. This is the main debugging tool for an unattended pipeline.
- **`schema.py` separate and first:** template work (Figma -> HTML) and LLM work can proceed in parallel against a fixture `issue.json` once the schema exists.
- **`delivery/` separate from `stages/`:** the content pipeline never touches subscriber data or SMTP credentials. Preview mode can run the whole content path with no delivery secrets present.
- **`archive/` in the repo:** free storage, free history, readable diffs of what was sent each week, and a weekly commit keeps the repo "active" (GitHub disables scheduled workflows in repos with no activity for 60 days).
- **`prompts/` as files:** prompt edits show up as clean diffs and do not require code changes.

## Architectural Patterns

### Pattern 1: Stage-gated pipeline with on-disk checkpoints

**What:** Each stage writes `archive/<issue>/<stage>.json`. On start, a stage checks whether its output already exists and skips unless `--force-stage` is passed.
**When to use:** Always here. It provides re-run safety, cost control (Claude is not re-billed on re-run), and post-mortem debugging.
**Trade-offs:** Slightly more code than one script. Stale checkpoints can hide prompt changes; `--force-stage analyze` covers that.

**Example:**
```python
def run_stage(name, issue_dir, fn, inp, force=False):
    out = issue_dir / f"{name}.json"
    if out.exists() and not force:
        return Model.model_validate_json(out.read_text())
    result = fn(inp)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result
```

### Pattern 2: Evidence first, then judgment (LLM grounding)

**What:** The enricher gathers facts (license tags, repo existence, model sizes) with no LLM. The analyzer receives the facts and must cite them; if a field has no supporting evidence, the schema forces the value `"확인 필요"`.
**When to use:** For every "상업적 사용 가능" / "PoC 가능" field. These are the core value claims, and an LLM guessing a license from a paper abstract is the top correctness risk.
**Trade-offs:** More API calls to HF and GitHub (about 10 to 30 per run; trivial). Some papers will legitimately show "확인 필요".

**Example:**
```python
class CommercialUse(BaseModel):
    verdict: Literal["가능", "제한적", "불가", "확인 필요"]
    license: str | None          # e.g. "apache-2.0" from HF tag / GitHub
    evidence_url: HttpUrl | None # model card or LICENSE file
    reason_ko: str
# Post-validation rule: verdict != "확인 필요" requires license and evidence_url.
```

### Pattern 3: Schema-constrained LLM output with validate-and-retry

**What:** Call Claude with a JSON schema (structured outputs or a forced tool call), parse into Pydantic, and on validation failure retry once with the validation error appended. One call per paper keeps failures isolated. A final call over the 10 analyses produces 주간 트렌드 총평.
**When to use:** All LLM output that feeds a template. Free-form markdown from the LLM breaks layouts.
**Trade-offs:** 11 calls per week instead of 1. Cost is negligible at this volume, and a single bad item does not sink the issue.

### Pattern 4: Mode switch instead of separate workflows

**What:** One CLI and one workflow with `mode`:
- `preview`: run content stages, render, upload `email.html` as an Actions artifact. No SMTP secrets read, nothing sent, no ledger.
- `test`: same as preview, then send only to `TEST_RECIPIENT` (secret). Ledger not written.
- `send`: full run. Ledger enforced.

The schedule trigger always uses `send`. `workflow_dispatch` defaults to `preview`, so a manual click can never mass-send by accident.
**Trade-offs:** None meaningful. This is the dry-run/preview requirement in its cheapest form.

**Example (workflow excerpt):**
```yaml
on:
  schedule:
    - cron: "7 22 * * 0"        # Sun 22:07 UTC = Mon 07:07 KST; off the top of the hour, with slack for delay
  workflow_dispatch:
    inputs:
      mode: { type: choice, options: [preview, test, send], default: preview }
      week: { type: string, required: false, description: "e.g. 2026-W44; blank = previous week" }

concurrency:
  group: newsletter
  cancel-in-progress: false      # never kill a run mid-send

permissions:
  contents: write                # commit archive/ back

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: python -m newsletter run --mode "${{ inputs.mode || 'send' }}" --week "${{ inputs.week }}"
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          SUBSCRIBERS_CSV: ${{ secrets.SUBSCRIBERS_CSV }}
          TEST_RECIPIENT: ${{ secrets.TEST_RECIPIENT }}
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: email-preview, path: archive/**/email.html }
      - name: Commit archive
        if: always()
        run: |
          git config user.name "newsletter-bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add archive/
          git diff --cached --quiet || git commit -m "archive: issue ${{ inputs.week || 'weekly' }}"
          git push
```
Note on cron time: the project spec says `0 23 * * 0` (exactly 08:00 KST). Scheduled runs are best-effort and the top of the hour is the busiest slot; community reports show delays from minutes to several hours and occasional dropped runs. Scheduling at an odd minute about an hour early (e.g. `7 22 * * 0`) makes "arrives by Monday morning" far more likely. The roadmap should decide whether "exactly 08:00" or "by 08:00" matters. If exact timing matters, the fallback is an external scheduler calling `workflow_dispatch`.

### Pattern 5: Ledger-based idempotency (two layers)

**What:**
1. **Issue-level guard:** at start of `send`, if `archive/<issue>/sent.json` exists and lists every current subscriber, exit 0 with "already sent".
2. **Recipient-level guard:** before each SMTP send, skip recipients already in the ledger. After each successful send, append to the ledger and flush to disk immediately. The commit step runs with `if: always()`, so a crash mid-list still commits partial progress, and a re-run sends only to the remainder.
3. **Concurrency group** prevents two runs (cron + manual) from racing on the same ledger.

Store a SHA-256 of the lowercase email in the ledger instead of the address, so the committed file contains no PII.
**Trade-offs:** If SMTP accepts a message and the job dies before the ledger write (a narrow window), that one recipient may get a duplicate on re-run. That is acceptable at this scale. Do not add IMAP "Sent folder" checks.

**Stale-issue guard:** if the run starts more than about 2 days after the issue's Monday (for example, a manual re-run the next week), `send` mode refuses unless `--allow-late` is passed. This prevents mailing last week's issue by mistake.

### Pattern 6: Render once, personalize per recipient

**What:** Render the full issue HTML once, with the greeting as the only per-recipient variable. Per recipient, render the greeting and inline it. With Jinja2 this means rendering the template per recipient with `recipient_name` set and autoescape on. That is cheap at this scale.
**Why:** The archived `email.html` (rendered with a neutral greeting such as "구독자님") is byte-identical to what recipients got apart from the name. It doubles as the preview and the "web version".

## Data Flow

### Weekly Run Flow

```
cron (Sun ~22:07 UTC)  or  manual dispatch(mode, week)
    v
issue_id = prev ISO week (Asia/Seoul)            e.g. 2026-W44  (Mon 10-26 .. Sun 11-01)
    v
fetch: HF /api/daily_papers?week=2026-W44 (paginate p=0..)   -> raw.json
    v
select: dedupe, sort paper.upvotes desc, top 10             -> selected.json
    v
enrich: per paper
    HF /api/arxiv/{id}/repos -> models[].tags license:*, pipeline_tag, safetensors size
    GitHub /repos/{o}/{r}/license (if paper.githubRepo)        -> enriched.json
    v
analyze: Claude x10 (per paper, schema) + Claude x1 (trend)  -> issue.json
    v
render: Jinja2 -> inline CSS -> size/lint checks             -> email.html, email.txt
    v
[mode=preview] upload artifact, stop
[mode=test]    send to TEST_RECIPIENT, stop
[mode=send]    ledger check -> for each subscriber: personalize -> SMTP -> ledger append
    v
commit archive/2026-W44/*  (+ upload artifact)
```

### Secrets and Sensitive Data Flow

```
GitHub Secrets ──env──> process memory only
  ANTHROPIC_API_KEY     -> analyze stage
  GMAIL_USER / GMAIL_APP_PASSWORD -> send stage
  SUBSCRIBERS_CSV       -> subscribers.py (parsed from env string, never written to disk or logged)
  TEST_RECIPIENT        -> test mode
GITHUB_TOKEN (auto)     -> GitHub license API + git push
```

Rules:
- Never `print` a recipient address or name in logs. Log counts and email hashes only. Actions masks secret values, but masking of multi-line secrets is unreliable when individual lines are echoed. Treat the CSV as never-log.
- Use `GITHUB_TOKEN`, not a PAT, for push and the GitHub API.
- Do not read SMTP or subscriber secrets in `preview` mode. Code should only touch them inside `delivery/`.

### Where the Subscriber CSV Lives (decision)

**Recommended: GitHub Secret `SUBSCRIBERS_CSV`** containing the raw CSV text (`email,name` lines), with `subscribers.example.csv` committed for format reference.

| Option | Verdict | Why |
|--------|---------|-----|
| Secret `SUBSCRIBERS_CSV` | **Use** | Works whether the repo is public or private. Never enters git history. Editing means pasting the new CSV in Settings > Secrets. Size limit (48 KB) fits thousands of rows. |
| CSV committed in a private repo | Acceptable fallback | Easier editing (a commit), but PII sits in git history permanently and leaks if the repo is ever made public or forked. |
| CSV in a public repo | Never | PII exposure. |
| Separate private "data" repo checked out with a PAT | Overkill | Adds a PAT secret to rotate for one CSV. |

Repo visibility: a private repo is still recommended for this project. The archive is harmless, but private keeps prompts and history out of view. GitHub's free tier gives private repos 2,000 Actions minutes per month, and this job uses about 5 minutes per week.

### Key Data Flows

1. **Content flow:** HF -> evidence -> Claude -> `issue.json` -> HTML. Strictly one-directional; no stage reads a later stage's output.
2. **Delivery flow:** `email.html` + secret CSV -> per-recipient messages -> ledger. Delivery depends on content, never the reverse.
3. **Design flow (one-time, offline):** Figma -> tokens + layout -> hand-written `email.html.j2`. This does not run in the pipeline (see below).

## Figma Design to Email-Safe HTML

Do not convert the Figma output directly into the email. Figma's code export and Figma MCP `get_design_context` produce web markup (div/flex, often React + Tailwind), and Gmail and Naver will break it. Use Figma as the spec and hand-build the template.

**Process:**
1. **Design the web version in Figma at email width.** Use a frame 600 to 640 px wide, not a 1200 px "desktop" page. Email clients render a fixed-width centered column on desktop; the "web-type" design should be a single column with an optional 2-column header/meta row at most.
2. **Constrain the design to email-buildable primitives** while designing: stacked sections, solid background colors, text, simple bordered "badge" cells (상업적 사용 O/X, PoC O/X, Claude/GPT O/X), images only where essential. Avoid overlapping layers, gradients, shadows, background images and custom fonts as load-bearing elements.
3. **Extract tokens** (colors, font sizes and line heights, spacing, radii, badge styles) from Figma via MCP (`get_design_context` / `get_variable_defs`) into `templates/tokens.json`. Reference the tokens from the Jinja template.
4. **Hand-write the template** with these rules:
   - Outer `<table role="presentation" width="100%">` with an inner centered `<table width="600">` and `style="max-width:600px;width:100%"`.
   - Layout only with nested tables, `<td>` padding and `align`/`valign`. No flexbox, grid, `position`, `float` or CSS variables.
   - All styles inline (author with a small `<style>` block, then inline at build time). Keep a minimal `<style>` only for progressive enhancement such as a mobile `@media` rule; the email must look correct with `<style>` stripped.
   - Fonts: Figma's font (likely Pretendard or similar) will not load in Gmail or Naver. Use a stack such as `font-family: Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', '맑은 고딕', 'Noto Sans KR', sans-serif;`.
   - Badges: `<td bgcolor="#..." style="background-color:#...;border-radius:4px;padding:2px 8px">`. A square corner fallback is fine.
   - Images: absolute HTTPS URLs (for example, raw GitHub or GitHub Pages), explicit `width`/`height`, `alt`, `display:block`. Prefer zero images in v1 apart from an optional logo.
   - Links: absolute URLs to the HF paper, HF model and GitHub repo.
   - Include `<meta charset="utf-8">`, `lang="ko"` and a hidden preheader `<div>`.
   - Total HTML under about 90 KB to stay below Gmail's ~102 KB clipping threshold. Ten items with inline styles fit, but repeated inline styles add up, so the renderer should assert the size.
5. **Plain-text alternative** (`email.txt.j2`) in the same message improves deliverability and readability in text-only views.
6. **Verify** with test-mode sends to a Gmail address and a Naver address (the actual subscriber is on naver.com), on desktop web and mobile app. No public reference documenting Naver Mail's CSS support was found, so assume "inline styles + tables only" until a test send proves otherwise.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 to 100 recipients | As designed. Sequential SMTP with a short sleep (about 1 s) between messages. |
| 100 to 400 | Same code. Watch Gmail's daily sending limit (about 500 per day for consumer accounts, lower for new accounts or app-password SMTP in practice). Add `List-Unsubscribe` and a reply-to-unsubscribe instruction. |
| 400+ | Swap `delivery/send.py` for an ESP (SES, Resend, Postmark) with SPF/DKIM on your own domain. Only the sender module changes, because delivery is isolated behind one function. |

### Scaling Priorities

1. **First bottleneck:** Gmail sending limits and spam filtering of a consumer Gmail account sending identical HTML. This is mitigated by low volume and a text part. The real fix is an ESP; keep `send()` behind an interface.
2. **Second bottleneck:** reliability of Actions scheduling. Mitigate with the off-peak minute and early schedule; escalate to an external dispatcher only if runs are missed in practice.

## Anti-Patterns

### Anti-Pattern 1: One monolithic script, fetch-to-send in a single function

**What people do:** `main()` fetches, calls the LLM, builds HTML strings and sends, with nothing saved.
**Why it's wrong:** When the Monday email looks wrong, you cannot see what HF returned or what Claude said. Every re-run re-bills the LLM and risks re-sending.
**Do this instead:** Stage checkpoints in `archive/<issue>/`, plus the ledger.

### Anti-Pattern 2: Letting the LLM decide license and commercial use from the abstract

**What people do:** Send title and abstract to Claude and ask "can this be used commercially?"
**Why it's wrong:** Papers rarely state licenses. The model will produce plausible guesses, which defeats the newsletter's core value ("실무에 쓸 수 있는가").
**Do this instead:** Gather license evidence from HF model tags and the GitHub license API first. Require an evidence URL for any verdict other than "확인 필요".

### Anti-Pattern 3: LLM writes HTML

**What people do:** Ask Claude to output the newsletter HTML directly.
**Why it's wrong:** The layout is non-deterministic, the email-client rules get broken, and output differs every week.
**Do this instead:** Claude outputs schema-validated JSON; the template owns all markup.

### Anti-Pattern 4: Using Figma or MCP generated markup as the email template

**What people do:** Export Figma to HTML/CSS (div + flex + classes) and send it.
**Why it's wrong:** Gmail strips or ignores much of `<style>` and modern layout CSS. The email collapses.
**Do this instead:** Use Figma as the spec and tokens; write a table-based template by hand.

### Anti-Pattern 5: BCC blast or a single `To:` list

**What people do:** One message to all recipients via BCC.
**Why it's wrong:** You cannot personalize ("홍길동님"), there is no per-recipient ledger, and it is more likely to be flagged as spam.
**Do this instead:** One message per recipient over a single SMTP connection.

### Anti-Pattern 6: Partial issue on upstream failure

**What people do:** If 3 of 10 Claude calls fail, send 7 items anyway, or send with empty fields.
**Why it's wrong:** A silent quality drop with no human review step (the user chose fully automatic).
**Do this instead:** Retry, then fail the whole run before delivery. GitHub emails the repo owner when a workflow fails, so a failed run is the alert. A degraded but valid item with "확인 필요" fields is fine; a missing or invalid item is not.

### Anti-Pattern 7: Time-of-run defines the week

**What people do:** `week = today - 7 days` in UTC at run time.
**Why it's wrong:** Cron runs at Sunday 23:00 UTC, which is still Sunday in UTC, so "last week" by UTC is off by one. Delayed runs shift it further.
**Do this instead:** Compute the previous ISO week in `Asia/Seoul`, and allow `--week` to override.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| HF Papers API | `GET /api/daily_papers?week=YYYY-Www&limit=100&p=N` | Verified live 2026-11-02: `week=2026-W44` returned papers submitted 10-26 to 10-30; `p` paginates; sort by `paper.upvotes` client-side. Unauthenticated, rate-limited, so add retries with backoff. Optional `HF_TOKEN` secret raises limits. |
| HF repo linkage | `GET /api/arxiv/{arxiv_id}/repos` | Verified live: returns models with `tags` including `license:<id>` and `arxiv:<id>`. Alternative: `/api/models?filter=arxiv:<id>`. |
| GitHub REST | `GET /repos/{o}/{r}/license`, `GET /repos/{o}/{r}` | Use `GITHUB_TOKEN` (1,000 req/hr per repo in Actions versus 60 unauthenticated). A 404 means no license detected, which maps to "확인 필요" or "라이선스 없음". |
| Anthropic API | Python SDK, structured JSON output | 11 calls per week. Model choice and pricing belong to STACK.md. Set a timeout and 2 retries. |
| Gmail SMTP | `SMTP_SSL smtp.gmail.com:465`, app password (requires 2FA on the account) | `From` must equal the authenticated account. Send one message per recipient. |
| GitHub Actions | cron + `workflow_dispatch` + `concurrency` + `contents: write` | Schedule is best-effort; a workflow failure email is the alert channel. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| stages <-> stages | JSON files in `archive/<issue>/` validated by `schema.py` | The only coupling is the schema. |
| analyze <-> render | `issue.json` (`Issue` model) | Freeze this contract early; template and prompt work proceed in parallel from a fixture. |
| content <-> delivery | `email.html`/`email.txt` + `Issue` metadata (subject line) | Delivery never calls content stages, and content never reads delivery secrets. |
| delivery <-> ledger | Function calls; ledger flushed after every send | Ledger stores email hashes, not addresses. |

## Suggested Build Order

Dependencies drive this order: the `Issue` schema is the hub; fetch and enrich feed it; the template consumes it; delivery consumes rendered output; scheduling wraps everything.

1. **Skeleton + schema + fetch/select + archive.** CLI, `issue_id` (KST ISO week), `schema.py`, HF fetch with pagination, Top 10 selection, checkpoint store. Runnable in Actions with no secrets in `preview` mode. Produce a fixture week.
2. **Enrichment.** HF arXiv-to-repo linkage, license tags, GitHub license. Evidence objects only. Unit-test on fixtures.
3. **Claude analysis.** Prompts, schema-constrained calls, "확인 필요" rule, trend call, validate-and-retry, caching by checkpoint. Output: real `issue.json`.
4. **Figma web design + email template** (can start in parallel with phases 2 and 3 once the schema from phase 1 exists). Create the Figma frame at 600 to 640 px, extract tokens, write `email.html.j2` + `email.txt.j2`, inline, size check, and the `preview` artifact.
5. **Delivery.** Subscriber CSV from secret, personalization, SMTP sender, `test` mode, ledger and idempotency guards.
6. **Automation and hardening.** Weekly workflow with cron, dispatch inputs, concurrency, commit-back, failure alerting via the Actions failure email, stale-issue guard. Do a test send to Gmail and Naver, then the first live Monday.

Phase 4 carries the most uncertainty (Naver rendering and Korean fonts); start it early. Phase 3 needs the most iteration on prompt quality. Phases 1, 2, 5 and 6 follow standard patterns.

## Sources

- HF Hub OpenAPI spec, `GET /api/daily_papers` params `p, limit, date, week, month, submitter, sort`: https://huggingface.co/.well-known/openapi.md (HIGH, fetched 2026-11-02)
- Live probes of `https://huggingface.co/api/daily_papers?week=2026-W44`, `/api/arxiv/2310.06825/repos` and `/api/models?filter=arxiv:2310.06825` (HIGH, 2026-11-02)
- HF Hub API docs: https://huggingface.co/docs/hub/en/api (HIGH)
- GitHub community reports on scheduled-workflow delays and drops: https://github.com/orgs/community/discussions/210625, https://github.com/orgs/community/discussions/201738, https://github.com/orgs/community/discussions/207346, https://github.com/orgs/community/discussions/185355 (MEDIUM; consistent with GitHub docs describing schedule as best-effort)
- Cron dialect notes (60-day inactivity disable, UTC, 5-minute minimum): https://cronuru.com/dialects/github-actions (MEDIUM)
- CSS inlining for email, Gmail `<style>` stripping: https://dev.to/min8t/how-to-inline-css-for-html-email-the-complete-guide-24pe (MEDIUM)
- Naver Mail CSS support: no authoritative source found (LOW; verify by test send)
- Gmail ~102 KB clipping and ~500/day consumer send limit: widely documented practitioner knowledge (MEDIUM; confirm against current Google Workspace/Gmail help pages in the delivery phase)

---
*Architecture research for: automated weekly AI-model email newsletter (HF Papers -> Claude -> HTML email -> Gmail SMTP on GitHub Actions)*
*Researched: 2026-11-02*
