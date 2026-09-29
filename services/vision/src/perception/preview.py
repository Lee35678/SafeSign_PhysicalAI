"""카메라 라이브 미리보기 — 캡처 루프의 최신 프레임을 MJPEG로 내보낸다 (GET /stream).

담당: 이동혁 (2026-09-29)

web 화면은 수신호 예시 사진 대신 Camera Module 3 영상을 그대로 보여 준다(2026-09-29 회의 결정).
판정 성능(result_fps · 지연 KPI)을 건드리지 않는 것이 제일 중요해서 이렇게 나눴다.
  - 캡처 루프가 하는 일은 `publish_frame()` 한 번 — 최신 프레임의 참조를 바꿔 끼울 뿐, 복사·인코딩은 없다.
    (camera_source 는 프레임마다 새 배열을 주므로 참조만 들고 있어도 덮어써지지 않는다)
  - JPEG 인코딩은 스트림을 보는 쪽(`mjpeg()`)이 한다. 보는 화면이 없으면 인코딩도 없다.
    같은 프레임은 한 번만 인코딩해 여러 화면이 나눠 쓴다.
  - 크기·빈도를 줄인다: 가로 STREAM_WIDTH(기본 640) 이하로 건너뛰며 줄이고, 초당 STREAM_FPS(기본 15)장.

프레임은 캡처 루프가 이미 좌우 반전(CAMERA_MIRROR)한 것이라 학습자에게는 거울처럼 보인다.

환경변수
  STREAM_FPS      미리보기 최대 프레임률 (기본 15)
  STREAM_WIDTH    미리보기 최대 가로 픽셀 (기본 640)
  STREAM_QUALITY  JPEG 품질 1~100 (기본 70)
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Optional

import numpy as np

STREAM_FPS = float(os.getenv("STREAM_FPS", "15"))
STREAM_WIDTH = int(os.getenv("STREAM_WIDTH", "640"))
STREAM_QUALITY = int(os.getenv("STREAM_QUALITY", "70"))
BOUNDARY = "frame"

_lock = threading.Lock()
_frame: Optional[np.ndarray] = None      # 최신 BGR 프레임 (참조)
_seq = 0                                 # publish 할 때마다 +1
_jpeg: Optional[bytes] = None            # 마지막으로 인코딩한 JPEG
_jpeg_seq = -1
_viewers = 0
_encode_lock = threading.Lock()


def publish_frame(frame_bgr: np.ndarray) -> None:
    """캡처 루프가 프레임마다 부른다. 참조만 바꾼다."""
    global _frame, _seq
    with _lock:
        _frame = frame_bgr
        _seq += 1


def viewers() -> int:
    with _lock:
        return _viewers


def _encoder():
    """JPEG 인코더 — OpenCV(mediapipe가 함께 설치) 우선, 없으면 Pillow."""
    try:
        import cv2

        def enc(img: np.ndarray) -> bytes:
            ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), STREAM_QUALITY])
            if not ok:
                raise RuntimeError("cv2.imencode 실패")
            return buf.tobytes()
        return enc
    except ImportError:
        pass
    try:
        import io

        from PIL import Image

        def enc(img: np.ndarray) -> bytes:
            out = io.BytesIO()
            Image.fromarray(np.ascontiguousarray(img[:, :, ::-1])).save(out, "JPEG", quality=STREAM_QUALITY)
            return out.getvalue()
        return enc
    except ImportError:
        return None


_enc = _encoder()


def encoder_available() -> bool:
    return _enc is not None


def _shrink(img: np.ndarray) -> np.ndarray:
    step = max(1, -(-img.shape[1] // STREAM_WIDTH))       # 올림 나눗셈 — 1280 → 2, 1920 → 3
    return np.ascontiguousarray(img[::step, ::step])


def get_jpeg() -> Optional[bytes]:
    """최신 프레임의 JPEG. 새 프레임이 없으면 직전 것을 돌려준다. 프레임·인코더가 없으면 None."""
    global _jpeg, _jpeg_seq
    if _enc is None:
        return None
    with _lock:
        frame, seq = _frame, _seq
    if frame is None:
        return None
    with _encode_lock:
        if seq != _jpeg_seq:
            _jpeg = _enc(_shrink(frame))
            _jpeg_seq = seq
        return _jpeg


def placeholder_frame(text: str, width: int = 640, height: int = 360) -> np.ndarray:
    """카메라가 없을 때(MOCK_CAMERA · 카메라 열기 실패) 스트림에 띄울 안내 화면."""
    img = np.full((height, width, 3), (24, 16, 12), dtype=np.uint8)     # 어두운 남색 (BGR)
    try:
        import cv2
        cv2.putText(img, text, (24, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (230, 210, 200), 2, cv2.LINE_AA)
    except ImportError:
        pass
    return img


def _chunk(jpeg: bytes) -> bytes:
    return (f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n"
            .encode("ascii") + jpeg + b"\r\n")


async def mjpeg(max_frames: int = 0):
    """multipart/x-mixed-replace 본문. 접속이 끊기면(취소) finally에서 보는 수를 되돌린다."""
    global _viewers
    with _lock:
        _viewers += 1
    interval = 1.0 / max(STREAM_FPS, 0.5)
    sent_seq, sent = -1, 0
    try:
        while True:
            t0 = time.monotonic()
            with _lock:
                seq = _seq
            if seq != sent_seq:
                jpeg = await asyncio.to_thread(get_jpeg)
                if jpeg is not None:
                    yield _chunk(jpeg)
                    sent_seq, sent = seq, sent + 1
                    if max_frames and sent >= max_frames:
                        return
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - t0)))
    finally:
        with _lock:
            _viewers -= 1


def _reset_for_tests() -> None:
    global _frame, _seq, _jpeg, _jpeg_seq, _viewers
    with _lock:
        _frame, _seq, _viewers = None, 0, 0
    with _encode_lock:
        _jpeg, _jpeg_seq = None, -1
