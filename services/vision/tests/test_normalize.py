"""정규화 불변성 테스트.

document/05_모델카드_v3.md §3-5는 정규화가 **위치·크기·회전·좌우손** 차이를 제거한다고 주장한다.
이 테스트는 그 주장이 코드에서 실제로 성립하는지 확인한다 — 여기가 깨지면 학습 데이터와 실제 추론
입력이 서로 다른 공간에 놓이게 되므로, 정확도가 조용히 무너진다.

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
    FEATURE_DIM,
    NormalizationError,
    landmarks_to_array,
    normalize_landmarks,
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
    feat = to_feature_vector(_as_landmarks(_sample_hand()))
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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(tests)}개 통과")
