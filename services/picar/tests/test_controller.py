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


def test_speed_confirmed_values():
    """2026-09-23 바닥 주행으로 확정한 값들 (13_picar_하드웨어_검증리포트_v1 §4.5)."""
    assert controller._speed_pct_to_byte(20) == 51    # 서행
    assert controller._speed_pct_to_byte(40) == 102   # 좌/우회전·후진
    assert controller._speed_pct_to_byte(50) == 128   # 상한


def test_speed_is_clamped_to_byte_range():
    """스키마를 벗어난 값이 와도 I2C에 잘못된 바이트를 쓰지 않는다."""
    assert controller._speed_pct_to_byte(-10) == 0
    assert controller._speed_pct_to_byte(999) == 255


# ── action -> I2C 레지스터/바이트 ──────────────────────────────────────────────
def _i2c(action: str, speed: int = 40) -> dict:
    return controller._apply_motor(action, speed, mock=True)["i2c"]


def test_stop_uses_stop_register_not_motor_register():
    i2c = _i2c("stop", 0)
    assert i2c["reg"] == hex(controller.REG_STOP)
    assert i2c["data"] == [0x00]


def test_forward_drives_both_wheels_forward():
    i2c = _i2c("forward")
    assert i2c["reg"] == hex(controller.REG_MOTOR)
    assert i2c["data"] == [controller.DIR_FORWARD, 102, controller.DIR_FORWARD, 102]


def test_backward_drives_both_wheels_backward():
    assert _i2c("backward")["data"] == [
        controller.DIR_BACKWARD, 102, controller.DIR_BACKWARD, 102,
    ]


def test_left_and_right_are_mirrored_spin_turns():
    """좌/우를 뒤바꾸는 실수는 실물에서 찾기 어려우므로 여기서 고정한다.

    제자리 회전 = 한쪽 전진 + 반대쪽 후진 (services/picar/README.md "좌/우 회전 방식").
    """
    left = _i2c("left")["data"]
    right = _i2c("right")["data"]

    assert left == [controller.DIR_BACKWARD, 102, controller.DIR_FORWARD, 102]
    assert right == [controller.DIR_FORWARD, 102, controller.DIR_BACKWARD, 102]
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
    """3채널 모두 배선 확정됨 — 빈 튜플이 남아 있으면 그 LED는 동작하지 않는다."""
    for name, pins in controller.PIN_MAP.items():
        assert pins, f"{name} 핀 미배정"


def test_red_channel_drives_two_dedicated_pins():
    """적색 2개는 2026-09-22부터 핀을 나눠 쓴다.

    한 핀에 병렬로 물리면 330Ω 기준 약 7.9mA로 핀 기본 구동 한도(8mA)에 붙어버려 5mm LED를
    밝게 쓸 여유가 없다. 다시 1핀으로 합치면 이 테스트가 막는다.
    """
    assert len(controller.PIN_MAP["led_red"]) == 2, controller.PIN_MAP["led_red"]
    assert len(controller.PIN_MAP["led_yellow_left"]) == 1
    assert len(controller.PIN_MAP["led_yellow_right"]) == 1


def test_every_led_channel_responds_in_mock_mode():
    for name in controller.PIN_MAP:
        for state in ("on", "off", "blink"):
            result = controller._apply_led(name, state, mock=True)
            assert result["status"] == "mocked", f"{name}/{state}: {result}"


def test_led_channels_use_distinct_pins():
    """황색 좌/우가 같은 핀이면 좌회전 유도에서 양쪽이 같이 켜져 의미가 사라진다.

    적색 2핀끼리의 중복도 함께 잡는다 — 같은 핀을 두 번 적으면 LED 하나가 안 켜진다.
    """
    pins = [p for pins in controller.PIN_MAP.values() for p in pins]
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
    for name, pins in controller.PIN_MAP.items():
        for pin in pins:
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
    assert d["leds"] == {n: list(p) for n, p in controller.PIN_MAP.items()}
    assert d["leds_unassigned"] == []  # 배선 확정으로 전부 배정됨


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


# ── 정지 경로 (2026-09-23 부하 테스트 #10 회귀 방지) ──────────────────────────
def test_stop_writes_before_cancelling_the_safety_timer(monkeypatch):
    """정지 쓰기가 **성공한 뒤에** 자동 정지 타이머를 걷어야 한다.

    먼저 취소해 버리면 `_write_stop()` 실패 시 안전망까지 사라져 차가 계속 달린다.
    2026-09-23 부하 테스트 #10(speed 50)에서 실제로 "끝날 때 정지 안 됨"이 관측된 결함이다.
    """
    order = []
    monkeypatch.setattr(controller, "_write_stop_retrying", lambda: order.append("write"))
    monkeypatch.setattr(controller, "_cancel_auto_stop", lambda: order.append("cancel"))

    controller._apply_motor("stop", 0, mock=False)

    assert order == ["write", "cancel"], f"순서가 뒤집혔다: {order}"


