#!/usr/bin/env python3
"""AI Hand 시범 → vision 판정 → picar 동작 교육 루프 — RPi5에서 실행한다 (web 없이).

담당: 송승호 (하드웨어·로봇동작 R)

`aihand_picar_demo.py`(사람이 수신호를 메뉴로 고름)에서 한 단계 나아가, **학습자가 AI Hand를 보고
따라 한 손모양을 vision이 판정**하고 정답일 때만 picar가 반응한다. web 상태머신(조은수)을 거치지
않는 하드웨어 통합 확인용이며, 여기서 검증한 순서·타이밍 규칙은 web 쪽에 스펙으로 전달한다.

## 한 수신호(라운드)의 흐름

    DEMO   : picar 정지 → AI Hand가 목표 수신호 시범 (`OK{n}` 회신 = 손모양 완성)
    ARM    : vision `/reset` 후 ARM_S 동안 판정 무시 — `/latest`에 직전 판정이 남아 있을 수 있다
    LISTEN : picar 순항(전진) 시작, `/latest`를 폴링하며 학습자 손 판정 대기 (최대 --listen-timeout초)
      ├ 정답    → picar를 **먼저** 수신호 동작으로(2초 유지 후 정지) → micro:bit O
      ├ 오답    → picar 정지 → micro:bit X → DEMO부터 재시도
      └ 시간초과 → picar 정지 → micro:bit X → DEMO부터 재시도
    --attempts회(기본 3) 모두 실패하면 그 수신호는 건너뛴다.

- **picar를 micro:bit보다 먼저 보내는 이유**: 물리 피드백 지연 KPI(P95 ≤ 2.0초, PRD §2.1)는 가장 늦게
  끝나는 출력 기준이다. picar는 Wi-Fi라 BLE(micro:bit)와 경합하지 않으므로 먼저 보내고 BLE를 쓴다.
- **순항은 LISTEN 중에만 한다**: 대기 상태가 순항이면 "정지" 수신호의 의미가 드러나지만, 시범·재시범·
  라운드 사이까지 달리면 차가 공간을 벗어난다. 한 시도당 주행은 최대 --listen-timeout초로 묶인다.
- **오답 확정**: vision은 이미 N프레임 연속일 때만 `is_reject=false`를 내지만, 학습자가 손모양을 만드는
  **도중**의 과도 자세가 오답으로 잡히지 않도록 같은 오답 클래스가 WRONG_CONFIRM_S 이상 유지돼야 오답으로
  친다. 정답은 즉시 확정한다.
- `below_tau`/`out_of_distribution`/`no_hand`는 오답으로 세지 않고 안내만 한다(시간초과로 이어질 수 있음).

## 화면이 없으므로

- 학습자에게 지금 수신호 이름을 알려줄 수단은 **콘솔 + AI Hand**뿐이다. 엄지 서보 고장으로 손모양이
  겹치는 쌍(좌회전_유도≈후진, 우회전_유도≈주의)이 있으니 콘솔을 학습자에게 보이게 두거나 진행자가 읽어준다.
- 진행자는 콘솔로 조작한다: `Enter` 다음 수신호 시작 · `s`+Enter 현재 수신호 건너뛰기 · `q`+Enter 종료.
- 끝나면 요약 표를 출력하고, 시도별 기록을 CSV(`--log`)로 남긴다(지연 KPI 분석용).

## ⚠️ AI Hand가 카메라 화각 안에 있으면 안 된다

AI Hand가 시범 자세를 유지한 채 화각에 들어오면 MediaPipe가 로봇 손을 잡아 **학습자 없이 정답 처리**될 수
있다. 시작 시 화각 점검(학습자 손을 치운 상태에서 AI Hand를 '정지' 자세로 펴고 손 검출 여부 확인)을 한다
— `--skip-fov-check`로 끌 수 있다.

## 사용

    # RPi5: vision(:8001, MOCK_CAMERA=false CAMERA_SOURCE=csi)과 actuation(:8002)이 떠 있을 때
    python3 aihand_vision_picar_demo.py --picar http://192.168.50.10:8000

    # picar 없이 AI Hand + vision + micro:bit만 (1차 확인)
    python3 aihand_vision_picar_demo.py --no-picar

    # 일부 수신호만, 라운드 사이 Enter 대기 없이
    python3 aihand_vision_picar_demo.py --picar http://192.168.50.10:8000 --signals 정지,서행 --auto

vision 서비스와 `webcam_check.py`는 CSI 카메라를 동시에 열 수 없다 — 이 스크립트는 vision 서비스를 쓴다.

## 안전

`aihand_picar_demo.py`와 같다 — 종료 경로와 무관하게 `finally`에서 정지 명령을 재시도하고, picar는
heartbeat가 끊기면 2초 안에 스스로 멈춘다. **배터리 스위치를 손 닿는 곳에 둘 것.**
"""
from __future__ import annotations

