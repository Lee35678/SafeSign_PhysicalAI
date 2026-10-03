"""picar HTTP 엔드포인트 — FastAPI TestClient로 /health·/picar 응답 형식과 종료 처리를 확인한다(mock 경로)."""
import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))

# actuation·vision에도 src/app.py가 있다 — 경로로 적재하고 고유 이름을 준다
_spec = importlib.util.spec_from_file_location("picar_app", _SRC / "app.py")
picar_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(picar_app)

client = TestClient(picar_app.app)


def test_health_reports_mock_hardware():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["service"] == "picar" and body["mock_hardware"] is True
    assert body["hardware"]["max_speed_pct"] == 50


def test_drive_command_is_executed():
    cmd = {"command": "slow", "target_signal": "서행", "motor": {"action": "forward", "speed": 20},
           "led": {"red": "off", "yellow_left": "blink", "yellow_right": "blink"}}
    body = client.post("/picar", json=cmd).json()
    assert body["status"] == "ok"
    assert body["motor"]["status"] == "mocked" and body["motor"]["speed_pct"] == 20


def test_null_parts_return_200_not_500():
    resp = client.post("/picar", json={"command": "stop", "led": None, "motor": None})
    assert resp.status_code == 200 and resp.json()["motor"]["action"] == "stop"


def test_shutdown_hook_runs_on_exit(monkeypatch):
    """lifespan 종료에서 controller.shutdown이 불려야 주행 중 종료 때 차가 선다."""
    calls = []
    monkeypatch.setattr(picar_app.controller, "shutdown", lambda mock: calls.append(mock))
    with TestClient(picar_app.app):
        pass
    assert calls == [picar_app.MOCK_HARDWARE]
