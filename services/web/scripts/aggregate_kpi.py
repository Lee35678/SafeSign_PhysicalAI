"""온라인 KPI 집계 — web 시행 로그 CSV → 06_테스트·평가리포트 2부 (web 할 일 ②-b).

    cd services/web
    python scripts/aggregate_kpi.py logs/web_trials_*.csv
    python scripts/aggregate_kpi.py logs/web_trials_*.csv ../actuation/aihand_vision_picar_*.csv --out kpi_out

명세는 16_통합테스트_KPI_CI §5.8, 집계 규칙은 §5.7. 오프라인 `services/vision/scripts/evaluate_kpi.py`와
지표 정의를 맞췄다(정답률·오분류율·미판정률의 분모 = 판정 대상 시도, Macro F1은 미판정을 FN으로).

- 입력 파일은 헤더로 종류를 가린다 — web 로그(`mocked` 열 있음)와 web 없는 데모 CSV. **두 종류는 합치지 않고
  따로 집계한다**(비교용).
- 제외(§5.7): `mocked=true` 행, 데모의 `timeout`·`skip`. 행을 지우지 않고 제외 건수를 출력한다.
- 측정 정의(회의안건_KPI측정방법 09-30 회의 + 2026-10-01 지연 측정 결정 D1~D5, 송승호)를 기본값으로 쓰고 옵션으로 바꿀 수 있다.
  - 안건 2(D3): 판정 지연 모수 = 정답 행만 (`--latency-include-wrong`로 오답 포함) — 오답은 1초 유지 대기가 들어가 있다
  - 안건 3: 물리 피드백 지연은 반응 시작(`feedback_ms`)으로 판정하고 완료(`feedback_done_ms`)를 병기
  - D2: 물리 피드백 모수 = 정답 행만(`--feedback-include-wrong`로 전체) — 오답 행은 picar를 부르지 않아 micro:bit만 반영돼 낮게 나온다
  - D1: CSV의 물리 피드백은 web 판정 확정(`t_dec`)부터 잰다. 01의 정의("손 정지 시점부터")에 가깝게
    **손 기준 보수적 상한** = `vision_latency_ms + POLL_WAIT_MS(200, web 폴링 간격) + feedback_ms`를 병기한다(판정은 `feedback_ms`)
  - D4: 지연 "달성"은 P95의 95% 신뢰 상한(순서통계량)이 목표 이하일 때 — 표본이 59개 미만이면 상한을 낼 수 없어 점추정만으로 "잠정 달성"
  - 안건 4: 치명 오분류 = 정지를 **신호 7종 중 다른 신호**로 판정한 건수(미판정은 별도 집계)
- D5: 온라인 측정은 `LOG_SUBJECT`를 쓰지 않는다 — `subject`는 로그인한 학습자의 사원 코드, 게스트 회차는 빈 값
- ⚠️ web 로그에는 below_tau·OOD·과도 자세가 기록되지 않는다(스펙 §7.1, 화면 안내만) — **온라인 미판정률은
  구조적으로 낮게 나오므로 참고치**다(안건 5). 판정 성능 5개의 확정값은 오프라인 경로를 쓴다.
- web 로그의 `timeout`(판정 제한시간 `JUDGING_TIMEOUT_S` 초과, 2026-09-29~)은 기본적으로 데모와 같이 분모에서 빼고
  건수만 적는다(§5.7). `--timeout-as-reject`면 미판정으로 센다 — 16 §6.4 "온라인 미판정률 집계 방법"의 선택지(결정 대기).
- P95는 최근접 순위(nearest-rank) — 오름차순 정렬 뒤 ceil(0.95·n)번째 값(06 §2-3 "95번째로 작은 값").
- `--out DIR`: 06 붙여넣기용 `kpi_report.md`를 쓰고, matplotlib이 있으면 혼동행렬·지연 히스토그램 PNG도 만든다.
"""
from __future__ import annotations

import argparse
import collections
import csv
import math
import sys
from pathlib import Path

