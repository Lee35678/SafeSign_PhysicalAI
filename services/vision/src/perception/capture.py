"""Raspberry Pi Camera Module 3(CSI) -> MediaPipe HandLandmarker(LIVE_STREAM) -> LandmarkFrame.

담당: 이동혁
하드웨어: Raspberry Pi Camera Module 3, CSI 직결 (document/02_설계문서_v2 §1-1).
실행 모드: LIVE_STREAM 비동기 콜백 채택 — VIDEO 동기 루프 대비 캡처가 추론을 기다리지 않음
(document/05_모델카드_v3 §3-2 근거).

로컬 개발 PC(비-RPi)에는 picamera2를 설치할 수 없으므로, MOCK_CAMERA=true(기본값)일 때는
실물 카메라 없이 파이프라인 배선만 검증합니다. 실물 카메라는 아직 도착 전입니다(2026-09-18 기준).
"""
import os
import threading
import time
from typing import Optional

MOCK_CAMERA = os.getenv("MOCK_CAMERA", "true").lower() == "true"
MODEL_PATH = os.getenv("HAND_LANDMARKER_MODEL", "models/hand_landmarker.task")

# 03_인터페이스계약서_v2 §2 확정값
CAPTURE_WIDTH = 1920
CAPTURE_HEIGHT = 1080
CAPTURE_FPS = 60  # Binned Mode

_lock = threading.Lock()
_latest_landmark_frame: Optional[dict] = None


def get_latest_landmark_frame() -> Optional[dict]:
    """cognition 루프가 폴링하는 최신 LandmarkFrame (스레드-세이프)."""
    with _lock:
        return _latest_landmark_frame


def _on_result(result, output_image, timestamp_ms: int) -> None:
    """HandLandmarker LIVE_STREAM 콜백 — mediapipe가 내부 스레드에서 호출한다.

    TODO(이동혁): 실물 연동 시 아래를 mediapipe 실제 result 객체 필드로 채우기
    - result.hand_landmarks / result.hand_world_landmarks (world 좌표 채택, §3-4)
    - result.handedness (좌우 손 판별 -> normalize.py의 좌우 반전에 사용)
    """
    global _latest_landmark_frame
    hand_detected = bool(getattr(result, "hand_world_landmarks", None))
    landmarks = []
    if hand_detected:
        world = result.hand_world_landmarks[0]
        landmarks = [{"id": i, "x": lm.x, "y": lm.y, "z": lm.z} for i, lm in enumerate(world)]
    frame = {"timestamp": timestamp_ms, "hand_detected": hand_detected, "landmarks": landmarks}
    with _lock:
        _latest_landmark_frame = frame


def _build_landmarker():
    """mediapipe Tasks API HandLandmarker를 LIVE_STREAM 모드로 구성.

    TODO(이동혁): hand_landmarker.task 모델 파일을 실제로 받아 MODEL_PATH에 배치
    (05_모델카드_v3 §1 다운로드 URL 참고).
    """
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

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


def run_capture_loop() -> None:
    """카메라 캡처 + MediaPipe LIVE_STREAM 전달 루프. app.py가 백그라운드 스레드로 실행한다.

    ⚠️ 프레임 타임스탬프는 반드시 단조 증가해야 한다 (LIVE_STREAM 요구사항, 05_모델카드_v3 §3-2).

    TODO(이동혁, 카메라 도착 후):
    - MOCK_CAMERA=false 분기에서 picamera2로 Camera Module 3 캡처
      (`from picamera2 import Picamera2`, Raspberry Pi OS의 apt 패키지 `python3-picamera2` 필요 —
      일반 pip으로 설치되지 않으므로 requirements.txt에 포함하지 않음, README 참고)
    - 캡처한 프레임을 mediapipe.Image로 감싸 `landmarker.detect_async(mp_image, timestamp_ms)` 호출
    - 1080p@60fps 원본을 그대로 추론에 넣지 말고, 처리 가능한 속도로 서브샘플링/축소 권장
      (03_인터페이스계약서_v2 §2 실무 참고)
    """
    landmarker = _build_landmarker()
    timestamp_ms = 0
    frame_interval_s = 1 / CAPTURE_FPS
    try:
        while True:
            if MOCK_CAMERA:
                time.sleep(frame_interval_s)
                # 목업 모드: 손 미검출 상태로 배선만 유지 (실물 연동 전까지 이대로 둠)
                with _lock:
                    global _latest_landmark_frame
                    _latest_landmark_frame = {
                        "timestamp": timestamp_ms,
                        "hand_detected": False,
                        "landmarks": [],
                    }
            else:
                raise NotImplementedError(
                    "picamera2 연동 미구현 — 카메라(Pi Camera Module 3) 도착 후 구현 "
                    "(services/vision/README.md 참고)"
                )
            timestamp_ms += int(frame_interval_s * 1000)
    finally:
        landmarker.close()
