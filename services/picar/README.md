# picar — picar 전용 컨트롤러 (담당: 송승호)

RACI: 하드웨어·로봇동작 **R** (services/actuation과 동일 담당자, 배포 보드만 다름)

> **이 서비스는 Raspberry Pi 4B 8GB(picar 차체 탑재)에서 실행됩니다.** Raspberry Pi 5(카메라·AI
> Hand·micro:bit 고정 스테이션)와는 **물리적으로 다른 보드**이며 **Wi-Fi(HTTP)** 로 통신합니다.

## 왜 별도 서비스/보드로 분리했나 (2026-09-18)

처음에는 RPi5가 카메라 추론과 picar 구동을 모두 맡는 구조였습니다. 그런데 picar가 실제로 주행하면
그 위의 카메라도 함께 움직여, **학습자가 판정을 받을 때마다 카메라(picar)를 따라가서 다시 손을
보여줘야 하는 문제**가 생겼습니다. 그래서 picar 구동만 별도의 Raspberry Pi 4B 8GB로 분리하고,
카메라·AI Hand·micro:bit는 RPi5에 그대로 두었습니다 (`document/02_설계문서_v2.md` §1-1 참고).

## 담당 범위

- `src/controller.py` — 모터(전진/후진/정지/좌우회전) + LED(적색×2, 황색×2) 제어. `document/hardware_pinmap.md`의 Raspbot_pinmap 표(2026-09-21 확인) 기준:
  - **모터**: Pi의 raw GPIO가 아니라 I2C(SCL=BCM3, SDA=BCM2)로 하위 코프로세서를 거쳐 구동.
    **명령 프로토콜 확보 완료(2026-09-21)** — 아래 "모터 I2C 프로토콜" 참고
  - **LED**: 보드 내장 LED는 적색(BCM21)·청색(BCM20) 2개뿐. 황색 2개는 보드에 없어 외부 LED를 여유 GPIO에 추가 배선 예정(실물 배선 후 핀 확정, `controller.py`의 `USED_BCM_PINS` 참고해 충돌 회피)

## 모터 I2C 프로토콜 (2026-09-21 확보)

Yahboom 공식 드라이버 라이브러리 `YB_Pcb_Car.py`에서 확보했습니다. Pi는 I2C 버스 1로 코프로세서에
레지스터 쓰기만 하면 됩니다.

| 레지스터 | 용도 | 바이트 포맷 |
| --- | --- | --- |
| `0x01` | 모터 구동 | `[좌_방향, 좌_속도, 우_방향, 우_속도]` (방향 `0`=후진 / `1`=전진, 속도 `0~255`) |
| `0x02` | 정지 | 단일 바이트 `0x00` |
| `0x03` | 서보 | `[서보ID, 각도(0~180)]` — 카메라 팬/틸트용, 이 제품의 주행에는 미사용 |

- **슬레이브 주소 `0x16`** (Raspbot 오리지널 기준)
- ⚠️ **Raspbot V2는 `0x2B`를 씁니다.** 실물에서 반드시 `i2cdetect -y 1`로 먼저 확인하고, 다르면
  `RASPBOT_I2C_ADDR` 환경변수로 덮어쓰세요.
- 우리 보드가 오리지널로 추정되는 근거: `hardware_pinmap.md`에서 초음파·부저·LED·트래킹이 전부
  Pi GPIO 직결인데, V2는 이 주변장치들까지 MCU가 I2C로 관장합니다.
- 스키마의 `motor.speed`는 `0~100(%)`, 코프로세서는 `0~255`라 `controller.py`가 변환합니다.

### ⚠️ 주행 지속 시간 — 팀 확인 필요

`picar_command.schema.json`에 **주행 지속 시간 필드가 없습니다.** 명령을 그대로 흘리면 다음 명령이
올 때까지 차가 계속 달립니다. 그래서 주행 명령 후 `MOTION_DURATION_S`(기본 2초) 뒤 자동 정지시키는
안전장치를 넣어 뒀습니다(`PICAR_MOTION_DURATION_S` 환경변수로 조정). **잠정값이며 실물 주행 후
확정이 필요합니다** — 스키마에 `duration_ms`를 추가할지도 함께 결정해야 합니다.

### 좌/우 회전 방식

