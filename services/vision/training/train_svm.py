# -*- coding: utf-8 -*-
"""SafeSign 경량 분류기(SVM) 학습 — 로컬 실행용.

    python training/train_svm.py --data ../data/datasets/processed

처음에는 Colab 전제로 설계했으나(training/train_svm_colab.ipynb), 실측 결과 전체 27,735건
단일 학습이 13초라 GPU가 필요 없었다. **로컬이 기본 경로**이고 노트북은 대체 경로로 남겨둔다
(2026-09-21).

문서 근거
  - 정규화/특징: document/05_모델카드_v3.md §3-5  (src/cognition/normalize.py를 그대로 import해
    학습과 추론이 같은 코드를 쓰게 한다 — train-serve skew 방지)
  - SVM 채택 근거·학습 방법: 같은 문서 §5, §6
  - τ 결정 절차: 같은 문서 §8-1  (이 스크립트의 `choose_tau`가 1~5단계를 그대로 구현)
  - KPI: document/01_프로젝트계획서_v4.md

2026-09-21 회의 결정 반영
  - 안건 2 A: **7클래스 학습**. negative는 학습하지 않고 τ 미달을 미판정으로 처리한다.
  - 안건 3 A: `--with-orientation`으로 손 방향 6차원을 특징에 추가할 수 있다. **기본은 꺼짐** —
    공개 데이터는 클래스별 출처 데이터셋이 달라 촬영 각도가 클래스와 상관되어 있을 수 있어,
    지금 켜면 "어느 데이터셋 사진인가"를 학습한다. 자체 촬영 데이터 확보 후 켜고 비교할 것.

분할 방식 (--split)
  공개 데이터는 촬영자 정보가 없어 subject_id가 전부 "public"이다. 그런데 같은 원본의 복사본과
  연속 촬영 컷이 섞여 있어, 무작위로 나누면 사실상 같은 사진을 학습·평가 양쪽에서 보게 된다.
  실측: 무작위 98.81% / 파일 그룹 98.88% / **세션 그룹 78.59%**. 그래서 기본값은 session이다.
  이 숫자도 KPI 근거는 못 된다 — KPI는 자체 촬영 데이터로만 측정한다(04 §4).
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from cognition.normalize import (  # noqa: E402
    NormalizationError,
    feature_dim,
    feature_mode,
    to_feature_vector,
)

# document/02_설계문서_v2 §4 확정 7종. negative는 학습하지 않는다 (안건 2 A).
SIGN_CLASSES = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]
CRITICAL_CLASS = "정지"          # 이 클래스의 오분류는 치명 오분류 (KPI 0건)
TAU_GRID = [round(float(x), 2) for x in np.arange(0.50, 0.96, 0.05)]
KPI = {"accuracy": 0.92, "misclass": 0.03, "reject": 0.05, "macro_f1": 0.90}


# ---------------------------------------------------------------- 데이터 적재

def session_key(source_file: str) -> str:
    """같은 촬영 세션에서 나온 사진을 한 그룹으로 묶는 키.

    복사본 표시 ' (2)', 확장자, '_cropped', '_seg_N', 꼬리 일련번호를 떼어낸다.
    (예: "color_18_0002 (3).png" -> "color_", bfritzy1.jpg / bfritzy2.jpg -> bfritzy)
    """
    n = re.sub(r"\.(jpe?g|png|bmp|webp)$", "", source_file, flags=re.I)
    n = re.sub(r"\s*\(\d+\)$", "", n)
    n = re.sub(r"_cropped$", "", n)
    n = re.sub(r"_seg_\d+$", "", n)
    return re.sub(r"\d+$", "", n)


def load_dataset(data_dir: Path, with_orientation: bool, per_class: int | None):
    """datasets/processed/{클래스}/*.json -> (X, y, subjects, sessions, 실패내역, 빈클래스)."""
    X, y, subjects, sessions = [], [], [], []
    failures: collections.Counter = collections.Counter()
    skipped_classes = []

    for cls in SIGN_CLASSES:
        files = sorted(glob.glob(str(data_dir / cls / "*.json")))
        if not files:
            skipped_classes.append(cls)
            continue
        if per_class and len(files) > per_class:
            # 앞에서 자르지 않고 고르게 솎아낸다(파일명 순 = 촬영 순인 경우가 많아서)
            files = [files[i] for i in np.linspace(0, len(files) - 1, per_class).astype(int)]
        for path in files:
            try:
                d = json.loads(Path(path).read_text(encoding="utf-8"))
                feat = to_feature_vector(
                    d["landmarks"],
                    handedness=d.get("handedness", "Right"),
                    with_orientation=with_orientation,
                )
            except NormalizationError as exc:
                failures[str(exc)[:50]] += 1
                continue
            except (OSError, ValueError, KeyError) as exc:
                failures[f"{type(exc).__name__}: {str(exc)[:40]}"] += 1
                continue
            X.append(feat)
            y.append(d.get("class_name", cls))
            subjects.append(d.get("subject_id", "unknown"))
            src = (d.get("source") or {}).get("file") or Path(path).name
            sessions.append(f"{cls}/{session_key(src)}")

    if not X:
        raise SystemExit(f"학습 데이터가 없습니다: {data_dir}")
    return (
        np.asarray(X),
        np.asarray(y),
        np.asarray(subjects),
        np.asarray(sessions),
        failures,
        skipped_classes,
    )


def _cache_signature(data_dir: Path, with_orientation: bool, per_class: int | None) -> str:
    """캐시가 지금 요청과 같은 조건에서 만들어졌는지 확인하는 지문.

    클래스별 파일 개수와 최신 mtime을 넣어, 데이터가 추가·갱신되면 캐시를 자동으로 버린다.
    """
    parts = [str(data_dir.resolve()), feature_mode(with_orientation), str(per_class)]
    for cls in SIGN_CLASSES:
        files = glob.glob(str(data_dir / cls / "*.json"))
        newest = max((os.path.getmtime(f) for f in files), default=0.0)
        parts.append(f"{cls}:{len(files)}:{newest:.0f}")
    return "|".join(parts)


def load_cached(data_dir: Path, with_orientation: bool, per_class: int | None,
                cache_path: Path | None):
    """load_dataset + 특징벡터 캐시.

    JSON 27,735건을 매번 읽으면 5분 넘게 걸린다(Windows 기준 실측 336초). 조건이 같으면
    캐시에서 바로 읽는다. 반환값 마지막은 캐시 적중 여부.
    """
    sig = _cache_signature(data_dir, with_orientation, per_class)
    if cache_path and cache_path.exists():
        try:
            z = np.load(cache_path, allow_pickle=False)
            if str(z["signature"]) == sig:
                return (z["X"], z["y"], z["subjects"], z["sessions"],
                        collections.Counter(), [], True)
        except (OSError, ValueError, KeyError) as exc:
            print(f"      [경고] 캐시를 읽지 못해 다시 적재합니다: {exc}")

    X, y, subjects, sessions, failures, skipped = load_dataset(
        data_dir, with_orientation, per_class
    )
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache_path, X=X, y=y, subjects=subjects, sessions=sessions,
                            signature=np.array(sig))
    return X, y, subjects, sessions, failures, skipped, False


# ---------------------------------------------------------------- τ 결정

def choose_tau(y_true: np.ndarray, proba: np.ndarray, classes: np.ndarray) -> dict:
    """05_모델카드_v3 §8-1 절차 1~5를 그대로 구현.

    2) τ 후보마다 confidence < τ를 미판정 처리하고 정답률/오분류율 재계산
    3) 치명 오분류(정지 -> 타 클래스)가 있는 후보는 제외
    4) 정답률 >= 92%, 오분류율 <= 3%, 미판정률 <= 5%를 모두 만족하는 후보만 남김
    5) 남은 후보 중 미판정률이 가장 낮은 τ 채택
    """
    pred = classes[np.argmax(proba, axis=1)]
    conf = proba.max(axis=1)
    n = len(y_true)
    rows = []
    for tau in TAU_GRID:
        reject = conf < tau
        judged = ~reject
        correct = int(((pred == y_true) & judged).sum())
        wrong = int(((pred != y_true) & judged).sum())
        critical = int(((y_true == CRITICAL_CLASS) & (pred != CRITICAL_CLASS) & judged).sum())
        rows.append(
            {
                "tau": tau,
                "accuracy": correct / n,
                "misclass": wrong / n,
                "reject": int(reject.sum()) / n,
                "critical": critical,
            }
        )

    ok = [
        r
        for r in rows
        if r["critical"] == 0
        and r["accuracy"] >= KPI["accuracy"]
        and r["misclass"] <= KPI["misclass"]
        and r["reject"] <= KPI["reject"]
    ]
    chosen = min(ok, key=lambda r: r["reject"]) if ok else None
    return {"grid": rows, "chosen": chosen}


# ---------------------------------------------------------------- 메인

def main() -> int:
    ap = argparse.ArgumentParser(description="SafeSign 경량 분류기 로컬 학습")
    ap.add_argument("--data", type=Path,
                    default=SERVICE_ROOT.parent / "data" / "datasets" / "processed")
    ap.add_argument("--out", type=Path, default=SERVICE_ROOT / "models" / "svm_classifier.joblib")
    ap.add_argument("--templates", type=Path,
                    default=SERVICE_ROOT / "models" / "sign_templates.json")
    ap.add_argument("--with-orientation", action="store_true",
                    help="손 방향 6차원 추가 (안건 3 A). 자체 촬영 데이터 확보 후에 켤 것")
    ap.add_argument("--split", choices=["session", "subject", "random"], default="session",
                    help="교차검증 그룹 기준 (기본 session — 누수 방지)")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--grid", action="store_true", help="하이퍼파라미터 탐색 (수십 분 소요)")
    ap.add_argument("--per-class", type=int, default=None, help="클래스당 표본 상한(빠른 시험용)")
    ap.add_argument("--cache", type=Path, default=SERVICE_ROOT / "training" / ".feature_cache.npz",
                    help="특징벡터 캐시 (JSON 27,735건 적재에 100초 이상 걸려서 둔다)")
    ap.add_argument("--no-cache", action="store_true", help="캐시를 읽지도 쓰지도 않음")
    ap.add_argument("--dry-run", action="store_true", help="데이터 점검만 하고 학습하지 않음")
    args = ap.parse_args()

    mode = feature_mode(args.with_orientation)
    print("=" * 74)
    print(f"SafeSign 분류기 학습  |  특징 모드 {mode} ({feature_dim(args.with_orientation)}차원)")
    print("=" * 74)
    if args.with_orientation:
        print("  [주의] 손 방향 축이 켜져 있습니다. 공개 데이터만으로 학습하면 클래스별 촬영 각도")
        print("         차이를 학습할 수 있습니다(04_데이터셋명세서_v2 §3). 자체 촬영 데이터로")
        print("         검증한 뒤에 쓰세요 — 회의안건_2026-09-21 안건 3.")

    t0 = time.time()
    X, y, subjects, sessions, failures, skipped, from_cache = load_cached(
        args.data, args.with_orientation, args.per_class,
        None if args.no_cache else args.cache,
    )
    origin = "캐시" if from_cache else "JSON"
    print(f"\n[1] 데이터 {len(X):,}건 적재 ({origin}, {time.time() - t0:.1f}초), 차원 {X.shape[1]}")
    counts = collections.Counter(y.tolist())
    for cls in SIGN_CLASSES:
        print(f"      {cls:<12}{counts.get(cls, 0):>7,}건")
    if skipped:
        print(f"      [경고] 데이터가 없는 클래스: {', '.join(skipped)}")
    if failures:
        print(f"      정규화 실패 {sum(failures.values())}건: {dict(failures)}")
    imbalance = max(counts.values()) / max(1, min(counts.values()))
    print(f"      불균형 {imbalance:.1f}배  |  세션 {len(set(sessions.tolist())):,}개"
          f"  |  subject {sorted(set(subjects.tolist()))}")

    if args.dry_run:
        print("\n--dry-run: 여기까지.")
        return 0

    try:
        import joblib
        import sklearn
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.metrics import confusion_matrix, f1_score
        from sklearn.model_selection import (
            GridSearchCV,
            GroupKFold,
            StratifiedKFold,
            cross_val_predict,
        )
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.svm import SVC
    except ImportError:
        print("\n[오류] scikit-learn / joblib 이 없습니다.  pip install -r requirements.txt")
        return 1

    # ---- 분할 전략 ----------------------------------------------------
    groups = {"session": sessions, "subject": subjects}.get(args.split)
    if groups is not None and len(set(groups.tolist())) < args.folds:
        print(f"\n[2] --split {args.split} 불가(그룹 {len(set(groups.tolist()))}개 "
              f"< {args.folds}겹) -> random으로 대체")
        groups = None
    if groups is None:
        cv, split_desc = StratifiedKFold(args.folds, shuffle=True, random_state=42), "무작위"
    else:
        cv, split_desc = GroupKFold(n_splits=args.folds), f"{args.split} 단위"
    print(f"\n[2] 교차검증 {args.folds}겹, {split_desc} 분할")
    if groups is None:
        print("      [주의] 무작위 분할은 같은 원본의 복사본이 학습·평가에 섞여 점수가 부풀려집니다.")

    # ---- 확률 보정 내부 겹수 ---------------------------------------------
    # CalibratedClassifierCV는 자기 안에서 또 한 번 교차검증을 돈다. 바깥 폴드의 학습셋에
    # 어떤 클래스가 그 겹수보다 적게 들어오면 ValueError로 죽는다 — 정지(308건)처럼 표본이
    # 적은 클래스가 세션 단위로 묶여 한쪽에 쏠리면 실제로 발생한다. 미리 재서 맞춰 준다.
    _labels = set(y.tolist())
    inner_cv = max(2, min(
        [3] + [collections.Counter(y[tr].tolist()).get(c, 0)
               for tr, _ in cv.split(X, y, groups=groups) for c in _labels]
    ))
    if inner_cv < 3:
        print(f"      [주의] 확률 보정 내부 겹수를 {inner_cv}로 낮춥니다 "
              f"(어떤 폴드의 학습셋에 표본이 극히 적은 클래스가 있음). "
              f"보정 품질이 떨어지므로 τ를 그대로 신뢰하지 마세요.")

    # ---- 학습 ---------------------------------------------------------
    # SVC(probability=True)는 sklearn 1.9에서 deprecated(1.11 제거) -> CalibratedClassifierCV로 보정
    def make_pipe(C=10.0, gamma="scale", calib_cv=None):
        return Pipeline([
            ("scaler", StandardScaler()),
            ("clf", CalibratedClassifierCV(
                SVC(kernel="rbf", C=C, gamma=gamma, class_weight="balanced", random_state=42),
                method="sigmoid", cv=calib_cv or inner_cv, ensemble=False)),
        ])

    params = {"C": 10.0, "gamma": "scale"}
    if args.grid:
        print("\n[3] 하이퍼파라미터 탐색 (오래 걸립니다)")
        t = time.time()
        gs = GridSearchCV(
            Pipeline([("scaler", StandardScaler()),
                      ("clf", SVC(kernel="rbf", class_weight="balanced", random_state=42))]),
            {"clf__C": [1, 10, 100], "clf__gamma": ["scale", 0.01, 0.1]},
            cv=cv, scoring="f1_macro", n_jobs=-1,
        ).fit(X, y, groups=groups)
        params = {"C": gs.best_params_["clf__C"], "gamma": gs.best_params_["clf__gamma"]}
        print(f"      최적 {params}  (f1_macro {gs.best_score_:.4f}, {time.time() - t:.0f}초)")
    else:
        print(f"\n[3] 하이퍼파라미터 고정 {params}  (탐색하려면 --grid)")

    print("\n[4] 교차검증 확률 산출 (τ 결정·평가에 쓸 편향 없는 확률)")
    t = time.time()
    proba = cross_val_predict(make_pipe(**params), X, y, cv=cv, groups=groups,
                              method="predict_proba", n_jobs=-1)
    classes = np.array(sorted(set(y.tolist())))
    pred = classes[np.argmax(proba, axis=1)]
    print(f"      {time.time() - t:.0f}초")

    acc = float((pred == y).mean())
    macro_f1 = float(f1_score(y, pred, labels=list(classes), average="macro", zero_division=0))
    critical = int(((y == CRITICAL_CLASS) & (pred != CRITICAL_CLASS)).sum())
    print(f"\n[5] τ 적용 전 성능  정답률 {acc * 100:.2f}%  MacroF1 {macro_f1:.4f}  "
          f"치명 오분류 {critical}건")
    names = [c for c in SIGN_CLASSES if c in classes]
    cm = confusion_matrix(y, pred, labels=names)
    print("      혼동행렬 (행=정답, 열=예측)")
    print("        " + "".join(f"{c[:5]:>8}" for c in names))
    for nm, row in zip(names, cm):
        print(f"      {nm[:9]:<9}" + "".join(f"{v:>8,}" for v in row))
    errs = collections.Counter(f"{a}->{b}" for a, b in zip(y, pred) if a != b)
    if errs:
        print(f"      주요 오분류: {dict(errs.most_common(5))}")

    # ---- τ (05 §8-1) ----------------------------------------------------
    print("\n[6] τ 결정 — 05_모델카드_v3 §8-1 절차")
    res = choose_tau(y, proba, classes)
    print(f"      {'τ':>6}{'정답률':>10}{'오분류':>9}{'미판정':>9}{'치명':>7}  판정")
    for r in res["grid"]:
        why = []
        if r["critical"]:
            why.append("치명")
        if r["accuracy"] < KPI["accuracy"]:
            why.append("정답률")
        if r["misclass"] > KPI["misclass"]:
            why.append("오분류")
        if r["reject"] > KPI["reject"]:
            why.append("미판정")
        mark = "통과" if not why else "탈락(" + ",".join(why) + ")"
        star = "*" if res["chosen"] and r["tau"] == res["chosen"]["tau"] else " "
        print(f"    {star}{r['tau']:>6.2f}{r['accuracy'] * 100:>9.2f}%"
              f"{r['misclass'] * 100:>8.2f}%{r['reject'] * 100:>8.2f}%"
              f"{r['critical']:>7}  {mark}")
    if res["chosen"]:
        tau = res["chosen"]["tau"]
        print(f"      -> τ = {tau} 채택 (KPI 전부 만족하는 후보 중 미판정률 최소)")
    else:
        tau = 0.75
        print(f"      -> KPI를 모두 만족하는 τ가 없습니다. 기본값 {tau} 사용.")
        print("         자체 촬영 데이터로 재측정 후 재결정할 것 (회의안건 안건 4).")

    # ---- 최종 모델 + 템플릿 --------------------------------------------
    print("\n[7] 전체 데이터로 최종 모델 학습")
    t = time.time()
    # 최종 모델은 전체 데이터를 쓰므로 폴드 쏠림이 없다 -> 보정 겹수는 표준 3 (가능하면)
    model = make_pipe(**params, calib_cv=max(2, min(3, min(counts.values())))).fit(X, y)
    print(f"      {time.time() - t:.0f}초")

    centroids = {c: X[y == c].mean(axis=0) for c in classes}
    sims: list[float] = []
    for c in classes:
        v = centroids[c]
        Xi = X[y == c]
        sims += list((Xi @ v) / (np.linalg.norm(Xi, axis=1) * np.linalg.norm(v) + 1e-12))
    calib = {"sim_min": float(np.percentile(sims, 5)), "sim_max": float(np.percentile(sims, 95))}
    print(f"      match_score 보정 p5={calib['sim_min']:.4f} p95={calib['sim_max']:.4f}")

    bundle = {
        "format_version": 2,
        "model": model,
        "classes": [str(c) for c in classes],
        "tau": tau,
        "n_frames": 3,
        "match_score_calibration": calib,
        "metadata": {
            "feature_mode": mode,
            "feature_dim": int(X.shape[1]),
            "sklearn_version": sklearn.__version__,
            "numpy_version": np.__version__,
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "trained_on": "local",
            "n_samples": int(len(X)),
            "class_counts": {str(k): int(v) for k, v in counts.items()},
            "split": args.split if groups is not None else "random",
            "cv_folds": args.folds,
            "hyperparams": params,
            "cv_accuracy": round(acc, 4),
            "cv_macro_f1": round(macro_f1, 4),
            "cv_critical_errors": critical,
            "note": "공개 데이터 기준 수치. KPI 실측은 자체 촬영 데이터로 별도 측정할 것 (04 §4).",
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out)
    print(f"\n[8] 저장  {args.out}  ({args.out.stat().st_size / 1e6:.1f} MB)")

    # 템플릿: services/data의 seed_templates.py가 DB에 넣을 수 있게 JSON으로 (담당 김지훈)
    args.templates.write_text(
        json.dumps(
            {
                "feature_mode": mode,
                "feature_dim": int(X.shape[1]),
                "generated_at": bundle["metadata"]["trained_at"],
                "templates": {str(c): centroids[c].tolist() for c in classes},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"    저장  {args.templates}  "
          f"(클래스 {len(classes)}개 centroid — seed_templates.py 입력용)")

    print("\n다음: docker compose up vision  또는  python scripts/webcam_check.py")
    if os.getenv("CONFIDENCE_THRESHOLD"):
        print(f"[주의] 환경변수 CONFIDENCE_THRESHOLD={os.environ['CONFIDENCE_THRESHOLD']} 가 "
              f"번들 τ({tau})보다 우선합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
