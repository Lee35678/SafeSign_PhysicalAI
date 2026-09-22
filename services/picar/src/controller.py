"""picar 모터+LED 제어. 이 서비스는 **Raspberry Pi 4B 8GB(picar 차체 탑재)** 에서 실행된다.

document/02_설계문서_v2 §1-1, §3-2 참고 — picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에
picar 전용 컴퓨트 보드(RPi4B)로 분리했다(2026-09-18). RPi5의 교육 상태머신이 Wi-Fi(HTTP)로 이 서비스의
`/picar` 엔드포인트를 호출한다 — document/03_인터페이스계약서_v2 §5-2 참고.

핀 배정 근거: document/hardware_pinmap.md "Raspbot_pinmap" 표(2026-09-21 확인).

## 모터/서보 — I2C 코프로세서 경유 (2026-09-21 프로토콜 확보)

Raspbot 차체의 모터/서보 포트(S1~S4)는 하위 코프로세서(MCU)가 직접 구동하고, Pi는 I2C(SCL=BCM3,
SDA=BCM2)로 그 코프로세서에 명령만 보낸다. 그 명령 프로토콜을 Yahboom 공식 드라이버 라이브러리
(`YB_Pcb_Car.py`)에서 확보했다:

| 레지스터 | 용도 | 바이트 포맷 |
| --- | --- | --- |
| `0x01` | 모터 구동 | `[좌_방향, 좌_속도, 우_방향, 우_속도]` (방향 0=후진/1=전진, 속도 0~255) |
| `0x02` | 정지 | 단일 바이트 `0x00` |
| `0x03` | 서보 | `[서보ID, 각도(0~180)]` — 이 제품에서는 카메라 팬/틸트용, 주행에는 미사용 |

슬레이브 주소는 **`0x16`**(Raspbot 오리지널 기준). ⚠️ Raspbot **V2**는 `0x2B`를 쓰므로 보드가 다르면
값이 달라진다 — 실물에서 `i2cdetect -y 1`로 먼저 확인하고, 다르면 `RASPBOT_I2C_ADDR` 환경변수로
덮어쓸 것(README "실물 검증 절차" 참고). 우리 보드가 오리지널로 추정되는 근거: hardware_pinmap.md의
초음파·부저·LED·트래킹이 전부 Pi GPIO 직결인데, V2는 이 주변장치들까지 MCU가 I2C로 관장한다.

## 주행 지속 시간 (⚠️ 팀 확인 필요)

`picar_command.schema.json`에는 **주행 지속 시간 필드가 없다.** 명령을 그대로 흘리면 다음 명령이
올 때까지 차가 계속 달린다(벽으로 돌진). 그래서 이 구현은 주행 명령 후 `MOTION_DURATION_S`(기본 2초)
뒤에 자동 정지시킨다 — 안전을 위한 잠정 기본값이며, 실물 주행 후 팀이 확정해야 한다.

## LED (2026-09-21 배선 확정)

보드 내장 LED는 적색(BCM21)·청색(BCM20) 2개뿐이라 설계가 요구하는 적색×2 + 황색×2(총 4개)를
채울 수 없다. **외부 LED 4개를 GPIO 3핀으로 구동**하기로 확정했다.

| 채널 | BCM | 물리 핀 | 외부 LED | 비고 |
| --- | --- | --- | --- | --- |
| `led_red` | 13 | 33 | **적색 2개 (병렬)** | 항상 양쪽 동조라 개별 제어 불필요 → 1핀 공통 |
| `led_yellow_left` | 5 | 29 | 황색 1개 | 좌회전 시 단독 점멸해야 해서 개별 핀 필수 |
| `led_yellow_right` | 6 | 31 | 황색 1개 | 우회전 시 단독 점멸 |

- **적색이 1핀인 근거**: 수신호 7종에서 적색이 쓰이는 경우는 정지(양쪽 점등)와 확인_완료(양쪽 점멸)
  뿐이고, **한쪽만 켜지는 경우가 없다.** 그래서 `picar_command.schema.json`도 `red` 단일 채널이다.
- **내장 적색(BCM21)은 쓰지 않는다.** 내장 LED의 직렬저항 값을 알 수 없어, 그 핀에 외부 2개를 더
  물리면 핀 전류 한도(기본 8mA / 최대 16mA)를 넘길 위험이 있다. 부하가 예측 가능한 여유 핀을 쓴다.
- **저항**: LED마다 개별 직렬저항을 달 것(공통 저항 금지 — 밝기 불균일·전류 쏠림). 적색 Vf≈2.0V
  기준 330Ω이면 개당 약 3.9mA, 적색 2개 합쳐 약 7.9mA로 핀 기본 구동 한도(8mA) 안에 들어온다.
- 위 3개 핀은 `USED_BCM_PINS`(Raspbot 점유)와 충돌하지 않는다 —
  `tests/test_controller.py`가 이를 자동 검사한다.
"""
from __future__ import annotations

