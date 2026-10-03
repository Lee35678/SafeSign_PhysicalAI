"""vision HTTP 엔드포인트 — FastAPI TestClient로 /health·/latest·/predict 응답 형식을 확인한다.

startup(카메라·판정 스레드)은 띄우지 않는다 — `with TestClient(...)`를 쓰지 않으면 시작 이벤트가 돌지 않는다.
"""
import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))

# actuation·picar에도 src/app.py가 있다 — 경로로 적재하고 고유 이름을 준다
_spec = importlib.util.spec_from_file_location("vision_app_http", _SRC / "app.py")
vision_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vision_app)

client = TestClient(vision_app.app)


def test_health_reports_judging_rule_and_model_state():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["service"] == "vision"
    assert isinstance(body["tau"], float) and isinstance(body["n_frames"], int)
    assert "loaded" in body["model"] and "camera" in body


def test_latest_has_the_judgment_fields():
    body = client.get("/latest").json()
    assert {"predicted_class", "is_reject", "reason"} <= set(body)


def test_predict_without_a_hand_is_a_reject():
    body = client.post("/predict", json={"hand_detected": False}).json()
    assert body["is_reject"] is True
