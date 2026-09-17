"""picar 모터+LED 제어. RPi5가 picar를 GPIO로 직접 구동한다 (document/02_설계문서_v2 §1-1).

document/03_인터페이스계약서_v2 §5-2 picar_command 스키마를 그대로 GPIO 제어 함수 인자로 매핑한다.
같은 RPi5 프로세스 내부 호출이므로 네트워크/시리얼 통신이 아니다 — 이 FastAPI 엔드포인트(/picar)는
로컬 개발 시 서비스 경계를 나누기 위한 것이고, 실물 배포에서는 이 함수를 상태머신이 직접 호출해도 된다.

TODO(송승호):
- 실제 GPIO 핀 배정 (모터 드라이버 IN/EN 핀, LED 4개: 적색×2, 황색×2)
- gpiozero(Motor, LED, PWMLED) 또는 RPi.GPIO로 구현 — gpiozero는 MockFactory로 비-RPi 환경에서도
  임포트/테스트가 가능해 로컬 개발에 유리 (requirements.txt 참고)
"""

# TODO(송승호): 실제 핀 번호로 채우기
PIN_MAP = {
    "motor_left_forward": None,
    "motor_left_backward": None,
    "motor_right_forward": None,
    "motor_right_backward": None,
    "led_red": None,
    "led_yellow_left": None,
    "led_yellow_right": None,
}


def execute(picar_command: dict, mock: bool = True) -> dict:
    """picar_command.schema.json 형식 입력을 받아 모터/LED 구동."""
    if mock:
        return {"status": "mocked", "received": picar_command}
    # TODO: motor = picar_command["motor"]; led = picar_command["led"] 를 실제 GPIO 핀에 적용
    raise NotImplementedError("실물 picar GPIO 제어 미구현 — picar 도착 후 구현")
