"""AiHandCommand(servo_angles) -> 실제 서보 구동.

document/03_인터페이스계약서_v2 §5-1 확정 초기값(실물 캘리브레이션 전 잠정, 2026-09-18):
펴짐(EXTENDED)=170°, 굽힘(CURLED)=10°, 손목중립=90°. AiHand 실물 수령 후 각 손가락이 실제로
펴짐/굽힘으로 보이는지 확인해 조정한다 (구조는 유지, 각도 수치만 보정).
"""

DEFAULT_SERVO_ANGLES = {
    "정지": {"thumb": 170, "index": 170, "middle": 170, "ring": 170, "pinky": 170, "wrist_rotation": 90},
    "서행": {"thumb": 10, "index": 170, "middle": 170, "ring": 10, "pinky": 10, "wrist_rotation": 90},
    "좌회전_유도": {"thumb": 170, "index": 170, "middle": 10, "ring": 10, "pinky": 10, "wrist_rotation": 90},
    "우회전_유도": {"thumb": 170, "index": 10, "middle": 10, "ring": 170, "pinky": 10, "wrist_rotation": 90},
    "확인_완료": {"thumb": 170, "index": 10, "middle": 10, "ring": 10, "pinky": 10, "wrist_rotation": 90},
    "후진": {"thumb": 10, "index": 170, "middle": 10, "ring": 10, "pinky": 10, "wrist_rotation": 90},
    "주의": {"thumb": 10, "index": 10, "middle": 10, "ring": 10, "pinky": 170, "wrist_rotation": 90},
}


def execute(aihand_command: dict, mock: bool = True) -> dict:
    if mock:
        return {"status": "mocked", "received": aihand_command}
    # TODO(송승호): gpiozero.Servo 또는 PCA9685 드라이버로 servo_angles를 실제 각도로 적용
    raise NotImplementedError("실물 서보 제어 미구현")
