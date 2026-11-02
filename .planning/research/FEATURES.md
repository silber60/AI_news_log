# Feature Research

**Domain:** Automated weekly AI model/paper email newsletter for Korean practitioners, curated from Hugging Face Papers and analyzed by an LLM
**Researched:** 2026-11-02
**Confidence:** MEDIUM. Newsletter feature conventions are well established. HF API field details come from community/third-party sources, not official docs. The Korean legal reading is an interpretation of 정보통신망법 제50조, not a KISA ruling on this case.

## Reference Products (what the landscape looks like)

| Product | Cadence | Item shape | What it does well | Gap our product fills |
|---------|---------|-----------|-------------------|-----------------------|
| AlphaSignal | Daily, with a weekly edition | Top models / repos / papers, 1-2 line blurb, link | AI-ranked "top 1%" selection, three fixed sections | No license or commercial-use verdict, no hardware info, English only |
| TLDR AI | Daily | Headline, read time, about 3-sentence summary | Very scannable, consistent per-item format | News-centric, not a practitioner checklist |
| The Batch (DeepLearning.AI) | Weekly | Editorial letter plus 4-6 long-form items | Opinionated framing ("why it matters") | Long, not structured for quick decisions |
| HF Papers weekly / "most upvoted this week" digests | Weekly | Title, upvotes, abstract or AI summary | Community-signal ranking (upvotes) | No practical "can I use it" judgment |
| Korean: 모두레터, 지피터스, AI매터스, 위클리 딥다이브 | Weekly | Korean-language trend or paper commentary | Korean language, Monday-morning slot (모두레터, 지피터스) | No per-model structured fields (license, PoC, GPU) |

**Takeaway:** Every competitor offers ranking, a summary, and a link. None gives a structured per-item verdict on whether a team can use the model at work: commercial license, PoC readiness, Claude/GPT applicability, and hardware. That verdict is the Core Value in PROJECT.md and the only place to differentiate. Everything else should be the cheapest acceptable version.

## Feature Landscape

### Table Stakes (Users Expect These)

#### Per-item (each of Top 10)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Title (original English) plus Korean title/gloss | Readers must recognize the paper when they see it elsewhere | LOW | Keep the English title verbatim. Add a short Korean gloss from Claude. |
| 한줄 요약 (one-line summary, Korean) | Every digest (TLDR, AlphaSignal) has one. It is the main scan unit. | LOW | Hard limit of about 80 Korean characters. Enforce it in the prompt and truncate in code. |
| Links: HF paper page, arXiv, code repo, HF model/Space | Readers need a one-click path to the source | LOW | HF paper data reportedly includes `githubRepo`/project fields. Linked models can be found via the Hub `arxiv:<id>` tag. Verify in the stack phase. |
| Rank and upvote count | It shows why the item was selected. HF digests show it. | LOW | Comes directly from the API. |
| AI 종류 tag (LLM / 비전 / 멀티모달 / 음성 / 에이전트 / 이미지·비디오 생성 / 기타) | Lets readers skip irrelevant categories fast | LOW | Use a closed enum in the structured output. Free text breaks the visual badges. |
| Consistent visual card per item | Scannability. TLDR's whole value is format consistency. | MEDIUM | One table-based card component, reused 10 times. Badges are colored table cells, not images or CSS. |

#### Email-level

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Week range in subject and header (e.g. "11/3~11/9") | Readers and archive need to identify the edition | LOW | Compute from the KST previous Monday through Sunday. |
| Personalized greeting ("홍길동님") | In PROJECT.md scope. Cheap. | LOW | Fall back to "구독자님" when the name is empty. HTML-escape the name. |
| Mobile-responsive layout that renders in Gmail and 네이버 메일 | Most opens are on mobile. Broken rendering destroys trust. | MEDIUM-HIGH | Use a table layout, inline CSS, 600-640px max width, system Korean font fallback (Apple SD Gothic Neo, Malgun Gothic, sans-serif). Naver strips `<style>` in places, so inline everything. |
| Plain-text alternative part (multipart/alternative) | Spam filters penalize HTML-only mail. Some clients prefer text. | LOW | Generate from the same data model, not by stripping HTML. |
| Sender identity and contact line in footer | Expected in any newsletter, and required if the mail is ever 광고성 (see legal note) | LOW | Use a static footer string. |
| Unsubscribe instruction (수신거부 방법) | Universal expectation. Legally required if 광고성 applies. Gmail and Naver treat it as a reputation signal. | LOW | v1: a "수신거부: 이 메일에 회신하거나 mailto 링크 클릭" line plus a `List-Unsubscribe: <mailto:...>` header. The operator removes the address from the CSV by hand. No web page needed, which matches Out of Scope. |
| "확인 필요" fallback on any unverifiable field | Wrong license claims are worse than none | LOW | Already in PROJECT.md. Make it a first-class enum value, not free text. |
| Reliable weekly arrival (Mon 08:00 KST, tolerating Actions delay) | A newsletter that silently skips a week loses trust | MEDIUM | Covered by the infra phase. A failure must notify the operator (Actions failure email is enough). |

