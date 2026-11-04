# Phase 5: Scheduled Automation & Hardening - Context

**Gathered:** 2026-11-04
**Status:** Ready for planning

<domain>
## Phase Boundary

From this phase on, the newsletter goes out every Monday with nobody touching it (AUTO-01, AUTO-03, AUTO-04, AUTO-05, DLVR-05):

- **Monday 06:00 KST:** a scheduled build of the previous KST week, then a `mode=test` mail to the owner.
- **Monday 08:00 KST:** a scheduled `mode=send` of that same built issue to the live subscriber list (Phase 4.1).
- **Re-run safety:**
  - Re-runs reuse stage checkpoints, so there is no re-fetch and no new Claude billing.
  - A committed hash ledger stops a duplicate send.
  - A stale-week guard stops a late run.
  - Runs never overlap.
  - `archive/` is committed back even after a partial failure.
- **Weekly run report:** the owner gets one each week.
- **Pause switch:** the owner can stop a week's send.

Out of scope: new content features, custom domain or ESP migration, and per-subscriber topics (v2).

Phase 4.1 Task 3's leftover round trip and the 04.1-06 CSV cleanup still belong to Phase 4.1. The cleanup runs after the first live-list send, so it may land during or after this phase but stays tracked there.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/ROADMAP.md` (Phase 5 section, success criteria 1-4)
- `.planning/REQUIREMENTS.md`: AUTO-01, AUTO-03, AUTO-04, AUTO-05, DLVR-05 (AUTO-02 is already done)
- `.claude/CLAUDE.md`: KST weeks, public repo (no PII in logs or ledger), commit author
- `.github/workflows/newsletter.yml`, `pages.yml`, `import-subscribers.yml`, `tests/test_workflow_static.py`: the current jobs and static guards
- `newsletter/pipeline.py`, `newsletter/store.py`, `newsletter/week.py`, `newsletter/__main__.py`: the build stages and archive layout
- `newsletter/delivery/deliver.py`, `notify.py`, `members.py`, `unsubscribe.py`: send path, fail-closed live list, failure notice
- `.planning/phases/04.1-public-subscribe-instant-welcome/04.1-CONTEXT.md`: the live list is the send source; welcome mails are separate

</canonical_refs>

<code_context>
## Existing Code Insights

- The workflow comment says "Manual dispatch only in Phase 1 (AUTO-02). The Monday cron arrives in Phase 5."
- The `publish` job already commits `data/issues` and `docs` on send. The ledger and checkpoints should share that serialized commit path.
- `notify-failure` already mails the owner a stage and error class. The run report extends it.
- `previous_iso_week(datetime.now(KST))` already gives the KST week.

</code_context>

<specifics>
## Specific Ideas

- The owner asked: "월요일 8시마다 자동으로 나가? 내가 따로 send 안보내도돼?" After this phase the answer is yes. The owner only flips `SEND_PAUSED` to skip a week.

</specifics>

<deferred>
## Deferred Ideas

- A custom domain plus a dedicated sending service (deliverability). The welcome landed in spam once on 2026-11-04.
- Approval-gated sending. The owner chose automatic sending with a pause switch instead.

</deferred>

---
*Phase: 05-scheduled-automation-hardening*
*Context gathered: 2026-11-04*
