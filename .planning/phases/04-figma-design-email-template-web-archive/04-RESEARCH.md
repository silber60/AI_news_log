# Phase 4: Figma Design, Email Template & Web Archive - Research

**Researched:** 2026-11-04
**Domain:** Static site generation on GitHub Pages, Google Apps Script unsubscribe backend, RFC 2369/8058 mail headers, email dark mode
**Confidence:** MEDIUM-HIGH (repo facts HIGH; Apps Script runtime behavior and inbox behavior MEDIUM/LOW, gated by owner checkpoints)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Site and hosting
- **D-01:** Everything goes on GitHub Pages at `https://silber60.github.io/AI_news_log/`. That covers the home page (subscribe hero plus 지난 호 cards), the issue pages and the unsubscribe confirm page. Netlify is dropped. The subscribe backend is Google Apps Script either way, so Netlify adds nothing. The owner asked for one site where 지난 호 보기 lands, "뉴닉처럼". — **Reversibility:** costly — moving hosts later changes every published issue URL and the footer links in already-sent emails.
- **D-02:** Issue URL: `https://silber60.github.io/AI_news_log/issues/<issue_id>/`, e.g. `/issues/2026-W45/`. — **Reversibility:** one-way — sent emails link to this URL forever, so it must never change after the first send.
- **D-03:** Web pages are published only on `mode=send`, never on preview or test. Before the send, a test email's 웹에서 보기 link may 404. Publishing works like the Phase 3 `record-topic` job: a separate job with `contents: write`, `needs: run`, running only for send on main. It reads the run artifact, commits the generated pages under `docs/` as `silber60 <81203897+silber60@users.noreply.github.com>`, and is idempotent per issue_id.
- **D-04:** No Figma pass first; go straight to code. The home page follows the existing Figma frame `Website / Subscribe landing (desktop 1280)`, node 25:356 in file `qyJcGii2MLHTbi4W9mPZkx`. Keep the owner's earlier edits: no otter at the top of the 지난 호 미리보기, and no 바로 써볼 만한 것 in "매주 이런 걸 받아요". Fonts are IBM Plex Sans KR. The owner checks a preview of the result.

