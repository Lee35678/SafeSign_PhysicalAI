# -*- coding: utf-8 -*-
"""Evidential 모델(MLP / HandFormer / 앙상블)을 실제 데이터로 평가한다.

재는 것
  ① 잘 만든 자세를 맞히는가    자체 촬영 정상 105시도 315프레임 (KPI, 테이크 단위)
  ② 7종 아닌 것을 막는가       자체 촬영 애매한 자세 16테이크 48프레임
  ③ 실사용에서 어떤가          웹캠 로그 (손을 만드는 중·푸는 중이 전부 들어 있다)
  ④ 배포할 수 있는가           CPU 한 프레임 추론 지연 (RPi5 에서 돌아야 한다)

거부 규칙
  relative   u > max b   임계값 없음 (b = 믿음 질량)
  threshold  u > tau_u   참고용 스윕. 여기서 고르면 평가 데이터로 고르는 것이므로 **채택 근거로
                         쓰지 않는다** (11 §8-6)

    python scripts/evaluate_edl.py                          # models/handformer_edl.pt

**최종 KPI 측정 전용이다.** 자체 촬영(JH·me01)을 읽는다. 모델을 고르는 데 이 결과를 쓰면
KPI 데이터가 "처음 보는 데이터"가 아니게 된다 — 최종 모델이 정해진 뒤 한 번만 돌린다.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
import time
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from cognition.evaldata import RealData  # noqa: E402
from cognition.evidential import EvidentialPredictor, load_predictor  # noqa: E402

# 비교 기준 — **운영에 쓰기로 한 모델**의 기록.
# SVM(RBF, joint23) + 중심 코사인 게이트 p10 + tau 0.75 를 아래와 같은 데이터로 잰 값이다.
# 이 브랜치에는 SVM 코드가 없으므로 숫자를 상수로 들고 비교한다.
BASELINE = {"acc": 97.1, "bad": 0.0, "rej": 2.9, "crit": 0, "amb": 81.2, "live": 40.5,
            "auc_ood": 0.820}
BASELINE_NAME = "SVM + 코사인 게이트 p10 (운영 모델)"


def cpu_latency_ms(predictor: EvidentialPredictor, sample: np.ndarray, n: int = 200) -> float:
    """CPU 한 프레임 추론 지연 중앙값 (ms). RPi5 배포 가능성을 가늠하는 대리 지표."""
    import torch
    cpu = EvidentialPredictor.from_bundle(predictor.to_bundle(), "cpu")
    prev = torch.get_num_threads()
    torch.set_num_threads(1)                  # RPi5 코어 하나 정도의 조건에 가깝게
    x = sample[:1]
    for _ in range(10):
        cpu(x)
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        cpu(x)
        ts.append((time.perf_counter() - t) * 1000)
    torch.set_num_threads(prev)
    return float(np.median(ts))


def print_report(res: dict, lat: float | None = None) -> None:
    print(f"  {'거부 규칙':<24}{'정답률':>8}{'오분류':>8}{'미판정':>8}{'치명':>6}"
          f"{'애매 차단':>11}{'웹캠 차단':>11}")
    print("  " + "-" * 78)
    b = BASELINE
    print(f"  {BASELINE_NAME:<30}{b['acc']:>7.1f}%{b['bad']:>7.1f}%{b['rej']:>7.1f}%{b['crit']:>6}"
          f"{b['amb']:>10.1f}%{b['live']:>10.1f}%")
    print("  " + "-" * 78)
    for label, a, bd, rj, cr, ab, lv in res["rows"]:
        print(f"  {label:<24}{a:>7.1f}%{bd:>7.1f}%{rj:>7.1f}%{cr:>6}{ab:>10.1f}%{lv:>10.1f}%")
    print(f"  {'KPI 목표':<24}{'>=92%':>8}{'<=3%':>8}{'<=5%':>8}{0:>6}")
    print()
    uc, ua, ul = res["u_median"]
    print(f"  u 중앙값 — 정상 {uc:.3f} · 애매 {ua:.3f} · 웹캠 {ul:.3f}")
    if "auc_ood" in res:
        print(f"  정상 vs 애매 분리 AUC  {res['auc_ood']:.3f}   (운영 모델 {BASELINE['auc_ood']:.3f})")
    if lat is not None:
        print(f"  CPU 1스레드 한 프레임 추론  {lat:.2f} ms")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="handformer_edl.pt",
                    help="models/ 안의 파일 이름 또는 경로")
    ap.add_argument("--subjects", default=None,
                    help="채점할 촬영자 (쉼표 구분). 예: me01 — 검증에 쓴 촬영자를 빼고 채점할 때")
    args = ap.parse_args()
    path = Path(args.model)
    if not path.exists():
        path = SERVICE_ROOT / "models" / args.model
    if not path.exists():
        print(f"모델이 없습니다: {path}")
        return 1
    pred = load_predictor(path)
    data = RealData(args.subjects.split(",") if args.subjects else None)
    print(f"실제 데이터 — {data.describe()}")
    print(f"모델: {path.name} · 구조 {pred.arch} · 멤버 {len(pred.members)}개 · "
          f"증거 {pred.activation} · negative 학습 데이터 0건")
    print()
    print_report(data.score(pred), cpu_latency_ms(pred, data.CC))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
