"""actuation 서비스 진입점.

담당: 송승호 (하드웨어·로봇동작 R)
역할: 상태머신으로부터 AiHandCommand/PicarCommand를 받아 서보/모터·LED 구동,
micro:bit 시리얼 송수신(RESULT/PROGRESS 송신, BTN 수신).

입력 스키마: shared/schemas/aihand_command.schema.json, picar_command.schema.json
시리얼 프로토콜: shared/schemas/microbit_protocol.md

참고: 실물 배포 시 picar는 이 서비스가 아니라 vision과 같은 RPi5 프로세스에서 GPIO로 직접
구동되는 편이 지연 면에서 유리하다(02_설계문서_v2 §1-1). 지금은 팀 분업을 위해 별도 서비스로
개발하고, 실제 통합 단계에서 배치를 재검토한다 (10_PRD_v1.md §4 참고).
"""
import os

from fastapi import FastAPI

from aihand import controller as aihand_controller
from microbit import bridge as microbit_bridge
from picar import controller as picar_controller

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


@app.post("/picar")
def picar(picar_command: dict):
    """picar_command.schema.json 형식 입력을 받아 모터/LED 구동."""
    return picar_controller.execute(picar_command, mock=MOCK_HARDWARE)


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