import argparse
import csv
import queue
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aihand_picar_demo as base  # noqa: E402 — PICAR_COMMANDS·통신 헬퍼를 공유한다

ARM_S = 0.5             # /reset 직후 판정 무시 구간
POLL_S = 0.1            # /latest 폴링 주기
VISION_TIMEOUT_S = 0.5
WRONG_CONFIRM_S = 1.0   # 같은 오답 클래스가 이만큼 유지돼야 오답 확정
FOV_CHECK_S = 2.0       # 화각 점검 관찰 시간

NEGATIVE_CLASS = "negative"  # services/vision/src/cognition/classify.py와 동일

# 학습자에게 보여줄 손모양 — PRD §3.2 확정 스펙(학습 데이터 기준). AI Hand 실물과 다를 수 있다:
# 엄지 서보 고장, 확인_완료는 펌웨어가 아직 "엄지만 펴기"(gesture5).
HAND_SHAPES = {
    "정지": "다섯 손가락 펴기",
    "서행": "검지 + 중지 펴기",
    "좌회전_유도": "엄지 + 검지 펴기",
    "우회전_유도": "엄지 + 소지 펴기",
    "확인_완료": "주먹 (다섯 손가락 접기)",
    "후진": "검지만 펴기",
    "주의": "소지만 펴기",
}

HINTS = {
    "no_hand": "손이 보이지 않습니다 — 카메라 앞에 손을 보여 주세요",
    "normalize_failed": "손이 잘 보이지 않습니다 — 손 전체가 화면에 들어오게",
    "below_tau": "조금 더 정확히 해 주세요",
    "out_of_distribution": "다른 손모양입니다 — AI Hand를 다시 보세요",
}

IDLE = "<idle>"      # 정지 + LED 소등
CRUISE = "<cruise>"  # 전진 순항 + LED 소등

_log = base._log


