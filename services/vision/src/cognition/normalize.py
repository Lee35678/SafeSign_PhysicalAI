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

**손 방향(orientation) 축** (2026-09-21 회의 안건 3 A안 채택)
  4번 회전 정렬은 손 기울임에 강해지는 대신 "같은 손모양을 다른 방향으로 든다"는 축을 통째로
  버린다. 손가락 5개 이진 조합(32자리)만으로는 7종을 충분히 떼어놓을 수 없다는 계산 결과
  (document/회의자료_안건3_손모양거리계산표.md §5)에 따라, 버려지던 회전 정보를 **선택적으로**
  특징에 되살릴 수 있게 했다:

      to_feature_vector(..., with_orientation=True) -> 63 + 6 = 69차원

  추가 6차원은 회전행렬의 앞 두 열(x축·y축)이다. 9개를 다 넣으면 중복이고, 오일러각은 불연속
  지점이 생기며, 쿼터니언은 부호 모호성이 있다. 앞 두 열만 쓰면 z축은 외적으로 복원되므로
  정보 손실 없이 연속적이다.

  **기본값은 사용하지 않음이다.** 공개 데이터는 클래스마다 출처 데이터셋이 달라 촬영 각도가
  클래스와 상관되어 있을 수 있고(04_데이터셋명세서_v2 §3), 그 상태로 방향 축을 켜면 모델이
  수신호가 아니라 "어느 데이터셋 사진인가"를 학습한다. 자체 촬영 데이터로 효과가 확인된 뒤에 켠다
  (회의안건_2026-09-21 안건 3 / 안건 1).

**특징 모드 (2026-09-22)**
  세 가지를 지원하고, 어느 것을 썼는지는 번들 metadata["feature_mode"]에 기록된다.

      joint23             (기본·권장) 관절 각도·거리 23차원 — joint_features 참고
      landmark63          canonical 좌표 그대로
      landmark63+orient6  위 + 손 방향 6차원

  실측(27,735건, 세션 단위 5겹): joint23 **88.71%** > landmark63+orient6 77.11% >
  landmark63 77.57%. 좌표를 그대로 쓰는 것보다 관절 관계량으로 바꾸는 쪽이 11%p 이상 낫다.

  주의: MediaPipe world landmark의 z는 단안 추정이라 x·y보다 부정확하다. 방향 6차원 중 z가
  섞인 성분은 상대적으로 노이즈가 크다.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

LANDMARK_COUNT = 21
FEATURE_DIM = LANDMARK_COUNT * 3  # 63 (canonical 좌표를 그대로 평탄화)
ORIENTATION_DIM = 6               # 회전행렬 앞 두 열
FEATURE_DIM_ORIENTED = FEATURE_DIM + ORIENTATION_DIM  # 69
JOINT_DIM = 23                    # 관절 각도·거리 특징 (아래 joint_features 참고)

# 번들 metadata["feature_mode"]에 기록되는 값. 학습과 추론이 반드시 같아야 한다.
FEATURE_MODE_BASE = "landmark63"
FEATURE_MODE_ORIENTED = "landmark63+orient6"
FEATURE_MODE_JOINT = "joint23"

FEATURE_DIMS = {
    FEATURE_MODE_BASE: FEATURE_DIM,
    FEATURE_MODE_ORIENTED: FEATURE_DIM_ORIENTED,
    FEATURE_MODE_JOINT: JOINT_DIM,
}
DEFAULT_FEATURE_MODE = FEATURE_MODE_JOINT

# MediaPipe Hand Landmarker 인덱스 (고정)
WRIST = 0
INDEX_MCP = 5
MIDDLE_MCP = 9
PINKY_MCP = 17

# 스케일/축 계산이 수치적으로 무의미해지는 하한 (world landmark 단위: 미터)
_EPS = 1e-6


def feature_dim(mode: str) -> int:
    """해당 모드의 특징 차원 수."""
    try:
        return FEATURE_DIMS[mode]
    except KeyError:
        raise NormalizationError(
            f"알 수 없는 feature_mode: {mode!r} (가능: {sorted(FEATURE_DIMS)})"
        ) from None


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


