"""actuation 서비스 진입점 — **Raspberry Pi 5(고정 스테이션)** 에서 실행.

담당: 송승호 (하드웨어·로봇동작 R)
역할: 상태머신(web)으로부터 AiHandCommand를 받아 micro:bit에 BLE로 전달, AiHand 서보 구동.
micro:bit 하드웨어 UART가 1개뿐이라 서보 초기화 시 USB 시리얼이 죽는 제약이 실측으로 확인되어
(doc/aihand_gesture_checklist_final.md 세션 1), RPi5 <-> micro:bit 통신은 USB 시리얼이 아니라
BLE(Nordic UART Service)로 이루어진다(2026-09-21, shared/schemas/microbit_protocol.md·
document/03_인터페이스계약서_v2.md §5-3에 갱신 반영됨).

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
async def result(payload: dict):
    """판정 결과(OK/NG)를 micro:bit LED로 전달 — "correct"/"incorrect" 전송 시 LED에 O/X를 2초간 표시.

    payload 예: {"is_correct": true, "match_score": 87}

    match_score는 펌웨어가 쓰지 않는다(LED 표시는 정오답 여부만 반영) — 응답 로그·화면 표시용으로는
    web 쪽에서 별도로 활용한다.
    """
    return await ble_bridge.send_result(payload.get("is_correct", False), mock=MOCK_HARDWARE)


@app.post("/progress")
async def progress(payload: dict):
    """진행 표시(현재/전체 수신호 번호)를 micro:bit로 전달 — LED 표시는 하지 않고 수신 확인만 받는다
    (진행 표시 자체는 web 화면 쪽 담당, 2026-09-21 결정).

    payload 예: {"current": 3, "total": 7}
    """
    return await ble_bridge.send_progress(
        payload.get("current", 0), payload.get("total", 7), mock=MOCK_HARDWARE
    )
