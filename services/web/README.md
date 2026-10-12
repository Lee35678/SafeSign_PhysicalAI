# web — 교육장 화면 · 교육 진행

RPi5에서 실행하는 교육장 화면 서버입니다. 교육장 PC 브라우저에 화면(SC-01~SC-07)을 띄우고, 교육 순서를 진행하며,
판정 결과에 따라 AI Hand·micro:bit(actuation)와 picar를 움직입니다.

- `backend/state_machine.py` — 교육 상태머신. vision 판정을 읽어 정답·오답을 정하고 장치에 명령을 보냅니다.
- `backend/camera.py` — 카메라 영상 중계. vision의 영상을 web 주소(`/api/camera/stream`)로 그대로 넘깁니다.
  브라우저는 교육장 PC에서 열리므로 RPi5 기준 주소인 vision에 직접 붙지 않고 web을 거칩니다.
- `backend/members.py` — 회원가입·로그인과 회원별 학습 결과 저장(Supabase 또는 RPi5 로컬 파일).
- `frontend/` — 화면(`index.html`, `station.css`, `main.js`). 글꼴·아이콘을 함께 넣어 두어 인터넷 없이 화면이 뜹니다.

전체 설치·실행 순서는 저장소 루트 [README](../../README.md) §4를 따릅니다.

## 1. 화면 흐름

| 화면 | 상태(`state`) | 내용 |
| --- | --- | --- |
| SC-01 | `landing` | 첫 화면. 장치 상태 표시, "시작하기" → 로그인·회원가입(게스트 가능, 가입하면 사원 코드 안내) |
| SC-02 | `curriculum_confirm` | 배울 수신호 7종과 AI Hand 시범·picar 동작 안내, "교육 시작" |
| SC-03 | `training` | 시범 → 확인 → 판정. 카메라 영상과 일치율 표시, 정답(03a)·오답(03b) 안내 |
| SC-04 | `camera_fail` | 판정 중 손이 계속 안 보일 때. 카메라 위치 조정 안내, 재시도 |
| SC-05 | `summary` | 학습 결과(합격 n/7, 첫 시도 정답, 총 시도). 결과는 회원 기록에 자동 저장 |
| SC-06 | `certificate` | 수료증. 이미지(PNG) 저장·인쇄, 다시 학습하기 |
| SC-07 | `reentry` | 교육 도중 화면을 다시 열었을 때. 이어하기는 없고 처음부터 다시 시작 |

교육 순서(7종): 정지 → 서행 → 좌회전_유도 → 우회전_유도 → 확인_완료 → 후진 → 주의

## 2. 교육 규칙

1. **시범** — 수신호마다 AI Hand가 먼저 손모양을 보여 줍니다. 이 동안에는 판정하지 않습니다.
2. **확인** — 학습자가 화면의 확인 버튼, `Space` 키, micro:bit `A` 버튼 중 하나를 누르면 판정을 시작합니다.
   micro:bit `A`는 시범이 끝난 뒤에 누른 것만 받습니다. micro:bit 연결이 끊기면 `Space` 키를 씁니다.
3. **판정**
   - 정답: 바로 확정합니다. picar가 그 신호대로 움직이고, micro:bit에 결과와 진행 상황이 표시되고,
     AI Hand가 정답 자세를 취한 뒤 다음 수신호 시범으로 넘어갑니다.
   - 오답: 같은 다른 수신호가 **1초** 이상 이어질 때만 확정합니다. AI Hand가 다시 시범을 보이고 확인 단계로 돌아갑니다.
   - 시간 초과: 판정 시작 후 **10초** 안에 정답이 없으면 시도 1회로 셉니다.
   - 확신이 낮거나(`below_tau`) 7종 밖의 손모양(`out_of_distribution`)이면 화면에 안내 문구만 띄우고 시도로 세지 않습니다.
4. **시도 횟수** — 수신호당 **3회**까지. 3회 안에 맞히면 합격, 넘기면 불합격으로 기록하고 다음 수신호로 넘어갑니다.
5. **판정 기준** — 일치율 = 목표 수신호에 대한 분류기 확률 × 100. 기준값(τ, 기본 75%)과 연속 프레임 수(기본 3)는
   vision에서 받아 화면에 표시합니다.
6. **카메라 안내(SC-04)** — 판정 중 손 미검출이 **25회 연속**(약 5초)이면 SC-04로 넘어갑니다. 손이 다시 보이면
   자동으로 돌아오고, 재시도(버튼·`Space`·micro:bit `A`)를 누르면 시범부터 다시 봅니다. 재시도는 시도 횟수에 넣지 않습니다.
7. **자동 로그아웃** — 교육이 끝난 뒤 5분 동안 입력이 없으면 로그아웃합니다(공용 PC 대비).

