# actuation — AI Hand + micro:bit (담당: 송승호)

RACI: 하드웨어·로봇동작 **R**, 파이프라인·판정로직 **A**

> **이 서비스는 Raspberry Pi 5(카메라·AI Hand·micro:bit 고정 스테이션)에서 실행됩니다.**
> picar는 더 이상 이 서비스가 담당하지 않습니다 — 별도 서비스 [`services/picar`](../picar/README.md)가
> **Raspberry Pi 4B 8GB**에서 담당합니다 (2026-09-18, picar가 카메라와 함께 움직이는 문제 해결).

`document/02_설계문서_v2.md` §1-1·§3, `document/03_인터페이스계약서_v2.md` §5-1·§5-3 기준 담당 범위:

- **AI Hand**: 손가락 서보 5개 + 손목 서보 1개 제어 (`shared/schemas/aihand_command.schema.json`)
- **micro:bit v2**: **BLE**(Nordic UART Service)로 통신. 펌웨어(`aihand_control.ts`)는 최상단
  `TEST_MODE` 한 줄로 운영(`false`, `G1`~`G7` 제스처 명령만 처리)/테스트(`true`, `IDX:`/`HAND:`/`G:`
  캘리브레이션 명령까지 처리) 모드를 전환한다 — micro:bit가 하드웨어 UART를 1개만 갖고 있어 서보 초기화 시
  USB 시리얼이 죽는 제약 때문에 애초 계획이던 USB 시리얼(`shared/schemas/microbit_protocol.md`에
  BLE 기준으로 갱신됨)에서 BLE로 전환했다. LED 매트릭스로 판정 결과(`correct`/`incorrect` →
  LED O/X 2초 표시)를 표시하고, 진행 표시(`P<current><total>`)는 LED 없이 수신 확인만 회신한다
  (두 모드 공통). **부저는 BLE SoftDevice 충돌(패닉 070)로 비활성화**되어 있다(2026-09-21 실측 확정).
  버튼 입력(테스트 모드 제외)은 아직 펌웨어에 없음.

## 디렉터리

- `src/aihand/controller.py` — `target_signal`(정지/서행/...) -> micro:bit `G{n}` 제스처 매핑
  (`GESTURE_MAP`). 10_PRD_v2.md §3.2 표 순서와 동일하되, 우회전_유도(G4)는 문서상 "엄지+약지"이나
  실제 펌웨어는 "엄지+소지"로 구현되어 있고 펌웨어 쪽이 최종 확정판이다(2026-09-21 팀 확인,
  문서 갱신 필요). `DEFAULT_SERVO_ANGLES`는 실제 구동에는 쓰이지 않는 참고용 스키마 예시값.
- `src/microbit/ble_bridge.py` — `bleak` 기반 BLE 브릿지(RPi5 쪽 Python). 연결/재연결, `G{n}`/
  `correct`·`incorrect`/`P<current><total>` 전송과 응답 대기를 담당 (UUID·재연결 정책은 아래
  "공통 전제" 참고)
- `src/firmware/*.ts` — micro:bit(MakeCode) 쪽 펌웨어 프로젝트. Python 서비스와는 별개로 MakeCode
  웹 에디터에서 micro:bit에 직접 플래시하는 코드라 `src/microbit/`(Python 패키지)와 폴더를
  분리했다(2026-09-21). 아래 각 파일 설명 참고
- `src/app.py` — FastAPI 진입점 (`/health`, `/command`, `/result`, `/progress`). 셋 다
  `ble_bridge`를 통해 실제 BLE 전송까지 연동되어 있음(`/progress`는 LED 표시 없이 수신 확인만)
- `tests/vision_to_command_integration_test.py` — vision의 JudgmentResult 형태 값을
  `/command`로 흘려보내 target_signal↔G{n} 매핑이 실제로 동작하는지 확인하는 통합 테스트
  (MediaPipe 연동 전 단계 검증용, "다음 단계" 참고)

