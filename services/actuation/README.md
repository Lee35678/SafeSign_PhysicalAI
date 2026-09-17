# actuation — AI Hand + picar + micro:bit (담당: 송승호)

RACI: 하드웨어·로봇동작 **R**, 파이프라인·판정로직 **A**

`document/02_설계문서_v2.md` §3·§3-2·§4·§5, `document/03_인터페이스계약서_v2.md` §5 기준 담당 범위:

- **AI Hand**: 손가락 서보 5개 + 손목 서보 1개 제어 (`shared/schemas/aihand_command.schema.json`)
- **picar**: 모터(전진/후진/정지/좌우회전) + LED(적색×2, 황색×2) 제어 (`shared/schemas/picar_command.schema.json`)
  — **RPi5가 GPIO로 직접 구동** (별도 컨트롤러/통신 프로토콜 없음, 02_설계문서_v2 §1-1)
- **micro:bit**: USB 시리얼(115200 baud)로 LED 매트릭스(O/X, 진행 표시) 송신, 버튼 입력 수신
  (`shared/schemas/microbit_protocol.md`)

## 디렉터리

- `src/aihand/` — 서보 제어. `controller.py`에 7종 서보 각도 초기값(펴짐 170°/굽힘 10°/손목중립 90°) 포함
- `src/picar/` — 모터/LED GPIO 제어 (핀 배정은 picar 실물 도착 후 확정)
- `src/microbit/` — pyserial 기반 시리얼 브릿지 (HELLO/READY 핸드셰이크, RESULT/PROGRESS 송신, BTN 수신)
- `src/app.py` — FastAPI 진입점 (`/health`, `/command`, `/picar`, `/result`, `/progress`)

## MOCK_HARDWARE 모드

로컬 PC(Windows)에는 서보/picar/micro:bit가 물리적으로 연결되어 있지 않으므로, 기본값
`MOCK_HARDWARE=true`일 때는 실제 GPIO/시리얼 호출 대신 로그만 남기고 성공 응답을 반환합니다.
하드웨어 도착 후 `MOCK_HARDWARE=false` + `devices:` 매핑(docker-compose.yml 주석 참고)으로 전환하세요.

## 실물 배포 시 참고 (10_PRD_v1.md §1.3, §4)

RPi5 한 대가 카메라 추론(vision)과 picar GPIO 구동을 모두 겸하도록 설계되었습니다. 지금은 팀 분업을
위해 vision과 actuation을 별도 컨테이너로 개발하지만, **picar 제어는 네트워크 호출이 아니라 GPIO
직접 제어**로 구현해야 하며, 실제 통합 단계에서 picar 제어 코드를 vision과 같은 프로세스/보드로
옮길지 재검토가 필요합니다.

## 아직 확정 안 된 것 (실물 테스트 필요)

- [ ] AI Hand/picar GPIO 핀 배정
- [ ] 서보 각도 초기값(170/10/90)의 실물 캘리브레이션
- [ ] picar 전원 계통 분리 여부 (모터 노이즈 영향) — picar 도착 후 이 서비스 구현 담당자가 직접 판단
      (시스템_구성도_초안.md §5, 08_리스크레지스터 참고)
- [ ] micro:bit 실제 시리얼 코드로 프로토콜 동작 검증

## 로컬 실행

```bash
docker compose up --build actuation
curl http://localhost:8002/health
```
