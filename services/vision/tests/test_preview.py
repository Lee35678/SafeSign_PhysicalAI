"""perception/preview.py — 라이브 미리보기(MJPEG)를 카메라 없이 검증한다.

  · 프레임을 넘기면 JPEG가 나오고, 가로 STREAM_WIDTH 이하로 줄어드는가
  · 같은 프레임은 한 번만 인코딩하는가 (보는 화면이 여럿이어도 인코딩은 한 번)
  · 스트림이 multipart 조각을 내보내고, 끝나면 보는 수를 되돌리는가
  · 캡처 루프가 프레임을 미리보기에 넘기는가 (거울 반전된 프레임)

실행: python tests/test_preview.py
"""
import asyncio
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from perception import capture, preview  # noqa: E402


def _jpeg_size(jpeg: bytes) -> tuple[int, int]:
    import cv2
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    return img.shape[1], img.shape[0]


def test_frame_becomes_small_jpeg():
    preview._reset_for_tests()
    assert preview.get_jpeg() is None, "프레임이 없으면 None"
    preview.publish_frame(np.zeros((720, 1280, 3), np.uint8))
    jpeg = preview.get_jpeg()
    assert jpeg[:2] == b"\xff\xd8", "JPEG 시작 표식"
    w, h = _jpeg_size(jpeg)
    assert w <= preview.STREAM_WIDTH and (w, h) == (640, 360), (w, h)


def test_same_frame_is_encoded_once():
    preview._reset_for_tests()
    calls = []
    original = preview._enc
    preview._enc = lambda img: calls.append(1) or b"\xff\xd8x"
    try:
        preview.publish_frame(np.zeros((360, 640, 3), np.uint8))
        preview.get_jpeg()
        preview.get_jpeg()
        assert len(calls) == 1
        preview.publish_frame(np.zeros((360, 640, 3), np.uint8))
        preview.get_jpeg()
        assert len(calls) == 2
    finally:
        preview._enc = original


def test_mjpeg_stream_chunks_and_viewer_count():
    preview._reset_for_tests()
    preview.publish_frame(np.zeros((360, 640, 3), np.uint8))

    async def run():
        chunks = []
        gen = preview.mjpeg(max_frames=1)
        async for c in gen:
            assert preview.viewers() == 1
            chunks.append(c)
        return chunks

    chunks = asyncio.run(run())
    assert len(chunks) == 1 and chunks[0].startswith(b"--frame\r\nContent-Type: image/jpeg")
    assert preview.viewers() == 0, "스트림이 끝나면 보는 수를 되돌린다"


def test_capture_loop_publishes_mirrored_frame():
    preview._reset_for_tests()
    frame = np.zeros((2, 4, 3), np.uint8)
    frame[:, 0] = 200                                   # 왼쪽 끝만 밝게

    class Cam:
        description = "가짜"
        def read(self): return frame.copy()
        def close(self): pass

    class LM:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def detect_async(self, image, ts): pass

    mirror = capture.CAMERA_MIRROR
    capture.CAMERA_MIRROR = True
    try:
        capture.run_capture_loop(camera_factory=Cam, landmarker_factory=LM,
                                 image_factory=lambda rgb: rgb, max_frames=1)
    finally:
        capture.CAMERA_MIRROR = mirror
    shown = preview._frame
    assert shown is not None and shown[0, -1, 0] == 200, "미리보기는 거울 반전된 프레임이다"


if __name__ == "__main__":
    _passed = []
    for _n, _f in sorted(globals().copy().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
            _passed.append(_n)
            print(f"  ok  {_n}")
    print(f"{len(_passed)}개 통과")
