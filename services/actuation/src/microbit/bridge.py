"""micro:bit와 USB 시리얼 통신 — document/03_인터페이스계약서_v2 §5-3 확정 프로토콜.

- 115200 baud, 8N1, 라인 기반(`:` 구분자, `\\n` 종료)
- HELLO/READY 핸드셰이크로 연결 확인
- ACK/재전송 없음 — RESULT/PROGRESS는 이벤트마다 재전송되므로 한 줄이 유실돼도 다음 이벤트에서
  자연 복구(self-healing)된다. 물리 피드백 지연 KPI(P95 ≤ 2.0초)를 고려해 왕복 확인을 의도적으로 뺀 설계.
"""
import os

MOCK_HARDWARE = os.getenv("MOCK_HARDWARE", "true").lower() == "true"
SERIAL_PORT = os.getenv("MICROBIT_PORT", "/dev/ttyACM0")
BAUDRATE = 115200

_serial = None  # TODO(송승호): mock=False일 때 serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1) 인스턴스


def connect(mock: bool = True) -> bool:
    """HELLO 전송 -> READY 응답 대기. 연결 성공 여부 반환.

    TODO(송승호): pyserial로 포트를 열고 `HELLO\\n` 전송 후 1초 타임아웃으로 `READY\\n` 대기.
    실패해도 예외를 던지지 말고 False를 반환 — app.py가 1초 간격으로 재시도한다(§7 폴백 정책).
    """
    if mock:
        return True
    raise NotImplementedError("실물 시리얼 연결 미구현")


def send_result(payload: dict, mock: bool = True) -> dict:
    """RESULT:<OK|NG>:<match_score>\\n 전송."""
    is_correct = payload.get("is_correct", False)
    match_score = payload.get("match_score", 0)
    line = f"RESULT:{'OK' if is_correct else 'NG'}:{match_score}\n"
    return _send_line(line, mock)


def send_progress(current: int, total: int, mock: bool = True) -> dict:
    """PROGRESS:<current>:<total>\\n 전송 (02_설계문서_v2 §5 진행 표시)."""
    line = f"PROGRESS:{current}:{total}\n"
    return _send_line(line, mock)


def _send_line(line: str, mock: bool) -> dict:
    if mock:
        return {"status": "mocked", "line": line}
    # TODO: _serial.write(line.encode("ascii"))
    raise NotImplementedError("실물 시리얼 통신 미구현")


def read_button(mock: bool = True):
    """BTN:A|B|AB\\n 수신. 파싱 실패한 줄은 조용히 무시하고 None 반환(self-healing 정책)."""
    if mock:
        return None
    # TODO: 한 줄 읽기 -> "BTN:" 접두사 확인 -> 값 파싱 실패 시 None 반환(에러 응답 없음)
    raise NotImplementedError("실물 시리얼 통신 미구현")