정답일 때 장치 호출 순서는 picar → micro:bit 결과 → AI Hand → micro:bit 진행입니다. 장치가 응답하지 않아도 교육은
멈추지 않습니다(연결 실패·서버 오류만 1회 다시 보냄). 장치 상태는 5초마다 확인해 화면 상단에 보여 줍니다.

## 3. 실행

RPi5에서, 반드시 `services/web` 폴더에서 실행합니다(화면 파일 `frontend/`를 이 폴더 기준으로 찾습니다).
가상환경과 의존성(`requirements.txt`) 설치는 루트 README §4.1 ③을 따릅니다.

```bash
cd ~/git/SafeSign_PhysicalAI/services/web
source .venv/bin/activate
VISION_URL=http://localhost:8001 ACTUATION_URL=http://localhost:8002 PICAR_URL=http://192.168.50.10:8000 \
  uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

- vision(8001)·actuation(8002)·picar를 먼저 켭니다. 켜는 순서와 한 번에 켜는 방법은 루트 README §4.2.
- 교육장 PC 브라우저에서 `http://<RPi5 주소>:8000`을 엽니다. 화면 기준은 1920×1080 전체 화면이며 1366×768에서도 잘리지 않습니다.
- 정상 확인: `curl http://localhost:8000/health` → `{"status": "ok", "service": "web"}`.
  장치 연결은 `curl http://localhost:8000/api/state`의 `devices`에서 봅니다(루트 README §4.3).

## 4. 환경변수

web은 시작할 때 저장소 루트 `.env`를 읽어 **비어 있는 환경변수만** 채웁니다. 셸이나 systemd에서 준 값이 항상 우선입니다.
`.env`는 [`.env.example`](../../.env.example)을 복사해 만듭니다(루트 README §4.1 ⑥).

| 이름 | 기본값 | 설명 |
| --- | --- | --- |
| `VISION_URL` | `http://localhost:8001` | vision 주소 (판정·영상) |
| `ACTUATION_URL` | `http://localhost:8002` | actuation 주소 (AI Hand·micro:bit) |
| `PICAR_URL` | `http://localhost:8003` | picar 주소. 실물은 `http://192.168.50.10:8000` — 빠지면 picar가 움직이지 않습니다 |
| `SUPABASE_URL` | (없음) | 회원 DB 주소. 비우면 로컬 저장 모드 |
| `SUPABASE_SERVICE_ROLE_KEY` | (없음) | 회원 DB 서버 전용 키. 브라우저·git·메신저에 노출 금지 |
| `PICAR_TIMEOUT_MS` | `500` | picar 응답 대기(ms) |
| `ACTUATION_COMMAND_TIMEOUT_S` | `1.5` | AI Hand `/command` 응답 대기(초). 손 동작이 끝난 뒤 회신하므로 길게 둡니다 |
| `ACTUATION_FEEDBACK_TIMEOUT_S` | `0.5` | micro:bit `/result`·`/progress` 응답 대기(초) |
| `VISION_POLL_INTERVAL_S` | `0.2` | vision 판정 확인 주기(초) |
| `VISION_TIMEOUT_S` | `0.5` | vision 응답 대기(초) |
| `DEVICE_HEALTH_INTERVAL_S` | `5.0` | 장치 상태 확인 주기(초) |
| `CAMERA_FAIL_STREAK_THRESHOLD` | `25` | 손 미검출 몇 회 연속이면 SC-04로 넘길지 (25회 ≈ 5초) |
| `WRONG_CONFIRM_S` | `1.0` | 같은 오답이 몇 초 이어져야 오답으로 확정할지 |
| `JUDGING_TIMEOUT_S` | `10.0` | 판정 한 번의 제한 시간(초) |
| `MAX_ATTEMPTS_PER_SIGNAL` | `3` | 수신호당 최대 시도 횟수 |
| `MICROBIT_BUTTON_CONFIRM` | `1` | micro:bit `A` 버튼을 확인 입력으로 쓸지. `0`이면 끔 |
| `BUTTON_TIMEOUT_S` | `0.3` | micro:bit 버튼 조회 대기(초) |
| `SUPABASE_TIMEOUT_S` | `5.0` | 회원 DB 응답 대기(초) |
| `RESULTS_RETRY_INTERVAL_S` | `30` | 저장 못 한 결과를 다시 보내는 주기(초) |
| `MEMBER_DATA_DIR` | `services/web/data` | 로컬 회원·결과 파일 폴더 |
| `TRIAL_LOG_DIR` | `services/web/logs` | 판정 기록 CSV 폴더 |
| `LOG_SUBJECT` | (없음) | 판정 기록의 `subject` 열 값. 없으면 로그인한 회원의 사원 코드 |
| `SAFESIGN_DOTENV` | (없음) | 루트 `.env` 대신 읽을 파일 경로 |
| `SAFESIGN_NO_DOTENV` | (없음) | `1`이면 `.env`를 읽지 않음 |

