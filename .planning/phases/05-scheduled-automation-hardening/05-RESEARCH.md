# Phase 5: Scheduled Automation & Hardening - Research

**Researched:** 2026-11-04
**Domain:** GitHub Actions scheduling, concurrency and commit-back; Python checkpointing, send ledger, run report
**Confidence:** HIGH for the GitHub features and the in-repo code. MEDIUM for the 60-day activity rule, which GitHub does not define.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Schedule (AUTO-01)
- **D-01 (owner):** A Monday 06:00 preview, then an automatic 08:00 send.
  - **06:00 KST run:** builds the previous KST week (Mon-Sun, `newsletter.week`), checkpoints it, and sends `mode=test` to `TEST_RECIPIENT`.
  - **08:00 KST run:** sends the issue built at 06:00 without rebuilding it.
  - If the 06:00 build is missing or failed, the 08:00 run builds first, then sends. The stale guard (D-03) still applies.
  - Both runs use a cron with `timezone: "Asia/Seoul"` where the runner supports it, and the UTC fallback otherwise: `0 21 * * 0` for 06:00 KST and `0 23 * * 0` for 08:00 KST. Research confirms which syntax GitHub supports today.
  - **Reversibility:** reversible.
- **D-02 (owner):** Pause switch. A repository variable `SEND_PAUSED` (Settings → Variables) set to `true` makes the scheduled 08:00 send skip that week. It logs and reports "paused" and sends nothing. The 06:00 preview still runs.
  - Manual `workflow_dispatch` keeps working whatever the variable says, so the owner can still send by hand.
  - Owners can flip the variable from a phone browser.

### Late and failed runs (AUTO-05)
- **D-03 (owner):** A week is sendable only until Monday 23:59 KST of the send day.
  - A scheduled or re-run send after that refuses to mail the old week. It reports that refusal to the owner, and nothing goes out.
  - GitHub schedule delays are expected, so an 08:00 run that starts late still sends within the same Monday.
  - A manual `mode=send` with an explicit `--week` outside the window needs a deliberate override flag (research names it), so the owner can recover on purpose.
- **D-04:** Checkpoints. Each stage (fetch, enrich, analyze, explainer and the rest, render) stores its output per week in `archive/<week>/`.
  - A re-run reuses them unless `--force-stage <name>` is given, so there is no re-fetch and no new Claude billing.
  - A partial failure still commits `archive/` back (AUTO-03).
- **D-05:** Send ledger (DLVR-05). `(week, SHA-256(normalized email))` entries are committed after each successful recipient batch.
  - A re-run skips everyone already in the ledger for that week.
  - The ledger holds hashes only, never an address. Normalization matches the Phase 4 token normalization (strip and lowercase).
  - The ledger must survive a run that stops partway through. Research decides whether it is committed per batch or written to the artifact and committed in an always-run step.

### Run report (AUTO-04)
- **D-06 (owner):** One report mail every week, to `TEST_RECIPIENT`.
  - On success it gives counts only: recipients, sent, skipped (ledger or unsubscribed), unsubscribed count, and the web issue link.
  - On failure or refusal it gives the stage and error class, as the existing failure notice does. On a pause it says "paused".
  - It has no addresses, names or Claude text.
  - It reuses the existing `notify` path where it can.
- **D-07:** The weekly archive commit (publish job plus ledger) keeps the public repo's schedule from GitHub's 60-day auto-disable. Research confirms that commits by `GITHUB_TOKEN` count as activity. If they don't, it names the alternative.

### Hardening (AUTO-03)
- **D-08:** One concurrency group for the newsletter workflow, so the 06:00 and 08:00 runs and any manual run never overlap.
  - The pending run waits; it is not cancelled.
  - The publish, record-topic and ledger commit steps share one serialized push path. There are no push races with the Pages commit.
- **D-09:** Every action stays SHA-pinned, and `contents: write` stays only on the commit job (existing static tests extend to the new schedule triggers).

### Claude's Discretion
- How the scheduled runs map to workflow inputs (schedule event to mode test or send by cron string)
- Checkpoint file format and the force-stage UX
- Exact wording of the run report, which must pass the humanizer lint (Korean, 해요체)

### Deferred Ideas (OUT OF SCOPE)
- A custom domain plus a dedicated sending service (deliverability). The welcome landed in spam once on 2026-11-04.
- Approval-gated sending. The owner chose automatic sending with a pause switch instead.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTO-01 | Workflow runs every Monday 08:00 KST via `cron` + `timezone: "Asia/Seoul"` (UTC fallback `0 23 * * 0`) | Timezone key is GA since 2026-03-19 (§Schedule). Two crons plus `github.event.schedule` mapping (Pattern 1). |
| AUTO-03 | Concurrency group, SHA pins, `contents: write` only on the commit step, `archive/` committed back on partial failure | `queue: max` (Pattern 5), `always()` commit job (Pattern 4), `ref: ${{ github.ref }}` checkout (Pitfall 1). |
| AUTO-04 | Weekly run-report mail; weekly archive commit keeps the schedule alive | `report` command replaces `notify-failure` (Pattern 7). 60-day rule analysis (§Keepalive). |
| AUTO-05 | Checkpoint reuse unless `--force-stage`; stale-issue guard | Per-stage checkpoints (Pattern 3). `--allow-stale` guard in `run_deliver` (Pattern 2). |
| DLVR-05 | Committed ledger keyed by (week, email hash) stops a duplicate send | `data/ledger/<week>.json`, HMAC key, write per SMTP send, commit in `always()` job (Pattern 6). |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Code decides the verdicts and Claude only explains. This phase adds no Claude text. The run report is fixed code copy.
- Any generated newsletter text follows the humanizer rules. The report copy must pass `newsletter.stages.humanize.lint` with 해요체.
- Public repo. Never commit the subscriber CSV. Never log emails, names or credentials. Never enable `smtplib` debug output. This applies to the ledger, `archive/` and the report.
- Compute weeks in `Asia/Seoul`, never runner UTC. The stale guard uses `newsletter.week.KST`.
- Email HTML uses tables plus inline CSS and stays under 90 KB. Unchanged by this phase.
- Commit author: `silber60 <81203897+silber60@users.noreply.github.com>`. The workflow already sets it (`newsletter.yml:121-122`).
- Do not change the frozen `Issue` schema. Checkpoints sit beside `issue.json` and never change its shape.

## Summary

