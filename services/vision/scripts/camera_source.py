"""카메라 캡처 계층 — CSI(picamera2)와 USB 웹캠(OpenCV)을 같은 얼굴로 감싼다.

담당: 이동혁 (vision)

`scripts/`의 도구들(record_dataset.py 등)이 노트북 웹캠과 RPi5의 Camera Module 3 양쪽에서
그대로 돌아가도록, 카메라를 여는 부분만 여기로 모았다. 어느 쪽이든 `read()`가 **BGR ndarray**를
돌려주므로 호출부는 차이를 몰라도 된다.

왜 CSI는 따로 다뤄야 하는가:
    Camera Module 3는 libcamera 스택이라 `/dev/video0`에 raw Bayer로만 올라온다.
    `cv2.VideoCapture`로는 디코딩이 안 되므로 picamera2(Picamera2)로 받아야 한다.

RPi5 준비 (최초 1회):
    sudo apt install -y python3-picamera2 fonts-nanum
    # picamera2는 libcamera에 의존하는 apt 패키지라 pip로 설치되지 않는다
    python -m venv --system-site-packages .venv
    source .venv/bin/activate
    pip install -r requirements-dev.txt
"""
from __future__ import annotations

import os
import sys
from typing import Optional, Tuple

import numpy as np

# 03_인터페이스계약서_v2 §2의 운영값은 1920x1080/60fps지만, 확인·촬영 도구는 같은 보드에서
# MediaPipe까지 돌리므로 기본을 낮춰 잡는다. 운영 해상도로 보려면 --size 1920x1080.
DEFAULT_SIZE = (1280, 720)
DEFAULT_FPS = 30


class CsiCamera:
    """Camera Module 3 (CSI) → picamera2 → BGR 프레임."""

    device_tag = "rpi5_csi_module3"      # 데이터셋 source.device 에 남는 값

    def __init__(self, size: Tuple[int, int], fps: int = DEFAULT_FPS, camera_num: int = 0,
                 swap_rb: bool = False, autofocus: bool = True) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise SystemExit(
                "picamera2를 불러올 수 없습니다. CSI 카메라에는 이 패키지가 필요합니다.\n"
                "  sudo apt install -y python3-picamera2\n"
                "  가상환경이라면 `python -m venv --system-site-packages .venv` 로 다시 만드세요\n"
                "  (pip로는 설치되지 않습니다. USB 웹캠으로 쓰려면 --source usb)"
            ) from exc

        self._swap_rb = swap_rb
        self._picam = Picamera2(camera_num)
        frame_us = int(1_000_000 / max(1, fps))
        config = self._picam.create_video_configuration(
            main={"size": size, "format": "RGB888"},
            controls={"FrameDurationLimits": (frame_us, frame_us)},
        )
        self._picam.configure(config)
        self._picam.start()
        if autofocus:
            self._enable_autofocus()

        actual = tuple(self._picam.camera_configuration()["main"]["size"])
        self.description = f"CSI {camera_num}번 (picamera2)  {actual[0]}x{actual[1]}  목표 {fps}fps"

    def _enable_autofocus(self) -> None:
        """AF는 Camera Module 3에만 있다 — 없는 모듈(예: v2)에서는 조용히 넘어간다."""
        try:
            from libcamera import controls as libcamera_controls

            self._picam.set_controls({"AfMode": libcamera_controls.AfMode.Continuous})
        except Exception:      # noqa: BLE001 - AF 미지원은 실패가 아니다
            pass

    def read(self) -> Optional[np.ndarray]:
        # format="RGB888"로 요청하면 메모리상 채널 순서는 BGR로 온다(picamera2의 알려진 규약).
        # 그래서 OpenCV에 그대로 넘길 수 있다. 빨강/파랑이 뒤집혀 보이면 swap_rb=True.
        arr = self._picam.capture_array()
        if arr is None:
            return None
        if arr.ndim == 3 and arr.shape[2] == 4:      # XRGB로 떨어지는 경우 알파 제거
            arr = arr[:, :, :3]
        if self._swap_rb:
            # 음수 스트라이드 뷰는 OpenCV가 거부하므로 연속 배열로 복사한다
            arr = np.ascontiguousarray(arr[:, :, ::-1])
        return arr

    def close(self) -> None:
        try:
            self._picam.stop()
        finally:
            self._picam.close()


