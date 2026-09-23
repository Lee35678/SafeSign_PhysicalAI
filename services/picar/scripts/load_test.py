#!/usr/bin/env python3
"""picar 부하 테스트 — 바닥 주행 조건에서 전원·무선·지연을 실측한다.

담당: 송승호 (하드웨어·로봇동작 R)

## 왜 필요한가

1차 벤치(2026-09-23)는 **바퀴를 띄운 무부하 조건**이었다. `vcgencmd get_throttled`가 `0x0`이고
Wi-Fi 실패도 0건이었지만, 바닥에서는 **기동 토크 때문에 전류가 크게 는다**. 배터리가
12.6V → 9.0V로 내려갈수록 강압 여유도 준다 — 시연 후반부가 가장 불리하다
(`document/11_하드웨어설계서_v1.md` §7.1.2, §10 #18).

## 무엇을 재는가

- **왕복 지연** — `03_인터페이스계약서_v2` §5-2의 **타임아웃 500ms**가 현실적인 값인지.
  이 스크립트를 **PC에서 실행하면** 실제 시연 경로(Wi-Fi + HTTP)를 그대로 지나간다.
- **요청 실패** — 모터 구동 중 무선이 끊기는지. 실패 시각을 찍어 모터 동작과 대조할 수 있다.
- **속도 감각** — `--speed`를 바꿔가며 바닥에서의 실제 거동을 본다. 2026-09-23 이 스크립트로
  **서행 20 / 좌·우회전·후진 40 / 상한 50**을 확정했다(`13_picar_하드웨어_검증리포트_v1` §4.5).

> ⚠️ **picar 서비스는 `PICAR_MAX_SPEED`(기본 50)를 넘는 속도를 잘라서 실행한다**(2026-09-24).
> 전원 여유를 보려고 50을 넘겨 돌리려면 RPi4B에서 서비스를 `PICAR_MAX_SPEED=70`처럼 올려 띄워야
> 한다 — 안 그러면 `--speed 70`을 줘도 실제로는 50으로 달린다(스크립트가 경고한다).

`get_throttled`는 Pi 로컬 값이라 이 스크립트가 직접 읽지 않는다. Pi 쪽에서 아래를 같이 띄울 것:

    watch -n1 vcgencmd get_throttled

## 안전

- 주행 명령은 `PICAR_MOTION_DURATION_S`(기본 2초) 뒤 **코프로세서가 자동 정지**한다. 이 스크립트는
  그보다 짧은 간격으로 명령을 갱신해 연속 주행을 만든다 — 즉 **스크립트가 죽으면 2초 안에 멈춘다.**
- Ctrl+C·예외·정상 종료 어디로 끝나든 `finally`에서 **정지 명령을 보낸다**(재시도 포함).
- 그래도 **배터리 스위치를 손 닿는 곳에 두고** 실행할 것. 무선이 끊기면 정지 명령도 못 간다.

## 사용

    # ① 제자리 회전 — 공간이 거의 필요 없고 전류는 가장 크다. 먼저 이것부터.
    python3 load_test.py --url http://192.168.50.10:8000 --pattern spin --speed 40 --duration 30

    # ② 원 주행 — 실제 이동 + 반복 기동 토크
    python3 load_test.py --url http://192.168.50.10:8000 --pattern circle --speed 40 --duration 60
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# picar_command.schema.json의 command/target_signal enum과 일치해야 한다.
_SIGNAL = {
    "stop": ("stop", "정지"),
    "forward": ("slow", "서행"),
    "backward": ("reverse", "후진"),
    "left": ("turn_left", "좌회전_유도"),
    "right": ("turn_right", "우회전_유도"),
}

# (action, 구간 길이 초). 구간 길이는 자동 정지(2초)보다 **짧아야** 주행이 끊기지 않는다.
PATTERNS = {
    # 제자리 회전: 양쪽 바퀴가 반대로 돌며 타이어 횡마찰을 이긴다 — 직진보다 전류가 크고,
    # 차가 제자리에 있어 공간·충돌 위험이 없다. 전원 스트레스 테스트로는 이쪽이 낫다.
    "spin": [("right", 1.5)],
    # 원 주행: 전진과 짧은 선회를 번갈아 다각형으로 원을 근사한다. --arc로 반지름을 조절.
    "circle": [("forward", 1.2), ("right", 0.45)],
    # 사각 주행: 직진 구간이 길어 기동 토크가 더 자주 걸린다.
    "square": [("forward", 1.5), ("right", 0.9)],
}


def _post(url: str, payload: dict, timeout: float) -> tuple[bool, float, str]:
    """(성공 여부, 왕복 초, 사유).

    🔴 **HTTP 200만으로 성공을 판정하지 않는다.** picar는 I2C가 실패해도 프로세스는 살아 있어
    `{"status": "partial", "motor": {"status": "error", "reason": "i2c_failed"}}` 를 **200으로**
    돌려준다. 본문을 읽지 않으면 "명령은 갔는데 모터는 안 돈" 상태를 성공으로 세게 된다 —
    2026-09-23 부하 테스트 #10의 "끝날 때 정지 안 됨"을 이 스크립트가 놓친 이유다.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:      # 서버는 살아 있으나 4xx/5xx
        return False, time.perf_counter() - t0, f"http_{e.code}"
    except Exception as e:                    # 타임아웃·연결 끊김 등
        return False, time.perf_counter() - t0, type(e).__name__

    dt = time.perf_counter() - t0
    try:
        data = json.loads(raw)
    except ValueError:
        return False, dt, "bad_json"

    motor = data.get("motor") or {}
    if motor.get("status") not in ("ok", "mocked"):
        # reason이 없으면 status라도 남긴다 — 원인 없이 실패만 세면 진단이 안 된다.
        return False, dt, f"motor_{motor.get('reason') or motor.get('status') or 'unknown'}"
    return True, dt, ""


