"""호환용 — 실제 구현은 `src/perception/camera_source.py` 로 옮겼다.

서비스(`perception/capture.py`)도 같은 카메라 계층을 써야 해서 `src/` 안으로 옮겼다
(Docker 이미지에는 `src/` 만 들어간다). 기존 도구(record_dataset.py 등)가
`from camera_source import ...` 로 부르던 것은 이 파일 덕분에 그대로 동작한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from perception.camera_source import *  # noqa: E402,F401,F403
from perception.camera_source import (  # noqa: E402,F401  — 밑줄 없는 이름을 명시적으로도 내보낸다
    DEFAULT_FPS, DEFAULT_SIZE, CsiCamera, UsbCamera, add_camera_args, has_display, list_cameras,
    open_camera, parse_size,
)
