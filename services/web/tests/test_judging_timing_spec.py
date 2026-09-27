"""web 할 일 ①-a·②-a·③ 인수 테스트 — 구현보다 먼저 스펙을 테스트로 고정해 둔다 (web 할 일 ⑪, 2026-09-28).

기준 문서:
    ①-a 판정 타이밍  document/proposals/web_판정_타이밍_스펙.md §4.1·§6
    ②-a 시행 로그    같은 스펙 §7
    ③  응답 판정     document/03_인터페이스계약서.md §5-5
    테스트가 기대하는 이름(구현 계약)은 같은 스펙 §8에 적어 두었다.

**아직 구현 전이라 각 묶음은 "예상된 실패(xfail)"로 표시된다.** 구현되면 아래 `*_READY` 감지가 참이 되어
**자동으로 실제 테스트가 된다** — 마커를 손으로 지울 필요가 없다. 반대로 구현 전인데 통과하는 테스트는
strict xfail이라 실패로 드러난다(아무것도 검사하지 않는 테스트를 막기 위함).

기존 test_state_machine.py처럼 httpx 호출만 바꿔 끼우고, 내부 함수 이름 대신 `_poll_once`·`/api/*`·세션 값으로
동작을 확인한다. pytest 전용(fixture·marker 사용).

실행:
    cd services/web && python -m pytest tests -q -rxX
"""
from __future__ import annotations

import copy
import csv
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import state_machine as sm  # noqa: E402


# ── 테스트 더블 ────────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, status_code: int = 200, payload=None):
        self.status_code = status_code
        self._payload = {"status": "ok"} if payload is None else payload

    def json(self):
        return self._payload


class _Devices:
    """httpx.post 대역 — 호출을 기록하고, URL 끝부분별로 응답(또는 예외)을 돌려준다.

    web의 판정 뒤 호출은 백그라운드 스레드에서 올 수 있어(스펙 §4.1 권장) 기록은 락으로 보호한다.
    """

    def __init__(self, **by_suffix):
        self.by_suffix = by_suffix     # 예: picar=_Resp(200, {"status": "partial"}), command=httpx.ReadTimeout("t")
        self.calls: list[tuple[str, dict]] = []
        self._lock = threading.Lock()

    def __call__(self, url, json=None, timeout=None, **_):
        with self._lock:
            self.calls.append((url, json or {}))
        for suffix, reply in self.by_suffix.items():
            if url.endswith("/" + suffix):
                if isinstance(reply, Exception):
                    raise reply
                return reply
        return _Resp()

    def urls(self, suffix: str) -> list[tuple[str, dict]]:
        with self._lock:
            return [c for c in self.calls if c[0].endswith("/" + suffix)]


class _Vision:
    """vision GET /latest 대역 — `_poll_once`에 주입한다."""

    def __init__(self, judgment: dict):
        self.judgment = judgment
        self.reset_calls = 0

    def get(self, url):
        return _Resp(200, self.judgment)

    def post(self, url, **_):
        self.reset_calls += 1
        return _Resp()


def _judgment(pred=None, *, reject=False, reason=None, score=90, conf=0.95, latency=40) -> dict:
    return {"predicted_class": pred, "confidence": conf, "match_score": score,
            "is_reject": reject, "latency_ms": latency, "reason": reason}


CORRECT_정지 = _judgment("정지")
WRONG_서행 = _judgment("서행", score=60)
WRONG_주의 = _judgment("주의", score=55)
NO_HAND = _judgment("negative", reject=True, reason="no_hand", score=0, conf=0.0)


