"""micro:bit와 BLE(Nordic UART Service)로 통신 — USB 시리얼 방식에서 전환됨(2026-09-21).

- micro:bit 하드웨어 UART가 1개뿐이라 `StartbitV2.startbit_Init()` 호출 시 USB 시리얼이 끊기는 것을
  실측으로 확인했다 (doc/aihand_gesture_checklist_final.md 세션 1). RPi5와의 통신은 BLE로 한다.
- 이 micro:bit 펌웨어는 표준 Nordic UART Service와 달리 RX/TX UUID가 반대로 배정되어 있다
  (`6e400003`=쓰기용 RX, `6e400002`=indicate용 TX, 세션 4 실측 — 다른 프로젝트 값을 그대로 쓰면 안 됨).
- 펌웨어(aihand_control.ts)는 TEST_MODE와 무관하게 "G1"~"G7"(제스처 실행, 완료 시 "OK{n}\n" 회신),
  "correct"/"incorrect"(판정 결과, "OK:CORRECT\n"/"OK:INCORRECT\n"을 **먼저** 회신한 뒤 LED에 O/X 1초
  표시 — 2026-09-23 ACK-first로 변경. 이전엔 LED 2초 뒤 회신이라 ACK_TIMEOUT_S를 넘겨 매번 timeout이었다),
  "P<current><total>"(진행 표시, 둘 다 한 자리 숫자, LED 표시 없이 "OKP<current><total>\n"만 회신 —
  진행 표시는 web 화면 쪽 담당)을 처리한다. BTN(버튼 입력)은 아직 펌웨어에 구현되어 있지 않다.
- 손가락 서보 동시 구동 시 전류 급증으로 BLE 연결이 끊길 수 있어(세션 6), 쓰기 실패 시 재연결 후
  1회 재시도한다 (03_인터페이스계약서_v2 §7의 "타임아웃+1회 재시도" 정책과 동일 기조).
  이 현상은 전원 구조로 설명된다(document/11_하드웨어설계서_v1.md §4.4) — 7.5V 3A 어댑터 하나가
  Hiwonder 확장보드를 거쳐 micro:bit와 서보 6개를 **같은 레일에서** 먹인다. 손가락 서보(LFD-01)
  구속 전류가 개당 700mA라 5개를 동시에 기동하면 3.5A로 어댑터 용량(3A)을 넘기고, 레일이
  주저앉으면 같은 레일의 micro:bit가 브라운아웃되어 BLE SoftDevice가 죽는다(패닉 070).
  손가락을 하나씩 순서대로 움직이는 것은 이 돌입 전류를 시간축으로 흩어 놓는 방식이다.
  (2026-09-23: 손가락 간 텀 200→150ms. 서보 이동 시간(setPwmServo duration)은 200ms 그대로라
  손가락마다 약 50ms씩 **서보 2개가 겹쳐 움직인다** — 최악 약 1.74A로 어댑터 3A 안이다.)
  (⚠️ 2026-09-21 정정: 이전 주석은 "micro:bit 보드 공급 한계 300mA"를 근거로 들었으나 틀렸다 —
  서보는 micro:bit를 거치지 않는다. 실제 제약은 어댑터 용량이다.)
"""
import asyncio
import contextlib
import logging
import os

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

DEVICE_NAME = os.getenv("MICROBIT_BLE_NAME", "BBC micro:bit")
UART_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # 쓰기용 (RPi5 -> micro:bit)
UART_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # 알림용 (micro:bit -> RPi5)

log = logging.getLogger("uvicorn.error")  # uvicorn 콘솔에 그대로 찍히도록

SCAN_TIMEOUT_S = 5.0
ACK_TIMEOUT_S = 2.0  # 물리 피드백 지연 KPI(P95<=2.0초, 10_PRD_v2 §3 참고) 기준