def normalize_landmarks(
    points: np.ndarray, handedness: str = "Right", return_rotation: bool = False
):
    """(21, 3) 원본 좌표 -> (21, 3) canonical 좌표.

    Args:
        points: hand_world_landmarks 기준 (21, 3). 단위는 미터지만 스케일 정규화로 상쇄된다.
        handedness: "Right" | "Left" (MediaPipe Handedness). Left면 x를 반전해 Right로 통일.
        return_rotation: True면 `(canonical, rotation)`을 돌려준다. `rotation`은 손의 고유 축을
            입력 좌표계(= 카메라 기준)로 표현한 (3, 3) 행렬로, **canonical에서 제거된 손 방향
            정보 그 자체**다. 방향 축 특징(ORIENTATION_DIM)을 만들 때 쓴다.
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

    if return_rotation:
        return canonical, rotation
    return canonical


def orientation_features(rotation: np.ndarray) -> np.ndarray:
    """회전행렬 (3, 3) -> 방향 특징 (6,).

    앞 두 열(x축·y축)만 쓴다. z축 = cross(x, y)로 복원되므로 정보 손실이 없고,
    오일러각(불연속)·쿼터니언(부호 모호)과 달리 연속적이라 학습에 안전하다.
    두 축 모두 단위벡터이므로 성분은 [-1, 1] 범위이고, canonical 좌표(스케일 1 기준)와
    크기가 비슷해 StandardScaler 이전 단계에서도 한쪽이 지배하지 않는다.

    반환 순서는 `[x축 3개, y축 3개]`다 (열 -> 행으로 전치 후 평탄화). 분류기 입장에서는 순서가
    무의미하지만, 디버깅·시각화 때 축 단위로 끊어 보려면 이 순서여야 한다.
    """
    return np.asarray(rotation, dtype=np.float64)[:, :2].T.reshape(-1)


# 손가락별 (MCP, PIP, DIP, TIP) 인덱스. 엄지는 (CMC, MCP, IP, TIP).
_FINGER_JOINTS = (
    (1, 2, 3, 4),      # 엄지
    (5, 6, 7, 8),      # 검지
    (9, 10, 11, 12),   # 중지
    (13, 14, 15, 16),  # 약지
    (17, 18, 19, 20),  # 소지
)
_TIPS = (4, 8, 12, 16, 20)


def _cos(u: np.ndarray, v: np.ndarray) -> float:
    denom = float(np.linalg.norm(u) * np.linalg.norm(v))
    return 0.0 if denom < _EPS else float(np.dot(u, v) / denom)


def joint_features(canonical: np.ndarray) -> np.ndarray:
    """canonical (21, 3) -> 관절 각도·거리 특징 (23,).

    **왜 좌표 대신 이것인가.** canonical 좌표 63차원에는 "엄지가 펴졌나"가 암묵적으로만 들어
    있다. 손모양 차이가 21개 점에 흩어져 있어서, 손가락 하나 차이는 63차원 중 12개 성분이
    조금씩 움직이는 형태로만 나타난다. 그래서 RBF 커널이 그 방향을 잘 못 잡는다.

    관절 각도·거리로 바꾸면 "손가락 f가 펴졌는가"가 **한 축**이 된다. 실측(27,735건, 세션 단위
    5겹): 63차원 77.57% -> 이 23차원 **88.71%** (+11.14%p), 주의↔우회전 유도 쌍은
    68.0% -> **90.0%**. 둘을 합친 86차원은 82.99%로 오히려 낮아, 원좌표는 잡음으로 작용한다.
    근거 논문: Aiman & Ahmad (2023) — 관절 각도·거리 기반 특징 설계.
    (document/제스처_오분류_해경방안_논문편.md, 05_모델카드_v3 §3-5)

    구성 (총 23개):
      5  손가락별 굽힘   — (MCP->DIP)와 (DIP->TIP) 사이 코사인. 펴면 1에 가깝다
      5  손가락별 폄방향 — (손목->MCP)와 (MCP->TIP) 사이 코사인
      5  손끝~손목 거리  — canonical은 스케일 정규화돼 있어 그대로 비교 가능
      4  인접 손끝 간격  — 손가락 벌어짐
      4  엄지끝~나머지 손끝 거리 — "엄지 하나 차이"를 직접 겨냥한 축
    """
    pts = np.asarray(canonical, dtype=np.float64).reshape(LANDMARK_COUNT, 3)
    wrist = pts[WRIST]
    feats: list[float] = []
    for mcp, _pip, dip, tip in _FINGER_JOINTS:
        feats.append(_cos(pts[dip] - pts[mcp], pts[tip] - pts[dip]))
    for mcp, _pip, _dip, tip in _FINGER_JOINTS:
        feats.append(_cos(pts[mcp] - wrist, pts[tip] - pts[mcp]))
    for tip in _TIPS:
        feats.append(float(np.linalg.norm(pts[tip] - wrist)))
    for a, b in zip(_TIPS[:-1], _TIPS[1:]):
        feats.append(float(np.linalg.norm(pts[a] - pts[b])))
    for tip in _TIPS[1:]:
        feats.append(float(np.linalg.norm(pts[_TIPS[0]] - pts[tip])))
    return np.asarray(feats, dtype=np.float64)


def to_feature_vector(
    landmarks: Sequence[dict],
    handedness: str = "Right",
    mode: str = DEFAULT_FEATURE_MODE,
) -> np.ndarray:
    """landmark_frame의 `landmarks`(+handedness) -> 특징벡터.

    분류기 입력과 match_score(cosine similarity) 계산에 공통으로 쓴다 (05_모델카드_v3 §3-5).

    Args:
        mode: `joint23`(기본, 권장) / `landmark63` / `landmark63+orient6`.
            **학습 때 쓴 값과 추론 때 쓴 값이 반드시 같아야 한다** — 번들
            metadata["feature_mode"]에 기록되고 classify.py가 그 값을 따른다.

    참고(landmark63): 정규화 결과상 손목(0)은 항상 (0,0,0), 중지 MCP(9)는 항상 (0,1,0)이라
    6개 차원은 상수다. 정보량은 없지만 문서가 정의한 "63차원"을 유지하려고 제거하지 않는다.
    """
    if mode not in FEATURE_DIMS:
        raise NormalizationError(
            f"알 수 없는 feature_mode: {mode!r} (가능: {sorted(FEATURE_DIMS)})"
        )
    points = landmarks_to_array(landmarks)

    if mode == FEATURE_MODE_ORIENTED:
        canonical, rotation = normalize_landmarks(
            points, handedness=handedness, return_rotation=True
        )
        return np.concatenate(
            [canonical.reshape(-1), orientation_features(rotation)]
        ).astype(np.float64)

    canonical = normalize_landmarks(points, handedness=handedness)
    if mode == FEATURE_MODE_JOINT:
        return joint_features(canonical)
    return canonical.reshape(-1).astype(np.float64)


def frame_to_feature_vector(
    landmark_frame: dict, mode: str = DEFAULT_FEATURE_MODE
) -> np.ndarray:
    """landmark_frame.schema.json 형식 전체 -> 특징벡터.

    `hand_detected`가 false면 NormalizationError를 던진다(호출 측에서 negative/reject 처리).
    """
    if not landmark_frame.get("hand_detected"):
        raise NormalizationError("hand_detected=false — 손이 검출되지 않은 프레임")
    return to_feature_vector(
        landmark_frame.get("landmarks"),
        handedness=landmark_frame.get("handedness", "Right"),
        mode=mode,
    )


def batch_to_feature_matrix(
    frames: Iterable[dict], mode: str = DEFAULT_FEATURE_MODE
) -> np.ndarray:
    """여러 프레임을 (N, D) 행렬로. 학습 데이터 적재용(정규화 실패 프레임은 호출 측에서 걸러낼 것)."""
    return np.stack([frame_to_feature_vector(f, mode=mode) for f in frames], axis=0)