제자리 회전(한쪽 전진 + 반대쪽 후진)으로 구현했습니다 — 교육용 시범이라 회전이 눈에 확실히 보이는
편이 낫다는 판단입니다. 완만한 선회가 필요하면 한쪽 속도를 0으로 두는 방식으로 바꾸면 됩니다
(실물 주행 후 조정 대상).
- `src/app.py` — FastAPI 진입점 (`/health`, `/picar`)

입력 스키마: `shared/schemas/picar_command.schema.json`. `document/03_인터페이스계약서_v2.md` §5-2에
정의된 필드명 그대로 사용하세요.

## 호출하는 쪽 (services/web)과의 계약

- 전송: `POST http://<RPi4B_IP>:8000/picar` (docker-compose 로컬 개발 시 `http://picar:8000/picar`)
- **타임아웃/재시도/폴백은 호출하는 쪽(web)이 책임집니다** — 이 서비스는 단순히 명령을 받아 실행할
  뿐, ACK나 재전송 로직을 갖지 않습니다 (03_인터페이스계약서_v2 §5-2·§7 확정 정책).

## MOCK_HARDWARE 모드

picar/RPi4B가 아직 팀에 도착하지 않았으므로, 기본값 `MOCK_HARDWARE=true`일 때는 실제 GPIO 호출 대신
로그만 남기고 성공 응답을 반환합니다.

## 실물 검증 절차 (RPi4B 도착 후)

아직 실물이 없어 아래는 **미검증**입니다. 보드가 오면 이 순서대로 확인하세요.

```bash
# 1) I2C 활성화 확인 + 슬레이브 주소 실측 (여기서 0x16이 아니면 RASPBOT_I2C_ADDR로 덮어쓸 것)
sudo raspi-config nonint do_i2c 0
i2cdetect -y 1

# 2) 서비스 기동 (실물 모드)
cd services/picar
MOCK_HARDWARE=false uvicorn app:app --app-dir src --host 0.0.0.0 --port 8000

# 3) 차를 들어 올린 상태에서(바퀴가 공중에 뜨게) 먼저 저속으로 확인
curl -s -X POST http://localhost:8000/picar -H "Content-Type: application/json" -d '{
  "command":"slow","target_signal":"서행",
  "motor":{"action":"forward","speed":30},
  "led":{"red":"off","yellow_left":"off","yellow_right":"off"}}'
```

확인할 것: ① 바퀴가 전진 방향으로 도는가 ② 2초 뒤 자동으로 멈추는가 ③ 좌/우 회전이 의도한
방향인가(반대면 좌우 배선이 뒤집힌 것) ④ 적색 LED(BCM21) on/off/blink 동작.

> `MOCK_HARDWARE=true`(기본값)에서는 실제로 전송될 I2C 주소·레지스터·바이트 배열을 응답에 담아
> 돌려주므로, 보드 없이도 프로토콜 변환이 맞는지 미리 검토할 수 있습니다.

## 아직 확정 안 된 것

- [x] ~~GPIO 핀 배정~~ → LED 적색(BCM21)만 확정. 모터는 GPIO가 아니라 I2C 구조로 확인됨(위 "담당 범위" 참고)
- [x] ~~모터 I2C 명령 프로토콜(레지스터 주소/바이트 포맷)~~ → Yahboom `YB_Pcb_Car.py`에서 확보,
  `controller.py`에 구현 완료(2026-09-21). **단 실물 검증은 아직** — 슬레이브 주소가 `0x16`이 맞는지
  `i2cdetect`로 확인 필요
- [ ] 주행 지속 시간 확정 (현재 자동 정지 2초 잠정값, 스키마에 `duration_ms` 추가 여부 포함)
- [ ] 황색 LED 2개 배선 및 최종 BCM 핀 번호 확정
- [ ] picar 전원 계통 분리 여부(모터 노이즈가 RPi4B 자체 Wi-Fi 모듈에 영향 주는지) — 실물 조립 후 이 서비스 구현 담당자가 직접 판단 (시스템_구성도_초안.md §5)
- [ ] RPi5 ↔ RPi4B Wi-Fi IP 구성(고정 IP/mDNS)

## 로컬 실행

```bash
docker compose up --build picar
curl http://localhost:8003/health
```
