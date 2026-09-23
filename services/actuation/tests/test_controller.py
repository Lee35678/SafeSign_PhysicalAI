"""actuation 제스처 매핑 / BLE 명령 문자열 단위 테스트 (하드웨어 없이 실행).

2026-09-21 실물 BLE 검증(A-1)은 통과했지만, 그건 micro:bit가 연결된 상태에서만 돌릴 수 있다.
이 테스트는 **micro:bit 없이도** `target_signal -> G{n}` 매핑과 BLE로 나가는 문자열이 프로토콜과
일치하는지 고정한다. 실제 BLE는 건드리지 않는다(mock=True 경로만).

프로토콜 근거: shared/schemas/microbit_protocol.md ·
document/03_인터페이스계약서_v2.md §5-3 · 펌웨어 src/firmware/aihand_control.ts

`pytest-asyncio`를 쓰지 않기 위해 async 함수는 `asyncio.run()`으로 감싼다
(actuation/requirements.txt에 테스트 전용 의존성을 추가하지 않으려는 의도).

실행:
    cd services/actuation && python -m pytest tests/test_controller.py -q
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aihand import controller  # noqa: E402
from microbit import ble_bridge  # noqa: E402

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
    """10_PRD_v2 §3.2 표 순서 = G1~G7. 순서가 밀리면 엉뚱한 제스처가 나간다."""
    assert controller.GESTURE_MAP == {
        "정지": 1,
        "서행": 2,
        "좌회전_유도": 3,
        "우회전_유도": 4,
        "확인_완료": 5,
        "후진": 6,
        "주의": 7,
    }


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

    2026-09-21 `tests/ble_debug_services.py` 실측: 6e400003=write, 6e400002=indicate.
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

    def __init__(self, address, fail_at=None, exc=None):
        self.address = address
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
                        lambda address: _ScriptedClient(address, fail_at, exc))
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