SIGNS = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]
CRITICAL = "정지"
REJECT_OUTCOMES = {"below_tau", "out_of_distribution", "timeout"}   # timeout은 --timeout-as-reject일 때만 여기까지 온다
EXCLUDED_OUTCOMES = {"timeout", "skip"}              # 분모에서 빼고 건수만 (§5.7). web timeout은 옵션으로 미판정 처리
TARGETS = {"accuracy": 92.0, "misclass": 3.0, "reject": 5.0, "macro_f1": 0.90,
           "decision_p95_ms": 1000, "feedback_p95_ms": 2000}
SMALL_N = 30
Z = 1.96
POLL_WAIT_MS = 200          # web VISION_POLL_INTERVAL_S 기본 0.2초 — vision 판정 뒤 web이 읽기까지의 최대 대기 (D1)
CONF = 0.95                 # P95 신뢰 상한의 신뢰수준 (D4)


def wilson(k: int, n: int) -> tuple[float, float]:
    """Wilson 95% 신뢰구간 (%, 하한·상한)."""
    if n == 0:
        return 0.0, 100.0
    ph = k / n
    denom = 1 + Z * Z / n
    centre = (ph + Z * Z / (2 * n)) / denom
    half = Z * math.sqrt(ph * (1 - ph) / n + Z * Z / (4 * n * n)) / denom
    return max(0.0, centre - half) * 100, min(1.0, centre + half) * 100


def p95(values: list[float]) -> "float | None":
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def p95_upper(values: list[float]) -> "float | None":
    """P95의 95% 신뢰 상한 — 분포 가정 없는 순서통계량. 오름차순 r번째 값이 진짜 P95 이상일 확률
    = P(Binomial(n, 0.95) ≤ r−1). 이 값이 0.95 이상이 되는 가장 작은 r의 값을 돌려준다. n < 59면 그런 r이 없어 None
    (59개가 모두 목표 이하여야 "P95 ≤ 목표"를 95% 신뢰로 말할 수 있다 — 0.95^59 < 0.05)."""
    n = len(values)
    if n == 0:
        return None
    ordered = sorted(values)
    cumulative = 0.0
    for r in range(1, n + 1):
        cumulative += math.comb(n, r - 1) * 0.95 ** (r - 1) * 0.05 ** (n - r + 1)
        if cumulative >= CONF:
            return ordered[r - 1]
    return None


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _num(value) -> "float | None":
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load(paths: list[Path]) -> dict[str, list[dict]]:
    """{"web": [...], "demo": [...]} — 행마다 `_file`을 붙인다."""
    groups: dict[str, list[dict]] = {"web": [], "demo": []}
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            kind = "web" if "mocked" in (reader.fieldnames or []) else "demo"
            for row in reader:
                row["_file"] = path.name
                groups[kind].append(row)
    return groups


def split_rows(rows: list[dict], include_mocked: bool, timeout_as_reject: bool = False) -> tuple[list[dict], collections.Counter]:
    """(판정 대상 행, 제외 사유별 건수). `timeout_as_reject`면 web `timeout` 행을 미판정으로 남긴다."""
    kept, excluded = [], collections.Counter()
    for r in rows:
        outcome = r.get("outcome", "")
        if not include_mocked and _truthy(r.get("mocked", "")):
            excluded["mocked=true"] += 1
        elif outcome == "timeout" and timeout_as_reject and "mocked" in r and r.get("signal") in SIGNS:
            kept.append({**r, "outcome": "timeout"})
        elif outcome in EXCLUDED_OUTCOMES:
            excluded[outcome] += 1
        elif outcome not in {"correct", "wrong"} | REJECT_OUTCOMES:
            excluded[f"알 수 없는 outcome({outcome!r})"] += 1
        elif r.get("signal") not in SIGNS:
            excluded[f"알 수 없는 signal({r.get('signal')!r})"] += 1
        else:
            kept.append(r)
    return kept, excluded


