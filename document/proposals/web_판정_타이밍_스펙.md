# web 판정 타이밍 스펙 — 시범 + 예시 사진 + 확인 버튼

**작성일**: 2026-09-27 · **작성자**: 송승호 · **구현 담당**: 이동혁(백엔드 §4.1) · 조은수(프론트엔드 §4.2) · 김지훈(예시 사진 §4.3) · 송승호(단위 테스트 §6) — 2026-09-28 분담
**관련**: `11_하드웨어설계서` §10 #22, `08_리스크레지스터`(web 판정 타이밍), `06_테스트·평가리포트` §1-3
**구현 현황 (2026-09-28)**: 백엔드 §4.1·§5·§7 **구현·`dev` 병합**(`c8f1fd3` 이동혁 → `1da641b`), §8 인수 테스트 전부 통과.
남은 것: 프론트엔드 §4.2(조은수)·예시 사진 반영 §4.3, §6 실물 재시험.
**2026-09-29**: §9 micro:bit 버튼 A web 연동 구현(송승호) — 단위 테스트 14개, actuation mock 서버 연동 확인.
**2026-09-29**: §4.2 프론트엔드 구현(송승호, 조은수 대행) · §4.3 사진 7장 반영(김지훈) — headless Chrome E2E 31/31(1280×900·1366×768). **남은 것: §6 실물 재시험.**

---

## 1. 배경 — 2026-09-25 web 전 구간 시험에서 드러난 문제

web은 **판정이 나온 뒤에만** AI Hand를 움직이고, 움직인 직후 곧바로 다시 판정한다.

1. **수신호 시작 시 시범이 없다.** 정답 직후 vision `/reset`을 해도 학습자는 방금 맞힌 손모양을 들고
   있어, 새 수신호의 오답으로 곧바로 잡힌다.
2. **오답 뒤 시범이 끝나자마자 다시 판정한다.** 손을 바꾸는 도중의 과도 자세가 다른 클래스로 읽혀
   새 오답이 된다(따라 할 틈 없이 실패·재시범 반복).
3. 시범을 보는 동안에도 손 미검출을 세서 약 3초 만에 SC-04로 넘어간다.

처음 스펙은 "시범 후 **보는 시간**(3초) 동안 판정 무시"였으나, 보는 데 걸리는 시간은 학습자마다 달라
고정값으로 정하기 어렵다. → **학습자가 확인 버튼으로 직접 판정을 시작**하는 방식으로 확정했다.

## 2. 확정 사항 (2026-09-27)

| # | 내용 |
| --- | --- |
| 1 | AI Hand가 시범을 보이는 **동시에** web 화면에 해당 수신호의 **예시 사진**을 보여준다 |
| 2 | 오답 시 예시 사진을 다시 보여주고, **확인 버튼**을 눌러야 판정(검정)에 들어간다 |
| 3 | 확인 버튼은 **스페이스바** 단축키로도 누를 수 있다 |
| 4 | 오답은 같은 오답 클래스가 **1초**(`WRONG_CONFIRM_S = 1.0`) 이상 유지될 때만 확정한다 |

> 1번의 "수신호 시작 시"에도 2번과 같이 **확인 버튼을 눌러야 판정이 시작**된다(시범 → 사진 → 버튼 → 판정).
> 수신호 시작과 오답 후의 흐름을 하나로 맞춘 것이다.

**없어지는 값**: 보는 시간 `OBSERVE_S`(3초). 버튼이 대신하므로 web에는 넣지 않는다.
**남는 값**: `WRONG_CONFIRM_S`. 버튼을 누른 뒤 **손을 올리는 동작**의 과도 자세는 버튼으로 막을 수 없기 때문이다.

## 3. 흐름

```
수신호 시작 ─▶ AI Hand 시범(/command)  +  화면: 예시 사진 + [확인 (Space)]   ← 판정 멈춤
                                            │
                                  확인 버튼 / 스페이스바
                                            │
                                   vision POST /reset
                                            ▼
                                        판정 중
            ┌───────────────────────────────┼───────────────────────────┐
         정답(즉시)                 같은 오답 1초 유지                   손 미검출 15회
            │                               │                              │
   정답 피드백(AI Hand·picar·micro:bit)  오답 피드백 + 재시범             SC-04
            │                     + 예시 사진 + [확인]  ← 판정 멈춤     (손이 보이면 판정 중으로 복귀)
   다음 수신호 시작(맨 위로)                  │
   마지막이면 SC-05                     확인 버튼 → /reset → 판정 중
```