판정 기록: 판정이 확정될 때마다(정답·오답·시간 초과) `logs/web_trials_<web 시작 시각>.csv`에 한 줄씩 남깁니다.
`logs/`와 `data/`는 git에 올라가지 않습니다(개인정보 포함).

## 5. 주요 API

화면(`main.js`)이 쓰는 API입니다. `/api/*` 응답은 브라우저에 캐시되지 않습니다.

| 메서드 · 경로 | 내용 |
| --- | --- |
| `GET /health` | web 동작 확인 |
| `GET /api/state` | 현재 상태(`state`, `phase` = `demo`·`judging`), 목표 수신호, 진행, 최근 판정, 시도 횟수, 장치 상태(`devices`), 회원·저장 상태(`member`, `result_save`) |
| `POST /api/start` | 교육을 처음부터 시작하고 첫 수신호 시범을 보냄 |
| `POST /api/confirm` | 확인. 시범 단계에서만 받고, 그 밖에는 `{"status": "ignored"}` |
| `POST /api/camera_retry` | SC-04 재시도 — 시범 단계로 돌아감 |
| `POST /api/certificate` | 7종을 마친 뒤 수료증 발급 |
| `GET /api/camera/stream` | 카메라 영상(MJPEG) 중계. vision에 닿지 않으면 503 |
| `POST /api/auth/signup` · `login` · `guest` · `logout` | 회원가입(`email, password, name, org`) · 로그인(`email, password`) · 게스트 · 로그아웃 |
| `GET /api/auth/me` | 지금 로그인한 회원과 저장 방식(`store.backend` = `supabase` · `local`) |
| `POST /api/auth/find-id` | 이름 + 사원 코드로 가린 이메일 찾기 |
| `POST /api/auth/password/request` · `password/reset` | 비밀번호 재설정 — 메일로 받은 6자리 코드와 새 비밀번호 입력 |
| `POST /api/auth/results/retry` | 저장 대기 중인 결과를 바로 다시 보냄 |

## 6. 회원과 결과 저장

- 사원 코드(`SS-00001` 꼴)는 가입할 때 자동으로 부여됩니다. 교육을 시작할 때 로그인해 있던 사람에게 그 회차 결과가 저장됩니다.
- `.env`에 `SUPABASE_URL`·`SUPABASE_SERVICE_ROLE_KEY`가 있으면 Supabase에, 없으면 RPi5 로컬 파일(`data/`)에 저장합니다.
  브라우저는 Supabase에 직접 접근하지 않습니다.
- 인터넷이 끊기면 결과를 대기열에 쌓았다가 30초마다 다시 보냅니다. 그동안 로그인·가입은 할 수 없고 게스트로 교육할 수 있습니다.
  게스트 결과는 회원 DB에 올리지 않고 로컬 파일에만 남깁니다.
- SC-05 저장 상태: 회원 기록에 저장 · 인터넷 연결 대기(자동 재전송) · 이 교육장 기기에 저장(로컬 모드) · 게스트 학습 · 저장 실패.
- 보안: 로그인 5회 실패 시 10분 잠금, 비밀번호 8자 이상 + 영문·숫자.
- 회원 DB 준비·설정은 [supabase/README.md](supabase/README.md). 회사 사이트([services/portal](../portal/README.md))도
  같은 회원 DB를 씁니다(루트 README §4.4).

## 7. 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| 화면이 안 뜨거나 404 | `services/web` 폴더에서 실행했는지 |
| picar가 안 움직임 | `PICAR_URL`을 실물 주소로 줬는지, `/api/state`의 `devices.picar` |
| 상단 장치 상태에 이상 표시 | 해당 장치 서비스가 켜져 있는지, `/api/state`의 `devices` (루트 README §4.3) |
| 카메라 영상이 안 나옴 | vision이 켜져 있는지, `VISION_URL`. 영상 중계는 vision에 닿지 않으면 503을 돌려줍니다 |
| micro:bit `A` 버튼이 안 먹음 | actuation의 micro:bit 연결. 그동안은 `Space` 키 사용 |
| SC-05에 "이 교육장 기기에 저장했습니다" | `.env`의 Supabase 키. `curl http://localhost:8000/api/auth/me`의 `store.backend`가 `supabase`여야 합니다 |
| SC-05에 "인터넷 연결을 기다리는 중" | 인터넷 연결. 연결되면 30초 안에 자동 저장되며, "지금 다시 저장"으로 바로 보낼 수 있습니다 |
| 교육 도중 화면을 새로 열었더니 SC-07 | 정상입니다. 이어하기는 없고 처음부터 다시 시작합니다 |

그 밖의 문제는 루트 README §4.6. 개발 자료(시험 코드·측정 스크립트·설계 문서)는 `dev` 브랜치에 있습니다.
