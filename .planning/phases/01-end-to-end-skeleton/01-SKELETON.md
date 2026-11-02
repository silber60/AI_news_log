# Walking Skeleton — AI 주간 모델 뉴스레터 (Weekly AI Model Brief)

**Phase:** 1
**Generated:** 2026-11-02

## Capability Proven End-to-End

The owner triggers one manual GitHub Actions run that fetches last week's (KST) HF Papers Top 10, has Claude fill a minimal analysis into the frozen `Issue` schema, renders a table email, and either uploads a de-personalized preview artifact or mails it to `TEST_RECIPIENT` / the `SUBSCRIBERS_CSV` list through Gmail SMTP, with no address, name or credential in public logs.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Runtime | Python 3.14, managed by uv (`pyproject.toml` + committed `uv.lock`, `uv sync --frozen` in CI) | Fixed by project research; uv gives reproducible installs on the Actions runner and installs 3.14 locally (Mac has only 3.9.6) |
| Packaging | Plain uv project, no build backend; package `newsletter/` at repo root, run as `python -m newsletter <cmd>`; pytest `pythonpath = ["."]` | Batch job, not a library; nothing to publish |
| Execution host | GitHub Actions `workflow_dispatch` (`mode = preview \| test \| send`, `week`) on `ubuntu-latest`; cron arrives in Phase 5 | No server; repo `silber60/AI_news_log` is public |
| Data layer | Files only. `archive/<YYYY-Www>/raw.json`, `selected.json`, `issue.json`, `email.html` (구독자님), `email.txt`; `archive/current.json` hands the resolved week from build to deliver; `out/status.json` records `{stage, error_class}` | Stage outputs are inspectable and become Phase 5 checkpoints. Phase 1 keeps them on the runner + artifact only (D-20); `.gitignore` excludes `archive/` and `out/` until Phase 5 commit-back |
| Contract | Frozen Pydantic `Issue` (`newsletter/schema.py`, `schema_version: 1`) with snapshot `schema/issue.schema.v1.json` guarded by a test. Phase 2-5 fields (verdicts, `trend_ko`, `highlights`, `explainer`) exist now with safe defaults | Later phases fill fields, never add/rename (CLAUDE.md, D-16, D-17) |
| Claude integration | One `messages.parse(output_format=ItemAnalysisLLM)` call per paper; Claude returns only `title_ko`, `ai_type`, `summary_ko`, `use_ideas_ko`. Code assembles `Item`/`Issue` from HF facts + analyses. Retry once with feedback, then fail the run (D-15) | Code owns ranks, URLs, verdicts; isolated per-item retry; small schema |
| HTTP | httpx client + tenacity (HF only); Anthropic SDK's own `max_retries` | Research "don't hand-roll" table |
| Rendering | Jinja2 (`templates/email.html.j2` autoescaped, `templates/email.txt.j2` plain) + `css_inline`; byte-size gate < 90 KB | Email-safe tables, inline CSS, KR font stack (DSGN-03/04) |
| Delivery | stdlib `EmailMessage` (multipart/alternative) + `smtplib.SMTP_SSL("smtp.gmail.com", 465)`; one message per recipient; sender display name `AI 주간 모델 브리프` | DLVR-03, D-02 |
| Secret isolation | Step-scoped env in the workflow: build step gets only `ANTHROPIC_API_KEY`; SMTP/subscriber secrets only in Deliver and Failure-notice steps; only `newsletter/delivery/` reads those env names | AUTO-02, criterion 1, DLVR-06 |
| Error model | `newsletter/errors.py` hierarchy (`PipelineError` with `stage`); `__main__` top-level handler prints `stage=X error=ClassName`, writes `out/status.json`, exits 1, no traceback unless `NEWSLETTER_DEBUG=1` | Exception text can carry addresses; public logs |
| Auth | None for users. Gmail app password in `SMTP_PASSWORD` secret | Single-owner tool |
| Directory layout | `newsletter/{__main__,errors,week,schema,store,pipeline}.py`, `newsletter/stages/{fetch,select,analyze,render}.py`, `newsletter/delivery/{subscribers,send,deliver,notify}.py`, `prompts/`, `templates/`, `schema/`, `tests/` (+ `tests/fixtures/`), `.github/workflows/{newsletter,ci}.yml` | Stage-per-module; delivery boundary is a package |

## Stack Touched in Phase 1

- [ ] Project scaffold: uv project, `uv.lock`, ruff, pytest (+ respx), CI workflow
- [ ] Entry point: `python -m newsletter build | deliver | notify-failure`
- [ ] Data: real write of `archive/<week>/*.json|html|txt` and real read of `issue.json` by deliver
- [ ] External APIs: HF `daily_papers` (week= + date= fallback), Anthropic `messages.parse`, Gmail SMTP
- [ ] Deployment: `.github/workflows/newsletter.yml` run manually on Actions (preview artifact, test mail, send mail)

## Out of Scope (Deferred to Later Slices)

- Evidence enrichment and code-decided 상업적 사용 / PoC / GPU verdicts, Claude/GPT 사용 가능 여부, 트렌드 총평 (Phase 2; schema fields exist with defaults and are not rendered)
- Humanizer lint + polish pass, "이번 주 바로 써볼 만한 것" highlight section, 기술 해설 코너 (Phase 3; Phase 1 ships only the humanizer core subset inside the system prompt, D-18)
- Figma-based 640px design, `List-Unsubscribe`, footer unsubscribe line, GitHub Pages web version and archive index (Phase 4)
- Monday cron, send ledger, checkpoint reuse, stale-issue guard, SHA-pinned actions, archive commit-back, weekly run report (Phase 5; Phase 1 sends only a minimal failure notice, D-13)

## Subsequent Slice Plan

- Phase 2: reader sees code-decided practical verdicts with evidence links, Claude/GPT applicability, and a weekly trend line
- Phase 3: every generated sentence passes the Korean humanizer lint; top highlight section and weekly explainer corner appear
- Phase 4: the email matches the Figma design in Naver/Gmail and every issue is browsable on GitHub Pages
- Phase 5: the issue arrives every Monday 08:00 KST unattended, re-runs never double-send, owner gets a run report