class PicarDriver(threading.Thread):
    """picar에 '현재 원하는 상태'를 유지시키는 스레드 (aihand_picar_demo.PicarDriver 변형).

    기본 상태를 IDLE/CRUISE 중에서 고를 수 있고, `hold(signal)`은 SIGNAL_HOLD_S 동안 수신호 상태를 유지한
    뒤 **IDLE로** 돌아간다(라운드가 끝났으므로). 주행 상태만 HEARTBEAT_S마다 갱신한다.
    """

    def __init__(self, url: str | None, cruise_speed: int):
        super().__init__(daemon=True)
        self.url = f"{url}/picar" if url else None
        self.cruise_speed = cruise_speed
        self._cv = threading.Condition()
        self._base = IDLE
        self._signal: str | None = None
        self._until = 0.0
        self._stopping = False
        self._last_fail = ""
        self.hold_ack: tuple[bool, float, str] | None = None  # (성공, 완료 시각 monotonic, 실패사유)

    def set_base(self, state: str) -> None:
        with self._cv:
            self._base = state
            self._cv.notify()

    def hold(self, signal_name: str) -> None:
        with self._cv:
            self._signal = signal_name
            self._until = time.monotonic() + base.SIGNAL_HOLD_S
            self._base = IDLE
            self.hold_ack = None
            self._cv.notify()

    def shutdown(self) -> None:
        with self._cv:
            self._stopping = True
            self._cv.notify()

    def _payload(self, state: str) -> dict:
        if state == CRUISE:
            return base._picar_payload(None, self.cruise_speed)
        if state == IDLE:
            return {"command": "stop", "target_signal": "정지",
                    "motor": {"action": "stop", "speed": 0}, "led": dict(base._LED_OFF)}
        return base._picar_payload(state, self.cruise_speed)

    @staticmethod
    def _moving(state: str) -> bool:
        if state == CRUISE:
            return True
        if state == IDLE:
            return False
        return base.PICAR_COMMANDS[state]["motor"]["action"] != "stop"

    def _send(self, state: str, changed: bool) -> bool:
        if self.url is None:
            return True
        ok, dt, why = base._send_picar(self.url, self._payload(state))
        label = {IDLE: "대기(정지)", CRUISE: f"순항(전진 {self.cruise_speed}%)"}.get(state, state)
        if not ok:
            if why != self._last_fail:   # heartbeat마다 같은 실패를 찍지 않는다
                _log(f"🔴 picar {label} 실패: {why}")
            self._last_fail = why
            return False
        if self._last_fail:
            _log(f"picar 복구됨 ({label})")
            self._last_fail = ""
        if changed:
            _log(f"picar ← {label}  {dt * 1000:.0f}ms")
        return True

    def run(self) -> None:
        current: str | None = None
        next_refresh = 0.0
        while True:
            with self._cv:
                if self._stopping:
                    return
                now = time.monotonic()
                if self._signal is not None and now >= self._until:
                    self._signal = None
                holding = self._signal
                desired = holding or self._base
                changed = desired != current
                moving = self._moving(desired)
                if not (changed or (moving and now >= next_refresh)):
                    wakes = ([self._until] if holding else []) + ([next_refresh] if moving else [])
                    self._cv.wait(timeout=max(0.0, min(wakes) - now) if wakes else None)
                    continue

            ok = self._send(desired, changed)
            if changed and holding and desired == holding:
                with self._cv:
                    if self._signal == holding:
                        self.hold_ack = (ok, time.monotonic(), "" if ok else self._last_fail)
            current = desired
            next_refresh = time.monotonic() + base.HEARTBEAT_S


class Operator(threading.Thread):
    """진행자 콘솔 입력을 큐로 넘긴다 — LISTEN 중에도 s/q를 받을 수 있도록."""

    def __init__(self):
        super().__init__(daemon=True)
        self.q: queue.Queue[str] = queue.Queue()

    def run(self) -> None:
        for line in sys.stdin:
            self.q.put(line.strip().lower())
        self.q.put("q")  # EOF

    def poll(self) -> str | None:
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None

    def wait(self) -> str:
        return self.q.get()


class Quit(Exception):
    pass


def _ok(body: dict | None, err: str) -> bool:
    return not err and (body or {}).get("status") in ("ok", "mocked")


def _aihand_demo(aihand: str, sig: str, command: str) -> bool:
    payload = {"command": command, "target_signal": sig, "servo_angles": base._NEUTRAL_ANGLES}
    dt, body, err = base._post(f"{aihand}/command", payload, base.AIHAND_TIMEOUT_S)
    if not _ok(body, err):
        _log(f"🔴 AI Hand 시범 실패: {err or (body or {}).get('reason') or (body or {}).get('status')} "
             f"({dt * 1000:.0f}ms) — 콘솔 안내만으로 진행합니다")
        return False
    _log(f"AI Hand ← {sig} ({command})  {dt * 1000:.0f}ms")
    return True


def _microbit(aihand: str, path: str, payload: dict) -> tuple[bool, float]:
    dt, body, err = base._post(f"{aihand}{path}", payload, base.AIHAND_TIMEOUT_S)
    ok = _ok(body, err)
    if not ok:
        _log(f"🔴 micro:bit {path} 실패: {err or (body or {}).get('status')}")
    return ok, time.monotonic()


def _vision_reset(vision: str) -> None:
    _, _, err = base._post(f"{vision}/reset", {}, VISION_TIMEOUT_S)
    if err:
        _log(f"⚠️  vision /reset 실패({err}) — 직전 연속판정이 남아 있을 수 있습니다")


def _get_json(url: str, timeout: float) -> dict | None:
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001 — 타임아웃·연결 끊김은 호출부가 None으로 처리
        return None