## 4. 구현 가이드 (`services/web`)

현재 구조에서 바꿀 곳을 짚은 것이다. 이름·세부 구조는 구현 담당 판단에 맡긴다.

### 4.1 백엔드 — `backend/state_machine.py`

- **SC-03 안에 하위 단계 추가**: `_session["phase"] = "demo" | "judging"`. SC-03 화면은 그대로이므로
  `STATES`에 새 상태를 추가하지 않고 하위 단계로 둔다(09_화면목록 "화면 내 상태" 원칙).
- **`_poll_once`**: `phase != "judging"`이면 판정하지 않고, `camera_fail_streak`도 올리지 않는다.
  지금 `state not in ("training", "camera_fail")`이면 바로 반환하는 곳(`_poll_once` 첫 부분)에 조건을 더하면 된다.
- **시범 전송 분리**: 지금 `/command`는 `_dispatch_feedback` 안에서만(판정 뒤) 보낸다.
  수신호 시작 시 쓸 **`/command`만 보내는 함수**가 필요하다
  (`command: "demo"`, `target_signal` = 현재 수신호). `/result`·`/progress`·picar는 보내지 않는다.
- **시범을 보내는 시점**
  - `POST /api/start` 직후 (첫 수신호)
  - 정답 처리 후 다음 수신호로 넘어갈 때 — 정답 피드백(`correct_pose`)이 끝난 뒤에 보낸다.
    `/command`는 손 동작이 끝난 뒤 회신하므로(실측 0.79~0.83초) 순차로 보내면 순서가 보장된다.
  - 오답 확정 시 — 기존 `_dispatch_feedback`이 이미 `command: "demo"`를 보내므로 추가 전송은 없다.
    전송 뒤 `phase = "demo"`로 바꾸기만 하면 된다.
  - 어느 경우든 `/command`는 최대 1.5초 × 2회 블로킹이다. API 핸들러에서 보낼 때는 응답을 늦추지 않도록
    백그라운드 스레드로 보내는 것을 권한다.
- **확인 API 추가**: `POST /api/confirm`(이름 자유)
  1. `phase == "demo"`일 때만 받는다(판정 중 중복 입력은 무시).
  2. vision `POST /reset` → 이전 프레임 누적 삭제
  3. `phase = "judging"`, `_last_dispatched = None`, 오답 추적값 초기화
- **오답 1초 유지**: `_session`에 `wrong_cls`, `wrong_since`를 두고, 오답 클래스가 처음 보이면 시각을
  기록하고, **같은 클래스가 1초 이상 이어질 때** 오답을 확정한다. 다른 클래스로 바뀌면 다시 센다.
  손 미검출(`no_hand`/`normalize_failed`)이 나오면 초기화한다(손을 내렸다 다시 들면 새로 센다).
  정답은 지금처럼 즉시 확정한다.
  - 기준 구현: `services/actuation/scripts/aihand_vision_picar_demo.py`의 `_listen()` — 같은 규칙이 이미
    들어가 있고 2026-09-25 실물에서 7/7 통과했다.
- **`GET /api/state`**에 `phase`를 추가해 프론트엔드가 버튼 표시 여부를 판단하게 한다.

### 4.2 프론트엔드 — `frontend/`

- **예시 사진 영역**: SC-03에 수신호 7종별 사진을 표시한다. `phase == "demo"`일 때 크게 보여주고,
  판정 중에는 작게 두거나 숨긴다(레이아웃은 구현 담당 판단).
- **확인 버튼**: `phase == "demo"`일 때만 보인다. 안내 문구 예: "AI Hand와 사진을 보고, 준비되면 확인을 누르세요 (Space)".
- **스페이스바**: `keydown`에서 `event.code === "Space"`이고 확인 버튼이 보일 때만 동작시키고,
  `event.preventDefault()`로 페이지 스크롤을 막는다. 키를 누르고 있을 때 반복 입력(`event.repeat`)은 무시한다.
