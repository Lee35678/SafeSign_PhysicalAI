# actuation — AI Hand + micro:bit (담당: 송승호)

RACI: 하드웨어·로봇동작 **R**, 파이프라인·판정로직 **A**

`document/02_설계문서_v1.md` §3, §5, `document/03_인터페이스계약서_v1.md` §5 기준 담당 범위:

- **AI Hand**: 손가락 서보 5개 + 손목 좌우 회전 서보 1개 제어 (`shared/schemas/aihand_command.schema.json`)
- **micro:bit**: USB 시리얼로 LED 매트릭스(O/X) 표시, 버튼(A/B) 입력 수신 (`shared/schemas/microbit_protocol.md`)

## 디렉터리

- `src/aihand/` — 서보 제어 (RPi5 GPIO/PCA9685 등, 실제 드라이버는 하드웨어 확정 후 결정)
- `src/microbit/` — pyserial 기반 시리얼 브릿지
- `src/app.py` — FastAPI 진입점 (`/health`, `/command`)

## MOCK_HARDWARE 모드

로컬 PC(Windows)에는 서보/micro:bit가 물리적으로 연결되어 있지 않으므로, 기본값
`MOCK_HARDWARE=true`일 때는 실제 GPIO/시리얼 호출 대신 로그만 남기고 성공 응답을 반환합니다.
RPi5에 실물 연결 후 `MOCK_HARDWARE=false` + `devices:` 매핑(docker-compose.yml 주석 참고)으로 전환하세요.

## 아직 확정 안 된 것 (실물 테스트 필요, 02_설계문서_v1 §4 참고)

- [ ] 최종 채택 5종 수신호별 서보 각도값 (특히 수중 OK 사인)
- [ ] micro:bit 시리얼 프로토콜 상세 (필드 구분자, 종료문자, 재전송 정책)
- [ ] 통신 두절 시 폴백 동작 (web과 협의)

## 로컬 실행

```bash
docker compose up --build actuation
curl http://localhost:8002/health
```