class UsbCamera:
    """USB/내장 웹캠 → OpenCV VideoCapture → BGR 프레임."""

    device_tag = "laptop_webcam"         # 기존에 모은 데이터와 값을 맞춰 둔다

    def __init__(self, index: int = 0, size: Optional[Tuple[int, int]] = None) -> None:
        import cv2

        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2
        self._cap = cv2.VideoCapture(index, backend)
        if not self._cap.isOpened():
            raise SystemExit(
                f"USB 카메라 {index}번을 열 수 없습니다. --list-cameras 로 인덱스를 확인하거나, "
                "다른 앱이 카메라를 점유 중인지 확인하세요."
            )
        if size:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.description = f"USB {index}번 (OpenCV)  {w}x{h}"

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        self._cap.release()


def parse_size(text: str) -> Tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise SystemExit(f"--size 형식이 잘못됐습니다: {text!r} (예: 1280x720)")


def add_camera_args(parser, default_source: str = "usb") -> None:
    """캡처 관련 공통 인자. 호출부는 그대로 `open_camera(args)`에 넘기면 된다."""
    parser.add_argument("--source", choices=("csi", "usb", "auto"), default=default_source,
                        help=f"캡처 경로 (기본 {default_source}). "
                             "csi=Camera Module 3, auto=CSI 실패 시 USB로 폴백")
    parser.add_argument("--camera", type=int, default=0, help="카메라 번호/인덱스 (기본 0)")
    parser.add_argument("--size", default=f"{DEFAULT_SIZE[0]}x{DEFAULT_SIZE[1]}",
                        help=f"캡처 해상도 (기본 {DEFAULT_SIZE[0]}x{DEFAULT_SIZE[1]})")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="CSI 목표 프레임률 (기본 30)")
    parser.add_argument("--swap-rb", action="store_true",
                        help="화면의 빨강/파랑이 뒤집혀 보일 때 채널 순서를 바꾼다")
    parser.add_argument("--no-autofocus", action="store_true",
                        help="Camera Module 3 연속 AF 끄기 (초점이 계속 움직여 거슬릴 때)")
    parser.add_argument("--list-cameras", action="store_true",
                        help="잡히는 카메라(CSI/USB)만 확인하고 종료")


def open_camera(args) -> "CsiCamera | UsbCamera":
    size = parse_size(args.size)
    if args.source == "usb":
        return UsbCamera(args.camera, size)
    if args.source == "csi":
        return CsiCamera(size, args.fps, args.camera, args.swap_rb, not args.no_autofocus)
    # auto: CSI 먼저, 안 되면 USB로 폴백
    try:
        return CsiCamera(size, args.fps, args.camera, args.swap_rb, not args.no_autofocus)
    except (SystemExit, RuntimeError, IndexError) as exc:
        first_line = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        print(f"[auto] CSI 카메라를 열지 못해 USB로 넘어갑니다: {first_line}")
        return UsbCamera(args.camera, size)


def list_cameras(max_index: int = 5) -> None:
    print("CSI 카메라 (picamera2):")
    try:
        from picamera2 import Picamera2

        infos = Picamera2.global_camera_info()
        if infos:
            for i, cam in enumerate(infos):
                print(f"  --source csi --camera {i}   {cam.get('Model', '?')}  ({cam.get('Id', '')})")
        else:
            print("  잡히는 CSI 카메라가 없습니다. 케이블 방향과 `rpicam-hello`를 먼저 확인하세요.")
    except ImportError:
        print("  picamera2가 설치되어 있지 않습니다 (sudo apt install -y python3-picamera2).")
    except Exception as exc:      # noqa: BLE001 - 진단 출력이므로 원인만 보여주고 계속한다
        print(f"  조회 실패: {exc}")

    print("USB 카메라 (OpenCV):")
    try:
        import cv2
    except ImportError:
        print("  opencv-python이 설치되어 있지 않습니다.")
        return
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2
    found = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, backend)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                found.append((idx, frame.shape[1], frame.shape[0]))
        cap.release()
    if found:
        for idx, w, h in found:
            print(f"  --source usb --camera {idx}   ({w}x{h})")
    else:
        print("  열리는 USB 카메라가 없습니다.")
    print("  ※ CSI 카메라는 이 목록에 안 잡히는 게 정상입니다 (raw Bayer라 OpenCV가 못 읽는다).")


def has_display() -> bool:
    """창을 띄울 수 있는 환경인지. SSH로 붙은 RPi5에서는 False."""
    if sys.platform == "win32" or sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