- **오답 오버레이(SC-03b)**: 기존 문구·일치율·시도 횟수 표시는 유지하고, 오버레이가 사라진 뒤 예시
  사진 + 확인 버튼 화면으로 이어진다.

### 4.3 예시 사진 (준비 필요)

- 저장소에 아직 수신호 예시 이미지가 없다. **7종 × 1장**이 필요하다
  (정지·서행·좌회전_유도·우회전_유도·확인_완료·후진·주의).
- **보관 위치·파일명 (2026-09-28 확정)**: `services/web/frontend/images/<command>.jpg` — 정적 파일로 바로 서빙된다.
  URL에서 한글 인코딩 문제가 없도록 **picar 명령명(영문)** 을 쓴다(`state_machine.py` `PICAR_COMMANDS`의 `command`와 같다).

  | 수신호 | 파일 |
  | --- | --- |
  | 정지 | `stop.jpg` |
  | 서행 | `slow.jpg` |
  | 좌회전_유도 | `turn_left.jpg` |
  | 우회전_유도 | `turn_right.jpg` |
  | 확인_완료 | `complete.jpg` |
  | 후진 | `reverse.jpg` |
  | 주의 | `caution.jpg` |

- 규격: 같은 배경·조명, 짧은 변 약 800px, 장당 200KB 이하.
- 사진은 **사람 손 기준 정답 자세**여야 한다. AI Hand는 엄지 서보 고장으로 `G3`≈`G6`, `G4`≈`G7`이
  구별되지 않는데(설계서 §4.7), 사진이 이 차이를 보완한다 — 개발로그의 협의 항목
  "겹치는 4종을 web 화면으로 구분시키는 방안"도 이것으로 해결된다.
- 촬영·제공: **김지훈**(2026-09-28 배정, web 할 일 ⑩). 프론트엔드(①-b, 조은수)는 사진이 오기 전엔 자리만 만들어 둔다.

## 5. 확인할 점 (구현 담당 판단 요청)

> **결정 (2026-09-28, 이동혁)**: `below_tau`/OOD는 **화면 안내 문구만** 띄운다 — 물리 피드백·시도 횟수·시행 로그 CSV 없음,
> 판정 단계 유지. 손을 올리는 도중에도 자주 나오는 값이라 매번 재시범하면 따라 할 틈이 없고, 9/25 실물 7/7이었던 데모
> 스크립트도 이렇게 했다. 시도 횟수는 아래 둘째 항목대로 구현했다. 아래는 결정 전 원문.

- **`below_tau`/`out_of_distribution`**: (결정 전) web은 이 둘이 나오면 곧바로 SC-03b 물리 피드백을 보냈다.
  손을 올리는 도중에도 자주 나오는 값이라, 오답과 같이 **1초 유지 시에만 확정**하거나, 데모 스크립트처럼
  **화면 안내 문구만 보여주고 물리 피드백은 보내지 않는** 방안을 권한다.
- **시도 횟수 집계**: 오답이 1초 유지 규칙을 통과한 경우만 1회로 센다(과도 자세는 세지 않음).

## 6. 완료 기준 (재시험 체크리스트)

- [ ] 수신호 시작 시 AI Hand 시범과 예시 사진이 **동시에** 나오고, 버튼을 누르기 전에는 판정·SC-04 진입이 없다
- [ ] 스페이스바로 확인이 되고, 페이지가 스크롤되지 않는다
- [ ] 정답 직후, 이전 손모양을 든 채로 있어도 다음 수신호의 오답으로 잡히지 않는다
- [ ] 버튼을 누르고 손을 올리는 도중에는 오답이 나오지 않는다(같은 오답 1초 유지 시에만 확정)
- [ ] 오답 시 재시범 + 예시 사진 + 버튼이 다시 나온다
- [ ] 7종 전 구간(SC-01 → SC-05) 끊김 없이 완료
- [ ] 단위 테스트(송승호): 시범 단계 판정 무시, 확인 시 `/reset` 호출, 오답 1초 미만 무시·1초 이상 확정

