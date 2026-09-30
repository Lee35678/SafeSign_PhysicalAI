#!/usr/bin/env python3
"""RPi5 자원 모니터 — 전체 테스트 동안 메모리·CPU·온도·판정 fps를 일정 간격으로 CSV에 남긴다. RPi5에서 실행.

    python3 scripts/rpi/monitor.py                     # 2초 간격, Ctrl+C로 끝내면 요약 출력
    python3 scripts/rpi/monitor.py --interval 1 --duration 1800
    python3 scripts/rpi/monitor.py --summary ~/safesign_logs/monitor_20260930_140000.csv

읽기만 한다 — 장치를 움직이는 요청은 보내지 않는다(vision `/health`, web `/api/state` GET만).
표준 라이브러리만 쓴다(RPi5에 추가 설치 없음). 서비스 프로세스는 명령줄의 `--port`로 찾는다(start_all.sh 기준
web 8000 · vision 8001 · actuation 8002). 프로세스 CPU%는 코어 1개 = 100%, 전체 CPU%는 모든 코어 합 = 100%.
자세한 사용법: document/17_실물실행_스크립트_사용법.md §10
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

SERVICES = {"8000": "web", "8001": "vision", "8002": "actuation"}
VISION_URL = os.getenv("VISION_URL", "http://localhost:8001")
WEB_URL = os.getenv("WEB_URL", "http://localhost:8000")
LOG_ROOT = Path(os.getenv("LOG_ROOT", str(Path.home() / "safesign_logs")))

FIELDS = (["time", "elapsed_s", "temp_c", "throttled", "arm_mhz", "cpu_pct", "load1",
           "mem_used_mb", "mem_avail_mb", "mem_pct", "swap_used_mb"]
          + [f"{s}_{k}" for s in SERVICES.values() for k in ("cpu_pct", "rss_mb", "threads")]
          + ["vision_capture_fps", "vision_result_fps", "vision_frame_age_ms", "preview_viewers",
             "web_state", "web_phase", "web_signal", "web_progress"])

# get_throttled 비트 (RPi 문서): 0~3은 지금 상태, 16~19는 부팅 뒤 한 번이라도 있었음
THROTTLE_BITS = {0: "저전압", 1: "클럭 제한", 2: "스로틀링", 3: "온도 소프트 제한"}


# ── /proc 읽기 (순수 함수 — 문자열을 받아 테스트할 수 있다) ─────────────────────────
def parse_cpu_times(stat_text: str) -> "tuple[int, int]":
    """/proc/stat 첫 줄 → (전체 jiffies, 유휴 jiffies). 유휴 = idle + iowait."""
    fields = stat_text.splitlines()[0].split()[1:]
    values = [int(v) for v in fields[:8]]
    return sum(values), values[3] + values[4]


def parse_meminfo(text: str) -> "dict[str, int]":
    """/proc/meminfo → {키: kB}."""
    out = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[key.strip()] = int(parts[0])
    return out


def parse_pid_stat(text: str) -> "tuple[int, int, int]":
    """/proc/<pid>/stat → (utime+stime 틱, 스레드 수, RSS 페이지). comm에 공백·괄호가 있어도 되게 마지막 ')' 뒤를 자른다."""
    rest = text[text.rindex(")") + 2:].split()
    # rest[0]은 3번째 필드(state) — utime=14, stime=15, num_threads=20, rss=24 (1부터 셈)
    return int(rest[11]) + int(rest[12]), int(rest[17]), int(rest[21])


def service_of(cmdline: "list[str]") -> "str | None":
    """uvicorn 명령줄의 --port 값으로 서비스 이름을 정한다."""
    if not any("uvicorn" in part for part in cmdline):
        return None
    for i, part in enumerate(cmdline):
        if part == "--port" and i + 1 < len(cmdline):
            return SERVICES.get(cmdline[i + 1])
        if part.startswith("--port="):
            return SERVICES.get(part.split("=", 1)[1])
    return None


class Proc:
    def __init__(self, root: Path):
        self.root = root
        self.tick = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        self.page_kb = (os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096) // 1024

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text()

    def cpu_times(self):
        return parse_cpu_times(self.read("stat"))

    def meminfo(self):
        return parse_meminfo(self.read("meminfo"))

    def load1(self) -> float:
        return float(self.read("loadavg").split()[0])

    def services(self) -> "dict[str, int]":
        found = {}
        for entry in self.root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
            except OSError:
                continue                         # 그사이 끝난 프로세스
            name = service_of(cmdline)
            if name and name not in found:
                found[name] = int(entry.name)
        return found

    def pid_stat(self, pid: int):
        return parse_pid_stat(self.read(f"{pid}/stat"))


# ── 장치 값 ──────────────────────────────────────────────────────────────────
def vcgencmd(*args: str) -> str:
    if not shutil.which("vcgencmd"):
        return ""
    try:
        return subprocess.run(["vcgencmd", *args], capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def board_values() -> dict:
    temp = vcgencmd("measure_temp").removeprefix("temp=").removesuffix("'C")
    throttled = vcgencmd("get_throttled").removeprefix("throttled=")
    clock = vcgencmd("measure_clock", "arm").partition("=")[2]
    return {"temp_c": temp, "throttled": throttled,
            "arm_mhz": round(int(clock) / 1e6) if clock.isdigit() else ""}


def get_json(url: str) -> "dict | None":
    try:
        with urllib.request.urlopen(url, timeout=0.8) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001 — 서비스가 없거나 재기동 중이어도 기록은 계속한다
        return None


def service_values() -> dict:
    out = {}
    health = get_json(f"{VISION_URL}/health")
    if health:
        cam = health.get("camera") or {}
        out.update(vision_capture_fps=cam.get("capture_fps", ""), vision_result_fps=cam.get("result_fps", ""),
                   vision_frame_age_ms=cam.get("last_frame_age_ms", ""),
                   preview_viewers=(health.get("preview") or {}).get("viewers", ""))
    state = get_json(f"{WEB_URL}/api/state")
    if state:
        progress = state.get("progress") or {}
        out.update(web_state=state.get("state", ""), web_phase=state.get("phase", ""),
                   web_signal=state.get("target_signal") or "",
                   web_progress=f"{progress.get('current', '')}/{progress.get('total', '')}")
    return out


# ── 기록 ─────────────────────────────────────────────────────────────────────
class Sampler:
    def __init__(self, proc: Proc):
        self.proc = proc
        self.prev_cpu = proc.cpu_times()
        self.prev_pid: "dict[str, tuple[int, int, float]]" = {}   # 서비스 → (pid, 틱, 시각)
        self.started = time.monotonic()

    def sample(self) -> dict:
        now = time.monotonic()
        row = {k: "" for k in FIELDS}
        row["time"] = datetime.now().isoformat(timespec="seconds")
        row["elapsed_s"] = round(now - self.started, 1)

        total, idle = self.proc.cpu_times()
        d_total, d_idle = total - self.prev_cpu[0], idle - self.prev_cpu[1]
        self.prev_cpu = (total, idle)
        if d_total > 0:
            row["cpu_pct"] = round(100 * (d_total - d_idle) / d_total, 1)
        row["load1"] = self.proc.load1()

        mem = self.proc.meminfo()
        total_kb, avail_kb = mem.get("MemTotal", 0), mem.get("MemAvailable", 0)
        row["mem_used_mb"] = round((total_kb - avail_kb) / 1024)
        row["mem_avail_mb"] = round(avail_kb / 1024)
        row["mem_pct"] = round(100 * (total_kb - avail_kb) / total_kb, 1) if total_kb else ""
        row["swap_used_mb"] = round((mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)) / 1024)

        for name, pid in self.proc.services().items():
            try:
                ticks, threads, rss_pages = self.proc.pid_stat(pid)
            except (OSError, ValueError, IndexError):
                continue
            row[f"{name}_rss_mb"] = round(rss_pages * self.proc.page_kb / 1024, 1)
            row[f"{name}_threads"] = threads
            prev = self.prev_pid.get(name)
            if prev and prev[0] == pid and now > prev[2]:     # 재기동으로 pid가 바뀌면 이번 한 번은 비운다
                row[f"{name}_cpu_pct"] = round(100 * (ticks - prev[1]) / self.proc.tick / (now - prev[2]), 1)
            self.prev_pid[name] = (pid, ticks, now)

        row.update(board_values())
        row.update(service_values())
        return row


def record(args) -> Path:
    proc = Proc(Path(args.proc_root))
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    path = Path(args.out) if args.out else LOG_ROOT / f"monitor_{datetime.now():%Y%m%d_%H%M%S}.csv"
    sampler = Sampler(proc)
    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))

    print(f"기록 시작 → {path}  (간격 {args.interval}초, Ctrl+C로 종료)")
    print(f"{'경과':>6} {'온도':>6} {'CPU%':>5} {'메모리':>10}  vision(CPU%/MB)  web(CPU%/MB)  fps   단계")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        next_at = time.monotonic() + args.interval
        while not stop["flag"]:
            time.sleep(max(0.0, next_at - time.monotonic()))
            # 서비스가 재기동 중이면 조회가 시간 초과로 늦어진다 — 밀린 만큼 몰아 찍지 않고 지금부터 다시 센다
            next_at = max(next_at + args.interval, time.monotonic() + args.interval / 2)
            row = sampler.sample()
            writer.writerow(row)
            f.flush()
            print(f"{row['elapsed_s']:>6} {row['temp_c'] or '-':>6} {row['cpu_pct']:>5} "
                  f"{row['mem_used_mb']:>5}MB {row['mem_pct']:>3}%  "
                  f"{row['vision_cpu_pct'] or '-':>5}/{row['vision_rss_mb'] or '-':<6}  "
                  f"{row['web_cpu_pct'] or '-':>5}/{row['web_rss_mb'] or '-':<6} "
                  f"{row['vision_result_fps'] or '-':>5}  {row['web_state']}/{row['web_phase']}", flush=True)
            if args.duration and row["elapsed_s"] >= args.duration:
                break
    print()
    summarize(path)
    return path


# ── 요약 ─────────────────────────────────────────────────────────────────────
def _num(v) -> "float | None":
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _stats(values: "list[float]") -> str:
    if not values:
        return "기록 없음"
    s = sorted(values)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return f"최소 {s[0]:g} · 평균 {sum(s) / len(s):.1f} · P95 {p95:g} · 최대 {s[-1]:g}"


def decode_throttled(hex_value: str) -> str:
    try:
        v = int(hex_value, 16)
    except (TypeError, ValueError):
        return "읽지 못함"
    if v == 0:
        return "0x0 (문제 없음)"
    now = [n for b, n in THROTTLE_BITS.items() if v & (1 << b)]
    past = [n for b, n in THROTTLE_BITS.items() if v & (1 << (b + 16))]
    return f"{hex_value} — 지금: {', '.join(now) or '없음'} / 부팅 뒤 발생: {', '.join(past) or '없음'}"


def summarize(path: Path) -> None:
    with Path(path).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("기록된 행이 없습니다.")
        return
    col = lambda k: [x for x in (_num(r.get(k)) for r in rows) if x is not None]  # noqa: E731
    minutes = (_num(rows[-1]["elapsed_s"]) or 0) / 60
    print(f"요약 — {path}  ({len(rows)}행, {minutes:.1f}분)")
    print(f"  온도(°C)        {_stats(col('temp_c'))}")
    temps = col("temp_c")
    if temps:
        hot = sum(t >= 80 for t in temps) / len(temps) * 100
        print(f"                  80°C 이상 {hot:.0f}% 시간 · 85°C(클럭 제한 시작) 이상 {sum(t >= 85 for t in temps) / len(temps) * 100:.0f}%")
    print(f"  스로틀링        {decode_throttled(rows[-1].get('throttled', ''))}")
    print(f"  ARM 클럭(MHz)   {_stats(col('arm_mhz'))}")
    print(f"  전체 CPU(%)     {_stats(col('cpu_pct'))}")
    print(f"  메모리 사용(MB) {_stats(col('mem_used_mb'))}  ·  스왑 최대 {max(col('swap_used_mb') or [0]):g}MB")
    for name in SERVICES.values():
        rss = col(f"{name}_rss_mb")
        if not rss:
            print(f"  {name:<10}      프로세스를 찾지 못함")
            continue
        grow = rss[-1] - rss[0]
        rate = grow / minutes * 60 if minutes >= 5 else None
        leak = f" · 시간당 {rate:+.0f}MB" if rate is not None else ""
        print(f"  {name:<10} CPU  {_stats(col(f'{name}_cpu_pct'))}  (100 = 코어 1개)")
        print(f"  {'':<10} RSS  {_stats(rss)}  · 처음→끝 {grow:+.1f}MB{leak}")
    print(f"  판정 fps        {_stats(col('vision_result_fps'))}")
    print(f"  캡처 fps        {_stats(col('vision_capture_fps'))}")
    print(f"  영상 시청자     최대 {max(col('preview_viewers') or [0]):g}")

    # 단계별 평균 — 시범/판정/SC-04에서 부하가 어떻게 다른지
    groups: "dict[str, list[dict]]" = {}
    for r in rows:
        key = r.get("web_state") or "(web 응답 없음)"
        if key == "training":
            key = f"training/{r.get('web_phase') or '?'}"
        groups.setdefault(key, []).append(r)
    print("  단계별 평균      단계: 행 수 · 온도 · CPU% · vision CPU% · 판정 fps")
    for key, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        avg = lambda k: (lambda v: f"{sum(v) / len(v):.1f}" if v else "-")(  # noqa: E731
            [x for x in (_num(r.get(k)) for r in rs) if x is not None])
        print(f"    {key:<22} {len(rs):>4} · {avg('temp_c'):>5} · {avg('cpu_pct'):>5} · "
              f"{avg('vision_cpu_pct'):>5} · {avg('vision_result_fps'):>5}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--interval", type=float, default=2.0, help="기록 간격 초 (기본 2)")
    ap.add_argument("--duration", type=float, default=0, help="이 초가 지나면 자동 종료 (기본 0 = Ctrl+C까지)")
    ap.add_argument("--out", help="CSV 경로 (기본 ~/safesign_logs/monitor_<시각>.csv)")
    ap.add_argument("--summary", metavar="CSV", help="기록하지 않고 기존 CSV만 요약")
    ap.add_argument("--proc-root", default="/proc", help=argparse.SUPPRESS)   # 테스트용
    args = ap.parse_args()
    if args.summary:
        summarize(Path(args.summary))
        return 0
    if not Path(args.proc_root, "stat").exists():
        print("/proc/stat이 없습니다 — RPi5(리눅스)에서 실행하세요.", file=sys.stderr)
        return 1
    record(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
