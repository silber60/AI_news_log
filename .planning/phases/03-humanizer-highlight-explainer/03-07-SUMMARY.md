---
phase: 03-humanizer-highlight-explainer
plan: 07
subsystem: verification
status: complete
tags: [live-run, owner-checkpoint, fonts, highlight]
requires: [03-01, 03-02, 03-03, 03-04, 03-05, 03-06]
provides:
  - Live proof of Phase 3 on real data and inboxes
  - Owner decision: Issue schema v4 (highlight tags 데모 / Claude/GPT 에이전트, demo_url)
key-files:
  created: []
  modified:
    - newsletter/schema.py
    - schema/issue.schema.v4.json
    - newsletter/stages/highlight.py
    - prompts/highlight.md
    - templates/email.html.j2
    - templates/email.txt.j2
decisions:
  - "Owner (2026-11-04): highlight candidates widened to Claude/GPT 직접 사용 items and HF Space demos, demo first; schema v3 -> v4 (commit a895af6)"
  - "Owner: fonts render fine in Gmail and Naver (D-09, D-14 checklist passes)"
---

# 03-07 Summary: live runs and owner review

## Runs (workflow_dispatch, main)

| Run | ID | Commit | Result |
|-----|----|--------|--------|
| newsletter #17 | 41749484803 | 6339932 | green; 이번 주 바로 써볼 만한 것 showed the fallback line |
| newsletter #18 | 41749504943 | 6339932 | green; same empty highlight section |
| newsletter #19 | 41751066208 | a895af6 | green (2m 56s); owner confirmed the highlight section is filled |

record-topic ran as a job in #19 and took 0s, so it was skipped. It runs only for mode=send, and no send was made in this plan.

## Gap found and fixed

After #17/#18 the highlight section was empty. Candidates were only items Claude labelled a Skill/GPTs fit, and no item that week had one. The owner asked to also include agents usable in Claude/GPT and items with a demo page, preferring demos. The owner chose a schema bump (v4) over reusing the old tags:

- `Highlight.tag` adds `Claude/GPT 에이전트` (claude_gpt 직접 사용) and `데모` (HF Space).
- `Highlight.demo_url` is code-owned: the HF Space, else the project page. The email shows `데모 써보기 →` or `프로젝트 페이지 →`.
- Candidates are sorted with demo items first. Prompt v3 prefers demo items, then agents, then Skill/GPTs.
- An empty pick list while candidates exist gets one retry.
- Label 어떻게 만들지 -> 어떻게 써 볼지.
- The worst-case email is 78,550 B, under the 92,160 B cap.

## Font check (D-09, D-14)

The owner reports that fonts render correctly in Gmail and Naver after the per-table font stack (03-05). There is no serif fallback.

## Not done here

- Claude did not audit the job log for #19. Job logs need a GitHub sign-in, and the API was rate-limited. The owner verified the delivered email instead.
- mode=send was not run, per plan. The first record-topic commit will come from the owner's own send.
