# -*- coding: utf-8 -*-
"""Colab 에서 받은 결과를 제자리에 넣고, 로컬 torch 로 읽히는지 확인한다.

    python colab/import_results.py C:/Users/.../Downloads/safesign_results.zip

넣는 곳
  models/handformer_edl.pt      최종 모델 — 서비스·웹캠 확인·KPI 측정이 이 파일을 읽는다
                                (이미 있으면 models/handformer_edl.<시각>.bak.pt 로 옮겨 둔다)
  reports/*.json, reports/*.png 학습 기록과 epoch 그래프

확인하는 것
  · 번들이 로컬 torch 로 열리는가 (Colab torch 버전과 달라도 state_dict 는 호환된다)
  · 한 프레임 추론이 되는가, sum(b) + u = 1 이 성립하는가
  · 선택 근거와 공개 test 결과를 요약해 보여준다

**KPI 측정은 하지 않는다.** 그건 결과를 확인한 뒤 따로 한 번만:
    python scripts/evaluate_edl.py
"""
from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # services/vision
sys.path.insert(0, str(ROOT / "src"))
MODEL = "models/handformer_edl.pt"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    zpath = Path(argv[0])
    if not zpath.exists():
        print(f"파일이 없습니다: {zpath}")
        return 1
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
        allowed = [n for n in names if n == MODEL or
                   (n.startswith("reports/") and n.endswith((".json", ".png")))]
        skipped = sorted(set(names) - set(allowed))
        if MODEL not in allowed:
            print(f"묶음에 {MODEL} 이 없습니다 — Colab 노트북의 3단계(최종)가 끝났는지 확인하세요")
            return 1
        dst = ROOT / MODEL
        if dst.exists():
            bak = dst.with_name(f"handformer_edl.{time.strftime('%Y%m%d_%H%M%S')}.bak.pt")
            dst.rename(bak)
            print(f"기존 모델을 옮겼습니다 -> {bak.name}")
        for n in allowed:
            (ROOT / n).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / n).write_bytes(zf.read(n))
        print(f"넣었습니다 — {MODEL} + reports/ {len(allowed) - 1}개"
              + (f" (무시한 파일 {len(skipped)}개: {skipped[:3]}…)" if skipped else ""))

    import numpy as np
    import torch
    from cognition.evidential import load_predictor

    raw = torch.load(dst, weights_only=False, map_location="cpu")
    pred = load_predictor(dst)
    x = np.zeros((1, 21, 3), np.float32)
    x[0, :, 1] = np.linspace(0, 1.5, 21)                # 모양만 갖춘 가짜 손 — 계산이 도는지만 본다
    out = pred(x)
    ok = abs(float(out["b"].sum() + out["u"][0]) - 1.0) < 1e-4
    print()
    print(f"  로컬 torch {torch.__version__} 로 열림 (학습: torch {raw.get('torch_version', '?')})")
    print(f"  구조 {pred.arch} · 멤버 {len(pred.members)}개 · 증거 {pred.activation} · 클래스 {pred.classes}")
    print(f"  추론 확인: sum(b) + u = 1 {'성립' if ok else '불성립 — 번들을 확인하세요'}")
    s, t = raw.get("summary_val", {}), raw.get("test_public", {})
    if s:
        print(f"  [val]  정답률 {s['val_acc']:.2f}% · LOCO AUC {s.get('loco_auc', float('nan')):.3f}"
              f" · 최고점 epoch 평균 {s['best_epoch_mean']:.0f}")
    if t:
        lo = t.get("loco", {})
        print(f"  [공개 test] 정답률 {t['acc']:.2f}% · 오답탐지 AUC {t['auc_err']:.3f}"
              + (f" · LOCO AUC {lo['mean_auc']:.3f} · 미지 차단 {lo['mean_block']:.1f}%" if lo else ""))
    print()
    print("다음:")
    print("  python scripts/plot_training.py      # 그래프 다시 그리기 (reports/ 기록 사용)")
    print("  python scripts/webcam_check.py       # 웹캠으로 직접 확인 — 자동으로 이 모델을 읽는다")
    print("  python scripts/evaluate_edl.py       # KPI 측정 — 최종 확정 후 한 번만")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
