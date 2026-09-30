"""카메라 라이브 영상 중계 — vision `GET /stream`(MJPEG)을 web 주소로 그대로 흘려보낸다.

담당: 이동혁 (2026-09-29)

학습 화면은 수신호 예시 사진 대신 Camera Module 3 영상을 보여 준다(2026-09-29 회의 결정).
브라우저가 vision에 직접 붙지 않고 web을 거치는 이유: 화면은 교육장 PC 브라우저에서 열리는데 VISION_URL은
RPi5 기준 주소(기본 localhost:8001)라 브라우저에서는 닿지 않는다. 같은 출처(`/api/camera/stream`)로 두면
주소·포트·CORS를 신경 쓸 필요가 없다. 바이트를 옮기기만 하므로 web에는 인코딩 부담이 없다.
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()

VISION_URL = os.getenv("VISION_URL", "http://localhost:8001")
CONNECT_TIMEOUT_S = 3.0
_transport = None       # 테스트용 (httpx.MockTransport)


@router.get("/stream")
async def camera_stream():
    client = httpx.AsyncClient(timeout=httpx.Timeout(CONNECT_TIMEOUT_S, read=None), transport=_transport)
    try:
        resp = await client.send(client.build_request("GET", f"{VISION_URL}/stream"), stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        return JSONResponse({"status": "error", "reason": "vision_unreachable", "detail": type(exc).__name__},
                            status_code=503)
    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        return JSONResponse({"status": "error", "reason": f"vision_http_{resp.status_code}"}, status_code=503)

    async def body():
        try:
            async for chunk in resp.aiter_raw():
                yield chunk
        except httpx.HTTPError:
            return          # vision이 끊김 — 화면 쪽 <img>가 onerror로 다시 붙는다
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(body(), media_type=resp.headers.get("content-type", "multipart/x-mixed-replace"),
                             headers={"Cache-Control": "no-store"})