def _wait_for(pred, timeout: float = 3.0) -> bool:
    """백그라운드 전송을 기다린다 — 시범 `/command`는 스레드로 보낼 수 있다(스펙 §4.1)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return pred()


def _reset(phase: "str | None" = None) -> None:
    sm._session.clear()
    sm._session.update(sm._fresh_session())
    sm._session["state"] = "training"
    if phase is not None:
        sm._session["phase"] = phase


def _client() -> TestClient:
    app = FastAPI()                                   # startup 폴링 스레드 없이 라우터만
    app.include_router(sm.router, prefix="/api")
    return TestClient(app)


# ── 구현 감지 ─────────────────────────────────────────────────────────────────
PHASE_READY = "phase" in sm._fresh_session()          # ①-a
CSV_READY = hasattr(sm, "TRIAL_LOG_DIR")              # ②-a


def _probe_status_ready() -> bool:
    """③ — picar가 `partial`을 돌려줄 때 정답 처리 결과가 실패로 기록되는지 한 번 돌려 본다."""
    saved = copy.deepcopy(sm._session)
    try:
        _reset("judging" if PHASE_READY else None)
        with patch.object(sm.httpx, "post", _Devices(picar=_Resp(200, {"status": "partial"}))):
            sm._poll_once(_Vision(CORRECT_정지))
        return (sm._session.get("last_dispatch") or {}).get("picar", {}).get("ok") is False
    except Exception:  # noqa: BLE001 — 감지 실패는 "미구현"으로 본다
        return False
    finally:
        sm._session.clear()
        sm._session.update(saved)


STATUS_READY = _probe_status_ready()

needs_phase = pytest.mark.xfail(not PHASE_READY, strict=True,
                                reason="①-a 판정 타이밍 미구현 — 구현되면 자동으로 실제 테스트가 된다")
needs_csv = pytest.mark.xfail(not CSV_READY, strict=True,
                              reason="②-a 시행 로그 CSV 미구현 (TRIAL_LOG_DIR 없음)")
needs_status = pytest.mark.xfail(not STATUS_READY, strict=True,
                                 reason="③ 본문 status 판정 미구현 (03 §5-5)")


@pytest.fixture
def fast_hold(monkeypatch):
    """오답 1초 유지를 0.2초로 줄여 테스트를 빠르게 한다. 상수가 아직 없으면 실제 시간(1.0초)을 쓴다."""
    if hasattr(sm, "WRONG_CONFIRM_S"):
        monkeypatch.setattr(sm, "WRONG_CONFIRM_S", 0.2)
        return 0.2
    return 1.0


# ══ ①-a 판정 타이밍 (스펙 §4.1·§6) ═══════════════════════════════════════════
@needs_phase
def test_fresh_session_starts_in_demo_phase():
    """수신호 시작은 항상 시범 단계 — 버튼을 누르기 전에는 판정하지 않는다."""
    assert sm._fresh_session()["phase"] == "demo"


@needs_phase
def test_api_state_exposes_phase():
    _reset("demo")
    assert _client().get("/api/state").json()["phase"] == "demo"


@needs_phase
def test_demo_phase_ignores_judgments():
    """시범을 보는 동안 정답 손모양이 보여도 판정하지 않는다 (9/25 문제 1)."""
    _reset("demo")
    devices = _Devices()
    with patch.object(sm.httpx, "post", devices):
        sm._poll_once(_Vision(CORRECT_정지))
    assert sm._session["curriculum_index"] == 0
    assert sm._session["last_result"] is None
    assert devices.calls == [], "시범 단계에서 장치를 호출하면 안 된다"


@needs_phase
def test_demo_phase_does_not_count_camera_fail():
    """시범을 보느라 손을 내려도 SC-04로 가지 않는다 (9/25 문제 3)."""
    _reset("demo")
    with patch.object(sm.httpx, "post", _Devices()):
        vision = _Vision(NO_HAND)
        for _ in range(sm.CAMERA_FAIL_STREAK_THRESHOLD + 5):
            sm._poll_once(vision)
    assert sm._session["state"] == "training"
    assert sm._session["camera_fail_streak"] == 0


@needs_phase
def test_start_sends_demo_command_only():
    """`/api/start` 직후 첫 수신호 시범 — `/command`만 보내고 `/result`·picar는 보내지 않는다."""
    devices = _Devices()
    with patch.object(sm.httpx, "post", devices):
        assert _client().post("/api/start").status_code == 200
        assert _wait_for(lambda: devices.urls("command")), "수신호 시작 시 시범 /command가 없다"
        time.sleep(0.1)
    (_, body), = devices.urls("command")
    assert body["command"] == "demo" and body["target_signal"] == "정지"
    assert devices.urls("result") == [] and devices.urls("picar") == []
    assert sm._session["phase"] == "demo"


@needs_phase
def test_confirm_resets_vision_and_starts_judging():
    """확인 버튼 → vision /reset → 판정 단계 (시범 동안 쌓인 연속판정 누적을 버린다)."""
    _reset("demo")
    devices = _Devices()
    with patch.object(sm.httpx, "post", devices):
        assert _client().post("/api/confirm").status_code == 200
    assert sm._session["phase"] == "judging"
    assert any(url == f"{sm.VISION_URL}/reset" for url, _ in devices.calls), "확인 시 vision /reset이 없다"


@needs_phase
def test_confirm_is_ignored_while_judging():
    """판정 중 중복 입력(스페이스바 연타)은 무시 — /reset을 다시 보내지 않는다."""
    _reset("judging")
    devices = _Devices()
    with patch.object(sm.httpx, "post", devices):
        assert _client().post("/api/confirm").status_code == 200, "POST /api/confirm이 없다"
    assert sm._session["phase"] == "judging"
    assert not any(url.endswith("/reset") for url, _ in devices.calls)


def test_correct_is_confirmed_immediately():
    """회귀 방지 — 오답 1초 유지가 들어와도 정답은 기다리지 않는다 (①-a 구현 전후 모두 참)."""
    _reset("judging" if PHASE_READY else None)
    with patch.object(sm.httpx, "post", _Devices()):
        sm._poll_once(_Vision(CORRECT_정지))
    assert sm._session["last_result"]["outcome"] == "correct"
    assert sm._session["curriculum_index"] == 1


@needs_phase
def test_wrong_shorter_than_hold_is_not_confirmed(fast_hold):
    """손을 올리는 도중의 과도 자세 — 유지 시간 전에는 오답이 아니다 (9/25 문제 2)."""
    _reset("judging")
    vision = _Vision(WRONG_서행)
    with patch.object(sm.httpx, "post", _Devices()):
        sm._poll_once(vision)
        time.sleep(fast_hold * 0.4)
        sm._poll_once(vision)
    assert sm._session["last_result"] is None
    assert sm._session["attempts"].get("정지", 0) == 0, "과도 자세는 시도 횟수로 세지 않는다(스펙 §5)"


@needs_phase
def test_wrong_held_past_hold_is_confirmed_and_returns_to_demo(fast_hold):
    """같은 오답이 유지 시간을 넘기면 확정 → 재시범과 함께 시범 단계로 돌아간다."""
    _reset("judging")
    vision = _Vision(WRONG_서행)
    devices = _Devices()
    with patch.object(sm.httpx, "post", devices):
        sm._poll_once(vision)
        time.sleep(fast_hold + 0.1)
        sm._poll_once(vision)
    assert sm._session["last_result"]["outcome"] == "wrong"
    assert sm._session["attempts"]["정지"] == 1
    assert sm._session["phase"] == "demo"
    assert any(b.get("command") == "demo" for _, b in devices.urls("command")), "오답 뒤 재시범이 없다"


@needs_phase
def test_changing_wrong_class_restarts_the_hold(fast_hold):
    """서행 → 주의로 바뀌면 주의 기준으로 다시 센다."""
    _reset("judging")
    vision = _Vision(WRONG_서행)
    with patch.object(sm.httpx, "post", _Devices()):
        sm._poll_once(vision)
        time.sleep(fast_hold * 0.7)
        vision.judgment = WRONG_주의
        sm._poll_once(vision)
        time.sleep(fast_hold * 0.7)                   # 서행 기준이면 넘었지만 주의 기준으로는 아직
        sm._poll_once(vision)
        assert sm._session["last_result"] is None
        time.sleep(fast_hold * 0.5)
        sm._poll_once(vision)
    assert sm._session["last_result"]["outcome"] == "wrong"
    assert sm._session["last_result"]["predicted_class"] == "주의"


@needs_phase
def test_hand_lowered_restarts_the_hold(fast_hold):
    """손을 내렸다 다시 들면 새로 센다 (데모 스크립트 `_listen()`과 같은 규칙)."""
    _reset("judging")
    vision = _Vision(WRONG_서행)
    with patch.object(sm.httpx, "post", _Devices()):
        sm._poll_once(vision)
        time.sleep(fast_hold * 0.7)
        vision.judgment = NO_HAND
        sm._poll_once(vision)
        vision.judgment = WRONG_서행
        sm._poll_once(vision)
        time.sleep(fast_hold * 0.7)
        sm._poll_once(vision)
    assert sm._session["last_result"] is None


@needs_phase
def test_next_signal_demo_follows_correct_pose():
    """정답 → (정답 자세) → 다음 수신호 시범. 두 `/command`가 이 순서로 가야 한다."""
    _reset("judging")
    devices = _Devices()
    with patch.object(sm.httpx, "post", devices):
        sm._poll_once(_Vision(CORRECT_정지))
        assert _wait_for(lambda: any(b.get("target_signal") == "서행" for _, b in devices.urls("command")))
    commands = [(b["command"], b["target_signal"]) for _, b in devices.urls("command")]
    assert commands.index(("correct_pose", "정지")) < commands.index(("demo", "서행"))
    assert sm._session["phase"] == "demo"


# ══ ③ 장치 응답 판정 (03 §5-5) ═══════════════════════════════════════════════
def _correct_with(devices: _Devices) -> dict:
    _reset("judging" if PHASE_READY else None)
    with patch.object(sm.httpx, "post", devices):
        sm._poll_once(_Vision(CORRECT_정지))
    return sm._session["last_dispatch"]


@needs_status
@pytest.mark.parametrize("body", [{"status": "timeout"},
                                  {"status": "error", "reason": "microbit_unreachable"},
                                  {"status": "error", "reason": "write_failed"}])
def test_actuation_failure_body_is_failure_without_retry(body):
    devices = _Devices(command=_Resp(200, body))
    dispatch = _correct_with(devices)
    assert dispatch["aihand"]["ok"] is False
    assert len([c for c in devices.urls("command") if c[1].get("command") == "correct_pose"]) == 1, \
        "본문 실패는 재시도하지 않는다 — 다시 보내면 AI Hand가 두 번 움직인다"


@needs_status
def test_picar_partial_is_failure_without_retry():
    devices = _Devices(picar=_Resp(200, {"status": "partial", "motor": {"status": "error", "reason": "i2c_failed"}}))
    dispatch = _correct_with(devices)
    assert dispatch["picar"]["ok"] is False
    assert len(devices.urls("picar")) == 1


def test_picar_ok_with_led_failure_is_still_success():
    """회귀 방지 — LED만 실패하면 최상위 status는 ok, 모터 기준으로 성공(③ 구현 뒤에도 실패로 세면 안 된다)."""
    body = {"status": "ok", "motor": {"status": "ok"},
            "led": {"red": {"status": "error", "reason": "gpio_failed"}}}
    assert _correct_with(_Devices(picar=_Resp(200, body)))["picar"]["ok"] is True


def test_mocked_counts_as_success():
    """회귀 방지 — `mocked`는 성공(③ 구현 뒤에도). 모의 여부 표시는 CSV `mocked` 열에서 본다."""
    dispatch = _correct_with(_Devices(command=_Resp(200, {"status": "mocked"}),
                                      picar=_Resp(200, {"status": "ok", "motor": {"status": "mocked"}})))
    assert dispatch["aihand"]["ok"] is True and dispatch["picar"]["ok"] is True


@needs_status
@pytest.mark.parametrize("suffix", ["command", "picar"])
def test_read_timeout_is_not_retried_for_command_and_picar(suffix):
    """web 1.5초 < actuation 회신 대기 2.0초 — 재시도하면 같은 명령이 두 번 간다 (03 §5-5 ⚠️)."""
    devices = _Devices(**{suffix: httpx.ReadTimeout("slow")})
    dispatch = _correct_with(devices)
    key = "aihand" if suffix == "command" else "picar"
    assert dispatch[key]["ok"] is False
    sent = devices.urls(suffix)
    if suffix == "command":
        sent = [c for c in sent if c[1].get("command") == "correct_pose"]
    assert len(sent) == 1, f"읽기 타임아웃 뒤 /{suffix}를 다시 보냈다"


def test_connect_error_is_still_retried_once():
    """연결 실패는 요청이 가지 않았으므로 재시도해도 안전하다 — 현행 동작 유지 (③ 구현 전후 모두 참)."""
    devices = _Devices(picar=httpx.ConnectError("refused"))
    dispatch = _correct_with(devices)
    assert dispatch["picar"]["ok"] is False
    assert len(devices.urls("picar")) == 2


# ══ ②-a 시행 로그 CSV (스펙 §7) ══════════════════════════════════════════════
DEMO_FIELDS = ("time", "signal", "attempt", "outcome", "predicted", "match_score", "confidence",
               "vision_latency_ms", "demo_ok", "demo_ms", "observe_ms", "listen_ms",
               "picar_ok", "picar_ms", "microbit_ok", "microbit_ms", "feedback_ms")
WEB_FIELDS = ("aihand_ok", "aihand_ms", "feedback_done_ms", "aihand_status", "microbit_status",
              "picar_status", "picar_led_ok", "mocked", "subject")


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    if CSV_READY:
        monkeypatch.setattr(sm, "TRIAL_LOG_DIR", tmp_path)
    return tmp_path


def _rows(log_dir: Path) -> "tuple[list[str], list[dict]]":
    files = sorted(log_dir.glob("web_trials_*.csv"))
    assert files, "web_trials_*.csv가 생기지 않았다"
    raw = files[-1].read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "엑셀용 UTF-8 BOM이 없다"
    with files[-1].open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


@needs_csv
def test_correct_writes_one_row_with_all_columns(log_dir):
    _correct_with(_Devices())
    header, rows = _rows(log_dir)
    assert list(header[:len(DEMO_FIELDS)]) == list(DEMO_FIELDS), "앞 열은 데모 스크립트 RECORD_FIELDS와 같은 순서"
    assert set(WEB_FIELDS) <= set(header)
    (row,) = rows
    assert row["signal"] == "정지" and row["outcome"] == "correct" and row["predicted"] == "정지"
    assert row["match_score"] == "90" and row["vision_latency_ms"] == "40"
    assert row["aihand_status"].startswith("ok") and row["picar_status"].startswith("ok")


@needs_csv
def test_transient_judgments_write_no_rows(log_dir):
    """미검출·과도기 사유는 판정이 아니다 — 정답 1행 뒤에 이것들이 와도 행이 늘지 않는다."""
    _correct_with(_Devices())
    if PHASE_READY:
        sm._session["phase"] = "judging"
    with patch.object(sm.httpx, "post", _Devices()):
        vision = _Vision(NO_HAND)
        sm._poll_once(vision)
        vision.judgment = _judgment(None, reject=True, reason="awaiting_consecutive_frames", score=0)
        sm._poll_once(vision)
    assert len(_rows(log_dir)[1]) == 1


@needs_csv
def test_failed_device_is_recorded_in_row(log_dir):
    _correct_with(_Devices(picar=_Resp(200, {"status": "partial", "motor": {"status": "error", "reason": "i2c_failed"}})))
    (row,) = _rows(log_dir)[1]
    assert row["picar_ok"].lower() in ("false", "0")
    assert row["picar_status"].startswith("partial")


@needs_csv
def test_feedback_ms_is_the_later_reaction_start(log_dir):
    _correct_with(_Devices())
    (row,) = _rows(log_dir)[1]
    assert float(row["feedback_ms"]) == max(float(row["picar_ms"]), float(row["microbit_ms"]))
