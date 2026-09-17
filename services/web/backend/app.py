"""web 서비스 진입점.

담당: 조은수 (웹 R, 성능측정 R)
역할: 09_화면목록_v2.md의 SC-01~SC-07 흐름을 담당하는 교육 상태머신 + 프론트엔드 서빙.
vision(GET /latest), actuation(POST /command, /picar, /result, /progress) 서비스를 httpx로 호출.
관리자/등록 관련 라우트 없음 — 수신호 등록 기능은 범위에서 제외됨 (03_인터페이스계약서_v2 §6).
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.state_machine import router as state_machine_router

VISION_URL = os.getenv("VISION_URL", "http://localhost:8001")
ACTUATION_URL = os.getenv("ACTUATION_URL", "http://localhost:8002")

app = FastAPI(title="SafeSign Web Service")
app.include_router(state_machine_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "web"}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