## MOCK_HARDWARE 모드

로컬 PC(Windows)에는 서보/micro:bit가 물리적으로 연결되어 있지 않으므로, 기본값
`MOCK_HARDWARE=true`일 때는 실제 GPIO/시리얼 호출 대신 로그만 남기고 성공 응답을 반환합니다.
하드웨어 도착 후 `MOCK_HARDWARE=false` + `devices:` 매핑(docker-compose.yml 주석 참고)으로 전환하세요.

## picar와의 관계

이전에는 이 서비스가 picar도 함께 제어했지만(RPi5 GPIO 직결 가정), picar가 실제로 주행하면 카메라도
함께 이동해버리는 문제가 있어 **picar 제어를 별도 보드(RPi4B 8GB)·별도 서비스(`services/picar`)로
분리**했습니다. `services/web`의 상태머신이 AI Hand/micro:bit는 이 서비스(`ACTUATION_URL`)로,
picar는 `services/picar`(`PICAR_URL`, Wi-Fi)로 각각 따로 호출합니다.

## 아직 확정 안 된 것 (실물 테스트 필요)

- [x] ~~AI Hand GPIO 핀 배정 및 연결 방식~~ → RPi5가 서보를 직접 구동하지 않음. micro:bit 펌웨어가
  서보를 직접 제어하고 RPi5는 BLE로 `G{n}` 제스처만 지시
- [x] ~~서보 각도 초기값(170/10/90)의 실물 캘리브레이션~~ → 손가락별 안전 가동범위 실측 완료(아래 표).
  엄지 서보는 **교체하지 않기로 확정**했지만, **엄지 동작은 설계·시현에 그대로 유지**한다(2026-09-21)
  — 펌웨어의 엄지 각도는 손대지 않고 물리적으로만 움직이지 않는 상태로 진행
- [x] ~~micro:bit 실제 시리얼 코드로 프로토콜 동작 검증~~ → bluetooth 방식으로 전환 완료
- [ ] `docker compose up actuation`으로 RPi5 실물 환경에서 BLE(BlueZ/D-Bus) 접근 검증 (컨테이너
  네트워킹, docker-compose.yml 주석 참고)
- [x] ~~RESULT(micro:bit LED 매트릭스) 프로토콜 펌웨어 구현~~ → `aihand_control.ts`가 `"correct"`/
  `"incorrect"` 문자열을 받으면 LED에 O/X를 2초간 표시하고 꺼지도록 구현 완료(TEST_MODE와 무관하게
  항상 처리). **부저는 비활성화**(`BUZZER_ENABLED = false`) — 아래 "부저 비활성화" 참고
- [x] ~~실물 micro:bit로 `MOCK_HARDWARE=false` BLE 검증~~ → 2026-09-21 완료. 스캔·UUID 대조·
  `/health`(`microbit_connected: true`)·`/command` 7종·`/result`(LED O/X)·`/progress`(`OKP37`/`OKP17`
  회신)까지 전부 확인. 손모양 육안 대조도 완료 — 엄지 미동작으로 `G3`↔`G6`, `G4`↔`G7`이 실제로
  구별되지 않음을 확인했다(아래 "현재 제약" 참고). 남은 것은 RPi5 컨테이너 BLE 접근 검증뿐
- [x] ~~`ble_bridge.py`/`app.py`의 `/result`를 펌웨어의 `correct`/`incorrect` 명령과 연동~~ →
  `ble_bridge.send_result()` 추가, `/result`가 `is_correct` 값을 그대로 BLE로 전송(2026-09-21)
- [x] ~~PROGRESS 프로토콜 펌웨어 구현~~ → `aihand_control.ts`가 `"P<current><total>"`(둘 다 한 자리
  숫자)을 받아 `"OKP<current><total>"`로 회신하도록 구현 완료. **LED 표시는 하지 않음**(2026-09-21
  결정 — 진행 표시는 web 화면 쪽 담당, micro:bit는 수신 확인만). `ble_bridge.send_progress()` +
  `/progress` 엔드포인트 연동까지 완료