def _listen(vision: str, target: str, timeout_s: float, op: Operator) -> tuple[str, dict | None, float]:
    """(outcome, judgment, 판정 시각 monotonic). outcome: correct | wrong | timeout | skip."""
    deadline = time.monotonic() + timeout_s
    wrong_cls, wrong_since = None, 0.0
    last_hint, last_j, vision_down = None, None, False
    while True:
        cmd = op.poll()
        if cmd == "q":
            raise Quit
        if cmd == "s":
            return "skip", last_j, time.monotonic()

        now = time.monotonic()
        if now >= deadline:
            return "timeout", last_j, now

        j = _get_json(f"{vision}/latest", VISION_TIMEOUT_S)
        if j is None:
            if not vision_down:
                _log("🔴 vision /latest 응답 없음")
            vision_down = True
            time.sleep(POLL_S)
            continue
        if vision_down:
            _log("vision 복구됨")
            vision_down = False
        last_j = j
        now = time.monotonic()

        pred = j.get("predicted_class")
        if not j.get("is_reject", True) and pred != NEGATIVE_CLASS:
            if pred == target:
                return "correct", j, now
            if pred != wrong_cls:
                wrong_cls, wrong_since = pred, now
                _log(f"… {pred}(으)로 보입니다 (match {j.get('match_score')})")
            elif now - wrong_since >= WRONG_CONFIRM_S:
                return "wrong", j, now
        else:
            reason = j.get("reason")
            if reason in ("no_hand", "normalize_failed"):
                wrong_cls = None  # 손을 내렸다 다시 들면 새로 센다
            hint = HINTS.get(reason)
            if hint and reason != last_hint:
                _log(f"… {hint}")
            last_hint = reason if hint else last_hint
        time.sleep(POLL_S)


def _banner(idx: int, total: int, sig: str) -> None:
    line = "═" * 56
    print(f"\n{line}\n  [{idx}/{total}]  {sig}   —   {HAND_SHAPES[sig]}")
    if sig in base.KNOWN_COLLISIONS:
        print(f"  ⚠️  AI Hand 손모양이 '{base.KNOWN_COLLISIONS[sig]}'와 비슷합니다 — 위 설명대로 하세요")
    print(line, flush=True)


def _fov_check(aihand: str, vision: str, op: Operator) -> None:
    print("\n── 화각 점검 ── 학습자는 손을 카메라에서 치워 주세요. Enter를 누르면 AI Hand를 '정지'(손 펴기)로 폅니다.")
    if op.wait() == "q":
        raise Quit
    _aihand_demo(aihand, "정지", "demo")
    _vision_reset(vision)
    time.sleep(ARM_S)
    seen: dict[str, int] = {}
    polls = 0
    end = time.monotonic() + FOV_CHECK_S
    while time.monotonic() < end:
        j = _get_json(f"{vision}/latest", VISION_TIMEOUT_S)
        if j is not None:
            polls += 1
            if j.get("reason") not in ("no_hand", "normalize_failed"):
                key = j.get("predicted_class") if not j.get("is_reject") else f"({j.get('reason')})"
                seen[key] = seen.get(key, 0) + 1
        time.sleep(POLL_S)
    if polls == 0:
        print("🔴 vision 응답이 없어 화각 점검을 못 했습니다.")
    elif seen:
        print(f"🔴 손 없이도 손이 검출됩니다 {seen} — AI Hand(또는 다른 손)가 화각 안에 있습니다. "
              "배치를 바꾸세요. 그대로 진행하면 로봇 손이 정답 처리될 수 있습니다.")
    else:
        print(f"✅ 손 미검출 ({polls}회 폴링) — AI Hand는 화각 밖입니다.")