GitHub Actions has supported an IANA `timezone:` key on `on.schedule` entries since 2026-03-19, so D-01 uses `cron: "0 6 * * 1"` and `cron: "0 8 * * 1"`, each with `timezone: "Asia/Seoul"`. The UTC fallback is not needed. Each run reads the cron that fired from `github.event.schedule`. Map only the exact string `'0 8 * * 1'` to `send` and everything else to `test`, so a mapping surprise fails safe. Schedule events carry no `inputs`, so `inputs.mode` and `inputs.week` are empty. The blank week already resolves to `previous_iso_week(now KST)`.

The best way for the 08:00 run to reuse the 06:00 build is to commit the de-personalized `archive/<week>/` from a commit job that runs on every test or send run, success or failure. The 08:00 run then checks out the branch tip and its `build` step finds every checkpoint and makes zero HTTP and zero Claude calls. A cross-run artifact download would need run-id discovery, an `actions: read` token in the run job and the 14-day retention, so it is rejected. One trap decides the design: a re-run, and a run queued behind another, keeps the original `GITHUB_SHA`. The default `actions/checkout` would then miss the archive and the ledger that the previous run committed. Both checkouts must pass `ref: ${{ github.ref }}` so they fetch the branch tip (verified in `actions/checkout` source).

The send ledger goes in `data/ledger/<week>.json`. Deliver rewrites it atomically after each successful `smtp.send_message`, the run job uploads it with `if: always()`, and the commit job commits it with `if: always()`. Do not use plain SHA-256 of the address: anyone can hash a guessed address and test membership in the public repo. Do not use the existing unsubscribe token either: it is a live one-click unsubscribe capability, and publishing it would let anyone unsubscribe every reader. Use a domain-separated HMAC-SHA256 keyed with the existing `UNSUBSCRIBE_TOKEN_SECRET`. That needs no new secret, and the secret already reaches the Deliver step. Concurrency uses `queue: max` (GA 2026-05-07). Without it, a third queued run cancels the pending one, which breaks D-08's "the pending run waits".

**Primary recommendation:** Build a tracer first: schedule plus mode mapping, then the pause and stale guards in `run_deliver`, then the always-run commit job with `ref: ${{ github.ref }}`. Add per-stage checkpoints, then the HMAC ledger, then the `report` command. Finish with an owner rehearsal: a refused W44 send, a twice-run test build, and the first unattended Monday, 2026-11-09.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trigger time, mode mapping, pause variable plumbing | GitHub Actions workflow (`newsletter.yml`) | — | Only the workflow sees `github.event.schedule` and `vars`. It passes plain env values to Python. |
| Pause decision, stale-week decision | Python `newsletter.delivery.deliver` | — | Unit-testable. Runs before any secret-using network call. |
| Stage checkpoints and force-stage | Python `newsletter.pipeline` + `newsletter.store` | Workflow input `force_stage` | Pipeline owns stage order. The workflow only forwards the value through env. |
| Ledger write and skip | Python `deliver` + `send` (callback) | Workflow artifact + commit job | Python writes per send. The workflow carries the file to a write-scoped job. |
| Durable state (archive, ledger, topic record, web data) | Git repo `main` via the commit job | — | Survives runs and re-runs. The only `contents: write` job. |
| Run report mail | Python `newsletter.delivery.notify` (`report`) | Run job `always()` step | Reuses the SMTP path and the status file. |
| Web deploy | `deploy-pages` job | `pages.yml` for human pushes | Unchanged pattern from Phase 4. |

## Standard Stack

No new packages. Everything uses the stdlib (`hmac`, `hashlib`, `os.replace`, `zoneinfo`) and the pinned actions already in the repo.

| Component | Version / Pin | Purpose | Source |
|-----------|---------------|---------|--------|
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1) | Add `ref: ${{ github.ref }}` | [VERIFIED: .github/workflows/newsletter.yml:42] |
| `actions/upload-artifact` | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` (v7.0.2) | Issue + ledger artifacts, `overwrite: true` | [VERIFIED: newsletter.yml:59] |
| `actions/download-artifact` | `9000827ccba6bdab643e8b6fd33ac0654aef8333` (v8.0.2) | Same-run download in the commit job | [VERIFIED: newsletter.yml:106] |
| `actions/upload-pages-artifact` / `deploy-pages` | `fc324d35…` / `368f8252…` | Unchanged | [VERIFIED: newsletter.yml:131,149] |
| `on.schedule[].timezone` | GA 2026-03-19 | 06:00 / 08:00 KST crons | [CITED: github.blog/changelog/2026-03-19-github-actions-late-march-2026-updates] |
| `concurrency.queue: max` | GA 2026-05-07 | Up to 100 pending runs, none cancelled | [CITED: github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues] |
| Python | 3.14 via uv, `uv sync --frozen` | Unchanged | [VERIFIED: pyproject.toml] |

## Package Legitimacy Audit

No external packages are installed in this phase. **Removed [SLOP]:** none. **Flagged [SUS]:** none.

Do not adopt third-party keepalive actions. `gautamkrishnar/keepalive-workflow`, the best-known one, now shows "Access to this repository has been disabled by GitHub Staff due to a violation of GitHub's terms of service." [VERIFIED: WebFetch github.com/gautamkrishnar/keepalive-workflow, 2026-11-04]

## Architecture Patterns

### System Architecture Diagram

```
 cron 0 6 * * 1 (Asia/Seoul) ─┐                       workflow_dispatch(mode, week, force_stage, allow_stale)
 cron 0 8 * * 1 (Asia/Seoul) ─┤                                        │
                              ▼                                        ▼
            concurrency group "newsletter" (queue: max, cancel-in-progress: false)
                              │
                     job run (contents: read)
   MODE = schedule ? (event.schedule=='0 8 * * 1' ? send : test) : inputs.mode
   checkout ref=github.ref (branch TIP: has committed archive/ + data/ledger/)
                              │
   build --week "" ──► checkpoints in archive/<week>/ ? reuse : compute (HF / Claude)
                              │  upload artifact issue-<run_id>  (always, overwrite)
                              ▼
   deliver --mode MODE
     send: paused? ──yes──► report.json outcome=paused, exit 0
           stale (today KST != Monday after week_end) and not --allow-stale? ──► StaleIssueError, exit 1
           live list + unsubscribe list (fail closed)
           skip ledger keys ──► SMTP one by one ──► after each: rewrite data/ledger/<week>.json
                              │  upload artifact ledger-<run_id> (always, send only)
                              ▼
   report --mode MODE (always): send → mail outcome sent/paused/refused/failed; test → mail only on failure
                              │
                     job publish (contents: write)   if: always() && main && not preview
   checkout TIP ──► download issue + ledger artifacts (continue-on-error)
     outcome==sent ? record-topic + publish web : skip
   git add archive data/ledger data/explainer_topics.json data/issues docs ──► commit ──► pull --rebase/push x3
                              │ outcome==sent
                              ▼
                     job deploy-pages (pages: write, id-token: write)