- [x] ~~`shared/schemas/microbit_protocol.md`를 BLE 프로토콜 기준으로 갱신~~ → `document/03_인터페이스계약서_v2.md` §5-3과 함께 갱신 완료(2026-09-21)
- [x] ~~`document/10_PRD_v2.md` §3.2 표의 우회전_유도(G4) 설명을 "엄지+소지"로 정정~~ → 정정 완료.
  PRD 표가 펌웨어와 일치함(2026-09-21 확인)
- [x] ~~엄지 제외 확정에 따른 제스처 구별성 재검토(4손가락 재설계)~~ → **재설계하지 않기로 확정**
  (2026-09-21). `G1`~`G7`은 엄지값만 다르고 나머지 4손가락 조합이 같은 쌍이 있어(`G3`(좌회전_유도)↔
  `G6`(후진), `G4`(우회전_유도)↔`G7`(주의)) 엄지가 멈춰 있으면 AI Hand 상에서 구별되지 않지만,
  손모양을 바꾸면 PRD §3.2·vision 학습 클래스·공개 데이터까지 연쇄 수정이 필요해 비용이 더 크다.
  **시현상의 제약으로 감수**하고 펌웨어 제스처 정의는 현행 유지 — 필요하면 web 화면 안내로 보완한다

# AiHand + micro:bit BLE 연동 코드

AI비전으로 인식한 수신호를 micro:bit(BLE)를 거쳐 AiHand 서보모터로 재현하기 위한 코드 모음입니다.

## 공통 전제

- micro:bit는 하드웨어 UART가 1개뿐이라 `startbit_Init()` 실행 시 USB 시리얼이 죽습니다. **PC와의 통신은 반드시 BLE**로 합니다.
- 이 보드는 표준 Nordic UART Service와 달리 RX/TX UUID가 **반대로 배정**되어 있습니다 (`6e400003`=쓰기용 RX, `6e400002`=indicate용 TX). 다른 프로젝트 코드를 그대로 가져다 쓰면 안 됩니다.
- 손가락 서보는 **동시 구동 금지**입니다(순간 전류 급증 → 전압 강하 → BLE 연결 끊김). 모든 코드는 손가락 간 200ms 텀을 둔 완전 순차 이동 방식을 사용합니다.
  - 스펙상 근거(`document/11_하드웨어설계서_v1.md` §4.4): 7.5V 3A 어댑터 하나가 Hiwonder 확장보드를 거쳐 **micro:bit와 서보를 같은 레일에서** 먹인다. 손가락 서보(LFD-01) 구속 전류가 개당 700mA라 5개 동시 기동 시 3.5A로 어댑터 용량(3A)을 넘기고, 레일이 주저앉으면 같은 레일의 micro:bit가 브라운아웃되어 BLE가 끊긴다.
  - ⚠️ **2026-09-21 정정**: 이전에는 "micro:bit 보드 공급 한계 300mA"를 근거로 들었으나 **틀린 설명이었다.** 서보는 micro:bit를 거치지 않고 확장보드가 어댑터에서 직접 분배한다. 결론(순차 구동)은 같지만 메커니즘이 다르다 — 실제 제약은 **어댑터 용량**이므로, 전원을 보강하면 동시 구동이 가능해질 여지가 있다(일정상 후순위).

---

## 단위 테스트 (micro:bit 불필요)

```bash
cd services/actuation
python -m pytest tests -q        # 14개
```

A-1 실물 검증은 micro:bit가 연결돼 있어야만 돌릴 수 있어서, **하드웨어 없이도 매핑·프로토콜이
어긋나지 않았는지** 확인할 수 있게 만든 테스트입니다 (`tests/test_controller.py`). 실제 BLE는
건드리지 않습니다. `pytest-asyncio` 없이 돌도록 `asyncio.run()`으로 감쌌습니다.