import os
import threading

# Raspbot 차체가 이미 점유한 BCM 핀 (hardware_pinmap.md 기준) — 외부 황색 LED 배선 시 피할 것.
USED_BCM_PINS = {
    27: "트래킹 Left1", 22: "트래킹 Left2", 17: "트래킹 Right1", 4: "트래킹 Right2",
    9: "적외선 회피 Left(MISO)", 10: "적외선 회피 Right(MOSI)", 25: "적외선 회피 스위치",
    24: "초음파 Echo", 23: "초음파 Trig", 12: "부저", 16: "적외선 수신 센서",
    21: "LED1(적색)", 20: "LED2(청색)", 3: "I2C SCL(모터·서보 코프로세서)", 2: "I2C SDA(모터·서보 코프로세서)",
}

# ── 모터/서보 코프로세서 I2C (hardware_pinmap.md "MCU 코프로세서" 행) ──────────────
I2C_BUS = 1  # SCL=BCM3 / SDA=BCM2 => Pi의 I2C 버스 1
I2C_ADDR = int(os.getenv("RASPBOT_I2C_ADDR", "0x16"), 16)

REG_MOTOR = 0x01  # [좌_방향, 좌_속도, 우_방향, 우_속도]
REG_STOP = 0x02   # 0x00 한 바이트
REG_SERVO = 0x03  # [서보ID, 각도] — 주행에는 미사용

DIR_BACKWARD = 0
DIR_FORWARD = 1

# 주행 명령 후 자동 정지까지의 시간(초). 스키마에 지속 시간 필드가 없어서 두는 안전장치 —
# 실물 주행 후 팀이 확정할 잠정값이다(위 docstring 참고).
MOTION_DURATION_S = float(os.getenv("PICAR_MOTION_DURATION_S", "2.0"))

# 외부 LED 4개 -> GPIO 3핀 (2026-09-21 확정, 위 docstring "LED" 절 참고).
# 내장 적색(BCM21)·청색(BCM20)은 사용하지 않는다.
PIN_MAP = {
    "led_red": 13,             # 물리 33 — 외부 적색 2개를 병렬로 구동(항상 동조)
    "led_yellow_left": 5,      # 물리 29 — 좌회전 시 단독 점멸
    "led_yellow_right": 6,     # 물리 31 — 우회전 시 단독 점멸
}

_i2c_lock = threading.Lock()
_bus = None
_auto_stop_timer: "threading.Timer | None" = None

# gpiozero LED 객체는 가비지 컬렉션되면 핀이 해제되므로 모듈 전역에 붙들어 둔다.
_leds: dict = {}


# ── I2C 저수준 ────────────────────────────────────────────────────────────────
def _get_bus():
    """smbus2는 RPi4B에서만 설치·동작한다 (비-RPi 개발 PC에서는 임포트 자체가 실패할 수 있음)."""
    global _bus
    if _bus is None:
        from smbus2 import SMBus  # noqa: PLC0415 — 실물 경로에서만 임포트
        _bus = SMBus(I2C_BUS)
    return _bus


