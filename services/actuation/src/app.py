"""actuation 서비스 진입점.

담당: 송승호 (하드웨어·로봇동작 R)
역할: web/vision으로부터 AiHandCommand를 받아 서보 구동, micro:bit 시리얼 송수신.
입력 스키마: shared/schemas/aihand_command.schema.json
시리얼 프로토콜: shared/schemas/microbit_protocol.md
"""
import os

from fastapi import FastAPI

from aihand import controller as aihand_controller
from microbit import bridge as microbit_bridge

MOCK_HARDWARE = os.getenv("MOCK_HARDWARE", "true").lower() == "true"

app = FastAPI(title="SafeSign Actuation Service")


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