```

### Recommended file layout (new or changed)

```
newsletter/
├── pipeline.py          # stage table + checkpoint load/save, --force-stage invalidation
├── store.py             # checkpoint_path(), write_json_atomic(), ledger_dir()
├── ledger.py            # NEW: key(email, secret), load(week), Ledger.add() atomic rewrite
├── week.py              # send_day(issue_id), is_sendable(issue_id, now)
├── __main__.py          # build --force-stage, deliver --allow-stale, report
├── errors.py            # StaleIssueError(stage="deliver")
└── delivery/
    ├── deliver.py       # pause → stale → secrets → lists → ledger skip → send(on_sent)
    ├── send.py          # send_messages(..., on_sent=None)
    └── notify.py        # build_report_text(); send_report(mode) (notify-failure kept as alias)
data/ledger/<YYYY-Www>.json   # committed, hashes only
archive/<YYYY-Www>/           # committed (de-personalized); archive/current.json stays ignored
```

### Pattern 1: Two timezone crons and the mode mapping

**What:** Two schedule entries. Mode is computed once at job level from the event.
**Verified facts:**
- "You can now specify an IANA timezone on your cron schedules instead of being locked to UTC." Published 2026-03-19. [CITED: github.blog changelog 2026-03-19]
- The docs example puts `timezone:` beside `cron:` in the same list item. The triggering cron is in `github.event.schedule`, and the docs example compares it to the cron string. [CITED: docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows]
- Scheduled runs use the default branch's latest commit. They can be delayed at the top of the hour, and under very high load some are dropped. [CITED: same page]
- Asia/Seoul has no DST, so the docs' DST skip rule never applies. [ASSUMED]
- `jobs.<id>.env` allows `github`, `inputs` and `vars`. `steps.env` and `steps.if` also allow `env`. `jobs.<id>.if` allows only `github`, `needs`, `vars` and `inputs`, not `env`. An undefined `vars.X` is `""`. [CITED: docs.github.com/en/actions/reference/workflows-and-actions/contexts]

```yaml
# Source: docs.github.com events-that-trigger-workflows (schedule) + contexts availability table
on:
  schedule:
    - cron: "0 6 * * 1"        # Monday 06:00 KST: build + test mail (D-01)
      timezone: "Asia/Seoul"
    - cron: "0 8 * * 1"        # Monday 08:00 KST: send (D-01)
      timezone: "Asia/Seoul"
  workflow_dispatch:
    inputs:
      mode: { type: choice, options: [preview, test, send], default: preview, required: true }
      week: { type: string, required: false, default: "" }
      force_stage:
        type: choice
        options: [none, fetch, analyze, enrich, notes, trend, highlight, explainer, headline, polish]
        default: none
      allow_stale: { type: boolean, default: false }

jobs:
  run:
    env:
      # Only the exact 08:00 cron sends. Anything else on a schedule is a test (fail safe).
      MODE: ${{ github.event_name == 'schedule' && (github.event.schedule == '0 8 * * 1' && 'send' || 'test') || inputs.mode }}
      WEEK_INPUT: ${{ inputs.week }}
      FORCE_STAGE: ${{ inputs.force_stage }}
      ALLOW_STALE: ${{ inputs.allow_stale }}
    outputs:
      mode: ${{ env.MODE }}
      outcome: ${{ steps.deliver.outputs.outcome }}
```

On a schedule event the `inputs.*` values are empty strings. `WEEK_INPUT=""` resolves to `previous_iso_week(datetime.now(KST))` (`__main__.py:123`), and `FORCE_STAGE=""` and `ALLOW_STALE=""` mean off. Python must treat `""` and `"none"` as no force, and accept only `"true"` as allow. Keep `${{ }}` out of every `run:` line. `test_no_expression_interpolation_in_run_lines` already enforces this.

**UTC fallback:** not needed. If the owner ever has to revert, the fallback is `cron: "0 21 * * 0"` for test and `cron: "0 23 * * 0"` for send, with no `timezone`. The send-mapping string then becomes `'0 23 * * 0'`. Keep the mapping string in one place, the `MODE` line, and assert it in the static test.

### Pattern 2: Pause and stale guard, in Python, before any network

The order in `run_deliver("send")` is: (1) pause, (2) stale, (3) `_env` secrets, (4) live list and unsubscribe list, (5) ledger filter, (6) SMTP. Steps 1 and 2 touch no secret and no network.

```python
# newsletter/week.py  (KST only; parse_week returns (Monday, Sunday) [VERIFIED: newsletter/week.py:22-31])
def send_day(issue_id: str) -> date:
    _, sun = parse_week(issue_id)
    return sun + timedelta(days=1)          # the Monday after week_end

def is_sendable(issue_id: str, now: datetime) -> bool:
    return now.astimezone(KST).date() == send_day(issue_id)   # 00:00:00..23:59:59 KST that Monday
