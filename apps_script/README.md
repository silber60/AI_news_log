# 구독 백엔드 설정 (Google Sheets + Apps Script)

이 폴더의 `Code.gs` 하나가 구독 신청, 구독 해지, 주간 발송용 구독자 목록, 기존 구독자 가져오기, 환영 메일을 모두 맡아요. 설정은 아래 순서대로 한 번만 하면 돼요.

- 구독 신청: 사이트 폼이 이름, 이메일, 동의 여부를 보내면 시트의 `subscribers` 탭에 한 줄이 생겨요. 같은 주소로 다시 신청해도 줄이 늘지 않아요.
- 환영 메일: 신청을 받으면 바로 보내지 않고 대기열에 넣어요. 1분마다 도는 트리거(`processWelcomeQueue`)가 몇 분 안에 최신 호를 환영 메일로 보내요. 한 주소에는 24시간에 한 번만 보내고, 하루에 50통을 넘기지 않아요.
- 구독 해지: 메일 하단의 "구독 해지" 링크는 `https://silber60.github.io/AI_news_log/unsubscribe/?t=<토큰>` 확인 페이지로 가요. 버튼을 누르면 `unsubscribes` 탭에 토큰을 적고, `subscribers` 탭의 그 사람 줄(이름, 이메일)을 지워요.
- 주간 발송: GitHub Actions가 매주 발송 전에 키로 목록을 읽어요. 해지한 사람은 빼고 보내요.

`unsubscribes` 탭에는 이메일 주소가 들어가지 않아요. 주소를 소문자로 바꾸고 앞뒤 공백을 지운 뒤 비밀값으로 HMAC-SHA256을 계산한 16진수 앞 32자리(토큰)만 적어요. `Code.gs`는 공개 저장소에 있고 비밀값은 하나도 들어 있지 않아요. 비밀값은 스크립트 속성과 GitHub Actions secrets에만 둬요.

> **지켜야 할 규칙**
>
> 처음 배포할 때 한 번만 **배포 → 새 배포**를 써요. 그 뒤로 스크립트를 고칠 때는 항상 **배포 → 배포 관리 → 수정(연필) → 버전: 새 버전 → 배포** 순서로 해요.
> 두 번째 **"새 배포"** 는 주소(`/exec` URL)를 새로 만들어서, 이미 보낸 메일의 해지 헤더가 모두 죽은 주소를 가리키게 돼요.
>
> `TOKEN_SECRET`은 절대 바꾸지 않아요. 바꾸면 이미 보낸 메일의 해지 링크가 모두 무효가 돼요.
>
> 비밀값(키 다섯 개, 시트 ID)은 채팅, 이슈, 커밋, 스크린샷 어디에도 붙여 넣지 않아요.

## 설정 순서

모든 단계는 `SMTP_USER`(발송용 Gmail) 계정으로 로그인한 상태에서 해요. 환영 메일은 이 계정에서 나가요.

1. Google 시트를 새로 만들고 이름을 `모닥로그 AI 리포트 구독 관리`로 정해요. 주소창의 `/d/<ID>/edit`에서 `<ID>` 부분을 복사해 둬요. 이 값이 `SHEET_ID`예요.
2. 시트에서 **확장 프로그램 → Apps Script**를 열어요. 기본으로 있는 `Code.gs` 내용을 모두 지우고, 이 저장소의 `apps_script/Code.gs` 내용을 그대로 붙여 넣은 뒤 저장해요.
3. 왼쪽 **프로젝트 설정(톱니바퀴)** 에서 **"편집기에서 'appsscript.json' 매니페스트 파일 표시"** 를 켜요. 편집기로 돌아가면 파일 목록에 `appsscript.json`이 보여요. 그 내용을 모두 지우고 이 저장소의 `apps_script/appsscript.json` 내용을 붙여 넣은 뒤 저장해요. 이 파일이 Gmail API(고급 서비스)를 켜고, 시간대를 `Asia/Seoul`로 맞춰요. 왼쪽 **서비스** 목록에 `Gmail`이 보이면 돼요.
4. 내 컴퓨터 터미널에서 비밀값 네 개를 만들어요. 아래 명령을 네 번 실행하면 서로 다른 값이 네 줄 나와요.

   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   순서대로 `TOKEN_SECRET`, `LIST_KEY`, `SEND_LIST_KEY`, `ADMIN_KEY`로 써요.
