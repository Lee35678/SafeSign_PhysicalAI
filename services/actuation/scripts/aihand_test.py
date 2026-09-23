#!/usr/bin/env python3
"""AI Hand 실물 검증 — 명령을 순서대로 보내고 **테스트 로그를 자동 작성**한다.

담당: 송승호 (하드웨어·로봇동작 R)

## picar 부하 테스트와 다른 점

picar는 전부 자동 측정이 가능했지만, AI Hand는 **사람이 봐야만 알 수 있는 것**이 핵심이다.

- 손모양이 맞는지 — 응답이 `ok`여도 서보가 안 움직일 수 있다(picar LED와 같은 거짓 양성)
- **동작 완료까지 걸린 시간** — 손가락 5개가 200ms 간격으로 순차 이동하므로 HTTP 응답보다 훨씬 길다

그래서 이 스크립트는 자동화가 아니라 **관찰을 구조화해 받아 적는 도구**다.

## 🔑 왜 지연을 두 번 재는가

KPI "물리 피드백 지연 P95 ≤ 2.0초"를 **어느 시점으로 재느냐**가 팀 결정으로 올라가 있다
(`document/proposals/picar_주행시간_스키마_변경안.md` 결정 2). 현재 근거는 계산값(약 4.2초)뿐이다.

| 측정 | 의미 |
| --- | --- |
| HTTP 응답 시간 (자동) | **펌웨어가 보고한 완료** — 펌웨어는 `setHand()`가 끝난 **뒤에** `OK{n}`을 회신한다 |
| Enter까지의 시간 (사람) | **육안 완료** — 서보가 물리적으로 멈춘 시점 |

> ⚠️ **HTTP 응답은 "반응 시작"이 아니다.** 펌웨어가 손가락 5개를 200ms 간격으로 다 움직인 다음에
> 회신하므로, `/command`의 HTTP 시간에는 손 동작 시간이 이미 들어 있다. "반응 시작"(첫 손가락이
> 움직이는 순간)은 전송 직후 BLE 지연 수십 ms 수준이라 이 도구로는 따로 재지 않는다.
>
> ⚠️ **`/result`는 `timeout`이 정상일 수 있다.** 펌웨어가 LED를 2초 보여준 **뒤에** 회신하는데
> `ble_bridge.ACK_TIMEOUT_S`가 2.0초라 회신이 대기 시간을 넘긴다. **LED가 정상이면 판정은 LED
> 기준으로 한다** — 이 스크립트는 `/result`의 timeout을 자동 실패로 세지 않는다.

이 두 숫자를 실측해야 회의에 계산값이 아닌 근거를 들고 갈 수 있다.

## 사용

    # 실물 (기본: 대화형 — 손을 보며 Enter/판정 입력)
    python3 aihand_test.py --url http://localhost:8002

    # 반복 측정만 (사람 개입 없이 HTTP 지연·회신만, 서보는 실제로 움직인다)
    python3 aihand_test.py --url http://localhost:8002 --auto --repeat 5

결과는 `--out`(기본 `aihand_log.md`)에 **마크다운 표**로 쌓인다. 그대로 리포트에 붙이면 된다.

## ⚠️ 서보 내구

확장보드가 서보에 **7.46V(정격 4.8~6.0V의 약 124%)** 를 인가한다. 반복 구동은 수명을 깎으므로
`--repeat`을 크게 주지 말 것. 기본 대화형은 7종을 1회씩만 돌린다.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

# aihand_command.schema.json은 servo_angles를 필수로 요구하지만, actuation은 target_signal만으로
# G{n}을 결정하고 각도는 쓰지 않는다(controller.py 주석 참고). 계약을 지키되 값은 중립값으로 채운다.
_NEUTRAL_ANGLES = {"thumb": 90, "index": 90, "middle": 90,
                   "ring": 90, "pinky": 90, "wrist_rotation": 90}

# (라벨, 엔드포인트, 페이로드, 관찰 안내)
GESTURES = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]

# 엄지 서보 고장으로 **구별되지 않는 것이 이미 확정된 쌍**이다(11_하드웨어설계서 §4.7).
# 이를 "실패"로 적으면 나중에 읽는 사람이 새 버그로 오해하므로 프롬프트에서 미리 알린다.
KNOWN_COLLISIONS = {
    "좌회전_유도": "후진",   # G3 ↔ G6
    "후진": "좌회전_유도",
    "우회전_유도": "주의",   # G4 ↔ G7
    "주의": "우회전_유도",
}

VERDICTS = {"1": "정상", "2": "기지 제약(감수)", "3": "🔴 실패"}


def _post(base: str, path: str, payload: dict, timeout: float) -> tuple[float, dict | None, str]:
    """(왕복 초, 응답 본문, 오류사유). 본문이 없으면 dict는 None."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{base}{path}", data=body,
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


