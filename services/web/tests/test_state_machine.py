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
    # web 할 일 ①-a 이후 세션은 시범 단계("demo")로 시작한다 — 여기 테스트는 판정 분기를 보므로 판정 단계로 둔다.
    # ①-a 전에는 "phase" 키가 없어 아무 일도 하지 않는다(test_judging_timing_spec.py 참고).
    if "phase" in sm._session:
        sm._session["phase"] = "judging"


def _poll_until_confirmed(client, polls: int = 2) -> None:
    """오답은 같은 클래스가 WRONG_CONFIRM_S 이상 유지돼야 확정된다(①-a) — 유지 시간을 0으로 두고 두 번 본다.
    ①-a 전에는 첫 폴링에서 바로 확정되고, 두 번째는 중복 방지(_last_dispatched)로 무시된다."""
    saved = getattr(sm, "WRONG_CONFIRM_S", None)
    if saved is not None:
        sm.WRONG_CONFIRM_S = 0.0
    try:
        for _ in range(polls):
            sm._poll_once(client)
    finally:
        if saved is not None:
            sm.WRONG_CONFIRM_S = saved


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
    # 통째 비교하지 않는다 — ②-a·③에서 응답 시간·본문 status 같은 필드가 붙는다
    assert result["ok"] is True
    assert result["body"] == {"a": 1}


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
        _poll_until_confirmed(client)

    assert sm._session["curriculum_index"] == 0
    assert sm._session["last_result"]["outcome"] == "wrong"
    assert sm._session["last_result"]["message"] == "다시 시도하세요"
    picar_calls = [c for c in fake_post.call_args_list if "/picar" in c.args[0]]
    assert len(picar_calls) == 0


