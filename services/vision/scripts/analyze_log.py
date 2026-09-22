"""webcam_check.py 진단 로그 분석 — 실제 손에서 무엇이 어떻게 틀리는가.

    python scripts/analyze_log.py logs/webcam_20260922_143000.jsonl

**왜 이 도구가 필요한가.** 공개 데이터 27,735건으로 잰 숫자(88.68%)는 인터넷 사진 기준이다.
실제 웹캠 앞의 손은 조명·각도·손 크기·수행 습관이 모두 다르다. 둘이 어긋나면 공개 데이터
점수를 아무리 올려도 체감이 나빠질 수 있다 — 이 스크립트는 그 격차를 수치로 드러낸다.

로그에 **원본 랜드마크**가 들어 있어서, 같은 프레임을 **다른 특징 모드로 다시 계산**해
비교할 수 있다. "joint23으로 바꾼 게 실제로 더 나쁜가?"를 같은 손·같은 프레임에서 직접 답한다.

출력:
  1. 정답 라벨별 판정 분포 (실사용 혼동행렬)
  2. 오판정 상세 — 무엇을 무엇으로, 얼마나 확신하며
  3. 특징 모드 비교 — 같은 프레임을 joint23 / landmark63 로 각각 재계산
  4. 소속 게이트 동작 — 애매한 자세를 막았는가, 정상 자세를 튕겼는가
  5. 흔들림 — 같은 동작을 유지하는 동안 판정이 몇 번 바뀌는가
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from cognition import model_store  # noqa: E402

AMBIGUOUS = "애매한자세"


def load(path: Path):
    header, frames = None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("record") == "header":
            header = rec
        else:
            frames.append(rec)
    return header, frames


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    ap = argparse.ArgumentParser(description="webcam_check 로그 분석")
    ap.add_argument("log", type=Path)
    ap.add_argument("--compare-model", type=Path, default=None,
                    help="추가로 비교할 모델 번들 경로. models/cmp_*.joblib 은 자동으로 포함된다")
    args = ap.parse_args()

    header, frames = load(args.log)
    labeled = [f for f in frames if f.get("intended")]
    with_hand = [f for f in frames if f.get("hand_detected")]

    section("0. 로그 요약")
    if header:
        m = (header.get("model") or {}).get("metadata") or {}
        print(f"  촬영 {header.get('started_at')}  |  모델 {(header.get('model') or {}).get('feature_mode')}"
              f"  |  τ {header.get('tau')}  |  N {header.get('n_frames')}프레임")
        if m:
            print(f"  학습 정보: {m.get('n_samples')}건, CV 정답률 {m.get('cv_accuracy')}, "
                  f"치명 {m.get('cv_critical_errors')}건")
    print(f"  총 {len(frames)}프레임  |  손 검출 {len(with_hand)}  |  정답 라벨 있음 {len(labeled)}")
    if not labeled:
        print("\n  [경고] 정답 라벨이 하나도 없습니다. 촬영 중 숫자키(1~7, 0)를 눌러야")
        print("         '무엇을 하려 했는지'가 기록되고, 그래야 오판정을 셀 수 있습니다.")
        return 1

    # ---------------------------------------------------------------- 1
    section("1. 정답 라벨별 판정 분포 (실사용 혼동행렬)")
    by_label = collections.defaultdict(collections.Counter)
    for f in labeled:
        out = "(미판정)" if f.get("is_reject") else f.get("predicted")
        by_label[f["intended"]][out] += 1
    order = [k for k in header_order(by_label)]
    print(f"  {'의도한 동작':<14}{'프레임':>7}{'맞음':>8}{'틀림':>8}{'미판정':>8}  주요 오판정")
    print("  " + "-" * 74)
    for lbl in order:
        c = by_label[lbl]
        n = sum(c.values())
        rej = c["(미판정)"]
        if lbl == AMBIGUOUS:
            # 애매한 자세는 '미판정'이 정답이다
            ok, bad = rej, n - rej
        else:
            ok = c[lbl]
            bad = n - ok - rej
        wrong = {k: v for k, v in c.items() if k not in (lbl, "(미판정)")}
        top = ", ".join(f"{k} {v}" for k, v in
                        sorted(wrong.items(), key=lambda kv: -kv[1])[:3]) or "-"
        print(f"  {lbl:<14}{n:>7}{ok / n * 100:>7.0f}%{bad / n * 100:>7.0f}%"
              f"{rej / n * 100:>7.0f}%  {top}")
    if AMBIGUOUS in by_label:
        print(f"\n  ※ '{AMBIGUOUS}'는 **미판정이 정답**이다(소속 게이트가 막아야 함).")

    # ---------------------------------------------------------------- 2
    section("2. 어떤 오판정이 많은가")
    errs = collections.Counter()
    conf_of = collections.defaultdict(list)
    for f in labeled:
        if f.get("is_reject") or f["intended"] == AMBIGUOUS:
            continue
        if f["predicted"] != f["intended"]:
            k = f"{f['intended']} -> {f['predicted']}"
            errs[k] += 1
            conf_of[k].append(f.get("confidence") or 0.0)
    if not errs:
        print("  오판정 없음")
    else:
        print(f"  {'오판정':<30}{'건수':>6}{'평균 confidence':>16}  해석")
        print("  " + "-" * 74)
        for k, v in errs.most_common(10):
            c = float(np.mean(conf_of[k]))
            note = "자신만만하게 틀림 — 특징이 두 클래스를 못 가름" if c >= 0.85 else \
                   ("애매하게 틀림 — τ를 올리면 미판정으로 뺄 수 있음" if c >= 0.6 else "확신 낮음")
            print(f"  {k:<30}{v:>6}{c:>16.3f}  {note}")

    # ---------------------------------------------------------------- 3
    section("3. 모델 비교 — 같은 프레임을 다른 모델로 다시 판정")
    print("  로그에 원본 랜드마크가 있어서, 같은 손·같은 프레임을 다른 모델로 재판정할 수 있다.")
    print("  '바꾼 게 실제로 더 나쁜가'를 공개 데이터가 아니라 이 손으로 답한다.\n")
    usable = [f for f in labeled if f.get("hand_detected") and f.get("landmarks")]
    if not usable:
        print("  비교할 프레임이 없습니다.")
    else:
        candidates = [("현재 모델", None)] + [
            (p.name, p) for p in sorted((SERVICE_ROOT / "models").glob("cmp_*.joblib"))
        ]
        if args.compare_model:
            candidates.append((args.compare_model.name, args.compare_model))
        print(f"  {'모델':<30}{'모드':<20}{'정답률':>8}{'미판정':>8}{'오판정':>8}")
        print("  " + "-" * 76)
        for name, path in candidates:
            res = rejudge(usable, path)
            if res is None:
                print(f"  {name:<30}{'(로드 실패)':<20}")
                continue
            mode, ok, rej, bad, n = res
            print(f"  {name:<30}{mode:<20}{ok / n * 100:>7.1f}%{rej / n * 100:>7.1f}%"
                  f"{bad / n * 100:>7.1f}%")
        print("\n  ※ '애매한자세' 프레임은 미판정이 정답이므로 위 정답률에 그렇게 반영했다.")
        print("  ※ 비교 모델을 더 만들려면:")
        print("       python training/train_svm.py --features landmark63 "
              "--out models/cmp_landmark63.joblib")

    # ---------------------------------------------------------------- 4
    section("4. 소속 게이트가 제 역할을 했나")
    gated = [f for f in labeled if f.get("reason") == "out_of_distribution"]
    amb = [f for f in labeled if f["intended"] == AMBIGUOUS]
    normal = [f for f in labeled if f["intended"] != AMBIGUOUS]
    if amb:
        blocked = sum(1 for f in amb if f.get("is_reject"))
        by_gate = sum(1 for f in amb if f.get("reason") == "out_of_distribution")
        print(f"  애매한 자세 {len(amb)}프레임 중 미판정 {blocked}"
              f" ({blocked / len(amb) * 100:.0f}%), 그중 게이트가 막은 것 {by_gate}")
    else:
        print("  '애매한자세'(0번 키) 프레임이 없어 게이트 차단력을 잴 수 없습니다.")
    if normal:
        fp = sum(1 for f in normal if f.get("reason") == "out_of_distribution")
        print(f"  정상 자세 {len(normal)}프레임 중 게이트가 잘못 막은 것 {fp}"
              f" ({fp / len(normal) * 100:.1f}%)  ← 미판정률 KPI(≤5%)와 직결")
    if gated:
        c = collections.Counter(f["intended"] for f in gated)
        print(f"  게이트가 막은 프레임의 의도 분포: {dict(c)}")

    # ---------------------------------------------------------------- 5
    section("5. 판정이 흔들리나 (같은 동작을 유지하는 동안)")
    runs, cur, flips = [], None, 0
    for f in labeled:
        if f["intended"] != cur:
            cur = f["intended"]
            runs.append([])
        runs[-1].append("(미판정)" if f.get("is_reject") else f.get("predicted"))
    for r in runs:
        flips += sum(1 for a, b in zip(r[:-1], r[1:]) if a != b)
    total_frames = sum(len(r) for r in runs)
    print(f"  구간 {len(runs)}개, 총 {total_frames}프레임에서 판정이 바뀐 횟수 {flips}")
    if total_frames:
        rate = flips / total_frames * 100
        print(f"  프레임당 변동률 {rate:.1f}%  "
              f"{'— 안정적' if rate < 5 else ('— 다소 흔들림' if rate < 15 else '— 심하게 흔들림, N프레임 상향 검토')}")

    print()
    return 0


def rejudge(frames: list[dict], model_path: Path | None):
    """프레임들을 지정한 모델 번들로 다시 판정.

    **운영과 같은 코드 경로를 쓴다** — model_store.MODEL_PATH를 잠시 바꿔 끼우고
    classify.predict를 그대로 호출한다. 판정 로직을 여기서 다시 구현하면 원본과 미묘하게
    달라져서, 비교 결과 자체를 믿을 수 없게 된다.

    Returns: (모드, 정답 수, 미판정 수, 오판정 수, 전체) 또는 로드 실패 시 None.
    """
    from cognition import classify

    original = model_store.MODEL_PATH
    try:
        if model_path is not None:
            model_store.MODEL_PATH = model_path
        model_store.load_bundle(force=True)
        bundle = model_store.load_bundle()
        if bundle is None:
            return None
        mode = (bundle.get("metadata") or {}).get("feature_mode", "?")

        ok = rej = bad = 0
        for f in frames:
            r = classify.predict({
                "hand_detected": True,
                "handedness": f.get("handedness", "Right"),
                "landmarks": f["landmarks"],
            })
            if f["intended"] == AMBIGUOUS:
                # 애매한 자세는 미판정이 정답
                ok += int(bool(r["is_reject"]))
                bad += int(not r["is_reject"])
            elif r["is_reject"]:
                rej += 1
            elif r["predicted_class"] == f["intended"]:
                ok += 1
            else:
                bad += 1
        return mode, ok, rej, bad, len(frames)
    finally:
        model_store.MODEL_PATH = original
        model_store.load_bundle(force=True)


def header_order(by_label):
    """7종 표준 순서 우선, 그 뒤 애매한자세."""
    std = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의", AMBIGUOUS]
    return [c for c in std if c in by_label] + [c for c in by_label if c not in std]


if __name__ == "__main__":
    raise SystemExit(main())
