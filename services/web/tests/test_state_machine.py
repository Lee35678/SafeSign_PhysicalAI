"""web 상태머신 단위 테스트 (vision/actuation/picar 실물·mock 서버 없이 httpx 호출만 patch).

정답/오답/below_tau/out_of_distribution 분기, SC-04(camera_fail) 임계값·자동 복귀,
2026-09-21 web_picar_통신_신뢰성_개선안.md의 4xx/5xx 실패 감지, SC-06 수료증 발급 조건을 검증한다.

실행:
    cd services/web && python -m pytest tests -q
    (pytest가 없으면) python tests/test_state_machine.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import state_machine as sm  # noqa: E402


def _reset_session(state: str = "training") -> None:
    sm._session.clear()
    sm._session.update(sm._fresh_session())
    sm._session["state"] = state


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _FakeVisionClient:
    """vision GET /latest 응답을 제어하는 테스트 더블 — httpx.Client 대신 _poll_once에 주입한다."""

    def __init__(self, judgment: dict):
        self.judgment = judgment
        self.reset_called = False

    def get(self, url):
        return _FakeResponse(200, self.judgment)

    def post(self, url):
        self.reset_called = True
        return _FakeResponse(200, {"status": "ok"})


# ---- _post_with_retry: 2026-09-21 web_picar_통신_신뢰성_개선안.md §1-1 ----

def test_post_with_retry_ok_on_2xx():
    with patch("backend.state_machine.httpx.post", return_value=_FakeResponse(200, {"a": 1})):
        result = sm._post_with_retry("http://x/y", {}, 1.0)
    assert result == {"ok": True, "body": {"a": 1}}


def test_post_with_retry_fails_on_5xx_not_silently_ok():
    """httpx.post()는 4xx/5xx에 예외를 던지지 않는다 — status_code를 직접 확인하지 않으면
    서버 오류를 성공으로 잘못 센다(개선안 §1-1이 지적한 원래 버그)."""
    with patch("backend.state_machine.httpx.post", return_value=_FakeResponse(500, {})):
        result = sm._post_with_retry("http://x/y", {}, 1.0)
    assert result["ok"] is False
    assert result["error"] == "http_500"


def test_post_with_retry_fails_on_connection_error():
    import httpx

    with patch("backend.state_machine.httpx.post", side_effect=httpx.ConnectError("boom")):
        result = sm._post_with_retry("http://x/y", {}, 1.0)
    assert result["ok"] is False
    assert result["error"] == "ConnectError"


# ---- _poll_once: 정답/오답/below_tau/out_of_distribution 분기 ----

def test_poll_once_correct_advances_curriculum_and_calls_picar():
    _reset_session("training")
    assert sm._current_target_signal() == "정지"

    fake_post = MagicMock(return_value=_FakeResponse(200, {"status": "ok"}))
    with patch("backend.state_machine.httpx.post", fake_post):
        client = _FakeVisionClient({
            "predicted_class": "정지", "confidence": 0.95, "match_score": 92,
            "is_reject": False, "latency_ms": 5,
        })
        sm._poll_once(client)

    assert sm._session["curriculum_index"] == 1
    assert sm._session["completed"] == [{"signal": "정지", "attempts": 1, "match_score": 92}]
    assert sm._session["last_result"]["outcome"] == "correct"
    assert client.reset_called is True, "정답 시 vision POST /reset을 호출해야 한다"
    picar_calls = [c for c in fake_post.call_args_list if "/picar" in c.args[0]]
    assert len(picar_calls) == 1, "정답일 때만 picar를 호출해야 한다"


def test_poll_once_wrong_does_not_advance_or_call_picar():
    _reset_session("training")
    fake_post = MagicMock(return_value=_FakeResponse(200, {"status": "ok"}))
    with patch("backend.state_machine.httpx.post", fake_post):
        client = _FakeVisionClient({
            "predicted_class": "서행", "confidence": 0.9, "match_score": 80,
            "is_reject": False, "latency_ms": 5,
        })
        sm._poll_once(client)

    assert sm._session["curriculum_index"] == 0
    assert sm._session["last_result"]["outcome"] == "wrong"
    assert sm._session["last_result"]["message"] == "다시 시도하세요"
    picar_calls = [c for c in fake_post.call_args_list if "/picar" in c.args[0]]
    assert len(picar_calls) == 0


def test_poll_once_below_tau_vs_out_of_distribution_messages_differ():
    """03_인터페이스계약서_v2 §4, 2026-09-22 추가 — 자세를 다듬으라는 안내(below_tau)와 다른
    수신호를 하고 있다는 안내(out_of_distribution)는 서로 다른 메시지를 써야 한다."""
    for reason, expected_message in (
        ("below_tau", "조금 더 정확히 해주세요"),
        ("out_of_distribution", "다른 수신호를 하고 계세요"),
    ):
        _reset_session("training")
        with patch("backend.state_machine.httpx.post", return_value=_FakeResponse(200, {})):
            client = _FakeVisionClient({
                "predicted_class": None, "confidence": 0.4, "match_score": 20,
                "is_reject": True, "latency_ms": 5, "reason": reason,
            })
            sm._poll_once(client)
        assert sm._session["last_result"]["outcome"] == reason
        assert sm._session["last_result"]["message"] == expected_message
        assert sm._session["curriculum_index"] == 0, "판정 보류는 커리큘럼을 진행시키면 안 된다"


def test_poll_once_silent_reasons_do_not_produce_overlay():
    _reset_session("training")
    with patch("backend.state_machine.httpx.post", return_value=_FakeResponse(200, {})):
        client = _FakeVisionClient({
            "predicted_class": None, "confidence": 0.0, "match_score": 0,
            "is_reject": True, "latency_ms": 5, "reason": "awaiting_consecutive_frames",
        })
        sm._poll_once(client)
    assert sm._session["last_result"] is None, "과도기 상태는 오버레이 없이 대기해야 한다"


# ---- SC-04(camera_fail): 임계값 + 자동 복귀 ----

def test_camera_fail_threshold_and_auto_recovery():
    _reset_session("training")
    no_hand = {
        "predicted_class": "negative", "confidence": 0.0, "match_score": 0,
        "is_reject": True, "latency_ms": 5, "reason": "no_hand",
    }
    with patch("backend.state_machine.httpx.post", return_value=_FakeResponse(200, {})):
        client = _FakeVisionClient(no_hand)
        for _ in range(sm.CAMERA_FAIL_STREAK_THRESHOLD - 1):
            sm._poll_once(client)
        assert sm._session["state"] == "training", "임계값 도달 전에는 SC-04로 전환하면 안 된다"

        sm._poll_once(client)
        assert sm._session["state"] == "camera_fail"

        # 손이 다시 보이면(below_tau 등 다른 reason) 자동으로 SC-03(training)으로 복귀해야 한다
        client.judgment = {
            "predicted_class": None, "confidence": 0.4, "match_score": 10,
            "is_reject": True, "latency_ms": 5, "reason": "below_tau",
        }
        sm._poll_once(client)
        assert sm._session["state"] == "training"


# ---- SC-06: 수료증 발급 조건 ----

def test_certificate_requires_all_signals_completed():
    _reset_session("training")
    sm._session["completed"] = [
        {"signal": s, "attempts": 1, "match_score": 90} for s in sm.CURRICULUM[:6]
    ]
    result = sm.issue_certificate()
    assert result["status"] == "error"
    assert sm._session["state"] == "training"

    sm._session["completed"].append({"signal": sm.CURRICULUM[6], "attempts": 1, "match_score": 90})
    result = sm.issue_certificate()
    assert result["status"] == "ok"
    assert sm._session["state"] == "certificate"
    assert sm._session["certificate_issued_at"] is not None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(tests)}개 통과")