def test_poll_once_below_tau_vs_out_of_distribution_messages_differ():
    """03_인터페이스계약서 §4, 2026-09-22 추가 — 자세를 다듬으라는 안내(below_tau)와 다른
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


_NO_HAND = {
    "predicted_class": "negative", "confidence": 0.0, "match_score": 0,
    "is_reject": True, "latency_ms": 5, "reason": "no_hand",
}


def _enter_camera_fail(client) -> None:
    for _ in range(sm.CAMERA_FAIL_STREAK_THRESHOLD):
        sm._poll_once(client)
    assert sm._session["state"] == "camera_fail"


def _wait_demo_sent(fake_post, signal: str, timeout: float = 2.0) -> bool:
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if any(c.args[0].endswith("/command") and c.kwargs.get("json", {}).get("command") == "demo"
               and c.kwargs.get("json", {}).get("target_signal") == signal for c in fake_post.call_args_list):
            return True
        time.sleep(0.02)
    return False


def test_camera_retry_returns_to_demo_and_resends_demo():
    """2026-09-29 ⑥ 재시험 — 카메라가 계속 손을 못 잡으면 SC-04에서 못 빠져나왔다. 재시도는 판정이 아니라
    **시범 단계**로 되돌리고 현재 수신호를 다시 보여 준다(판정으로 바로 돌리면 손이 카메라 밖이라 다시 튕긴다)."""
    _reset_session("training")
    fake_post = MagicMock(return_value=_FakeResponse(200, {"status": "ok"}))
    with patch("backend.state_machine.httpx.post", fake_post):
        client = _FakeVisionClient(_NO_HAND)
        _enter_camera_fail(client)
        result = sm.camera_retry()
        assert result["status"] == "ok"
        assert sm._session["state"] == "training"
        assert sm._session["phase"] == "demo"
        assert sm._session["camera_fail_streak"] == 0
        assert _wait_demo_sent(fake_post, "정지"), "재시도 뒤 AI Hand 재시범이 없다"
    assert sm._session["attempts"].get("정지", 0) == 0, "재시도는 시도 횟수에 넣지 않는다"


def test_camera_retry_does_not_bounce_back_while_hand_is_still_away():
    """재시도 뒤 손이 아직 카메라 밖이어도(버튼을 누르느라) 시범 단계에서는 미검출을 세지 않아 SC-04로 안 돌아간다."""
    _reset_session("training")
    with patch("backend.state_machine.httpx.post", return_value=_FakeResponse(200, {"status": "ok"})):
        client = _FakeVisionClient(_NO_HAND)
        _enter_camera_fail(client)
        sm.camera_retry()
        for _ in range(sm.CAMERA_FAIL_STREAK_THRESHOLD * 2):
            sm._poll_once(client)
    assert sm._session["state"] == "training"
    assert sm._session["phase"] == "demo"


def test_no_hand_poll_racing_a_retry_does_not_reenter_camera_fail():
    """vision을 조회하는 사이 재시도로 시범 단계가 되면, 그 조회 결과(no_hand)로 다시 SC-04를 만들지 않는다."""
    _reset_session("training")
    with patch("backend.state_machine.httpx.post", return_value=_FakeResponse(200, {"status": "ok"})):
        client = _FakeVisionClient(_NO_HAND)
        _enter_camera_fail(client)

        class _RetryDuringGet(_FakeVisionClient):
            def get(self, url):
                sm.camera_retry()                  # 조회 도중 재시도가 들어온다
                return super().get(url)

        sm._poll_once(_RetryDuringGet(_NO_HAND))
    assert sm._session["state"] == "training"
    assert sm._session["phase"] == "demo"


def test_camera_retry_is_ignored_outside_camera_fail():
    _reset_session("training")
    result = sm.camera_retry()
    assert result["status"] == "ignored"
    assert sm._session["state"] == "training"
    assert sm._session["phase"] == "judging"


# ---- 판정 제한시간: below_tau/OOD만 계속 나와도 판정이 끝나야 시도 횟수 상한이 적용된다 ----

_BELOW_TAU = {
    "predicted_class": None, "confidence": 0.4, "match_score": 20,
    "is_reject": True, "latency_ms": 5, "reason": "below_tau",
}


def _start_judging_ago(seconds: float) -> None:
    import time
    sm._session["trial"]["t_judge_start"] = time.monotonic() - seconds


def test_judging_timeout_counts_as_attempt_and_redemos():
    """2026-09-29 ⑥ 재시험 — 틀린 손모양이 below_tau/OOD로만 잡히면 판정이 끝나지 않아 상한이 무의미했다.
    제한시간(기준 구현 `_listen()`과 같은 10초)을 넘기면 timeout으로 시도 1회를 세고 재시범한다."""
    _reset_session("training")
    fake_post = MagicMock(return_value=_FakeResponse(200, {"status": "ok"}))
    with patch("backend.state_machine.httpx.post", fake_post):
        client = _FakeVisionClient(_BELOW_TAU)
        _start_judging_ago(sm.JUDGING_TIMEOUT_S - 1)
        sm._poll_once(client)
        assert sm._session["last_result"]["outcome"] == "below_tau", "제한시간 전에는 안내만"
        _start_judging_ago(sm.JUDGING_TIMEOUT_S + 0.1)
        sm._poll_once(client)
    assert sm._session["last_result"]["outcome"] == "timeout"
    assert sm._session["attempts"]["정지"] == 1
    assert sm._session["phase"] == "demo"
    assert sm._session["curriculum_index"] == 0
    demos = [c for c in fake_post.call_args_list
             if c.args[0].endswith("/command") and c.kwargs["json"]["command"] == "demo"]
    assert len(demos) == 1, "timeout 뒤 재시범이 없다"


def test_correct_frame_wins_over_timeout():
    _reset_session("training")
    with patch("backend.state_machine.httpx.post", return_value=_FakeResponse(200, {"status": "ok"})):
        _start_judging_ago(sm.JUDGING_TIMEOUT_S + 5)
        sm._poll_once(_FakeVisionClient({
            "predicted_class": "정지", "confidence": 0.95, "match_score": 92,
            "is_reject": False, "latency_ms": 5,
        }))
    assert sm._session["last_result"]["outcome"] == "correct"


def test_timeouts_reach_attempt_cap_and_advance():
    """timeout도 시도로 세므로 3번째에서 재시범 없이 다음 수신호로 넘어간다 — 실물에서 '무제한'으로 보이던 경로."""
    _reset_session("training")
    fake_post = MagicMock(return_value=_FakeResponse(200, {"status": "ok"}))
    with patch("backend.state_machine.httpx.post", fake_post):
        client = _FakeVisionClient(_BELOW_TAU)
        for n in range(1, sm.MAX_ATTEMPTS_PER_SIGNAL + 1):
            sm._session["phase"] = "judging"          # 재시범을 보고 확인을 눌렀다고 가정
            _start_judging_ago(sm.JUDGING_TIMEOUT_S + 0.1)
            sm._poll_once(client)
            assert sm._session["last_result"]["attempt"] == n
    assert sm._session["last_result"]["given_up"] is True
    assert sm._session["curriculum_index"] == 1
    assert sm._session["completed"][-1]["given_up"] is True
    assert _wait_demo_sent(fake_post, "서행"), "상한 도달 뒤 다음 수신호 시범이 없다"
    demo_stop = [c for c in fake_post.call_args_list if c.args[0].endswith("/command")
                 and c.kwargs["json"].get("command") == "demo" and c.kwargs["json"].get("target_signal") == "정지"]
    assert len(demo_stop) == sm.MAX_ATTEMPTS_PER_SIGNAL - 1, "상한 도달 때는 같은 수신호를 다시 보여주지 않는다"


def test_state_exposes_max_attempts():
    """화면 '시도 n / 3' 표시용 — 실물에 새 코드가 올라갔는지 `curl /api/state`로 확인하는 데도 쓴다."""
    _reset_session("training")
    assert sm.get_state()["max_attempts"] == sm.MAX_ATTEMPTS_PER_SIGNAL


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