_client: "BleakClient | None" = None
_reply_event: "asyncio.Event | None" = None
_last_reply: "str | None" = None
# 회신 칸(_last_reply/_reply_event)이 하나뿐이라 전송은 **한 번에 하나만** 한다. 잠금이 없으면 동시 요청
# (예: web이 /command와 /result를 병렬로 보냄)이 서로의 대기 이벤트를 지우고 회신을 가로챈다.
_send_lock: "asyncio.Lock | None" = None


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
        # 이미 다른 쪽(bluetoothctl connect, 죽은 이전 서버 등)에 연결된 micro:bit는 광고를 멈추므로
        # 스캔에 안 잡힌다 — 원인을 좁힐 수 있게 무엇이 보였는지 남긴다.
        seen = sorted({d.name for d in devices if d.name})
        log.warning("micro:bit(%r)가 스캔(%.0f초)에 안 보임 — 보인 기기 %d개: %s",
                    DEVICE_NAME, SCAN_TIMEOUT_S, len(devices), seen[:10])
        return False

    # 주소 문자열이 아니라 **스캔에서 찾은 BLEDevice**를 넘긴다. 문자열을 주면 BlueZ 백엔드가 connect()
    # 안에서 find_device_by_address로 스캔을 한 번 더 돌려 연결 시간 예산을 잡아먹는다.
    client = BleakClient(target)
    try:
        await client.connect()
        await client.start_notify(UART_TX_UUID, _on_notify)
    except Exception:
        # 연결만 되고 notify 등록이 실패하면 BlueZ에 연결이 **남는다**. micro:bit는 연결된 상태라 광고를
        # 멈추고, 이후 스캔에서 영영 안 보인다. 반드시 끊고 나간다.
        with contextlib.suppress(Exception):
            await client.disconnect()
        raise
    _client = client
    log.info("micro:bit BLE 연결됨: %s (%s)", target.name, target.address)
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
    except (BleakError, asyncio.TimeoutError, OSError) as exc:
        # asyncio.TimeoutError(연결 시간 초과)는 BleakError가 아니다 — 안 잡으면 서버 기동 자체가 죽는다
        hint = ""
        if isinstance(exc, asyncio.TimeoutError):
            # 2026-09-23 RPi5 실측: bluetoothctl `scan on`을 켜 둔 채(Discovering: yes)면 스캔에는 잡히는데
            # 연결만 시간 초과됐다. BlueZ 스캔은 클라이언트별이라 bleak가 남의 스캔을 끌 수 없다.
            hint = (" — 다른 프로그램의 BLE 스캔이 켜져 있지 않은지 확인"
                    " (`bluetoothctl show | grep Discovering` → no 여야 함)")
        log.warning("micro:bit BLE 연결 실패: %s: %s%s", type(exc).__name__, exc, hint)
        return False


async def disconnect() -> None:
    global _client
    if _client is not None and _client.is_connected:
        await _client.disconnect()
    _client = None


def is_connected(mock: bool = True) -> bool:
    if mock:
        return True
    # 🔴 반드시 bool()로 감쌀 것. bleak 0.22의 BlueZ 백엔드(RPi5)는 `is_connected`가 bool이 아니라
    # `_DeprecatedIsConnectedReturn` 래퍼 객체를 돌려준다. 그대로 반환하면 FastAPI가 이를
    # `{"_value": true}`로 직렬화하는데, **dict는 값과 무관하게 항상 참**이라 연결이 끊겨도 호출부는
    # "연결됨"으로 읽는다 (2026-09-23 RPi5 실측 로그에서 발견. Windows 백엔드는 bool이라 A-1에서는 안 보였다).
    return _client is not None and bool(_client.is_connected)


async def _send_line(line: str) -> dict:
    """실물 연결 상태에서 한 줄을 전송하고 응답을 ACK_TIMEOUT_S 동안 대기 (mock 처리는 호출부 담당).

    동시에 불려도 순서대로 하나씩 처리한다(_send_lock 주석 참고). micro:bit 펌웨어도 명령을 하나씩
    처리하므로 병렬로 보내 얻는 이득은 없다."""
    global _send_lock
    if _send_lock is None:
        _send_lock = asyncio.Lock()
    async with _send_lock:
        return await _send_line_locked(line)


async def _send_line_locked(line: str) -> dict:
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
    """"correct\\n"/"incorrect\\n" 전송 -> "OK:CORRECT"/"OK:INCORRECT" 응답 대기 (펌웨어가 ACK 후 LED에 O/X 1초 표시)."""
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
