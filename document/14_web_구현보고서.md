# web 구현 보고서 (v1 — 초안)

**팀명**: 심기일전 · **담당**: 조은수 (웹 R · 성능측정 R)
**최초 작성**: 2026-09-27 (초안 정리: 송승호 — 조은수 검토·보완 필요) · **대상**: `services/web`

> **이 문서의 범위**: web(교육 상태머신 + 화면)이 **무엇을 어떻게 구현했고, 왜 그렇게 정했는가**를
> 기록한다. 수신호 분류 정확도·혼동행렬은 `06_테스트·평가리포트`, 장치 쪽 실측은
> `11_하드웨어설계서`·`13_picar_하드웨어_검증리포트`, 화면 설계 원안은 `09_화면목록`가 다룬다.
>
> 📝 **표기**: 이 문서 안의 `§n`은 이 문서의 절이다. 다른 문서는 **"설계서 §n"**(= `11_하드웨어설계서`)처럼
> 문서명을 앞에 적는다. 기준 코드는 `feature/picar` `43fc3cb`(web 최종 변경 `6f82886`, 2026-09-25)이다.
>
> ✏️ **초안 상태**: 코드·커밋·개발로그에서 확인되는 사실만 정리했다. `【확인 필요】` 표시는 담당자가
> 채우거나 정정할 곳이다.

---

## 1. 역할과 구성 (as-built)

web은 학습 흐름 전체를 지휘하는 **오케스트레이터**다. vision의 판정 결과를 받아 현재 커리큘럼 단계와
비교하고, 정답/오답에 따라 물리 장치(AI Hand·micro:bit·picar)를 호출하며, 학습자에게 화면을 보여준다.

| 항목 | 값 |
| --- | --- |
| 실행 위치 | **RPi5** (vision·actuation과 같은 보드), 포트 **8000**, `0.0.0.0` 바인딩 |
| 접속 | 시연 PC 브라우저 → RPi5와 **UTP 직결**(설계서 §6.2) → `http://<RPi5 eth0 주소>:8000` |
| 백엔드 | Python · FastAPI · `httpx` (`backend/app.py`, `backend/state_machine.py`) |
| 프론트엔드 | 바닐라 JS (프레임워크 없음) — `frontend/index.html`·`main.js`·`style.css` |
| 상태 저장 | 프로세스 메모리 딕셔너리 `_session` 1개 (DB·세션 ID 없음 — §5 D1) |
| 호출 대상 | vision `:8001`(RPi5) · actuation `:8002`(RPi5) · picar `:8000`(**RPi4B**, Wi-Fi `192.168.50.10`) |

```
 [PC 브라우저] ──UTP── [RPi5]  web ──▶ vision   GET /latest (0.2초 폴링), POST /reset
                              │  └──▶ actuation POST /command · /result · /progress ──BLE──▶ AI Hand + micro:bit
                              └──── Wi-Fi(AP) ──▶ [RPi4B] picar POST /picar ──▶ 모터 + LED
```

---

## 2. 화면 흐름 (SC-01~SC-07)

`09_화면목록`의 화면 표를 그대로 구현했다. 같은 레이아웃에서 상태만 바뀌는 정답/오답은 별도 화면이
아니라 **SC-03 위의 오버레이**다.