def classify_rows(rows: list[dict]) -> dict:
    """정답/오분류/미판정·치명·Macro F1 (evaluate_kpi.py kpi_table과 같은 정의)."""
    n = len(rows)
    correct = sum(1 for r in rows if r["outcome"] == "correct")
    rejected = sum(1 for r in rows if r["outcome"] in REJECT_OUTCOMES)
    wrong = n - correct - rejected
    stop_rows = [r for r in rows if r["signal"] == CRITICAL]
    critical = sum(1 for r in stop_rows if r["outcome"] == "wrong" and r.get("predicted") in SIGNS
                   and r["predicted"] != CRITICAL)
    stop_rejected = sum(1 for r in stop_rows if r["outcome"] in REJECT_OUTCOMES)

    f1s = []
    for c in SIGNS:
        tp = sum(1 for r in rows if r["signal"] == c and r["outcome"] == "correct")
        fp = sum(1 for r in rows if r["signal"] != c and r["outcome"] == "wrong" and r.get("predicted") == c)
        fn = sum(1 for r in rows if r["signal"] == c and r["outcome"] != "correct")
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)

    pct = (lambda k: k / n * 100) if n else (lambda k: 0.0)
    return {"n": n, "correct": correct, "wrong": wrong, "rejected": rejected,
            "accuracy": pct(correct), "misclass": pct(wrong), "reject": pct(rejected),
            "macro_f1": sum(f1s) / len(f1s) if n else 0.0,
            "critical": critical, "stop_n": len(stop_rows), "stop_rejected": stop_rejected}


def latencies(rows: list[dict], include_wrong: bool, feedback_include_wrong: bool = False) -> dict:
    decision_rows = [r for r in rows if r["outcome"] == "correct" or (include_wrong and r["outcome"] == "wrong")]
    out = {"decision": [v for r in decision_rows if (v := _num(r.get("vision_latency_ms"))) is not None]}
    fb_rows = rows if feedback_include_wrong else [r for r in rows if r["outcome"] == "correct"]   # D2
    out["feedback"] = [v for r in fb_rows if (v := _num(r.get("feedback_ms"))) is not None]
    out["feedback_done"] = [v for r in fb_rows if (v := _num(r.get("feedback_done_ms"))) is not None]
    out["feedback_hand"] = [vl + POLL_WAIT_MS + fb for r in fb_rows                                 # D1
                            if (vl := _num(r.get("vision_latency_ms"))) is not None
                            and (fb := _num(r.get("feedback_ms"))) is not None]
    return out


def confusion(rows: list[dict]) -> tuple[list[str], dict]:
    cols = SIGNS + ["미판정"]
    table = {s: collections.Counter() for s in SIGNS}
    for r in rows:
        if r["outcome"] in REJECT_OUTCOMES:
            table[r["signal"]]["미판정"] += 1
        elif r["outcome"] == "correct":
            table[r["signal"]][r["signal"]] += 1
        else:
            table[r["signal"]][r.get("predicted") if r.get("predicted") in SIGNS else "미판정"] += 1
    return cols, table


def _nflag(n: int) -> str:
    return f" (n={n})" if n < SMALL_N else ""


