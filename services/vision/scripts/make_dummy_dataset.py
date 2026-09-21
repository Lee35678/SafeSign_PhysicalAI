"""학습 파이프라인 예행연습용 **더미** 랜드마크 데이터 생성기.

데이터 담당(김지훈)이 실제 수신호 데이터를 아직 수집 중이라, 그 전에 학습 노트북과 추론 코드의
배선이 맞는지 확인하려고 만든 도구다. **실제 학습에는 절대 쓰지 말 것** — 손 모양을 흉내 낸
합성 좌표일 뿐, 실제 사람 손의 분포가 아니다.

용도:
  1. `train_svm_colab.ipynb`가 기대하는 폴더/JSON 형식을 눈으로 확인
  2. 정규화 → 학습 → 번들 저장 → 추론 로딩까지 한 바퀴 돌려보기 (services/vision/tests 참고)

생성 형식 (04_데이터셋명세서_v2 §6 폴더 구조안):
    {out}/{class_name}/{subject_id}_{index}.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

SIGN_CLASSES = [
    "정지",
    "서행",
    "좌회전_유도",
    "우회전_유도",
    "확인_완료",
    "후진",
    "주의",
    "negative",
]

# 02_설계문서_v2 §4 "AiHand 표현"을 손가락 펴짐(True)/굽힘(False)으로 옮긴 것
# 순서: [엄지, 검지, 중지, 약지, 소지]
FINGER_STATE = {
    "정지": [True, True, True, True, True],
    "서행": [False, True, True, False, False],
    "좌회전_유도": [True, True, False, False, False],
    "우회전_유도": [True, False, False, False, True],   # 2026-09-20 약지→소지 변경
    "확인_완료": [False, False, False, False, False],    # 2026-09-20 따봉→주먹 변경
    "후진": [False, True, False, False, False],
    "주의": [False, False, False, False, True],
    # negative는 "손은 있으나 7종이 아닌 자세"다(04_데이터셋명세서_v2 §1). 확인_완료가 주먹이 되면서
    # 겹치지 않도록 엄지+중지라는 7종에 없는 조합을 쓴다.
    "negative": [True, False, True, False, False],
}

# MediaPipe 손 랜드마크 인덱스: 각 손가락의 [MCP, PIP, DIP, TIP]
FINGER_CHAINS = {
    0: [1, 2, 3, 4],       # 엄지
    1: [5, 6, 7, 8],       # 검지
    2: [9, 10, 11, 12],    # 중지
    3: [13, 14, 15, 16],   # 약지
    4: [17, 18, 19, 20],   # 소지
}
# 손바닥에서 각 손가락 MCP가 놓이는 x 위치(손목 기준, 대략적인 비율)
MCP_X = {0: -0.35, 1: -0.18, 2: 0.0, 3: 0.16, 4: 0.30}


def synth_hand(finger_extended: list[bool], rng: np.random.Generator) -> np.ndarray:
    """손가락 펴짐 상태 -> (21, 3) 가짜 world landmarks (미터 단위 흉내)."""
    pts = np.zeros((21, 3), dtype=np.float64)
    pts[0] = (0.0, 0.0, 0.0)  # 손목

    palm_len = 0.09  # 손목→중지 MCP 약 9cm
    for finger, chain in FINGER_CHAINS.items():
        mcp_pos = np.array([MCP_X[finger] * palm_len, palm_len * (0.55 if finger == 0 else 1.0), 0.0])
        pts[chain[0]] = mcp_pos
        extended = finger_extended[finger]
        seg = palm_len * (0.33 if extended else 0.22)
        # 펴면 손가락 방향(+y)으로 뻗고, 굽히면 손바닥 쪽(-z)으로 말린다
        direction = np.array([0.0, 1.0, 0.0]) if extended else np.array([0.0, 0.15, -0.95])
        direction = direction / np.linalg.norm(direction)
        for j, idx in enumerate(chain[1:], start=1):
            pts[idx] = mcp_pos + direction * seg * j

    # 촬영 변인 흉내: 약간의 관절 노이즈 + 전체 3D 회전 + 손 크기 편차
    pts += rng.normal(scale=0.0025, size=pts.shape)
    pts *= rng.uniform(0.85, 1.15)

    angle = rng.uniform(-math.radians(20), math.radians(20))
    ca, sa = math.cos(angle), math.sin(angle)
    rot = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    tilt = rng.uniform(-math.radians(15), math.radians(15))
    ct, st = math.cos(tilt), math.sin(tilt)
    rot = rot @ np.array([[1.0, 0.0, 0.0], [0.0, ct, -st], [0.0, st, ct]])
    return pts @ rot.T


def main() -> None:
    parser = argparse.ArgumentParser(description="더미 랜드마크 데이터셋 생성 (실제 학습용 아님)")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "training" / "_dummy_dataset"))
    parser.add_argument("--subjects", nargs="+", default=["dummy01", "dummy02", "dummy03", "dummy_ext"],
                        help="촬영자 ID. 마지막 하나를 외부인(test)처럼 쓰면 subject-wise 분할 연습이 된다")
    parser.add_argument("--per-class", type=int, default=30, help="촬영자·클래스당 샘플 수")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_root = Path(args.out)
    rng = np.random.default_rng(args.seed)

    total = 0
    for class_name in SIGN_CLASSES:
        class_dir = out_root / class_name
        class_dir.mkdir(parents=True, exist_ok=True)
        for subject in args.subjects:
            for i in range(args.per_class):
                handedness = "Left" if rng.random() < 0.3 else "Right"
                pts = synth_hand(FINGER_STATE[class_name], rng)
                if handedness == "Left":
                    pts = pts.copy()
                    pts[:, 0] = -pts[:, 0]  # 실제 왼손처럼 거울상으로 저장
                doc = {
                    "class_name": class_name,
                    "subject_id": subject,
                    "handedness": handedness,
                    "landmarks": [
                        {"id": idx, "x": float(p[0]), "y": float(p[1]), "z": float(p[2])}
                        for idx, p in enumerate(pts)
                    ],
                }
                (class_dir / f"{subject}_{i:03d}.json").write_text(
                    json.dumps(doc, ensure_ascii=False), encoding="utf-8"
                )
                total += 1

    # Windows 콘솔(cp949)에서도 깨지지 않도록 이모지 없이 출력한다
    print(f"더미 데이터 {total}개 생성: {out_root}")
    print("[주의] 합성 좌표입니다. 실제 모델 학습에는 사용하지 마세요.")


if __name__ == "__main__":
    main()