### Differentiators (Competitive Advantage)

These are the practitioner verdict fields. Each must carry 근거 (evidence), or it becomes hallucination with a badge on it.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 상업적 사용 가능 여부 (가능 / 조건부 / 불가 / 확인 필요) plus license name | Answers "can I ship this?" No competitor does this. | HIGH | Source of truth is the `license` tag of the linked HF model or the GitHub repo LICENSE. **Determine it deterministically from metadata in code, not by Claude guessing.** Map SPDX ids to verdicts with a lookup table: Apache-2.0/MIT/BSD gives 가능; Llama/Gemma/OpenRAIL-style custom licenses give 조건부; CC-BY-NC and research-only licenses give 불가; no license found gives 확인 필요. Claude only writes the human-readable reason. |
| PoC 사용 가능 여부 (바로 가능 / 코드만 / 논문만 / 확인 필요) | Tells readers whether they can try it this week | MEDIUM | Derive from presence of weights (HF model link), code (githubRepo), and demo (HF Space). Use deterministic rules plus a short Claude note. |
| Claude/GPT에서 사용 가능 여부 (API로 바로 / 기법 적용 가능 / 해당 없음) | Most Korean practitioners use hosted LLMs, not self-hosted ones. This translates research into "how does it help my Claude/GPT workflow". | MEDIUM | Inherently a judgment call, so this is the field most prone to hallucination. Constrain it to 3 enum values plus one sentence. Typical answers: a prompting/agent technique gives 기법 적용 가능; a new open model gives 해당 없음 (self-host); an OpenAI/Anthropic feature paper gives API로 바로. |
| 활용 아이디어 (1-2 concrete use ideas) | Turns a summary into action. The Batch's "why it matters" is the closest analogue. | LOW | Prompt for a Korean-business context. Cap at 2 bullets. |
| 라이선스·공개 여부 (가중치 ✓/✗, 코드 ✓/✗, HF 모델 링크) | Quick open-weights check | LOW | Same metadata fetch as the commercial-use field. Render as icon/text badges. Use text characters, not emoji images, for Naver safety. |
| 실행 난이도·필요 GPU (e.g. "7B, 약 16GB VRAM, 로컬 가능 / 8xA100 필요") | Answers "can I run it on my machine?" Rare in any digest. | MEDIUM-HIGH | Parameter count from HF model metadata (safetensors total, when present). VRAM rule of thumb: about 2 bytes per parameter in FP16, plus about 20%. Label it as an estimate. If there is no model card, output 확인 필요. Do not let Claude invent parameter counts. |
| 이번 주 트렌드 총평 (2-3 sentences, top of email) | Gives the edition a narrative. The Batch and Korean newsletters lead with this. | LOW | One extra Claude call over all 10 items' structured output. Generate it after the per-item analysis. |
| At-a-glance summary table at the top (10 rows x badges) | Lets a reader decide in 10 seconds which items to read | MEDIUM | This is the real UX differentiator for "한눈에". Build it from the same data and render it as a compact table above the cards. Must work at mobile width: use 3-4 badge columns maximum, or stack. |
| Web version link ("웹에서 보기") plus archive | Fixes client rendering failures, and makes issues shareable and searchable | MEDIUM | Publish a de-personalized HTML to GitHub Pages from the same Actions run. Caveat: Pages on a **private** repo needs a paid GitHub plan, so the repo visibility decision matters (the subscriber CSV must not be public). Option: a separate public "archive" repo, or keep the CSV in Secrets. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Claude decides license and commercial-use from the paper text alone | Simple, one prompt | Papers rarely state the weights license. The LLM will confidently guess "Apache 2.0". A false "상업적 사용 가능" is the most harmful error this product can make. | Fetch Hub/GitHub license metadata, map it in code, and let Claude only explain. Missing metadata means 확인 필요. |
| Open/click tracking pixels | Standard ESP feature | Out of scope. Naver and Gmail proxy images anyway. For 1 to a few recipients it adds privacy burden (개인정보) for no signal. | Ask for reply feedback in the footer. |
| Subscribe/unsubscribe web app | Feels "complete" | Needs hosting, a DB, and a double opt-in flow. Out of scope in PROJECT.md. | mailto unsubscribe plus manual CSV edit. Revisit once there are more than about 50 subscribers. |
| Full abstract or long summaries per item | "More info is better" | Ten long items make the email too long. Gmail clips messages over **102KB**, which hides the footer and unsubscribe line. | One-line summary plus 2 ideas plus a link. Keep the HTML size under about 90KB and check it in CI. |
| Images/thumbnails per paper (arXiv figures) | Visual appeal | Remote images are blocked by default in many clients, inflate size, and raise hotlinking and copyright issues. Naver handles them inconsistently. | Text and colored-cell badges. At most one header logo, hosted on Pages. |
| Custom web fonts as the primary font | Match the Figma design | Gmail and Naver ignore most `@font-face`, so the layout shifts. | Use the Figma font in the web version only. The email uses a system Korean font stack with sizes tuned to look similar. |
| Mixing in promotional content (sponsor slots, paid course links) | Monetization later | It turns the mail into 영리목적 광고성 정보, which triggers 정보통신망법 제50조 obligations: (광고) prefix in the subject, documented prior consent, and a free unsubscribe. | Keep it purely informational. If promotion is ever added, implement 제50조 compliance first. |
| Pre-send human review gate | Safety | User explicitly chose full automation. | Use automated guards instead: schema validation, a "확인 필요" fallback, and fail-closed on an empty fetch (send nothing rather than a broken issue). |
| Multiple sources (arXiv, X, GitHub trending) | Coverage | Out of scope. It breaks the upvote-ranking logic and dedup. | HF Papers only. HF already aggregates the community signal. |

