"""actuation 서비스 진입점 — **Raspberry Pi 5(고정 스테이션)** 에서 실행.

담당: 송승호 (하드웨어·로봇동작 R)
역할: 상태머신으로부터 AiHandCommand를 받아 서보 구동, micro:bit 시리얼 송수신
(RESULT/PROGRESS 송신, BTN 수신). AI Hand와 micro:bit는 둘 다 RPi5에 직결되어 있다.

picar는 이 서비스가 아니라 **별도 서비스(services/picar, Raspberry Pi 4B 8GB)** 에서 담당한다 —
picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에 컴퓨트 보드를 분리했다
(document/02_설계문서_v2 §1-1, 2026-09-18). 상태머신(web)이 picar_command는 이 서비스가 아니라
services/picar의 `/picar` 엔드포인트로 직접(Wi-Fi) 전송한다.

입력 스키마: shared/schemas/aihand_command.schema.json
시리얼 프로토콜: shared/schemas/microbit_protocol.md
"""
import os

from fastapi import FastAPI

from aihand import controller as aihand_controller
from microbit import bridge as microbit_bridge

MOCK_HARDWARE = os.getenv("MOCK_HARDWARE", "true").lower() == "true"

app = FastAPI(title="SafeSign Actuation Service")


@app.on_event("startup")
def _startup() -> None:
    microbit_bridge.connect(mock=MOCK_HARDWARE)


@app.get("/health")
def health():
    return {"status": "ok", "service": "actuation", "mock_hardware": MOCK_HARDWARE}


@app.post("/command")
def command(aihand_command: dict):
    """aihand_command.schema.json 형식 입력을 받아 서보 구동."""
    return aihand_controller.execute(aihand_command, mock=MOCK_HARDWARE)


@app.post("/result")
def result(payload: dict):
    """판정 결과(OK/NG + match_score)를 micro:bit LED 매트릭스로 전달.

    payload 예: {"is_correct": true, "match_score": 87}
    """
    return microbit_bridge.send_result(payload, mock=MOCK_HARDWARE)


@app.post("/progress")
def progress(payload: dict):
    """진행 표시(현재/전체 수신호 번호)를 micro:bit로 전달.

    payload 예: {"current": 3, "total": 7}
    """
    return microbit_bridge.send_progress(
        payload.get("current", 0), payload.get("total", 7), mock=MOCK_HARDWARE
    )
