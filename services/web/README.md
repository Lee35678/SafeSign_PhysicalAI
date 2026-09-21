# web — 프론트엔드 + 교육 상태머신 (담당: 조은수)

RACI: 웹 **R**, 성능측정 **R**

`document/09_화면목록_v2.md`의 SC-01~SC-07 화면 흐름을 상태머신으로 구현하고, vision(`GET /latest`)·
actuation(`POST /command`, `/result`, `/progress` — AI Hand+micro:bit, RPi5) · **picar(`POST /picar`,
별도 서비스, Raspberry Pi 4B 8GB, Wi-Fi)** 를 호출해 화면에 반영합니다. picar는 actuation과 다른
서비스/보드이므로 `PICAR_URL`로 따로 호출하고, 타임아웃(500ms)+1회 재시도 후 실패하면 picar 없이
진행합니다 (03_인터페이스계약서_v2 §5-2·§7 — picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에
보드를 분리했습니다, 02_설계문서_v2 §1-1).

> **현재 우선순위 (10_PRD_v2.md §1 갱신 로그 참고)**: 지금은 인식→판정→Actuation 입력-출력
> 파이프라인이 정상 동작하는지 확인하는 단계입니다. 이 서비스는 그 흐름을 눈으로 확인할 수 있는
> 최소 골격이면 충분하며, 화면 디자인/레이아웃은 파이프라인 검증 이후에 다듬습니다.

## 담당 범위

- `backend/state_machine.py` — 교육 상태머신. 백그라운드 스레드(`start_polling`, 앱 startup에서 시작)가
  0.2초 간격으로 vision `GET /latest`를 폴링해 현재 커리큘럼 단계(`CURRICULUM`, PRD §3.2 순서)와
  비교, 정답/오답을 판정해 actuation `/command`·`/result`·`/progress`와 picar `/picar`를 호출한다.
  - `GET /api/state` — 현재 state/target_signal/progress/last_result 조회
  - `POST /api/start` — 커리큘럼 처음부터 시작 (SC-01/02 -> SC-03, 세션 이어하기 없음)
  - 같은 (커리큘럼 단계, predicted_class) 조합에는 물리 피드백을 한 번만 보낸다(`_last_dispatched`) —
    학습자가 같은 자세를 계속 취하고 있어도 매 폴링마다 AI Hand/picar가 반복 동작하지 않도록 함
  - actuation/picar 호출 모두 "실패해도 학습 흐름은 계속"(best-effort) — 예외를 삼키고 1회 재시도 후 진행
- `frontend/` — 정적 HTML/CSS/JS (SC-01~SC-07 화면). 프레임워크 도입은 팀 논의 후 결정.
  아직 `/api/state`·`/api/start`를 호출하지 않는 정적 스텁 상태(파이프라인 검증이 우선이라 후순위)

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
- [ ] 프론트엔드(`main.js`)가 `/api/state`를 폴링해 SC-01~SC-07 화면을 실제로 전환하도록 연결
- [ ] `picar_command`의 `motor.speed` 값(현재 `state_machine.py`의 `PICAR_COMMANDS`에 잠정치로만
  있음) 실측 후 확정
- [ ] SC-04(camera_fail) 진입 조건 — 현재는 `is_reject`/`negative`를 그냥 무시만 하고 별도 상태
  전환은 구현하지 않음 (연속 미검출 횟수 등 임계값 필요)
- [ ] 커리큘럼 순서(`CURRICULUM`)가 PRD §3.2 표 순서 그대로인데, 실제 교육 설계상 순서인지 확인 필요

## 로컬 실행

```bash
docker compose up --build web
# http://localhost:8000
```