```

- The window is exactly the KST calendar Monday after `week_end`. An early send (a week still running) is refused too.
- Override: CLI flag `--allow-stale` on `deliver`, fed from the dispatch input `allow_stale` through env `ALLOW_STALE`. Schedule runs can never set it.
- Pause: the Deliver step gets `SEND_PAUSED: ${{ github.event_name == 'schedule' && vars.SEND_PAUSED || '' }}`. Python pauses only when `.strip().lower() == "true"`, and only in send mode. Manual dispatch always passes `''` (D-02).
- Paused: write `out/report.json` `{"outcome": "paused", "issue_id": ...}`, append `outcome=paused` to `$GITHUB_OUTPUT`, return 0. Publish is skipped.
- Stale: raise `StaleIssueError(PipelineError)` with `stage = "deliver"`. The existing `_report` writes `out/status.json`. The job fails visibly, and the report maps that class to the refused copy.
- Example: W45 runs Mon 11-02 to Sun 11-08 and its send day is 2026-11-09. W44 (sent by hand today, 11-04) is now outside its window, so a W44 resend is refused without `--allow-stale`.

### Pattern 3: Per-stage checkpoints and `--force-stage`

**What run_build does today** [VERIFIED: newsletter/pipeline.py:33-110]: fetch (HTTP), select (code), analyze (Claude), enrich (HTTP), verdicts.finalize (code), notes (Claude), trend (Claude), highlight (Claude), explainer (Claude, reads `topics.load_past()`), headline (Claude), Issue, humanize.polish_issue (Claude), render (code). It writes `raw.json`, `selected.json`, `enriched.json` (EVID-01 records only), `issue.json`, `email.html`, `email.txt` and `archive/current.json`. Only `raw.json` and `issue.json` can serve as checkpoints today. Nothing is read back.

**Design:**
- Linear stage list: `fetch, analyze, enrich, notes, trend, highlight, explainer, headline, polish`. `render` always re-runs: it is deterministic code with zero cost.
- One file per paid stage, `archive/<week>/checkpoints/<stage>.json`, as `{"version": 1, "issue_id", "stage", "data"}`. The public `raw.json`, `enriched.json`, `selected.json` and `issue.json` keep their current shapes.
  - fetch: `raw.json` is already the checkpoint. Rebuild entries with `[HfEntry.model_validate(d) for d in raw["entries"]]` (`fetch.py:189`), plus `method` and `fetched_at`.
  - analyze, enrich, notes: `list[Item]`.
  - trend: `str | None`. highlight: `list[Highlight]`. explainer: `Explainer | None`. headline: `str`.
  - polish: `issue.json` itself.
- `select` and `verdicts.finalize` are code, so recompute them. Persisting the enrich output after `finalize` is fine as long as the reload path does not call `finalize` twice. Pick one and test it.
- A checkpoint is valid only if the file parses, `issue_id` matches, `version == 1` and the payload validates. An invalid file means recompute that stage and every later one. It never raises.
- `--force-stage X` recomputes X and every stage after it. `"none"` or `""` means none. Unknown names are rejected by argparse `choices`.
- Create the Claude client lazily, only when a Claude stage must run. A full-reuse build then needs no `ANTHROPIC_API_KEY` call path. The step still receives the key.
- Log `checkpoint=<stage> reused|computed` (ids only) so the owner can see "no billing" in the Actions log.
- Write each checkpoint right after its stage succeeds, atomically (`tmp` + `os.replace`). A crash in `headline` then keeps analyze through explainer for the re-run.

**Build reuse between 06:00 and 08:00 (Q4 recommendation): commit `archive/`.**

| Option | Verdict |
|--------|---------|
| Commit `archive/<week>/` in the always-run commit job (CONTEXT D-04) | **Use.** The 08:00 checkout of the branch tip has every checkpoint. Re-runs and manual runs on any later day reuse it too. No new token scope. |
| Cross-run `download-artifact` with `run-id` + `github-token` | Reject. It needs the 06:00 run id (an API lookup), `actions: read` in the run job (the artifact list endpoint is an Actions read permission [CITED: docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens]) and the 14-day retention. A missing artifact also leaves it no resume path. |

PII check of `archive/`: `trim_entry` keeps only paper keys, `title`, `numComments` and the org name. It "Drops authors / submittedBy profile data" [VERIFIED: newsletter/stages/fetch.py:53-63]. `email.html` and `email.txt` are rendered with `PREVIEW_GREETING = "구독자님"` and no `unsubscribe_url` [VERIFIED: pipeline.py:30,106-107], so they carry no token. Deliver writes nothing under `archive/`. `issue.json` is already public through `data/issues/`. Add a test that a built archive has no `@` address pattern and no `?t=`.

`.gitignore` [VERIFIED: .gitignore lines "archive/" and "out/"]: remove `archive/`, add `archive/current.json`. The pointer is per-run state, and every run re-runs `build`, which rewrites it (`pipeline.py:108`). Keep `out/` ignored.

### Pattern 4: One always-run commit job (serialized push)

Keep the job id `publish`. The static tests and `deploy-pages` `needs: publish` already depend on it. It becomes the one write path for archive, ledger, topic record and web.

```yaml
  publish:
    needs: run
    # Every test/send run on main, even a failed or cancelled one (AUTO-03). Preview commits nothing.
    if: ${{ always() && github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || inputs.mode != 'preview') }}
    permissions:
      contents: write
    env:
      MODE: ${{ needs.run.outputs.mode }}
      OUTCOME: ${{ needs.run.outputs.outcome }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          ref: ${{ github.ref }}          # branch tip, not the run's frozen GITHUB_SHA
          persist-credentials: false
      # setup-uv + uv sync --frozen (unchanged)
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333  # v8.0.2
        continue-on-error: true
        with: { name: "issue-${{ github.run_id }}", path: archive/ }
      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333  # v8.0.2
        continue-on-error: true
        with: { name: "ledger-${{ github.run_id }}", path: data/ledger/ }
      - name: Append explainer topic
        if: ${{ env.OUTCOME == 'sent' }}
        run: uv run python -m newsletter record-topic --mode "$MODE"
      - name: Publish web pages
        if: ${{ env.OUTCOME == 'sent' }}
        run: uv run python -m newsletter publish --mode "$MODE"
      - name: Commit archive, ledger, record and pages
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          git add -- archive data/ledger data/explainer_topics.json data/issues docs
          git diff --cached --quiet && exit 0
          git config user.name silber60
          git config user.email 81203897+silber60@users.noreply.github.com
          git commit -m "chore(newsletter): archive, ledger and publish"
          for i in 1 2 3; do
            git pull --rebase "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" main \
              && git push "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:main && exit 0
            sleep $((i * 5))
          done
          exit 1
      - uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9  # v5.0.0
        if: ${{ env.OUTCOME == 'sent' }}
        with: { path: docs/ }
  deploy-pages:
    needs: [run, publish]
    if: ${{ needs.run.outputs.outcome == 'sent' && needs.publish.result == 'success' }}
```

- The `if: always()` job runs even when `run` failed or was cancelled. Its `MODE` comes from `needs.run.outputs.mode`. The job `if` recomputes "not preview" from `github` and `inputs`, because `env` is not allowed in `jobs.<id>.if`. [CITED: contexts table]
- Push races: all bot commits happen in this one job, inside the workflow-level group, so runs never race each other. Only a human push can race, and rebase plus retry handles that. `pages.yml` only deploys and never commits. A `GITHUB_TOKEN` push triggers neither `pages.yml` nor `ci.yml`, so nothing double-deploys (unchanged Phase 4 reasoning, `pages.yml:3-5`).
- Conflicts on rebase are practically impossible: the bot alone writes `archive/` and `data/ledger/`, and the human never edits them.

### Pattern 5: Concurrency that never cancels a pending run

- "By default, any existing `pending` job or workflow in the same concurrency group will be canceled." With `queue: max`, "Up to 100 jobs or workflow runs can be `pending`". "The combination of `queue: max` and `cancel-in-progress: true` is not allowed." [CITED: docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax; changelog 2026-05-07]
- Without `queue: max`, this happens: 06:00 is running late, 08:00 is pending, the owner dispatches by hand, and the 08:00 send is cancelled. That violates D-08.

```yaml
concurrency:
  group: newsletter
  cancel-in-progress: false
  queue: max
```

Apply the same three lines in `import-subscribers.yml`, which shares the group, so both workflows treat the group the same way. Whether mixed `queue` values in one group are defined is not documented [ASSUMED risk]. FIFO order inside the queue is not documented either. Correctness never depends on order: the ledger, checkpoints and stale guard make any order safe.

### Pattern 6: Send ledger (DLVR-05)

- **Location:** `data/ledger/<YYYY-Www>.json`, committed. `ledger_dir()` honors `NEWSLETTER_LEDGER_DIR`, like `web.issues_dir()` [VERIFIED: newsletter/web.py:45-47]. A conftest fixture must set it, so tests never write into the repo.
- **Format:** `{"version": 1, "issue_id": "2026-W45", "scheme": "hmac-sha256-ledger-v1", "sent": [sorted 64-hex keys]}`. Sorting hides send order. The file holds no counts beyond the list length and no timestamps.
- **Key:** `hmac.new(secret, b"ledger-v1:" + email.strip().lower().encode(), sha256).hexdigest()`, with `secret = UNSUBSCRIBE_TOKEN_SECRET`. The normalization matches `unsubscribe.token` (`email.strip().lower()`) [VERIFIED: newsletter/delivery/unsubscribe.py:36-40].
  - Not plain SHA-256: in a public repo, a plain hash of an address lets anyone confirm "alice@example.com subscribes". [ASSUMED: standard dictionary-test reasoning]
  - Not the unsubscribe token: the token is a 32-hex HMAC over the address, sent in every footer and List-Unsubscribe header [VERIFIED: unsubscribe.py:22,36-40; deliver.py:61-62]. Apps Script honors it as a one-click unsubscribe, so committing tokens would let anyone unsubscribe everyone.
  - The `ledger-v1:` prefix makes the key unrelated to the token under the same secret. The docstring says the secret never changes (`unsubscribe.py:7-8`), so ledgers stay valid.
  - D-05 literally says `SHA-256(normalized email)`. HMAC-SHA256 is a strengthening, so the planner should record it as A1 for owner acknowledgement.
- **Write timing:** `send_messages(..., on_sent=callback)` calls `on_sent(i)` right after each `smtp.send_message(msg)` (`send.py:85`). Deliver's callback adds the key and atomically rewrites the ledger file. A mid-run SMTP failure still raises `DeliveryError` (unchanged), and the file already holds every successful send.
- **Commit timing (D-05 open choice):** use the artifact plus the always-run commit job, not a commit per batch. A per-batch commit would need `contents: write` in the run job, which breaks D-09. Run job step: `upload-artifact` `name: ledger-${{ github.run_id }}`, `path: data/ledger/`, `if: ${{ always() && env.MODE == 'send' }}`, `if-no-files-found: ignore`, `overwrite: true`.
- **Skip:** after the live-list fetch, drop every subscriber whose key is already in `load(week)`. Count those as `skipped_ledger`. The ledger skip runs after the unsubscribe filter, so the counts stay separate.
- **Residual risk:** if the runner dies hard before the `always()` upload, that attempt's progress is lost and a re-run resends to those readers. For a list of a few readers that is acceptable. Document it.
- **Scope:** test mode never reads or writes the ledger.

### Pattern 7: Run report (extends notify.py)

- Add a `report --mode test|send` command and keep `notify-failure` as an alias. The step runs `if: ${{ always() && env.MODE != 'preview' }}`. It gets SMTP_USER, SMTP_PASSWORD and TEST_RECIPIENT, like today's Failure notice step.
- Inputs: `out/report.json` (written by deliver on success or pause) and `out/status.json` (written by `_report` on failure, `__main__.py:162-165`).
- Decision table:

| mode | status.json | report.json outcome | Mail |
|------|-------------|---------------------|------|
| send | — | sent | `[발송 완료]` counts + `SITE_URL/issues/<id>/` |
| send | — | paused | `[일시정지]` |
| send | error_class=StaleIssueError | — | `[발송 거부]` stage + class |
| send | other | — | `[실패]` stage + class + run URL |
| test | present | — | `[실패]` (today's behavior) |
| test | absent | — | none. The test mail is the 06:00 signal (one report a week, D-06). |
| any | neither file (cancelled or timeout) | — | `[실패]` with `stage: unknown` |

- Counts only: recipients, sent, skipped_ledger, unsubscribed, skipped_rows. No address, name or Claude text.
- Body copy that passes `humanize.lint` (checked this session; every line returned `[]`):
  - `모닥로그 AI 리포트 2026-W45 호를 보냈어요.`
  - `이번 주 발송은 멈춰 두었어요. 아무에게도 보내지 않았어요.`
  - `발송 기한(월요일 23:59)이 지나서 2026-W45 호를 보내지 않았어요.`
  - `모닥로그 AI 리포트 2026-W45 실행이 실패했어요.`
  - `다시 보내려면 Actions에서 mode=send로 직접 실행해 주세요.`
- Today's notice says `실행이 실패했습니다.` (합쇼체, `notify.py:54`). Change it to 해요체. Keep the subject `[실패] 모닥로그 AI 리포트 {id}`, which `tests/test_cli.py:198` asserts.
- The report goes out from the run job, before the commit job. If only the commit job fails, the owner relies on GitHub's own failed-run notification. Scheduled-run notifications go to the user who last changed the cron syntax. [CITED: events-that-trigger-workflows]

### Anti-Patterns to Avoid

- **Default checkout in a re-runnable sender:** re-runs keep the original `GITHUB_SHA` [CITED: docs.github.com/.../re-run-workflows-and-jobs], so the ledger the failed attempt committed would be invisible. The result is a duplicate send.
- **Mode from wall-clock hour in Python:** a delayed 06:00 run would become a send. Map from `github.event.schedule`.
- **Pause in YAML only, by skipping the Deliver step:** then no "paused" report and no test. Pass the value down and decide in Python.
- **`needs.run.result == 'success'` gating the commit:** it loses the archive and ledger on partial failure. That is today's publish condition (`newsletter.yml:87`), and it must change.
- **Reusing the artifact name across attempts without `overwrite: true`:** v4+ artifacts are immutable, and the upload fails when the name already exists. [CITED: github.com/actions/upload-artifact]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Local-time cron | UTC math, or a Python hour check | `timezone: "Asia/Seoul"` | GA, and documented |
| Run queueing | A lock file or API polling for other runs | `concurrency` + `queue: max` | Native, nothing cancelled |
| Cross-run state | Artifact lookup through the REST API | Commit to `main` + `ref: ${{ github.ref }}` | Survives retention and re-runs |
| Keyed hashing | `sha256(secret + email)` | `hmac.new(..., hashlib.sha256)` | Avoids length-extension and concatenation mistakes |
| Keepalive | Dummy commits or a third-party keepalive action | The real weekly content commit, plus an optional `gh workflow enable` | The best-known keepalive repo is ToS-disabled |

## Keepalive: the 60-day auto-disable (D-07)

- Rule: "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." [CITED: docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows]
- What counts as "activity" is **not documented**. Whether a `GITHUB_TOKEN` push counts got **no observation**: no GitHub source says yes or no. The claim stays [ASSUMED] and cannot be falsified here before the 60-day horizon.
- Our weekly commit is real content authored as `silber60`, unlike the empty commits that keepalive tools push. Commit-pushing keepalive tools assume bot commits count. [CITED: github.com/WaterLemons2k/scheduled-workflow-activity-action (third-party)]
- **Recommendation:** (1) rely on the weekly commit (D-07). (2) Add a cheap, documented safety net: the commit job gets `actions: write` and runs `gh workflow enable newsletter.yml` (`PUT /repos/{owner}/{repo}/actions/workflows/{id}/enable`, an Actions write permission [CITED: fine-grained permissions table]). The claim that a re-enable resets the counter is third-party only (PhrozenByte/gh-workflow-immortality) [ASSUMED]. The step is harmless if the claim is false. It widens the commit job's token, so make it owner-approved (A3), or drop it. (3) The owner's normal human commits also count, almost certainly. (4) Recovery if the schedule is ever disabled: Actions tab → newsletter → Enable workflow.

## Common Pitfalls

### Pitfall 1: Frozen SHA on queued runs and re-runs
**What goes wrong:** The 08:00 run, queued while 06:00 is still committing, or a "Re-run failed jobs", checks out the old SHA. It rebuilds (Claude billing) and ignores the ledger (duplicate mail).
**Why:** Re-runs use "the same `GITHUB_SHA` (commit SHA) and `GITHUB_REF`" [CITED]. `actions/checkout` with an empty `ref` sets `result.commit = github.context.sha`. With `ref` given and not a 40/64-hex SHA, `commit` stays unset and the ref tip is fetched [VERIFIED: raw.githubusercontent.com/actions/checkout/main/src/input-helper.ts].
**Avoid:** `ref: ${{ github.ref }}` on both checkouts. Add a static test.

### Pitfall 2: Pending run cancelled
**Avoid:** `queue: max` (Pattern 5). Add a static test that it is present and that `cancel-in-progress: false` stays.

### Pitfall 3: Ledger or checkpoints lost on failure
**What goes wrong:** Today the upload step uses `if: ${{ !cancelled() }}` (`newsletter.yml:58`), and the publish job needs `needs.run.result == 'success'`. A timeout or cancel drops everything.
**Avoid:** `always()` on both uploads, on the report step and on the commit job. `continue-on-error: true` on the downloads.

### Pitfall 4: Publishing an unsent issue
**What goes wrong:** A paused run exits 0, so `success` would publish the web page and the topic record for a week nobody received.
**Avoid:** Gate publish and deploy on `outcome == 'sent'`, written by deliver to `$GITHUB_OUTPUT`. A partial send that failed has no outcome and publishes on the completing re-run.

### Pitfall 5: Tests writing into the real repo
**Avoid:** Add `NEWSLETTER_LEDGER_DIR` to the fixtures that already redirect `NEWSLETTER_ARCHIVE_DIR` (`tests/conftest.py:621-622`). Test that no test leaves `data/ledger/` changed.

### Pitfall 6: Secret-scoping static tests break
**What goes wrong:** Expressions change from `inputs.mode == 'test'` to `env.MODE == 'test'`. `test_delivery_secret_values_are_mode_gated` and `test_subscriber_list_key_send_gated_in_deliver_only` assert the old strings.
**Avoid:** Update them deliberately and keep their intent: secrets reach only Deliver and Report, gated by mode. `text.count("UNSUBSCRIBE_") == 4` must still hold. The Deliver step is the only place `UNSUBSCRIBE_TOKEN_SECRET` appears, and the ledger reuses it there.

### Pitfall 7: Schedule mapping string drift
**What goes wrong:** Someone edits the cron, but not the `'0 8 * * 1'` literal in `MODE`, and 08:00 silently becomes a test.
**Avoid:** A static test that the send literal equals the second cron line. The fail-safe direction (test, not send) holds either way.

### Pitfall 8: Week resolution on a late run
`previous_iso_week` on Tuesday still returns last week (Tuesday minus 7 days). The stale guard then refuses. That is correct, but the owner must read "[발송 거부]" as "dispatch with allow_stale", never as a bug.

### Pitfall 9: Mixed concurrency settings with import-subscribers
Give both workflows the same group block. 04.1-06 deletes `import-subscribers.yml` later, and its static tests then go too.

## Code Examples

```python
# newsletter/delivery/send.py: on_sent callback, unchanged error handling (send.py:67-94)
def send_messages(messages, *, user, password, pause=0.0, on_sent=None) -> int:
    ...
            for i, msg in enumerate(messages):
                if i and pause > 0:
                    time.sleep(pause)
                smtp.send_message(msg)
                sent += 1
                if on_sent is not None:
                    on_sent(i)          # ledger write; must not log the address
```

```python
# newsletter/ledger.py
LEDGER_SCHEME = "hmac-sha256-ledger-v1"

def key(email: str, secret: str) -> str:
    norm = email.strip().lower()                    # same as unsubscribe.token
    return hmac.new(secret.encode(), b"ledger-v1:" + norm.encode(), hashlib.sha256).hexdigest()

def save(issue_id: str, keys: set[str]) -> None:   # atomic: tmp + os.replace
    path = ledger_dir() / f"{issue_id}.json"
    tmp = path.with_suffix(".json.tmp")
    store.write_json(tmp, {"version": 1, "issue_id": issue_id, "scheme": LEDGER_SCHEME,
                           "sent": sorted(keys)})
    os.replace(tmp, path)
```

```python
# newsletter/delivery/deliver.py: order inside run_deliver("send")
issue = load_current_issue()
if _paused():                       # SEND_PAUSED == "true" (schedule only, set by YAML)
    return _finish({"outcome": "paused", "issue_id": issue.issue_id})
if not allow_stale and not week.is_sendable(issue.issue_id, datetime.now(KST)):
    raise StaleIssueError("issue outside its send day")
user, password = _env("SMTP_USER"), _env("SMTP_PASSWORD")
...  # live list, unsubscribe list, ledger skip, send with on_sent
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| UTC-only cron (`0 23 * * 0`) | `timezone: "Asia/Seoul"` beside `cron` | 2026-03-19 | Use KST crons directly |
| One pending run per group, older pending cancelled | `queue: max`, up to 100 pending | 2026-05-07 | Meets D-08 "pending waits" |
| Mutable artifacts (v3) | Immutable artifacts, `overwrite: true` (v4+) | v4 | Re-runs need `overwrite` |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The ledger uses HMAC-SHA256 keyed with `UNSUBSCRIBE_TOKEN_SECRET` instead of D-05's literal plain SHA-256 | Pattern 6 | Low. **RESOLVED (owner, 2026-11-04):** HMAC-SHA256 approved ("비밀값으로 서명한 해시"); key = HMAC-SHA256(UNSUBSCRIBE_TOKEN_SECRET, "ledger-v1:" + strip().lower()). Planned in 05-03. |
| A2 | `github.event.schedule` holds exactly the cron string (`'0 8 * * 1'`) when `timezone` is set | Pattern 1 | Fail-safe: 08:00 becomes a test and nothing reaches subscribers. **RESOLVED (owner):** verified live on the first Monday (2026-11-09) from the Trigger log line, 05-05 Task 3; fails safe to test. |
| A3 | A weekly `GITHUB_TOKEN` push counts as repo activity. The optional `gh workflow enable` resets the 60-day counter. | Keepalive | The schedule silently disables after 60 quiet days. **RESOLVED (owner: "안 넣음"):** no `actions: write` re-enable step; the weekly content commit is the keepalive; recovery is Actions tab → Enable workflow. |
| A4 | Artifacts from attempt 1 are downloadable by name in a re-run attempt of the same run | Pattern 4/6 | The commit job misses the ledger on a commit-only re-run. `continue-on-error` keeps it from failing, and the next send re-reads the committed state. |
| A5 | Job outputs (`mode: ${{ env.MODE }}`) are set even when the run job fails | Pattern 4 | The commit job `MODE` would be empty. Publish steps are gated on outcome anyway, and the job `if` does not use outputs. |
| A6 | Mixed `queue` settings across workflows in one group are undefined | Pattern 5 | Set both the same. |
| A7 | Asia/Seoul has no DST | Pattern 1 | None in practice |

## Open Questions (all RESOLVED 2026-11-04 by the owner)

1. **Catch-up cron (owner call):** a third schedule, for example `0 10 * * 1` mapped to send, would recover from a dropped 08:00 run. GitHub documents that scheduled runs can be dropped under load. The ledger makes it idempotent. It adds a second report on normal weeks unless an "all already in ledger" run skips the mail. Recommendation: not in this phase. Owner guidance instead: if no report arrives by 10:00, dispatch `mode=send`. **RESOLVED:** no catch-up cron; the owner dispatches by hand if no report by 10:00.
2. **`actions: write` re-enable step (A3):** include it or not. Recommendation: include it in plan 4 behind an owner checkpoint. **RESOLVED:** not included (owner: "안 넣음"); the weekly content commit is the keepalive.
3. **Git history growth:** `raw.json` is trimmed but holds roughly 50-200 entries. Expect a few hundred KB per week. Acceptable for years. Revisit only if it becomes a problem. **RESOLVED:** accepted as is.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv + Python 3.14 | tests | ✓ | local uv at `~/.local/bin/uv` | — |
| Test suite | regression | ✓ | `uv run pytest -q` green in about 13 s (2026-11-04) | — |
| `gh` CLI (local) | owner API checks | ✗ | — | GitHub web UI for variables and the Actions tab |
| `gh` on `ubuntu-latest` runners | optional enable step | [ASSUMED] preinstalled | — | `curl -X PUT` against the REST endpoint |
| Repository variable `SEND_PAUSED` | D-02 | not yet created | — | Undefined evaluates to `""` (not paused) [CITED: contexts] |

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | yes | Least-privilege `GITHUB_TOKEN`: `contents: read` by default. `contents: write` (plus the optional `actions: write`) only on `publish`. `pages`/`id-token` only on deploy. |
| V5 Input Validation | yes | Dispatch inputs reach the shell only through env. `week` is validated by `parse_week`. `force_stage` uses argparse `choices`. `allow_stale` is accepted only as the exact `"true"`. |
| V6 Cryptography | yes | stdlib `hmac` + SHA-256 with domain separation. Never concatenate a secret into a hash. |
| V7 Logging | yes | Counts and ids only. The ledger callback never logs. No `set -x` or `echo` in the commit script. |

| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Membership disclosure through a public ledger | Information disclosure | HMAC key, not plain SHA-256 |
| Mass unsubscribe through leaked tokens | Tampering / DoS | Never commit unsubscribe tokens; the ledger key is domain-separated |
| Duplicate mail on re-run | Repudiation / abuse | Ledger + tip checkout + `always()` commit |
| Late mail of an old week | Integrity | `is_sendable` KST guard + explicit `allow_stale` |
| Script injection through dispatch inputs | Tampering | No `${{ }}` in `run:` lines (static test) |
| Over-broad token | Elevation | Static test: write scopes only in `publish` and deploy |

## Static Tests to Add or Extend (`tests/test_workflow_static.py`)

- The schedule has exactly two entries, `0 6 * * 1` and `0 8 * * 1`, each followed by `timezone: "Asia/Seoul"`. The `MODE` line maps only `'0 8 * * 1'` to `send`, and that literal matches the second cron.
- `test_dispatch_inputs`: still one `workflow_dispatch`, plus `force_stage` (with `none` default) and `allow_stale` (boolean, default false). `inputs.week`, `inputs.force_stage` and `inputs.allow_stale` each appear exactly once, in the run job env.
- Concurrency: `group: newsletter`, `cancel-in-progress: false` and `queue: max` in both `newsletter.yml` and `import-subscribers.yml`.
- Every `actions/checkout` in `newsletter.yml` has `ref: ${{ github.ref }}` and `persist-credentials: false`.
- `SEND_PAUSED` appears only in the Deliver step, gated by `github.event_name == 'schedule'`. `vars.` appears nowhere else.
- The issue and ledger uploads use `always()` and `overwrite: true`. The ledger upload has `path: data/ledger/`.
- `publish` job `if` contains `always()`, `refs/heads/main` and the not-preview clause, and does **not** contain `needs.run.result == 'success'`. The commit step `git add` lists `archive data/ledger data/explainer_topics.json data/issues docs`. The record-topic, publish and upload-pages steps are gated on `OUTCOME == 'sent'`. `deploy-pages` is gated on `needs.run.outputs.outcome == 'sent'`.
- The secret-scoping tests are rewritten for `env.MODE` and the `Report` step name. Delivery secrets appear only in Deliver and Report. `UNSUBSCRIBE_` count stays 4.
- If A3 is approved: `actions: write` appears only in the `publish` header.

Python tests: `week.is_sendable` boundaries (Monday 00:00:00 and 23:59:59 KST, Sunday, Tuesday, a UTC-aware `now`). Paused send makes zero list fetches and zero SMTP connections. Stale send makes zero network calls and raises `StaleIssueError`. `--allow-stale` lets it through. Checkpoint reuse makes 0 `FakeAnthropic` calls and 0 respx calls on the second build. `--force-stage notes` recomputes notes onward and reuses analyze and enrich. A corrupt checkpoint is recomputed. On the ledger: a mid-send `FakeSMTP` failure leaves the first N keys on disk, a re-run sends only the rest, the file holds no `@`, and the key differs from `unsubscribe.token`. On the report: every row of the decision table, every copy line lint-clean, no address in the body. The archive holds no address and no `?t=`.

## Recommended Plan Split (tracer first)

1. **Schedule tracer + guards:** crons, `MODE` mapping, `queue: max`, `ref: ${{ github.ref }}`, inputs `allow_stale`, `SEND_PAUSED` plumbing, `week.is_sendable`, `StaleIssueError`, pause outcome + `$GITHUB_OUTPUT`, and the publish/deploy gating on `outcome == 'sent'`. Static tests updated.
2. **Commit-back + checkpoints:** `.gitignore` change, always-run `publish` commit job committing `archive/`, per-stage checkpoints, lazy Claude client, `--force-stage` + dispatch input. Reuse tests.
3. **Ledger:** `newsletter/ledger.py`, the `on_sent` callback, the skip filter, the ledger artifact + commit path, the fixtures env var.
4. **Run report + keepalive:** a `report` command (alias `notify-failure`), the decision table, 해요체 copy with lint tests, the always step, and the optional `gh workflow enable` step (owner decision A3).
5. **Owner verification (checkpoint):**
   - (a) Optionally create the variable `SEND_PAUSED=false` (Settings → Secrets and variables → Actions → Variables), so it can be flipped from a phone later.
   - (b) Dispatch `mode=test` twice. The second log shows `checkpoint=* reused` and no Claude calls, and `archive/2026-W44/` is committed.
   - (c) Dispatch `mode=send` for W44 without `allow_stale`. Expect `[발송 거부]` and no subscriber mail.
   - (d) Confirm the Actions tab lists the schedule.
   - (e) Watch Monday 2026-11-09: the 06:00 `[TEST]` mail, the 08:00 send, `[발송 완료]` with counts, and `data/ledger/2026-W45.json` committed with no `@`.

## Sources

### Primary (HIGH)
- In-repo files read this session: `.github/workflows/newsletter.yml`, `pages.yml`, `import-subscribers.yml`, `ci.yml`, `tests/test_workflow_static.py`, `newsletter/pipeline.py`, `store.py`, `week.py`, `__main__.py`, `errors.py`, `web.py`, `newsletter/delivery/{deliver,notify,members,unsubscribe,send}.py`, `newsletter/stages/fetch.py`, `.gitignore`, `pyproject.toml`
- [GitHub Changelog 2026-03-19: timezone support for scheduled workflows](https://github.blog/changelog/2026-03-19-github-actions-late-march-2026-updates/)
- [GitHub Changelog 2026-05-07: concurrency groups allow larger queues](https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues)
- [Events that trigger workflows: schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [Workflow syntax: concurrency, queue](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [Contexts availability](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)
- [Re-run workflows (same GITHUB_SHA)](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
- [Disable and enable workflows (60-day rule)](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
- [REST: enable a workflow](https://docs.github.com/en/rest/actions/workflows#enable-a-workflow) and [fine-grained permissions table](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens)
- [actions/checkout input-helper.ts](https://raw.githubusercontent.com/actions/checkout/main/src/input-helper.ts)
- [actions/upload-artifact README](https://github.com/actions/upload-artifact), [actions/download-artifact README](https://github.com/actions/download-artifact)

### Secondary / Tertiary (LOW, third-party)
- [WaterLemons2k/scheduled-workflow-activity-action](https://github.com/WaterLemons2k/scheduled-workflow-activity-action): bot-commit keepalive
- [PhrozenByte/gh-workflow-immortality](https://github.com/PhrozenByte/gh-workflow-immortality): API re-enable claim
- [gautamkrishnar/keepalive-workflow](https://github.com/gautamkrishnar/keepalive-workflow): now disabled by GitHub Staff

## Metadata

**Confidence breakdown:**
- Schedule, concurrency, checkout, artifact behavior: HIGH (official docs, changelog and action source this session)
- Checkpoint, ledger and report design: HIGH (grounded in code read this session)
- 60-day activity semantics: LOW-MEDIUM (undocumented by GitHub)

**Research date:** 2026-11-04
**Valid until:** 2026-12-04