| 화면 | 상태머신 `state` | 구현 내용 |
| --- | --- | --- |
| SC-01 시작 | `landing` | 시작 버튼 |
| SC-02 교육 시작 확인 | (프론트엔드 전용) | 수신호 7종 목록(AI Hand 자세·picar 동작) 미리보기 → "교육 시작" → `POST /api/start` |
| SC-03 시범/인식 | `training` | 현재 수신호 이름·설명, 진행(n/7), 시도 횟수, 실시간 일치율 바 |
| ㄴ SC-03a 정답 | `training` + `last_result.outcome=correct` | "정답!" + 일치율, 2초 후 자동으로 다음 수신호 |
| ㄴ SC-03b 오답 | `training` + `wrong`/`below_tau`/`out_of_distribution` | 사유별 문구, 일치율, 권장 재도전 횟수, 현재 시도 횟수 |
| SC-04 카메라 인식 실패 | `camera_fail` | 손 미검출 15회 연속(약 3초) 시 진입, **손이 다시 보이면 SC-03 자동 복귀** |
| SC-05 학습 완료 | `summary` | 수신호별 시도 횟수·최종 일치율 표 |
| SC-06 수료증 | `certificate` | `<canvas>` 렌더링 → PNG 저장 / 인쇄(PDF 저장). 7종 모두 완료해야 발급 |
| SC-07 재접속 | (프론트엔드 판단) | 새로고침 시 `state ≠ landing`이면 "처음부터 다시" 안내 (이어하기 없음 — §5 D1) |

- 프론트엔드는 `/api/state`를 **0.4초** 간격으로 폴링해 화면을 전환한다.
- 화면 상단에 vision·actuation·picar 장치 상태(BLE 끊김, I2C 무응답 등)를 표시한다.
- 카메라 실시간 미리보기는 vision에 프레임 스트리밍 엔드포인트가 없어 **자리표시자**만 있다(§8).

---

## 3. 상태머신 동작

### 3.1 판정 루프

백그라운드 스레드 2개가 앱 시작과 함께 뜬다.

| 스레드 | 주기 | 하는 일 |
| --- | --- | --- |
| `_poll_loop` | 0.2초 (`VISION_POLL_INTERVAL_S`) | vision `GET /latest` → 분기 → 장치 호출 |
| `_device_health_loop` | 5초 (`DEVICE_HEALTH_INTERVAL_S`) | 3개 장치 `GET /health` → `devices`로 노출 |

### 3.2 판정 결과 분기 (`judgment_result.reason` 기준)

| vision 응답 | web 처리 |
| --- | --- |
| `is_reject=false`, `predicted_class == target_signal` | **SC-03a 정답** → 물리 피드백 + picar + 다음 수신호 + vision `/reset` |
| `is_reject=false`, `predicted_class ≠ target_signal` | **SC-03b 오답** → AI Hand 재시범 + micro:bit 결과 표시 |
| `below_tau` | SC-03b "조금 더 정확히 해주세요" |
| `out_of_distribution` | SC-03b "다른 수신호를 하고 계세요" |
| `no_hand` / `normalize_failed` | 미검출 카운트 +1 → 15회 연속이면 SC-04 |
| `awaiting_consecutive_frames` / `model_not_loaded` / `inference_error` | 과도기 상태 — 화면 변화 없이 대기 |
| `predicted_class == negative` | 무시 |

- **중복 방지**: 같은 (커리큘럼 단계, 결과, 예측 클래스) 조합은 한 번만 처리한다(`_last_dispatched`).
  학습자가 같은 자세를 들고 있어도 매 폴링마다 장치가 반복 동작하거나 시도 횟수가 늘지 않는다.
- **집계**: 수신호별 시도 횟수(`attempts`)와 완료 목록(`completed`: 수신호·시도 횟수·최종 일치율)을 쌓아
  SC-05·SC-06에 쓴다.

### 3.3 장치 호출 순서 (`_dispatch_feedback`)

```
actuation POST /command   (정답: correct_pose / 오답: demo)      timeout 1.5초 × 최대 2회
actuation POST /result    (is_correct, match_score)              timeout 0.5초 × 최대 2회
actuation POST /progress  (current, total)                       timeout 0.5초 × 최대 2회
picar     POST /picar     (정답일 때만, 수신호별 모터·LED 명령)    timeout 0.5초 × 최대 2회
```

- 순차 호출이다. micro:bit가 명령을 하나씩 처리하므로 병렬로 보내도 빨라지지 않고, 순서 보장이 필요하다(§5 D4).
- 최악 대기시간은 약 **6초**(모든 호출이 재시도까지 timeout일 때), 정상 시에는 `/command` 약 0.8초가 대부분이다.