## 7. 시행 로그 CSV — 열 정의 (web 할 일 ②-a, 2026-09-28 송승호)

`06_테스트·평가리포트` §1-2의 원본 데이터다. 혼동행렬(§2-2)·지연 P95(§2-3)·인물 단위 비교(§2-4)가 전부 이 파일에서 나온다.
**열 이름은 web 없는 데모 스크립트 CSV(`services/actuation/scripts/aihand_vision_picar_demo.py` `RECORD_FIELDS`)와 같게** 해서
web 유무 결과를 한 표로 비교한다. web에만 있는 값은 뒤에 붙인다.

### 7.1 언제 한 줄을 쓰나

- **판정이 확정될 때마다 1행** — 정답, 오답(1초 유지 통과). `below_tau`/OOD는 §5 결정(화면 안내만)에 따라 **쓰지 않는다**.
  과도 자세(1초 미만)·미검출·과도기 사유도 쓰지 않는다.
- 쓰는 즉시 `flush`한다 — 시연 중 web이 죽어도 그때까지의 행은 남아야 한다.
- 위치: `services/web/logs/web_trials_<시작시각 YYYYMMDD_HHMMSS>.csv` (web 기동마다 새 파일, UTF-8 BOM — 엑셀용).
  `services/web/logs/`는 `.gitignore`에 추가한다(시행 로그는 결과 정리 후 필요한 것만 문서에 붙인다).

### 7.2 열

시각 기준점: `t_demo`(시범 `/command` 전송), `t_demo_done`(그 응답), `t_confirm`(확인 버튼), **`t_dec`(판정 확정 — 지연의 원점)**.

| 열 | 값 | 데모 CSV와 |
| --- | --- | --- |
| `time` | 판정 확정 시각 ISO 8601 (ms) | 같음 |
| `signal` | 목표 수신호(`target_signal`) — **정답 클래스** | 같음 |
| `attempt` | 이 수신호의 시도 번호(1부터) | 같음 |
| `outcome` | `correct` · `wrong` (`below_tau`·`out_of_distribution`은 §5 결정으로 행을 쓰지 않음) | 같음(데모는 `timeout`·`skip`도 있음) |
| `predicted` | vision `predicted_class` — **예측 클래스** | 같음 |
| `match_score` · `confidence` | vision 응답 그대로 | 같음 |
| `vision_latency_ms` | vision 응답 `latency_ms` 그대로 — **판정지연** | 같음 |
| `demo_ok` · `demo_ms` | 이 시도 직전 시범 `/command`의 판정(03 §5-5)과 `t_demo → t_demo_done` | 같음 |
| `observe_ms` | `t_demo_done → t_confirm` — 학습자가 시범을 **본 시간**(버튼을 누르기까지) | 같음(데모는 고정 `OBSERVE_S`) |
| `listen_ms` | `t_confirm → t_dec` — 학습자가 **따라 하는 데 걸린 시간** | 같음 |
| `picar_ok` · `picar_ms` | 정답일 때만. 판정(03 §5-5)과 `t_dec → /picar 응답` = **반응 시작**(주행은 이후 2초) | 같음 |
| `microbit_ok` · `microbit_ms` | `/result`의 판정과 `t_dec → /result 응답` = **반응 시작**(LED O/X 1초는 회신 뒤) | 같음 |
| `feedback_ms` | `max(picar_ms, microbit_ms)` — **반응 시작 기준 물리 피드백 지연** | 같음 |
| `aihand_ok` · `aihand_ms` | 판정 뒤 `/command`(정답 `correct_pose` / 오답 `demo`)의 판정과 `t_dec → 응답` = 손 동작 **완료** | web만 |
| `feedback_done_ms` | `max(aihand_ms, microbit_ms + 1000)` — **완료 기준 물리 피드백 지연**(LED 표시 1초 포함, picar 주행 제외) | web만 |
| `aihand_status` · `microbit_status` · `picar_status` | 본문 `status`/`reason` 원문(예: `ok`, `timeout`, `error:write_failed`, `partial:i2c_failed`) | web만 |
| `picar_led_ok` | picar `led.*.status`가 전부 `ok`/`mocked`인지 | web만 |
| `mocked` | 셋 중 하나라도 `mocked`면 `true` — 실물 KPI 행에서 걸러낸다 | web만 |
| `subject` | 대상자 ID — 환경변수 `LOG_SUBJECT`(대상자마다 web 재기동). 없으면 빈 값 | web만 |