주요 항목:
- `GESTURE_MAP`이 `aihand_command.schema.json`의 7종과 정확히 일치하는지 (어긋나면 특정 수신호에서
  AI Hand가 침묵함)
- G번호가 1~7 중복 없이, PRD §3.2 표 순서와 같은지
- BLE 명령 문자열 형식: `G{n}` / `correct`·`incorrect` / `P37`(콜론·구분자 없음 — 펌웨어가
  문자코드로 직접 파싱)
- **RX/TX UUID가 이 보드에서 실측한 반대 배정 그대로인지** — 표준 NUS 값으로 되돌리면 통신이 죽음
- 알 수 없는/누락된 `target_signal`에 죽지 않고 에러를 돌려주는지
- mock 경로가 BLE 연결을 열지 않는지

## `ble_debug_services.py`

**용도**: micro:bit가 광고하는 BLE 서비스/캐릭터리스틱 UUID 전체를 스캔해서 출력하는 디버그 스크립트.

**언제 쓰나**: 새 micro:bit 보드로 교체했거나, `start_notify()`에서 `characteristic does not support notifications` 에러가 날 때 실제 UUID 속성을 확인하기 위해 실행합니다.

**주의**: 여기서 확인한 UUID가 위 "공통 전제"의 값과 다르면, 보드/펌웨어가 바뀐 것이니 다른 파일들의 UUID 상수도 함께 갱신해야 합니다.

---

## `aihand_control.ts` / `aihand_control_pc.py` (운영/테스트 통합)

**용도**: 기존 `aihand_named_control.ts`(캘리브레이션용)와 `aihand_production.ts`(운영용)를 하나로
합친 펌웨어. 최상단 `const TEST_MODE = false;` **한 줄만 바꿔서** 운영/테스트 모드를 전환합니다.

**판정 결과 표시 (RESULT, 모드 공통)**: `TEST_MODE` 값과 무관하게 항상 처리됩니다.
- `"correct"` 수신 → LED에 O 모양 2초간 표시 후 소등, `OK:CORRECT\n` 회신
- `"incorrect"` 수신 → LED에 X 모양 2초간 표시 후 소등, `OK:INCORRECT\n` 회신
- `showResult()` 실행 중(2초) `basic.pause()`로 블로킹되므로 그 사이 다른 BLE 명령은 처리되지 않음

> 🔴 **절대 규칙 — BLE 시작 후 `music.*` 호출 금지 (2026-09-22 확정)**
>
> micro:bit v2에서 **BLE SoftDevice와 `music` 라이브러리는 같은 하드웨어 타이머/PWM 자원을 공유**해
> 함께 쓸 수 없습니다. `bluetooth.startUartService()` 이후 `music.*`를 호출하면 **소리가 나야 할
> 바로 그 시점에 패닉 070(SD_ASSERT)** 이 발생하고 BLE가 끊깁니다.
>
> - 2026-09-21 `/result` 실물 테스트에서 최초 재현("부저 울리는 순간 슬픈 얼굴 + 070, BLE 끊김"),
>   이후 부저 코드를 직접 넣어 실행하는 전용 검증으로 **확정**했습니다.
> - **타이밍 튜닝으로 우회할 수 있는 버그가 아닙니다.** 종전 README에 있던 "비블로킹 재생·볼륨
>   저감 등을 검증하면 되살릴 수 있다"는 단서는 **철회합니다.**
> - 전례: `StartbitV2_patched.ts:324`도 같은 이유로 `music.playTone()`을 LED로 대체해 두었는데,
>   RESULT 기능을 추가하면서 같은 호출이 다시 들어갔던 적이 있습니다(회귀).
>
> **지켜야 할 것**
> 1. `bluetooth.startUartService()` 이후 `music.*`를 호출하지 않습니다.
> 2. 소리 피드백이 필요하면 `basic.showIcon()` / `basic.showLeds()` / `basic.showString()` 등
>    **LED로 대체**합니다.
>
> 조치: 2026-09-22 `aihand_control.ts`에서 `playResultTone()`과 `BUZZER_ENABLED` 플래그를
> **삭제**했습니다. 꺼둔 채로 남겨두면 플래그 한 줄로 패닉을 부를 수 있기 때문입니다.
> `showResult()`는 `basic.pause(2000)`으로 LED 표시 시간 2초를 유지합니다.

