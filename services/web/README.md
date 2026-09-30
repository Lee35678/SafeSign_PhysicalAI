# web — 프론트엔드 + 교육 상태머신 (담당: 조은수)

RACI: 웹 **R**, 성능측정 **R**

`document/09_화면목록.md`의 SC-01~SC-07 화면 흐름을 상태머신으로 구현하고, vision(`GET /latest`)·
actuation(`POST /command`, `/result`, `/progress` — AI Hand+micro:bit, RPi5) · **picar(`POST /picar`,
별도 서비스, Raspberry Pi 4B 8GB, Wi-Fi)** 를 호출해 화면에 반영합니다. picar는 actuation과 다른
서비스/보드이므로 `PICAR_URL`로 따로 호출하고, 타임아웃(500ms)+1회 재시도 후 실패하면 picar 없이
진행합니다 (03_인터페이스계약서 §5-2·§7 — picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에
보드를 분리했습니다, 02_설계문서 §1-1).

> **2026-09-29 갱신 (이동혁)**: 화면을 **Gemini AI Edition 디자인**(`stitch_safesign_design_system_final/`)으로 새로 만들었다.
> **회원가입·로그인**(회원코드 SS-00001 자동 부여)과 **회원별 학습 결과 저장(Supabase)** 을 추가하고, SC-05의 CSV 내려받기를
> 회원 기록 자동 저장으로 바꿨다. 회의 결정대로 **수신호 예시 사진을 빼고 Camera Module 3 라이브 영상**을 보여 준다.
> 설정은 [supabase/README.md](supabase/README.md).
>
> **2026-09-22 갱신**: SC-01~SC-06 전체 흐름을 `/api/state` 폴링 기반으로 구현했다(SC-07은 프론트엔드가
> 최초 로드 시 상태를 보고 판단). below_tau/out_of_distribution 구분, SC-04(카메라 인식 실패) 자동
> 전환, 시도 횟수·수신호별 집계, 수료증(SC-06) 발급까지 포함. 화면 디자인/레이아웃은 여전히 최소
> 수준이며, 실물 하드웨어 연동 후 다듬을 대상이다 (아래 "아직 확정 안 된 것" 참고).

## 담당 범위

