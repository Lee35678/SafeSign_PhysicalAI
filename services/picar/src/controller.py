"""picar 모터+LED GPIO 직접 제어. 이 서비스는 **Raspberry Pi 4B 8GB(picar 차체 탑재)** 에서 실행된다.

document/02_설계문서_v2 §1-1, §3-2 참고 — picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에
picar 전용 컴퓨트 보드(RPi4B)로 분리했다(2026-09-18). RPi5의 교육 상태머신이 Wi-Fi(HTTP)로 이 서비스의
`/picar` 엔드포인트를 호출한다 — document/03_인터페이스계약서_v2 §5-2 참고.

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
    raise NotImplementedError("실물 picar GPIO 제어 미구현 — picar/RPi4B 도착 후 구현")
