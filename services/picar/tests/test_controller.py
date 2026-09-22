"""picar 모터/LED 변환 로직 단위 테스트 (하드웨어 없이 실행).

RPi4B·picar 실물이 아직 없으므로, 실물이 도착했을 때 "코드가 틀린 건지 배선이 틀린 건지"로
헤매지 않도록 **I2C 바이트 변환과 분기 로직만** 먼저 고정해 둔다. 실제 I2C/GPIO는 건드리지 않는다
(mock=True 경로만 사용 — smbus2/gpiozero는 실물 경로에서만 지연 임포트되므로 여기서 임포트조차
되지 않아야 한다).

프로토콜 근거: services/picar/README.md "모터 I2C 프로토콜" ·
document/03_인터페이스계약서_v2.md §5-2 · Yahboom `YB_Pcb_Car.py`

실행:
    cd services/picar && python -m pytest tests -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import controller  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA = _REPO_ROOT / "shared" / "schemas" / "picar_command.schema.json"


# ── 속도 변환 (스키마 0~100% -> 코프로세서 0~255) ────────────────────────────
def test_speed_0_and_100_map_to_range_ends():
    assert controller._speed_pct_to_byte(0) == 0
    assert controller._speed_pct_to_byte(100) == 255


def test_speed_web_default_values():
    """web(state_machine.PICAR_COMMANDS)이 실제로 보내는 값들."""
    assert controller._speed_pct_to_byte(40) == 102   # 서행
    assert controller._speed_pct_to_byte(50) == 128   # 후진
    assert controller._speed_pct_to_byte(60) == 153   # 좌/우회전


def test_speed_is_clamped_to_byte_range():
    """스키마를 벗어난 값이 와도 I2C에 잘못된 바이트를 쓰지 않는다."""
    assert controller._speed_pct_to_byte(-10) == 0
    assert controller._speed_pct_to_byte(999) == 255


# ── action -> I2C 레지스터/바이트 ──────────────────────────────────────────────
def _i2c(action: str, speed: int = 60) -> dict:
    return controller._apply_motor(action, speed, mock=True)["i2c"]


def test_stop_uses_stop_register_not_motor_register():
    i2c = _i2c("stop", 0)
    assert i2c["reg"] == hex(controller.REG_STOP)
    assert i2c["data"] == [0x00]


def test_forward_drives_both_wheels_forward():
    i2c = _i2c("forward")
    assert i2c["reg"] == hex(controller.REG_MOTOR)
    assert i2c["data"] == [controller.DIR_FORWARD, 153, controller.DIR_FORWARD, 153]


def test_backward_drives_both_wheels_backward():
    assert _i2c("backward")["data"] == [
        controller.DIR_BACKWARD, 153, controller.DIR_BACKWARD, 153,
    ]


def test_left_and_right_are_mirrored_spin_turns():
    """좌/우를 뒤바꾸는 실수는 실물에서 찾기 어려우므로 여기서 고정한다.

    제자리 회전 = 한쪽 전진 + 반대쪽 후진 (services/picar/README.md "좌/우 회전 방식").
    """
    left = _i2c("left")["data"]
    right = _i2c("right")["data"]

    assert left == [controller.DIR_BACKWARD, 153, controller.DIR_FORWARD, 153]
    assert right == [controller.DIR_FORWARD, 153, controller.DIR_BACKWARD, 153]
    assert left != right
    # 좌우 바퀴 방향이 서로 반대여야 제자리 회전이 된다
    assert left[0] != left[2] and right[0] != right[2]


def test_all_schema_actions_are_handled():
    """스키마 enum에 있는 action은 전부 처리되어야 한다(미처리 시 error 반환)."""
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    actions = schema["properties"]["motor"]["properties"]["action"]["enum"]
    for action in actions:
        result = controller._apply_motor(action, 50, mock=True)
        assert result["status"] == "mocked", f"{action} 미처리: {result}"


def test_unknown_action_is_rejected_without_touching_i2c():
    result = controller._apply_motor("fly", 50, mock=True)
    assert result["status"] == "error"
    assert result["reason"] == "unknown_motor_action"
    assert "i2c" not in result


# ── 자동 정지 (스키마에 지속 시간 필드가 없어 넣은 안전장치) ──────────────────
def test_drive_commands_schedule_auto_stop():
    """주행 명령은 자동 정지 예약이 붙어야 한다 — 없으면 무한 주행한다."""
    for action in ("forward", "backward", "left", "right"):
        result = controller._apply_motor(action, 50, mock=True)
        assert result["auto_stop_s"] == controller.MOTION_DURATION_S, action


def test_stop_command_does_not_schedule_auto_stop():
    assert controller._apply_motor("stop", 0, mock=True)["auto_stop_s"] is None


# ── LED ───────────────────────────────────────────────────────────────────────
def test_all_led_channels_have_a_pin_assigned():
    """3채널 모두 배선 확정됨(2026-09-21) — None이 남아 있으면 그 LED는 동작하지 않는다."""
    for name, pin in controller.PIN_MAP.items():
        assert pin is not None, f"{name} 핀 미배정"


def test_every_led_channel_responds_in_mock_mode():
    for name in controller.PIN_MAP:
        for state in ("on", "off", "blink"):
            result = controller._apply_led(name, state, mock=True)
            assert result["status"] == "mocked", f"{name}/{state}: {result}"


def test_led_channels_use_distinct_pins():
    """황색 좌/우가 같은 핀이면 좌회전 유도에서 양쪽이 같이 켜져 의미가 사라진다."""
    pins = [p for p in controller.PIN_MAP.values() if p is not None]
    assert len(pins) == len(set(pins)), f"핀 중복: {controller.PIN_MAP}"


def test_led_states_match_schema_enum():
    """스키마의 led.* enum과 코드가 어긋나면 web이 보낸 상태를 조용히 무시하게 된다."""
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    for channel in ("red", "yellow_left", "yellow_right"):
        enum = schema["properties"]["led"]["properties"][channel]["enum"]
        assert set(enum) == set(controller.LED_STATES), channel


def test_unknown_led_state_is_rejected():
    result = controller._apply_led("led_red", "strobe", mock=True)
    assert result["status"] == "error"
    assert result["reason"] == "unknown_led_state"


def test_board_pins_do_not_collide_with_raspbot_reserved_pins():
    """Raspbot이 이미 쓰는 핀을 고르면 센서/모터와 충돌한다.

    내장 적색(BCM21)·청색(BCM20)은 쓰지 않고 외부 LED만 사용하므로 예외가 없다
    (근거는 controller.py docstring "LED" 절).
    """
    for name, pin in controller.PIN_MAP.items():
        if pin is None:
            continue
        assert pin not in controller.USED_BCM_PINS, f"{name}(BCM{pin})이 이미 점유된 핀"


# ── diagnose() — /health가 "조용한 실패"를 드러내는지 ─────────────────────────
def test_diagnose_reports_i2c_target():
    d = controller.diagnose(mock=True)
    assert d["i2c"]["bus"] == controller.I2C_BUS
    assert d["i2c"]["addr"] == hex(controller.I2C_ADDR)


def test_diagnose_does_not_claim_reachable_in_mock():
    """mock에서 I2C를 '정상'이라고 보고하면 실물 장애를 감춘다 — None이어야 한다."""
    assert controller.diagnose(mock=True)["i2c"]["reachable"] is None


def test_diagnose_lists_led_pins_and_unassigned():
    d = controller.diagnose(mock=True)
    assert d["leds"] == controller.PIN_MAP
    assert d["leds_unassigned"] == []  # 2026-09-21 배선 확정으로 전부 배정됨


def test_diagnose_exposes_motion_duration():
    assert controller.diagnose(mock=True)["motion_duration_s"] == controller.MOTION_DURATION_S


def test_diagnose_does_not_touch_hardware_in_mock():
    controller.diagnose(mock=True)
    assert "smbus2" not in sys.modules


# ── execute() 전체 경로 ───────────────────────────────────────────────────────
def _command(action: str, speed: int, red: str = "off") -> dict:
    return {
        "command": "slow", "target_signal": "서행",
        "motor": {"action": action, "speed": speed},
        "led": {"red": red, "yellow_left": "off", "yellow_right": "off"},
    }


def test_execute_returns_motor_and_led_results():
    result = controller.execute(_command("forward", 40), mock=True)
    assert result["status"] == "ok"
    assert result["motor"]["status"] == "mocked"
    assert set(result["led"]) == {"red", "yellow_left", "yellow_right"}


def test_execute_echoes_command_and_target_signal():
    result = controller.execute(_command("stop", 0), mock=True)
    assert result["command"] == "slow"
    assert result["target_signal"] == "서행"


def test_execute_survives_missing_fields():
    """계약 위반 메시지가 와도 서비스가 죽으면 안 된다 (web은 실패를 무시하고 진행한다)."""
    result = controller.execute({}, mock=True)
    assert result["status"] in ("ok", "partial")


def test_mock_mode_never_imports_hardware_libraries():
    """mock 경로가 실수로 실물 라이브러리를 건드리면 개발 PC에서 테스트가 깨진다."""
    controller.execute(_command("left", 60, red="blink"), mock=True)
    assert "smbus2" not in sys.modules
    assert "gpiozero" not in sys.modules


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
