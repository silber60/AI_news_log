# 구독 해지 백엔드 설정 (Google Sheets + Apps Script)

메일 하단의 "구독 해지" 링크는 `https://silber60.github.io/AI_news_log/unsubscribe/?t=<토큰>` 확인 페이지로 가요. 버튼을 누르면 이 폴더의 `Code.gs`가 Google 시트에 토큰을 한 줄 적고, 매주 발송 전에 GitHub Actions가 그 목록을 읽어서 해지한 사람을 빼고 보내요.

시트에는 이메일 주소가 들어가지 않아요. 주소를 소문자로 바꾸고 앞뒤 공백을 지운 뒤 비밀값으로 HMAC-SHA256을 계산한 16진수 앞 32자리(토큰)만 적어요. `Code.gs`는 공개 저장소에 있고 비밀값은 하나도 들어 있지 않아요. 비밀값은 스크립트 속성과 GitHub Actions secrets에만 둬요.

> **지켜야 할 규칙**
>
> 스크립트를 고칠 때는 항상 **배포 → 배포 관리 → 수정(연필) → 버전: 새 버전 → 배포** 순서로 해요.
> 절대 **"새 배포"** 를 누르지 않아요. 새 배포는 주소(`/exec` URL)를 새로 만들어서, 이미 보낸 메일의 해지 헤더가 모두 죽은 주소를 가리키게 돼요.
>
> `TOKEN_SECRET`도 절대 바꾸지 않아요. 바꾸면 이미 보낸 메일의 해지 링크가 모두 무효가 돼요.

## 설정 순서

모든 단계는 `SMTP_USER`(발송용 Gmail) 계정으로 로그인한 상태에서 해요.

1. Google 시트를 새로 만들고 이름을 `모닥로그 AI 리포트 구독 관리`로 정해요. 주소창의 `/d/<ID>/edit`에서 `<ID>` 부분을 복사해 둬요. 이 값이 `SHEET_ID`예요.
2. 시트에서 **확장 프로그램 → Apps Script**를 열어요. 기본으로 있는 `Code.gs` 내용을 모두 지우고, 이 저장소의 `apps_script/Code.gs` 내용을 그대로 붙여 넣은 뒤 저장해요.
3. 내 컴퓨터 터미널에서 비밀값 두 개를 만들어요. 아래 명령을 두 번 실행하면 서로 다른 값이 두 줄 나와요.

   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   첫 번째 값은 `TOKEN_SECRET`, 두 번째 값은 `LIST_KEY`로 써요. 두 값은 채팅, 이슈, 커밋 어디에도 붙여 넣지 않아요.
4. Apps Script 왼쪽의 **프로젝트 설정(톱니바퀴) → 스크립트 속성 → 스크립트 속성 추가**에서 세 개를 넣어요.
   - `SHEET_ID`: 1단계에서 복사한 시트 ID
   - `TOKEN_SECRET`: 3단계의 첫 번째 값
   - `LIST_KEY`: 3단계의 두 번째 값
5. 편집기 위쪽 함수 목록에서 `setup`을 고르고 **실행**을 눌러요. 권한 확인 창이 뜨면 허용해요. 시트에 `unsubscribes` 탭이 생기고 첫 줄에 `id | at | via`가 보이면 돼요.
6. 함수 목록에서 `selfTest`를 고르고 실행해요. 실행 로그에 `PASS`가 나와야 해요. `FAIL`과 16진수가 나오면 여기서 멈추고 그 16진수를 Claude에게 알려 주세요. Python 쪽 값과 비교해서 고쳐야 메일을 보낼 수 있어요.
7. **배포 → 새 배포**를 누르고 유형으로 **웹 앱**을 골라요. 처음 한 번만 새 배포를 써요.
   - 다음 사용자 인증 정보로 실행: **나**
   - 액세스 권한이 있는 사용자: **모든 사용자**

   배포하면 `https://script.google.com/macros/s/.../exec` 형태의 웹 앱 URL이 나와요. 이 주소는 모든 메일 헤더에 들어가는 공개 값이라 비밀이 아니에요. Claude에게 알려 주면 코드의 `UNSUBSCRIBE_ENDPOINT`에 넣어서 커밋해요.
8. GitHub 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에서 두 개를 만들어요.
   - `UNSUBSCRIBE_TOKEN_SECRET`: 4단계의 `TOKEN_SECRET`과 같은 값
   - `UNSUBSCRIBE_LIST_KEY`: 4단계의 `LIST_KEY`와 같은 값
9. 터미널에서 목록 읽기를 확인해요. `<LIST_KEY>`와 `<URL>`은 내 값으로 바꿔요.

   ```
   curl -sL -d "action=list&key=<LIST_KEY>" "<URL>"
   ```

   `{"version":1,"ids":[]}`가 나와야 해요. 키를 일부러 틀리게 넣으면 `{"error":"forbidden"}`이 나와야 해요. 이 명령은 터미널 기록에 키가 남으니, 확인한 뒤 `history -c` 등으로 지워도 좋아요.
10. 원클릭 해지를 확인해요. 아래 토큰은 테스트용 값이라 실제 구독자와 겹치지 않아요.

    ```
    curl -s -o /dev/null -w "%{http_code}\n" -d "List-Unsubscribe=One-Click" "<URL>?t=82a671b5104273fe07992f40d81000c8"
    ```

    `302`가 나오고, 시트의 `unsubscribes` 탭에 `82a671b5104273fe07992f40d81000c8` 행이 생기면 돼요.
11. 10단계에서 생긴 테스트 행을 시트에서 삭제해요. 첫 줄(`id | at | via`)은 지우지 않아요.

## Claude에게 알려 줄 것

- `selfTest` 결과 (`PASS`, 또는 `FAIL`과 16진수)
- 9단계 결과 두 개 (`{"version":1,"ids":[]}`, `{"error":"forbidden"}`)
- 10단계 상태 코드와 시트에 행이 생겼는지 여부 (삭제했는지도)
- 7단계의 `/exec` URL

`TOKEN_SECRET`, `LIST_KEY`, 시트 ID는 알려 주지 않아요. Claude에게 필요한 값은 `/exec` URL 하나예요.

## 나중에 스크립트를 고칠 때

1. Apps Script 편집기에서 `Code.gs`를 새 내용으로 바꾸고 저장해요.
2. **배포 → 배포 관리**를 열고, 지금 쓰는 배포의 **수정(연필)** 을 눌러요.
3. 버전에서 **새 버전**을 고르고 **배포**를 눌러요. URL은 그대로예요.
4. "새 배포"는 누르지 않아요.
