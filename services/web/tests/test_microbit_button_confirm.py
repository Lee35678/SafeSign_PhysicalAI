"""micro:bit 버튼 A를 확인 입력으로 — web 쪽 수신 (판정 타이밍 스펙 §9, 03 §5-3).

actuation `GET /button`의 누른 횟수 `seq`를 시범 단계에서만 폴링해, 기준값보다 커지면 `/api/confirm`과 같은 확인을 한다.
conftest가 버튼 폴링을 꺼 두므로 여기서만 켜고 `httpx.get`(버튼 조회)·`httpx.post`(vision `/reset`·장치)를 바꿔 끼운다.

실행:
    cd services/web && python -m pytest tests -q
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import state_machine as sm  # noqa: E402


class _Resp:
    def __init__(self, status_code: int = 200, payload=None, *, bad_json: bool = False):
        self.status_code = status_code
        self._payload = {"status": "ok"} if payload is None else payload
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


class _Button:
    """actuation `GET /button` 대역 — `seq`를 바꿔 가며 누름을 흉내 낸다. `reply`를 주면 그것을 돌려준다(또는 raise)."""

    def __init__(self, seq: int = 0):
        self.seq = seq
        self.reply = None
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, url, timeout=None, **_):
        assert url == f"{sm.ACTUATION_URL}/button"
        with self._lock:
            self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        if self.reply is not None:
            return self.reply
        return _Resp(200, {"seq": self.seq, "last_button": "A", "microbit_connected": True})


class _Posts:
    """httpx.post 대역 — vision `/reset` 호출만 센다."""

    def __init__(self):
        self.urls: list[str] = []

    def __call__(self, url, json=None, timeout=None, **_):
        self.urls.append(url)
        return _Resp()

    def resets(self) -> int:
        return sum(u == f"{sm.VISION_URL}/reset" for u in self.urls)


class _Vision:
    """`_poll_once`에 넣는 vision 대역 — 시범 단계에서는 불리면 안 된다."""

    def __init__(self):
        self.gets = 0

    def get(self, url):
        self.gets += 1
        return _Resp(200, {"predicted_class": "정지", "confidence": 0.95, "match_score": 90,
                           "is_reject": False, "latency_ms": 40, "reason": None})

    def post(self, url, **_):
        return _Resp()


@pytest.fixture
def button(monkeypatch):
    monkeypatch.setattr(sm, "BUTTON_CONFIRM_ENABLED", True)
    fake, posts = _Button(seq=3), _Posts()
    sm._session.clear()
    sm._session.update(sm._fresh_session())
    sm._session["state"] = "training"          # _fresh_session()은 phase="demo"로 시작한다
    with patch.object(sm.httpx, "get", fake), patch.object(sm.httpx, "post", posts):
        yield fake, posts


def _poll(n: int = 1, vision: "_Vision | None" = None) -> None:
    for _ in range(n):
        sm._poll_once(vision or _Vision())


def _mark_demo_shown() -> None:
    """아래 테스트들은 '시범이 이미 끝났다' 상태를 가정하고 버튼 확인의 안정 상태만 검증한다.

    실제로는 `_send_demo` 완료 시 `trial["t_demo_done"]`가 채워지고, `_poll_button`은 이 값이 없으면
    조회 자체를 하지 않는다(2026-09-29 수정 — 세션 시작 직후 시범이 아직 응답하기 전에 폴링이 먼저 돌아
    기준을 잡아버리던 회귀. 재현·회귀 방지 테스트는 `test_press_before_async_start_demo_replies_is_not_counted`)."""
    sm._session["trial"]["t_demo_done"] = 0.0


def test_first_poll_only_records_base(button):
    """시범 단계의 첫 조회는 기준값만 적는다 — 그전에 누적된 seq(3)는 확인이 아니다."""
    fake, posts = button
    _mark_demo_shown()
    _poll(3)
    assert sm._session["phase"] == "demo"
    assert sm._session["button_seq_base"] == 3
    assert posts.resets() == 0


def test_press_after_base_confirms_like_api(button):
    """기준값보다 커지면 `/api/confirm`과 같은 처리 — vision `/reset` 뒤 판정 단계."""
    fake, posts = button
    _mark_demo_shown()
    _poll()
    fake.seq = 4
    _poll()
    assert sm._session["phase"] == "judging"
    assert posts.resets() == 1
    assert sm._session["last_confirm_source"] == "microbit_button"
    assert "t_confirm" in sm._session["trial"]


def test_judging_phase_does_not_poll_button(button):
    """판정 중에는 버튼을 조회하지 않는다 — 판정 루프는 vision만 본다."""
    fake, posts = button
    sm._session["phase"] = "judging"
    vision = _Vision()
    with patch.object(sm, "_dispatch_feedback", return_value={}), \
         patch.object(sm, "_write_trial_row"), patch.object(sm, "_send_demo"):
        _poll(vision=vision)
    assert fake.calls == 0
    assert vision.gets == 1


def test_press_during_judging_does_not_leak_into_next_demo(button):
    """판정 중에 누른 입력은 다음 시범 단계의 확인이 되지 않는다 — 판정 확정 때 기준을 비운다."""
    fake, posts = button
    _mark_demo_shown()
    _poll()                                   # 기준 3
    sm._session["phase"] = "judging"
    fake.seq = 5                              # 판정 중 두 번 누름
    with patch.object(sm, "_dispatch_feedback", return_value={}), \
         patch.object(sm, "_write_trial_row"), patch.object(sm, "_send_demo"):
        _poll()                               # 정답 확정 → 다음 수신호 시범 단계 (_send_demo는 이 테스트에서 no-op)
    assert sm._session["phase"] == "demo" and sm._session["curriculum_index"] == 1
    # 정답 처리는 다음 시범을 폴링 루프 안에서 **동기로** 보내므로(§ 코드 참고) 실제로는 이 시점에
    # t_demo_done이 이미 채워져 있다 — 여기서는 _send_demo를 no-op으로 막았으니 대신 채워 재현한다.
    _mark_demo_shown()
    _poll(2)
    assert sm._session["phase"] == "demo", "판정 중 누른 입력이 확인으로 샜다"
    assert sm._session["button_seq_base"] == 5


def test_press_during_demo_motion_is_not_counted(button):
    """`_send_demo`가 폴링 루프 안에서 동기로 도는 경로(오답 재시범·정답 후 다음 신호) — 이 경로는
    같은 스레드가 응답을 기다리는 동안 폴링이 끼어들 수 없어 원래도 경합이 없었다. 시범 응답 전 폴링은
    2026-09-29 수정으로 아예 조회하지 않고, 응답 뒤에는 기존과 같이 기준을 다시 잡는다."""
    fake, posts = button
    _poll()                                   # 시범 응답 전 — 게이트에 걸려 조회 자체를 안 한다
    assert sm._session["button_seq_base"] is None
    fake.seq = 4                              # 시범 도중 누름 (조회를 안 하니 영향 없음)
    sm._send_demo("정지", sm._session["_gen"])  # 시범 응답 도착 — t_demo_done 기록
    assert sm._session["button_seq_base"] is None
    _poll()
    assert sm._session["phase"] == "demo" and sm._session["button_seq_base"] == 4
    fake.seq = 5                              # 시범을 본 뒤 누름
    _poll()
    assert sm._session["phase"] == "judging"


def test_press_before_async_start_demo_replies_is_not_counted(button):
    """2026-09-29 실물 회귀 재현 — `/api/start`(`state_machine.start()`)는 첫 시범을 **백그라운드
    스레드**로 보낸다(실측 응답 약 0.8초). 수정 전 코드는 그동안 폴링(0.2초 간격)이 먼저 기준값을
    잡아버려, 시범이 끝나기도 전에 누른 버튼이 확인으로 확정됐다(실물에서 828ms 시범 도중 눌러 재현).
    이 테스트는 그 스레드 타이밍을 실제로 재현해 회귀를 막는다."""
    fake, posts = button
    demo_started = threading.Event()
    release_demo = threading.Event()

    def gate_http_post(url, json=None, timeout=None, **_):
        # 시범(`command=="demo"`)만 붙잡는다 — 확인 처리의 vision `/reset`, 오작동 시 뒤이어 나갈 수 있는
        # 판정 피드백(`correct_pose`)은 붙잡지 않고 그대로 흘려보낸다(`posts`, 기존 fixture 계측 유지).
        if url == f"{sm.ACTUATION_URL}/command" and (json or {}).get("command") == "demo":
            demo_started.set()
            assert release_demo.wait(timeout=2), "테스트가 시범 스레드를 풀어주지 못했다"
        return posts(url, json=json, timeout=timeout)

    with patch.object(sm.httpx, "post", gate_http_post):
        t = threading.Thread(target=sm._send_demo, args=("정지", sm._session["_gen"]), daemon=True)
        t.start()
        assert demo_started.wait(timeout=1), "시범 호출이 시작되지 않았다"

        # 시범이 아직 응답하기 전 — 폴링이 여러 번 돌고 그 사이 버튼을 눌러도 확인되면 안 된다.
        # 확인 뒤에는 정확히 한 번만 더 폴링한다 — 두 번째부터는(버그가 있어 판정 단계로 잘못 넘어갔을 때)
        # 가짜 vision이 항상 "정답"을 돌려줘 다음 시범까지 연쇄로 발사되므로, 실패 지점을 흐리지 않기 위함이다.
        _poll(2)
        fake.seq = 4                          # 시범 도중 누름
        _poll()
        assert sm._session["phase"] == "demo", "시범 응답 전에 확인이 확정됐다(회귀)"
        assert sm._session["button_seq_base"] is None, "시범 응답 전에 기준을 잡았다(회귀)"

        release_demo.set()
        t.join(timeout=2)

    assert sm._session["trial"]["t_demo_done"] is not None

    # 시범이 실제로 끝난 뒤에야 폴링이 기준을 잡는다
    _poll()
    assert sm._session["phase"] == "demo" and sm._session["button_seq_base"] == 4

    fake.seq = 5                              # 시범을 본 뒤 누름
    _poll()
    assert sm._session["phase"] == "judging"


def test_seq_going_down_rebases_without_confirming(button):
    """seq가 기준보다 작으면 actuation이 재시작된 것 — 기준만 다시 잡고, 그 뒤 누름은 정상 처리."""
    fake, posts = button
    _mark_demo_shown()
    _poll()                                   # 기준 3
    fake.seq = 0                              # actuation 재시작
    _poll()
    assert sm._session["phase"] == "demo" and sm._session["button_seq_base"] == 0
    fake.seq = 1
    _poll()
    assert sm._session["phase"] == "judging"


@pytest.mark.parametrize("reply", [
    httpx.ConnectError("refused"),
    httpx.ReadTimeout("slow"),
    _Resp(500, {"detail": "boom"}),
    _Resp(200, bad_json=True),
    _Resp(200, {"no_seq": 1}),
], ids=["connect", "timeout", "http500", "not_json", "no_seq"])
def test_button_lookup_failure_is_silent(button, reply):
    """버튼은 보조 입력 — 조회 실패는 예외 없이 넘기고 시범 단계를 유지한다."""
    fake, posts = button
    _mark_demo_shown()
    fake.reply = reply
    _poll(3)
    assert sm._session["phase"] == "demo"
    assert sm._session["button_seq_base"] is None
    assert posts.resets() == 0


def test_disabled_does_not_poll(button, monkeypatch):
    fake, posts = button
    monkeypatch.setattr(sm, "BUTTON_CONFIRM_ENABLED", False)
    _poll(3)
    assert fake.calls == 0


def test_api_confirm_first_then_button_is_ignored(button):
    """스페이스바로 먼저 확인했으면 뒤이은 버튼 A는 무시 — `/reset`은 한 번만."""
    fake, posts = button
    _mark_demo_shown()
    _poll()
    assert sm.confirm()["status"] == "ok"
    fake.seq = 4
    sm._poll_button()                         # 판정 단계라 조회 없이 빠진다 (_poll_once는 vision 판정으로 가므로 직접 부름)
    assert sm._session["phase"] == "judging"
    assert fake.calls == 1
    assert posts.resets() == 1
    assert sm._session["last_confirm_source"] == "web"


def test_state_exposes_confirm_source(button):
    fake, posts = button
    _mark_demo_shown()
    _poll()
    fake.seq = 4
    _poll()
    assert sm.get_state()["last_confirm_source"] == "microbit_button"