> **"완료" 정의가 미결**이어도(picar 변경안 안건 2) 반응 시작(`feedback_ms`)과 완료(`feedback_done_ms`)를 둘 다 남기므로
> 어느 쪽으로 정해져도 다시 잴 필요가 없다.

### 7.3 판정 뒤 장치 호출 순서 — ✅ 반영(2026-09-28 `c8f1fd3`, 이동혁)

변경 전 `_dispatch_feedback`은 **`/command` → `/result` → `/progress` → `/picar`** 순서로 차례대로 보낸다. `/command`는 손 동작이
끝나야 회신하므로(약 0.8초), **micro:bit와 picar는 판정 후 약 0.85초가 지나서야 반응을 시작**한다. web 없는 데모(picar →
micro:bit 순, 반응 시작 19~47ms)와 같은 KPI를 재도 web만 나빠진다.

→ **`/picar` → `/result` → `/command` → `/progress`** 순서로 바꿨다(14 §3.3·D11).
- picar는 Wi-Fi·다른 보드라 micro:bit 순서 제약(명령을 하나씩 처리)과 무관하다 — 맨 앞에 둔다.
- `/result`(ACK 26~42ms)를 `/command`(0.8초) 앞에 두면 micro:bit O/X가 바로 뜬다.
- 학습 흐름상 문제 없음: 정답 연출(picar·LED)과 AI Hand 정답 자세가 거의 동시에 보인다.
- 결정·구현은 이동혁(①-a·②-a와 같은 함수). 바꾸면 14 §3.3 표도 함께 고친다(2026-09-28 함께 고침).

## 8. 테스트가 기대하는 이름 — 구현 계약 (web 할 일 ⑪, 2026-09-28 송승호)

`services/web/tests/test_judging_timing_spec.py`가 ①-a·②-a·③을 **구현 전에 먼저** 고정해 둔 인수 테스트다(22개).
지금은 "예상된 실패(xfail)"로 표시되고, **아래 이름대로 구현하면 자동으로 실제 테스트로 바뀐다** — 마커를 지울 필요가 없다.
스펙대로 만든 검증용 구현으로 22개 전부 통과하는 것을 확인했다(2026-09-28, 저장소에는 넣지 않음).
**→ 실제 구현(`c8f1fd3`) 병합 후 xfail 0, web 35개 전부 통과(2026-09-28).** 테스트 중 CSV는 `tests/conftest.py`가 임시 폴더로 돌리므로
반드시 `pytest`로 실행한다.

| 무엇 | 이름 · 형태 | 감지 |
| --- | --- | --- |
| 단계 | `_fresh_session()["phase"]` = `"demo"` 로 시작, 판정 중 `"judging"`. `GET /api/state`에도 `phase` | ①-a 묶음 활성화 |
| 확인 API | `POST /api/confirm` — `demo`일 때만 받고, vision reset은 **`httpx.post(f"{VISION_URL}/reset", ...)`** 로 | |
| 오답 유지 | 모듈 상수 **`WRONG_CONFIRM_S`**(기본 1.0) — **호출 시점에 읽기**(테스트가 0.2초로 바꿔 끼운다) | |
| 판정 루프 | `_poll_once(vision_client)` 시그니처 유지. 세션 키 `last_result`·`attempts`·`camera_fail_streak`·`curriculum_index` 유지 | |
| 전송 결과 | `_session["last_dispatch"]`의 `aihand`·`result`·`progress`·`picar` 키, 각각 `{"ok": bool, ...}` (필드 추가는 자유) | ③ 묶음: picar `partial` → `ok: False`가 되면 활성화 |
| 시행 로그 | 모듈 속성 **`TRIAL_LOG_DIR`**(`Path`) — **쓰는 시점에 읽기**. 파일 `web_trials_*.csv`, UTF-8 BOM, 앞 17열은 데모 `RECORD_FIELDS` 순서 | ②-a 묶음 활성화 |

