#!/usr/bin/env python3
"""AI Hand + picar 연동 데모 — RPi5에서 실행한다.

담당: 송승호 (하드웨어·로봇동작 R)

## 흐름

    ① picar 기본 상태: 전진(순항)
    ② 사용자가 수신호 선택 → actuation `/command` (FastAPI) 로 전송
    ③ AI Hand가 해당 손모양으로 서보 구동 (펌웨어가 동작을 마친 뒤 `OK{n}` 회신)
    ④ picar가 수신호에 맞는 모터·LED 상태로 **2초 동안만** 전환
    ⑤ 다시 ① 전진으로 복귀

web 상태머신(vision 판정)을 거치지 않고 **사람이 수신호를 직접 고르는** 하드웨어 연동 확인용이다.

## 🔑 "계속 전진"을 heartbeat로 만드는 이유

picar는 주행 명령 후 `PICAR_MOTION_DURATION_S`(기본 2초) 뒤 **스스로 정지**한다(스키마에 지속 시간
필드가 없어 둔 안전장치 — `services/picar/src/controller.py`). 그래서 이 스크립트는 전진 명령을
`HEARTBEAT_S`(1초)마다 **다시 보내** 연속 주행을 만든다. `load_test.py`와 같은 방식이며,
**이 스크립트가 죽거나 Wi-Fi가 끊겨도 차는 2초 안에 멈춘다.**

수신호 상태(④)도 같은 규칙을 따른다 — 주행이 있는 수신호(서행·좌/우회전·후진)는 2초 안에 자동 정지가
끼어들지 않도록 heartbeat로 갱신하고, 정지 계열(정지·주의·확인_완료)은 LED 점멸 위상이 리셋되지 않게
**한 번만** 보낸다.

## 속도 — 2026-09-23 바닥 주행 확정값

`PICAR_COMMANDS`의 속도는 **서행 20 / 좌·우회전·후진 40 / 상한 50**이다
(`document/13_picar_하드웨어_검증리포트_v1.md` §4.5). 60은 "너무 빠름"으로 기각됐다.
(2026-09-24까지는 옛 placeholder 서행 30 / 회전 50 / 후진 40이 들어 있었다.)

- 순항 속도는 `--cruise-speed`(기본 40 = 일반 주행)로 바꿀 수 있고, **상한 50을 넘기면 거부**한다.
- **서행은 순항보다 느려야 의미가 있으므로** 순항 속도 이하로 내리면 시작 시 경고한다.
- picar 서비스도 `PICAR_MAX_SPEED`(기본 50)를 넘는 요청을 잘라서 실행한다 — 이 스크립트가 틀린 값을
  보내도 차는 50을 넘지 않는다. 잘렸으면 응답에 `speed_capped_from`이 붙는다.

`확인_완료`는 PRD상 "적색·황색 번갈아 2회 점멸"이지만 스키마가 off/on/blink만 표현하므로 전체 점멸로
근사한다.

## 사용

    # RPi5에서 actuation이 localhost:8002에 떠 있고, picar(RPi4B)가 RPi5 AP의 192.168.50.10:8000일 때
    python3 aihand_picar_demo.py --picar http://192.168.50.10:8000

    # 순항 속도 조정 (0~50)
    python3 aihand_picar_demo.py --picar http://192.168.50.10:8000 --cruise-speed 30

## 안전

- Ctrl+C·`q`·예외 어디로 끝나든 `finally`에서 **정지 명령을 재시도하며** 보낸다.
- 그래도 **배터리 스위치를 손 닿는 곳에 두고** 실행할 것. 무선이 끊기면 정지 명령도 못 간다.
- 서보가 정격 124%(7.46V)로 구동 중이다 — 수신호를 연타하지 말 것.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

MAX_SPEED_PCT = 50  # 2026-09-23 확정 상한 — picar 서비스의 PICAR_MAX_SPEED 기본값과 같다
HEARTBEAT_S = 1.0    # picar 자동 정지(2초)보다 충분히 짧아야 주행이 끊기지 않는다
SIGNAL_HOLD_S = 2.0  # ④ 수신호 상태 유지 시간

# 03_인터페이스계약서_v2 §5-2: 타임아웃 500ms + 1회 재시도
PICAR_TIMEOUT_S = 0.5
PICAR_RETRY = 1

# aihand: 손가락 5개 순차 구동(약 0.75초) + ble_bridge ACK 대기(2초)를 덮을 만큼 둔다.
AIHAND_TIMEOUT_S = 5.0

# aihand_command.schema.json은 servo_angles를 필수로 요구하지만 actuation은 target_signal만으로
# G{n}을 결정한다(aihand_test.py와 동일). 계약을 지키되 값은 중립값으로 채운다.
_NEUTRAL_ANGLES = {"thumb": 90, "index": 90, "middle": 90,
                   "ring": 90, "pinky": 90, "wrist_rotation": 90}

_LED_OFF = {"red": "off", "yellow_left": "off", "yellow_right": "off"}

# 순서가 메뉴 번호이자 펌웨어 G{n} 번호다 (G1=정지 … G7=주의).
# 속도는 2026-09-23 확정값 — 위 docstring "속도" 참고.
PICAR_COMMANDS = {
    "정지": {"command": "stop", "motor": {"action": "stop", "speed": 0},
           "led": {"red": "on", "yellow_left": "off", "yellow_right": "off"}},
    "서행": {"command": "slow", "motor": {"action": "forward", "speed": 20},
           "led": {"red": "off", "yellow_left": "blink", "yellow_right": "blink"}},
    "좌회전_유도": {"command": "turn_left", "motor": {"action": "left", "speed": 40},
               "led": {"red": "off", "yellow_left": "blink", "yellow_right": "off"}},
    "우회전_유도": {"command": "turn_right", "motor": {"action": "right", "speed": 40},
               "led": {"red": "off", "yellow_left": "off", "yellow_right": "blink"}},
    "확인_완료": {"command": "complete", "motor": {"action": "stop", "speed": 0},
             "led": {"red": "blink", "yellow_left": "blink", "yellow_right": "blink"}},
    "후진": {"command": "reverse", "motor": {"action": "backward", "speed": 40},
           "led": dict(_LED_OFF)},
    "주의": {"command": "caution", "motor": {"action": "stop", "speed": 0},
           "led": {"red": "off", "yellow_left": "blink", "yellow_right": "blink"}},
}
SIGNALS = list(PICAR_COMMANDS)

# 엄지 서보 고장으로 손모양이 겹치는 쌍(11_하드웨어설계서 §4.7) — 실패로 오해하지 않게 안내만 한다.
KNOWN_COLLISIONS = {"좌회전_유도": "후진", "후진": "좌회전_유도",
                    "우회전_유도": "주의", "주의": "우회전_유도"}


def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S.%f}"[:-3] + f"] {msg}", flush=True)


def _post(url: str, payload: dict, timeout: float) -> tuple[float, dict | None, str]:
    """(왕복 초, 응답 본문, 오류사유)."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        return time.perf_counter() - t0, None, f"http_{e.code}"
    except Exception as e:  # noqa: BLE001 — 타임아웃·연결 끊김
        return time.perf_counter() - t0, None, type(e).__name__
    dt = time.perf_counter() - t0
    try:
        return dt, json.loads(raw), ""
    except ValueError:
        return dt, None, "bad_json"


