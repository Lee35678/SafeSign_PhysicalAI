"""자체 촬영 데이터로 KPI 실측 — 01_프로젝트계획서_v4의 5개 지표.

    python scripts/evaluate_kpi.py

**왜 이 도구인가.** 공개 데이터로 낸 점수(88.68%)는 촬영자 정보가 없어 KPI 근거가 못 된다
(04_데이터셋명세서_v2 §4). KPI는 `record_dataset.py`로 모은 자체 촬영 데이터로만 측정할 수 있고,
이 스크립트가 그 계산을 한다.

**테이크 단위로 센다.** KPI의 "전체 시도 수"는 프레임이 아니라 **한 번의 시도**다. 한 테이크의
3프레임은 같은 시도이고, 운영에서도 N=3 연속 프레임이 같아야 확정하므로(05_모델카드_v3 §3-6)
그 규칙을 그대로 적용해 테이크 하나를 한 번의 판정으로 집계한다. 프레임 단위 수치도 참고로 낸다.

모델을 여러 개 비교하려면 `models/cmp_*.joblib` 에 두면 자동으로 함께 평가한다.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from cognition import classify, model_store  # noqa: E402
from cognition.normalize import FEATURE_MODE_JOINT, to_feature_vector  # noqa: E402

CLASSES = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]
CRITICAL = "정지"
AMBIGUOUS = "애매한자세"
KPI = {"accuracy": 92.0, "misclass": 3.0, "reject": 5.0, "macro_f1": 0.90}


def load(data_dir: Path) -> list[dict]:
    out = []
    for path in sorted(glob.glob(str(data_dir / "*" / "*.json"))):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        src = d.get("source") or {}
        out.append({
            "cls": d["class_name"],
            "subject": d.get("subject_id", "?"),
            "take": src.get("take"),
            "orientation": src.get("orientation"),
            "handedness": d.get("handedness", "Right"),
            "landmarks": d["landmarks"],
            "file": Path(path).name,
        })
    return out


def judge_take(frames: list[dict]) -> tuple[str, bool, str | None]:
    """한 테이크(=한 시도)의 최종 판정. 운영의 N프레임 규칙과 같은 방식.

    프레임별 판정 중 **확정된 것들의 최빈값**을 결과로 삼고, 확정이 하나도 없으면 미판정이다.
    """
    votes, reasons = [], []
    for f in frames:
        r = classify.predict({"hand_detected": True, "handedness": f["handedness"],
                              "landmarks": f["landmarks"]})
        if r["is_reject"]:
            reasons.append(r.get("reason"))
        else:
            votes.append(r["predicted_class"])
    if not votes:
        top = collections.Counter(reasons).most_common(1)
        return "negative", True, (top[0][0] if top else None)
    return collections.Counter(votes).most_common(1)[0][0], False, None


def evaluate(samples: list[dict], model_path: Path | None):
    """지정한 모델로 평가. 운영과 같은 코드 경로(classify.predict)를 쓴다."""
    original = model_store.MODEL_PATH
    try:
        if model_path is not None:
            model_store.MODEL_PATH = model_path
        model_store.load_bundle(force=True)
        bundle = model_store.load_bundle()
        if bundle is None:
            return None
        mode = (bundle.get("metadata") or {}).get("feature_mode", "?")

        takes = collections.defaultdict(list)
        for s in samples:
            takes[(s["subject"], s["cls"], s["take"])].append(s)

        rows = []
        for (subject, cls, take), fs in sorted(takes.items(), key=lambda kv: str(kv[0])):
            pred, rej, reason = judge_take(fs)
            rows.append({"cls": cls, "subject": subject, "take": take,
                         "pred": pred, "reject": rej, "reason": reason,
                         "orientation": fs[0]["orientation"], "n": len(fs)})
        return mode, rows
    finally:
        model_store.MODEL_PATH = original
        model_store.load_bundle(force=True)


def kpi_table(rows: list[dict]) -> dict:
    signs = [r for r in rows if r["cls"] in CLASSES]
    n = len(signs)
    if not n:
        return {}
    correct = sum(1 for r in signs if not r["reject"] and r["pred"] == r["cls"])
    wrong = sum(1 for r in signs if not r["reject"] and r["pred"] != r["cls"])
    rej = sum(1 for r in signs if r["reject"])
    crit = sum(1 for r in signs
               if r["cls"] == CRITICAL and not r["reject"] and r["pred"] != CRITICAL)
    # Macro F1 (미판정은 오답으로 계산 — 판정되지 않은 것도 학습자 입장에선 실패다)
    f1s = []
    for c in CLASSES:
        tp = sum(1 for r in signs if r["cls"] == c and not r["reject"] and r["pred"] == c)
        fp = sum(1 for r in signs if r["cls"] != c and not r["reject"] and r["pred"] == c)
        fn = sum(1 for r in signs if r["cls"] == c and (r["reject"] or r["pred"] != c))
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * p * rc / (p + rc) if p + rc else 0.0)
    return {"n": n, "accuracy": correct / n * 100, "misclass": wrong / n * 100,
            "reject": rej / n * 100, "critical": crit, "macro_f1": float(np.mean(f1s))}


def main() -> int:
    ap = argparse.ArgumentParser(description="자체 촬영 데이터로 KPI 실측")
    ap.add_argument("--data", type=Path,
                    default=SERVICE_ROOT.parent / "data" / "datasets" / "self_recorded")
    ap.add_argument("--subject", default=None, help="특정 촬영자만")
    args = ap.parse_args()

    samples = load(args.data)
    if args.subject:
        samples = [s for s in samples if s["subject"] == args.subject]
    if not samples:
        print(f"데이터가 없습니다: {args.data}")
        return 1

    subs = collections.Counter(s["subject"] for s in samples)
    print("=" * 78)
    print(f"자체 촬영 KPI 실측  —  {args.data}")
    print("=" * 78)
    print(f"  샘플 {len(samples)}건  |  촬영자 {dict(subs)}")
    per_cls = collections.Counter(s["cls"] for s in samples)
    print(f"  클래스별: {dict(per_cls)}")
    if len(subs) < 2:
        print("\n  [주의] 촬영자가 1명뿐입니다. 인물 단위 분할이 불가능해 '처음 보는 사람'")
        print("         기준 KPI로는 쓸 수 없습니다 (04_데이터셋명세서_v2 §4). 최소 2명 필요.")

    candidates = [("현재 모델", None)] + [
        (p.name, p) for p in sorted((SERVICE_ROOT / "models").glob("cmp_*.joblib"))
    ]

    results = {}
    for name, path in candidates:
        res = evaluate(samples, path)
        if res is None:
            continue
        mode, rows = res
        results[name] = (mode, rows, kpi_table(rows))

    print()
    print("=" * 78)
    print("KPI 표 (테이크 단위 = 한 번의 시도)")
    print("=" * 78)
    print(f"  {'모델':<26}{'모드':<20}{'정답률':>8}{'오분류':>8}{'미판정':>8}{'MacroF1':>9}{'치명':>6}")
    print("  " + "-" * 76)
    for name, (mode, rows, k) in results.items():
        if not k:
            continue
        print(f"  {name:<26}{mode:<20}{k['accuracy']:>7.1f}%{k['misclass']:>7.1f}%"
              f"{k['reject']:>7.1f}%{k['macro_f1']:>9.3f}{k['critical']:>6}")
    print("  " + "-" * 76)
    print(f"  {'KPI 목표':<46}{'>=92%':>8}{'<=3%':>8}{'<=5%':>8}{'>=0.90':>9}{'0':>6}")

    # 현재 모델 상세
    mode, rows, k = results.get("현재 모델", (None, [], {}))
    if not rows:
        return 0

    print()
    print("=" * 78)
    print("클래스별 상세 (현재 모델)")
    print("=" * 78)
    print(f"  {'클래스':<12}{'시도':>5}{'정답':>7}{'오분류':>8}{'미판정':>8}  틀린 내역")
    print("  " + "-" * 70)
    for c in CLASSES:
        rs = [r for r in rows if r["cls"] == c]
        if not rs:
            continue
        ok = sum(1 for r in rs if not r["reject"] and r["pred"] == c)
        rj = sum(1 for r in rs if r["reject"])
        bad = collections.Counter(r["pred"] for r in rs if not r["reject"] and r["pred"] != c)
        detail = ", ".join(f"{k2} {v}" for k2, v in bad.most_common(3)) or "-"
        if rj:
            reasons = collections.Counter(r["reason"] for r in rs if r["reject"])
            detail += f"  [미판정 사유 {dict(reasons)}]"
        print(f"  {c:<12}{len(rs):>5}{ok:>7}{sum(bad.values()):>8}{rj:>8}  {detail}")

    # 손 방향별
    print()
    print("=" * 78)
    print("손 방향별 (안건 3 A안 — 방향 축이 필요한지 판단할 근거)")
    print("=" * 78)
    for o in sorted({r["orientation"] for r in rows if r["orientation"]}):
        rs = [r for r in rows if r["orientation"] == o and r["cls"] in CLASSES]
        if not rs:
            continue
        ok = sum(1 for r in rs if not r["reject"] and r["pred"] == r["cls"])
        print(f"  {o:<10}{len(rs):>4}시도   정답률 {ok / len(rs) * 100:>5.1f}%")

    # 소지 진단 — 2026-09-22 로그에서 드러난 문제
    print()
    print("=" * 78)
    print("손가락 신전 진단 — 학습 데이터와 얼마나 다른가")
    print("=" * 78)
    cache = SERVICE_ROOT / "training" / ".feature_cache.joint23.npz"
    if not cache.exists():
        print("  (학습 특징 캐시가 없어 생략. train_svm.py를 한 번 실행하면 생깁니다)")
    else:
        z = np.load(cache, allow_pickle=False)
        Xtr, ytr = z["X"], z["y"]
        FING = ["엄지", "검지", "중지", "약지", "소지"]
        print("  '폄 방향' 지표 (1=쭉 폄, 0 이하=접힘). 학습 / 내 손 순서.\n")
        print(f"  {'클래스':<12}" + "".join(f"{n:>14}" for n in FING))
        print("  " + "-" * 74)
        for c in CLASSES:
            fs = [s for s in samples if s["cls"] == c]
            if not fs:
                continue
            V = np.stack([to_feature_vector(s["landmarks"], s["handedness"],
                                            mode=FEATURE_MODE_JOINT) for s in fs])
            tr = Xtr[ytr == c].mean(0)[5:10]
            me = V.mean(0)[5:10]
            cells = ""
            for a, b in zip(tr, me):
                flag = "*" if abs(a - b) > 0.5 else " "
                cells += f"{a:>6.2f}/{b:<6.2f}{flag}"
            print(f"  {c:<12}{cells}")
        print("\n  * = 0.5 이상 차이. 학습 데이터(ASL 사진)보다 덜 편다는 뜻이고,")
        print("    그 손가락으로 구분하는 클래스가 무너진다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