## Legal Note: Unsubscribe and 정보통신망법 (for the requirements author)

- **제50조 scope:** It regulates **영리목적의 광고성 정보** sent by electronic means. That requires prior explicit consent, and for email a "(광고)" subject marker, sender name and contact, and a free, easy unsubscribe method (제50조 ①, ④).
- **This product as specified:** It is a free, non-commercial, informational digest with no product or service promotion. It most likely falls **outside** 제50조. Confidence: MEDIUM. This is an interpretation. No KISA ruling was found for this exact case, and KISA's guidance says content that induces use of a service or promotes a product makes a message 광고성.
- **Caveat on "internal" use:** If it is sent under a company (example.com) identity and links to company products or services, it can tip into 광고성.
- **Separate obligation that does apply:** The CSV holds names and emails, which is personal data under 개인정보보호법. Collect it with consent, limit its use, and do not commit it to a public repo. This is already noted in PROJECT.md Constraints.
- **Recommendation:** Include an unsubscribe line, a `List-Unsubscribe` mailto header, and a sender/contact footer anyway. The cost is near zero. It also keeps compliance automatic if the newsletter grows or turns commercial, and helps deliverability. Do **not** add "(광고)" to the subject: it is not required for informational mail and it hurts open rates.

## Feature Dependencies