def _speed_pct_to_byte(speed_pct: int) -> int:
    """스키마의 speed(0~100%)를 코프로세서가 받는 0~255로 변환."""
    return max(0, min(255, round(speed_pct * 255 / 100)))


def _write_motor(l_dir: int, l_speed: int, r_dir: int, r_speed: int) -> None:
    with _i2c_lock:
        _get_bus().write_i2c_block_data(I2C_ADDR, REG_MOTOR, [l_dir, l_speed, r_dir, r_speed])


def _write_stop() -> None:
    with _i2c_lock:
        _get_bus().write_byte_data(I2C_ADDR, REG_STOP, 0x00)


# ── 모터 ──────────────────────────────────────────────────────────────────────
def _cancel_auto_stop() -> None:
    global _auto_stop_timer
    if _auto_stop_timer is not None:
        _auto_stop_timer.cancel()
        _auto_stop_timer = None


def _schedule_auto_stop() -> None:
    """MOTION_DURATION_S 후 자동 정지 (다음 주행 명령이 오면 취소하고 새로 건다)."""
    global _auto_stop_timer
    _cancel_auto_stop()
    _auto_stop_timer = threading.Timer(MOTION_DURATION_S, _safe_stop)
    _auto_stop_timer.daemon = True
    _auto_stop_timer.start()


def _safe_stop() -> None:
    """타이머 스레드에서 호출 — 실패해도 서비스를 죽이지 않는다."""
    try:
        _write_stop()
    except Exception:  # noqa: BLE001 — I2C 실패로 타이머 스레드가 죽지 않게만 한다
        pass


def _apply_motor(action: str, speed_pct: int, mock: bool) -> dict:
    """motor.action/speed를 코프로세서 명령으로 변환해 전송.

    좌/우 회전은 제자리 회전(한쪽 전진 + 반대쪽 후진)으로 구현했다 — 교육용 시범이라 회전이 눈에
    확실히 보이는 편이 낫다는 판단. 완만한 선회가 필요하면 한쪽 속도를 0으로 두는 방식으로 바꾸면 된다
    (실물 주행 후 조정 대상).
    """
    speed = _speed_pct_to_byte(speed_pct)

    if action == "stop":
        plan = ("stop", None)
    elif action == "forward":
        plan = ("drive", (DIR_FORWARD, speed, DIR_FORWARD, speed))
    elif action == "backward":
        plan = ("drive", (DIR_BACKWARD, speed, DIR_BACKWARD, speed))
    elif action == "left":
        plan = ("drive", (DIR_BACKWARD, speed, DIR_FORWARD, speed))
    elif action == "right":
        plan = ("drive", (DIR_FORWARD, speed, DIR_BACKWARD, speed))
    else:
        return {"status": "error", "reason": "unknown_motor_action", "action": action}

    kind, payload = plan

    if mock:
        return {
            "status": "mocked", "action": action, "speed_pct": speed_pct,
            "i2c": {"addr": hex(I2C_ADDR),
                    "reg": hex(REG_STOP if kind == "stop" else REG_MOTOR),
                    "data": [0x00] if kind == "stop" else list(payload)},
            "auto_stop_s": None if kind == "stop" else MOTION_DURATION_S,
        }

    if kind == "stop":
        _cancel_auto_stop()
        _write_stop()
        return {"status": "ok", "action": "stop"}

    _write_motor(*payload)
    _schedule_auto_stop()
    return {"status": "ok", "action": action, "speed_pct": speed_pct,
            "auto_stop_s": MOTION_DURATION_S}


# ── LED ───────────────────────────────────────────────────────────────────────
def _get_led(name: str, pin: int):
    if name not in _leds:
        from gpiozero import LED  # noqa: PLC0415 — 실물 경로에서만 임포트
        _leds[name] = LED(pin)
    return _leds[name]


LED_STATES = ("off", "on", "blink")  # picar_command.schema.json의 led.* enum과 동일


