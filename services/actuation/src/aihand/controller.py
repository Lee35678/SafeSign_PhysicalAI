"""AiHandCommand(servo_angles) -> 실제 서보 구동.

TODO(송승호):
- 실물 서보 드라이버 연동 (하드웨어 확정 후 requirements.txt에 라이브러리 추가)
- 02_설계문서_v1 §4 최종 채택 5종별 실측 각도값 반영
"""


def execute(aihand_command: dict, mock: bool = True) -> dict:
    if mock:
        return {"status": "mocked", "received": aihand_command}
    # TODO: 실제 서보 각도 적용
    raise NotImplementedError("실물 서보 제어 미구현")
