# Phase 4: Figma Design, Email Template & Web Archive - Context

**Gathered:** 2026-11-04
**Status:** Ready for planning

<domain>
## Phase Boundary

The email design from Phase 1.1 (Figma v2) is already live. This phase adds:

- **One public website on GitHub Pages**, in the style of 뉴닉. The home page follows the Figma subscribe landing frame and adds 지난 호 cards. Each sent issue also gets its own web page (WEB-01, WEB-02).
- **Reason and license detail on the web issue.** This is what the email leaves out (Phase 2 D-02, roadmap SC5).
- **Click-to-unsubscribe.** A signed link goes to a confirm page, the click is recorded in a Google Sheet through Apps Script, and the weekly send skips anyone on that list. The `List-Unsubscribe` header is added too (DLVR-04).
- **Footer links that work.** 웹에서 보기 and 지난 호 보기 point to the site.
- **A real-inbox check, now including dark mode** (DSGN-05).

Out of scope for this phase:
- Phase 4.1 handles subscribing: the form submit, adding the row to the Sheet, the welcome issue, and moving the subscriber list off `SUBSCRIBERS_CSV`.
- Phase 5 handles the cron, the send ledger and the run report.

</domain>

<decisions>
## Implementation Decisions

### Site and hosting
- **D-01:** Everything goes on GitHub Pages at `https://silber60.github.io/AI_news_log/`. That covers the home page (subscribe hero plus 지난 호 cards), the issue pages and the unsubscribe confirm page. Netlify is dropped. The subscribe backend is Google Apps Script either way, so Netlify adds nothing. The owner asked for one site where 지난 호 보기 lands, "뉴닉처럼". — **Reversibility:** costly — moving hosts later changes every published issue URL and the footer links in already-sent emails.
- **D-02:** Issue URL: `https://silber60.github.io/AI_news_log/issues/<issue_id>/`, e.g. `/issues/2026-W45/`. — **Reversibility:** one-way — sent emails link to this URL forever, so it must never change after the first send.
- **D-03:** Web pages are published only on `mode=send`, never on preview or test. Before the send, a test email's 웹에서 보기 link may 404. Publishing works like the Phase 3 `record-topic` job: a separate job with `contents: write`, `needs: run`, running only for send on main. It reads the run artifact, commits the generated pages under `docs/` as `silber60 <81203897+silber60@users.noreply.github.com>`, and is idempotent per issue_id.
- **D-04:** No Figma pass first; go straight to code. The home page follows the existing Figma frame `Website / Subscribe landing (desktop 1280)`, node 25:356 in file `qyJcGii2MLHTbi4W9mPZkx`. Keep the owner's earlier edits: no otter at the top of the 지난 호 미리보기, and no 바로 써볼 만한 것 in "매주 이런 걸 받아요". Fonts are IBM Plex Sans KR. The owner checks a preview of the result.

### Web issue page
- **D-05 (Claude's default; area not discussed):** The web issue reuses the email design. Under each card it adds an always-open "판정 근거" block with each verdict's `reason_ko`, the Claude/GPT reason, the code license and weights license listed separately, and their evidence links. No JavaScript is needed. Unknown values stay `확인 필요`, and the `해당 없음` Claude/GPT verdict stays hidden (Phase 2 D-11).
- **D-06:** The web copy is de-personalized: the generic greeting (e.g. "구독자님"), no unsubscribe token, and no address or name anywhere.

### 지난 호 (archive)
- **D-07:** 지난 호 is a section of the home page, not something inside the email. The email footer only links to it. The owner asked for past issues "차곡차곡 모아서".
- **D-08 (Claude's default; the owner did not pick a card format):** Cards are newest first. Each shows the send date, `headline_ko`, the Top 3 model names, and the #1 image when one exists.
- **D-09:** The subscribe form section is built now but hidden until Phase 4.1 sets its endpoint. A code constant such as `SUBSCRIBE_URL = None` keeps it off, the same pattern as `WEB_URL` today. The owner chose "자리만, 4.1에서 켬".

### Unsubscribe and footer (DLVR-04)
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

### Inbox check (DSGN-05)
- **D-16:** One owner `mode=test` send is checked in Gmail web, the Gmail app, Naver web and the Naver app, in light and dark mode. Light mode fonts already pass (Phase 3). The email stays under 92,160 B.

### Claude's Discretion
- Static site generation details: the Jinja templates, how the home page and index data are regenerated from committed issue JSON, and the CSS approach.
- Web issue layout details beyond D-05.
- Card format details beyond D-08.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and requirements
- `.planning/ROADMAP.md` (Phase 4 and Phase 4.1 sections): goals and success criteria. Phase 4.1's Netlify direction is superseded by D-01.
- `.planning/REQUIREMENTS.md`: DSGN-01, DSGN-02, DSGN-05, DLVR-04, WEB-01, WEB-02, SUBS-01/03/04 (4.1)
- `.claude/CLAUDE.md`: public-repo rules (no addresses or names in the repo or logs), commit author, week in Asia/Seoul

### Prior decisions
- `.planning/phases/02-evidence-practical-verdicts/02-CONTEXT.md`: D-02 (reasons only on the web), D-09 (code-only license phrase), D-11 (hide `해당 없음`)
- `.planning/phases/03-humanizer-highlight-explainer/03-CONTEXT.md`: D-06/D-15 (the record-topic job pattern that D-03 here copies)
- `.planning/phases/01.1-newsletter-design-v2/01.1-FIGMA-SPEC.md`: the email design that the web issue reuses

### Design
- Figma file `qyJcGii2MLHTbi4W9mPZkx`, node 25:356 `Website / Subscribe landing (desktop 1280)`: the home page layout

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `templates/email.html.j2` + `newsletter/stages/render.py`: card, verdict line and section macros. `WEB_URL = None` already gates the footer links.
- `docs/assets/email/v1/`: otter images and fonts already served by GitHub Pages
- `newsletter/__main__.py` `record-topic` and the `record-topic` job in `.github/workflows/newsletter.yml`: the pattern for a send-only commit job
- `archive/<issue_id>/issue.json` (run artifact): the source for web pages
- `newsletter/schema.py`: `Issue` v4 already holds every reason, license and evidence field the web page needs. No schema change is expected.

### Established Patterns
- The build step has exactly one `secrets.` (ANTHROPIC_API_KEY). Delivery secrets are scoped to the deliver step (`tests/test_workflow_static.py`).
- Logs carry counts and codes only, never addresses or Claude text.

### Integration Points
- `newsletter/delivery/deliver.py`: add the `List-Unsubscribe` headers, add a per-recipient unsubscribe link, and filter by the Sheet's unsubscribe list.
- `render.py`: render the web variant (D-05, D-06) and set `WEB_URL` per issue.

</code_context>

<specifics>
## Specific Ideas

- "뉴닉처럼": one site where past issues are collected and you can subscribe, and the email's 지난 호 보기 lands there.
- Owner flow, verbatim intent: 1) build a web page, 2) collect past issues there, 3) put the subscribe page on it, 4) 지난 호 보기 opens it.

</specifics>

<deferred>
## Deferred Ideas

- Backfilling issues sent before Phase 4 into the archive. Their artifacts expire after 90 days, so it could be done once by hand if wanted.
- A custom domain for the site.

</deferred>

---
*Phase: 04-figma-design-email-template-web-archive*
*Context gathered: 2026-11-04*
