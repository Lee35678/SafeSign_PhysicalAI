"""이미 학습된 모델 번들에 **클래스별 일치율 보정**(match_score_calibration.per_class)만 추가한다 — 재학습 없이.

    python scripts/add_match_calibration.py            # models/svm_classifier.joblib 갱신 (원본은 백업)
    python scripts/add_match_calibration.py --dry-run  # 계산만 보고 저장하지 않음

왜 (2026-09-30): 일치율(match_score)은 "그 클래스 중심과의 코사인 유사도"를 0~100으로 바꾼 표시용 점수인데,
환산 구간이 7종 공통 하나였다. 접힌 손가락이 많은 손모양(확인_완료·주의·후진)은 사람마다 굽힘이 달라 원래
중심에서 더 퍼져 있어서, 정답으로 판정된 정상 동작도 50~70점대가 나왔다(공개 데이터 기준 확인_완료 중앙값 78,
하위 10% 52). 클래스마다 제 분포(학습 데이터의 1~95 퍼센타일)로 재면 이 불공평이 없어진다.

바뀌는 것: 화면의 일치율, SC-03b 권장 재도전 횟수(일치율 구간으로 정한다). **판정(정답/오답)·모델·KPI 수치는 그대로**.
쓰는 데이터: 공개 학습 데이터의 특징 캐시(training/.feature_cache.joint23.npz)만. 자체 촬영 KPI 데이터는 읽지 않는다.
새로 학습하면 train_svm.py가 같은 값을 번들에 넣으므로 이 스크립트는 기존 번들용이다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = SERVICE_ROOT / "models" / "svm_classifier.joblib"
CACHE = SERVICE_ROOT / "training" / ".feature_cache.joint23.npz"
# 구간: 그 클래스 학습 데이터의 1~95 퍼센타일. 5~95로 하면 퍼짐이 좁은 클래스(서행·정지·좌회전)의 정상 동작이
# 오히려 60점대까지 깎였다. 1~95면 7종 모두 정상 손의 중앙값 96~98·하위 10% 86~95로 고르다(공개 데이터 기준).
LO_PCT, HI_PCT = 1, 95


def per_class_calibration(X: np.ndarray, y: np.ndarray, classes: list[str]) -> dict:
    out = {}
    for c in classes:
        Xi = X[y == c]
        v = Xi.mean(axis=0)
        s = (Xi @ v) / (np.linalg.norm(Xi, axis=1) * np.linalg.norm(v) + 1e-12)
        out[c] = {"sim_min": float(np.percentile(s, LO_PCT)), "sim_max": float(np.percentile(s, HI_PCT))}
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="모델 번들에 클래스별 일치율 보정 추가")
    ap.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import joblib

    bundle = joblib.load(args.bundle)
    meta = bundle.get("metadata") or {}
    if meta.get("feature_mode") != "joint23":
        raise SystemExit(f"joint23 번들만 지원합니다 (지금: {meta.get('feature_mode')})")
    if not CACHE.exists():
        raise SystemExit(f"학습 특징 캐시가 없습니다: {CACHE}\n  python training/train_svm.py --dry-run 으로 먼저 만드세요")

    z = np.load(CACHE, allow_pickle=False)
    X, y = z["X"], z["y"]
    classes = [str(c) for c in bundle["classes"]]

    # 이 캐시가 번들을 만든 그 데이터인지 확인 — 건수와 클래스 중심이 같아야 한다
    if meta.get("n_samples") and int(meta["n_samples"]) != len(X):
        raise SystemExit(f"캐시 건수 {len(X)} ≠ 번들 학습 건수 {meta['n_samples']} — 다른 데이터입니다. 재학습하세요")
    centroids = (bundle.get("open_set_gate") or {}).get("centroids") or {}
    worst = max(float(np.max(np.abs(np.asarray(centroids[c]) - X[y == c].mean(axis=0)))) for c in classes) \
        if centroids else 0.0
    if worst > 1e-6:
        raise SystemExit(f"캐시의 클래스 중심이 번들과 다릅니다(최대 차이 {worst:.2e}) — 재학습하세요")

    per_class = per_class_calibration(X, y, classes)
    calib = dict(bundle.get("match_score_calibration") or {})
    print(f"공통 구간(기존): {calib.get('sim_min', 0):.4f} ~ {calib.get('sim_max', 1):.4f}")
    for c, v in per_class.items():
        print(f"  {c:<8} {v['sim_min']:.4f} ~ {v['sim_max']:.4f}")
    if args.dry_run:
        print("(--dry-run: 저장하지 않음)")
        return 0

    calib["per_class"] = per_class
    bundle["match_score_calibration"] = calib
    meta["match_score_calibration_per_class_added_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    bundle["metadata"] = meta

    backup = args.bundle.with_name(f"{args.bundle.stem}.bak-{datetime.now():%Y%m%d-%H%M%S}.joblib")
    shutil.copy2(args.bundle, backup)
    tmp = args.bundle.with_suffix(".tmp")
    joblib.dump(bundle, tmp)
    tmp.replace(args.bundle)          # 실행 중인 vision이 반쪽 파일을 읽지 않게 한 번에 바꾼다
    print(f"저장: {args.bundle}  (원본 백업: {backup.name})")
    print("실행 중인 vision은 파일이 바뀐 것을 보고 다음 판정부터 새 값을 쓴다(재시작 불필요).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