- `backend/state_machine.py` — 교육 상태머신. 백그라운드 스레드(`start_polling`, 앱 startup에서 시작)가
  0.2초 간격으로 vision `GET /latest`를 폴링해 현재 커리큘럼 단계(`CURRICULUM`, PRD §3.2 순서)와
  비교, 정답/오답/below_tau/out_of_distribution을 판정해 actuation `/command`·`/result`·`/progress`와
  picar `/picar`를 호출하고, 정답 시 vision `POST /reset`으로 N프레임 누적을 초기화한다.
  - `GET /api/state` — state/**phase**/target_signal/progress/last_result/live_judgment/attempts/completed/
    last_dispatch/last_demo/last_confirm_source/devices/certificate_issued_at 조회
  - `POST /api/start` — 커리큘럼 처음부터 시작 (SC-01/02 -> SC-03, 세션 이어하기 없음). 첫 수신호 AI Hand 시범을
    보내고 `phase: "demo"`로 시작한다
  - `POST /api/confirm` — 확인 버튼(스페이스바). `phase == "demo"`일 때만 받아 vision `/reset` 뒤 `"judging"`으로.
    판정 중 연타는 `{"status": "ignored"}` (2026-09-28, [판정 타이밍 스펙](../../document/proposals/web_판정_타이밍_스펙.md) §4.1)
  - **micro:bit 버튼 A 확인** (2026-09-29, 스펙 §9): 시범 단계에서만 actuation `GET /button`을 폴링(0.2초, 타임아웃
    `BUTTON_TIMEOUT_S` 0.3초)해 누른 횟수 `seq`가 기준값보다 커지면 `/api/confirm`과 같은 확인을 한다. 기준값은 시범
    `/command`가 끝난 뒤 처음 읽은 값이라 **AI Hand 동작 중·판정 중에 누른 것은 세지 않는다**. 조회 실패는 조용히 넘긴다
    (보조 입력 — 스페이스바를 항상 함께 둔다). 어느 입력으로 확인했는지는 `/api/state`의 `last_confirm_source`
    (`web` | `microbit_button`). 끄려면 `MICROBIT_BUTTON_CONFIRM=0`. micro:bit 없이 시험: actuation `POST /button/simulate`
  - `POST /api/certificate` — 7종 완료 후 수료증 발급 (SC-05 -> SC-06)
  - **판정 타이밍**: `phase == "judging"`일 때만 판정한다. 정답은 즉시, 오답은 같은 클래스가 1초(`WRONG_CONFIRM_S`)
    이어질 때만 확정하고 재시범과 함께 `"demo"`로 돌아간다. `below_tau`·OOD는 화면 안내 문구만(물리 피드백 없음)
  - **시행 로그**: 판정이 확정될 때마다(정답·오답) `logs/web_trials_<기동시각>.csv`에 1행(스펙 §7 열 정의,
    UTF-8 BOM). 대상자 ID는 환경변수 `LOG_SUBJECT`(대상자마다 web 재기동). 폴더는 `TRIAL_LOG_DIR`로 바꿀 수 있다
  - 장치 호출 순서는 `/picar` → `/result` → `/command` → `/progress`(2026-09-28, 스펙 §7.3). 응답은 본문
    `status`까지 본다 — `timeout`·`error`·`partial`은 실패로 기록하고 재시도하지 않는다(03 §5-5)
  - actuation/picar 호출 모두 "실패해도 학습 흐름은 계속"(best-effort) — 예외/4xx/5xx를 모두 실패로
    간주해 재시도 후에도 실패하면 결과를 `last_dispatch`에 남기고 진행한다(2026-09-21
    web_picar_통신_신뢰성_개선안.md 반영 — 이전에는 응답을 확인하지 않아 "조용한 실패"를 감지할 수
    없었다). actuation 타임아웃은 엔드포인트별로 나눈다 — `/command` 1.5초
    (`ACTUATION_COMMAND_TIMEOUT_S`, 손 동작 완료 후 회신이라 실측 0.79~0.83초), `/result`·`/progress`
    0.5초(`ACTUATION_FEEDBACK_TIMEOUT_S`, 실측 26~42ms). 같은 문서 §4 C′안(2026-09-23) — 이전 C안(일괄
    0.6초)은 `/command`가 전부 timeout 나서 철회됐다. micro:bit가 명령을 하나씩 처리하므로 actuation
    호출은 순차로 보낸다.
  - vision/actuation/picar의 `GET /health`를 5초 간격으로 확인해 `devices`로 노출한다.
  - 손 미검출(no_hand/normalize_failed)이 `CAMERA_FAIL_STREAK_THRESHOLD`(25회 ≈ 5초, 환경변수)회 연속되면 SC-04로
    전환하고, 손이 다시 보이면 자동으로 SC-03에 복귀한다.
  - **회원 결과 저장** (2026-09-29): 7종을 마쳐 SC-05로 넘어가는 순간 `backend/members.py`로 회원 기록에 저장한다.
    회원은 `/api/start` 때 로그인해 있던 학습자로 고정한다. 저장 상태는 `/api/state`의 `result_save`, 이 회차의 학습자는 `member`.
    KPI 시행 로그의 `subject` 열에는 회원코드가 들어간다(`LOG_SUBJECT`가 있으면 그 값이 우선).
