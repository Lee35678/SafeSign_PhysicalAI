"""picar 서비스 진입점 — **Raspberry Pi 4B 8GB(picar 차체 탑재)** 에서 실행.

담당: 송승호 (하드웨어·로봇동작 R)
역할: RPi5(vision+actuation+web)로부터 Wi-Fi(HTTP)로 picar_command를 받아 모터/LED GPIO 구동.

document/02_설계문서_v2 §1-1: picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에, picar만 이
별도 보드(RPi4B)에서 돌고 RPi5와는 네트워크로 통신한다. 같은 프로세스 내 함수 호출이 아니다.
입력 스키마: shared/schemas/picar_command.schema.json
통신 정책(타임아웃/재시도/폴백)은 호출하는 쪽(services/web)이 관리한다 — 03_인터페이스계약서_v2 §5-2, §7.
"""
import os

from fastapi import FastAPI

import controller

MOCK_HARDWARE = os.getenv("MOCK_HARDWARE", "true").lower() == "true"

app = FastAPI(title="SafeSign Picar Service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "picar", "mock_hardware": MOCK_HARDWARE}


@app.post("/picar")
def picar(picar_command: dict):
    """picar_command.schema.json 형식 입력을 받아 모터/LED 구동."""
    return controller.execute(picar_command, mock=MOCK_HARDWARE)