### 3.4 picar 명령표 (`PICAR_COMMANDS`)

| 수신호 | motor | speed | LED (적 / 황좌 / 황우) |
| --- | --- | --- | --- |
| 정지 | stop | 0 | on / off / off |
| 서행 | forward | **20** | off / blink / blink |
| 좌회전_유도 | left | **40** | off / blink / off |
| 우회전_유도 | right | **40** | off / off / blink |
| 확인_완료 | stop | 0 | blink / blink / blink |
| 후진 | backward | **40** | off / off / off |
| 주의 | stop | 0 | off / blink / blink |

속도는 2026-09-23 바닥 주행 실측으로 확정했다(`13_picar_…` §4.5). picar 서비스가 50 초과를 잘라내지만
안전망일 뿐이라 web이 처음부터 확정값을 보낸다.

---

## 4. 인터페이스

### 4.1 web이 제공하는 API (`/api` 접두)

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| GET | `/api/state` | 화면 렌더링용 전체 상태 — `state`, `target_signal`, `signal_info`, `curriculum`, `progress`, `last_result`, `live_judgment`, `attempts`, `last_dispatch`, `devices`, `completed`, `certificate_issued_at` |
| POST | `/api/start` | 세션 초기화 후 SC-03 시작 (장치 상태는 유지) |
| POST | `/api/certificate` | 7종 완료 시 수료증 발급 시각·집계 확정, 미완료면 `not_completed` |
| GET | `/health` | web 자체 상태 |

### 4.2 web이 호출하는 API

| 대상 | 경로 | 스키마 (`shared/schemas/`) | 실패 시 |
| --- | --- | --- | --- |
| vision | `GET /latest` | `judgment_result` | 해당 폴링 건너뜀 |
| vision | `POST /reset` | — | 무시 |
| actuation | `POST /command` | `aihand_command` (`servo_angles`는 스키마 호환용 placeholder — 실제 동작은 `target_signal`로 결정) | 재시도 1회 후 기록하고 진행 |
| actuation | `POST /result`, `/progress` | — | 〃 |
| picar | `POST /picar` | `picar_command` | 〃 |
| 3개 모두 | `GET /health` | — | `unreachable`로 표시 |

---

## 5. 설계 결정과 근거

| # | 결정 | 근거 | 시점 |
| --- | --- | --- | --- |
| D1 | 세션을 **메모리 딕셔너리 1개**로 관리, 이어하기 없음 | 1대1 교육 스테이션이라 동시 세션이 범위 밖. 재접속 시 항상 처음부터(팀 결정) → DB·Redis 불필요 | 2026-09-18 |
| D2 | 장치 호출은 **best-effort** — 실패해도 학습 흐름은 계속 | `03_인터페이스계약서` §7. 장치 하나의 고장이 교육 전체를 멈추지 않게 | 설계 |
| D3 | 4xx/5xx도 실패로 판정하고 결과를 `last_dispatch`로 노출 | 이전에는 응답을 버려 서버 오류를 성공으로 셌다("조용한 실패") — `archive/web_picar_통신_신뢰성_개선안` 변경 1·2 | 2026-09-22 |
| D4 | 장치 호출 **순차 유지**, 타임아웃 **엔드포인트별 분리**(C′안) | `/command`는 손 동작 완료 후 회신(실측 0.79~0.83초) → 1.5초, `/result`·`/progress`(실측 26~42ms) → 0.5초. 앞서 채택한 C안(일괄 0.6초)은 `/command`가 전부 timeout 나서 철회 | 2026-09-22 C안 → 09-25 C′안 |
| D5 | SC-04 진입 = 손 미검출 **15회 연속**(0.2초 × 15 ≈ 3초) | `09_화면목록`가 "임계값 필요"라고만 정의 → 잠정치 | 2026-09-22 |
| D6 | 정답 시 vision `POST /reset` 호출 | 호출이 빠져 있어 이전 수신호의 N프레임 누적이 이월될 수 있었음 | 2026-09-22 |
| D7 | `below_tau`와 `out_of_distribution` 문구 구분 | "자세를 다듬으라"와 "다른 수신호를 하고 있다"는 학습자에게 다른 행동을 요구 | 2026-09-22 |
| D8 | picar 속도 20/40/40/40 | 바닥 주행 실측, 60은 너무 빨라 기각(`13_picar_…` §4.5) | 2026-09-25 반영 |
| D9 | **판정 타이밍 재설계**: 시범 + 예시 사진 → 확인 버튼(스페이스바) → 판정, 오답 1초 유지 | 9/25 실물에서 학습자가 AI Hand를 보기 전에 오답 처리됨(§6.2). 고정 보는 시간(3초)은 학습자마다 달라 버튼으로 대체 — `proposals/web_판정_타이밍_스펙` | 2026-09-27 스펙 확정, **구현 예정** |

