# actuation — AI Hand + micro:bit (담당: 송승호)

RACI: 하드웨어·로봇동작 **R**, 파이프라인·판정로직 **A**

> **이 서비스는 Raspberry Pi 5(카메라·AI Hand·micro:bit 고정 스테이션)에서 실행됩니다.**
> picar는 더 이상 이 서비스가 담당하지 않습니다 — 별도 서비스 [`services/picar`](../picar/README.md)가
> **Raspberry Pi 4B 8GB**에서 담당합니다 (2026-09-18, picar가 카메라와 함께 움직이는 문제 해결).

`document/02_설계문서_v2.md` §1-1·§3, `document/03_인터페이스계약서_v2.md` §5-1·§5-3 기준 담당 범위:

- **AI Hand**: 손가락 서보 5개 + 손목 서보 1개 제어 (`shared/schemas/aihand_command.schema.json`)
- **micro:bit v2**: **BLE**(Nordic UART Service)로 통신. 운영 펌웨어(`aihand_production.ts`)가
  `G1`~`G7` 제스처 명령만 처리한다 — micro:bit가 하드웨어 UART를 1개만 갖고 있어 서보 초기화 시
  USB 시리얼이 죽는 제약 때문에 애초 계획이던 USB 시리얼(`shared/schemas/microbit_protocol.md`,
  아직 미갱신)에서 BLE로 전환했다. LED 매트릭스(RESULT/PROGRESS)·버튼 입력은 아직 펌웨어에 없음.

## 디렉터리

- `src/aihand/controller.py` — `target_signal`(정지/서행/...) -> micro:bit `G{n}` 제스처 매핑
  (`GESTURE_MAP`). 10_PRD_v2.md §3.2 표 순서와 동일하되, 우회전_유도(G4)는 문서상 "엄지+약지"이나
  실제 펌웨어는 "엄지+소지"로 구현되어 있고 펌웨어 쪽이 최종 확정판이다(2026-09-21 팀 확인,
  문서 갱신 필요). `DEFAULT_SERVO_ANGLES`는 실제 구동에는 쓰이지 않는 참고용 스키마 예시값.
- `src/microbit/ble_bridge.py` — `bleak` 기반 BLE 브릿지. 연결/재연결, `G{n}` 전송과 `OK{n}`/
  타임아웃 처리를 담당 (UUID·재연결 정책은 아래 "공통 전제" 참고)
- `src/microbit/*.ts` — micro:bit(MakeCode) 쪽 펌웨어. 아래 각 파일 설명 참고
- `src/app.py` — FastAPI 진입점 (`/health`, `/command`, `/result`, `/progress` — 뒤 둘은 펌웨어
  미구현으로 MOCK_HARDWARE=false에서 `{"status": "unsupported"}` 반환)
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
- [x] ~~서보 각도 초기값(170/10/90)의 실물 캘리브레이션~~ → 손가락별 안전 가동범위 실측 완료(아래 표),
  엄지 서보만 하드웨어 고장으로 교체 대기 중
- [x] ~~micro:bit 실제 시리얼 코드로 프로토콜 동작 검증~~ → bluetooth 방식으로 전환 완료
- [ ] `docker compose up actuation`으로 RPi5 실물 환경에서 BLE(BlueZ/D-Bus) 접근 검증 (컨테이너
  네트워킹, docker-compose.yml 주석 참고)
- [ ] RESULT/PROGRESS(micro:bit LED 매트릭스) 프로토콜 펌웨어 구현 — 현재 `/result`, `/progress`는
  펌웨어 미지원으로 `MOCK_HARDWARE=false`에서도 동작하지 않음
- [ ] `shared/schemas/microbit_protocol.md`를 BLE 프로토콜 기준으로 갱신 (아직 USB 시리얼 기준)
- [ ] `document/10_PRD_v2.md` §3.2 표의 우회전_유도(G4) 설명을 "엄지+소지"로 정정 (현재 "엄지+약지"로
  펌웨어와 불일치)

# AiHand + micro:bit BLE 연동 코드

AI비전으로 인식한 수신호를 micro:bit(BLE)를 거쳐 AiHand 서보모터로 재현하기 위한 코드 모음입니다.

## 공통 전제

- micro:bit는 하드웨어 UART가 1개뿐이라 `startbit_Init()` 실행 시 USB 시리얼이 죽습니다. **PC와의 통신은 반드시 BLE**로 합니다.
- 이 보드는 표준 Nordic UART Service와 달리 RX/TX UUID가 **반대로 배정**되어 있습니다 (`6e400003`=쓰기용 RX, `6e400002`=indicate용 TX). 다른 프로젝트 코드를 그대로 가져다 쓰면 안 됩니다.
- 손가락 서보는 **동시 구동 금지**입니다(순간 전류 급증 → 전압 강하 → BLE 연결 끊김). 모든 코드는 손가락 간 200ms 텀을 둔 완전 순차 이동 방식을 사용합니다.
  - 스펙상 근거(`doc/hardware_spec.md`): micro:bit v2 보드 최대 공급 전류 약 300mA vs 손가락 서보(LFD-01) 구속 전류 최대 700mA(6V). 서보 1개만 걸려도 보드 공급 한계를 넘으므로, 동시 구동 금지는 임시방편이 아니라 이 보드에서 사실상 유일하게 안전한 구동 방식이다.