```
HF weekly paper fetch (Top 10 by upvotes)
    └──requires──> Linked-artifact enrichment (HF model/Space by arxiv id, githubRepo, license tag, param count)
                       └──requires──> Deterministic verdict rules (license→상업적 사용, artifacts→PoC, params→GPU)
                                          └──requires──> Claude analysis (summary, 활용, Claude/GPT, reasons) with structured output
                                                             └──requires──> Weekly trend 총평 (needs all 10 analyses)
                                                                                └──requires──> Data model (JSON per issue)

Data model (JSON per issue)
    ├──feeds──> HTML email template (cards + top summary table)  ──requires──> Figma web design
    ├──feeds──> Plain-text part
    └──feeds──> Web version / archive page (de-personalized)

Per-recipient render (greeting) ──requires──> CSV subscriber load
SMTP send ──requires──> per-recipient render + unsubscribe footer/header

Web version link ──enhances──> HTML email (fallback for rendering failures)
Top summary table ──enhances──> Per-item cards (scan, then dive)

Personalized greeting ──conflicts──> Single shared web-version HTML (must render web copy without name)
Long per-item content ──conflicts──> Gmail 102KB clipping (footer/unsubscribe disappears)
```

### Dependency Notes

- **Verdict fields require enrichment before Claude:** The commercial-use, PoC, and GPU fields are only trustworthy if Hub/GitHub metadata is fetched first and passed into the prompt as facts. Build enrichment as its own step and phase. Do not fold it into the prompt.
- **The trend summary requires all item analyses:** Run it as a second-pass call over structured results. That costs one extra API call per week.
- **Template requires the Figma design and a frozen data model:** Freeze the JSON schema (field names plus enums) before the HTML template so design and analysis can proceed in parallel against a fixture JSON.
- **Web version conflicts with personalization:** Render twice. Make the web copy without the greeting, then make the per-recipient email.
- **Web version depends on the repo visibility decision:** Free GitHub Pages needs a public repo, and a public repo forbids committing the CSV. Decide this in the infra phase.

## MVP Definition

### Launch With (v1)

- [ ] HF Papers previous-week fetch, Top 10 by upvotes. This is the core pipeline.
- [ ] Enrichment: linked HF model/Space, GitHub repo, license tag, parameter count. Without it, the verdict fields cannot be trusted.
- [ ] Per-item fields: AI 종류, 상업적 사용 (enum plus license plus reason), PoC (enum plus reason), Claude/GPT (enum plus reason), 한줄 요약, 활용 아이디어, 공개 여부, 실행 난이도·GPU, all with a 확인 필요 fallback. This is the Core Value.
- [ ] 이번 주 트렌드 총평. User-selected, and cheap.
- [ ] HTML email (Figma-derived, table and inline CSS) plus a plain-text part, with a Gmail and Naver rendering check. Without this nothing ships.
- [ ] Personalized greeting from CSV. In scope.
- [ ] Footer: sender, contact, mailto unsubscribe line, and `List-Unsubscribe` header. Near-zero cost, and it covers legal and deliverability.
- [ ] Fail-closed behavior: if the fetch is empty or validation fails, do not send, and let the Actions job fail and notify. This replaces the human review gate.

### Add After Validation (v1.x)

- [ ] At-a-glance summary table at the top. Add it once the card layout is stable, or in v1 if the Figma design includes it.
- [ ] Web version link plus GitHub Pages archive. Add it once rendering complaints appear or the issue is shared beyond one recipient.
- [ ] Issue number and "지난 호 보기" link. Comes with the archive.
- [ ] HTML size guard (fail under 102KB) in CI. Add it as soon as real content length is known.

### Future Consideration (v2+)

