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

- `src/controller.py` — 모터(전진/후진/정지/좌우회전) + LED(적색×2, 황색×2) GPIO 직접 제어
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

## 아직 확정 안 된 것

- [ ] GPIO 핀 배정
- [ ] picar 전원 계통 분리 여부(모터 노이즈가 RPi4B 자체 Wi-Fi 모듈에 영향 주는지) — 실물 조립 후 이 서비스 구현 담당자가 직접 판단 (시스템_구성도_초안.md §5)
- [ ] RPi5 ↔ RPi4B Wi-Fi IP 구성(고정 IP/mDNS)

## 로컬 실행

```bash
docker compose up --build picar
curl http://localhost:8003/health
```
