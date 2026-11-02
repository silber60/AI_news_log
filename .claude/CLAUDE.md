# AI 주간 모델 뉴스레터 — Project Guide

<!-- GSD:project-start -->
Weekly Monday 08:00 KST newsletter: HF Papers Top 10 → evidence enrichment → Claude analysis → 640px table HTML email → Gmail SMTP to `SUBSCRIBERS_CSV`, run by GitHub Actions. Public repo under `silber60`.

Planning docs: `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/research/`.
<!-- GSD:project-end -->

<!-- GSD:workflow-start -->
## Workflow

- Work phase by phase via GSD: `/gsd:discuss-phase N` → `/gsd:plan-phase N` → `/gsd:execute-phase N`.
- Do not change the frozen `Issue` schema contract outside a planned phase.

## Hard rules

- Code decides license / PoC / GPU verdicts from HF/GitHub evidence; Claude only explains. Unknown → `확인 필요`.
- All Claude-generated newsletter text must follow the humanizer rules (`~/.claude/skills/humanizer/SKILL.md`, ported to `prompts/humanizer_ko.md`).
- Public repo: never commit subscriber CSV, never log emails/names/credentials, never enable `smtplib` debug output.
- Compute weeks in `Asia/Seoul`, never runner UTC.
- Email HTML: tables + inline CSS, system Korean font stack, < 90 KB.
- Commit author: `silber60 <81203897+silber60@users.noreply.github.com>`.
<!-- GSD:workflow-end -->