def _health(base: str) -> dict:
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=3.0) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return {"status": f"unreachable ({type(e).__name__})"}


def _steps(args) -> list[tuple[str, str, dict, str]]:
    """(라벨, path, payload, 관찰 안내)."""
    out: list[tuple[str, str, dict, str]] = []
    for i, sig in enumerate(GESTURES, start=1):
        hint = f"G{i} — 손모양이 `{sig}`에 맞는지"
        if sig in KNOWN_COLLISIONS:
            hint += f"  ⚠️ `{KNOWN_COLLISIONS[sig]}`와 구별 불가(엄지 고장, 기지 제약)"
        out.append((f"G{i} {sig}", "/command",
                    {"command": "demo", "target_signal": sig, "servo_angles": _NEUTRAL_ANGLES},
                    hint))
    if not args.gestures_only:
        out.append(("result correct", "/result", {"is_correct": True, "match_score": 90},
                    "LED에 O 모양이 2초간 뜨는지 · **패닉 070이 뜨지 않는지**"
                    "  (status=timeout은 예상 가능 — LED로 판정)"))
        out.append(("result incorrect", "/result", {"is_correct": False, "match_score": 40},
                    "LED에 X 모양이 2초간 뜨는지  (status=timeout은 예상 가능 — LED로 판정)"))
        out.append(("progress 3/7", "/progress", {"current": 3, "total": 7},
                    "LED 표시는 **없는 것이 정상**. 회신 `OKP37`이 유일한 성공 근거"))
        out.append(("progress 1/7", "/progress", {"current": 1, "total": 7},
                    "회신 `OKP17` 확인"))
    return out


