# Phase 1: End-to-End Skeleton - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-02
**Phase:** 01-end-to-end-skeleton
**Areas discussed:** 메일 제목·발신자 표기, 항목 카드 구성, Top 10 선정 규칙, 실패·미리보기 동작

---

## 메일 제목·발신자 표기

| Option | Description | Selected |
|--------|-------------|----------|
| 브랜드+기간 | "[AI 주간 모델 브리프] 10/26~11/1 Top 10" | |
| 브랜드+1위 논문 | "[AI 주간 브리프] 이번 주 1위: <한글 제목> 외 9건" | ✓ |
| 브랜드+ISO 주차 | "[AI 주간 브리프] 2026-W44" | |

Sender name: "AI 주간 모델 브리프" ✓ (alternatives: 본인 이름 + 뉴스레터명, "AI 주간 브리프").
Test marking: 제목 앞에 [TEST] ✓ (alternative: 구분 없음).

## 항목 카드 구성

| Option | Description | Selected |
|--------|-------------|----------|
| 한글 제목 크게 + 원제 작게 | | |
| 원제 크게 + 한글 작게 | | |
| 한글 제목만 | | |

**User's choice (free text):** 모델 이름이 영어면 영어로, AI 용어도 영어로, 그 외는 한국어. Follow-up: 원제도 작게 병기 ✓; 본문 전체에 같은 규칙 적용 ✓.
**Links:** HF Papers, arXiv, GitHub 코드, 프로젝트 페이지 (all selected).
**활용 아이디어 (free text):** 실무·개발에 맞추지 말고 어디서 쓸 수 있는지만 단순하게. 창의적이지 않게, 관련 페이지 내용 참조.
**저자:** 주요 소속만 ✓ (alternative: 표시 안 함).

## Top 10 선정 규칙

Questions asked: 주 경계 (KST 월~일 vs HF 주간 페이지), 동점 처리, 10편 미만, 최소 upvote.
**User's choice:** Not answered; user sent a new idea instead. Recommended defaults applied and stated: KST 월~일, 댓글 수 → 먼저 올라온 순, 있는 만큼 발송, 기준 없음.

## 기술 해설 코너 (raised by user)

User asked for a weekly corner explaining the #1 or a not-yet-covered AI technique in plain language, like 어세스타 성장레터.

| Question | Selected |
|----------|----------|
| Roadmap placement | Phase 3에 합치기 ✓ (alternatives: 별도 3.1, v2) |
| Reserve schema slot now | 미리 만들어 둠 ✓ |
| Topic choice | 이번 주 Top 10에서 새 기술 우선 ✓ (alternative: 항상 1위) |

## 실패·미리보기 동작

| Question | Options | Selected |
|----------|---------|----------|
| 실패 알림 | job 실패만 / 지금부터 본인에게 실패 메일 | 지금부터 본인에게 실패 메일 |
| preview 결과물 | HTML+텍스트+JSON / HTML만 | HTML+텍스트+JSON |
| 부분 실패 | 전체 실패 / 그 항목만 빼고 발송 | 전체 실패 |

**Notes:** Failure mail limited to test/send modes because preview must not read SMTP secrets.

## Claude's Discretion

- Subject truncation length, Phase 1 table layout details, failure-notice wording.

## Deferred Ideas

- Weekly 기술 해설 코너 → Phase 3 (needs roadmap/requirements update).