5. **프로젝트 설정 → 스크립트 속성 → 스크립트 속성 추가**에서 다섯 개를 넣어요.
   - `SHEET_ID`: 1단계에서 복사한 시트 ID
   - `TOKEN_SECRET`: 4단계의 첫 번째 값
   - `LIST_KEY`: 4단계의 두 번째 값 (해지한 토큰 목록만 읽는 키)
   - `SEND_LIST_KEY`: 4단계의 세 번째 값 (주간 발송이 이름과 주소를 읽는 키)
   - `ADMIN_KEY`: 4단계의 네 번째 값 (기존 구독자를 한 번 가져오는 키)
6. 편집기 위쪽 함수 목록에서 `setup`을 고르고 **실행**을 눌러요. 권한 확인 창이 떠요.
   - "Google에서 확인하지 않은 앱" 화면(확인되지 않은 앱)이 나오면 **고급**을 누르고 맨 아래 **(프로젝트 이름)(으)로 이동(안전하지 않음)** 을 눌러요. 내 계정으로 만든 내 스크립트라서 나오는 화면이에요.
   - 권한 목록을 확인하고 **허용**을 눌러요.

   실행이 끝나면 시트에 탭 두 개가 생겨요.
   - `unsubscribes`: 첫 줄 `id | at | via`
   - `subscribers`: 첫 줄 `id | email | name | status | consent_at | consent_version | source | created_at | welcomed_at`

   `setup`은 환영 메일을 보내는 1분 트리거도 함께 만들어요. 왼쪽 **트리거(시계 모양)** 를 열면 `processWelcomeQueue`, 시간 기반, 1분마다 실행되는 줄이 하나 보여요. `setup`을 여러 번 실행해도 탭과 트리거는 하나씩만 생겨요.
7. 함수 목록에서 `selfTest`를 고르고 실행해요. 실행 로그에 `PASS` 한 줄이 나와야 해요.
   - `FAIL` 뒤에 붙는 단어는 실패한 검사 이름이에요 (`token`, `greeting`, `escape`, `gmail`, `user`, `latest`, `tabs`, `trigger`). 여기서 멈추고 그 단어들을 Claude에게 알려 주세요.
   - 실행하자마자 권한(authorization) 오류가 나면 `appsscript.json`에서 `"oauthScopes"` 부분(대괄호까지)을 지우고 저장한 뒤 `setup`과 `selfTest`를 다시 실행해요. 그러면 Apps Script가 필요한 권한을 스스로 찾아서 다시 물어봐요.
8. **배포 → 새 배포**를 누르고 유형으로 **웹 앱**을 골라요. 새 배포는 이번 한 번만 써요.
   - 다음 사용자 인증 정보로 실행: **나**
   - 액세스 권한이 있는 사용자: **모든 사용자**

   배포하면 `https://script.google.com/macros/s/.../exec` 형태의 웹 앱 URL이 나와요. 이 주소는 모든 메일 헤더와 사이트 폼에 들어가는 공개 값이라 비밀이 아니에요. Claude에게 알려 주면 코드의 `UNSUBSCRIBE_ENDPOINT`에 넣어서 커밋해요.
9. GitHub 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에서 네 개를 만들어요.
   - `UNSUBSCRIBE_TOKEN_SECRET`: 5단계의 `TOKEN_SECRET`과 같은 값
   - `UNSUBSCRIBE_LIST_KEY`: 5단계의 `LIST_KEY`와 같은 값
   - `SUBSCRIBER_LIST_KEY`: 5단계의 `SEND_LIST_KEY`와 같은 값
   - `SUBSCRIBE_ADMIN_KEY`: 5단계의 `ADMIN_KEY`와 같은 값

## 터미널로 확인하기

아래 명령은 키를 화면이나 터미널 기록에 남기지 않도록 `read -rs`로 받아요. 명령을 실행하면 아무것도 보이지 않는 채로 입력을 기다리는데, 키를 붙여 넣고 Enter를 누르면 돼요.

```
read -r URL                       # 8단계의 /exec URL을 붙여 넣고 Enter
read -rs LIST_KEY                 # LIST_KEY를 붙여 넣고 Enter (화면에 안 보여요)
read -rs SEND_LIST_KEY            # SEND_LIST_KEY를 붙여 넣고 Enter
```

1. 해지 목록 읽기를 확인해요.

   ```
   curl -sL -d "action=list&key=$LIST_KEY" "$URL"; echo
   curl -sL -d "action=list&key=wrong" "$URL"; echo
   ```

   첫 줄은 `{"version":1,"ids":[]}`, 둘째 줄은 `{"error":"forbidden"}`이 나와야 해요.
