# AI 주간 모델 뉴스레터 (Weekly AI Model Brief)

## What This Is

매주 월요일 오전 8시(KST)에 지난 한 주 동안 Hugging Face Papers(https://huggingface.co/papers/)에 올라온 AI 모델/논문 Top 10을 정리해 CSV 구독자 목록으로 발송하는 웹형 HTML 이메일 뉴스레터. 각 항목은 AI 종류, 상업적 사용 가능 여부, PoC 사용 가능 여부, Claude/GPT에서 사용 가능 여부 등을 한눈에 보여준다. 디자인은 Figma 파일의 기존 모바일 디자인(폰트·스타일)을 참고해 같은 파일에 웹형 뉴스레터 디자인을 새로 만들고, 이를 HTML 이메일로 구현한다.

## Core Value

매주 월요일 아침, 이번 주 꼭 알아야 할 AI 모델이 "실무에 쓸 수 있는가" 기준(상업적 사용·PoC·Claude/GPT 연동)으로 정리된 메일이 사람 손 없이 구독자 메일함에 도착한다.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] HF Papers에서 지난 주(월~일) 논문 목록을 upvote 순으로 수집, Top 10 선정
- [ ] 각 항목을 Claude API로 분석해 필드 생성:
  - AI 종류 (LLM, 비전, 멀티모달, 음성, 에이전트, 이미지/비디오 생성 등)
  - 상업적 사용 가능 여부 (라이선스 근거 포함)
  - PoC 사용 가능 여부 (가중치/코드/데모 공개 여부 근거)
  - Claude나 GPT에서 사용 가능 여부 (API/툴/기법 적용 가능성)
  - 한줄 요약 + 활용 아이디어
  - 라이선스·공개 여부 (가중치/코드 공개, HF 모델 링크)
  - 실행 난이도·필요 GPU (모델 크기, 로컬 실행 가능 여부)
- [ ] 이번 주 트렌드 총평 (2~3문장) 생성
- [ ] Claude가 생성한 모든 본문 텍스트는 humanizer skill 규칙 적용 필수 (AI 티 나는 문장 제거: not-X-but-Y 대비, 강제 3단 나열, 과장·영업 문구, 대시 남발 등). 파이프라인에서 humanizer 규칙을 프롬프트에 넣거나 별도 다듬기 패스로 적용
- [ ] 상단 "이번 주 바로 써볼 만한 것" 하이라이트 섹션: Claude Skill 또는 GPTs(커스텀 GPT)로 만들기 좋은 항목을 Top 10 위에 별도로 한 번 더 강조·홍보 (왜 좋은지 + 어떻게 만들지 한두 줄)
- [ ] 매주 기술 해설 코너: 이번 주 Top 10 중 이전에 다루지 않은 AI 기술(없으면 1위 논문의 핵심 기술)을 쉽게 풀어 설명 (어세스타 성장레터 참고)
- [ ] Figma 파일에 웹형 뉴스레터 디자인 제작 (기존 모바일 디자인의 폰트·스타일 참고)
- [ ] Figma 디자인을 이메일 클라이언트 호환 HTML 템플릿으로 구현 (Gmail, 네이버 메일)
- [ ] CSV 구독자 목록(이메일, 이름)을 읽어 개인화 인사(예: "홍길동님")와 함께 발송
- [ ] Gmail SMTP로 발송
- [ ] GitHub Actions cron으로 매주 월요일 08:00 KST 자동 실행 (+ 수동 실행 트리거)
- [ ] 초기 구독자: subscriber@example.com / 홍길동 1명

### Out of Scope

- 구독/구독취소 웹 폼 — v1은 CSV 직접 관리로 충분 (웹 버전·아카이브 페이지는 v1 포함)
- 발송 전 수동 검토/승인 단계 — 사용자가 완전 자동 발송을 선택
- 오픈율/클릭 트래킹 — 1명 대상 초기 단계라 불필요
- 대량 발송 인프라(ESP, 도메인 인증) — Gmail SMTP 일일 한도 내 소규모
- HF Papers 외 소스(arXiv 직접, X/Twitter 등) — 기준 소스는 HF Papers로 고정

## Context