def verdict_rows(k: dict, lat: dict, rejects_recorded: bool = True) -> list[tuple[str, str, str, str]]:
    """06 §2-1 요약표 행: (지표, 목표, 실측, 달성).

    `rejects_recorded=False`(web 로그): below_tau·OOD가 기록되지 않아 미판정률이 구조적으로 0이므로 달성 판정을 내지 않는다."""
    n = k["n"]
    rows = []

    def rate(name, key, count, target, higher_better):
        lo, hi = wilson(count, n)
        point = k[key]
        meets = point >= target if higher_better else point <= target
        bound_ok = lo >= target if higher_better else hi <= target
        status = "미달" if not meets else ("달성" if bound_ok else "잠정 달성")
        ci = f"하한 {lo:.1f}%" if higher_better else f"상한 {hi:.1f}%"
        goal = f"≥ {target:g}%" if higher_better else f"≤ {target:g}%"
        rows.append((name, goal, f"{point:.1f}% ({count}/{n}, Wilson {ci}){_nflag(n)}", status))

    rate("정답률", "accuracy", k["correct"], TARGETS["accuracy"], True)
    rate("오분류율", "misclass", k["wrong"], TARGETS["misclass"], False)
    rate("미판정률 (온라인 참고치)", "reject", k["rejected"], TARGETS["reject"], False)
    if not rejects_recorded:
        rows[-1] = rows[-1][:3] + ("판정 불가 (미기록)",)
    f1_ok = k["macro_f1"] >= TARGETS["macro_f1"]
    rows.append(("Macro F1", "≥ 0.90", f"{k['macro_f1']:.3f}{_nflag(n)}", "달성" if f1_ok else "미달"))
    # 목표가 0건이라 Wilson 상한은 언제나 0보다 크다 → 관측 0건이어도 "잠정 달성"(§5.7, 06 §2-1과 같은 규칙)
    _, crit_hi = wilson(k["critical"], k["stop_n"])
    rows.append(("치명 오분류", "0건",
                 f"{k['critical']}건 / 정지 {k['stop_n']}시도 (Wilson 상한 {crit_hi:.1f}%, 정지→미판정 "
                 f"{k['stop_rejected']}건 별도){_nflag(k['stop_n'])}",
                 "미달" if k["critical"] else ("잠정 달성" if k["stop_n"] else "측정 없음")))

    def lat_row(name, values, target, extra=""):
        v = p95(values)
        if v is None:
            rows.append((name, f"≤ {target / 1000:g}초", "기록 없음", "측정 없음"))
            return
        upper = p95_upper(values)                                   # D4
        bound = f"95% 상한 {upper / 1000:.3f}초" if upper is not None else "n<59 — 95% 상한 계산 불가"
        status = "미달" if v > target else ("달성" if upper is not None and upper <= target else "잠정 달성")
        rows.append((name, f"≤ {target / 1000:g}초", f"{v / 1000:.3f}초 (n={len(values)}, {bound}){extra}", status))

    lat_row("판정 지연 (P95)", lat["decision"], TARGETS["decision_p95_ms"])
    extra = ""
    done, hand = p95(lat["feedback_done"]), p95(lat.get("feedback_hand", []))
    if done is not None:
        extra += f" · 완료 기준 {done / 1000:.3f}초"
    if hand is not None:
        extra += f" · 손 기준 상한 {hand / 1000:.3f}초"
    lat_row("물리 피드백 지연 (P95, 반응 시작)", lat["feedback"], TARGETS["feedback_p95_ms"], extra)
    return rows