def _command(action: str, speed: int) -> dict:
    command, target = _SIGNAL[action]
    # 선회 시 해당 방향 황색 점멸 — 실제 시연과 같은 조합이라 LED 경로도 함께 부하를 받는다.
    led = {"red": "off", "yellow_left": "off", "yellow_right": "off"}
    if action == "left":
        led["yellow_left"] = "blink"
    elif action == "right":
        led["yellow_right"] = "blink"
    return {
        "command": command,
        "target_signal": target,
        "motor": {"action": action, "speed": speed},
        "led": led,
    }


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))
    return ordered[idx]


def main() -> int:
    # Windows 콘솔은 기본이 cp949라 이모지·기호에서 UnicodeEncodeError로 죽는다.
    # 이 스크립트는 **PC에서 실행해 Wi-Fi 경로까지 재는 것**이 주 용도이므로 반드시 필요하다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — 재설정 불가한 스트림이면 그대로 진행
            pass

    ap = argparse.ArgumentParser(description="picar 부하 테스트 (바닥 주행)")
    ap.add_argument("--url", required=True, help="예: http://192.168.50.10:8000")
    ap.add_argument("--pattern", choices=sorted(PATTERNS), default="spin")
    ap.add_argument("--speed", type=int, default=40, help="0~100%% (기본 40 = 일반 주행 확정값. 50 초과는 서버가 자른다)")
    ap.add_argument("--duration", type=float, default=30.0, help="총 주행 초 (기본 30)")
    ap.add_argument("--timeout", type=float, default=2.0,
                    help="요청 타임아웃 초. 계약서 예산은 0.5초지만, 측정이 목적이라 "
                         "기본값을 넉넉히 둬서 '느린 응답'과 '끊김'을 구분한다")
    ap.add_argument("--arc", type=float, default=None,
                    help="circle 패턴의 선회 구간 길이(초). 크게 줄수록 원이 작아진다")
    args = ap.parse_args()

    if not 0 <= args.speed <= 100:
        ap.error("--speed는 0~100 사이여야 한다 (퍼센트)")
    if args.speed > 50:
        print(f"⚠️  --speed {args.speed}: picar 서비스 기본 상한(PICAR_MAX_SPEED=50)을 넘습니다. "
              "서버에서 상한을 올리지 않았다면 실제로는 50으로 달립니다.")
    if args.duration > 300:
        ap.error("--duration은 300초를 넘기지 않는다 (배터리·안전)")

    base = args.url.rstrip("/")
    picar_url = f"{base}/picar"
    steps = list(PATTERNS[args.pattern])
    if args.arc is not None and args.pattern == "circle":
        steps = [("forward", steps[0][1]), ("right", args.arc)]
    for _, seg in steps:
        if seg >= 2.0:
            ap.error(f"구간 길이 {seg}초가 자동 정지(2초) 이상이라 주행이 끊긴다")

    stopping = False

    def _on_signal(signum, _frame):
        nonlocal stopping
        stopping = True
        print(f"\n[{datetime.now():%H:%M:%S}] 신호 {signum} 수신 — 정지 중...", flush=True)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    print(f"패턴={args.pattern} 속도={args.speed}% 시간={args.duration}s 대상={picar_url}")
    print("⚠️  배터리 스위치를 손 닿는 곳에 두세요. Ctrl+C로 즉시 정지합니다.\n")

    latencies: list[float] = []
    failures: list[tuple[str, str]] = []
    sent = 0
    deadline = time.monotonic() + args.duration
    i = 0

    try:
        while not stopping and time.monotonic() < deadline:
            action, seg = steps[i % len(steps)]
            i += 1
            ok, dt, why = _post(picar_url, _command(action, args.speed), args.timeout)
            sent += 1
            if ok:
                # 실패한 요청의 시간은 넣지 않는다 — 타임아웃 값이 섞이면 지연 통계가 거짓이 된다.
                latencies.append(dt)
                print(f"{action:<8} {dt * 1000:6.0f}ms", flush=True)
            else:
                stamp = f"{datetime.now():%H:%M:%S}"
                failures.append((stamp, why))
                print(f"{action:<8} \033[31mFAIL {why}\033[0m ({stamp})", flush=True)

            # 남은 시간보다 구간이 길면 잘라서 정시에 끝낸다.
            remain = deadline - time.monotonic()
            if remain <= 0 or stopping:
                break
            time.sleep(min(seg, remain))
    finally:
        # 어떤 경로로 끝나든 반드시 멈춘다. 무선이 불안정할 수 있으므로 3회 시도.
        print(f"\n[{datetime.now():%H:%M:%S}] 정지 명령 전송...", flush=True)
        stopped = False
        for attempt in range(3):
            ok, _, why = _post(picar_url, _command("stop", 0), max(args.timeout, 2.0))
            if ok:
                stopped = True
                break
            print(f"  정지 {attempt + 1}회차 실패: {why}", flush=True)
        if not stopped:
            print("  \033[31m🔴 정지 명령이 실패했습니다 — 배터리 스위치를 내리세요.\033[0m"
                  "\n     (자동 정지가 살아 있다면 2초 안에 멈춥니다)", flush=True)

    # ── 요약 ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 52)
    print(f"전송 {sent}회 · 실패 {len(failures)}회", end="")
    print(f" ({len(failures) / sent * 100:.1f}%)" if sent else "")
    if latencies:
        ms = [v * 1000 for v in latencies]
        print(f"왕복 지연 (성공 {len(ms)}회 기준)  최소 {min(ms):.0f}ms · 중앙 {_pct(ms, 50):.0f}ms · "
              f"P95 {_pct(ms, 95):.0f}ms · 최대 {max(ms):.0f}ms")
        over = sum(1 for v in ms if v > 500)
        verdict = "✅ 여유" if over == 0 else f"⚠️  {over}건이 초과 ({over / len(ms) * 100:.0f}%)"
        print(f"계약 예산 500ms 대비: {verdict}   (03_인터페이스계약서_v2 §5-2)")
        if failures:
            print("  ※ 실패분은 위 통계에서 제외됐다. **실패는 지연이 아니라 유실**이므로, "
                  "예산 판정보다 실패율을 먼저 볼 것")
    else:
        print("성공한 요청이 없어 지연을 측정하지 못했다 — 연결·IP·서비스 기동을 먼저 확인할 것")
    if failures:
        print("\n실패 시각 — Pi 쪽 get_throttled·모터 동작과 대조할 것:")
        for stamp, why in failures[:20]:
            print(f"  {stamp}  {why}")
        if len(failures) > 20:
            print(f"  ... 외 {len(failures) - 20}건")

    # 자동 정지가 실제로 풀렸는지 확인 — controller.diagnose()가 motion_active를 노출한다.
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=3.0) as r:
            hw = json.loads(r.read()).get("hardware", {})
        active = hw.get("motion_active")
        print(f"\n/health motion_active = {active}"
              f"{'  🔴 자동 정지 타이머가 살아 있습니다' if active else '  ✅ 타이머 없음'}")
        # motion_active는 **타이머 상태**일 뿐 바퀴가 실제로 도는지가 아니다. 정지 쓰기가 실패한
        # 경우는 이 값으로 드러나지 않으므로 last_stop_error를 함께 본다.
        err = hw.get("last_stop_error")
        if err:
            print(f"\033[31m🔴 last_stop_error = {err}\033[0m"
                  "\n   정지 I2C 쓰기가 실패한 이력이 있습니다 — 차량이 실제로 멈췄는지"
                  " 눈으로 확인하세요.")
    except Exception as e:
        print(f"\n/health 확인 실패: {type(e).__name__} — 차량 상태를 눈으로 확인하세요")

    print("=" * 52)
    print("Pi 쪽에서 `vcgencmd get_throttled` 결과를 함께 기록하세요 (0x0이어야 정상).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
