"""actuation HTTP 엔드포인트 — FastAPI TestClient로 응답 형식을 확인한다(mock 경로, micro:bit 없음)."""
import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))

# picar·vision에도 src/app.py가 있다 — 경로로 적재하고 고유 이름을 준다
_spec = importlib.util.spec_from_file_location("actuation_app_http", _SRC / "app.py")
actuation_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(actuation_app)


def _client():
    return TestClient(actuation_app.app)


def test_health_reports_mock_connection():
    with _client() as client:          # startup(BLE connect)까지 — mock이면 바로 연결된 것으로 본다
        body = client.get("/health").json()
    assert body == {"status": "ok", "service": "actuation", "mock_hardware": True, "microbit_connected": True}


def test_command_maps_target_signal_to_gesture():
    cmd = {"command": "demo", "target_signal": "정지",
           "servo_angles": {"thumb": 170, "index": 170, "middle": 170, "ring": 170, "pinky": 170,
                            "wrist_rotation": 90}}
    body = _client().post("/command", json=cmd).json()
    assert body["status"] == "mocked" and body["sent"] == "G1"


def test_result_and_progress_lines():
    client = _client()
    assert client.post("/result", json={"is_correct": True}).json()["sent"] == "correct"
    assert client.post("/progress", json={"current": 2, "total": 7}).json()["sent"] == "P27"
    assert client.post("/progress", json={"current": 12, "total": 7}).json()["reason"] == "invalid_progress"


def test_button_simulate_then_read():
    client = _client()
    before = client.get("/button").json()["seq"]
    client.post("/button/simulate", json={"button": "A"})
    after = client.get("/button").json()
    assert after["seq"] == before + 1 and after["last_button"] == "A" and after["microbit_connected"] is True