- `backend/members.py` — 회원가입·로그인·게스트·로그아웃(`/api/auth/*`)과 회원별 결과 저장. 브라우저는 Supabase에 직접
  붙지 않고 백엔드만 `SUPABASE_URL`·`SUPABASE_SERVICE_ROLE_KEY`로 접근한다. 키가 없으면 로컬 모드(`data/`), 인터넷이 끊기면
  결과를 대기열에 쌓았다가 30초마다 다시 보낸다. 자세한 설정·동작은 [supabase/README.md](supabase/README.md)
  - `POST /api/auth/signup` `{email, password, name, org}` → 회원코드 부여 · `POST /api/auth/login` `{email, password}`
  - `POST /api/auth/guest` · `POST /api/auth/logout` · `GET /api/auth/me` · `POST /api/auth/results/retry`(대기열 즉시 재전송)
  - (2026-09-30) `POST /api/auth/find-id` `{name, member_code}` → 가린 이메일 · `POST /api/auth/password/request` `{email}` →
    6자리 인증 코드 메일 · `POST /api/auth/password/reset` `{email, code, new_password}`
  - **보안**: 로그인 실패 5회/10분 잠금, 비밀번호 8자+영문·숫자, 모든 응답에 CSP 등 보안 헤더, `/api/*` `no-store`,
    공용 PC 5분 무입력 자동 로그아웃. 결과에는 수신호별 **합격/불합격**(`passed`)이 함께 저장된다 — [18_DB설계서](../../document/18_DB설계서.md)
- `backend/camera.py` — `GET /api/camera/stream`: vision `GET /stream`(MJPEG)을 그대로 중계한다. 브라우저는 교육장 PC에서
  열리는데 `VISION_URL`은 RPi5 기준 주소라, web을 거쳐야 주소·포트가 맞는다.
- `frontend/` — `index.html`(화면 마크업) + `style.css`(Gemini 테마 구조 그대로, **색만 산업 안전 팔레트** — 2026-09-30) + `app.css`(회원·라이브 영상·손가락 패턴 등
  원본에 없는 요소 + 디자인 방향 절) + `main.js`(폴링·전환) + `fonts/`(SUIT·Inter, OFL — 오프라인용 동봉).
  - 디자인 (2026-09-30): Industrial Intelligence · Mission Control · Technical Editorial → **산업 제어실(HMI, ISA-101) 기준으로 정리** — 무채색 불투명 패널,
    색은 상태·핵심 조작에만, 일치율 계기에 판정 기준 75% 눈금, 안돈식 정답 화면(14 §11). 수료증 = 성명·사원 코드·수료 일시·번호 + 가상 기관 직인.
    회사 사이트(같은 회원 DB)는 `services/portal` — [19_회사웹사이트](../../document/19_회사웹사이트.md). 팔레트 Industrial Black `#111820`(배경) ·
    Safety Orange `#F28C28`(핵심 강조, 주 버튼은 검정 글자) · Steel Gray `#687582`(보조 정보) · Signal White `#F4F6F8`(주요 텍스트) ·
    Safe Green `#22C55E`(정상) · Alert Red `#EF4444`(위험 경고). SC-01 오른쪽은 제품 소개(손 관절 21점 인식 애니메이션),
    판정 중 카메라에는 실시간 판정값 계기판(`live_judgment`: 손 검출 · 인식 수신호 · 신뢰도).
  - 화면 기준 (2026-09-30): 시연 PC **1920×1080 전체 화면**. 노트북 1366×768(전체 화면)·1366×657(창 모드)도 전 화면이
    스크롤·잘림 없이 들어간다 — 세로 820px·700px 이하에서 간격·글자만 줄인다(`app.css` "노트북 화면 맞춤"). 프레임워크 없이 바닐라 JS. 수료증(SC-06)은 `<canvas>`(성명·회원코드 포함).
  - 흐름: SC-01 → **로그인/회원가입**(가입 완료 시 회원코드 안내, 게스트 가능) → SC-02 → SC-03 → … → SC-06 → 다시 학습 / 끝내기(로그아웃)
  - **SC-03 시범/판정 단계**: 두 단계 모두 **라이브 영상**(한 `<img>`가 자리만 옮긴다). 정답 손모양은 사진 대신 **손가락 패턴**
    (엄지~소지 폄/접음)으로 보여 준다 — AI Hand가 구별하지 못하는 G3≈G6·G4≈G7(설계서 §4.7)도 이 패턴으로 구분된다.
    Space는 확인 버튼이 보일 때만 받고(`preventDefault`, `event.repeat` 무시), 오버레이가 떠 있는 동안은 받지 않는다.
    `below_tau`/OOD는 오버레이 대신 판정 화면 안 문구로 보여 준다.
  - **일치율** (2026-09-30): 화면의 일치율 = **분류기가 본 목표 수신호 확률 × 100**(`_target_score`, vision `class_probabilities`).
    판정과 같은 값이라 목표를 제대로 하면 높고(75점 이상이어야 정답) 다른 손동작이면 낮다. 시행 로그에는 `target_score` 열로 남는다
  - **SC-05**: 결과는 자동으로 회원 기록에 저장되고 화면에 상태가 나온다(저장됨 · 연결 대기 · 로컬 모드 · 게스트 · 실패).
    예전 "결과 저장 (CSV)" 내려받기(⑨)는 이것으로 대신한다.