- 기준 소스: https://huggingface.co/papers/ (주간 뷰 / HF API로 날짜별 daily papers 조회 가능)
- "AI 모델 정리"지만 소스는 논문 목록 → 각 논문에 연결된 모델/코드/라이선스를 찾아 실무 관점으로 판단해야 함. 근거 없는 판단은 "확인 필요"로 표기.
- 디자인: Figma 파일 `qyJcGii2MLHTbi4W9mPZkx` (ai뉴스레터, node 0-1)에 모바일 디자인 존재. 폰트/색/컴포넌트 스타일을 참고해 웹형(데스크톱 폭) 디자인을 같은 파일에 추가.
- 수신자는 한국어 사용자. 뉴스레터 본문은 한국어.
- 작업 환경 Mac에 Node.js 미설치 — 런타임은 GitHub Actions 위에서 동작하도록 설계 (언어는 Python 또는 Node, 리서치 후 결정).
- 사용자 이메일(작성자): owner@example.com
- GitHub 계정: silber60 (GitHub Actions용 repo는 이 계정 아래 생성)
- humanizer skill 원본: `~/.claude/skills/humanizer/SKILL.md` — Actions 환경엔 Claude Code skill이 없으므로 규칙을 repo에 프롬프트 파일로 복사해 사용

## Constraints

- **실행 환경**: GitHub Actions — PC 상태와 무관한 무료 cron
- **스케줄**: `cron: "0 8 * * 1"` + `timezone: "Asia/Seoul"` (2026-03 GitHub 지원). YAML 위치는 구현 시 공식 문서로 확인. Actions cron은 수 분~수십 분 지연 가능
- **메일**: Gmail SMTP + 앱 비밀번호 (GitHub Secrets 저장), Gmail 일일 발송 한도 존재
- **보안**: SMTP 비밀번호, Anthropic API 키는 Secrets로만 관리, 코드/로그에 노출 금지
- **Public repo**: 구독자 CSV는 절대 커밋 금지 → `SUBSCRIBERS_CSV` Secret으로만 관리, `subscribers.example.csv`만 커밋. 발송 장부는 이메일 해시만 저장. Actions 로그도 공개되므로 주소·이름 로그 금지(개수만). 60일 무활동 시 cron 비활성화 → 주간 아카이브 커밋으로 유지
- **이메일 HTML**: 테이블 기반 레이아웃 + 인라인 CSS, 웹폰트는 fallback 필요 (Gmail/네이버는 웹폰트 제한)
- **비용**: Claude API 주 1회 10건 분석 — 저비용

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| GitHub Actions cron으로 스케줄 | PC 꺼져 있어도 매주 실행, 무료 | — Pending |
| Gmail SMTP 발송 | 무료, 소규모 리스트에 충분 | — Pending |
| Claude API로 완전 자동 분석·발송 | 사람 개입 없이 매주 발송 | — Pending |
| Top 10, upvote 순 | 읽기 좋은 분량 | — Pending |
| Figma에 웹형 디자인 새로 제작 후 HTML 구현 | 기존 모바일 디자인 톤 유지 | — Pending |
| Public repo (silber60) | 사용자 선택. GitHub Pages 무료로 웹 버전/아카이브 가능 | — Pending |
| cron `0 8 * * 1` + `timezone: Asia/Seoul` | 사용자 선택. KST 기준이라 계산 단순 | — Pending |
| Figma 웹형 디자인 640px 이메일 폭 | Gmail/네이버 호환 | — Pending |
| 발신: 개인 Gmail + 앱 비밀번호 | 사용자 선택 (전용 계정 대신) | — Pending |
| 웹 버전 + 아카이브 v1 포함 (GitHub Pages) | public repo라 무료 | — Pending |
| Vertical MVP 단계 구성 | 빨리 끝까지 도는 버전 우선 | — Pending |
| Claude 생성 텍스트에 humanizer 필수 | 사용자 요구: AI 티 안 나는 뉴스레터 | — Pending |
| Claude Skill / GPTs 활용 후보를 상단에서 별도 강조 | 사용자 요구: 바로 써볼 만한 것 홍보 | — Pending |
| 추가 필드: 한줄요약+활용, 라이선스·공개, 실행 난이도·GPU, 주간 트렌드 | 사용자 선택 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-11-02 after initialization*