def _ask(prompt: str, default: str = "") -> str:
    try:
        v = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise
    return v or default


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="AI Hand 실물 검증 + 테스트 로그 작성")
    ap.add_argument("--url", default="http://localhost:8002")
    ap.add_argument("--out", default="aihand_log.md")
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="요청 타임아웃 초. 서보 순차 구동이 길어 넉넉히 둔다")
    ap.add_argument("--auto", action="store_true",
                    help="사람 개입 없이 HTTP 지연·회신만 측정 (반복 측정용)")
    ap.add_argument("--repeat", type=int, default=1, help="--auto 에서 반복 횟수 (서보 수명 주의)")
    ap.add_argument("--gestures-only", action="store_true", help="G1~G7만 (result/progress 생략)")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    if args.repeat > 5 and args.auto:
        print("⚠️  --repeat 가 큽니다. 서보가 정격 124%로 구동 중이라 반복은 수명을 깎습니다.")
        if _ask("계속하려면 yes: ") != "yes":
            return 1

    before = _health(base)
    print(f"\n대상 {base}   /health → {before}")
    if before.get("mock_hardware") is True:
        print("⚠️  **MOCK_HARDWARE=true 입니다.** 서보가 실제로 움직이지 않습니다.")
    if before.get("microbit_connected") is False:
        print("🔴 micro:bit가 연결되지 않았습니다. 전원·BLE를 먼저 확인하세요.")

    env = "auto" if args.auto else _ask(
        "\n실행 환경 (예: RPi5 네이티브 / RPi5 Docker / Windows PC): ", "미기재")
    note_boot = "auto" if args.auto else _ask(
        "micro:bit를 이번 회차 전에 재부팅했습니까? (y/n): ", "n")

    rows: list[dict] = []
    steps = _steps(args)

    try:
        for rep in range(args.repeat if args.auto else 1):
            for label, path, payload, hint in steps:
                if not args.auto:
                    print(f"\n── {label} ──\n   관찰: {hint}")
                    _ask("   준비되면 Enter (명령 전송) ")

                # 요청은 **백그라운드**로 보낸다. 펌웨어가 손 동작을 다 끝낸 뒤에 회신하므로,
                # 요청을 블로킹으로 기다리면 "멈추면 Enter" 프롬프트가 동작이 끝난 **뒤에야** 떠서
                # 육안 완료 시간을 잴 수 없다. 전송 즉시 프롬프트를 띄워 동작 중에 누르게 한다.
                box: dict = {}
                t_send = time.perf_counter()
                worker = threading.Thread(
                    target=lambda: box.update(v=_post(base, path, payload, args.timeout)),
                    daemon=True)
                worker.start()

                done_s = ""
                if not args.auto:
                    # 사람이 손 동작이 끝나는 순간 Enter — 이것이 "육안 완료" 시점이다.
                    # setHand()는 엄지→검지→중지→약지→소지 순서라 **소지가 멈추는 순간**이 끝이다.
                    _ask("   → 전송됨. 손(마지막은 소지)이 **완전히 멈추는 순간** Enter ")
                    done_s = f"{time.perf_counter() - t_send:.2f}"

                worker.join(args.timeout + 1.0)
                dt, body, err = box.get("v", (args.timeout, None, "no_response"))
                status = (body or {}).get("status", "?")
                reply = (body or {}).get("reply", "")

                if err:
                    print(f"   🔴 요청 실패: {err}")
                elif status == "timeout" and path == "/result":
                    print(f"   ⚠️  status=timeout ({dt * 1000:.0f}ms) — 펌웨어가 LED 2초 표시 후 회신해"
                          " ACK 대기(2.0s)를 넘긴 것으로 보임. LED가 정상이면 정상 판정")
                elif status not in ("ok", "mocked"):
                    print(f"   🔴 status={status}  reason={(body or {}).get('reason', '')}")
                else:
                    print(f"   HTTP {dt * 1000:.0f}ms   status={status}   reply={reply or '-'}")

                if args.auto:
                    verdict, memo = "auto", ""
                else:
                    v = _ask(f"   판정 [1]{VERDICTS['1']} [2]{VERDICTS['2']} [3]{VERDICTS['3']} : ", "1")
                    verdict = VERDICTS.get(v, VERDICTS["1"])
                    memo = _ask("   비고(패닉코드·이상음·발열 등, 없으면 Enter): ")

                rows.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "rep": rep + 1, "label": label, "path": path,
                    "http_ms": f"{dt * 1000:.0f}", "status": status if not err else err,
                    "reply": reply or "-", "done_s": done_s,
                    "verdict": verdict, "memo": memo,
                })
    except (EOFError, KeyboardInterrupt):
        print("\n중단됨 — 여기까지의 기록을 저장합니다.")

    after = _health(base)

    # ── 로그 파일 작성 ──────────────────────────────────────────────────────
    lines = [
        f"\n### AI Hand 검증 — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"- 실행 환경: **{env}**",
        f"- micro:bit 재부팅 후 첫 회차: {note_boot}",
        f"- `/health` 전: `{before}`",
        f"- `/health` 후: `{after}`",
        "",
        "| 시각 | 회차 | 명령 | HTTP(ms) | status | 회신 | **완료(s)** | 판정 | 비고 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(f"| {r['time']} | {r['rep']} | {r['label']} | {r['http_ms']} | "
                     f"{r['status']} | `{r['reply']}` | {r['done_s']} | {r['verdict']} | {r['memo']} |")

    # 지연 통계는 손 동작(/command)만 — result(LED 2초)·progress(즉시 회신)는 성격이 달라 섞지 않는다.
    http_ms = [float(r["http_ms"]) for r in rows
               if r["status"] in ("ok", "mocked") and r["path"] == "/command"]
    done = [float(r["done_s"]) for r in rows if r["done_s"] not in ("", "auto")]
    lines.append("")
    if http_ms:
        lines.append(f"- **펌웨어 보고 완료**(G1~G7 HTTP): 중앙 {sorted(http_ms)[len(http_ms) // 2]:.0f}ms · "
                     f"최대 {max(http_ms):.0f}ms  ({len(http_ms)}건) — 회신이 손 동작 **이후**라 동작 시간 포함")
    if done:
        lines.append(f"- **완료**(육안): 중앙 {sorted(done)[len(done) // 2]:.2f}s · "
                     f"최대 {max(done):.2f}s  ({len(done)}건)")
        lines.append("  > KPI 2.0초를 **어느 쪽으로 재느냐**가 팀 결정이다 "
                     "(`proposals/picar_주행시간_스키마_변경안.md` 결정 2).")
    # /result의 timeout은 펌웨어 구조상 예상되는 값이라 자동 실패로 세지 않는다(사람 판정은 반영).
    fails = [r for r in rows if r["verdict"].startswith("🔴")
             or (r["status"] not in ("ok", "mocked", "?")
                 and not (r["status"] == "timeout" and r["path"] == "/result"))]
    if fails:
        lines.append(f"- 🔴 **실패 {len(fails)}건** — " +
                     ", ".join(f"{r['label']}({r['status']})" for r in fails[:8]))

    text = "\n".join(lines) + "\n"
    with open(args.out, "a", encoding="utf-8") as f:
        f.write(text)

    print(text)
    print(f"→ {args.out} 에 추가했습니다. 그대로 리포트에 붙이면 됩니다.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