- 장치 호출은 전부 `httpx.post`로 한다(테스트가 이것 하나만 바꿔 끼운다). 시범 `/command`는 백그라운드 스레드로 보내도 된다 — 테스트가 최대 3초 기다린다.
- 기존 `test_state_machine.py` 9개는 ①-a 이후에도 통과하도록 미리 맞춰 뒀다(판정 단계로 시작, 오답은 두 번 폴링).
- 실행: `cd services/web && python -m pytest tests -q -rxX` — `XFAIL`이 사라지고 전부 `passed`면 완료. 구현 중 실패하는 테스트는 **스펙과 다른 곳**을 가리킨다.

## 9. micro:bit 버튼 A를 확인 입력으로 — 2026-09-28 제안 · 2026-09-29 구현 (송승호)

> **✅ web 구현 (2026-09-29)** — `state_machine.py` `_poll_button()`·`_confirm()`, 테스트 `tests/test_microbit_button_confirm.py`(14개).
> actuation mock 서버(`POST /button/simulate`)와 실제 HTTP로 붙여 확인 → `phase` `demo` → `judging`, `last_confirm_source: microbit_button`.
> 실물(micro:bit 버튼)은 미검증(11 §9.1 ④). **아래 1번은 구현에서 바꿨다** — 기준값을 "시범 단계 진입 때"가 아니라
> **시범 `/command` 응답 뒤**(오답 재시범·정답 뒤 다음 시범은 판정 확정 뒤) 처음 읽은 값으로 잡아, AI Hand가 움직이는 동안 누른 입력도 세지 않는다.
> 스페이스바는 시범 도중에도 받는다(§4.1 그대로). 끄려면 `MICROBIT_BUTTON_CONFIRM=0`. 아래는 제안 원문.

학습자가 키보드 없이 AI Hand 옆에서 "준비됨"을 누를 수 있게 하는 **보조 입력**이다. 형식은 [03 §5-3](../03_인터페이스계약서.md).

**web이 폴링한다(pull)** — actuation이 web을 부르면(push) actuation이 web 주소·장애 처리를 떠안는 역방향 의존이 생긴다.
web은 이미 vision·장치를 스스로 불러오는 쪽이라 pull이 구조에 맞고, 폴링 주기(0.2초) 지연은 확인 용도로 충분하다.

1. **시범 단계에 들어갈 때** `GET {ACTUATION_URL}/button`의 `seq`를 `_session["button_seq_base"]`(이름 자유)로 적어 둔다.
   시범 전·판정 중에 눌린 입력이 나중에 확인으로 새지 않게 하려는 것이다.
2. `_poll_once`에서 `phase == "demo"`일 때만 `GET /button`(타임아웃 0.3초 정도)을 부른다. `seq > 기준값`이면 **`/api/confirm`과
   같은 함수**를 부른다 — 스페이스바와 경로가 같아 중복 확인은 `phase` 검사 하나로 막힌다.
3. `seq < 기준값`이면 actuation이 재시작된 것이다 → 기준값을 새 `seq`로 다시 잡는다(확인으로 치지 않음).
4. `GET /button` 실패(연결 실패·타임아웃)는 **조용히 넘긴다** — 버튼은 보조 입력이라 실패가 흐름을 막으면 안 된다.
5. 프론트엔드는 `phase`로 화면이 바뀌므로 수정할 것이 없다. 안내 문구만 "준비되면 확인을 누르세요 (Space 또는 micro:bit A)"로.

- ⚠️ **BLE가 끊긴 동안 누른 입력은 사라진다**(03 §7). 서보 전류로 연결이 끊기는 시점이 시범 직후와 겹칠 수 있으므로 **확인 버튼·
  스페이스바를 반드시 함께 둔다.**
- `_poll_loop`는 `_dispatch_feedback` 동안(최대 수 초) 멈추지만, 그동안은 `phase`가 `demo`가 아니고 1번 기준값 때문에 그 사이 누른 입력도
  확인으로 치지 않는다.
- 시험: actuation `POST /button/simulate`로 `seq`를 올리면 micro:bit 없이 흐름을 확인할 수 있다. §8 인수 테스트에는 넣지 않았다
  (채택 뒤 필요하면 추가).
