"""perception/capture.py — 카메라·MediaPipe 없이 캡처 루프의 배선을 검증한다.

실물 CSI 카메라(picamera2)와 MediaPipe 대신 가짜를 넣어서 확인하는 것:
  · 카메라가 준 BGR 프레임이 RGB 로 바뀌어 MediaPipe 에 들어가는가 (좌우 반전 포함)
  · LIVE_STREAM 타임스탬프가 단조 증가하는가
  · 콜백 결과가 landmark_frame 형식으로 publish 되는가 (captured_at_ms 는 캡처 시각)
  · 카메라가 안 열려도 서비스가 죽지 않고 "손 없음"으로 버티며 원인을 상태에 남기는가

실행: python tests/test_capture.py
"""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from perception import capture  # noqa: E402


class FakeCamera:
    description = "가짜 카메라 4x2"

    def __init__(self, n=5):
        self.n, self.closed = n, False
        # 픽셀마다 (B,G,R) 가 다르게 — 순서가 바뀌면 바로 드러난다
        self.frame = np.zeros((2, 4, 3), dtype=np.uint8)
        for x in range(4):
            self.frame[:, x] = (10 * x + 1, 10 * x + 2, 10 * x + 3)

    def read(self):
        return self.frame.copy()

    def close(self):
        self.closed = True


def _fake_result(hand=True):
    lms = [SimpleNamespace(x=0.01 * i, y=0.02 * i, z=0.0) for i in range(21)]
    return SimpleNamespace(hand_world_landmarks=[lms] if hand else [],
                           handedness=[[SimpleNamespace(category_name="Left")]] if hand else [])


class FakeLandmarker:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def detect_async(self, image, ts_ms):
        self.calls.append((image, ts_ms))
        capture._on_result(_fake_result(), image, ts_ms)     # 실제로는 MediaPipe 스레드가 부른다


def _reset():
    capture._set_status(state="not_started", source=None, description=None, error=None,
                        frames_captured=0, results=0, capture_fps=0.0, result_fps=0.0,
                        last_frame_at_ms=None)
    capture._publish(None)


def test_frames_flow_to_landmark_frame():
    _reset()
    cam, lm = FakeCamera(), FakeLandmarker()
    capture.run_capture_loop(camera_factory=lambda: cam, landmarker_factory=lambda: lm,
                             image_factory=lambda rgb: rgb, max_frames=5)
    assert len(lm.calls) == 5
    ts = [t for _, t in lm.calls]
    assert all(b > a for a, b in zip(ts, ts[1:])), f"타임스탬프가 단조 증가하지 않음: {ts}"
    img = lm.calls[0][0]
    assert img.flags["C_CONTIGUOUS"]
    # 좌우 반전(CAMERA_MIRROR 기본 true) + BGR->RGB: 맨 왼쪽 픽셀 = 원래 맨 오른쪽 픽셀의 (R,G,B)
    b, g, r = cam.frame[0, -1]
    assert tuple(img[0, 0]) == (r, g, b), img[0, 0]
    f = capture.get_latest_landmark_frame()
    assert f["hand_detected"] and len(f["landmarks"]) == 21 and f["handedness"] == "Left"
    assert f["timestamp"] == ts[-1] and f["captured_at_ms"] > 0
    st = capture.get_status()
    assert st["state"] == "stopped" and st["frames_captured"] == 5 and st["results"] == 5
    assert cam.closed


def test_camera_failure_does_not_kill_service():
    _reset()
    stop = threading.Event()

    def broken():
        raise SystemExit("picamera2를 불러올 수 없습니다.\n  sudo apt install -y python3-picamera2")

    th = threading.Thread(target=capture.run_capture_loop, args=(stop,),
                          kwargs={"camera_factory": broken}, daemon=True)
    th.start()
    time.sleep(0.15)
    st = capture.get_status()
    f = capture.get_latest_landmark_frame()
    stop.set()
    th.join(timeout=1)
    assert st["state"] == "error" and "picamera2" in st["error"], st
    assert f is not None and f["hand_detected"] is False       # 손 없음으로 버틴다
    assert not th.is_alive()


def test_no_hand_result():
    _reset()
    capture._on_result(_fake_result(hand=False), None, 123)
    f = capture.get_latest_landmark_frame()
    assert f["hand_detected"] is False and f["landmarks"] == [] and f["timestamp"] == 123


_passed = []
for _n, _f in sorted(globals().copy().items()):
    if _n.startswith("test_") and callable(_f):
        _f()
        _passed.append(_n)
        print(f"  ok  {_n}")
print(f"{len(_passed)}개 통과")
