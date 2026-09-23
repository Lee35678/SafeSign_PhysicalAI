# -*- coding: utf-8 -*-
"""Colab 에 올릴 묶음을 만든다 — colab/safesign_colab.zip

    python colab/make_bundle.py

담는 것 (전부 합쳐 약 6MB)
  코드   src/cognition/{edl, handformer, evidential, normalize}.py
         training/{train_handformer, select_model}.py · scripts/plot_training.py
         tests/{test_edl, test_handformer}.py          (Colab 에서 먼저 돌려 보는 점검용)
  데이터 training/.landmark_cache.npz                  공개 데이터 27,735건의 canonical 랜드마크
  노트북 colab/colab_train.ipynb

**KPI 데이터(자체 촬영 JH·me01)와 웹캠 로그는 절대 담지 않는다** — 담기 전에 확인하고,
하나라도 섞이면 멈춘다. Colab 에서 할 일은 공개 데이터로 학습하는 것뿐이다.
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # services/vision
OUT = ROOT / "colab" / "safesign_colab.zip"
FILES = [
    "src/cognition/__init__.py",
    "src/cognition/edl.py",
    "src/cognition/handformer.py",
    "src/cognition/evidential.py",
    "src/cognition/normalize.py",
    "training/train_handformer.py",
    "training/select_model.py",
    "training/.landmark_cache.npz",
    "scripts/plot_training.py",
    "tests/test_edl.py",
    "tests/test_handformer.py",
    "colab/colab_train.ipynb",
]
FORBIDDEN = ("self_recorded", "logs/", "evaldata", "evaluate_edl", ".jsonl")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    missing = [f for f in FILES if not (ROOT / f).exists()]
    if missing:
        print("없는 파일:", missing)
        if "training/.landmark_cache.npz" in missing:
            print("  먼저: python training/build_landmark_cache.py")
        return 1
    bad = [f for f in FILES if any(x in f for x in FORBIDDEN)]
    if bad:
        print("KPI 데이터·도구가 섞였습니다 — 멈춥니다:", bad)
        return 1

    import numpy as np
    z = np.load(ROOT / "training/.landmark_cache.npz", allow_pickle=False)
    subjects = sorted(set(z["subjects"].tolist()))
    if any(s in ("JH", "me01") for s in subjects):
        print("랜드마크 캐시에 자체 촬영 촬영자가 들어 있습니다 — 멈춥니다:", subjects)
        return 1

    manifest = {f: {"bytes": (ROOT / f).stat().st_size, "sha256": sha256(ROOT / f)} for f in FILES}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in FILES:
            zf.write(ROOT / f, f)
        zf.writestr("MANIFEST.json", json.dumps({"files": manifest, "samples": int(len(z["labels"])),
                                                 "subjects": subjects}, ensure_ascii=False, indent=1))
    print(f"만들었습니다  {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB · 파일 {len(FILES)}개)")
    print(f"  공개 데이터 {len(z['labels'])}건 · 자체 촬영 없음 확인")
    print("다음: Google Drive 의 MyDrive/safesign_vision/ 에 이 zip 을 올리고 colab_train.ipynb 를 연다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
