"""21 keypoints -> 정규화 -> 63차원 특징벡터.

document/05_모델카드_v3.md §3-5 "정규화 절차"의 구현체다. **학습(Colab)과 추론(RPi5)이 반드시 이
동일한 코드를 써야 한다** — 학습 때와 추론 때 전처리가 달라지면(train-serve skew) 정답률이 조용히
무너진다. 그래서 이 모듈은 numpy에만 의존하도록 두어 Colab에서 `git clone` 후 그대로 import할 수 있다
(services/vision/training/train_svm_colab.ipynb 참고).

정규화 단계 (05_모델카드_v3 §3-5):
  1. 좌우 손 정규화 — Handedness가 Left면 x를 반전해 Right 기준으로 통일
  2. 원점 이동 — 손목(landmark 0)을 원점으로
  3. 스케일 정규화 — 손목(0)↔중지 MCP(9) 거리로 나눠 손 크기·카메라 거리 영향 제거
  4. 회전 정렬 — 손의 고유 좌표계를 만들어 3D 회전(손 기울임 ±15° 변인)을 흡수
  5. 21×3 = 63차원 벡터로 평탄화

4번은 문서가 "손목→중지 MCP 벡터를 기준 축에 정렬"이라고만 정하고 있다. 축 하나만 맞추면 그 축을
중심으로 도는 회전(roll)이 남으므로, 여기서는 손바닥 가로 방향(검지 MCP(5)→새끼 MCP(17))을 두 번째
기준으로 써서 3축을 모두 고정한다 — 남는 자유도 없이 완전한 canonical 자세가 된다.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

LANDMARK_COUNT = 21
FEATURE_DIM = LANDMARK_COUNT * 3  # 63

# MediaPipe Hand Landmarker 인덱스 (고정)
WRIST = 0
INDEX_MCP = 5
MIDDLE_MCP = 9
PINKY_MCP = 17

# 스케일/축 계산이 수치적으로 무의미해지는 하한 (world landmark 단위: 미터)
_EPS = 1e-6


class NormalizationError(ValueError):
    """랜드마크가 정규화 불가능한 상태(손가락 수 부족, 축 퇴화 등)."""


def landmarks_to_array(landmarks: Sequence[dict]) -> np.ndarray:
    """landmark_frame.schema.json의 `landmarks` 배열 -> (21, 3) ndarray.

    `id` 기준으로 정렬하므로 입력 순서가 뒤섞여 있어도 안전하다.
    """
    if landmarks is None or len(landmarks) != LANDMARK_COUNT:
        raise NormalizationError(
            f"랜드마크가 {LANDMARK_COUNT}개여야 하는데 {0 if landmarks is None else len(landmarks)}개 들어옴"
        )

    points = np.zeros((LANDMARK_COUNT, 3), dtype=np.float64)
    seen = set()
    for lm in landmarks:
        idx = int(lm["id"])
        if not 0 <= idx < LANDMARK_COUNT:
            raise NormalizationError(f"랜드마크 id 범위 오류: {idx}")
        points[idx] = (float(lm["x"]), float(lm["y"]), float(lm["z"]))
        seen.add(idx)
    if len(seen) != LANDMARK_COUNT:
        raise NormalizationError(f"랜드마크 id 누락/중복: {sorted(set(range(LANDMARK_COUNT)) - seen)}")
    return points


def normalize_landmarks(points: np.ndarray, handedness: str = "Right") -> np.ndarray:
    """(21, 3) 원본 좌표 -> (21, 3) canonical 좌표.

    Args:
        points: hand_world_landmarks 기준 (21, 3). 단위는 미터지만 스케일 정규화로 상쇄된다.
        handedness: "Right" | "Left" (MediaPipe Handedness). Left면 x를 반전해 Right로 통일.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape != (LANDMARK_COUNT, 3):
        raise NormalizationError(f"(21, 3) 배열이어야 하는데 {pts.shape} 들어옴")
    if not np.all(np.isfinite(pts)):
        raise NormalizationError("랜드마크에 NaN/Inf 포함")

    # 1) 좌우 손 정규화: 왼손은 거울상으로 뒤집어 오른손 기준으로 통일
    #    (좌/우 어느 손으로 시연해도 같은 클래스로 분류되도록 — 05_모델카드_v3 §3-5 4번)
    if str(handedness).strip().lower().startswith("l"):
        pts = pts.copy()
        pts[:, 0] = -pts[:, 0]

    # 2) 원점 이동: 손목이 원점
    pts = pts - pts[WRIST]

    # 3) 스케일 정규화: 손목→중지 MCP 길이를 1로
    scale = float(np.linalg.norm(pts[MIDDLE_MCP]))
    if scale < _EPS:
        raise NormalizationError("손목과 중지 MCP가 같은 위치 — 스케일 정규화 불가")
    pts = pts / scale

    # 4) 회전 정렬: 손 고유 좌표계(y=손가락 방향, x=손바닥 가로, z=손등 법선)로 변환
    y_axis = pts[MIDDLE_MCP]
    y_norm = float(np.linalg.norm(y_axis))
    if y_norm < _EPS:
        raise NormalizationError("주축(손목→중지 MCP) 퇴화")
    y_axis = y_axis / y_norm

    across = pts[PINKY_MCP] - pts[INDEX_MCP]  # 손바닥 가로 방향(검지 MCP → 새끼 MCP)
    x_axis = across - np.dot(across, y_axis) * y_axis  # y 성분 제거(그람-슈미트)
    x_norm = float(np.linalg.norm(x_axis))
    if x_norm < _EPS:
        raise NormalizationError("보조축(검지 MCP→새끼 MCP)이 주축과 평행 — 회전 정렬 불가")
    x_axis = x_axis / x_norm

    z_axis = np.cross(x_axis, y_axis)

    rotation = np.stack([x_axis, y_axis, z_axis], axis=1)  # 열이 각 축인 (3, 3)
    canonical = pts @ rotation  # == (R^T @ p) 를 행벡터로 쓴 것

    return canonical


def to_feature_vector(landmarks: Sequence[dict], handedness: str = "Right") -> np.ndarray:
    """landmark_frame의 `landmarks`(+handedness) -> (63,) 특징벡터.

    분류기 입력과 match_score(cosine similarity) 계산에 공통으로 쓴다 (05_모델카드_v3 §3-5 5번).

    참고: 정규화 결과상 손목(0)은 항상 (0,0,0), 중지 MCP(9)는 항상 (0,1,0)이라 6개 차원은 상수다.
    정보량은 없지만 문서가 정의한 "63차원"을 그대로 유지하기 위해 제거하지 않는다.
    """
    points = landmarks_to_array(landmarks)
    canonical = normalize_landmarks(points, handedness=handedness)
    return canonical.reshape(-1).astype(np.float64)


def frame_to_feature_vector(landmark_frame: dict) -> np.ndarray:
    """landmark_frame.schema.json 형식 전체 -> (63,) 특징벡터.

    `hand_detected`가 false면 NormalizationError를 던진다(호출 측에서 negative/reject 처리).
    """
    if not landmark_frame.get("hand_detected"):
        raise NormalizationError("hand_detected=false — 손이 검출되지 않은 프레임")
    return to_feature_vector(
        landmark_frame.get("landmarks"),
        handedness=landmark_frame.get("handedness", "Right"),
    )


def batch_to_feature_matrix(frames: Iterable[dict]) -> np.ndarray:
    """여러 프레임을 (N, 63) 행렬로. 학습 데이터 적재용(정규화 실패 프레임은 호출 측에서 걸러낼 것)."""
    return np.stack([frame_to_feature_vector(f) for f in frames], axis=0)