def md_table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def report(kind: str, rows: list[dict], excluded: collections.Counter, files: list[str],
           include_wrong: bool, feedback_include_wrong: bool = False) -> tuple[str, dict, dict]:
    k = classify_rows(rows)
    lat = latencies(rows, include_wrong, feedback_include_wrong)
    out = [f"## {'web 시행 로그 (온라인)' if kind == 'web' else 'web 없는 데모 CSV (비교용)'}", ""]
    out.append(f"- 입력: {', '.join(sorted(set(files)))}")
    out.append(f"- 판정 대상 {k['n']}행 · 제외 {sum(excluded.values())}행"
               + (f" ({', '.join(f'{r} {c}' for r, c in excluded.items())})" if excluded else ""))
    out.append(f"- 정의: 판정 지연 모수 = {'정답+오답' if include_wrong else '정답 행만'}(안건 2), "
               f"물리 피드백 모수 = {'전체' if feedback_include_wrong else '정답 행만'}(D2) · 반응 시작 판정·완료 병기(안건 3) · "
               f"손 기준 상한 = 판정 지연 + {POLL_WAIT_MS}ms + 반응 시작(D1), "
               "치명 = 정지→다른 신호(안건 4), P95 = nearest-rank · 달성 = 95% 상한 ≤ 목표(D4, n≥59)")
    if kind == "web":
        guests = sum(1 for r in rows if not r.get("subject"))
        if guests:
            out.append(f"- 대상자 미기재 {guests}행 — 로그인하지 않은(게스트) 회차. 온라인 측정은 LOG_SUBJECT 없이 사원 코드로 구분한다(D5)")
    total = k["accuracy"] + k["misclass"] + k["reject"]
    out.append(f"- 합계 확인: 정답률 + 오분류율 + 미판정률 = {total:.1f}%" + ("" if k["n"] == 0 or abs(total - 100) < 0.05
                                                                     else "  ⚠️ 100%가 아님"))
    if kind == "web" and k["rejected"] == 0:
        out.append("- ⚠️ web 로그는 below_tau·OOD를 기록하지 않아(화면 안내만) 미판정률이 0%로 나온다 — 참고치")
    out += ["", "### 2-1. 요약", "", md_table(["지표", "목표값", "실측값", "달성 여부"],
                                              [list(r) for r in verdict_rows(k, lat, rejects_recorded=kind != "web")])]

    cols, table = confusion(rows)
    matrix = [[f"**{s}**" if s == CRITICAL else s] + [table[s][c] for c in cols] for s in SIGNS]
    out += ["", "### 2-2. 혼동행렬 (행 = 정답 클래스, 열 = 예측 클래스)", "",
            md_table(["정답 \\ 예측"] + cols, matrix)]
    if k["critical"]:
        out.append(f"\n⚠️ 치명 오분류 {k['critical']}건 — 정지 행의 대각선 밖 신호 칸")

    by_subject = collections.defaultdict(list)
    for r in rows:
        by_subject[r.get("subject") or "(미기재)"].append(r)
    subj_rows = []
    for s, rs in sorted(by_subject.items()):
        ks = classify_rows(rs)
        subj_rows.append([s, f"{ks['n']}{_nflag(ks['n'])}", f"{ks['accuracy']:.1f}%", f"{ks['misclass']:.1f}%",
                          f"{ks['reject']:.1f}%", ks["critical"]])
    out += ["", "### 2-4. 대상자별", "", md_table(["대상자", "시도", "정답률", "오분류율", "미판정률", "치명"], subj_rows)]

    lat_rows = []
    for name, key in (("판정 지연 vision_latency_ms", "decision"), ("물리 피드백 반응 시작 feedback_ms", "feedback"),
                      ("물리 피드백 완료 feedback_done_ms", "feedback_done"),
                      (f"물리 피드백 손 기준 상한 (판정 지연+{POLL_WAIT_MS}+반응 시작)", "feedback_hand")):
        vs = lat.get(key, [])
        if vs:
            up = p95_upper(vs)
            lat_rows.append([name, len(vs), f"{min(vs):.0f}", f"{sorted(vs)[len(vs) // 2]:.0f}", f"{p95(vs):.0f}",
                             f"{up:.0f}" if up is not None else "n<59", f"{max(vs):.0f}"])
        else:
            lat_rows.append([name, 0, "-", "-", "-", "-", "-"])
    out += ["", "### 2-3. 지연 분포 (ms)", "",
            md_table(["항목", "n", "최소", "중앙값", "P95", "P95 95% 상한", "최대"], lat_rows)]
    return "\n".join(out), k, lat