def _get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=3.0) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return {"status": f"unreachable ({type(e).__name__})"}


def _picar_payload(signal_name: str | None, cruise_speed: int) -> dict:
    """signal_name이 None이면 ① 순항(전진, LED 소등)."""
    if signal_name is None:
        return {"command": "slow", "target_signal": "서행",   # 스키마 enum에 '순항'이 없어 가장 가까운 값
                "motor": {"action": "forward", "speed": cruise_speed}, "led": dict(_LED_OFF)}
    return {**PICAR_COMMANDS[signal_name], "target_signal": signal_name}


def _send_picar(url: str, payload: dict) -> tuple[bool, float, str]:
    """계약서 §5-2 정책(500ms + 1회 재시도). **본문의 motor.status로 성공을 판정한다** —
    picar는 I2C가 실패해도 HTTP 200에 `partial`을 돌려준다(load_test.py 참고)."""
    why = ""
    dt = 0.0
    for _ in range(1 + PICAR_RETRY):
        dt, body, why = _post(url, payload, PICAR_TIMEOUT_S)
        if not why:
            motor = (body or {}).get("motor") or {}
            if motor.get("status") in ("ok", "mocked"):
                return True, dt, ""
            why = f"motor_{motor.get('reason') or motor.get('status') or 'unknown'}"
    return False, dt, why