## 화면 ↔ 상태 매핑 (09_화면목록.md 참고, 2026-09-18 갱신)

| 화면ID | 상태머신 state | 비고 |
| --- | --- | --- |
| SC-01 | `landing` | |
| SC-02 | `curriculum_confirm` | 수신호 7종 안내 (구 SC-02 분야선택은 폐지) |
| SC-03 (+03a/03b) | `training` (하위 상태: 정답/오답) | 핵심 화면, vision `GET /latest` 폴링 |
| SC-04 | `camera_fail` | 손 미검출 지속 시 |
| SC-05 | `summary` | |
| SC-06 | `certificate` | |
| SC-07 | `reentry` | 세션 이어하기 미구현 — 항상 처음부터 재시작 |

관리자 화면(구 SC-08 신규 수신호 등록)은 없습니다 — 경량 분류기(SVM) 채택으로 해당 기능 자체가
범위에서 제외되었습니다 (03_인터페이스계약서 §6).

## 아직 확정 안 된 것

- [x] ~~SC-03 화면 분할 단위 (시범/인식 동시 표시 여부)~~ → 2026-09-27 결정: 한 화면 안에서 **시범 단계 →
  판정 단계** (예시 사진 + 확인 버튼(스페이스바), 오답 1초 유지). `document/09_화면목록.md`,
  `document/proposals/web_판정_타이밍_스펙.md` — 구현은 web 할 일 ①(`document/14_web_구현보고서.md` §8)
- [x] ~~vision `/latest` 폴링 주기~~ → 0.2초로 우선 구현(`VISION_POLL_INTERVAL_S`), 실측 후 조정
- [x] ~~프론트엔드(`main.js`)가 `/api/state`를 폴링해 SC-01~SC-07 화면을 실제로 전환하도록 연결~~ →
  2026-09-22 구현
- [x] ~~`picar_command`의 `motor.speed` 값~~ → 2026-09-23 바닥 주행 테스트로 확정: 서행 20,
  좌/우회전·후진 40, 정지/확인_완료/주의 0 (13_picar_하드웨어_검증리포트.md §4.5). picar 서비스가
  50 초과를 잘라내지만(`speed_capped_from`) 안전망일 뿐
- [x] ~~SC-04(camera_fail) 진입 조건~~ → `CAMERA_FAIL_STREAK_THRESHOLD` 25회(약 5초, 2026-09-29 조은수 결정 — 웹 A 이동혁 확인 대기; 이전 15회·3초 잠정치).
  9/25 실물 데모에서 판정 시작 → 정답까지 1.2~8.0초라 3초는 짧았다. 필요하면 환경변수로 조정
- [x] ~~SC-05·06 "성공률"(100/시도 횟수)~~ → **"첫 시도 정답"(O/X, 전체 k/7)**으로 교체(2026-09-29 조은수 결정 — 웹 A 이동혁 확인 대기) — KPI 정답률과 혼동 방지
- [ ] 커리큘럼 순서(`CURRICULUM`)가 PRD §3.2 표 순서 그대로인데, 실제 교육 설계상 순서인지 확인 필요
- [ ] SC-03b "권장 재도전 횟수" 산식 — 어느 문서에도 정의돼 있지 않아 `_recommended_retry_count`에
  match_score 구간별 잠정치(1~3회)로 구현. 실측/교육 설계 확정 필요
