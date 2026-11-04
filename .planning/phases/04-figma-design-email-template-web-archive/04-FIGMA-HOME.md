# Figma home page reference (node 25:356)

File `qyJcGii2MLHTbi4W9mPZkx`, frame `Website / Subscribe landing (desktop 1280)`, 1280 x 2922.
Screenshot: `figma-25-356.png` (in this folder, 614 x 1400). Pulled on 2026-11-04 with the Figma MCP (`get_metadata` + `get_screenshot`). For exact copy and colors, an executor with Figma MCP access should call `get_design_context` on these node ids. That call requires loading the `figma:figma-design-to-code` skill first.

Sections, top to bottom (content column x=120, width 1040):

| Node | Section | Contents |
|------|---------|----------|
| 25:357 | Nav (h 91) | logo: otter 36px + "모닥로그 AI 리포트"; right side: "지난 호" text link, "구독하기" button (nav_cta) |
| 25:365 | Hero (h 747) | left (544w): tags, hero_title, hero_body, hero_otter image (544x315); right (440w): Subscribe form (hero) with form_title, 이름 field, 이메일 field, consent checkbox + text, "무료로 구독하기" submit, note |
| 25:387 | What you get (h 566) | centered title + sub; two cards (508w each), each with a 140px otter, a title and a body: "GitHub star Top 10" and "AI 기술 쉽게 보기" (owner removed 바로 써볼 만한 것 here) |
| 25:404 | Sample issue (h 796) | left copy: eyebrow, title, body, link "전체 지난 호 보기 →"; right: 420x620 clipped, scaled newsletter preview (top otter banner hidden, per owner) |
| 25:489 | Bottom CTA (h 572) | left: wave_otter image (544x292) + title; right: a second subscribe form identical to the hero one |
| 25:509 | Footer (h 150) | name, about, privacy (개인정보 처리방침 link) |

How it maps to Phase 4 (04-CONTEXT):
- D-09: both subscribe forms and the nav "구독하기" CTA stay hidden while `SUBSCRIBE_URL is None`. Phase 4.1 turns them on.
- D-07/D-08: the 지난 호 archive is an added section, e.g. replacing or following "Sample issue". Its cards are newest first and show the date, headline_ko, Top 3 names and the #1 image. The nav "지난 호" link and the email's 지난 호 보기 both point to it (anchor `#archive`, which must stay fixed once emails link to it).
- The sample preview can be the latest issue's web page, or a static image. This is the planner's choice.