class PicarDriver(threading.Thread):
    """picar에 '현재 원하는 상태'를 계속 유지시키는 스레드.

    - 평소: 순항(전진)을 HEARTBEAT_S마다 갱신
    - `hold(signal)` 호출 시: SIGNAL_HOLD_S 동안 수신호 상태, 끝나면 **즉시** 순항 복귀
    """

    def __init__(self, url: str, cruise_speed: int):
        super().__init__(daemon=True)
        self.url = f"{url}/picar"
        self.cruise_speed = cruise_speed
        self._cv = threading.Condition()
        self._signal: str | None = None
        self._until = 0.0
        self._stopping = False
        self._last_fail = ""

    def hold(self, signal_name: str) -> None:
        with self._cv:
            self._signal = signal_name
            self._until = time.monotonic() + SIGNAL_HOLD_S
            self._cv.notify()

    def shutdown(self) -> None:
        with self._cv:
            self._stopping = True
            self._cv.notify()

    def _send(self, payload: dict, label: str, verbose: bool) -> None:
        ok, dt, why = _send_picar(self.url, payload)
        if not ok:
            # heartbeat마다 같은 실패를 찍으면 화면이 묻힌다 — 사유가 바뀔 때만 알린다.
            if why != self._last_fail:
                _log(f"🔴 picar {label} 실패: {why}")
            self._last_fail = why
            return
        if self._last_fail:
            _log(f"picar 복구됨 ({label})")
            self._last_fail = ""
        if verbose:
            _log(f"picar ← {label}  {dt * 1000:.0f}ms")

    def run(self) -> None:
        current: str | None = "<init>"   # 직전에 보낸 상태 (None = 순항)
        next_refresh = 0.0
        while True:
            with self._cv:
                if self._stopping:
                    return
                now = time.monotonic()
                if self._signal is not None and now >= self._until:
                    self._signal = None          # ⑤ 2초 경과 → 순항 복귀
                desired = self._signal
                # 같은 수신호를 연달아 고르면 유지 시간만 새로 센다 — 정지 계열을 다시 보내면
                # LED 점멸 위상이 리셋되므로 재전송하지 않는다.
                changed = desired != current
                moving = desired is None or PICAR_COMMANDS[desired]["motor"]["action"] != "stop"
                due = changed or (moving and now >= next_refresh)
                if not due:
                    wake = self._until if desired is not None else next_refresh
                    if moving:
                        wake = min(wake, next_refresh)
                    self._cv.wait(timeout=max(0.0, wake - now))
                    continue
                until = self._until

            if desired is None:
                self._send(_picar_payload(None, self.cruise_speed),
                           f"순항(전진 {self.cruise_speed}%)", verbose=changed)
            else:
                self._send(_picar_payload(desired, self.cruise_speed),
                           f"{desired} ({until - time.monotonic():.1f}s 유지)", verbose=changed)
            current = desired
            next_refresh = time.monotonic() + HEARTBEAT_S


def _stop_picar(url: str) -> None:
    payload = {"command": "stop", "target_signal": "정지",
               "motor": {"action": "stop", "speed": 0}, "led": dict(_LED_OFF)}
    for _ in range(3):
        ok, _, why = _send_picar(f"{url}/picar", payload)
        if ok:
            _log("picar 정지 완료")
            return
    _log(f"🔴 picar 정지 명령 실패({why}) — 자동 정지(2초)에 맡깁니다. 배터리 스위치를 확인하세요.")


def _send_aihand(url: str, signal_name: str) -> None:
    payload = {"command": "demo", "target_signal": signal_name, "servo_angles": _NEUTRAL_ANGLES}
    dt, body, err = _post(f"{url}/command", payload, AIHAND_TIMEOUT_S)
    status = (body or {}).get("status", "?")
    if err or status not in ("ok", "mocked"):
        reason = err or (body or {}).get("reason", status)
        _log(f"🔴 aihand 실패: {reason}  ({dt * 1000:.0f}ms) — picar는 그대로 진행합니다")
        return
    _log(f"aihand ← {signal_name}  {dt * 1000:.0f}ms  reply={(body or {}).get('reply') or '-'}")


