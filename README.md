# 배재대 알리미

배재대학교 학식과 공지를 카카오톡에서 조회하고, 새 공지와 학식 소식을 Telegram으로 받는 비공식 챗봇입니다. 학식과 공지 검색 결과는 배재대 홈페이지에서 가져옵니다.

[배재대 알리미 카카오톡 채널](https://pf.kakao.com/_hIeGX) · [서비스 상태 페이지 (UptimeRobot)](https://stats.uptimerobot.com/aoBQJ1uTFV)

## 사용하기

| 하고 싶은 일 | 카카오톡에서 |
| --- | --- |
| 학식 보기 | 메뉴에서 **오늘식단** 또는 **내일식단**을 누르거나 `내일 점심`, `학식 7/21`처럼 입력 |
| 최신 공지 보기 | 일반공지, 학사공지 또는 생활관 메뉴에서 게시판을 선택하면 최신 공지 최대 4건과 원문 링크 표시 |
| 키워드로 공지 찾기 | **공지 검색**을 누르거나 `검색`을 입력한 뒤 `장학금`처럼 키워드 입력 |

공지 검색은 **학사공지, 일반공지, 생활관 일반공지, 생활관 입퇴사공지**에서 제목을 검색하고, 각 게시판의 검색 결과 첫 페이지에서 총 최대 5건을 모아 보여줍니다. 결과 아래의 **다시 검색** 버튼으로 새 키워드를 입력할 수 있습니다.

### Telegram 알림

| 알림 | 확인 시각 (한국 시간) | 발송 조건 |
| --- | --- | --- |
| 새 공지·제목 변경 | 매시 00·10·20·30·40·50분 | 이전에 저장한 공지 상태와 비교해 신규 공지나 제목 변경을 감지했을 때 |
| 오늘 식단 | 매일 오전 10시 | 당일 식단이 등록된 평일 |
| 다음 주 식단 등록 | 매일 오전 10시 | 다음 주 평일 메뉴가 확인되면 해당 주에 한 번 |

Firebase Realtime Database의 `/notices`에는 게시판별 최신 글 번호, 고정 공지 ID, 제목과 제목 해시를 저장합니다. `/next_meal_alert`에는 발송한 주의 월요일 날짜를 저장합니다. 서버가 시작되면 다음 정해진 시각에 공지 확인이 시작됩니다.

## 로컬 실행

Python 3.12를 기준으로 합니다. 저장소 루트에서 가상환경을 만들고 의존성을 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`에 아래 값을 채우고 실행합니다. 시스템 환경변수가 함께 설정돼 있으면 시스템 값을 사용합니다. 로컬에서 운영용 인증정보로 서버를 시작하면 예약된 시각에 운영 DB와 Telegram 채팅에 접근하므로 개발 검증에는 테스트용 DB와 채팅을 사용하세요.

| 환경변수 | 값 |
| --- | --- |
| `FIREBASE_DB_URL` | Firebase Realtime Database 기본 HTTPS URL |
| `FIREBASE_SECRET` | 동일한 Realtime Database의 REST 인증에 사용하는 DB 시크릿 |
| `NOTIFIER_TELEGRAM_TOKEN` | BotFather가 발급한 Telegram 봇 토큰 |
| `CHAT_ID` | 알림을 받을 Telegram 채팅 ID. 봇과의 개인 채팅이라면 수신자의 Telegram 사용자 ID |
| `PORT` | 실행 포트. 기본값은 `5000` |

```powershell
.\.venv\Scripts\python.exe main.py
Invoke-RestMethod http://localhost:5000/
```

두 번째 명령은 서버를 실행한 상태에서 별도 PowerShell 창에 입력합니다. 실제 토큰과 인증정보는 로컬 `.env`, Cloudtype 시크릿 또는 GitHub Actions 시크릿에 저장합니다.

## Cloudtype 배포

[배포 워크플로](.github/workflows/deploy.yml)가 `main`에 푸시될 때 Cloudtype 배포를 요청합니다. 워크플로의 `project`에는 배포할 **스페이스/프로젝트**가 설정되어 있으며, 서비스는 `main` 배포환경의 `pcu-chatbot`입니다.

1. Cloudtype의 **배포환경 → 설정 → 시크릿 관리**에서 위 표의 필수 환경변수 네 개를 **동일한 이름으로** 등록합니다.
2. GitHub 저장소의 **Settings → Secrets and variables → Actions**에 `CLOUDTYPE_TOKEN`(Cloudtype API 키)과 `GHP_TOKEN`(GitHub 배포용 토큰)을 등록합니다.
3. GitHub Actions 배포 결과와 Cloudtype 실행 로그를 확인하고, 서비스 주소의 `GET /`에 응답하는지 확인합니다. [Cloudtype 환경변수](https://docs.cloudtype.dev/ko/developers/env) · [Cloudtype GitHub Actions](https://docs.cloudtype.dev/ko/developers/githubactions)

Telegram 개인 알림을 받으려면 사용할 봇과의 채팅에서 **시작**을 누르거나 `/start`를 보냅니다. `NOTIFIER_TELEGRAM_TOKEN`에는 그 봇의 토큰을, `CHAT_ID`에는 알림을 받을 본인의 사용자 ID를 지정합니다.

### 카카오 챗봇 연결

카카오 챗봇 관리자센터에서 배포한 서비스의 HTTPS 주소에 아래 경로를 붙여 등록합니다. 각 블록의 봇 응답은 **스킬데이터 사용**으로 설정합니다. [카카오 스킬 만들기](https://kakaobusiness.gitbook.io/main/tool/chatbot/skill_guide/make_skill)

| 스킬 URL 경로 | 역할 |
| --- | --- |
| `POST /meal` | 날짜별 학식 조회 |
| `POST /notice` | 게시판별 최신 공지 조회 |
| `POST /search` | 공지 제목 검색 |

**공지 검색** 블록의 사용자 발화에 `검색`을 추가합니다. 필수 파라미터 이름은 `search_query`, 엔티티는 `@sys.text`, 값은 `$search_query`를 사용합니다. 되묻기 질문을 설정하고 **봇 테스트**에서 `검색`과 `장학금`을 차례로 보낸 뒤 블록과 스킬을 배포합니다. [카카오 파라미터 설정](https://kakaobusiness.gitbook.io/main/tool/chatbot/main_notions/setting_parameter)

운영 상태는 `GET /monitoring/health`에서 서버 시각과 함께, `GET /monitoring/status`에서 앱 버전과 가동 시간과 함께 확인할 수 있습니다.

## 운영 진단

Cloudtype 서비스 터미널에서 확인하려는 범위를 선택합니다.

| 명령 | 확인할 내용 |
| --- | --- |
| `python -m diagnostics db` | 운영 공지 DB 읽기 |
| `python -m diagnostics notices` | 학교 게시판에서 최신 공지 조회 |
| `python -m diagnostics write` | Firebase 테스트 데이터 저장 및 재조회 |
| `python -m diagnostics telegram` | 설정된 Telegram 채팅에 테스트 메시지 한 건 발송 |
| `python -m diagnostics` | DB 읽기 → 학교 공지 조회 → 조회 결과 저장 및 재조회 → Telegram 테스트 발송 |

쓰기 테스트는 Firebase의 `/diagnostics/<테스트 ID>`에 기록을 남깁니다. DB 오류는 `db`, Telegram 오류는 `telegram`부터 실행하면 해당 연결만 확인할 수 있습니다. 학교 사이트에 대한 HTTP 요청은 Cloudtype 실행 로그에서 경로, 응답 시간, HTTP 상태를 확인할 수 있습니다.

## 소스 구조

| 파일 | 역할 |
| --- | --- |
| [main.py](main.py) | FastAPI 라우팅, 카카오 응답, 스케줄 등록 |
| [bot_meal.py](bot_meal.py) | 식단 조회, 오늘 식단 및 다음 주 식단 알림 |
| [bot_notice.py](bot_notice.py) | 게시판 조회, 제목 검색, 공지 변경 감지 |
| [database.py](database.py) | Firebase REST 읽기·쓰기와 공지 DB 진단 |
| [diagnostics.py](diagnostics.py) | 학교·Firebase·Telegram 연동 테스트 |
| [monitoring.py](monitoring.py) | 헬스체크와 상태 응답 |
| [config.py](config.py), [utils.py](utils.py) | 환경변수, 게시판 설정, HTTP 요청과 공통 함수 |
