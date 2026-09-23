"""Raspberry Pi Camera Module 3(CSI) -> MediaPipe HandLandmarker(LIVE_STREAM) -> LandmarkFrame.

담당: 이동혁
하드웨어: Raspberry Pi Camera Module 3, CSI 직결, RPi5 (document/02_설계문서_v2 §1-1).
실행 모드: LIVE_STREAM 비동기 콜백 — VIDEO 동기 루프 대비 캡처가 추론을 기다리지 않음
(document/05_모델카드_v3 §3-2 근거).

카메라 여는 부분은 `perception/camera_source.py`(CSI=picamera2, USB=OpenCV)를 쓴다. 촬영 도구
record_dataset.py 와 같은 코드라 **데이터를 찍은 경로와 판정하는 경로가 같다.**

환경변수
  MOCK_CAMERA      true(기본)면 실물 카메라 없이 "손 미검출" 프레임만 흘린다 — 노트북/Docker 배선 확인용.
                   RPi5 실물에서는 false.
  CAMERA_SOURCE    csi(기본) | usb | auto (auto = CSI 먼저, 안 되면 USB)
  CAMERA_INDEX     카메라 번호 (기본 0)
  CAPTURE_SIZE     캡처 해상도 (기본 1280x720)
  CAPTURE_FPS      CSI 목표 프레임률 (기본 30)
  CAMERA_MIRROR    true(기본)면 좌우 반전 — record_dataset·webcam_check 와 같게 맞춘다.
                   (joint23 특징은 거울 반전에 불변이라 판정에는 영향이 없고, handedness 표기만 맞춘다)
  CAMERA_SWAP_RB   true면 빨강/파랑 채널을 바꾼다 (색이 뒤집혀 보일 때)
  CAMERA_AUTOFOCUS false면 Camera Module 3 연속 AF 를 끈다

해상도를 03_인터페이스계약서_v2 §2 의 1920x1080@60 대신 1280x720@30 으로 두는 이유:
  같은 RPi5 에서 MediaPipe 까지 돌려야 한다. MediaPipe 는 어차피 내부에서 작게 줄여 추론하므로
  1080p 를 받아도 정확도 이득이 적고, 색 변환·복사 비용만 늘어난다(camera_source 와 같은 판단).
  계약값으로 돌리려면 CAPTURE_SIZE=1920x1080 CAPTURE_FPS=60.

카메라가 안 열리면 서비스는 죽지 않는다 — "손 미검출" 프레임을 흘리며 버티고, 원인은
`get_status()`(= GET /health 의 camera)에 남긴다.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from types import SimpleNamespace
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

MOCK_CAMERA = os.getenv("MOCK_CAMERA", "true").lower() == "true"
MODEL_PATH = os.getenv("HAND_LANDMARKER_MODEL", "models/hand_landmarker.task")

# 03_인터페이스계약서_v2 §2 확정값 (참고용 — 실제 기본값은 아래 CAPTURE_*)
CONTRACT_WIDTH, CONTRACT_HEIGHT, CONTRACT_FPS = 1920, 1080, 60

CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "csi").lower()
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
CAPTURE_SIZE = os.getenv("CAPTURE_SIZE", "1280x720")
CAPTURE_FPS = int(os.getenv("CAPTURE_FPS", "30"))
CAMERA_MIRROR = os.getenv("CAMERA_MIRROR", "true").lower() == "true"
CAMERA_SWAP_RB = os.getenv("CAMERA_SWAP_RB", "false").lower() == "true"
CAMERA_AUTOFOCUS = os.getenv("CAMERA_AUTOFOCUS", "true").lower() == "true"

_lock = threading.Lock()
_latest_landmark_frame: Optional[dict] = None

# GET /health 에 그대로 나가는 캡처 상태
_status_lock = threading.Lock()
_status: dict = {"state": "not_started", "source": None, "description": None, "error": None,
                 "frames_captured": 0, "results": 0, "capture_fps": 0.0, "result_fps": 0.0,
                 "last_frame_at_ms": None}


def get_latest_landmark_frame() -> Optional[dict]:
    """cognition 루프가 폴링하는 최신 LandmarkFrame (스레드-세이프)."""
    with _lock:
        return _latest_landmark_frame


def get_status() -> dict:
    """캡처 상태 요약 — 카메라가 실제로 돌고 있는지, 몇 fps 인지, 왜 멈췄는지."""
    with _status_lock:
        s = dict(_status)
    if s["last_frame_at_ms"]:
        s["last_frame_age_ms"] = int(time.time() * 1000) - s["last_frame_at_ms"]
    return s


def _set_status(**kw) -> None:
    with _status_lock:
        _status.update(kw)


def _publish(frame: dict) -> None:
    global _latest_landmark_frame
    with _lock:
        _latest_landmark_frame = frame


def _on_result(result, output_image, timestamp_ms: int) -> None:
    """HandLandmarker LIVE_STREAM 콜백 — mediapipe가 내부 스레드에서 호출한다.

    landmark_frame.schema.json 형식으로 변환해 최신 프레임으로 publish한다.
    - `hand_world_landmarks`(실세계 3D) 사용: 카메라 거리 변화에 강함 (05_모델카드_v3 §3-4)
    - `handedness`: 정규화 단계의 좌우 손 통일(미러링)에 필요 (§3-5 4번)
    - `captured_at_ms`: 판정 지연(P95 ≤ 1.0초) 측정을 위한 벽시계 기준 캡처 시각
    """
    world = getattr(result, "hand_world_landmarks", None) or []
    handedness_list = getattr(result, "handedness", None) or []

    hand_detected = len(world) > 0
    landmarks = []
    handedness = "Right"
    if hand_detected:
        landmarks = [
            {"id": i, "x": float(lm.x), "y": float(lm.y), "z": float(lm.z)}
            for i, lm in enumerate(world[0])
        ]
        if handedness_list:
            # mediapipe Category 리스트: [[Category(category_name='Right', score=0.99)]]
            first = handedness_list[0]
            category = first[0] if isinstance(first, (list, tuple)) else first
            handedness = getattr(category, "category_name", None) or getattr(
                category, "display_name", "Right"
            )

    now_ms = int(time.time() * 1000)
    _publish(
        {
            "timestamp": int(timestamp_ms),
            "captured_at_ms": _pop_capture_time(int(timestamp_ms), now_ms),
            "hand_detected": hand_detected,
            "handedness": handedness,
            "landmarks": landmarks,
        }
    )
    with _status_lock:
        _status["results"] += 1


# detect_async 에 넘긴 시각(ts) -> 실제 캡처 벽시계 시각. 콜백은 추론이 끝난 뒤에 오므로,
# 콜백 시점의 시각을 쓰면 판정 지연에서 MediaPipe 추론 시간이 빠진다.
_capture_times: dict[int, int] = {}
_ct_lock = threading.Lock()         # 캡처 루프와 MediaPipe 콜백 스레드가 함께 쓴다


def _pop_capture_time(ts_ms: int, default: int) -> int:
    with _ct_lock:
        return _capture_times.pop(ts_ms, default)


def _remember_capture_time(ts_ms: int, wall_ms: int) -> None:
    with _ct_lock:
        _capture_times[ts_ms] = wall_ms
        if len(_capture_times) > 256:   # 추론이 밀려 버려진 프레임의 기록이 쌓이지 않게
            for k in sorted(_capture_times)[:-128]:
                del _capture_times[k]


def _build_landmarker():
    """mediapipe Tasks API HandLandmarker를 LIVE_STREAM 모드로 구성."""
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        HandLandmarker,
        HandLandmarkerOptions,
        RunningMode,
    )

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=RunningMode.LIVE_STREAM,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        result_callback=_on_result,
    )
    return HandLandmarker.create_from_options(options)


def _to_mp_image(rgb: np.ndarray):
    import mediapipe as mp

    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


def _open_camera():
    """환경변수 설정으로 camera_source 의 카메라를 연다."""
    from perception.camera_source import open_camera

    args = SimpleNamespace(source=CAMERA_SOURCE, camera=CAMERA_INDEX, size=CAPTURE_SIZE,
                           fps=CAPTURE_FPS, swap_rb=CAMERA_SWAP_RB,
                           no_autofocus=not CAMERA_AUTOFOCUS)
    return open_camera(args)


def _run_mock_loop(reason: str, stop: Optional[threading.Event] = None) -> None:
    """실물 카메라 없이 "손 미검출" 프레임만 흘려보낸다 (배선 검증용 · 카메라 실패 시 버티기용)."""
    logger.warning("카메라 없이 동작합니다(손 미검출 프레임만 발행) — %s", reason)
    timestamp_ms = 0
    interval = 1 / 30
    while stop is None or not stop.is_set():
        _publish(
            {
                "timestamp": timestamp_ms,
                "captured_at_ms": int(time.time() * 1000),
                "hand_detected": False,
                "handedness": "Right",
                "landmarks": [],
            }
        )
        timestamp_ms += int(interval * 1000)
        time.sleep(interval)


def run_capture_loop(stop: Optional[threading.Event] = None, *,
                     camera_factory: Callable = None, landmarker_factory: Callable = None,
                     image_factory: Callable = None, max_frames: int = 0) -> None:
    """카메라 캡처 + MediaPipe LIVE_STREAM 전달 루프. app.py가 백그라운드 스레드로 실행한다.

    ⚠️ 프레임 타임스탬프는 반드시 단조 증가해야 한다 (LIVE_STREAM 요구사항, 05_모델카드_v3 §3-2).

    LIVE_STREAM 은 추론이 밀리면 들어온 프레임을 스스로 버린다(flow limit). 그래서 캡처를 추론
    속도에 맞춰 늦출 필요가 없고, 카메라는 제 속도로 돌린다. 실제 추론 속도는 get_status() 의
    result_fps 로 본다 — 판정 지연 P95 ≤ 1.0초(01_프로젝트계획서_v4)가 안 나오면 여기부터 점검.

    camera_factory / landmarker_factory / image_factory / max_frames 는 테스트용이다.
    """
    if MOCK_CAMERA and camera_factory is None:
        _set_status(state="mock", source="mock", description="MOCK_CAMERA=true")
        _run_mock_loop("MOCK_CAMERA=true — RPi5 실물에서는 MOCK_CAMERA=false 로 실행하세요", stop)
        return

    _set_status(state="starting", source=CAMERA_SOURCE)
    try:
        camera = (camera_factory or _open_camera)()
    except (SystemExit, Exception) as exc:      # noqa: BLE001 - 카메라 실패로 서비스가 죽으면 안 된다
        msg = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        logger.error("카메라를 열지 못했습니다 (%s): %s", CAMERA_SOURCE, msg)
        _set_status(state="error", error=f"카메라 열기 실패: {msg}")
        _run_mock_loop(f"카메라 열기 실패: {msg}", stop)
        return
    _set_status(state="running", description=getattr(camera, "description", str(camera)),
                error=None)
    logger.info("카메라: %s", getattr(camera, "description", camera))

    make_image = image_factory or _to_mp_image
    last_ts_ms = 0
    misses = 0
    n, t0 = 0, time.perf_counter()
    r0 = 0
    try:
        with (landmarker_factory or _build_landmarker)() as landmarker:
            while stop is None or not stop.is_set():
                frame_bgr = camera.read()
                if frame_bgr is None:
                    misses += 1
                    if misses >= 30:            # 약 1초 넘게 못 읽으면 상태에 남긴다
                        _set_status(state="error", error="카메라 프레임을 읽지 못함 (30회 연속)")
                    time.sleep(0.03)
                    continue
                if misses:
                    _set_status(state="running", error=None)
                misses = 0

                if CAMERA_MIRROR:
                    frame_bgr = frame_bgr[:, ::-1]
                # MediaPipe 는 RGB 를 받는다. camera_source 는 CSI·USB 모두 BGR 을 준다.
                rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])

                ts_ms = max(int(time.monotonic() * 1000), last_ts_ms + 1)
                last_ts_ms = ts_ms
                wall_ms = int(time.time() * 1000)
                _remember_capture_time(ts_ms, wall_ms)
                landmarker.detect_async(make_image(rgb), ts_ms)

                n += 1
                with _status_lock:
                    _status["frames_captured"] += 1
                    _status["last_frame_at_ms"] = wall_ms
                dt = time.perf_counter() - t0
                if dt >= 2.0:
                    with _status_lock:
                        results = _status["results"]
                        _status["capture_fps"] = round(n / dt, 1)
                        _status["result_fps"] = round((results - r0) / dt, 1)
                    n, t0, r0 = 0, time.perf_counter(), results
                if max_frames and _status["frames_captured"] >= max_frames:
                    break
    except Exception as exc:      # noqa: BLE001
        logger.exception("캡처 루프가 멈췄습니다")
        _set_status(state="error", error=f"캡처 루프 중단: {exc}")
        raise
    finally:
        try:
            camera.close()
        except Exception:        # noqa: BLE001
            pass
        if _status.get("state") == "running":
            _set_status(state="stopped")