def _menu() -> str:
    lines = ["", "── 수신호 선택 ──"]
    for i, s in enumerate(SIGNALS, start=1):
        m = PICAR_COMMANDS[s]["motor"]
        note = f"  (손모양이 {KNOWN_COLLISIONS[s]}와 겹침)" if s in KNOWN_COLLISIONS else ""
        lines.append(f"  {i}. {s:<7} → picar {m['action']} {m['speed']}%{note}")
    lines.append("  q. 종료")
    return "\n".join(lines)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="AI Hand + picar 연동 데모 (RPi5)")
    ap.add_argument("--aihand", default="http://localhost:8002", help="actuation 서비스 URL")
    ap.add_argument("--picar", required=True, help="picar 서비스 URL (RPi4B), 예: http://192.168.0.42:8000")
    ap.add_argument("--cruise-speed", type=int, default=40, help=f"① 순항 전진 속도 0~{MAX_SPEED_PCT}%% (기본 40 = 일반 주행)")
    args = ap.parse_args()

    if not 0 <= args.cruise_speed <= MAX_SPEED_PCT:
        ap.error(f"--cruise-speed는 0~{MAX_SPEED_PCT} 사이여야 한다 (60 이상은 바닥 주행에서 기각)")
    aihand = args.aihand.rstrip("/")
    picar = args.picar.rstrip("/")

    if PICAR_COMMANDS["서행"]["motor"]["speed"] >= args.cruise_speed:
        print(f"⚠️  서행 속도({PICAR_COMMANDS['서행']['motor']['speed']}%)가 순항({args.cruise_speed}%) "
              "이상입니다 — 서행이 감속으로 보이지 않습니다.")

    ah = _get(f"{aihand}/health")
    pc = _get(f"{picar}/health")
    print(f"aihand /health → {ah}")
    print(f"picar  /health → {pc}")
    if "hardware" in pc and "max_speed_pct" not in pc["hardware"]:   # 응답은 왔는데 상한 필드가 없음
        print("⚠️  picar 서비스에 속도 상한이 없는 이전 버전입니다 — RPi4B에서 pull 후 재시작하세요.")
    if ah.get("mock_hardware") is True:
        print("⚠️  actuation이 MOCK_HARDWARE=true — 서보가 실제로 움직이지 않습니다.")
    mc = ah.get("microbit_connected")
    if isinstance(mc, dict):
        mc = mc.get("_value")
    if mc is False:
        print("🔴 micro:bit가 연결되지 않았습니다. 전원·BLE를 먼저 확인하세요.")
    if pc.get("mock_hardware") is True:
        print("⚠️  picar가 MOCK_HARDWARE=true — 모터·LED가 실제로 움직이지 않습니다.")
    if pc.get("status") != "ok":
        print("🔴 picar 상태가 ok가 아닙니다. 계속하면 모터가 돌지 않을 수 있습니다.")

    print("\n⚠️  배터리 스위치를 손 닿는 곳에 두세요. Enter를 누르면 picar가 전진을 시작합니다.")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        return 1

    driver = PicarDriver(picar, args.cruise_speed)

    def _on_term(signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _on_term)

    try:
        driver.start()
        while True:
            print(_menu())
            choice = input("번호> ").strip().lower()
            if choice in ("q", "quit", "exit"):
                break
            if not choice.isdigit() or not 1 <= int(choice) <= len(SIGNALS):
                print("1~7 또는 q를 입력하세요.")
                continue
            sig = SIGNALS[int(choice) - 1]
            _log(f"▶ G{choice} {sig}")
            # ②③ 손이 수신호를 다 만든 **뒤에** picar가 반응한다 (펌웨어가 동작 완료 후 회신).
            _send_aihand(aihand, sig)
            # ④ picar 2초 유지 → ⑤ 순항 복귀는 driver가 처리
            driver.hold(sig)
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        driver.shutdown()
        driver.join(timeout=2.0)
        _stop_picar(picar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