def save_plots(kind: str, rows: list[dict], lat: dict, out_dir: Path) -> list[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("  (matplotlib이 없어 PNG는 건너뜀 — pip install matplotlib)")
        return []
    for name in ("AppleGothic", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR"):
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False
    written = []

    cols, table = confusion(rows)
    fig, ax = plt.subplots(figsize=(8, 6))
    data = [[table[s][c] for c in cols] for s in SIGNS]
    ax.imshow(data, cmap="Blues")
    ax.set_xticks(range(len(cols)), cols, rotation=45, ha="right")
    ax.set_yticks(range(len(SIGNS)), SIGNS)
    ax.set_xlabel("예측 클래스")
    ax.set_ylabel("정답 클래스")
    vmax = max(max(r) for r in data) or 1
    for i, s in enumerate(SIGNS):
        for j, c in enumerate(cols):
            if data[i][j]:
                if s == CRITICAL and c in SIGNS and c != CRITICAL:   # 치명 오분류 칸
                    ax.text(j, i, data[i][j], ha="center", va="center", color="red", fontweight="bold",
                            bbox={"facecolor": "white", "edgecolor": "red", "boxstyle": "round"})
                else:
                    ax.text(j, i, data[i][j], ha="center", va="center",
                            color="white" if data[i][j] > vmax / 2 else "black")
    ax.add_patch(plt.Rectangle((-0.5, SIGNS.index(CRITICAL) - 0.5), len(cols), 1, fill=False, edgecolor="red", lw=2))
    ax.set_title(f"혼동행렬 ({kind}) — 빨간 테두리 = 정지 행(치명 오분류)")
    fig.tight_layout()
    path = out_dir / f"confusion_{kind}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    written.append(path)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    dec_t, fb_t = TARGETS["decision_p95_ms"], TARGETS["feedback_p95_ms"]
    for ax, (key, title, target) in zip(axes, (("decision", "판정 지연", dec_t), ("feedback", "물리 피드백 (반응 시작)", fb_t),
                                               ("feedback_done", "물리 피드백 (완료)", fb_t))):
        vs = lat[key]
        ax.set_title(f"{title} (n={len(vs)})")
        ax.set_xlabel("ms")
        if vs:
            ax.hist(vs, bins=min(30, max(5, len(vs) // 3)), color="#60a5fa")
            ax.axvline(p95(vs), color="orange", ls="--", label=f"P95 {p95(vs):.0f}")
        ax.axvline(target, color="red", label=f"목표 {target}")
        ax.legend()
    fig.tight_layout()
    path = out_dir / f"latency_{kind}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    written.append(path)
    return written


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("csv", nargs="+", type=Path, help="web_trials_*.csv 또는 데모 CSV")
    parser.add_argument("--out", type=Path, help="kpi_report.md·PNG를 쓸 폴더")
    parser.add_argument("--latency-include-wrong", action="store_true", help="판정 지연 모수에 오답 포함(안건 2 B/C)")
    parser.add_argument("--feedback-include-wrong", action="store_true",
                        help="물리 피드백 모수에 오답 행도 포함(D2 — 기본은 정답 행만)")
    parser.add_argument("--include-mocked", action="store_true", help="mocked=true 행도 집계(개발 확인용, KPI 아님)")
    parser.add_argument("--timeout-as-reject", action="store_true",
                        help="web timeout 행을 미판정으로 계산(16 §6.4 결정 대기 — 기본은 분모에서 제외)")
    args = parser.parse_args(argv)

    missing = [p for p in args.csv if not p.exists()]
    if missing:
        print(f"파일이 없습니다: {', '.join(map(str, missing))}", file=sys.stderr)
        return 2

    groups = load(args.csv)
    sections = []
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    for kind, rows in groups.items():
        if not rows:
            continue
        kept, excluded = split_rows(rows, args.include_mocked, args.timeout_as_reject and kind == "web")
        text, _, lat = report(kind, kept, excluded, [r["_file"] for r in rows], args.latency_include_wrong,
                              args.feedback_include_wrong)
        if args.include_mocked:
            text += "\n\n> ⚠️ `--include-mocked` — mock 행이 섞여 있어 KPI로 쓸 수 없다."
        sections.append(text)
        print(text, end="\n\n")
        if args.out and kept:
            for p in save_plots(kind, kept, lat, args.out):
                print(f"  PNG: {p}")
    if not sections:
        print("집계할 행이 없습니다.", file=sys.stderr)
        return 1
    if args.out:
        md = args.out / "kpi_report.md"
        cmd = "python scripts/aggregate_kpi.py " + " ".join(str(p) for p in args.csv)
        md.write_text("# KPI 집계 (06 2부 붙여넣기용)\n\n" + f"> 생성: `{cmd}`\n\n" + "\n\n".join(sections) + "\n",
                      encoding="utf-8")
        print(f"  보고서: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