- [ ] Subscribe/unsubscribe web form. Only past about 50 subscribers.
- [ ] Per-subscriber interest filtering (e.g. only 비전/음성). Needs a subscriber preference model, which is overkill now.
- [ ] Week-over-week trend tracking (e.g. "에이전트 논문 3주 연속 증가"). Needs stored history, which the archive provides.
- [ ] Reply-based feedback ("유용했나요?"). Only useful with multiple readers.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Weekly Top 10 fetch | HIGH | LOW | P1 |
| Metadata enrichment (license/artifacts/params) | HIGH | MEDIUM | P1 |
| 상업적 사용 verdict (rule-based) | HIGH | MEDIUM | P1 |
| PoC verdict | HIGH | LOW | P1 |
| Claude/GPT applicability | HIGH | LOW | P1 |
| 한줄 요약 + 활용 아이디어 | HIGH | LOW | P1 |
| AI 종류 tag | MEDIUM | LOW | P1 |
| 실행 난이도·GPU | MEDIUM | MEDIUM | P1 (estimate or 확인 필요) |
| 트렌드 총평 | MEDIUM | LOW | P1 |
| HTML email Gmail/Naver compatible | HIGH | HIGH | P1 |
| Plain-text part | MEDIUM | LOW | P1 |
| Personalized greeting | LOW | LOW | P1 (in scope, trivial) |
| Unsubscribe line + List-Unsubscribe header | MEDIUM | LOW | P1 |
| Fail-closed send guard | HIGH | LOW | P1 |
| Top summary table | HIGH | MEDIUM | P2 |
| Web version + archive | MEDIUM | MEDIUM | P2 |
| 102KB size guard | MEDIUM | LOW | P2 |
| Subscribe web page | LOW (now) | HIGH | P3 |
| Open/click tracking | LOW | MEDIUM | P3 (do not build) |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | AlphaSignal / TLDR AI | The Batch / Korean newsletters | Our Approach |
|---------|----------------------|--------------------------------|--------------|
| Selection | AI-ranked or editor-picked | Editor-picked | HF upvotes, Top 10, deterministic |
| Per-item summary | 1-3 sentences, English | Long-form commentary | One Korean line plus 2 use ideas |
| License / commercial use | Not shown | Occasionally mentioned in prose | Structured verdict plus license plus evidence |
| Hardware requirements | Not shown | Rarely | Param-based VRAM estimate or 확인 필요 |
| Hosted LLM applicability | Not shown | Not shown | Claude/GPT enum plus reason |
| Trend summary | Rare | Editorial letter (The Batch) | 2-3 sentence auto 총평 |
| Web version / archive | Yes (Substack/web) | Yes | v1.x via GitHub Pages |
| Unsubscribe | ESP one-click | ESP one-click | mailto plus List-Unsubscribe header, manual CSV |
| Personalization | Name merge tag | Name merge tag | CSV name greeting |
| Tracking | Yes | Yes | None (deliberate) |

## Sources

- AlphaSignal content categories and cadence: https://agentwiki.org/alphasignal, https://alphasignalai.substack.com, https://huggingface.co/AlphaSignal/models (MEDIUM; third-party and own listings conflict on daily vs weekly)
- Weekly HF upvote digests as a format precedent: https://aigazine.com/industry/10-most-upvoted-ai-papers-on-hugging-face-this-week-march-1622--ms, https://ml-papers-weekly.vercel.app/ (MEDIUM)
- HF daily papers API (`/api/daily_papers?date=`, upvotes, githubRepo): https://skills.cat/skills/fratert691/auto-hf-papers, https://apify.com/realai_pl/hugging-face-papers-monitor.md (LOW-MEDIUM; community docs, verify against the live API in the stack phase)
- Korean AI newsletter landscape (모두레터, 지피터스, AI매터스, 위클리 딥다이브): https://www.gpters.org/news/post/5-recommended-domestic-ai-adybRwUYpQmqe2J (MEDIUM; author is an interested party)
- 정보통신망법 제50조 text and obligations: https://korea.legal/wiki/%ec%a0%95%eb%b3%b4%ed%86%b5%ec%8b%a0%eb%a7%9d-%ec%9d%b4%ec%9a%a9%ec%b4%89%ec%a7%84-%eb%b0%8f-%ec%a0%95%eb%b3%b4%eb%b3%b4%ed%98%b8-%eb%93%b1%ec%97%90-%ea%b4%80%ed%95%9c-%eb%b2%95-21/, https://www.itwiki.kr/w/%EC%A0%95%EB%B3%B4%ED%86%B5%EC%8B%A0%EB%A7%9D%EB%B2%95_%EC%A0%9C50%EC%A1%B0 (MEDIUM)
- 광고성 판단 기준 (service inducement or promotion makes a message 광고성), email "(광고)" and free unsubscribe: https://solapi.com/guides/sms-ad-guide, https://thecheck.co.kr/promotional-email-label-unsubscribe/, https://research.beautifulfund.org/archive/ (MEDIUM; secondary sources, KISA 안내서 original not read)
- Gmail 102KB clipping, Naver/Gmail web-font and `<style>` limits, GitHub Pages private-repo plan requirement: training knowledge (MEDIUM; verify in the template and infra phases)

---
*Feature research for: automated Korean weekly AI model newsletter (HF Papers to Claude to Gmail SMTP)*
*Researched: 2026-11-02*
