# web — 프론트엔드 + 교육 상태머신 (담당: 조은수)

RACI: 웹 **R**, 성능측정 **R**

`document/09_화면목록_v2.md`의 SC-01~SC-07 화면 흐름을 상태머신으로 구현하고, vision(`GET /latest`)·
actuation(`POST /command`, `/result`, `/progress` — AI Hand+micro:bit, RPi5) · **picar(`POST /picar`,
별도 서비스, Raspberry Pi 4B 8GB, Wi-Fi)** 를 호출해 화면에 반영합니다. picar는 actuation과 다른
서비스/보드이므로 `PICAR_URL`로 따로 호출하고, 타임아웃(500ms)+1회 재시도 후 실패하면 picar 없이
진행합니다 (03_인터페이스계약서_v2 §5-2·§7 — picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에
보드를 분리했습니다, 02_설계문서_v2 §1-1).

> **2026-09-22 갱신**: SC-01~SC-06 전체 흐름을 `/api/state` 폴링 기반으로 구현했다(SC-07은 프론트엔드가
> 최초 로드 시 상태를 보고 판단). below_tau/out_of_distribution 구분, SC-04(카메라 인식 실패) 자동
> 전환, 시도 횟수·수신호별 집계, 수료증(SC-06) 발급까지 포함. 화면 디자인/레이아웃은 여전히 최소
> 수준이며, 실물 하드웨어 연동 후 다듬을 대상이다 (아래 "아직 확정 안 된 것" 참고).

## 담당 범위

- `backend/state_machine.py` — 교육 상태머신. 백그라운드 스레드(`start_polling`, 앱 startup에서 시작)가
  0.2초 간격으로 vision `GET /latest`를 폴링해 현재 커리큘럼 단계(`CURRICULUM`, PRD §3.2 순서)와
  비교, 정답/오답/below_tau/out_of_distribution을 판정해 actuation `/command`·`/result`·`/progress`와
  picar `/picar`를 호출하고, 정답 시 vision `POST /reset`으로 N프레임 누적을 초기화한다.
  - `GET /api/state` — state/target_signal/progress/last_result/live_judgment/attempts/completed/
    last_dispatch/devices/certificate_issued_at 조회
  - `POST /api/start` — 커리큘럼 처음부터 시작 (SC-01/02 -> SC-03, 세션 이어하기 없음)
  - `POST /api/certificate` — 7종 완료 후 수료증 발급 (SC-05 -> SC-06)
  - 같은 (커리큘럼 단계, outcome, predicted_class/reason) 조합에는 물리 피드백·시도횟수 집계를 한 번만
    반영한다(`_last_dispatched`) — 학습자가 같은 자세를 계속 취하고 있어도 매 폴링마다 반복 동작하지 않도록 함
  - actuation/picar 호출 모두 "실패해도 학습 흐름은 계속"(best-effort) — 예외/4xx/5xx를 모두 실패로
    간주해 재시도 후에도 실패하면 결과를 `last_dispatch`에 남기고 진행한다(2026-09-21
    web_picar_통신_신뢰성_개선안.md 반영 — 이전에는 응답을 확인하지 않아 "조용한 실패"를 감지할 수
    없었다). `ACTUATION_TIMEOUT_S` 기본값도 2.0 -> 0.6초로 낮춰 순차 블로킹 최악 시간을 줄였다(같은
    문서 §4 C안, 조은수 결정).
  - vision/actuation/picar의 `GET /health`를 5초 간격으로 확인해 `devices`로 노출한다.
  - 손 미검출(no_hand/normalize_failed)이 `CAMERA_FAIL_STREAK_THRESHOLD`(잠정 15회)회 연속되면 SC-04로
    전환하고, 손이 다시 보이면 자동으로 SC-03에 복귀한다.
- `frontend/` — SC-01~SC-07 화면 전체를 `index.html`의 `.screen` 섹션 + `main.js`의 폴링/전환 로직으로
  구현. 프레임워크 없이 바닐라 JS 유지(팀 논의 전까지). 수료증(SC-06)은 `<canvas>`로 그려 PNG 다운로드/
  인쇄(PDF 저장)를 제공한다. 카메라 실시간 영상 미리보기는 vision에 프레임 스트리밍 엔드포인트가 없어
  자리표시자만 표시한다(§ "아직 확정 안 된 것" 참고).

## 화면 ↔ 상태 매핑 (09_화면목록_v2.md 참고, 2026-09-18 갱신)

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
범위에서 제외되었습니다 (03_인터페이스계약서_v2 §6).

## 아직 확정 안 된 것

- [ ] SC-03 화면 분할 단위 (시범/인식 동시 표시 여부) — vision 담당과 협의
- [x] ~~vision `/latest` 폴링 주기~~ → 0.2초로 우선 구현(`VISION_POLL_INTERVAL_S`), 실측 후 조정
- [x] ~~프론트엔드(`main.js`)가 `/api/state`를 폴링해 SC-01~SC-07 화면을 실제로 전환하도록 연결~~ →
  2026-09-22 구현
- [ ] `picar_command`의 `motor.speed` 값(현재 `state_machine.py`의 `PICAR_COMMANDS`에 잠정치로만
  있음) 실측 후 확정
- [x] ~~SC-04(camera_fail) 진입 조건~~ → `CAMERA_FAIL_STREAK_THRESHOLD`(연속 15회, ~3초) 잠정치로
  2026-09-22 구현. 실측 후 조정 필요
- [ ] 커리큘럼 순서(`CURRICULUM`)가 PRD §3.2 표 순서 그대로인데, 실제 교육 설계상 순서인지 확인 필요
- [ ] SC-03b "권장 재도전 횟수" 산식 — 어느 문서에도 정의돼 있지 않아 `_recommended_retry_count`에
  match_score 구간별 잠정치(1~3회)로 구현. 실측/교육 설계 확정 필요
- [ ] SC-03 카메라 실시간 영상 미리보기 — vision이 프레임 스트리밍 엔드포인트를 제공하지 않아 현재는
  자리표시자만 표시. vision 담당과 스트리밍 방식(MJPEG/WebSocket 등) 협의 필요
- [ ] `확인_완료` AI Hand 자세 — 10_PRD_v2/03_인터페이스계약서_v2는 "주먹"으로 확정(2026-09-20)했지만
  실제 actuation 코드(controller.py/firmware)는 아직 "엄지만 펴기"로 남아 있는 known gap. 웹 화면은
  확정된 스펙("주먹")을 표시하므로, actuation 코드가 갱신되기 전까지는 화면 설명과 실물 AI Hand
  동작이 다를 수 있음 — actuation 담당 확인 필요
- [ ] SC-06 수료증 — 현재 `<canvas>` 기반 PNG/인쇄만 제공. 정식 이미지/PDF 템플릿 디자인은 별도 확정 필요

## 로컬 실행

```bash
docker compose up --build web
# http://localhost:8000
```

## 테스트

`tests/test_state_machine.py` — vision/actuation/picar 실물·mock 서버 없이 httpx 호출만 patch해
정답/오답/below_tau/out_of_distribution 분기, SC-04 임계값·자동 복귀, 4xx/5xx 실패 감지, SC-06 발급
조건을 검증한다 (services/vision/tests와 동일한 스타일 — pytest 없이도 단독 실행 가능).

```bash
cd services/web && python -m pytest tests -q
# (pytest가 없으면) python tests/test_state_machine.py
```
