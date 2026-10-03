"""actuation 제스처 매핑 / BLE 명령 문자열 단위 테스트 (하드웨어 없이 실행).

2026-09-21 실물 BLE 검증(A-1)은 통과했지만, 그건 micro:bit가 연결된 상태에서만 돌릴 수 있다.
이 테스트는 **micro:bit 없이도** `target_signal -> G{n}` 매핑과 BLE로 나가는 문자열이 프로토콜과
일치하는지 고정한다. 실제 BLE는 건드리지 않는다(mock=True 경로만).

프로토콜 근거: shared/schemas/microbit_protocol.md ·
document/03_인터페이스계약서.md §5-3 · 펌웨어 src/firmware/aihand_control.ts

버튼 A(`BTN:A`, 2026-09-28) 수신도 여기서 고정한다 — 맨 아래 "버튼 입력" 절 참고.

`pytest-asyncio`를 쓰지 않기 위해 async 함수는 `asyncio.run()`으로 감싼다
(actuation/requirements.txt에 테스트 전용 의존성을 추가하지 않으려는 의도).

실행:
    cd services/actuation && python -m pytest tests/test_controller.py -q
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))

from aihand import controller  # noqa: E402
from microbit import ble_bridge  # noqa: E402

# picar·vision에도 src/app.py가 있다. `import app`으로 올리면 sys.modules["app"]에 남아 다른 서비스
# 테스트가 이 모듈을 잘못 집는다 — 경로로 적재하고 고유 이름을 준다.
_spec = importlib.util.spec_from_file_location("actuation_app", _SRC / "app.py")
actuation_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(actuation_app)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA = _REPO_ROOT / "shared" / "schemas" / "aihand_command.schema.json"


def _schema_signals() -> list:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    return schema["properties"]["target_signal"]["enum"]


# ── target_signal <-> G{n} 매핑 ───────────────────────────────────────────────
def test_gesture_map_covers_exactly_the_schema_signals():
    """스키마의 7종과 매핑 테이블이 어긋나면 특정 수신호에서 AI Hand가 침묵한다."""
    assert set(controller.GESTURE_MAP) == set(_schema_signals())


def test_gesture_numbers_are_unique_and_one_to_seven():
    numbers = sorted(controller.GESTURE_MAP.values())
    assert numbers == [1, 2, 3, 4, 5, 6, 7]


def test_gesture_map_order_matches_prd_table():
    """10_PRD §3.2 표 순서 = G1~G7. 순서가 밀리면 엉뚱한 제스처가 나간다."""
    assert controller.GESTURE_MAP == {
        "정지": 1,
        "서행": 2,
        "좌회전_유도": 3,
        "우회전_유도": 4,
        "확인_완료": 5,
        "후진": 6,
        "주의": 7,
    }


def test_demo_signal_order_matches_gesture_numbers():
    """aihand_test는 aihand_picar_demo.SIGNALS 순서를 G1~G7 라벨로 쓴다(KPI 물리 지연 로그).
    picar 메뉴 순서가 밀리면 로그에 엉뚱한 G 번호가 경고 없이 찍힌다."""
    spec = importlib.util.spec_from_file_location(
        "aihand_picar_demo", _SRC.parent / "scripts" / "aihand_picar_demo.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    assert demo.SIGNALS == sorted(controller.GESTURE_MAP, key=controller.GESTURE_MAP.get)


# ── controller.execute() ─────────────────────────────────────────────────────
def _execute(command: dict) -> dict:
    return asyncio.run(controller.execute(command, mock=True))


def test_every_schema_signal_produces_a_gesture_command():
    for signal in _schema_signals():
        result = _execute({"target_signal": signal})
        assert result["status"] == "mocked", f"{signal} 미처리: {result}"
        assert result["sent"] == f"G{controller.GESTURE_MAP[signal]}"
        assert result["target_signal"] == signal


def test_unknown_signal_is_rejected_without_sending():
    result = _execute({"target_signal": "손흔들기"})
    assert result["status"] == "error"
    assert result["reason"] == "unknown_target_signal"
    assert "sent" not in result


def test_missing_target_signal_does_not_crash():
    """web이 필드를 빠뜨려도 서비스가 죽으면 안 된다."""
    result = _execute({})
    assert result["status"] == "error"
    assert result["reason"] == "unknown_target_signal"


def test_servo_angles_are_ignored_for_gesture_selection():
    """servo_angles는 스키마 호환용으로만 남아 있고 구동에는 쓰이지 않는다.

    (RPi5가 각도를 계산하던 방식 -> micro:bit 펌웨어의 캘리브레이션된 G{n} 호출 방식으로 전환됨)
    """
    absurd = {"thumb": 0, "index": 0, "middle": 0, "ring": 0, "pinky": 0, "wrist_rotation": 0}
    result = _execute({"target_signal": "정지", "servo_angles": absurd})
    assert result["sent"] == "G1"


# ── DEFAULT_SERVO_ANGLES (web이 스키마를 채울 때 참고하는 값) ────────────────
def test_default_servo_angles_cover_all_signals():
    assert set(controller.DEFAULT_SERVO_ANGLES) == set(controller.GESTURE_MAP)


def test_default_servo_angles_match_schema_field_and_range():
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    props = schema["properties"]["servo_angles"]["properties"]
    for signal, angles in controller.DEFAULT_SERVO_ANGLES.items():
        assert set(angles) == set(props), signal
        for joint, value in angles.items():
            lo, hi = props[joint]["minimum"], props[joint]["maximum"]
            assert lo <= value <= hi, f"{signal}.{joint}={value} 범위 밖"


# ── BLE 명령 문자열 (펌웨어가 문자코드로 직접 파싱하므로 형식이 정확해야 함) ──
def test_gesture_line_format():
    for n in range(1, 8):
        result = asyncio.run(ble_bridge.send_gesture(n, mock=True))
        assert result["sent"] == f"G{n}"


def test_result_maps_bool_to_firmware_keywords():
    assert asyncio.run(ble_bridge.send_result(True, mock=True))["sent"] == "correct"
    assert asyncio.run(ble_bridge.send_result(False, mock=True))["sent"] == "incorrect"


def test_progress_is_two_digits_without_separator():
    """펌웨어가 콜론/parseInt 없이 문자코드로 파싱한다 — "P37" 형식이어야 한다."""
    assert asyncio.run(ble_bridge.send_progress(3, 7, mock=True))["sent"] == "P37"
    assert asyncio.run(ble_bridge.send_progress(1, 7, mock=True))["sent"] == "P17"


def test_uart_uuids_are_the_reversed_pair_measured_on_this_board():
    """이 보드는 표준 NUS와 RX/TX가 반대다 — 표준값으로 되돌리면 통신이 죽는다.

    2026-09-21 `scripts/ble_debug_services.py` 실측: 6e400003=write, 6e400002=indicate.
    """
    assert ble_bridge.UART_RX_UUID.startswith("6e400003")
    assert ble_bridge.UART_TX_UUID.startswith("6e400002")


def test_mock_mode_never_opens_a_ble_connection():
    asyncio.run(ble_bridge.send_gesture(1, mock=True))
    asyncio.run(ble_bridge.send_result(True, mock=True))
    asyncio.run(ble_bridge.send_progress(1, 7, mock=True))
    assert ble_bridge._client is None


if __name__ == "__main__":  # pytest 없이도 돌려볼 수 있게
    import traceback

    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"\n{'FAILED ' + str(failed) if failed else 'ALL PASSED'}")


# ── is_connected (2026-09-23 RPi5 실측에서 발견) ─────────────────────────────
class _DeprecatedIsConnectedLike:
    """bleak 0.22 BlueZ 백엔드가 `is_connected`로 돌려주는 래퍼를 흉내 낸다.

    bool처럼 쓰이지만 bool이 아니다 — FastAPI가 `{"_value": ...}` dict로 직렬화한다.
    """

    def __init__(self, value: bool):
        self._value = value

    def __bool__(self) -> bool:
        return self._value


class _FakeClient:
    def __init__(self, connected: bool):
        self.is_connected = _DeprecatedIsConnectedLike(connected)


def test_is_connected_returns_a_real_bool_on_bluez(monkeypatch):
    """래퍼 객체를 그대로 반환하면 /health가 `{"_value": false}`를 내보내고,
    dict는 항상 참이라 **연결이 끊겨도 호출부는 연결됨으로 읽는다.**"""
    monkeypatch.setattr(ble_bridge, "_client", _FakeClient(connected=False))
    result = ble_bridge.is_connected(mock=False)
    assert result is False, f"bool이 아니라 {type(result).__name__}를 반환했다"

    monkeypatch.setattr(ble_bridge, "_client", _FakeClient(connected=True))
    assert ble_bridge.is_connected(mock=False) is True


# ── connect 실패 경로 (2026-09-23 RPi5에서 "연결이 안 된다"는데 서버가 아무 이유도 안 남김) ──────────
class _Dev:
    def __init__(self, name, address="AA:BB:CC:DD:EE:FF"):
        self.name = name
        self.address = address


class _ScriptedClient:
    """connect/start_notify에서 지정한 예외를 던지고, disconnect 호출 여부를 기록한다."""
    instances: list = []

    def __init__(self, device, fail_at=None, exc=None):
        self.device = device
        self.fail_at = fail_at
        self.exc = exc
        self.disconnected = False
        _ScriptedClient.instances.append(self)

    async def connect(self):
        if self.fail_at == "connect":
            raise self.exc

    async def start_notify(self, _uuid, _cb):
        if self.fail_at == "notify":
            raise self.exc

    async def disconnect(self):
        self.disconnected = True


def _patch_ble(monkeypatch, devices, fail_at=None, exc=None):
    async def _discover(timeout):
        return devices

    _ScriptedClient.instances = []
    monkeypatch.setattr(ble_bridge.BleakScanner, "discover", staticmethod(_discover))
    monkeypatch.setattr(ble_bridge, "BleakClient",
                        lambda device: _ScriptedClient(device, fail_at, exc))
    monkeypatch.setattr(ble_bridge, "_client", None)
    monkeypatch.setattr(ble_bridge, "_reply_event", None)


def test_notify_failure_releases_the_half_open_connection(monkeypatch):
    """연결 후 notify 등록이 실패했는데 안 끊으면 BlueZ에 연결이 남아 micro:bit가 광고를 멈추고,
    **이후 스캔에서 영영 안 보인다.**"""
    from bleak.exc import BleakError

    _patch_ble(monkeypatch, [_Dev("BBC micro:bit [zavig]")], fail_at="notify", exc=BleakError("x"))
    assert asyncio.run(ble_bridge.connect(mock=False)) is False
    assert _ScriptedClient.instances[0].disconnected, "반쯤 열린 연결을 끊지 않았다"
    assert ble_bridge._client is None


def test_connect_timeout_returns_false_instead_of_crashing_startup(monkeypatch):
    """asyncio.TimeoutError는 BleakError가 아니다 — 안 잡으면 uvicorn 기동이 통째로 실패한다."""
    _patch_ble(monkeypatch, [_Dev("BBC micro:bit")], fail_at="connect", exc=asyncio.TimeoutError())
    assert asyncio.run(ble_bridge.connect(mock=False)) is False


def test_not_found_logs_what_the_scan_did_see(monkeypatch, caplog):
    """원인(이미 다른 쪽에 연결됨 / 전원 / 이름 불일치)을 좁히려면 스캔에 뭐가 보였는지가 필요하다."""
    _patch_ble(monkeypatch, [_Dev("Galaxy Buds"), _Dev(None)])
    with caplog.at_level("WARNING", logger="uvicorn.error"):
        assert asyncio.run(ble_bridge.connect(mock=False)) is False
    assert "Galaxy Buds" in caplog.text


def test_connect_passes_the_scanned_device_not_the_address(monkeypatch):
    """주소 문자열을 넘기면 bleak BlueZ 백엔드가 connect() 안에서 **스캔을 한 번 더** 돈다
    (find_device_by_address) — 연결 시간 예산을 잡아먹어 RPi5에서 시간 초과를 키운다."""
    dev = _Dev("BBC micro:bit [zezuz]")
    _patch_ble(monkeypatch, [dev])
    assert asyncio.run(ble_bridge.connect(mock=False)) is True
    assert _ScriptedClient.instances[0].device is dev


# ── 동시 전송 직렬화 ─────────────────────────────────────────────────────────
class _EchoClient:
    """쓴 명령에 대해 잠시 뒤 펌웨어처럼 회신한다 (G{n} → OK{n})."""
    is_connected = True

    async def write_gatt_char(self, _uuid, data):
        n = data.decode().strip()[1:]

        async def _reply():
            await asyncio.sleep(0.02)
            ble_bridge._on_notify(None, f"OK{n}".encode())

        asyncio.get_running_loop().create_task(_reply())


def test_concurrent_sends_each_get_their_own_reply(monkeypatch):
    """회신 칸이 하나뿐이라 잠금 없이 동시에 보내면 뒤 요청이 앞 요청의 대기 이벤트를 지우고
    회신을 가로챈다 — web이 actuation을 병렬로 호출하면 '엉뚱한 OK'나 timeout이 난다."""
    monkeypatch.setattr(ble_bridge, "_client", _EchoClient())
    monkeypatch.setattr(ble_bridge, "_reply_event", None)
    monkeypatch.setattr(ble_bridge, "_send_lock", None)

    async def _run():
        ble_bridge._reply_event = asyncio.Event()
        return await asyncio.gather(*(ble_bridge.send_gesture(n, mock=False) for n in (1, 2, 3)))

    results = asyncio.run(_run())
    assert [r.get("reply") for r in results] == ["OK1", "OK2", "OK3"], results


# ── 버튼 입력 (BTN, 2026-09-28) ──────────────────────────────────────────────
# 펌웨어는 버튼 A를 누르면 **요청 없이** "BTN:A\n"을 알림으로 올린다. 회신 칸(_last_reply/_reply_event)이
# 하나뿐이라 이 줄을 회신으로 받으면 대기 중인 G 명령이 엉뚱한 줄로 "ok" 처리되고(AI Hand가 아직
# 움직이는 중인데 /command가 돌아감) 버튼 입력은 사라진다. BTN 줄이 회신과 섞이지 않고 seq로만
# 쌓이는지 고정한다.
@pytest.fixture
def fresh_bridge(monkeypatch):
    """모듈 전역 상태가 테스트 사이로 새지 않게 매번 새로 깐다."""
    monkeypatch.setattr(ble_bridge, "_button", {"seq": 0, "last_button": None, "last_at": None})
    monkeypatch.setattr(ble_bridge, "_last_reply", None)
    monkeypatch.setattr(ble_bridge, "_reply_event", None)
    monkeypatch.setattr(ble_bridge, "_send_lock", None)
    monkeypatch.setattr(ble_bridge, "_client", None)


def test_button_line_is_not_taken_as_a_reply(fresh_bridge):
    ble_bridge._reply_event = asyncio.Event()
    ble_bridge._on_notify(None, b"BTN:A\n")
    assert not ble_bridge._reply_event.is_set(), "버튼 알림이 회신 대기를 깨웠다"
    assert ble_bridge._last_reply is None
    assert ble_bridge.button_state()["seq"] == 1
    assert ble_bridge.button_state()["last_button"] == "A"


def test_reply_and_button_in_one_notify_are_split(fresh_bridge):
    """두 줄이 알림 한 번에 붙어 와도 회신은 회신대로, 버튼은 버튼대로 처리한다."""
    ble_bridge._reply_event = asyncio.Event()
    ble_bridge._on_notify(None, b"OK3\nBTN:A\n")
    assert ble_bridge._last_reply == "OK3"
    assert ble_bridge._reply_event.is_set()
    assert ble_bridge.button_state()["seq"] == 1


def test_button_before_reply_does_not_shadow_it(fresh_bridge):
    ble_bridge._reply_event = asyncio.Event()
    ble_bridge._on_notify(None, b"BTN:A\nOK:CORRECT\n")
    assert ble_bridge._last_reply == "OK:CORRECT"
    assert ble_bridge.button_state()["seq"] == 1


def test_reply_without_newline_still_counts(fresh_bridge):
    """기존 동작 유지 — 줄바꿈 없이 온 회신도 한 줄로 받는다."""
    ble_bridge._reply_event = asyncio.Event()
    ble_bridge._on_notify(None, b"OK5")
    assert ble_bridge._last_reply == "OK5"


def test_each_press_increments_seq_and_stamps_time(fresh_bridge):
    for _ in range(3):
        ble_bridge._on_notify(None, b"BTN:A\n")
    state = ble_bridge.button_state()
    assert state["seq"] == 3
    assert state["last_at"] is not None


def test_button_state_is_a_copy(fresh_bridge):
    """호출부가 받은 dict를 고쳐도 내부 seq가 바뀌면 안 된다."""
    state = ble_bridge.button_state()
    state["seq"] = 99
    assert ble_bridge.button_state()["seq"] == 0


class _SlowGestureClient:
    """G{n}을 받으면 버튼 알림을 먼저, 회신을 나중에 보낸다 (시범 동작 끝 무렵에 누르는 상황)."""
    is_connected = True

    async def write_gatt_char(self, _uuid, data):
        n = data.decode().strip()[1:]

        async def _events():
            await asyncio.sleep(0.01)
            ble_bridge._on_notify(None, b"BTN:A\n")
            await asyncio.sleep(0.02)
            ble_bridge._on_notify(None, f"OK{n}\n".encode())

        asyncio.get_running_loop().create_task(_events())


def test_press_during_gesture_keeps_the_real_ack(fresh_bridge, monkeypatch):
    monkeypatch.setattr(ble_bridge, "_client", _SlowGestureClient())

    async def _run():
        ble_bridge._reply_event = asyncio.Event()
        return await ble_bridge.send_gesture(4, mock=False)

    result = asyncio.run(_run())
    assert result["status"] == "ok"
    assert result["reply"] == "OK4", f"버튼 알림을 회신으로 받았다: {result}"
    assert ble_bridge.button_state()["seq"] == 1


def test_get_button_reports_seq_and_connection(fresh_bridge):
    body = actuation_app.button()
    assert body["seq"] == 0
    assert body["last_button"] is None
    assert body["microbit_connected"] is True  # 기본 MOCK_HARDWARE=true


def test_simulate_increments_seq_without_touching_ble(fresh_bridge):
    actuation_app.button_simulate(None)
    body = actuation_app.button_simulate({"button": "A"})
    assert body["seq"] == 2
    assert actuation_app.button()["seq"] == 2
    assert ble_bridge._client is None


# ── /result·/progress 입력 검증 ───────────────────────────────────────────────
@pytest.mark.parametrize("value", ["false", "true", 1, None])
def test_result_counts_only_json_true_as_correct(value):
    """문자열 "false"가 참으로 평가돼 O가 뜨던 결함 — JSON true만 정답이다."""
    assert asyncio.run(actuation_app.result({"is_correct": value}))["sent"] == "incorrect"
    assert asyncio.run(actuation_app.result({"is_correct": True}))["sent"] == "correct"


@pytest.mark.parametrize("payload", [{"current": 10, "total": 7}, {"current": -1}, {"current": "3"},
                                     {"current": True}, {"total": 3.5}])
def test_progress_rejects_values_the_protocol_cannot_carry(payload):
    """프로토콜은 P<한 자리><한 자리> — P107(10/7)은 펌웨어가 1/07인지 10/7인지 모른다."""
    assert asyncio.run(actuation_app.progress(payload))["reason"] == "invalid_progress"


def test_progress_sends_single_digits():
    assert asyncio.run(actuation_app.progress({"current": 3, "total": 7}))["sent"] == "P37"