---

## `ble_debug_services.py`

**용도**: micro:bit가 광고하는 BLE 서비스/캐릭터리스틱 UUID 전체를 스캔해서 출력하는 디버그 스크립트.

**언제 쓰나**: 새 micro:bit 보드로 교체했거나, `start_notify()`에서 `characteristic does not support notifications` 에러가 날 때 실제 UUID 속성을 확인하기 위해 실행합니다.

**주의**: 여기서 확인한 UUID가 위 "공통 전제"의 값과 다르면, 보드/펌웨어가 바뀐 것이니 다른 파일들의 UUID 상수도 함께 갱신해야 합니다.

---

## `aihand_named_control.ts` / `aihand_named_control_pc.py` (캘리브레이션용)

**용도**: 서보 개별 제어 및 각도 캘리브레이션 전용 코드. 운영 코드가 아니라 튜닝 도구입니다.

**지원 명령**:
- `IDX` : 손가락 번호 확인용 (1=엄지, 2=검지, 3=중지, 4=약지, 5=소지)
- `HAND:170,170,...` : 5개 서보 각도 동시 지정 (파싱 비용이 커서 운영용에는 미사용)

**서보 방향**:
- 엄지: raw 각도 그대로 사용 (혼 장착 방향이 반대이므로 반전 불필요)
- 검지~소지: `moveInverted()` (180-각도) 적용

**손가락별 안전 가동범위 (스톨 방지)**:

| 손가락 | min | max |
|---|---|---|
| 엄지 | 60 | 170 |
| 검지 | 20 | 135 |
| 중지 | 25 | 135 |
| 약지 | 25 | 125 |
| 소지 | 30 | 120 |

**이동 방식**: 손가락 간 텀 200ms 완전 순차 이동 (초기화 시 주먹 자세 포함).

**PC 쪽(`_pc.py`)**: `bleak` 사용, RX/TX UUID는 위 "공통 전제" 참고.

---

## `aihand_production.ts` / `aihand_production_pc.py` (운영용)

**용도**: 실제 시연/운영에 쓰는 경량화 버전. 캘리브레이션 코드와 달리 파싱 비용을 최소화했습니다.

**지원 명령**: `G1`~`G7` (수신호 7종에 대응하는 완성 동작만 전송). `HAND:` 형식은 지원하지 않습니다.

**경량화 이유**: `substr()+split()+parseInt()` 다회 호출은 micro:bit의 협소한 RAM에서 힙 할당이 잦아 불안정합니다. 운영 코드는 `charCodeAt()`으로 문자 직접 비교만 수행합니다.

**이동 방식**: 캘리브레이션용과 동일하게 손가락 간 200ms 순차 이동, 초기화 시 주먹 자세.

**현재 제약**: 엄지 서보 고장(하드웨어 교체 대기 중)으로 인해 **엄지 제외 4손가락 기준**으로만 정상 동작합니다. 엄지 서보(Hiwonder LFD-01) 교체 후 `fingerMinAngle[0]`/`fingerMaxAngle[0]` 재검증 필요.

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
| `POST /result` | 판정 결과 LED 표시 (펌웨어 미구현, 현재는 `MOCK_HARDWARE=true`에서만 응답) |
| `POST /progress` | 진행 표시 (`/result`와 동일한 이유로 펌웨어 미구현) |

`/command` 응답 예 (`MOCK_HARDWARE=true`): `{"status": "mocked", "sent": "G1", "target_signal": "정지", "gesture": 1}`

## 다음 단계

1. 엄지 서보(Hiwonder LFD-01) 교체 → `aihand_named_control.ts`의 엄지 min/max 재검증
2. `aihand_production.ts`에 검증된 값 반영
3. 실물 micro:bit + RPi5에서 `MOCK_HARDWARE=false`로 `/command` end-to-end 검증
   (`tests/vision_to_command_integration_test.py`로 target_signal별 `G{n}` 전송·BLE 재현 확인)
4. `services/web`의 상태머신이 vision `/latest` 판정 결과를 이 서비스의 `/command`로 실제로
   호출하도록 연동 (현재 `state_machine.py`는 TODO 상태)
5. RESULT/PROGRESS 프로토콜을 펌웨어(`aihand_production.ts`)에 추가해 `/result`, `/progress` 실물 지원

## 로컬 실행

```bash
docker compose up --build actuation
curl http://localhost:8002/health

# 또는 컨테이너 없이 직접 (MOCK_HARDWARE 기본값 true):
cd src && uvicorn app:app --reload --port 8002
```


