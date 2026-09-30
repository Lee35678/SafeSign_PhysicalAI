# portal — SafeSign 회사 웹사이트 (주식회사 심기일전)

담당: 이동혁 · 2026-09-30

교육장 키트 화면(`services/web`)은 RPi5에서 켜야만 돌아가서, 사원이 미리 가입하거나 수료증을 다시 받으려면 RPi5가 필요했다.
이 사이트는 **RPi5 없이 회사 서버에서 항상 켜 두는** 웹서버다. **같은 회원 DB(Supabase)** 를 쓴다.

| 기능 | 내용 |
| --- | --- |
| 회사 소개 | 제품(AI Hand · AI 비전 스테이션 · picar), 교육 과정 7종, 검증 결과(최종 KPI 210시도), 회사·연혁, 문의 — **시연용 가상 기업** |
| 회원가입 · 로그인 | 교육장과 같은 규칙(비밀번호 8자+영문·숫자, 실패 5회/10분 잠금). 가입하면 사원 코드(SS-00001) 발급 → 교육장 키트에서 같은 계정으로 로그인 |
| 아이디 · 비밀번호 찾기 | 이름+사원 코드 → 가린 이메일 / 메일 6자리 코드 → 새 비밀번호 |
| 내 정보 | 계정 정보, **수료 여부**(7종 전 과정을 한 번이라도 마쳤으면 수료), 교육 이력, 수신호별 결과(마지막 시도: 정답·오답·시간 초과, 오답이면 인식된 수신호) |
| 수료증 | 수료한 회차마다 발급 — 교육장과 같은 디자인(`frontend/cert.js`), 이미지 저장·인쇄 |

**카메라 영상은 받지 않는다.** 교육(시범·판정)은 교육장 키트에서만 한다.

## DB — 기존 스키마를 바꾸지 않는다

- `services/web/supabase/schema.sql`은 **그대로**다. 이 사이트가 하는 쓰기는 회원가입(교육장과 같은 경로: Auth 계정 + `members` 행)뿐이고,
  학습 기록(`training_sessions` · `training_results`)은 **읽기만** 한다 — 본인 `user_id`의 행만.
- 코드는 교육장 web의 `backend/members.py` 저장소를 그대로 쓴다(가입·로그인·찾기 규칙이 두 사이트에서 어긋나지 않게).
  조회용으로 `get_member` · `list_sessions` 두 메서드만 추가했다(읽기 전용).

## 로그인 · 보안

- 교육장은 화면 1대라 "지금 학습자"를 서버 전역으로 두지만, 이 사이트는 여러 사람이 동시에 쓴다 → **사람마다 서명된 쿠키**
  (HMAC-SHA256, HttpOnly · SameSite=Lax · HTTPS면 Secure, 8시간).
- POST에는 `X-SafeSign-Portal: 1` 헤더가 필요하다(다른 사이트에서 쿠키를 싣고 보내는 요청 차단).
- CSP 등 보안 헤더, `/api/*` `no-store`, HTTPS면 HSTS. `service_role` 키는 서버 환경변수에만.

## 실행

```bash
# 개발 (키 없이 = 로컬 모드: services/web/data 의 회원 파일을 교육장 web과 함께 쓴다)
cd services/portal
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8100
# → http://localhost:8100
```

| 환경변수 | 필수 | 설명 |
| --- | --- | --- |
| `SUPABASE_URL` · `SUPABASE_SERVICE_ROLE_KEY` | 운영 | 교육장 web과 **같은 값** — 같은 회원 DB |
| `PORTAL_SESSION_SECRET` | 운영 | 쿠키 서명 키, 32자 이상 무작위(`python -c "import secrets;print(secrets.token_hex(32))"`). 없으면 임시 키 → 재시작 때 모두 로그아웃 |
| `PORTAL_COOKIE_SECURE` | | `auto`(기본, HTTPS일 때만 Secure) · `1` · `0` |
| `PORTAL_SESSION_TTL_S` | | 로그인 유지 시간(초), 기본 28800 |

## 비밀 키 — 저장소 루트 `.env` (git에 올라가지 않는다)

`SUPABASE_URL` · `SUPABASE_SERVICE_ROLE_KEY` · `PORTAL_SESSION_SECRET`은 **저장소 루트의 `.env`** 에 둔다(`.gitignore`의 `.env`·`*.env`·`.env.*`).
web(RPi5)과 portal 모두 시작할 때 이 파일을 읽고(`members._load_dotenv` — 셸·호스팅에서 준 값이 우선), **테스트는 읽지 않는다.**
RPi5에는 git으로 가지 않으니 파일을 직접 복사한다: `scp .env <사용자>@<RPi5 주소>:~/git/SafeSign_PhysicalAI/.env`

## 외부에 열기 — ngrok (지금 쓰는 방법, 2026-09-30 결정)

회사 사이트를 이 PC에서 띄우고 **ngrok이 HTTPS 주소를 붙여** 밖에서 들어오게 한다. 서버를 따로 배포하지 않는다.