def test_failed_stop_leaves_the_auto_stop_timer_armed(monkeypatch):
    """정지 쓰기가 실패하면 타이머를 걷지 않고 예외를 올린다 — 늦어도 2초 안에 멈추도록."""
    cancelled = []
    monkeypatch.setattr(controller, "_cancel_auto_stop", lambda: cancelled.append(True))

    def _boom():
        raise OSError("i2c nack")

    monkeypatch.setattr(controller, "_write_stop_retrying", _boom)

    try:
        controller._apply_motor("stop", 0, mock=False)
    except OSError:
        pass
    else:
        raise AssertionError("정지 실패가 예외로 올라오지 않았다")

    assert cancelled == [], "정지에 실패했는데 안전망(자동 정지 타이머)을 걷어냈다"


def test_stop_retries_before_giving_up(monkeypatch):
    """I2C 노이즈로 한 번 실패해도 재시도로 살아나야 한다."""
    attempts = []

    def _flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise OSError("i2c nack")

    monkeypatch.setattr(controller, "_write_stop", _flaky)
    controller._write_stop_retrying()

    assert len(attempts) == 2
    assert controller._last_stop_error is None


def test_stop_failure_is_recorded_for_health(monkeypatch):
    """자동 정지는 타이머 스레드에서 돌아 호출부가 결과를 못 본다 —
    실패 사유가 /health에 드러나지 않으면 '조용한 실패'가 된다."""
    monkeypatch.setattr(controller, "_write_stop", lambda: (_ for _ in ()).throw(OSError("nack")))
    controller._last_stop_error = None

    controller._safe_stop()          # 예외를 삼키되 사유는 남긴다

    assert controller._last_stop_error is not None
    assert "OSError" in controller._last_stop_error
    controller._last_stop_error = None   # 다른 테스트에 새지 않게 되돌린다


def test_gpio_failure_does_not_block_the_motor(monkeypatch):
    """LED(GPIO)가 죽어도 모터 명령 — 특히 정지 — 는 실행돼야 한다 (Docker에 gpiochip 미매핑 등)."""
    def _no_gpio(name, pins):
        raise RuntimeError("BadPinFactory")

    stops = []
    monkeypatch.setattr(controller, "_get_led", _no_gpio)
    monkeypatch.setattr(controller, "_write_stop_retrying", lambda: stops.append(True))

    result = controller.execute(
        {"motor": {"action": "stop", "speed": 0}, "led": {"red": "on"}}, mock=False)

    assert stops == [True]
    assert result["motor"]["status"] == "ok"
    assert result["led"]["red"]["reason"] == "gpio_failed"


# ── 속도 상한 (2026-09-24 — 확정값이 코드 곳곳에 흩어져 옛 값 60이 남아 있었다) ─────────────
def test_default_speed_cap_is_the_confirmed_upper_limit():
    """60은 바닥 주행에서 "너무 빠름"으로 기각, 50이 상한 (리포트 13 §4.5)."""
    assert controller.MAX_SPEED_PCT == 50


def test_speed_above_cap_is_clipped_before_reaching_the_motor():
    """web(feature/web)이 좌/우회전을 60으로 보내고 있다 — 그대로 쓰면 기각한 속도로 제자리 회전한다."""
    result = controller._apply_motor("left", 60, mock=True)
    assert result["status"] == "mocked"
    assert result["i2c"]["data"] == [controller.DIR_BACKWARD, 128, controller.DIR_FORWARD, 128]
    assert result["speed_pct"] == 50
    assert result["speed_capped_from"] == 60, "잘렸다는 표시가 없으면 호출 측이 옛 값을 못 찾는다"


def test_speed_within_cap_is_untouched_and_unmarked():
    result = controller._apply_motor("forward", 20, mock=True)
    assert result["i2c"]["data"][1] == 51
    assert "speed_capped_from" not in result


def test_non_numeric_speed_is_rejected_not_reported_as_i2c_failure():
    """숫자가 아니면 비교에서 TypeError가 나 execute()가 i2c_failed로 오보했을 것이다."""
    result = controller._apply_motor("forward", "fast", mock=True)
    assert result["reason"] == "invalid_speed"
    assert "i2c" not in result


def test_stop_ignores_a_garbage_speed():
    """정지는 속도와 무관하다 — 속도 값이 이상해도 멈춰야 한다."""
    result = controller._apply_motor("stop", "??", mock=True)
    assert result["status"] == "mocked"
    assert result["i2c"]["reg"] == hex(controller.REG_STOP)


def test_diagnose_exposes_speed_cap():
    assert controller.diagnose(mock=True)["max_speed_pct"] == controller.MAX_SPEED_PCT
