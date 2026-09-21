"""micro:bit와 BLE(Nordic UART Service)로 통신 — USB 시리얼 방식에서 전환됨(2026-09-21).

- micro:bit 하드웨어 UART가 1개뿐이라 `StartbitV2.startbit_Init()` 호출 시 USB 시리얼이 끊기는 것을
  실측으로 확인했다 (doc/aihand_gesture_checklist_final.md 세션 1). RPi5와의 통신은 BLE로 한다.
- 이 micro:bit 펌웨어는 표준 Nordic UART Service와 달리 RX/TX UUID가 반대로 배정되어 있다
  (`6e400003`=쓰기용 RX, `6e400002`=indicate용 TX, 세션 4 실측 — 다른 프로젝트 값을 그대로 쓰면 안 됨).
- 펌웨어(aihand_control.ts)는 TEST_MODE와 무관하게 "G1"~"G7"(제스처 실행, 완료 시 "OK{n}\n" 회신),
  "correct"/"incorrect"(판정 결과, LED에 O/X 2초 표시 후 "OK:CORRECT\n"/"OK:INCORRECT\n" 회신),
  "P<current><total>"(진행 표시, 둘 다 한 자리 숫자, LED 표시 없이 "OKP<current><total>\n"만 회신 —
  진행 표시는 web 화면 쪽 담당)을 처리한다. BTN(버튼 입력)은 아직 펌웨어에 구현되어 있지 않다.
- 손가락 서보 동시 구동 시 전류 급증으로 BLE 연결이 끊길 수 있어(세션 6), 쓰기 실패 시 재연결 후
  1회 재시도한다 (03_인터페이스계약서_v2 §7의 "타임아웃+1회 재시도" 정책과 동일 기조).
  이 현상은 스펙 수치로도 설명된다(doc/hardware_spec.md) — micro:bit v2 보드가 공급 가능한 최대
  전류는 약 300mA인데, 손가락 서보(Hiwonder LFD-01) 1개의 구속(stall) 전류만 최대 700mA(6V 기준)
  이다. 손가락 하나만 걸려도 보드 공급 한계를 넘어서므로, 2개 이상을 동시에 구동하면 전압이 크게
  떨어져 BLE 연결이 끊기는 것은 당연한 결과다 — 완전 순차 이동(finger 간 200ms 텀)이 임시방편이
  아니라 이 보드에서 사실상 유일하게 안전한 구동 방식이다.
"""
import asyncio
import os

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

DEVICE_NAME = os.getenv("MICROBIT_BLE_NAME", "BBC micro:bit")
UART_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # 쓰기용 (RPi5 -> micro:bit)
UART_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # 알림용 (micro:bit -> RPi5)

SCAN_TIMEOUT_S = 5.0
ACK_TIMEOUT_S = 2.0  # 물리 피드백 지연 KPI(P95<=2.0초, 10_PRD_v2 §3 참고) 기준

_client: "BleakClient | None" = None
_reply_event: "asyncio.Event | None" = None
_last_reply: "str | None" = None


def _on_notify(_sender, data: bytearray) -> None:
    global _last_reply
    _last_reply = data.decode("utf-8", errors="replace").strip()
    if _reply_event is not None:
        _reply_event.set()


async def _connect_once() -> bool:
    global _client
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT_S)
    target = next((d for d in devices if d.name and DEVICE_NAME in d.name), None)
    if target is None:
        return False

    client = BleakClient(target.address)
    await client.connect()
    await client.start_notify(UART_TX_UUID, _on_notify)
    _client = client
    return True


async def connect(mock: bool = True) -> bool:
    """micro:bit를 스캔해 BLE 연결. 실패해도 예외를 던지지 않고 False를 반환한다."""
    global _reply_event
    if mock:
        return True

    if _reply_event is None:
        _reply_event = asyncio.Event()

    try:
        return await _connect_once()
    except BleakError:
        return False


async def disconnect() -> None:
    global _client
    if _client is not None and _client.is_connected:
        await _client.disconnect()
    _client = None


def is_connected(mock: bool = True) -> bool:
    if mock:
        return True
    return _client is not None and _client.is_connected


async def _send_line(line: str) -> dict:
    """실물 연결 상태에서 한 줄을 전송하고 응답을 ACK_TIMEOUT_S 동안 대기 (mock 처리는 호출부 담당)."""
    if not is_connected(mock=False) and not await connect(mock=False):
        return {"status": "error", "reason": "microbit_unreachable"}

    async def _write() -> bool:
        try:
            await _client.write_gatt_char(UART_RX_UUID, line.encode())
            return True
        except BleakError:
            return False

    global _last_reply
    _last_reply = None
    _reply_event.clear()

    if not await _write():
        # 세션 6: 동시 구동 시 전압 강하로 연결이 끊길 수 있음 -> 재연결 후 1회 재시도
        if not await connect(mock=False) or not await _write():
            return {"status": "error", "reason": "write_failed"}

    try:
        await asyncio.wait_for(_reply_event.wait(), timeout=ACK_TIMEOUT_S)
        return {"status": "ok", "sent": line.strip(), "reply": _last_reply}
    except asyncio.TimeoutError:
        return {"status": "timeout", "sent": line.strip()}


async def send_gesture(gesture_num: int, mock: bool = True) -> dict:
    """"G{n}\\n" 전송 후 "OK{n}" 응답을 ACK_TIMEOUT_S 동안 대기."""
    if mock:
        return {"status": "mocked", "sent": f"G{gesture_num}"}
    return await _send_line(f"G{gesture_num}\n")


async def send_result(is_correct: bool, mock: bool = True) -> dict:
    """"correct\\n"/"incorrect\\n" 전송 -> LED에 O/X 2초 표시. "OK:CORRECT"/"OK:INCORRECT" 응답 대기."""
    line = "correct\n" if is_correct else "incorrect\n"
    if mock:
        return {"status": "mocked", "sent": line.strip()}
    return await _send_line(line)


async def send_progress(current: int, total: int, mock: bool = True) -> dict:
    """"P<current><total>\\n" 전송 (둘 다 한 자리 숫자 가정, 7종 고정). LED 표시 없음 — 회신만 대기."""
    line = f"P{current}{total}\n"
    if mock:
        return {"status": "mocked", "sent": line.strip()}
    return await _send_line(line)