#### Web issue page
- **D-05 (Claude's default; area not discussed):** The web issue reuses the email design. Under each card it adds an always-open "판정 근거" block with each verdict's `reason_ko`, the Claude/GPT reason, the code license and weights license listed separately, and their evidence links. No JavaScript is needed. Unknown values stay `확인 필요`, and the `해당 없음` Claude/GPT verdict stays hidden (Phase 2 D-11).
- **D-06:** The web copy is de-personalized: the generic greeting (e.g. "구독자님"), no unsubscribe token, and no address or name anywhere.

#### 지난 호 (archive)
- **D-07:** 지난 호 is a section of the home page, not something inside the email. The email footer only links to it. The owner asked for past issues "차곡차곡 모아서".
- **D-08 (Claude's default; the owner did not pick a card format):** Cards are newest first. Each shows the send date, `headline_ko`, the Top 3 model names, and the #1 image when one exists.
- **D-09:** The subscribe form section is built now but hidden until Phase 4.1 sets its endpoint. A code constant such as `SUBSCRIBE_URL = None` keeps it off, the same pattern as `WEB_URL` today. The owner chose "자리만, 4.1에서 켬".

#### Unsubscribe and footer (DLVR-04)
- **D-10:** Click-to-unsubscribe ships in this phase, as the owner chose. The pieces:
  - A Google Sheet holds an unsubscribe list. A Google Apps Script web app receives the confirm and writes to it.
  - The owner creates the Sheet and deploys the script by hand. Claude supplies the script and step-by-step setup.
  - Phase 4.1 reuses the same Sheet and script for subscribing.
  — **Reversibility:** costly — the unsubscribe link format is baked into sent emails, so the endpoint and token scheme must stay valid for every issue already sent.
- **D-11:** The link carries a signed opaque token, never a plain email address. For example, an HMAC of the address with a shared secret held in an Actions secret and Apps Script properties. The token scheme is for research.
- **D-12:** The link opens a confirm page ("구독을 해지할까요?" plus a button). Only the button press unsubscribes, so mail security scanners that prefetch links cannot unsubscribe anyone.
- **D-13:** The subscriber list stays in the `SUBSCRIBERS_CSV` secret until Phase 4.1. In this phase the send step also reads the Sheet's unsubscribe list and skips matches. It logs counts only, never addresses (CLAUDE.md public-repo rule).
- **D-14:** Every message carries a `List-Unsubscribe` header. Research decides whether a `mailto:` plus the https link and RFC 8058 `List-Unsubscribe-Post` one-click can work against Apps Script. Keep the existing "수신거부" reply line as a fallback.
- **D-15:** The footer's sender info is the brand name and send note only. No contact address appears, because the footer is also published on the public web copy.

#### Inbox check (DSGN-05)
- **D-16:** One owner `mode=test` send is checked in Gmail web, the Gmail app, Naver web and the Naver app, in light and dark mode. Light mode fonts already pass (Phase 3). The email stays under 92,160 B.

### Claude's Discretion
- Static site generation details: the Jinja templates, how the home page and index data are regenerated from committed issue JSON, and the CSS approach.
- Web issue layout details beyond D-05.
- Card format details beyond D-08.

### Deferred Ideas (OUT OF SCOPE)
- Backfilling issues sent before Phase 4 into the archive. Their artifacts expire after 90 days, so it could be done once by hand if wanted.
- A custom domain for the site.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DSGN-01 | Figma 640px web/email frame from the mobile design | Satisfied by the Phase 1.1 v2 frame already live (CONTEXT D-04: no new Figma pass). Plan only records it as met. The home page reads frame 25:356 (needs the Figma MCP, which currently needs `/mcp` auth). |
| DSGN-02 | Section order header, greeting, 바로 써볼 만한 것, 트렌드, Top 10, footer | Already enforced by `tests/test_render.py::test_all_eleven_sections_render_in_order_when_filled`. The web variant reuses the same template, so the order carries over. |
| DSGN-05 | Renders in Naver/Gmail web + app, light + dark | §Dark mode: minimal mitigations plus the owner checklist (checkpoint). |
| DLVR-04 | Footer sender info + unsubscribe line, `List-Unsubscribe: <mailto:>` header | §Unsubscribe: header set, the per-recipient footer link, and the folding pitfall (verified). |
| WEB-01 | De-personalized web version on Pages, linked from 웹에서 보기 | §Static site, §Web issue variant, §Publish job. Needs the Pages source switch (verified pitfall). |
| WEB-02 | Archive index of past issues | §Static site: home page 지난 호 cards regenerated from `data/issues/*.json`. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Code decides license / PoC / GPU verdicts. Claude only explains. Unknown → `확인 필요`. The web 판정 근거 block shows code fields as they are and never asks Claude for anything.
- All Claude-generated newsletter text follows the humanizer rules. This phase adds no Claude calls. Fixed Korean UI strings (confirm page, footer) are code constants and should still read naturally in 해요체.
- Public repo: never commit the subscriber CSV. Never log emails, names or credentials. Never enable `smtplib` debug output. New for this phase: tokens and the list key must never be logged either.
- Compute weeks in `Asia/Seoul`. Send dates come from `render.date_line` (`week_end + 1 day`), never runner time.
- Email HTML: tables + inline CSS, system Korean font stack, < 90 KB (`MAX_EMAIL_BYTES = 90 * 1024` = 92,160 B).
- Commit author: `silber60 <81203897+silber60@users.noreply.github.com>`.
- Work through GSD phases. Do not change the frozen `Issue` schema. This phase needs no schema change (verified below).

## Summary

The repo already has everything the web archive needs except the publishing path. `Issue` v4 holds every reason, license and evidence field (`newsletter/schema.py:84-118`). `render.py` gates footer links behind `WEB_URL = None` (`render.py:37`). The email is rendered per recipient already (`deliver.py:58-68`), so a per-recipient unsubscribe link costs no new architecture. The current worst-case email is **77,611 B with 14,549 B headroom** (measured this session by `pytest tests/test_render.py -k worst -s`). The footer links and the unsubscribe link add about 300 B.

Two findings change the plan. **(1) Pushes made with `GITHUB_TOKEN` do not trigger a GitHub Pages build** when Pages deploys from a branch (official GitHub docs). The D-03 publish job would commit pages that never go live. The fix is to switch the Pages source to "GitHub Actions" once (an owner step) and deploy with `actions/upload-pages-artifact` + `actions/deploy-pages` in the same workflow run. **(2) Apps Script `/exec` always answers with a 302** to `script.googleusercontent.com`, and RFC 8058 says "The mail sender MUST NOT return an HTTPS redirect". RFC 8058 one-click is therefore not strictly compliant against Apps Script. It is still useful, because `doPost` runs before the redirect is served and the token sits in the query string. Gmail and Naver do not require one-click from a sender this small, so the header set is `mailto` + `https` + `List-Unsubscribe-Post`, and the plan accepts that one-click may not be offered.

A third, verified pitfall: Python's `email.policy.default` folds a long `List-Unsubscribe` value into RFC 2047 encoded-words (`=?utf-8?q?=3Chttps=3A//...`), which breaks the header. Cloning the message policy with `max_line_length=998` after `set_content` fixes it and leaves the body encodings unchanged (probe run this session).

**Primary recommendation:** Go tracer first. A `publish` CLI command and one merged `publish` job (topic record + web pages, one commit) plus a deploy-pages job, with the Pages source switched to GitHub Actions, make 웹에서 보기 work end to end. Then build the home page design. Then the Apps Script unsubscribe backend with an HMAC-SHA256 hex token (32 chars). Then the delivery integration. Then the dark-mode inbox check.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Web issue + home page HTML | Build-time static generation (Python/Jinja in the Actions `publish` job) | CDN/Static (GitHub Pages) | No server; pages are regenerated from committed `data/issues/*.json` |
| Issue data store | Repo (`data/issues/<id>.json`, git) | — | Same pattern as `data/explainer_topics.json`; no PII in `Issue` |
| Pages deployment | GitHub Actions (`deploy-pages`) | — | `GITHUB_TOKEN` pushes cannot trigger branch builds |
| Unsubscribe confirm UI | CDN/Static (`docs/unsubscribe/index.html`) | Apps Script `doGet` fallback page | D-01 puts the confirm page on Pages; branded, no Google banner |
| Unsubscribe record | Apps Script web app `doPost` → Google Sheet | — | D-10 |
| Unsubscribe list read | Python deliver step → Apps Script `doPost action=list` | — | Key-protected, ids only |
| Token generation | Python deliver step (HMAC) | Apps Script (`tokenFor_`, used by 4.1 welcome mail + self-test) | One secret, two implementations, one test vector |
| List-Unsubscribe headers | Python `send.build_message` | — | Per recipient |

## Standard Stack

No new runtime dependencies. Everything uses packages already locked in `pyproject.toml` [VERIFIED: pyproject.toml read this session].

### Core (already installed)
| Library | Version | Purpose | Note |
|---------|---------|---------|------|
| jinja2 | 3.1.6 | web templates (issue variant, home, unsubscribe page) | `select_autoescape(["html", "j2"])` already escapes `.j2` [VERIFIED: render.py:39-43] |
| css-inline | >=0.23,<0.24 | email only; the web variant skips inlining | |
| httpx | 0.28.1 | Apps Script list fetch | 302 on POST becomes GET [VERIFIED: httpx/_client.py `_redirect_method` lines 494-508 read this session] |
| respx | 0.23.1 (dev) | mock the Apps Script POST → 302 → GET chain | |
| stdlib `hmac`, `hashlib` | Python 3.14.10 | token | |

### GitHub Actions to add (official GitHub actions)
| Action | Version | SHA (verified via `git ls-remote` this session) | Purpose |
|--------|---------|------|---------|
| actions/upload-pages-artifact | v5.0.0 (2026-04-10) | `fc324d3547104276b827a68afc52ff2a11cc49c9` | tar `docs/` as the Pages artifact |
| actions/deploy-pages | v5.0.1 (2026-09-01) | `368f82528645a54fb793d4d04e342629a3f51346` | deploy; job needs `pages: write`, `id-token: write`, `environment: github-pages` [CITED: github.com/actions/deploy-pages README v5.0.1] |

`upload-pages-artifact` excludes hidden files by default (`include-hidden-files: false`) [VERIFIED: action.yml v5.0.0]. `docs/.nojekyll` is then not shipped, which is fine: the Actions source runs no Jekyll. Keep the file; it is harmless and keeps a fallback to branch deploy.

**Installation:** none. `uv sync --frozen` stays the same.

## Package Legitimacy Audit

No new packages from PyPI/npm. The two GitHub actions are first-party `actions/*` repos, resolved to commit SHAs with `git ls-remote` this session. They follow the existing SHA-pin rule (`tests/test_workflow_static.py::test_actions_pinned_to_commit_sha`).

| Package | Registry | Source Repo | Verdict | Disposition |
|---------|----------|-------------|---------|-------------|
| actions/upload-pages-artifact@v5.0.0 | GitHub | github.com/actions/upload-pages-artifact | first-party | Approved (SHA-pin) |
| actions/deploy-pages@v5.0.1 | GitHub | github.com/actions/deploy-pages | first-party | Approved (SHA-pin) |

**Packages removed:** none. **Flagged:** none.

## Architecture Patterns

### System Architecture Diagram

```
workflow_dispatch(mode=send, main)
   │
   ▼
[run job] build ──► archive/<id>/issue.json ──► artifact issue-<run_id>
   │                                   │
   │  Deliver step (send):             │
   │   SUBSCRIBERS_CSV ─► parse ─┐     │
   │   Apps Script POST action=list ─► ids set ─► filter (token(email) ∉ ids)
   │                             └─► per recipient: token ► footer link + List-Unsubscribe headers ► SMTP
   ▼                                   ▼
[publish job] (contents: write) download artifact
   │   record-topic ─► data/explainer_topics.json
   │   publish ─► data/issues/<id>.json (first write wins)
   │            └► regenerate docs/issues/*/index.html, docs/index.html, docs/unsubscribe/index.html
   │   one commit + pull --rebase retry ─► main
   │   upload-pages-artifact(docs/)
   ▼
[deploy-pages job] (pages: write, id-token: write) ─► https://silber60.github.io/AI_news_log/

Reader click (email footer) ─► /unsubscribe/?t=<token> (static, GET = no side effect)
   └► button: form POST ─► Apps Script /exec (doPost) ─► Sheet row {id, at, via} ─► 302 ─► "해지됐어요" page
Mail client one-click ─► POST /exec?t=<token> body List-Unsubscribe=One-Click ─► same doPost
Scanner prefetch ─► GET /unsubscribe/?t=… or GET /exec?t=… ─► confirm page only
```

### Recommended file layout

```
newsletter/
├── web.py                     # NEW: publish(): data/issues + regenerate docs/ (no network)
├── delivery/unsubscribe.py    # NEW: token(), fetch_unsubscribed(), header values
├── delivery/deliver.py        # filter + per-recipient link
├── delivery/send.py           # build_message(..., list_unsubscribe=...)
└── stages/render.py           # SITE_URL, issue_url(), render_web_issue(), unsubscribe_url kwarg
templates/
├── email.html.j2              # template-version 9: web flag, 판정 근거 macro, footer links
├── email.txt.j2               # template-version 8
└── web/
    ├── _base.html.j2          # <head>, IBM Plex Sans KR link, site <style>
    ├── home.html.j2           # Figma 25:356 + 지난 호 cards + hidden subscribe section
    └── unsubscribe.html.j2    # 구독을 해지할까요? + form POST
apps_script/
└── Code.gs                    # NEW: committed, no secrets (owner pastes it)
data/issues/<issue_id>.json    # NEW: committed Issue v4 copies
docs/
├── index.html                 # generated
├── issues/<issue_id>/index.html
├── unsubscribe/index.html
└── assets/email/v1/…          # untouched (test_assets exact-set guard)
.github/workflows/
├── newsletter.yml             # record-topic job → publish job + deploy-pages job
└── pages.yml                  # NEW: push to main (docs/**) + workflow_dispatch → deploy
```

### Pattern 1: Static site regenerated from committed data (WEB-01, WEB-02)

- **Source of truth:** `data/issues/<issue_id>.json`, a validated `Issue` v4 dump written with `store.write_json`. `Issue` contains no address or name. Its fields are issue_id, dates, `generated_at`, `model`, `items`, `headline_ko`, `trend_ko`, `highlights`, `explainer` [VERIFIED: newsletter/schema.py:205-218]. Keep the data out of `docs/` so Pages never serves raw JSON. Pages deploys only `docs/`.
- **Idempotent per issue_id:** if `data/issues/<id>.json` exists, keep it (first send wins, as in `topics.record`) and log `web=exists issue=<id>`. Otherwise write it and log `web=published`. Then always regenerate **all** of `docs/issues/*/index.html`, `docs/index.html` and `docs/unsubscribe/index.html` from `data/issues/*.json`. A template change then propagates to every past issue on the next publish, and a re-run with no change gives `git diff --quiet` and no commit.
- **No separate index JSON.** The home page sorts `data/issues/*.json` by `issue_id` descending (`2026-W45` > `2026-W44` sorts correctly as a string; ISO week ids are zero-padded) [VERIFIED: newsletter/week.py format used by `previous_iso_week`; topics.py sorts the same way, line `sorted(entries, key=lambda e: e["issue_id"], reverse=True)`].
- **Deterministic output:** no timestamps in the generated HTML. That keeps re-runs byte-identical, so there are no empty commits.
- **Validation on read:** `Issue.model_validate(read_json(p))` per file. One invalid file raises (fail loud in the publish job, like `topics.record`).

Home page card data (D-08):
```python
# newsletter/web.py (sketch)
def card(issue: Issue) -> dict:
    first = issue.items[0]
    return {
        "url": issue_url(issue.issue_id),          # f"{SITE_URL}issues/{issue_id}/"
        "date": render.date_line(issue),            # "2026.11.09 월요일", KST rule
        "headline": issue.headline_ko,
        "top3": [it.title_ko for it in issue.items[:3]],
        "image": first.image,                       # ItemImage | None; hotlinked as in email
    }
```

### Pattern 2: One template, two variants (D-05, D-06)

Render the web issue with the **same** `email.html.j2` plus a `web` flag. Do not write a second card template. Two card templates would drift, and WEB-01 asks for a copy of the issue.

- `_context(issue, greeting, *, web=False, unsubscribe_url=None)` adds `web`, `issue_url`, `site_url`, `unsubscribe_url`.
- `render_html(issue, greeting, *, unsubscribe_url=None)` keeps the byte check and inlining.
- `render_web_issue(issue) -> str` renders with `greeting=DEFAULT_GREETING` (`"구독자님"`), `web=True`, `unsubscribe_url=None`. It **skips `_INLINER`**, because the template already writes every style inline, and the web page keeps a real `<style>` block for responsive rules. No byte limit applies, but keep a sanity test.
- Inside the template, `{% if web %}` adds:
  - `<style>` with `@media (max-width: 680px) { .wrap { width: 100% !important; } img { max-width: 100% !important; height: auto !important; } }`. Add `class="wrap"` to the 640 table (+13 B in the email).
  - the 판정 근거 block after each card's verdict row (below).
  - a web footer line that replaces the reply line ("이 메일에 회신" makes no sense on the web), e.g. "구독 해지는 받으신 메일 아래쪽 링크에서 할 수 있어요." D-15: no contact address.
- In the email (`not web`): the footer shows 웹에서 보기 → `issue_url`, 지난 호 보기 → `site_url` (or `site_url + "#archive"`), the per-recipient `구독 해지` link when `unsubscribe_url`, and keeps the "수신거부" reply line (D-14).
- `WEB_URL: str | None = None` is replaced by `SITE_URL = "https://silber60.github.io/AI_news_log/"` and `issue_url(issue_id)`. The links now always render in test and send email. D-03 accepts a 404 before the send.

Template versions: `email.html.j2` → `template-version: 9`, `email.txt.j2` → `template-version: 8`.

### Pattern 3: 판정 근거 block — exact schema fields [VERIFIED: newsletter/schema.py:84-118 read this session]

Quoted verbatim:
```python
class LicenseInfo(Strict):
    spdx_id: str | None = None
    name: str | None = None
    source_url: HttpsUrl | None = None

class CommercialUse(Strict):  # Phase 2 (EVID-02, ANLY-04)
    verdict: CommercialVerdict = "확인 필요"
    code_license: LicenseInfo | None = None
    weights_license: LicenseInfo | None = None
    evidence: list[EvidenceLink] = []
    reason_ko: str | None = None

class PocReadiness(Strict):  # Phase 2 (EVID-03)
    verdict: PocVerdict = "확인 필요"
    has_weights: bool | None = None
    has_code: bool | None = None
    has_demo: bool | None = None
    evidence: list[EvidenceLink] = []
    reason_ko: str | None = None

class Hardware(Strict):  # Phase 2 (EVID-04)
    param_count: int | None = None
    est_vram_gb: float | None = None
    local_run: LocalRun = "확인 필요"
    evidence: list[EvidenceLink] = []

class ClaudeGptUse(Strict):  # Phase 2 (ANLY-02)
    verdict: ClaudeGptVerdict = "확인 필요"
    reason_ko: str | None = None
```
and `EvidenceLink(label: str, url: HttpsUrl)`, `UNKNOWN = "확인 필요"`, `ClaudeGptVerdict = Literal["직접 사용", "기법 적용 가능", "해당 없음", "확인 필요"]`.

Block rows (code builds them in `render.py` as `basis_rows(it)`; the template only loops):

| Row | Value | Rule |
|-----|-------|------|
| 상업 이용 | `commercial.verdict` + `commercial.reason_ko` | reason missing → verdict only |
| 코드 라이선스 | `code_license.spdx_id or name`, linked to `source_url` | None → `확인 필요` |
| 가중치 라이선스 | `weights_license.spdx_id or name`, linked to `source_url` | None → `확인 필요` (shows the D-09 code-only case) |
| 바로 써보기 | `poc.verdict` + `poc.reason_ko` | |
| GPU | `hardware.local_run`, `ceil(est_vram_gb)`GB, `param_count` | None → `확인 필요`; no reason field exists |
| Claude/GPT | `claude_gpt.verdict` + `claude_gpt.reason_ko` | **hidden when verdict == "해당 없음"** (Phase 2 D-11) |
| 근거 링크 | `commercial.evidence + poc.evidence + hardware.evidence`, deduped by url, `label` as text | only `url.startswith(EVIDENCE_HOSTS)` (`("https://huggingface.co/", "https://github.com/")`, verdicts.py:17-19) |

`skill_gpt.reason_ko` and `model_info.evidence` exist too. They are optional extras; D-05 does not ask for them.

### Pattern 4: Merged publish job + Pages deploy (D-03)

Merge `record-topic` and publishing into one job named `publish`. Two jobs pushing to `main` in the same run would race (both `pull --rebase` the same tip). One job makes one commit and one push.

```yaml
  publish:
    needs: run
    if: ${{ inputs.mode == 'send' && github.ref == 'refs/heads/main' && needs.run.result == 'success' }}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: write
    env:
      MODE: ${{ inputs.mode }}
      PYTHONUNBUFFERED: "1"
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2  # v10.3.3
        with: { python-version: "3.14", enable-cache: true }
      - name: Install locked dependencies (publish)
        run: uv sync --frozen
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333  # v8.0.2
        with: { name: "issue-${{ github.run_id }}", path: archive/ }
      - name: Append explainer topic
        run: uv run python -m newsletter record-topic --mode "$MODE"
      - name: Publish web pages
        run: uv run python -m newsletter publish --mode "$MODE"
      - name: Commit record and pages
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          git add -- data/explainer_topics.json data/issues docs
          git diff --cached --quiet && exit 0
          git config user.name silber60
          git config user.email 81203897+silber60@users.noreply.github.com
          git commit -m "chore(web): publish issue and topic record"
          for i in 1 2; do
            git pull --rebase "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" main \
              && git push "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:main && exit 0
          done
          exit 1
      - uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9  # v5.0.0
        with:
          path: docs/

  deploy-pages:
    needs: publish
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
    concurrency:
      group: pages
      cancel-in-progress: false
    steps:
      - uses: actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346  # v5.0.1
```

`pages.yml` (new) covers human pushes that touch `docs/**` (asset or template-regenerated commits from a laptop). It runs on `push: branches: [main], paths: ["docs/**"]` and `workflow_dispatch`, does checkout → upload-pages-artifact `docs/` → deploy-pages, and uses the same `concurrency: group: pages`. A `GITHUB_TOKEN` push from `publish` does not trigger it (that is the reason for `deploy-pages` inside newsletter.yml), so there are no double deploys.

The upload step runs after the commit in the same working tree, so the artifact holds the new pages. `deploy-pages` needs no checkout. That avoids the stale-`github.sha` checkout trap.

### Anti-Patterns to Avoid
- **Separate `publish-web` job next to `record-topic`:** two pushes to main per run; rebase races.
- **Committing generated JSON under `docs/`:** it becomes public raw data and has to be scrubbed forever. Keep data in `data/issues/`.
- **Putting the email address in the unsubscribe URL or the Sheet.** D-11 forbids it. Store only the token id.
- **A second card template for the web.** It drifts. Use the `web` flag.
- **Auto-submitting the confirm form with JS.** That defeats D-12 (scanners run JS sometimes).

## Unsubscribe design (D-10..D-14)

### Token scheme [VERIFIED: Python hmac run this session]

`token = HMAC-SHA256(key=UNSUBSCRIBE_TOKEN_SECRET (UTF-8), msg=email.strip().lower() (UTF-8)).hexdigest()[:32]` (128 bits, lowercase hex).

- Hex, not base64. It is case-stable, has no `-`/`_`/padding, and is trivial to build from Apps Script's signed bytes.
- The Sheet stores the token only. The Python send recomputes the token for each CSV recipient and skips members of the set. Apps Script never needs the address in Phase 4. It keeps the secret for the Phase 4.1 welcome mail and for the self-test.
- Forgery: making a valid token for a target address needs the secret. A random token only adds a junk row that matches nobody.
- Rotation: never rotate (the D-10 one-way door). If the secret leaks, the worst case is forged unsubscribes and dictionary reversal of ids. A v2 scheme would need a new param name (`t2=`) with old tokens still honored.

Python:
```python
# newsletter/delivery/unsubscribe.py
import hashlib, hmac, re

TOKEN_LEN = 32
TOKEN_RE = re.compile(r"[0-9a-f]{32}")

def token(email: str, secret: str) -> str:
    norm = email.strip().lower()
    return hmac.new(secret.encode("utf-8"), norm.encode("utf-8"), hashlib.sha256).hexdigest()[:TOKEN_LEN]
```

Apps Script (V8):
```javascript
function tokenFor_(email, secret) {
  const bytes = Utilities.computeHmacSha256Signature(
      String(email).trim().toLowerCase(), secret, Utilities.Charset.UTF_8);
  // Byte[] values are signed (-128..127); & 0xff makes them 0..255.
  return bytes.map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); })
      .join('').slice(0, 32);
}
```

**Test vector** (computed this session with Python 3.14 `hmac`):

| secret | input | normalized | token |
|--------|-------|-----------|-------|
| `test-secret-do-not-use` | `"Subscriber@Example.com "` | `subscriber@example.com` | `f290b8e448576cf84f63ac2b465c3e65` |
| `test-secret-do-not-use` | `"a@example.com"` | `a@example.com` | `82a671b5104273fe07992f40d81000c8` |

The Apps Script side is [ASSUMED] until the owner runs `selfTest()`. Two points are unconfirmed. The Utilities docs give no default charset for the 2-arg overload, and it is not said whether the `charset` arg also covers the key; the secret is ASCII, so that is moot. The docs do not say the returned `Byte[]` is signed, but their decode example logs negative values. `selfTest` compares against the vector above, so a mismatch is caught before any email ships.

### Endpoint and pages

- `UNSUBSCRIBE_ENDPOINT: str | None = None` in code (`newsletter/delivery/unsubscribe.py`). The `/exec` URL appears in every email header, so it is not a secret. While it is None (before the owner deploys), the email omits the footer link and the https header part, and keeps the `mailto` header and the reply line. Plans 1-2 can then ship before Google setup.
- Footer link: `https://silber60.github.io/AI_news_log/unsubscribe/?t=<token>`. It is on Pages (D-01) and decoupled from the Apps Script URL, so a broken deployment can be fixed by regenerating one page, and old emails keep working.
- `docs/unsubscribe/index.html` (generated from `templates/web/unsubscribe.html.j2`): "구독을 해지할까요?" plus `<form method="post" action="{{ endpoint }}">` with a hidden `t` and a button. About 6 lines of inline JS copy `t` from `location.search` into the hidden input **only if** it matches `/^[0-9a-f]{32}$/`, set via `.value`, never `innerHTML`. With no or a bad token, show "링크가 올바르지 않아요" and hide the button. `<noscript>`: "메일에 '수신거부'라고 회신해 주세요." The page contains no token and no address, and its GET has no side effect.
- `List-Unsubscribe` https target: `<UNSUBSCRIBE_ENDPOINT>?t=<token>`. GET → `doGet` renders a fallback confirm page that uses `google.script.run` (documented client→server call, no form-in-iframe issues). POST → `doPost` records it.

### Apps Script behaviors (evidence)

- Apps Script content is "redirected to a one-time URL at `script.googleusercontent.com`"; clients must follow the redirect [CITED: developers.google.com/apps-script/guides/content]. curl needs `-L` [CITED: dev.to/googleworkspace, Justin Poehnelt, 2025-07-09].
- **doPost side effect runs on the first POST.** The 302 points to the stored output. A Stack Overflow report says that even when the follow-up fails (405), "the data still appears in the Google Sheet" [CITED: backiee.wasmer.app mirror of stackoverflow q/79776622]. The Poehnelt article is ambiguous here ("doesn't directly execute"). This is [ASSUMED/MEDIUM] and confirmed by the owner curl step below.
- `e.parameter` holds query-string params for both GET and POST [CITED: developers.google.com/apps-script/guides/web, event object]. Whether a form-encoded body is merged in is not stated on that page. **The design never depends on the body:** the token is always in the query string for one-click and the list call, and the confirm form posts `t` in the body **and** the action URL carries `?t=` as well. Simplest: the JS sets `form.action = endpoint + "?t=" + t`.
- RFC 8058 receivers "SHOULD" send `multipart/form-data` and "MAY" send `application/x-www-form-urlencoded` [CITED: rfc-editor.org/rfc/rfc8058]. The body may not parse into `e.parameter`. That does not matter because of the query token.
- Deployment URL stays the same only by **Deploy > Manage deployments > Edit > New version**: "the standard way to update your application without changing its URL or deployment ID" [CITED: developers.google.com/apps-script/concepts/deployments]. A "New deployment" creates a new URL, which breaks every sent header.
- "Execute as: Me" runs as the owner [CITED: guides/web]. "Who has access: Anyone" (anonymous) is required for a mail-server POST. Its behavior is not covered on that page [ASSUMED]; the owner curl test confirms it.
- Consumer-account HtmlService pages show a Google "created by another user" banner [ASSUMED]. That is the reason the primary confirm page lives on Pages.

### RFC 8058 / receiver requirements → header decision (D-14)

- RFC 8058: "The mail sender MUST NOT return an HTTPS redirect" (line 216), and one-click needs a DKIM signature whose `h=` covers both headers; without it "the mail receiver SHOULD NOT offer a one-click unsubscribe" [VERIFIED: rfc8058.txt grep this session]. Apps Script always 302s, so it is **not strictly compliant**.
- Gmail: one-click is required only for senders of 5,000+/day. All senders need SPF or DKIM and a spam rate below 0.3% [CITED: support.google.com/a/answer/81126]. This newsletter sends from a gmail.com account via smtp.gmail.com, a tiny volume, so one-click is **not required**.
- Whether Gmail's outbound DKIM `h=` covers `List-Unsubscribe` for SMTP-submitted mail: no observation [ASSUMED]. The owner checks "원본 보기" (Show original) → `DKIM-Signature: … h=…`.
- Naver Mail's handling of `List-Unsubscribe`: no observation [ASSUMED]. Owner checkpoint.

**Recommendation:**
```
List-Unsubscribe: <mailto:{SMTP_USER}?subject=unsubscribe>, <{UNSUBSCRIBE_ENDPOINT}?t={token}>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```
- Include `List-Unsubscribe-Post`. If a receiver does one-click, `doPost` records it before the 302, so the result is correct even if the receiver flags the redirect. If the receiver refuses one-click (no DKIM coverage, redirect), it falls back to mailto or the https GET, which shows the confirm page. Scanners do not POST, and RFC 8058 says receivers "MUST NOT perform a POST … without user consent", so D-12 holds.
- `mailto` uses `SMTP_USER` at runtime (never hardcoded in the repo) and an ASCII subject `unsubscribe`. The owner handles these by hand, as with today's "수신거부" replies (Phase 4.1 automates).
- When `UNSUBSCRIBE_ENDPOINT is None`: `List-Unsubscribe: <mailto:…>` only and no `-Post` header (RFC 8058 requires an https URI for `-Post`).
- Test mode also gets the headers and the link, with the token of `TEST_RECIPIENT`. The owner can then test the flow and delete their row afterwards.

### Header folding pitfall [VERIFIED: probe run this session, Python 3.14.10]

`EmailMessage` (policy.default) serializes a long `List-Unsubscribe` as:
```
List-Unsubscribe: <mailto:owner@gmail.com?subject=unsubscribe>, =?utf-8?q??=
 =?utf-8?q?=3Chttps=3A//script=2Egoogle=2Ecom/macros/s/AKfycbxAAAAAAAAAAAAAA?=
```
That is broken for receivers. Fix: after `set_content`/`add_alternative`, set `msg.policy = msg.policy.clone(max_line_length=998)` before sending. The probe showed the header on one line, `Content-Transfer-Encoding: 8bit` (text) and `base64` (html) unchanged, and the max body line 76. `smtplib.send_message` flattens with the message's policy when not international. Add a test that parses `msg.as_bytes()` and asserts the raw header line contains `<https://` and no `=?utf-8?`.

### Apps Script code (to commit as `apps_script/Code.gs`; no secrets in it)

```javascript
// 모닥로그 AI 리포트 — unsubscribe web app (Phase 4). Phase 4.1 adds subscribe.
// Script properties: SHEET_ID, TOKEN_SECRET, LIST_KEY. Never log ids or keys.
const SHEET = 'unsubscribes';
const TOKEN_RE = /^[0-9a-f]{32}$/;
const SITE = 'https://silber60.github.io/AI_news_log/';

function prop_(k) { return PropertiesService.getScriptProperties().getProperty(k); }
function sheet_() { return SpreadsheetApp.openById(prop_('SHEET_ID')).getSheetByName(SHEET); }

function doGet(e) {
  const t = String((e && e.parameter && e.parameter.t) || '').toLowerCase();
  const tpl = HtmlService.createTemplate(CONFIRM_HTML);
  tpl.t = TOKEN_RE.test(t) ? t : '';
  return tpl.evaluate().setTitle('구독 해지');
}

function doPost(e) {
  const p = (e && e.parameter) || {};
  if (p.action === 'list') return list_(String(p.key || ''));
  const t = String(p.t || '').toLowerCase();
  if (!TOKEN_RE.test(t)) return done_('링크가 올바르지 않아요.');
  record_(t, p['List-Unsubscribe'] === 'One-Click' ? 'one-click' : 'button');
  return done_('구독이 해지됐어요. 다음 주부터는 메일이 가지 않아요.');
}

function unsubscribe(t) {               // google.script.run target (doGet fallback page)
  t = String(t || '').toLowerCase();
  if (!TOKEN_RE.test(t)) return false;
  record_(t, 'button');
  return true;
}

function record_(t, via) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sh = sheet_();
    const found = sh.getRange('A:A').createTextFinder(t).matchEntireCell(true).findNext();
    if (!found) sh.appendRow([t, new Date().toISOString(), via]);
  } finally { lock.releaseLock(); }
}

function list_(key) {
  const want = prop_('LIST_KEY') || '';
  if (!want || !safeEq_(key, want)) {
    return ContentService.createTextOutput('{"error":"forbidden"}').setMimeType(ContentService.MimeType.JSON);
  }
  const last = sheet_().getLastRow();
  const ids = last < 2 ? [] : sheet_().getRange(2, 1, last - 1, 1).getValues()
      .map(function (r) { return String(r[0]); }).filter(function (v) { return TOKEN_RE.test(v); });
  return ContentService.createTextOutput(JSON.stringify({ version: 1, ids: ids }))
      .setMimeType(ContentService.MimeType.JSON);
}

function safeEq_(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

function done_(msg) {
  const tpl = HtmlService.createTemplate(DONE_HTML);
  tpl.msg = msg; tpl.site = SITE;
  return tpl.evaluate().setTitle('구독 해지');
}

function tokenFor_(email, secret) { /* see Token scheme */ }

function setup() {                       // owner runs once
  const ss = SpreadsheetApp.openById(prop_('SHEET_ID'));
  const sh = ss.getSheetByName(SHEET) || ss.insertSheet(SHEET);
  sh.getRange('A:A').setNumberFormat('@'); // keep ids as text (e.g. "123e45..." must not become a number)
  if (sh.getLastRow() === 0) sh.appendRow(['id', 'at', 'via']);
}

function selfTest() {                    // owner runs once; must log PASS
  const got = tokenFor_('Subscriber@Example.com ', 'test-secret-do-not-use');
  Logger.log(got === 'f290b8e448576cf84f63ac2b465c3e65' ? 'PASS' : 'FAIL ' + got);
}

const CONFIRM_HTML = '<!doctype html><html lang="ko"><body style="font-family:sans-serif;padding:24px">'
  + '<? if (t) { ?><h2>구독을 해지할까요?</h2><button id="b">구독 해지</button><p id="m"></p>'
  + '<script>document.getElementById("b").onclick=function(){this.disabled=true;'
  + 'google.script.run.withSuccessHandler(function(ok){document.getElementById("m").textContent='
  + 'ok?"구독이 해지됐어요.":"링크가 올바르지 않아요.";}).unsubscribe(<?= t ?>);};</script>'
  + '<? } else { ?><p>링크가 올바르지 않아요.</p><? } ?></body></html>';
const DONE_HTML = '<!doctype html><html lang="ko"><body style="font-family:sans-serif;padding:24px">'
  + '<p><?= msg ?></p><p><a href="<?= site ?>" target="_top">모닥로그 AI 리포트 홈</a></p></body></html>';
```
In the `CONFIRM_HTML` scriptlet, `<?= t ?>` inside a `<script>` context is auto-escaped by HtmlService contextual escaping [ASSUMED]. `t` is regex-limited to hex, so it is safe either way, but the executor should quote it as a JS string. `TextFinder`, `LockService`, `ContentService` and `HtmlService.createTemplate` are standard services [ASSUMED from training; the owner's `setup()`/`selfTest()` runs exercise them].

### Python list fetch (deliver step)

```python
def fetch_unsubscribed(endpoint: str, key: str, client: httpx.Client | None = None) -> set[str]:
    c = client or httpx.Client(timeout=20)
    try:
        r = c.post(endpoint, data={"action": "list", "key": key}, follow_redirects=True)
    except httpx.HTTPError as e:
        raise DeliveryError(f"unsubscribe list {type(e).__name__}") from None
    if r.status_code != 200:
        raise DeliveryError(f"unsubscribe list status={r.status_code}")
    try:
        data = r.json()
        ids = {i for i in data["ids"] if isinstance(i, str) and TOKEN_RE.fullmatch(i)}
    except (ValueError, KeyError, TypeError):
        raise DeliveryError("unsubscribe list unreadable") from None
    return ids
```
- `follow_redirects=True` is required. httpx defaults to False, and every existing call in the repo uses False [VERIFIED: grep enrich.py:586,639,674, licenses.py:206]. httpx turns a 302 after POST into a GET [VERIFIED: httpx `_redirect_method`].
- The key goes in the POST body, never the URL. httpx INFO logs are already silenced (`__main__.py`, `logging.getLogger("httpx").setLevel(logging.WARNING)`).
- **Fail closed in send mode.** If the list cannot be read, raise `DeliveryError`. The failure notice fires, and nobody who unsubscribed gets mail. Test mode does not fetch the list (one recipient, the owner).
- Log: `mode=send recipients=%d unsubscribed=%d sent=%d skipped_rows=%d`, counts only. If filtering leaves zero recipients, log it and return success with `sent=0`. It is not an error.

### Secrets (new) — scoped to the `Deliver` step only

| Secret | Used in | Gate |
|--------|---------|------|
| `UNSUBSCRIBE_TOKEN_SECRET` | Deliver (test + send) | `inputs.mode == 'test' \|\| inputs.mode == 'send'` (the step condition) |
| `UNSUBSCRIBE_LIST_KEY` | Deliver (send only) | `${{ inputs.mode == 'send' && secrets.UNSUBSCRIBE_LIST_KEY \|\| '' }}` |

Add both names to `DELIVERY_SECRETS` in `tests/test_workflow_static.py` so the "only in Deliver/Failure notice" guard covers them. Also assert they are **not** in the Failure notice step.

If `UNSUBSCRIBE_ENDPOINT` is set but `UNSUBSCRIBE_TOKEN_SECRET` is missing, raise `DeliveryError("missing environment variable UNSUBSCRIBE_TOKEN_SECRET")` (existing `_env` pattern). Never send links without tokens.

### Owner setup steps (draft for the checkpoint task)

1. In the Google account that owns `SMTP_USER`, create a Google Sheet named `모닥로그 AI 리포트 구독 관리`. Copy its ID from the URL (`/d/<ID>/edit`).
2. In the Sheet, open 확장 프로그램 → Apps Script. Replace `Code.gs` with `apps_script/Code.gs` from the repo. Save.
3. On a laptop, generate two secrets: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` (run twice).
4. In Apps Script, open 프로젝트 설정 → 스크립트 속성 and add `SHEET_ID`, `TOKEN_SECRET` (secret 1) and `LIST_KEY` (secret 2).
5. Run `setup` from the editor and approve the permissions. Check that a tab `unsubscribes` appears with the header `id | at | via`.
6. Run `selfTest`. 실행 로그 must show `PASS`. If it shows `FAIL <hex>`, stop and report the hex.
7. Open 배포 → 새 배포 → 유형: 웹 앱. Set 다음 사용자 인증 정보로 실행: **나** and 액세스 권한이 있는 사용자: **모든 사용자**. Deploy and copy the `/exec` URL. It is not secret; give it to Claude so it can be committed as `UNSUBSCRIBE_ENDPOINT`.
8. In GitHub, open Settings → Secrets and variables → Actions. Add `UNSUBSCRIBE_TOKEN_SECRET` (= TOKEN_SECRET) and `UNSUBSCRIBE_LIST_KEY` (= LIST_KEY).
9. From a terminal, check the list call: `curl -sL -d "action=list&key=<LIST_KEY>" "<URL>"` → `{"version":1,"ids":[]}`. A wrong key → `{"error":"forbidden"}`.
10. Check one-click: `curl -s -o /dev/null -w "%{http_code}\n" -d "List-Unsubscribe=One-Click" "<URL>?t=82a671b5104273fe07992f40d81000c8"` → `302`. A row with that id appears in the Sheet. Delete the row.
11. Rule for later script edits: 배포 → 배포 관리 → 수정(연필) → 버전: 새 버전 → 배포. **Never "새 배포"**; it changes the URL baked into sent emails.

### Size impact

The per-recipient footer link is about 130 B (`…/unsubscribe/?t=` + 32 hex + markup). The two web links in the footer and header add about 200 B. Total about 350 B against 14,549 B headroom (worst case 77,611 B measured). Headers do not count toward the HTML byte check. Update `_worst_case` tests to render with an `unsubscribe_url` of max length.

## Dark mode (DSGN-05)

- Gmail (web, iOS, Android) does not support `prefers-color-scheme`, the `color-scheme` property or the meta tag. Gmail iOS does a full color inversion. Gmail Android does a partial inversion that varies by device [CITED: courier.com/blog/dark-mode-email-design, citing caniemail; dev.to/mailpeek; MEDIUM, vendor blogs]. Gmail web keeps the message body light in its dark theme [ASSUMED].
- Naver Mail app: it supports dark mode per its App Store listing. How it treats HTML mail colors: no observation [ASSUMED]. Test only.
- Repo specifics:
  - Banners `otter-banner.jpg`/`otter-wave.jpg` were flattened onto white (01.1-02 plan). In inverted dark mode they show as white rectangles. That is acceptable and needs no change.
  - The otter PNGs have true alpha with transparent corners (`tests/test_assets.py::test_otter_has_real_alpha`) and a halo guard against the Figma (30,30,30) canvas. On an inverted dark `#FFF6F0`/`#EDF6FF` box, their dark outlines lose contrast. The halo fix means no grey fringe.
  - `#FF6B00` orange text and `#A3A3A3` meta text are auto-adjusted by inverting clients. `#A3A3A3` on a dark background may get dim.
- Minimal mitigations (cheap, no layout change):
  1. Add `<meta name="color-scheme" content="light">` and `<meta name="supported-color-schemes" content="light">`. Apple Mail/iOS Mail honor them and keep the light design. Gmail ignores them (harmless, about 90 B).
  2. Keep explicit `background-color` on every colored cell (already done). Never rely on a transparent background for meaning.
  3. Do not ship dark-mode-specific CSS. Gmail ignores it, and Naver is unknown, so it is untestable cost.
  4. If the owner flags the otters as unreadable in dark mode, the fallback is a new `docs/assets/email/v3/` with a 2px light outline (D-09 immutability: v1 and v2 are both live in sent mail and never edited; v2 became the current set in commit 450e1c8). Defer unless the checkpoint fails.
- Owner checklist (one `mode=test` send, after the footer/header plan):
  - [ ] Gmail web, light: layout, fonts, footer links open `/issues/<id>/` (404 is OK before the first send, D-03) and home
  - [ ] Gmail web: "원본 보기" shows `List-Unsubscribe` on one line with `<mailto:` and `<https://`, `List-Unsubscribe-Post`, and note whether `DKIM-Signature h=` includes `list-unsubscribe`
  - [ ] Gmail web: an "구독 취소" link near the sender name? (record yes/no; not required)
  - [ ] Gmail app iOS/Android, dark: text readable; highlight box and explainer box readable; otters visible
  - [ ] Naver web, light: same as Gmail web; Naver shows any 수신거부 UI? (record)
  - [ ] Naver app, dark: text and boxes readable
  - [ ] Footer `구독 해지` → Pages confirm page → button → "구독이 해지됐어요"; the Sheet has one row; delete the row
  - [ ] Message size stays below the clip (Gmail shows no "[메시지가 잘렸습니다]")

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pages deployment | `git push` + hoping Pages rebuilds, or a PAT | `actions/upload-pages-artifact` + `actions/deploy-pages` | GITHUB_TOKEN pushes do not trigger Pages builds (official) |
| Token MAC | custom hash/concat | `hmac.new(..., hashlib.sha256)` / `Utilities.computeHmacSha256Signature` | length-extension and encoding bugs |
| Concurrent sheet writes | read-then-write without a lock | `LockService.getScriptLock()` | duplicate rows from a double click + one-click |
| Header folding | manual string building with CRLF | `EmailMessage` + `policy.clone(max_line_length=998)` | header injection; encoded-word breakage |
| HTML escaping | string concatenation | Jinja autoescape (already on) | Claude text in pages |
| Redirect following | manual Location handling | `httpx … follow_redirects=True` | POST→GET semantics |

## Common Pitfalls

### Pitfall 1: Pages never updates after the publish job pushes
**What goes wrong:** the commit lands on main, and the site stays stale or 404s.
**Why:** "Commits pushed by a GitHub Actions workflow that uses the `GITHUB_TOKEN` do not trigger a GitHub Pages build." [CITED: docs.github.com/en/actions/concepts/security/github_token]
**How to avoid:** switch the Pages source to GitHub Actions (owner, one time) and add the deploy job. Fallback if the owner refuses: `POST /repos/{owner}/{repo}/pages/builds` with `pages: write` on the job token. Whether the job token is accepted there is [ASSUMED]; the docs do not list token types.
**Warning signs:** `curl -sI https://silber60.github.io/AI_news_log/issues/<id>/` → 404 after a send.

### Pitfall 2: Switching the Pages source drops the email assets
**What goes wrong:** sent emails show broken otter images.
**How to avoid:** right after switching the source, run `pages.yml` with workflow_dispatch. It deploys all of `docs/`, including `assets/email/v1`. Then check `curl -sI …/assets/email/v1/otter-tool.png` → 200. That URL returned `HTTP/2 200` this session [VERIFIED: curl]. Whether the old branch deployment keeps serving until the first Actions deploy is [ASSUMED]; do the switch and the dispatch back to back.

### Pitfall 3: List-Unsubscribe folded into encoded-words
Covered above [VERIFIED probe]. Test the raw bytes, not `msg["List-Unsubscribe"]`, which round-trips fine and hides the bug.

### Pitfall 4: Apps Script URL changes
"New deployment" makes a new URL. Old emails' headers then hit a dead endpoint. The footer link survives (it is a Pages page). Write the rule into `apps_script/README` or the owner steps.

### Pitfall 5: Sheets turns ids into numbers
A hex id like `1234e567…` can parse as scientific notation in `appendRow`. Set column A to plain text (`setNumberFormat('@')` in `setup`). `list_` also filters with `TOKEN_RE`.

### Pitfall 6: httpx does not follow the 302
The list call returns 302 with an empty body, and the code treats that as "no unsubscribes". It must be `follow_redirects=True`, and any non-200 is an error (fail closed).

### Pitfall 7: The web page leaks personalization
`render_web_issue` must hard-code `DEFAULT_GREETING` and `unsubscribe_url=None`. Test: the generated `docs/**/*.html` match no email regex (`[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}`, the same one as `__main__._EMAIL_RE`), contain no `?t=` with 32 hex chars, and contain no `구독 해지` link.

### Pitfall 8: Existing tests assume `WEB_URL is None`
`test_footer_source_and_unsubscribe_without_web_links` and `test_web_links_appear_once_web_url_is_set` (test_render.py:1093-1117) must be rewritten for `SITE_URL`/`issue_url`. `test_only_record_topic_job_has_write_scope` asserts `set(jobs) == {"run", "record-topic"}`; it changes to `{"run", "publish", "deploy-pages"}` and checks `contents: write` only on `publish` and `pages: write`/`id-token: write` only on `deploy-pages`. `test_job_token_only_in_build_and_topic_commit` changes to name the `Commit record and pages` step. `test_actions_pinned_to_commit_sha` should add `pages.yml`.

### Pitfall 9: Stale checkout in a deploy job
If a deploy job checks out `github.sha`, it gets the commit from before the publish push. Upload the artifact in `publish` after the commit (as above). In `pages.yml` (push trigger), `github.sha` is correct.

### Pitfall 10: The test send has no token data before the owner's Google setup
Gate on `UNSUBSCRIBE_ENDPOINT is None`, so plans 1-2 work before Google setup.

## Code Examples

### build_message with headers (send.py)
```python
def build_message(*, subject, sender_addr, to, text, html, list_unsubscribe: str | None = None,
                  one_click: bool = False) -> EmailMessage:
    msg = EmailMessage()
    ...existing headers...
    if list_unsubscribe:
        msg["List-Unsubscribe"] = list_unsubscribe.replace("\r", "").replace("\n", "")
        if one_click:
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    msg.policy = msg.policy.clone(max_line_length=998)  # keep URL headers unfolded (verified)
    return msg
```

### Per-recipient loop (deliver.py)
```python
secret = _env("UNSUBSCRIBE_TOKEN_SECRET") if UNSUBSCRIBE_ENDPOINT else None
gone = fetch_unsubscribed(UNSUBSCRIBE_ENDPOINT, _env("UNSUBSCRIBE_LIST_KEY")) if UNSUBSCRIBE_ENDPOINT else set()
for sub in subscribers:
    t = token(sub.email, secret) if secret else None
    if t in gone:
        unsubscribed += 1
        continue
    link = f"{SITE_URL}unsubscribe/?t={t}" if t else None
    header = f"<mailto:{user}?subject=unsubscribe>" + (f", <{UNSUBSCRIBE_ENDPOINT}?t={t}>" if t else "")
    messages.append(build_message(..., html=render_html(issue, greeting, unsubscribe_url=link),
                                  text=render_text(issue, greeting, unsubscribe_url=link),
                                  list_unsubscribe=header, one_click=bool(t)))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pages "Deploy from a branch" rebuilt on any push | Branch deploy ignores GITHUB_TOKEN pushes; Actions-based deploy (`deploy-pages`) is the supported path for CI-published sites | docs current 2026 | owner switches the source |
| `List-Unsubscribe: <mailto:>` only | mailto + https + `List-Unsubscribe-Post` (RFC 8058); Gmail/Yahoo require it for bulk senders since 2024-02-01 | 2024 | small senders: recommended, not required |
| `WEB_URL = None` gate | `SITE_URL` + per-issue `issue_url()` | this phase | footer links live in test sends (may 404 until send) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Apps Script `doPost` executes on the initial POST, before the 302 is followed | Unsubscribe | one-click from mail servers that do not follow redirects records nothing. The confirm-page path (browser follows) still works. Owner curl step 10 checks it |
| A2 | `Utilities.computeHmacSha256Signature(str, str, UTF_8)` returns signed bytes and matches Python for the test vector | Token | links unsubscribe nobody in 4.1 welcome mails. `selfTest` catches it |
| A3 | "Who has access: Anyone" allows anonymous POST from curl and mail servers | Unsubscribe | one-click and the list call fail. Owner steps 9-10 check it |
| A4 | Gmail's outbound DKIM may not cover List-Unsubscribe; Gmail may not show one-click for this sender | Headers | cosmetic only; the footer link is the main path |
| A5 | Naver Mail's List-Unsubscribe and dark-mode behavior | Dark mode, headers | the checklist records it; mitigate after the test |
| A6 | The old branch deployment keeps serving until the first Actions deploy | Pitfall 2 | brief image breakage in sent mail. Run the dispatch immediately |
| A7 | `POST /pages/builds` accepts the job token with `pages: write` (fallback only) | Pitfall 1 | the fallback fails; use the Actions source |
| A8 | HtmlService shows a "created by another user" banner on consumer accounts | Endpoint | cosmetic; the primary page is on Pages |
| A9 | `e.parameter` merges form-encoded POST bodies | Apps Script | `t` is always in the query string, so unsubscribe does not depend on it. The list call's `action`/`key` do sit in the body; if they are not merged, `list_` never runs. Owner step 9 checks it, and the fallback below removes the dependency |
| A10 | `TextFinder`, `LockService`, `createTemplate` scriptlet escaping behave as used | Apps Script | caught by setup/selfTest/curl steps |

On A9: to remove the dependency, `doPost` can parse `e.postData.contents` as form-urlencoded whenever `e.parameter.action` is missing. Recommend that the executor add this 5-line fallback.

## Open Questions

1. **RESOLVED (04-FIGMA-HOME.md + figma-25-356.png, pulled 2026-11-04 with the Figma MCP; the brand later changed to render.BRAND in 450e1c8, so the png is a layout reference only). Home page layout specifics (Figma 25:356).** The Figma MCP needs `/mcp` authorization in this session, so the frame was not read. Recommendation: the home-page plan starts with a `get_design_context`/screenshot of node 25:356 (after the owner authorizes the Figma MCP), or the owner pastes a screenshot. Section list from ROADMAP 4.1: nav, hero with form (hidden by `SUBSCRIBE_URL = None`), 매주 이런 걸 받아요 (without 바로 써볼 만한 것), sample issue preview (no otter at top), bottom CTA, footer with a privacy-policy link. The privacy-policy page itself belongs to 4.1, so link it only when it exists.
2. **RESOLVED (owner decision at the 04-01 Task 1 checkpoint; recorded in 04-01-SUMMARY.md). What should 지난 호 보기 open: home top or `#archive`?** Recommend `SITE_URL + "#archive"` so the reader lands on the cards. That is one-way per D-02 logic, so the anchor id `archive` must stay.
3. **RESOLVED (inline: no conflict, see answer). Should `data/issues/` overlap Phase 5 archive commit-back (D-20)?** Phase 5 may commit full `archive/<id>/` later. `data/issues/` stays the web source either way. No conflict.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | tests, CLI | ✓ | 0.13.6 | — |
| Python (uv-managed) | all | ✓ | 3.14.10 | — |
| `gh` CLI | Pages settings | ✗ | — | owner uses the GitHub web UI (Settings → Pages → Source: GitHub Actions) |
| Google account + Apps Script | unsubscribe | owner only | — | none; `UNSUBSCRIBE_ENDPOINT = None` keeps the phase shippable |
| Figma MCP | home page design read | needs auth | — | owner screenshot |
| GitHub Pages (live) | assets, site | ✓ (asset URL → 200 this session) | — | — |

## Validation Architecture

(`workflow.nyquist_validation` is false in `.planning/config.json`, but the orchestrator asked for this mapping explicitly.)

| Property | Value |
|----------|-------|
| Framework | pytest ≥9.2 + respx 0.23.1 |
| Config | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run | `uv run pytest tests/test_web.py tests/test_unsubscribe.py tests/test_render.py tests/test_delivery.py tests/test_workflow_static.py -q` |
| Full suite | `uv run pytest && uv run ruff check` |

| Req | Behavior | Test (file) | Type |
|-----|----------|-------------|------|
| WEB-01 | `publish` writes `data/issues/<id>.json` + `docs/issues/<id>/index.html`; idempotent (second run, no diff); preview/test mode → no-op | `tests/test_web.py` (new; `tmp_path` repo root via env override like `NEWSLETTER_TOPICS_PATH`) | unit |
| WEB-01 / D-06 | web HTML has `구독자님`, no email regex hit, no 32-hex token, no `구독 해지` link | test_web.py | unit |
| WEB-01 / D-05 | 판정 근거 shows reason_ko, code vs weights license separately, evidence links on HF/GitHub only; `해당 없음` Claude/GPT hidden; unknown → `확인 필요` | test_web.py / test_render.py | unit |
| WEB-02 | home lists cards newest first, date via `date_line`, top-3 titles, #1 image only when present; subscribe section absent while `SUBSCRIBE_URL is None` | test_web.py | unit |
| DLVR-04 | footer has issue link, home link, `구독 해지` link (when token), reply line kept | test_render.py | unit |
| DLVR-04 | raw message bytes: single-line `List-Unsubscribe: <mailto:…>, <https://…?t=…>`, no `=?utf-8?`, `-Post` only with https | test_delivery.py | unit |
| D-11 | token test vector (both rows above) | tests/test_unsubscribe.py (new) | unit |
| D-13 | respx: POST endpoint → 302 Location → GET echo JSON; ids filtered; counts logged; caplog has no address, token or key | test_unsubscribe.py, test_delivery.py | unit |
| D-13 | list 500 / bad JSON / 302 not followed → DeliveryError, zero messages sent | test_delivery.py | unit |
| D-03 | workflow: `publish` job send-on-main only, `contents: write` only there, `deploy-pages` has `pages: write`+`id-token: write` and no secrets, new secrets only in Deliver, all actions SHA-pinned (incl. pages.yml) | test_workflow_static.py | static |
| DSGN-05 | worst-case email < 92,160 B with max-length unsubscribe link; `color-scheme` meta present | test_render.py | unit |
| DSGN-05 | real inbox light/dark | owner checklist | manual |
| assets | `docs/assets/email/v1` exact set unchanged after publish | test_assets.py (existing) | unit |

Wave 0 gaps: `tests/test_web.py`, `tests/test_unsubscribe.py`; a `NEWSLETTER_REPO_ROOT`/`NEWSLETTER_DOCS_DIR`/`NEWSLETTER_ISSUES_DIR` env override (mirroring `NEWSLETTER_TOPICS_PATH`) so tests never write the real `docs/`.

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no user login) | — |
| V4 Access Control | yes | `LIST_KEY` constant-time compare in Apps Script; Actions secret scoped to Deliver |
| V5 Input Validation | yes | token regex `^[0-9a-f]{32}$` on Pages JS, Apps Script and Python; Jinja autoescape |
| V6 Cryptography | yes | HMAC-SHA256 from stdlib / Utilities; 128-bit truncation |
| V7 Logging | yes | counts only; no token, key, address (existing `_report` redaction + caplog tests) |
| V8 Data Protection | yes | Sheet stores ids only; `data/issues` and `docs/` hold no PII (regex test) |
| V14 Config | yes | SHA-pinned actions; least-privilege job permissions |

| Pattern | STRIDE | Mitigation |
|---------|--------|-----------|
| Scanner prefetch unsubscribes | Tampering | GET never writes (Pages page + doGet); POST only on a button or a receiver one-click |
| Forged tokens | Spoofing | HMAC needs the secret; random ids match nobody |
| CSRF: a third-party page auto-POSTs a known token | Tampering | needs the victim's token (only in their mail); low impact; accept |
| List endpoint scraping | Info disclosure | key in POST body; ids are not reversible without the secret |
| XSS via Claude text on public pages | Tampering | Jinja autoescape; no `|safe` on Issue fields |
| Secret leak in Actions logs | Info disclosure | step-scoped env; no `set -x`; httpx logs at WARNING |
| Header injection via token or endpoint | Tampering | CR/LF stripped; token regex; endpoint is a code constant |

## Recommended plan split (tracer first)

1. **04-01 Tracer: one web issue live + working links.** `SITE_URL`/`issue_url`, minimal `render_web_issue` (web flag, no 판정 근거 yet), `newsletter publish --mode` (data/issues + docs/issues + bare `docs/index.html` list), merged `publish` job + `deploy-pages` job + `pages.yml`, static tests updated, email footer/header 웹에서 보기 / 지난 호 보기 live, template versions bumped. **Owner checkpoint A:** Settings → Pages → Source: GitHub Actions → run `pages.yml` → `curl` asset 200 → one `mode=send` (or wait for the next real send) → `/issues/<id>/` 200.
2. **04-02 Web content and design.** 판정 근거 block (D-05), responsive CSS, home page per Figma 25:356 with 지난 호 cards (D-08), hidden subscribe section (`SUBSCRIBE_URL = None`), PII regex test. **Owner checkpoint B:** preview of the home page and an issue page (local `uv run python -m newsletter publish --mode send` against a fixture, opened in a browser, not committed).
3. **04-03 Unsubscribe backend.** `apps_script/Code.gs`, `newsletter/delivery/unsubscribe.py` (token, fetch), `docs/unsubscribe/` page template, test vector + respx tests. **Owner checkpoint C:** Google setup steps 1-11 → give the `/exec` URL → commit `UNSUBSCRIBE_ENDPOINT`.
4. **04-04 Delivery integration.** Per-recipient link, headers with the folding fix, filter, fail-closed policy, new secrets in Deliver only, worst-case size test updated.
5. **04-05 Inbox check (DSGN-05).** `color-scheme` metas, then **owner checkpoint D:** one `mode=test` send through the full checklist (light/dark, Gmail/Naver, web/app, unsubscribe round trip, header check). Close DSGN-01/02 as already met (record evidence).

Plans 3 and 2 can run in parallel after 1. Plan 4 needs 3. Plan 5 needs 4.

## Sources

### Primary (HIGH)
- Repo files read this session: `newsletter/schema.py`, `newsletter/stages/render.py`, `templates/email.html.j2`, `templates/email.txt.j2`, `newsletter/delivery/{deliver,send,subscribers,notify}.py`, `newsletter/{store,topics,pipeline,__main__}.py`, `.github/workflows/newsletter.yml`, `tests/test_workflow_static.py`, `tests/test_render.py`, `tests/test_assets.py`, `pyproject.toml`, `.gitignore`, `docs/` listing
- Probes run this session: worst-case size (77,611 B), HMAC test vector, header folding before/after, httpx `_redirect_method`, `curl -sI` asset 200 / issues 404, `git ls-remote` action SHAs
- RFC 8058 text — https://www.rfc-editor.org/rfc/rfc8058.txt (redirect, DKIM, cookies)
- GITHUB_TOKEN and Pages — https://docs.github.com/en/actions/concepts/security/github_token
- actions/deploy-pages v5.0.1 README; actions/upload-pages-artifact v5.0.0 action.yml (raw.githubusercontent.com)

### Secondary (MEDIUM)
- Gmail sender guidelines — https://support.google.com/a/answer/81126
- Apps Script Utilities — https://developers.google.com/apps-script/reference/utilities/utilities
- Apps Script web apps — https://developers.google.com/apps-script/guides/web
- Apps Script Content service redirect — https://developers.google.com/apps-script/guides/content
- Apps Script deployments — https://developers.google.com/apps-script/concepts/deployments
- REST Pages builds — https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build

### Tertiary (LOW)
- [You're probably using curl wrong with your Apps Script web app](https://dev.to/googleworkspace/youre-probably-using-curl-wrong-with-your-google-apps-script-web-app-1ed8)
- [Stack Overflow mirror: 405 after 302 but data in sheet](https://backiee.wasmer.app/http_stackoverflow_com/questions/79776622/error-405-moved-temporarily-from-google-apps-script-even-though-server-still-ac)
- [Courier: dark mode email design](https://www.courier.com/blog/dark-mode-email-design), [dev.to mailpeek dark mode](https://dev.to/mailpeek/dark-mode-is-still-breaking-your-html-emails-here-is-the-logic-to-fix-it-g5c)
- [innoq: GITHUB_TOKEN does not trigger Pages](https://www.innoq.com/en/blog/github-actions-automation/) (2020, consistent with the current docs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH (no new packages; actions SHA-verified)
- Static site + publish job: HIGH (repo patterns plus official Pages/GITHUB_TOKEN docs)
- Unsubscribe backend: MEDIUM (Apps Script runtime behaviors gated by owner self-test/curl)
- Inbox/dark mode: LOW-MEDIUM (vendor blogs; Naver unobserved) → owner checklist

**Research date:** 2026-11-04
**Valid until:** 2026-12-04 (Apps Script and Gmail policy can shift; re-check the action SHAs if planning slips)