2. 구독자 목록 읽기(`action=members`)를 확인해요.

   ```
   curl -sL -d "action=members&key=$SEND_LIST_KEY" "$URL"; echo
   curl -sL -d "action=members&key=$LIST_KEY" "$URL"; echo
   ```

   첫 줄은 `{"version":1,"subscribers":[]}`, 둘째 줄은 `{"error":"forbidden"}`이 나와야 해요. 나중에 구독자가 생긴 뒤에는 첫 줄에 이름과 주소가 나오니, 그 내용은 어디에도 옮기지 않아요.
3. 원클릭 해지를 확인해요. 아래 토큰은 테스트용 값이라 실제 구독자와 겹치지 않아요.

   ```
   curl -s -o /dev/null -w "%{http_code}\n" -d "List-Unsubscribe=One-Click" "$URL?t=82a671b5104273fe07992f40d81000c8"
   ```

   `302`가 나오고, 시트의 `unsubscribes` 탭에 `82a671b5104273fe07992f40d81000c8` 행이 생기면 돼요. 확인한 뒤 그 테스트 행을 지워요. 첫 줄(`id | at | via`)은 지우지 않아요.
4. 사이트 폼이 결과를 읽을 수 있는지(CORS) 확인해요. `website` 칸을 채워 보내는 요청이라 시트에는 아무것도 적히지 않아요.

   ```
   curl -sL -D - -o /dev/null -H "Origin: https://silber60.github.io" -d "action=subscribe&fmt=json&website=x" "$URL" | grep -i "access-control-allow-origin"
   ```

   `access-control-allow-origin`이 들어간 줄이 하나 나와야 해요. 아무것도 안 나오면 그대로 Claude에게 알려 주세요.

다 끝나면 `unset URL LIST_KEY SEND_LIST_KEY`로 터미널에 남은 값을 지워요.

## Claude에게 알려 줄 것

- 8단계의 `/exec` URL
- `selfTest` 결과 (`PASS`, 또는 `FAIL`과 검사 이름)
- 트리거 화면에 `processWelcomeQueue` 줄이 있는지
- 확인 1, 2의 결과가 위와 같은지 (구독자가 있으면 내용 대신 "같음/다름"만)
- 확인 3의 상태 코드, 시트에 행이 생겼는지, 지웠는지
- 확인 4에서 `access-control-allow-origin` 줄이 나왔는지

키 값과 시트 ID, 구독자 목록 내용은 알려 주지 않아요. Claude에게 필요한 값은 `/exec` URL 하나예요.

## 못 받은 환영 메일 다시 보내기

첫 호를 보내기 전에 가입한 사람은 예전 스크립트에서 환영 메일을 받지 못했어요. 2026-11-04에 고친 뒤로는 이런 신청도 호가 나올 때까지 기다렸다가 보내요. 이미 놓친 사람에게 보내려면 아래처럼 해요.

1. `Code.gs`를 이 저장소의 최신 내용으로 바꾸고 저장해요. 아래 "나중에 스크립트를 고칠 때"의 새 버전 배포도 해 둬요.
2. 함수 선택 칸에서 `requeueUnwelcomed`를 고르고 **▷ 실행**을 눌러요.
3. 1~2분 안에 환영 메일이 가요. 이미 환영 메일을 받은 사람과 가져오기로 들어온 사람에게는 보내지 않아요. 하루 50통 제한도 그대로예요.

## 나중에 스크립트를 고칠 때

1. Apps Script 편집기에서 `Code.gs`(바뀌었다면 `appsscript.json`도)를 새 내용으로 바꾸고 저장해요.
2. **배포 → 배포 관리**를 열고, 지금 쓰는 배포의 **수정(연필)** 을 눌러요.
3. 버전에서 **새 버전**을 고르고 **배포**를 눌러요. URL은 그대로예요.
4. "새 배포"는 누르지 않아요.

트리거는 배포와 상관없이 저장된 최신 코드로 돌아요. `setup`을 다시 실행해도 트리거가 늘지 않아요.

키를 바꿔야 할 때(`LIST_KEY`, `SEND_LIST_KEY`, `ADMIN_KEY`)는 스크립트 속성과 GitHub secret을 같은 새 값으로 함께 바꿔요. `TOKEN_SECRET`은 바꾸지 않아요.