- [x] ~~SC-03 카메라 실시간 영상 미리보기~~ → 2026-09-29 MJPEG로 구현(vision `GET /stream` → web `/api/camera/stream`).
  예시 사진은 회의 결정으로 뺐다. RPi5 실물에서 영상을 켠 채 `result_fps`가 떨어지지 않는지 확인 필요
- [x] ~~`확인_완료` AI Hand 자세 gap (문서는 "주먹", actuation 코드는 "엄지만 펴기")~~ → 2026-09-25 해소:
  actuation `gesture5`를 주먹으로 수정·재플래시(`d3a209e`). 화면 설명과 실물 AI Hand 동작이 일치한다
- [x] ~~`확인_완료` picar LED 설명~~ → "번갈아 2회 점멸 후 소등"에서 **"정지 + 적색·황색 LED 전부 동시 점멸"**로
  정정(2026-09-27 확정). LED는 2초 뒤 picar가 스스로 끈다(2026-09-28)
- [ ] SC-06 수료증 — 현재 `<canvas>` 기반 PNG/인쇄만 제공. 정식 이미지/PDF 템플릿 디자인은 별도 확정 필요

## 로컬 실행

```bash
docker compose up --build web
# http://localhost:8000
```

## 테스트

vision/actuation/picar 실물·mock 서버 없이 httpx 호출만 patch해 검증한다.

- `tests/test_state_machine.py` — 정답/오답/below_tau/out_of_distribution 분기, SC-04 임계값·자동 복귀,
  4xx/5xx 실패 감지, SC-06 발급 조건
- `tests/test_judging_timing_spec.py` — 판정 타이밍 스펙 인수 테스트(①-a·②-a·③)
- `tests/test_microbit_button_confirm.py` — micro:bit 버튼 A 확인(스펙 §9)
- `tests/test_members.py` — 가짜 Supabase(httpx.MockTransport)로 가입·로그인·회원코드·결과 저장·오프라인 대기열·재전송,
  로컬 모드, 시작한 회원에게 저장되는지
- `tests/test_camera_proxy.py` — 영상 중계·vision 다운 시 503
- `tests/test_aggregate_kpi.py` — KPI 집계 스크립트(아래)

테스트 동안 회원 파일·시행 로그는 임시 폴더를 쓰고 Supabase 키는 지운다(`tests/conftest.py`).

```bash
cd services/web && python -m pytest tests -q
```

> ⚠️ **반드시 pytest로 실행한다.** `tests/conftest.py`가 테스트 동안 시행 로그를 임시 폴더로 돌린다.
> `python tests/test_state_machine.py`처럼 직접 실행하면 이 설정을 거치지 않아 실제 `logs/`에 가짜 판정 행이 쓰인다
> (그래서 직접 실행하면 안내만 하고 끝나게 해 두었다).

## KPI 집계 (06 2부)

`scripts/aggregate_kpi.py` — 시행 로그 CSV를 `06_테스트·평가리포트` §2 표(요약·혼동행렬·지연 분포·대상자별)로
집계한다(16 §5.7 규칙, §5.8 명세). `mocked=true` 행은 빼고 제외 건수를 출력한다. 미결 KPI 정의는
[회의안건_KPI측정방법](../../document/proposals/회의안건_KPI측정방법.md)의 잠정치가 기본값이다. web `timeout`(판정 제한시간
초과)은 기본적으로 분모에서 빼고 건수만 적으며, `--timeout-as-reject`면 미판정으로 센다(16 §6.4 결정 대기).

```bash
cd services/web
python scripts/aggregate_kpi.py logs/web_trials_*.csv --out kpi_out   # kpi_out/kpi_report.md
# web 없는 데모 CSV를 같이 주면 따로 집계해 비교한다(합치지 않음)
python scripts/aggregate_kpi.py logs/web_trials_*.csv ../actuation/aihand_vision_picar_*.csv
```

PNG(혼동행렬·지연 히스토그램)는 matplotlib이 설치돼 있을 때만 만든다 — web 의존성에는 넣지 않았다.