---

## 6. 검증 결과

### 6.1 단위 테스트 — `tests/test_state_machine.py`

vision·actuation·picar 서버 없이 `httpx` 호출만 patch해서 검증한다.
**2026-09-27 실행: 9개 전부 통과** (`python -m pytest tests -q`, 0.98초).

| 테스트 | 확인 내용 |
| --- | --- |
| `test_post_with_retry_ok_on_2xx` | 2xx → 성공 |
| `test_post_with_retry_fails_on_5xx_not_silently_ok` | 5xx를 성공으로 세지 않음 (D3) |
| `test_post_with_retry_fails_on_connection_error` | 연결 실패 → 실패 기록 |
| `test_poll_once_correct_advances_curriculum_and_calls_picar` | 정답 → 다음 수신호 + picar 호출 |
| `test_poll_once_wrong_does_not_advance_or_call_picar` | 오답 → 단계 유지, picar 미호출 |
| `test_poll_once_below_tau_vs_out_of_distribution_messages_differ` | 두 사유 문구 구분 (D7) |
| `test_poll_once_silent_reasons_do_not_produce_overlay` | 과도기 사유는 화면 변화 없음 |
| `test_camera_fail_threshold_and_auto_recovery` | 15회 → SC-04, 손 보이면 SC-03 복귀 (D5) |
| `test_certificate_requires_all_signals_completed` | 7종 미완료 시 수료증 거부 |

### 6.2 실물 통합 — 2026-09-25 (RPi5 + RPi4B, PC UTP 직결)

| 단계 | 결과 |
| --- | --- |
| PC 브라우저 → RPi5 web 접속 (UTP) | ✅ SC-01부터 진행, 상단 장치 상태 전부 정상 |
| web → actuation·picar 연동 | ✅ 호출·응답 정상 (타임아웃 1.5/0.5초 반영 후) |
| SC-04 자동 복귀 | ✅ 손을 다시 올리면 SC-03 복귀 |
| **web 전 구간 (SC-01 → SC-05)** | 🔴 **미완** — 판정 타이밍 문제로 진행이 끊김 |

같은 날 web 없이 돌린 전 구간(데모 스크립트)은 **7/7 정답**, 정답 확정 → 장치 반응 시작 25~47ms였다.
즉 장치·판정 경로는 정상이고, 남은 문제는 web의 **흐름 설계**다.

**드러난 문제**
1. 수신호를 시작할 때 AI Hand 시범이 없다. 정답 직후 학습자가 방금 맞힌 손모양을 들고 있어 약 0.12초 만에 새 수신호의 오답이 된다.
2. 오답 시범이 끝나자마자 다시 판정한다. 손을 바꾸는 도중의 자세가 새 오답으로 잡힌다(중복 방지는 직전과 같은 오답만 막는다).
3. 시범·정답 연출을 보는 동안에도 미검출을 세서 SC-04로 쉽게 넘어간다.

→ D9로 재설계. web 반영 후 전 구간 재시험 예정.

---

## 7. 이슈 이력