def _health(aihand: str, vision: str, picar: str | None) -> None:
    vh = _get_json(f"{vision}/health", 3.0) or {"status": "unreachable"}
    ah = base._get(f"{aihand}/health")
    cam = vh.get("camera") or {}
    print(f"vision /health → status={vh.get('status')} camera={cam.get('state')} "
          f"fps={cam.get('capture_fps')} tau={vh.get('tau')} N={vh.get('n_frames')}")
    print(f"aihand /health → {ah}")
    if vh.get("status") != "ok":
        print("🔴 vision이 응답하지 않습니다. RPi5에서 vision 서비스를 먼저 띄우세요.")
    elif cam.get("state") != "running":
        print(f"🔴 카메라 상태가 running이 아닙니다({cam.get('state')}) — MOCK_CAMERA=false CAMERA_SOURCE=csi 확인.")
    if ah.get("mock_hardware") is True:
        print("⚠️  actuation이 MOCK_HARDWARE=true — 서보가 실제로 움직이지 않습니다.")
    mc = ah.get("microbit_connected")
    if isinstance(mc, dict):
        mc = mc.get("_value")
    if mc is False:
        print("🔴 micro:bit가 연결되지 않았습니다. 전원·BLE를 먼저 확인하세요.")
    if picar:
        pc = base._get(f"{picar}/health")
        print(f"picar  /health → {pc}")
        if pc.get("mock_hardware") is True:
            print("⚠️  picar가 MOCK_HARDWARE=true — 모터·LED가 실제로 움직이지 않습니다.")
        if pc.get("status") != "ok":
            print("🔴 picar 상태가 ok가 아닙니다. 계속하면 모터가 돌지 않을 수 있습니다.")


