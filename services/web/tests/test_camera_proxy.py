"""카메라 영상 중계(backend/camera.py) 단위 테스트 — vision 없이 httpx.MockTransport로.

실행: cd services/web && python -m pytest tests/test_camera_proxy.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import camera  # noqa: E402

MJPEG = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 3\r\n\r\n\xff\xd8x\r\n"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(camera.router, prefix="/api/camera")
    return TestClient(app)


def test_stream_is_relayed_as_is():
    def handler(request):
        assert request.url.path == "/stream"
        return httpx.Response(200, stream=httpx.ByteStream(MJPEG),     # 실제 vision처럼 흘려보내는 응답
                              headers={"content-type": "multipart/x-mixed-replace; boundary=frame"})
    camera._transport = httpx.MockTransport(handler)
    try:
        r = _client().get("/api/camera/stream")
    finally:
        camera._transport = None
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert r.content == MJPEG


def test_vision_down_is_503_not_crash():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)
    camera._transport = httpx.MockTransport(handler)
    try:
        r = _client().get("/api/camera/stream")
    finally:
        camera._transport = None
    assert r.status_code == 503 and r.json()["reason"] == "vision_unreachable"
