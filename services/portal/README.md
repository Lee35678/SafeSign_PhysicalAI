# portal — SafeSign 회사 웹사이트

교육장 키트(RPi5)를 켜지 않아도 쓸 수 있는 회사 웹사이트입니다. 교육장 키트와 **같은 회원 DB(Supabase)** 를 쓰므로,
사이트에서 가입한 계정으로 교육장에서 바로 로그인하고, 교육장에서 쌓인 학습 기록을 사이트에서 볼 수 있습니다.
클라우드(Render)에 올려 항상 켜 두는 것을 기준으로 합니다. 전체 구성은 루트 [README](../../README.md) §4.4를 보십시오.

## 1. 할 수 있는 일

| 기능 | 내용 |
| --- | --- |
| 회사 소개 | 제품(AI Hand · AI 비전 스테이션 · picar), 교육 과정 7종, 검증 결과, 회사 정보, 문의 |
| 회원가입 · 로그인 | 교육장과 같은 규칙(비밀번호 8자 이상, 영문·숫자 포함 / 로그인 실패 5회(10분 안) 시 10분 잠금). 가입하면 사원 코드(예: `SS-00001`)가 발급되고, 교육장 키트에서 같은 계정으로 로그인합니다 |
| 아이디 · 비밀번호 찾기 | 이름 + 사원 코드 → 가린 이메일 표시 / 가입 이메일로 받은 6자리 코드 → 새 비밀번호 |
| 내 정보 | 계정 정보, 수료 여부(7종 전 과정을 한 번이라도 마쳤으면 수료), 교육 이력, 수신호별 마지막 결과(정답·오답·시간 초과, 오답이면 인식된 수신호) |
| 수료증 | 수료한 회차마다 발급. 교육장과 같은 디자인(`frontend/cert.js`), 이미지 저장·인쇄 가능 |

카메라 영상은 받지 않습니다. 교육(시범·판정)은 교육장 키트에서만 합니다.

### DB 사용 범위

- 스키마([`services/web/supabase/schema.sql`](../web/supabase/schema.sql))를 바꾸지 않습니다.
- 쓰기는 회원가입(Auth 계정 + `members` 행, 교육장과 같은 경로)뿐입니다.
- 학습 기록(`training_sessions` · `training_results`)은 로그인한 본인 것만 읽습니다.
- 가입·로그인·찾기 코드는 교육장 web의 `services/web/backend/members.py`를 그대로 가져다 씁니다. 그래서 두 사이트의 규칙이 같습니다.
  Docker 이미지에도 이 파일이 함께 들어갑니다(빌드 문맥이 `services/`인 이유).

DB 준비 방법은 [`services/web/supabase/README.md`](../web/supabase/README.md)를 보십시오.

## 2. 배포 — Render

저장소 루트의 [`render.yaml`](../../render.yaml)에 설정이 들어 있습니다.
(Docker, `services/portal/Dockerfile`, 빌드 문맥 `services`, 무료 플랜, 싱가포르 리전, 헬스 체크 `/health`)

1. render.com에서 **New → Blueprint** → 이 저장소를 고릅니다. 배포 브랜치는 `main`입니다. 이 브랜치에 push하면 자동으로 다시 배포됩니다.
2. 비밀 값 3개를 Render 대시보드 입력 창에 넣습니다. `render.yaml`에는 적지 않습니다(`sync: false`).
   - `SUPABASE_URL` · `SUPABASE_SERVICE_ROLE_KEY` — 교육장 키트와 **같은 값**
   - `PORTAL_SESSION_SECRET` — 32자 이상 무작위 값. 만드는 법: `python -c "import secrets;print(secrets.token_hex(32))"`
3. 배포가 끝나면 Render가 HTTPS 주소를 붙여 줍니다. `https://<주소>/health/db`가
   `{"status":"ok","store":"supabase","db":"ok"}`를 돌려주면 정상입니다.

Render에서는 위 값이 하나라도 빠지면(또는 세션 키가 32자 미만이면) 서버가 시작하지 않습니다(`PORTAL_STRICT_CONFIG`).
빠진 채로 돌면 재시작 때마다 전원이 로그아웃되고, 회원이 재배포 때 지워지는 컨테이너 파일에 저장되기 때문입니다.

### 무료 플랜 주의

- Render 무료 서비스는 15분 동안 요청이 없으면 잠들고, 다음 접속 때 깨어나는 데 30초~1분 걸립니다.
- Supabase 무료 프로젝트는 7일 동안 요청이 없으면 일시 정지됩니다.
- 둘 다 막으려면 외부 모니터(예: UptimeRobot 무료)로 `https://<주소>/health/db`를 5분마다 부르게 합니다. `/health/db`는 DB까지 한 번 읽습니다.
- 무료 플랜의 한도·약관은 바뀔 수 있으니 가입할 때 확인하십시오.