| 날짜 | 이슈 | 원인 | 조치 | 상태 |
| --- | --- | --- | --- | --- |
| 09-21 | 장치 호출 실패를 감지할 수 없음 | 응답을 버리고 예외만 잡음 | D3 | ✅ |
| 09-21 | 폴링 최악 정지시간 13초 | 2.0초 타임아웃 × 재시도 × 순차 호출 | D4 (C안 → C′안) | ✅ |
| 09-22 | 이전 수신호 판정 누적 이월 가능 | 정답 시 vision `/reset` 누락 | D6 | ✅ |
| 09-25 | C안 적용 후 `/command`가 전부 timeout | `/command`는 손 동작 완료 후 회신(0.8초) > 0.6초 | C′안(1.5초)으로 교체 | ✅ |
| 09-25 | 학습자가 AI Hand를 보기 전에 오답 처리 | §6.2 문제 1·2 | D9 스펙 확정 | 🔴 구현 예정 |
| 09-25 | 손을 잠깐 내리면 SC-04 | §6.2 문제 3 | D9로 완화(시범 단계에서는 카운트 정지) | 🔴 구현 예정 |
| — | HTTP 200이면 무조건 성공 처리 | 응답 본문 `status`(actuation `timeout`, picar `partial`)를 안 봄 | 미정 | 🟡 |
| — | 정지 계열 picar LED가 다음 명령까지 켜진 채 남음 | 끄는 시점 미정의 | 미정 | 🟡 |

---

## 8. 남은 작업 (조은수)

우선순위 순이다. 개발로그 `web` 할 일과 같은 목록이다.

1. 🔴 **판정 타이밍 재설계 구현** (D9) — `proposals/web_판정_타이밍_스펙.md` §4, 완료 기준 §6
2. 🔴 **시행 로그 CSV 자동 기록** — `06_테스트·평가리포트` §1-2 열(정답/예측 클래스, confidence,
   match_score, 판정지연, 물리피드백지연) 기준. KPI 실측(W4)의 원본 데이터
3. **이 보고서 완성** — `【확인 필요】` 항목 보완, D9 구현 후 §3·§6 갱신
4. **실제 화면 캡처본** — SC-01~SC-07(시범 단계·정답/오답 오버레이·수료증 포함), 예시 사진 반영 후. `09_화면목록` v3 또는 이 보고서 부록
5. **교육자용 결과 집계 내보내기** — SC-05 집계(수신호별 시도 횟수·일치율)를 파일로 저장

---

## 9. 미확정 항목

| 항목 | 현재 | 필요한 것 |
| --- | --- | --- |
| 커리큘럼 순서 | PRD §3.2 표 순서 그대로 | 교육 설계상 순서 확인 |
| 권장 재도전 횟수 산식 | match_score ≥70 → 1회, ≥40 → 2회, 그 외 3회 (잠정) | 교육 설계 확정 |
| SC-04 임계값 | 15회(약 3초) 잠정 | D9 반영 후 실측 조정 |
| SC-05·SC-06의 "성공률" | `100 / 시도 횟수`로 계산 | 【확인 필요】 지표 이름과 정의가 맞는지 (KPI 정답률과 혼동 우려) |
| 카메라 실시간 미리보기 | 자리표시자 | vision 스트리밍 방식(MJPEG/WebSocket) 협의 |
| 수료증 디자인 | canvas 기본 레이아웃 | 정식 템플릿 확정 |
| `below_tau`/OOD 처리 | 즉시 SC-03b + 물리 피드백 | D9 스펙 §5 — 1초 유지 또는 화면 안내만 |

> **정리 필요**: `state_machine.py`의 `CURRICULUM_INFO` 주석과 web README의 "`확인_완료` actuation 코드가 아직
> 엄지만 펴기" gap은 **2026-09-25 해소**됐다(actuation `gesture5`를 주먹으로 수정·재플래시, `d3a209e`).
> 코드 주석·README에서 지워야 한다.

---

## 10. 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v1 초안 | 2026-09-27 | 최초 작성 — 코드(`6f82886` 기준)·커밋·개발로그·9/25 통합 결과를 정리. 조은수 검토 전 |