**진행 표시 (PROGRESS, 모드 공통)**: `TEST_MODE` 값과 무관하게 항상 처리됩니다.
- `"P<current><total>"` 수신 (예: `"P37"` = 3/7번째) → **LED 표시는 하지 않고** `"OKP<current><total>\n"`만
  회신 (2026-09-21 결정 — 진행 표시는 web 화면 쪽 담당). 콜론 없이 한 자리 숫자 두 개만 붙여서
  `charCodeAt()`으로 파싱 — `G{n}`과 같은 경량화 방식.

**모드별 동작**:
- `TEST_MODE = false` (운영, 기존 `aihand_production.ts`와 동일 동작): `G1`~`G7`만 처리.
  파싱 비용이 큰 `substr()+split()+parseInt()` 대신 `charCodeAt()` 문자 직접 비교만 수행 —
  micro:bit의 협소한 RAM에서 힙 할당이 잦으면 불안정해지기 때문. `HAND:`/`IDX:` 형식은 지원하지 않음.
- `TEST_MODE = true` (테스트/캘리브레이션, 기존 `aihand_named_control.ts`와 동일 동작): 아래 명령까지 처리.
  - `IDX:번호,각도` : 개별 서보에 반전 없이 raw 각도 그대로 전달 (손가락 번호 확인·캘리브레이션용)
  - `HAND:엄지,검지,중지,약지,소지` : 5개 서보 각도 동시 지정
  - `G:1` ~ `G:7` : 콜론 포함 형식으로 제스처 호출 (운영 모드의 `G1`~`G7`과 별개 형식)
  - 시작 시 LED에 `READY` 표시, 버튼 B로 `READY` 재표시

**서보 방향**: 엄지는 raw 각도 그대로 사용(혼 장착 방향이 반대라 반전 불필요), 검지~소지는
`moveInverted()`(180-각도) 적용 — 두 모드 공통.

**손가락별 안전 가동범위 (스톨 방지, 두 모드 공통)**:

| 손가락 | min | max |
|---|---|---|
| 엄지 | 60 | 170 |
| 검지 | 20 | 135 |
| 중지 | 25 | 135 |
| 약지 | 25 | 125 |
| 소지 | 30 | 120 |

**이동 방식**: 손가락 간 텀 200ms 완전 순차 이동 (초기화 시 주먹 자세 포함) — 두 모드 공통.

**현재 제약**: 엄지 서보 하드웨어 고장 — **교체하지 않기로 확정**(2026-09-21). 다만 **엄지 동작은
설계·시현에 그대로 유지**하므로 펌웨어의 `G1`~`G7` 엄지 각도는 변경하지 않는다.

**2026-09-21 실물 육안 대조 결과**: 엄지가 움직이지 않아 `G3`(좌회전_유도)↔`G6`(후진),
`G4`(우회전_유도)↔`G7`(주의)이 **실제로 구별되지 않음을 확인**했다. 즉 AI Hand 시범 단계에서 7종 중
4종이 2쌍으로 겹친다. 제스처 재설계는 하지 않기로 확정했으므로(위 "아직 확정 안 된 것"),
시현에서는 web 화면이 표시하는 목표 수신호 이름(`GET /api/state`의 `target_signal`)으로 학습자가
구분하고 AI Hand는 보조 시범 역할을 한다. 인식·판정 경로는 로봇손과 무관하므로 KPI에는 영향이 없다.