### 직접 서버에서 Docker로 돌릴 때

저장소 루트에서:

```bash
docker build -f services/portal/Dockerfile -t safesign-portal services
docker run -d --restart unless-stopped -p 8100:8100 --env-file .env safesign-portal
```

반드시 **HTTPS 뒤에** 두십시오(비밀번호가 오갑니다). 이미지는 `--proxy-headers`로 앞단의 HTTPS를 인식하고,
호스팅이 `$PORT`를 주면 그 포트를, 없으면 8100을 씁니다.

## 3. 로컬 실행

```bash
cd services/portal
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8100
# → http://localhost:8100
```

- 저장소 루트의 `.env`가 있으면 시작할 때 읽습니다(셸·호스팅에서 준 값이 우선). 형식은 [`.env.example`](../../.env.example)을 보십시오.
- Supabase 키가 없으면 **로컬 모드**로 돕니다. 회원은 `services/web/data`의 파일에 저장되고(교육장 web과 함께 씀),
  화면에 로컬 모드 안내가 나오며, 비밀번호 찾기 코드는 메일 대신 서버 로그에 찍힙니다. 운영에는 쓰지 마십시오.

## 4. 환경변수

| 이름 | 운영 필수 | 설명 |
| --- | --- | --- |
| `SUPABASE_URL` · `SUPABASE_SERVICE_ROLE_KEY` | 예 | 교육장 키트와 같은 값(같은 회원 DB). 비우면 로컬 모드 |
| `PORTAL_SESSION_SECRET` | 예 | 로그인 쿠키 서명 키, 32자 이상. 없으면 임시 키를 만들어 재시작 때 모두 로그아웃됨 |
| `PORTAL_COOKIE_SECURE` | | `auto`(기본, HTTPS일 때만 Secure) · `1` · `0`. `render.yaml`에서 `1`로 설정 |
| `PORTAL_SESSION_TTL_S` | | 로그인 유지 시간(초), 기본 `28800`(8시간) |
| `PORTAL_STRICT_CONFIG` | | `1`이면 설정 누락 시 시작하지 않음. 기본은 Render(`RENDER` 변수 있음)에서 `1`, 그 밖에는 `0` |

## 5. 보안

- **`SUPABASE_SERVICE_ROLE_KEY`는 서버에만 둡니다.** 브라우저 코드·git·메신저에 넣지 마십시오.
  루트 `.env`는 `.gitignore`에 들어 있어 git에 올라가지 않습니다.
- 로그인은 사람마다 서명된 쿠키(`ss_portal`, HMAC-SHA256)로 유지합니다. HttpOnly · SameSite=Lax · HTTPS면 Secure.
- `/api/*`에 대한 POST는 `X-SafeSign-Portal: 1` 헤더가 없으면 403으로 막습니다(다른 사이트에서 쿠키를 싣고 보내는 요청 차단).
- 모든 응답에 CSP 등 보안 헤더를 붙이고, `/api/*`는 `Cache-Control: no-store`, HTTPS면 HSTS를 붙입니다.

## 6. API 요약

POST는 모두 `X-SafeSign-Portal: 1` 헤더가 필요합니다.

| 메서드 · 경로 | 설명 |
| --- | --- |
| `POST /api/auth/signup` | 회원가입(`email`, `password`, `name`, `org` 선택). 성공하면 바로 로그인 쿠키 발급 |
| `POST /api/auth/login` | 로그인(`email`, `password`). 성공하면 로그인 쿠키 발급 |
| `POST /api/auth/logout` | 로그아웃(쿠키 삭제) |
| `POST /api/auth/find-id` | 아이디 찾기(이름 + 사원 코드 → 가린 이메일) |
| `POST /api/auth/password/request` | 비밀번호 재설정 코드 요청(가입 이메일로 6자리 코드) |
| `POST /api/auth/password/reset` | 코드 + 새 비밀번호로 재설정 |
| `GET /api/session` | 현재 로그인한 사람(사원 코드·이름)과 저장소 종류(`supabase`/`local`) |
| `GET /api/me` | 내 정보·수료 여부·교육 이력. 로그인 안 했으면 401 |
| `GET /health` | 서버 상태(Render 헬스 체크) |
| `GET /health/db` | DB까지 확인. 실패하면 503 |
| `GET /` | 회사 사이트 화면(`frontend/`) |

개발 자료(테스트, 화면 영상 원본 등)는 `dev` 브랜치에 있습니다.
