"""POST /reset — N프레임 누적과 직전 판정을 함께 초기화하는지 (카메라·모델 없이, classify.predict만 바꿔 끼운다).

2026-10-02 지연 측정에서 확인 버튼 → 판정 확정이 8·18ms인 행이 나왔다. `/reset`이 누적만 비우고 `/latest`의
직전 판정을 남겨, web이 확인 직후 **확인 전 손모양으로 내린 판정**을 받은 것이다.

실행: python -m pytest tests/test_reset.py -q
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app  # noqa: E402
from cognition import classify, smoothing  # noqa: E402


def _ok(cls="정지"):
    return {"predicted_class": cls, "confidence": 0.95, "match_score": 90, "is_reject": False,
            "latency_ms": 40, "reason": None}


def _frame(captured_at_ms=None):
    return {"timestamp": time.monotonic_ns(), "captured_at_ms": captured_at_ms or int(time.time() * 1000) + 5}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    smoothing.reset()
    monkeypatch.setattr(app, "_latest_judgment", dict(app._latest_judgment))
    monkeypatch.setattr(classify, "predict", lambda frame: _ok())
    yield
    smoothing.reset()


def _confirm_now():
    for _ in range(smoothing.N_FRAMES):
        app._process_frame(_frame())
    assert app.latest()["is_reject"] is False


def test_reset_also_clears_latest_judgment():
    _confirm_now()
    app.reset()
    latest = app.latest()
    assert latest["is_reject"] is True
    assert latest["reason"] == "awaiting_consecutive_frames"
    assert latest["consecutive"] == 0


def test_result_of_frame_classified_across_a_reset_is_dropped(monkeypatch):
    """분류하는 사이 /reset이 오면 그 결과는 누적에도 `/latest`에도 들어가지 않는다."""
    _confirm_now()

    def predict_while_reset(frame):
        app.reset()
        return _ok()

    monkeypatch.setattr(classify, "predict", predict_while_reset)
    app._process_frame(_frame())
    assert app.latest()["is_reject"] is True
    assert smoothing.streak() == 0


def test_frame_captured_before_reset_is_not_counted():
    app.reset()
    app._process_frame(_frame(captured_at_ms=app._reset_at_ms - 10))
    assert smoothing.streak() == 0
    assert app.latest()["reason"] == "awaiting_consecutive_frames"


def test_after_reset_needs_n_fresh_frames():
    _confirm_now()
    app.reset()
    for i in range(smoothing.N_FRAMES - 1):
        app._process_frame(_frame())
        assert app.latest()["is_reject"] is True, f"{i + 1}번째 새 프레임에서 벌써 확정됐다"
    app._process_frame(_frame())
    assert app.latest()["is_reject"] is False