**PC 쪽 (`tests/aihand_control_pc.py`)**: micro:bit 쪽과 동일하게 최상단 `TEST_MODE` 한 줄로 운영
(숫자 입력 → `G1`~`G7`, `loop` 내구성 테스트, `progress <current> <total>`)/테스트(`idx`/`g`/`hand`
명령 → `IDX:`/`G:`/`HAND:`) 모드를 전환합니다. micro:bit 펌웨어의 `TEST_MODE` 값과 반드시 맞춰서
실행하세요. 두 모드 모두 `correct`/`incorrect`(LED O/X, 부저 없음), `progress`(수신
확인만) 입력을 테스트할 수 있습니다. `bleak` 사용, RX/TX UUID는 위 "공통 전제" 참고.

---

## `aihand_finger_test.ts` (손가락별 개별 테스트)

**용도**: 손가락 1개씩 개별 채널을 격리해서 테스트하는 진단 도구. 버튼 단독 사용과 BLE(`IDX`) 겸용을 모두 지원합니다.

**언제 쓰나**:
- 특정 서보가 무반응/이상 동작할 때 하드웨어(보드 채널) 문제인지 서보 자체 문제인지 구분할 때
- **서보 스왑 테스트** 절차: 의심되는 채널에 정상 작동 중인 다른 서보를 연결해 반응을 확인 (반전 방향으로 움직이면 채널은 정상, 서보 쪽이 원인)

**진단 이력 참고**: 엄지 채널(1번)은 이 도구로 스왑 테스트를 완료해 보드는 정상, 엄지 서보 자체의 하드웨어 고장으로 최종 확정되었습니다.

---

## FastAPI 레이어 (`src/app.py`)

RPi5에서 실행되며, 상태머신(web)과 micro:bit BLE 사이를 잇는 서비스 레이어입니다.

| 엔드포인트 | 설명 |
| --- | --- |
| `GET /health` | `mock_hardware`, `microbit_connected` 상태 확인 |
| `POST /command` | `aihand_command.schema.json` 형식 입력 → `target_signal`을 `G{n}`으로 변환해 BLE 전송 |
| `POST /result` | 판정 결과 LED 표시(O/X) — `is_correct`를 `correct`/`incorrect`로 변환해 BLE 전송
  (`match_score`는 펌웨어가 쓰지 않아 전달하지 않음) |
| `POST /progress` | 진행 표시 — `current`/`total`을 `P<current><total>`로 변환해 BLE 전송 (LED 표시는
  펌웨어가 하지 않음, 수신 확인만) |

`/command` 응답 예 (`MOCK_HARDWARE=true`): `{"status": "mocked", "sent": "G1", "target_signal": "정지", "gesture": 1}`

## 다음 단계

1. ~~엄지 서보(Hiwonder LFD-01) 교체 → 엄지 min/max 재검증~~ → **교체하지 않기로 확정**(2026-09-21).
   엄지 각도 상수는 현행 유지하고 엄지 동작은 설계·시현에 그대로 둔다
2. 실물 micro:bit + RPi5에서 `MOCK_HARDWARE=false`로 `/command`·`/result`·`/progress` end-to-end
   검증 (`tests/vision_to_command_integration_test.py`로 target_signal별 `G{n}` 전송·BLE 재현 확인)
3. ~~`services/web`의 상태머신이 vision `/latest` 판정 결과를 이 서비스의 `/command`로 호출하도록
   연동~~ → `state_machine.py`에 구현 완료(2026-09-21, `services/web/README.md` 참고)
4. ~~PROGRESS 프로토콜을 펌웨어(`aihand_control.ts`)에 추가해 `/progress`까지 실물 지원~~ → 구현
   완료(2026-09-21, LED 표시 없이 수신 확인만)
5. BTN(버튼 입력) 프로토콜 필요 여부 검토 — 아직 펌웨어에 없고 사용 계획도 불명확

## 로컬 실행

```bash
docker compose up --build actuation
curl http://localhost:8002/health

# 또는 컨테이너 없이 직접 (MOCK_HARDWARE 기본값 true):
cd src && uvicorn app:app --reload --port 8002
```


