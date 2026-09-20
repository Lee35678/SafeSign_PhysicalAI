"""actuation 서비스 진입점 — **Raspberry Pi 5(고정 스테이션)** 에서 실행.

담당: 송승호 (하드웨어·로봇동작 R)
역할: 상태머신(web)으로부터 AiHandCommand를 받아 micro:bit에 BLE로 전달, AiHand 서보 구동.
micro:bit 하드웨어 UART가 1개뿐이라 서보 초기화 시 USB 시리얼이 죽는 제약이 실측으로 확인되어
(doc/aihand_gesture_checklist_final.md 세션 1), RPi5 <-> micro:bit 통신은 USB 시리얼이 아니라
BLE(Nordic UART Service)로 이루어진다(2026-09-21, shared/schemas/microbit_protocol.md는 아직
USB 시리얼 기준으로 남아있어 갱신이 필요하다).

picar는 이 서비스가 아니라 **별도 서비스(services/picar, Raspberry Pi 4B 8GB)** 에서 담당한다 —
picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에 컴퓨트 보드를 분리했다
(document/02_설계문서_v2 §1-1, 2026-09-18). 상태머신(web)이 picar_command는 이 서비스가 아니라
services/picar의 `/picar` 엔드포인트로 직접(Wi-Fi) 전송한다.

입력 스키마: shared/schemas/aihand_command.schema.json
"""
import os

from fastapi import FastAPI

from aihand import controller as aihand_controller
from microbit import ble_bridge

MOCK_HARDWARE = os.getenv("MOCK_HARDWARE", "true").lower() == "true"

app = FastAPI(title="SafeSign Actuation Service")


@app.on_event("startup")
async def _startup() -> None:
    await ble_bridge.connect(mock=MOCK_HARDWARE)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await ble_bridge.disconnect()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "actuation",
        "mock_hardware": MOCK_HARDWARE,
        "microbit_connected": ble_bridge.is_connected(mock=MOCK_HARDWARE),
    }


@app.post("/command")
async def command(aihand_command: dict):
    """aihand_command.schema.json 형식 입력을 받아 target_signal에 대응하는 G{n} 제스처를
    micro:bit BLE로 전송한다 (target_signal <-> G{n} 매핑은 aihand/controller.py 참고)."""
    return await aihand_controller.execute(aihand_command, mock=MOCK_HARDWARE)


@app.post("/result")
def result(payload: dict):
    """판정 결과(OK/NG + match_score)를 micro:bit LED로 전달.

    payload 예: {"is_correct": true, "match_score": 87}

    TODO(송승호): 현재 운영 펌웨어(aihand_production.ts)는 "G1"~"G7" 제스처 명령만 처리하며
    RESULT 프로토콜은 아직 구현되어 있지 않다. 펌웨어에 RESULT 처리가 추가되면 ble_bridge를 통해
    실제로 전송하도록 연결한다.
    """
    if MOCK_HARDWARE:
        return {"status": "mocked", "received": payload}
    return {"status": "unsupported", "reason": "microbit firmware does not implement RESULT yet"}


@app.post("/progress")
def progress(payload: dict):
    """진행 표시(현재/전체 수신호 번호)를 micro:bit로 전달.

    payload 예: {"current": 3, "total": 7}

    TODO(송승호): /result와 동일한 이유로 PROGRESS 프로토콜도 펌웨어에 아직 없다.
    """
    if MOCK_HARDWARE:
        return {"status": "mocked", "received": payload}
    return {"status": "unsupported", "reason": "microbit firmware does not implement PROGRESS yet"}
