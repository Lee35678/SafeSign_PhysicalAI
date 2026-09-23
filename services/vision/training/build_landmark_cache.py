# -*- coding: utf-8 -*-
"""공개 데이터의 랜드마크를 canonical 좌표로 변환해 캐시한다.

왜 필요한가 — negative 합성은 **랜드마크 단계**에서 해야 한다.
joint23은 좌표의 비선형 함수라, 특징 벡터끼리 보간하면 기하학적으로 존재할 수 없는 손이
나온다(마디 길이가 늘어나거나 관절이 꺾이는 방향이 뒤집힌다). 손을 먼저 섞고 나서
정규화 → 특징 추출을 다시 돌려야 진짜 손처럼 생긴 negative가 된다.

canonical 좌표를 캐시하는 이유 — 좌우손 통일·원점·크기·회전이 이미 맞춰져 있어서
서로 다른 샘플의 손가락을 이식하거나 보간해도 좌표계가 어긋나지 않는다.

    python training/build_landmark_cache.py

결과: training/.landmark_cache.npz  (canonical 21x3, 클래스, 세션)
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from cognition.normalize import landmarks_to_array, normalize_landmarks  # noqa: E402

DATA_DIR = SERVICE_ROOT.parent / "data" / "datasets" / "processed"
OUT = SERVICE_ROOT / "training" / ".landmark_cache.npz"


def session_key(source_file: str) -> str:
    """같은 촬영 세션에서 나온 사진을 한 그룹으로 묶는 키 (원래 train_svm.py 의 규칙 그대로).

    복사본 표시 ' (2)', 확장자, '_cropped', '_seg_N', 꼬리 일련번호를 떼어낸다.
    (예: "color_18_0002 (3).png" -> "color_", bfritzy1.jpg / bfritzy2.jpg -> bfritzy)

    **2026-09-23 수정.** 처음 버전은 저장 파일 이름(public_00000 …)을 세션으로 썼다. 그건
    샘플마다 다른 값이라 세션 분할이 전혀 되지 않았다 — 98.81% 허수를 만든 것과 같은 누수다.
    원본 파일 이름(source.file)에서 세션을 뽑아야 한다.
    """
    n = re.sub(r"\.(jpe?g|png|bmp|webp)$", "", source_file, flags=re.I)
    n = re.sub(r"\s*\(\d+\)$", "", n)
    n = re.sub(r"_cropped$", "", n)
    n = re.sub(r"_seg_\d+$", "", n)
    return re.sub(r"\d+$", "", n)


def main() -> int:
    if not DATA_DIR.is_dir():
        print(f"데이터 폴더가 없습니다: {DATA_DIR}")
        return 1

    canon, labels, sessions, subjects = [], [], [], []
    failed = 0
    t0 = time.time()
    files = sorted(DATA_DIR.glob("*/*.json"))
    print(f"파일 {len(files)}개를 읽습니다...")

    for i, path in enumerate(files):
        if i and i % 5000 == 0:
            print(f"  {i}/{len(files)}  ({time.time() - t0:.0f}초)")
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            arr = landmarks_to_array(d["landmarks"])
            c = normalize_landmarks(arr, handedness=d.get("handedness", "Right"))
        except Exception:
            failed += 1
            continue
        cls = d.get("class_name", path.parent.name)
        canon.append(c)
        labels.append(cls)
        src_file = (d.get("source") or {}).get("file") or path.name
        # 세션 = 같은 원본에서 나온 묶음. 누수 방지용 그룹 키 (05 §3-2)
        sessions.append(f"{cls}/{session_key(src_file)}")
        subjects.append(str(d.get("subject_id") or "public"))

    C = np.asarray(canon, dtype=np.float32)
    np.savez_compressed(
        OUT,
        canonical=C,
        labels=np.asarray(labels),
        sessions=np.asarray(sessions),
        subjects=np.asarray(subjects),
    )
    print()
    print(f"저장  {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")
    print(f"  샘플 {len(C)}개 · 실패 {failed}개 · {time.time() - t0:.0f}초")
    uniq, cnt = np.unique(labels, return_counts=True)
    for u, n in zip(uniq, cnt):
        print(f"  {u:<12} {n:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