```powershell
# 터미널 1 — 회사 사이트 (루트 .env의 Supabase 키를 자동으로 읽는다)
cd C:\SafeSign_PhysicalAI\services\portal
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100

# 터미널 2 — 외부 주소
ngrok http 8100
#   고정 주소를 쓰려면(무료 계정 1개): ngrok 대시보드 Domains에서 받은 주소로
#   ngrok http --url=<받은 주소>.ngrok-free.app 8100
```

- `--host 127.0.0.1`로 띄운다 — 밖에서는 ngrok을 거쳐서만 들어온다(같은 공유기의 다른 PC에서 8100으로 바로 붙지 못하게).
- 코드 변경 없음: uvicorn은 기본으로 같은 PC(127.0.0.1)의 전달 헤더를 믿어서, ngrok HTTPS로 온 요청을 HTTPS로 알고
  로그인 쿠키에 Secure를 붙이고, 로그인 실패 잠금도 접속자 IP별로 동작한다.
- **이 PC와 두 터미널이 켜져 있는 동안만** 열린다. 시연 기간에는 절전 모드를 끈다.
- 무료 ngrok은 브라우저로 처음 들어올 때 ngrok 안내 화면이 한 번 뜬다("Visit Site"를 누르면 된다). 사용량 한도가 있다.
- 주소를 무작위로 받으면(`ngrok http 8100`) ngrok을 다시 켤 때마다 바뀐다 — 팀원에게 매번 새 주소를 알려야 한다. 고정 주소를 권한다.
- Supabase 무료 프로젝트는 7일 동안 요청이 없으면 일시 정지된다. 시연 전 일주일 넘게 쉬었다면 대시보드에서 다시 켠다(또는 외부 모니터로 `/health/db`).

## (다른 방법) 항상 켜 두기 — 무료 (Render + 5분 확인 요청)

**Render 무료 웹 서비스**에 Docker로 올리고, **무료 외부 모니터**가 5분마다 `/health/db`를 부르게 한다.

- 무료 서비스는 15분 동안 요청이 없으면 잠들고, 다음 접속 때 깨느라 30초~1분 걸린다. 5분마다 요청이 오면 잠들지 않는다.
- `/health/db`는 DB도 한 번 읽는다. Supabase 무료 프로젝트는 **7일 동안 요청이 없으면 일시 정지**되는데, 이것도 함께 막는다.
- 무료 사용 시간(월 750시간)은 서비스 1개를 한 달 내내 켜 두기에 맞다. 약관·한도는 바뀔 수 있으니 가입할 때 확인한다.

1. **render.com** 가입(GitHub 계정) → **New → Blueprint** → 이 저장소 선택. 루트의 `render.yaml`을 읽어 설정이 채워진다
   (Docker, `services/portal/Dockerfile`, 빌드 문맥 `services`, 무료, 싱가포르 리전, 헬스 체크 `/health`).
   - 브랜치는 `dev`·`main` 중 배포할 쪽을 고른다(`feature/web-member`에서 먼저 확인해도 된다). 그 브랜치에 push할 때마다 자동으로 다시 배포된다.
2. 비밀 값 3개를 입력 창에 넣는다 — 루트 `.env`의 `SUPABASE_URL` · `SUPABASE_SERVICE_ROLE_KEY` · `PORTAL_SESSION_SECRET` 값 그대로.
3. 배포가 끝나면 주소가 생긴다: `https://safesign-portal.onrender.com`(이름이 겹치면 뒤에 글자가 붙는다). HTTPS는 Render가 자동으로 붙인다.
   확인: `https://<주소>/health/db` → `{"status":"ok","store":"supabase","db":"ok"}`
4. **uptimerobot.com**(무료) 가입 → **New Monitor** → HTTP(s) → URL `https://<주소>/health/db` → 간격 **5분**.
   멈추면 메일로도 알려 준다.

> 다른 무료 방법: **Oracle Cloud Always Free** VM은 잠들지 않는 진짜 상시 서버다(가입 때 카드 인증 필요, 설정이 더 많다).
> VM에 Docker를 깔고 위의 `docker build` / `docker run --restart unless-stopped` 두 줄 + Caddy로 HTTPS. 이때도 Supabase 일시 정지를 막으려면
> 외부 모니터로 `/health/db`를 부른다.

직접 서버에서 돌릴 때(Docker):

```bash
docker build -f portal/Dockerfile -t safesign-portal services
docker run -d --restart unless-stopped -p 8100:8100 --env-file .env safesign-portal
```

반드시 **HTTPS 뒤에** 둔다(비밀번호가 오간다). 이미지는 `--proxy-headers`로 앞단의 HTTPS를 인식하고, 호스팅이 주는 `$PORT`를 쓴다.

## 테스트

```bash
cd services/portal && python -m pytest -q      # 10개 — 쿠키·CSRF·수료 판정·타인 기록 차단·찾기/재설정·Supabase 조회 형식
```