def _apply_led(name: str, state: str, mock: bool) -> dict:
    """LED 하나에 off/on/blink 적용. PIN_MAP에 핀이 없으면(mock 무관) 미구현으로 응답.

    검증은 mock 분기보다 **먼저** 한다 — mock 응답이 실물과 같은 판정을 내려야 보드 없이 하는
    테스트에 의미가 있다(`_apply_motor`도 같은 순서).
    """
    pin = PIN_MAP.get(name)
    if pin is None:
        return {"status": "unsupported", "led": name, "reason": "pin_not_assigned"}
    if state not in LED_STATES:
        return {"status": "error", "led": name, "reason": "unknown_led_state", "state": state}
    if mock:
        return {"status": "mocked", "led": name, "pin": pin, "state": state}

    led = _get_led(name, pin)
    if state == "on":
        led.on()
    elif state == "off":
        led.off()
    else:  # blink
        led.blink(on_time=0.3, off_time=0.3)  # 비블로킹 — 다음 명령이 오면 덮어쓴다
    return {"status": "ok", "led": name, "pin": pin, "state": state}


# ── 진단 (GET /health 용) ─────────────────────────────────────────────────────
def _probe_i2c() -> dict:
    """코프로세서가 실제로 ACK하는지 확인하는 **비파괴 프로브**.

    `write_quick`은 주소만 보내고 데이터를 쓰지 않으므로 모터가 돌지 않는다.
    """
    info = {"bus": I2C_BUS, "addr": hex(I2C_ADDR)}
    try:
        with _i2c_lock:
            _get_bus().write_quick(I2C_ADDR)
        info["reachable"] = True
    except Exception as exc:  # noqa: BLE001 — 진단 경로는 어떤 실패도 응답으로 돌려준다
        info["reachable"] = False
        info["reason"] = f"{type(exc).__name__}: {exc}"
    return info


def diagnose(mock: bool = True) -> dict:
    """서비스 생존과 **하드웨어 접근 가능 여부를 구분해서** 보고한다.

    `/picar`가 HTTP 200을 돌려줘도 모터가 실제로 돌았다는 보장이 없다. web이 "프로세스는 살아
    있는데 I2C가 죽었다"를 알 수 있어야 시연 중 조용한 실패를 감지할 수 있다.
    """
    if mock:
        i2c = {"bus": I2C_BUS, "addr": hex(I2C_ADDR), "reachable": None, "reason": "mocked"}
    else:
        i2c = _probe_i2c()

    return {
        "i2c": i2c,
        "leds": dict(PIN_MAP),
        "leds_unassigned": [n for n, pin in PIN_MAP.items() if pin is None],
        "motion_duration_s": MOTION_DURATION_S,
        "motion_active": _auto_stop_timer is not None and _auto_stop_timer.is_alive(),
    }


# ── 엔트리포인트 ───────────────────────────────────────────────────────────────
def execute(picar_command: dict, mock: bool = True) -> dict:
    """picar_command.schema.json 형식 입력을 받아 모터/LED 구동.

    LED가 미배선(황색 2개)이거나 I2C가 실패해도 가능한 부분은 처리하고 결과를 함께 돌려준다 —
    호출하는 쪽(web 상태머신)이 picar 실패로 학습 흐름을 막지 않는 정책이기 때문
    (03_인터페이스계약서_v2 §7).
    """
    led = picar_command.get("led", {})
    motor = picar_command.get("motor", {})

    led_result = {
        "red": _apply_led("led_red", led.get("red", "off"), mock),
        "yellow_left": _apply_led("led_yellow_left", led.get("yellow_left", "off"), mock),
        "yellow_right": _apply_led("led_yellow_right", led.get("yellow_right", "off"), mock),
    }

    try:
        motor_result = _apply_motor(motor.get("action", "stop"), motor.get("speed", 0), mock)
    except Exception as exc:  # noqa: BLE001 — I2C 실패를 응답으로 돌려주고 서비스는 계속 산다
        motor_result = {"status": "error", "reason": "i2c_failed", "detail": str(exc)}

    return {
        "status": "ok" if motor_result.get("status") in ("ok", "mocked") else "partial",
        "command": picar_command.get("command"),
        "target_signal": picar_command.get("target_signal"),
        "motor": motor_result,
        "led": led_result,
    }
