"""정규화 불변성 테스트.

document/05_모델카드_v3.md §3-5는 정규화가 **위치·크기·회전·좌우손** 차이를 제거한다고 주장한다.
이 테스트는 그 주장이 코드에서 실제로 성립하는지 확인한다 — 여기가 깨지면 학습 데이터와 실제 추론
입력이 서로 다른 공간에 놓이게 되므로, 정확도가 조용히 무너진다.

**카메라를 쓰지 않는다.** 합성 좌표로 로직만 검증하는 단위 테스트다.
학습된 모델을 실제 손으로 확인하려면 `scripts/webcam_check.py`(노트북 웹캠)를 쓸 것.

실행:
    cd services/vision && python -m pytest tests -q
    (pytest가 없으면) python tests/test_normalize.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cognition.normalize import (  # noqa: E402
    DEFAULT_FEATURE_MODE,
    FEATURE_DIM,
    FEATURE_DIM_ORIENTED,
    FEATURE_DIMS,
    FEATURE_MODE_BASE,
    FEATURE_MODE_JOINT,
    FEATURE_MODE_ORIENTED,
    JOINT_DIM,
    ORIENTATION_DIM,
    NormalizationError,
    feature_dim,
    joint_features,
    landmarks_to_array,
    normalize_landmarks,
    orientation_features,
    to_feature_vector,
)

rng = np.random.default_rng(0)


def _sample_hand() -> np.ndarray:
    """손처럼 생긴 (21, 3) 좌표. 퇴화(축 평행/영벡터)만 아니면 형태는 중요하지 않다."""
    pts = rng.normal(scale=0.03, size=(21, 3))
    pts[0] = (0.0, 0.0, 0.0)          # 손목
    pts[9] = (0.0, 0.09, 0.0)         # 중지 MCP (주축)
    pts[5] = (-0.02, 0.085, 0.0)      # 검지 MCP
    pts[17] = (0.03, 0.08, 0.0)       # 새끼 MCP (보조축)
    return pts


def _as_landmarks(pts: np.ndarray) -> list[dict]:
    return [{"id": i, "x": float(p[0]), "y": float(p[1]), "z": float(p[2])} for i, p in enumerate(pts)]


def _rotation(yaw: float, pitch: float) -> np.ndarray:
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]])
    return rz @ rx


def test_feature_dim():
    feat = to_feature_vector(_as_landmarks(_sample_hand()), mode=FEATURE_MODE_BASE)
    assert feat.shape == (FEATURE_DIM,), feat.shape


def test_translation_invariance():
    pts = _sample_hand()
    base = normalize_landmarks(pts)
    moved = normalize_landmarks(pts + np.array([0.5, -0.3, 0.2]))
    assert np.allclose(base, moved, atol=1e-9)


def test_scale_invariance():
    pts = _sample_hand()
    base = normalize_landmarks(pts)
    scaled = normalize_landmarks(pts * 2.7)
    assert np.allclose(base, scaled, atol=1e-9)


def test_rotation_invariance():
    """손을 통째로 돌려도 같은 특징이 나와야 한다 (촬영 변인 ±15° 흡수)."""
    pts = _sample_hand()
    base = normalize_landmarks(pts)
    rotated = normalize_landmarks(pts @ _rotation(math.radians(25), math.radians(15)).T)
    assert np.allclose(base, rotated, atol=1e-9)


def test_left_right_unification():
    """같은 손 모양이면 왼손으로 해도 오른손과 같은 특징이 나와야 한다."""
    pts = _sample_hand()
    right = normalize_landmarks(pts, handedness="Right")
    mirrored = pts.copy()
    mirrored[:, 0] = -mirrored[:, 0]          # 실제 왼손처럼 거울상으로 촬영된 좌표
    left = normalize_landmarks(mirrored, handedness="Left")
    assert np.allclose(right, left, atol=1e-9)


def test_canonical_anchor_points():
    """정규화 후 손목은 원점, 중지 MCP는 +y 단위벡터에 놓인다."""
    canonical = normalize_landmarks(_sample_hand())
    assert np.allclose(canonical[0], [0.0, 0.0, 0.0], atol=1e-9)
    assert np.allclose(canonical[9], [0.0, 1.0, 0.0], atol=1e-9)


def test_different_shapes_differ():
    """서로 다른 손 모양은 서로 다른 특징이어야 한다(정규화가 정보를 다 지우면 안 된다)."""
    a = _sample_hand()
    b = a.copy()
    b[8] += np.array([0.0, 0.05, 0.0])        # 검지 끝만 이동
    assert not np.allclose(normalize_landmarks(a), normalize_landmarks(b), atol=1e-6)


def test_landmark_order_independent():
    pts = _sample_hand()
    lms = _as_landmarks(pts)
    shuffled = list(reversed(lms))
    assert np.allclose(landmarks_to_array(lms), landmarks_to_array(shuffled))


def test_rejects_bad_input():
    for bad in ([], [{"id": 0, "x": 0, "y": 0, "z": 0}], None):
        try:
            landmarks_to_array(bad)
        except NormalizationError:
            continue
        raise AssertionError(f"NormalizationError가 나와야 함: {bad}")


def test_rejects_degenerate_hand():
    pts = _sample_hand()
    pts[9] = pts[0]  # 손목과 중지 MCP가 같은 위치 -> 스케일 계산 불가
    try:
        normalize_landmarks(pts)
    except NormalizationError:
        return
    raise AssertionError("퇴화 입력은 NormalizationError여야 함")


# --------------------------------------------------------------------------
# 관절 특징 (joint23) — 2026-09-22
#
# canonical 좌표 63차원은 "엄지가 펴졌나"를 암묵적으로만 담는다. 관절 각도·거리로 바꾸면
# 그것이 한 축이 된다. 실측 77.57% -> 88.71%, 주의↔우회전 68.0% -> 90.0%.
# --------------------------------------------------------------------------

def test_joint_dim_and_default_mode():
    lms = _as_landmarks(_sample_hand())
    assert to_feature_vector(lms, mode=FEATURE_MODE_JOINT).shape == (JOINT_DIM,)
    assert DEFAULT_FEATURE_MODE == FEATURE_MODE_JOINT, "기본 모드는 joint23이어야 한다"
    assert to_feature_vector(lms).shape == (JOINT_DIM,), "인자 없이 부르면 기본 모드"


def test_feature_dim_table_matches_actual():
    """FEATURE_DIMS 표와 실제 출력 길이가 어긋나면 번들·스키마 검증이 조용히 깨진다."""
    lms = _as_landmarks(_sample_hand())
    for mode, dim in FEATURE_DIMS.items():
        assert to_feature_vector(lms, mode=mode).shape == (dim,), mode
        assert feature_dim(mode) == dim


def test_unknown_mode_raises():
    with np.errstate(all="ignore"):
        try:
            to_feature_vector(_as_landmarks(_sample_hand()), mode="없는모드")
        except NormalizationError:
            return
    raise AssertionError("알 수 없는 모드인데 예외가 안 났다")


def test_joint_features_invariant_like_canonical():
    """관절 특징도 위치·크기·회전에 불변이어야 한다(canonical 좌표에서 계산하므로)."""
    pts = _sample_hand()
    variants = {
        "이동": pts + np.array([0.3, -0.2, 0.1]),
        "확대": pts * 2.5,
        "회전": pts @ _rotation(0.7, 0.3).T,
    }
    base = to_feature_vector(_as_landmarks(pts), mode=FEATURE_MODE_JOINT)
    for name, v in variants.items():
        got = to_feature_vector(_as_landmarks(v), mode=FEATURE_MODE_JOINT)
        assert np.allclose(base, got, atol=1e-9), f"{name}에 불변이 아니다"


def test_joint_features_separate_finger_states():
    """손가락 하나를 접으면 그 손가락 관련 성분이 움직여야 한다 — 이 특징의 존재 이유."""
    pts = _sample_hand()
    pts[8] = (-0.02, 0.16, 0.0)        # 검지 TIP을 쭉 편 위치로
    extended = to_feature_vector(_as_landmarks(pts), mode=FEATURE_MODE_JOINT)
    pts[8] = (-0.02, 0.05, 0.03)       # 접은 위치로
    folded = to_feature_vector(_as_landmarks(pts), mode=FEATURE_MODE_JOINT)
    assert not np.allclose(extended, folded, atol=1e-3)


def test_joint_features_all_finite():
    """퇴화 입력(손끝이 겹침 등)에서도 NaN이 나오면 안 된다 — 분류기가 통째로 죽는다."""
    pts = _sample_hand()
    pts[4] = pts[8] = pts[0]           # 엄지·검지 끝이 손목과 같은 위치
    feat = joint_features(normalize_landmarks(pts))
    assert np.all(np.isfinite(feat)), feat


# --------------------------------------------------------------------------
# 손 방향(orientation) 축 — 2026-09-21 회의 안건 3 A안
#
# 손모양 63차원은 회전 불변을 **유지하면서**, 추가 6차원이 회전을 **담아야** 한다.
# 둘 중 하나라도 깨지면 방향 축을 도입한 의미가 없다.
# --------------------------------------------------------------------------

def test_orientation_dim():
    lms = _as_landmarks(_sample_hand())
    assert to_feature_vector(lms, mode=FEATURE_MODE_BASE).shape == (FEATURE_DIM,)
    assert to_feature_vector(lms, mode=FEATURE_MODE_ORIENTED).shape == (FEATURE_DIM_ORIENTED,)


def test_orientation_is_appended_not_mixed():
    """앞 63차원은 방향 축을 켜도 그대로여야 한다(기존 모델과 해석이 어긋나지 않게)."""
    lms = _as_landmarks(_sample_hand())
    base = to_feature_vector(lms, mode=FEATURE_MODE_BASE)
    oriented = to_feature_vector(lms, mode=FEATURE_MODE_ORIENTED)
    assert np.allclose(base, oriented[:FEATURE_DIM])


def test_orientation_axes_are_orthonormal():
    """추가 6차원 = 회전행렬의 x축·y축. 각각 단위벡터이고 서로 직교해야 한다."""
    feat = to_feature_vector(_as_landmarks(_sample_hand()), mode=FEATURE_MODE_ORIENTED)
    x_axis, y_axis = feat[FEATURE_DIM:FEATURE_DIM + 3], feat[FEATURE_DIM + 3:]
    assert len(x_axis) + len(y_axis) == ORIENTATION_DIM
    assert math.isclose(float(np.linalg.norm(x_axis)), 1.0, abs_tol=1e-9)
    assert math.isclose(float(np.linalg.norm(y_axis)), 1.0, abs_tol=1e-9)
    assert abs(float(np.dot(x_axis, y_axis))) < 1e-9


def test_orientation_captures_rotation():
    """손을 돌리면 손모양 63차원은 그대로, 방향 6차원만 바뀌어야 한다."""
    pts = _sample_hand()
    rotated = pts @ _rotation(0.6, -0.4).T
    a = to_feature_vector(_as_landmarks(pts), mode=FEATURE_MODE_ORIENTED)
    b = to_feature_vector(_as_landmarks(rotated), mode=FEATURE_MODE_ORIENTED)
    assert np.allclose(a[:FEATURE_DIM], b[:FEATURE_DIM], atol=1e-9), "손모양이 회전에 흔들렸다"
    assert not np.allclose(a[FEATURE_DIM:], b[FEATURE_DIM:], atol=1e-3), "방향이 회전을 못 담았다"


def test_orientation_features_from_rotation_matrix():
    """normalize_landmarks(return_rotation=True)가 돌려준 행렬과 일관되어야 한다."""
    pts = _sample_hand()
    _, rotation = normalize_landmarks(pts, return_rotation=True)
    feat = to_feature_vector(_as_landmarks(pts), mode=FEATURE_MODE_ORIENTED)
    assert np.allclose(orientation_features(rotation), feat[FEATURE_DIM:])
    # z축은 외적으로 복원 가능 -> 6개만 실어도 정보 손실이 없다
    x_axis, y_axis = rotation[:, 0], rotation[:, 1]
    assert np.allclose(np.cross(x_axis, y_axis), rotation[:, 2], atol=1e-9)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(tests)}개 통과")
