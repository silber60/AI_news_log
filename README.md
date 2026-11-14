# 모닥로그 AI 리포트 (AI_news_log)

매주 월요일 아침, 지난주 Hugging Face Papers에 올라온 AI 모델 중 주목할 만한 것들을 골라 **쉬운 한국어로 풀어 메일로 보내 주는 뉴스레터**예요.
논문 수집부터 분석, 메일 작성, 발송, 웹 아카이브 게시까지 전부 GitHub Actions와 Claude로 자동화돼 있어요.

### 👉 [silber60.github.io/AI_news_log](https://silber60.github.io/AI_news_log/)

---

## 🦦 웹사이트 소개

[모닥로그 AI 리포트 사이트](https://silber60.github.io/AI_news_log/)에서 뉴스레터를 구독하고, 지난 호를 모두 볼 수 있어요.

| 메뉴 | 내용 |
| --- | --- |
| **구독하기** | 이름과 이메일만 넣으면 무료로 구독돼요. 신청하면 몇 분 안에 최신 호가 환영 메일로 와요. |
| **매주 이렇게 받아요** | 매주 어떤 코너가 오는지 미리 보여 줘요. |
| **모델 검색** ([/search](https://silber60.github.io/AI_news_log/search/)) | Hugging Face Papers를 키워드로 찾아보고, 벤치마크 점수가 공개된 모델끼리 나란히 비교할 수 있어요. |
| **지난 호 아카이브** | 지금까지 보낸 메일을 호별 페이지로 다시 볼 수 있어요. 예: [2026-W45](https://silber60.github.io/AI_news_log/issues/2026-W45/), [2026-W44](https://silber60.github.io/AI_news_log/issues/2026-W44/) |
| **개인정보 처리방침** ([/privacy](https://silber60.github.io/AI_news_log/privacy/)) | 어떤 정보를 왜 받고 어떻게 다루는지 적어 뒀어요. |

### 매주 받는 내용

- **GitHub 스타 Top 10**: 지난주 Hugging Face Papers 모델 중 GitHub 스타가 많은 순으로 최대 10개를 골라, 각각 무엇을 하는 모델인지 쉽게 설명해요.
- **AI 기술 쉽게 보기**: 그 주 모델에 쓰인 기술 하나를 골라 예시와 함께 풀어 줘요.

각 호에는 그 주의 흐름을 담은 헤드라인이 붙어요. 예를 들면 이런 식이에요.

- `2026.11.09` 오픈 모델로 로봇을 움직인다? 이번 주 AI 모델 9
- `2026.11.02` 긴 추론 학습, 이제 안정적으로 이번 주 AI 모델 10

구독 해지는 메일 하단의 링크에서 한 번에 할 수 있어요.

---

## ⚙️ 동작 방식

```
Hugging Face Papers ─▶ build (Claude 분석) ─▶ deliver (메일 발송) ─▶ publish (웹 아카이브)
                                                     ▲
                       Google Sheets + Apps Script ──┘ (구독자 목록·구독/해지·환영 메일)
```

### 1. 빌드: `python -m newsletter build`

한 주(ISO 주차, 예: `2026-W45`)의 호를 만들어요. 단계는 이 순서로 돌아요.

`fetch` → `select` → `analyze` → `enrich` → `verdicts` → `notes` → `trend` → `highlight` → `explainer` → `headline` → `polish` → `render`

- **fetch / select**: Hugging Face Papers에서 지난주 논문을 모으고, GitHub 스타 기준으로 상위 모델을 골라요. 라이선스는 GitHub API로 확인해요.
- **analyze ~ polish**: Claude가 논문을 읽고 요약, 트렌드, 하이라이트, 기술 해설, 헤드라인을 쓴 뒤 자연스러운 한국어로 다듬어요. 프롬프트는 [`prompts/`](prompts/)에 있어요.
- **render**: Jinja2 템플릿으로 HTML 메일과 텍스트 메일을 만들어요.

비용이 드는 단계는 끝날 때마다 결과를 `archive/<주차>/checkpoints/`에 저장해요. 그래서 다시 실행하면 Hugging Face나 Claude를 다시 부르지 않고 저장된 결과를 써요. 특정 단계부터 다시 만들고 싶으면 `--force-stage`를 쓰면 돼요 (그 단계와 이후 단계만 다시 계산해요).

### 2. 발송: `python -m newsletter deliver --mode test|send`

- `test`: 운영자 테스트 메일함으로만 보내요.
- `send`: 구독자 전체에게 보내요. 해지한 사람은 빼고 보내고, 발송 기록(ledger)이 있어서 같은 호를 두 번 보내지 않아요.
- 발송일(그 주 다음 월요일, KST)이 아니면 보내지 않아요. 복구용으로만 `--allow-stale`을 써요.

### 3. 게시: `python -m newsletter publish --mode send`

보낸 호를 `data/issues/`에 저장하고 `docs/` 아래 GitHub Pages 파일을 다시 만들어요. 템플릿만 바꿨을 때는 `python -m newsletter site`로 `docs/`만 다시 생성해요.

### 자동 실행 일정 (매주 월요일, KST)

| 시각 | 하는 일 |
| --- | --- |
| 05:47 | 지난주 호를 빌드하고 운영자에게 테스트 메일 발송 |
| 08:17 | 구독자에게 정식 발송 |
| 10:17, 12:47 | 예비 발송 (이미 보냈으면 아무에게도 안 보내요) |

GitHub의 cron이 늦거나 빠지는 경우가 있어서 정각을 피하고 예비 실행을 둬요. 저장소 변수 `SEND_PAUSED`로 정기 발송을 잠시 멈출 수 있어요. 매 실행 결과는 운영자에게 리포트 메일로 와요.

---

## 📁 폴더 구조

```
newsletter/          파이프라인 코드 (CLI, 단계별 stages/, 발송 delivery/)
prompts/             Claude 프롬프트
templates/           메일 템플릿, 웹 페이지 템플릿 (templates/web/)
schema/              호(issue) JSON 스키마
archive/<주차>/      주차별 원본 데이터, 체크포인트, 완성된 메일
data/                게시된 호, 발송 기록(ledger), 다룬 기술 해설 주제 목록
docs/                GitHub Pages 사이트 (자동 생성)
apps_script/         구독 백엔드 (Google Sheets + Apps Script)
scripts/             메일 이미지 빌드·점검 스크립트
tests/               pytest 테스트
.github/workflows/   newsletter(빌드·발송·게시), pages(사이트 배포), ci
```

---

## 🛠 로컬에서 실행하기

필요한 것: Python 3.14, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

```bash
export ANTHROPIC_API_KEY=...   # Claude API 키
uv run python -m newsletter build --week 2026-W45
```

결과는 `archive/2026-W45/`에 생겨요. `email.html`을 브라우저로 열면 메일 미리보기를 볼 수 있어요.

테스트와 린트:

```bash
uv run pytest
```

```bash
uv run ruff check .
```

### GitHub Actions 비밀값

| 이름 | 용도 |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude 분석 |
| `SMTP_USER`, `SMTP_PASSWORD` | 메일 발송 계정 |
| `TEST_RECIPIENT` | 테스트 메일 받는 주소 |
| `UNSUBSCRIBE_TOKEN_SECRET`, `UNSUBSCRIBE_LIST_KEY`, `SUBSCRIBER_LIST_KEY` | 구독 백엔드(Apps Script)와 통신 |

구독 백엔드 설정은 [`apps_script/README.md`](apps_script/README.md)에 단계별로 정리돼 있어요.

---

## 🔒 개인정보

- 구독자 정보는 Google 시트에만 있고, 저장소에는 들어가지 않아요.
- 해지 기록에는 이메일 주소 대신 HMAC 토큰만 남겨요.
- 실행 로그에는 개수와 상태만 찍고, 주소·이름·오류 본문은 남기지 않아요.

자세한 내용은 [개인정보 처리방침](https://silber60.github.io/AI_news_log/privacy/)을 봐 주세요.

---

데이터 출처: [Hugging Face Papers](https://huggingface.co/papers) · 분석: [Claude](https://www.anthropic.com/claude)
