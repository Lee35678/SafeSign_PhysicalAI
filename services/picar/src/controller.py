"""picar 모터+LED 제어. 이 서비스는 **Raspberry Pi 4B 8GB(picar 차체 탑재)** 에서 실행된다.

document/02_설계문서_v2 §1-1, §3-2 참고 — picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에
picar 전용 컴퓨트 보드(RPi4B)로 분리했다(2026-09-18). RPi5의 교육 상태머신이 Wi-Fi(HTTP)로 이 서비스의
`/picar` 엔드포인트를 호출한다 — document/03_인터페이스계약서_v2 §5-2 참고.

핀 배정 근거: doc/hardware_pinmap.md(services/actuation) "Raspbot_pinmap" 표(2026-09-21 확인).

- **모터는 Pi의 raw GPIO로 직접 구동하지 않는다.** Raspbot 차체의 모터/서보 포트(S1~S4)는 하위
  코프로세서(MCU)가 직접 구동하고, Pi는 I2C(SCL=BCM3, SDA=BCM2)로 그 코프로세서에 명령만 보낸다.
  실제 구동에는 그 코프로세서의 I2C 명령 프로토콜(레지스터 주소/바이트 포맷)이 필요한데
  hardware_pinmap.md에는 핀 배정만 있고 프로토콜은 없다 — Raspbot 벤더(Hiwonder 등) 라이브러리나
  프로토콜 문서를 구해야 실제 구현이 가능하다(TODO).
- **LED**: 보드에 내장된 LED는 적색(BCM21, `led_red`)·청색(BCM20) 2개뿐이다. PRD가 요구하는
  적색×2+황색×2(`led_yellow_left`/`led_yellow_right` 개별 점멸) 중 황색 2개는 보드에 없어
  외부 LED를 여유 GPIO에 추가 배선하기로 했다(2026-09-21 팀 확인). 정확한 핀 번호는 실물 배선 후
  확정 — 아래 USED_BCM_PINS(Raspbot이 이미 점유한 핀)와 충돌하지 않는 핀으로 고를 것.
"""

# Raspbot 차체가 이미 점유한 BCM 핀 (hardware_pinmap.md 기준) — 외부 황색 LED 배선 시 피할 것.
USED_BCM_PINS = {
    27: "트래킹 Left1", 22: "트래킹 Left2", 17: "트래킹 Right1", 4: "트래킹 Right2",
    9: "적외선 회피 Left(MISO)", 10: "적외선 회피 Right(MOSI)", 25: "적외선 회피 스위치",
    24: "초음파 Echo", 23: "초음파 Trig", 12: "부저", 16: "적외선 수신 센서",
    21: "LED1(적색)", 20: "LED2(청색)", 3: "I2C SCL(모터·서보 코프로세서)", 2: "I2C SDA(모터·서보 코프로세서)",
}

# 모터/서보 코프로세서 I2C 버스 (hardware_pinmap.md "MCU 코프로세서" 행)
I2C_SCL_BCM = 3
I2C_SDA_BCM = 2
I2C_COPROCESSOR_ADDRESS = None  # TODO(송승호): Raspbot 벤더 문서/라이브러리에서 슬레이브 주소 확인

# 보드 내장 LED (hardware_pinmap.md "LED1"/"LED2" 행)
PIN_MAP = {
    "led_red": 21,        # LED1 (적색), 그대로 사용
    "led_yellow_left": None,   # TODO: 외부 LED 배선 후 여유 BCM 핀 배정 (USED_BCM_PINS와 충돌 금지)
    "led_yellow_right": None,  # TODO: 위와 동일
}


def _apply_led(name: str, state: str, mock: bool) -> dict:
    """LED 하나에 off/on/blink 적용. PIN_MAP에 핀이 없으면(mock 무관) 미구현으로 응답."""
    pin = PIN_MAP.get(name)
    if pin is None:
        return {"status": "unsupported", "led": name, "reason": "pin_not_assigned"}
    if mock:
        return {"status": "mocked", "led": name, "pin": pin, "state": state}
    # TODO(송승호): gpiozero.LED(pin)로 on/off, blink는 LED.blink() 사용
    raise NotImplementedError(f"실물 LED({name}) GPIO 제어 미구현")


def execute(picar_command: dict, mock: bool = True) -> dict:
    """picar_command.schema.json 형식 입력을 받아 모터/LED 구동."""
    if mock:
        return {"status": "mocked", "received": picar_command}

    led = picar_command.get("led", {})
    led_result = {
        "red": _apply_led("led_red", led.get("red", "off"), mock),
        "yellow_left": _apply_led("led_yellow_left", led.get("yellow_left", "off"), mock),
        "yellow_right": _apply_led("led_yellow_right", led.get("yellow_right", "off"), mock),
    }

    # TODO(송승호): I2C_COPROCESSOR_ADDRESS로 motor.action/speed를 코프로세서 명령으로 변환해 전송
    raise NotImplementedError(
        "실물 모터 I2C 제어 미구현 — Raspbot 코프로세서 명령 프로토콜 확보 필요. "
        f"LED 처리 결과: {led_result}"
    )
