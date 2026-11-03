---
phase: 02-evidence-practical-verdicts
plan: 06
status: complete
---

# 02-06 Summary: push, live preview, owner review

- Push: 1533ddc..63b4009 to origin/main. CI run #14 green.
- Live preview run ID: **41589810089** (newsletter, commit 63b4009). Green in 1m57s.
- test send run ID: (owner, 2026-11-03) mode=test on 63b4009. Owner confirmed the mail arrived ("test도 잘 됐어").
- mode=send was not run in this plan (out of scope).

## Owner review (answers given in chat, 2026-11-03)

| Item | Owner answer |
|---|---|
| D-02 also covers the ANLY-02 Claude/GPT reason and the per-side code/weights licenses. The email shows the one-line labels only, and the rest goes to the Phase 4 web issue (ROADMAP Phase 4 SC5). | Yes, "웹에서만" |
| Copyleft (GPL/AGPL/LGPL/MPL) → `조건부` (research A1) | Yes, 조건부 |
| Fine-tunes of meta-llama / google-gemma base models → `조건부` even when their own card says Apache | Yes, lower to 조건부 |
| D-09 reading: code MIT plus weights that exist but can't be read → `확인 필요` (G5 DeepSeek-V3) | Not asked separately. It follows the conservative D-03 rule the owner chose. |

## Not done

- **Artifact audit:** coverage, token and email grep on issue-41589810089. The artifact was not downloaded locally, and the logs need a login.
- **Code-side guards that stand in:**
  - the httpx logger is set to WARNING
  - a caplog test checks that no token is logged
  - a test checks that `enriched.json` contains no authors, `@` or Bearer
- **Carried to Phase 5:** a run-report audit.