def _ms(a: float | None, b: float | None) -> int | str:
    return "" if a is None or b is None else round((b - a) * 1000)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="AI Hand 시범 → vision 판정 → picar 동작 교육 루프 (RPi5, web 없이)")
    ap.add_argument("--aihand", default="http://localhost:8002", help="actuation 서비스 URL")
    ap.add_argument("--vision", default="http://localhost:8001", help="vision 서비스 URL")
    ap.add_argument("--picar", help="picar 서비스 URL (RPi4B), 예: http://192.168.50.10:8000")
    ap.add_argument("--no-picar", action="store_true", help="picar 없이 AI Hand + vision + micro:bit만")
    ap.add_argument("--cruise-speed", type=int, default=40, help=f"LISTEN 중 순항 속도 0~{base.MAX_SPEED_PCT}%% (기본 40)")
    ap.add_argument("--signals", help="진행할 수신호(쉼표 구분, 기본 7종 전부 PRD 순서)")
    ap.add_argument("--attempts", type=int, default=3, help="수신호당 최대 시도 횟수 (기본 3)")
    ap.add_argument("--listen-timeout", type=float, default=10.0, help="시도당 판정 대기 초 (기본 10)")
    ap.add_argument("--auto", action="store_true", help="라운드 사이 Enter 대기 없이 자동 진행")
    ap.add_argument("--skip-fov-check", action="store_true", help="시작 시 AI Hand 화각 점검 생략")
    ap.add_argument("--log", default=f"aihand_vision_picar_{datetime.now():%Y%m%d_%H%M%S}.csv",
                    help="시도별 기록 CSV 경로")
    args = ap.parse_args()

    if not args.no_picar and not args.picar:
        ap.error("--picar URL을 주거나 --no-picar를 지정하세요")
    if not 0 <= args.cruise_speed <= base.MAX_SPEED_PCT:
        ap.error(f"--cruise-speed는 0~{base.MAX_SPEED_PCT} 사이여야 한다")
    signals = [s.strip() for s in args.signals.split(",")] if args.signals else list(base.SIGNALS)
    unknown = [s for s in signals if s not in base.PICAR_COMMANDS]
    if unknown:
        ap.error(f"알 수 없는 수신호: {unknown} (가능: {', '.join(base.SIGNALS)})")

    aihand = args.aihand.rstrip("/")
    vision = args.vision.rstrip("/")
    picar = None if args.no_picar else args.picar.rstrip("/")

    _health(aihand, vision, picar)
    op = Operator()
    op.start()
    driver = PicarDriver(picar, args.cruise_speed)
    records: list[dict] = []
    summary: list[tuple[str, str, int, int | str]] = []

    def _on_term(signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _on_term)

    try:
        if not args.skip_fov_check:
            _fov_check(aihand, vision, op)
        if picar:
            print("\n⚠️  배터리 스위치를 손 닿는 곳에 두세요. picar는 판정 대기(LISTEN) 중에만 전진합니다.")
        print("조작: Enter=시작/다음 · s=건너뛰기 · q=종료.  Enter를 누르면 시작합니다.")
        if op.wait() == "q":
            raise Quit
        driver.start()

        for idx, sig in enumerate(signals, start=1):
            _banner(idx, len(signals), sig)
            if not args.auto and idx > 1:
                print("Enter = 시작 (picar 위치를 다시 잡을 시간입니다)")
                cmd = op.wait()
                if cmd == "q":
                    raise Quit
                if cmd == "s":
                    summary.append((sig, "건너뜀", 0, ""))
                    continue
            _microbit(aihand, "/progress", {"current": idx, "total": len(signals)})

            result = "실패"
            best: int | str = ""
            attempt = 0
            for attempt in range(1, args.attempts + 1):
                driver.set_base(IDLE)
                _log(f"▶ 시도 {attempt}/{args.attempts} — AI Hand 시범")
                t_demo = time.monotonic()
                demo_ok = _aihand_demo(aihand, sig, "demo" if attempt == 1 else "correct_pose")
                _vision_reset(vision)
                time.sleep(ARM_S)
                driver.set_base(CRUISE)
                _log("따라 해 보세요!")
                t_listen = time.monotonic()
                outcome, j, t_dec = _listen(vision, sig, args.listen_timeout, op)
                j = j or {}

                rec = {"time": datetime.now().isoformat(timespec="milliseconds"), "signal": sig,
                       "attempt": attempt, "outcome": outcome, "predicted": j.get("predicted_class", ""),
                       "match_score": j.get("match_score", ""), "confidence": j.get("confidence", ""),
                       "vision_latency_ms": j.get("latency_ms", ""), "demo_ok": demo_ok,
                       "demo_ms": _ms(t_demo, t_listen), "listen_ms": _ms(t_listen, t_dec),
                       "picar_ok": "", "picar_ms": "", "microbit_ok": "", "microbit_ms": "",
                       "feedback_ms": ""}

                if outcome == "correct":
                    driver.hold(sig)                                   # picar 먼저 (Wi-Fi)
                    mb_ok, t_mb = _microbit(aihand, "/result",        # 그다음 micro:bit (BLE)
                                            {"is_correct": True, "match_score": j.get("match_score", 0)})
                    _log(f"✅ 정답!  match {j.get('match_score')}  conf {j.get('confidence')}")
                    time.sleep(base.SIGNAL_HOLD_S)
                    ack = driver.hold_ack if picar else None
                    t_pc = ack[1] if ack else None
                    rec.update(picar_ok=(ack[0] if ack else ""), picar_ms=_ms(t_dec, t_pc),
                               microbit_ok=mb_ok, microbit_ms=_ms(t_dec, t_mb),
                               feedback_ms=_ms(t_dec, max(t for t in (t_pc, t_mb) if t is not None)))
                    records.append(rec)
                    result, best = "정답", j.get("match_score", "")
                    break

                driver.set_base(IDLE)
                records.append(rec)
                if outcome == "skip":
                    result = "건너뜀"
                    break
                mb_ok, _ = _microbit(aihand, "/result", {"is_correct": False, "match_score": j.get("match_score", 0)})
                if outcome == "wrong":
                    _log(f"❌ 오답 — '{j.get('predicted_class')}'(으)로 판정 (목표: {sig})")
                else:
                    _log(f"⏱  시간 초과 ({args.listen_timeout:.0f}초) — 마지막 상태: {j.get('reason') or j.get('predicted_class') or '-'}")
            else:
                _log(f"➡ {args.attempts}회 실패 — {sig} 건너뜀")
            summary.append((sig, result, attempt, best))
        driver.set_base(IDLE)
        print("\n모든 수신호를 마쳤습니다.")
    except (Quit, EOFError, KeyboardInterrupt):
        print("\n종료합니다.")
    finally:
        driver.shutdown()
        if driver.is_alive():
            driver.join(timeout=2.0)
        if picar:
            base._stop_picar(picar)

    if summary:
        print("\n── 결과 ──")
        for sig, res, n, score in summary:
            print(f"  {sig:<7} {res:<4}  시도 {n}  match {score}")
        correct = sum(1 for s in summary if s[1] == "정답")
        print(f"  정답 {correct}/{len(summary)}")
    if records:
        with open(args.log, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(records[0]))
            w.writeheader()
            w.writerows(records)
        print(f"기록 저장: {args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
