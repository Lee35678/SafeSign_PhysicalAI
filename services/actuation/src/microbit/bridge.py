"""USB 시리얼로 micro:bit와 통신.

TODO(송승호):
- pyserial로 실제 포트(/dev/ttyACM0 등) 연결
- shared/schemas/microbit_protocol.md 프로토콜 확정 후 파싱/전송 로직 구현
- BTN:A/B/AB 수신 -> 분야 선택/화면 전환 이벤트로 web에 전달 (연동 방식 협의 필요)
"""


def send_result(payload: dict, mock: bool = True) -> dict:
    is_correct = payload.get("is_correct", False)
    match_score = payload.get("match_score", 0)
    line = f"RESULT:{'OK' if is_correct else 'NG'}:{match_score}\n"

    if mock:
        return {"status": "mocked", "line": line}
    # TODO: serial.Serial(...).write(line.encode())
    raise NotImplementedError("실물 시리얼 통신 미구현")
