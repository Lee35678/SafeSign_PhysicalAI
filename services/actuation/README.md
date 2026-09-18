# actuation — AI Hand + micro:bit (담당: 송승호)

RACI: 하드웨어·로봇동작 **R**, 파이프라인·판정로직 **A**

> **이 서비스는 Raspberry Pi 5(카메라·AI Hand·micro:bit 고정 스테이션)에서 실행됩니다.**
> picar는 더 이상 이 서비스가 담당하지 않습니다 — 별도 서비스 [`services/picar`](../picar/README.md)가
> **Raspberry Pi 4B 8GB**에서 담당합니다 (2026-09-18, picar가 카메라와 함께 움직이는 문제 해결).

`document/02_설계문서_v2.md` §1-1·§3, `document/03_인터페이스계약서_v2.md` §5-1·§5-3 기준 담당 범위:

- **AI Hand**: 손가락 서보 5개 + 손목 서보 1개 제어 (`shared/schemas/aihand_command.schema.json`)
- **micro:bitv2**: USB 시리얼(115200 baud)로 LED 매트릭스(O/X, 진행 표시) 송신, 버튼 입력 수신
  (`shared/schemas/microbit_protocol.md`)

## 디렉터리

- `src/aihand/` — 서보 제어. `controller.py`에 7종 서보 각도 초기값(펴짐 170°/굽힘 10°/손목중립 90°) 포함
- `src/microbit/` — pyserial 기반 시리얼 브릿지 (HELLO/READY 핸드셰이크, RESULT/PROGRESS 송신, BTN 수신)
- `src/app.py` — FastAPI 진입점 (`/health`, `/command`, `/result`, `/progress`)

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

- [ ] AI Hand GPIO 핀 배정 및 연결 방식
- [ ] 서보 각도 초기값(170/10/90)의 실물 캘리브레이션
- [ ] micro:bit 실제 시리얼 코드로 프로토콜 동작 검증

## 로컬 실행

```bash
docker compose up --build actuation
curl http://localhost:8002/health



```
