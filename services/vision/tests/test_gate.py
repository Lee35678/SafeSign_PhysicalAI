"""1단계 소속 게이트(open-set) 테스트.

**왜 이 게이트가 필요한가.** 분류기의 확률은 7종 안에서 정규화된다(합=1). 그래서 7종이 아닌
손모양이 들어와도 "그나마 가장 비슷한" 클래스가 높은 confidence를 받고 τ를 그냥 통과한다.
실측(2026-09-22, 한 클래스씩 빼고 학습 -> 그 클래스를 미지 입력으로 투입):

    τ가 거른 비율 16.7%  /  confidence 0.90 이상으로 오판 77.3%
    분리 AUC — 중심 거리 0.932 vs confidence 0.594(거의 무작위)

τ 값을 조정해서 풀 문제가 아니라 구조 문제라서, 예측 클래스 중심과의 거리를 따로 본다.

**모델 없이 도는 테스트다.** 번들을 흉내 낸 가짜 게이트를 주입해 분기만 검증한다
(실모델 검증은 scripts/webcam_check.py).

실행:
    cd services/vision && python tests/test_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cognition import classify, model_store  # noqa: E402
from cognition.normalize import FEATURE_DIM  # noqa: E402


def _unit(vec) -> np.ndarray:
    v = np.asarray(vec, dtype=float)
    return v / np.linalg.norm(v)


def _install_gate(monkey: dict) -> None:
    """model_store.get_open_set_gate 를 가짜로 바꿔치기."""
    model_store.get_open_set_gate = lambda: monkey  # type: ignore[assignment]


def _restore() -> None:
    model_store._gate_cache = None
    model_store._gate_cache_key = None


def _fake_gate(threshold: float = 0.9) -> dict:
    centroid = np.zeros(FEATURE_DIM)
    centroid[:3] = (1.0, 0.0, 0.0)
    return {
        "kind": "centroid_cosine",
        "percentile": 1.0,
        "thresholds": {"정지": threshold},
        "centroids": {"정지": centroid},
    }


def test_gate_passes_similar_pose():
    """중심과 거의 같은 방향이면 통과해야 한다."""
    _install_gate(_fake_gate(0.9))
    feature = np.zeros(FEATURE_DIM)
    feature[:3] = (1.0, 0.02, 0.0)
    ok, sim = classify.gate_check(feature, "정지")
    assert ok is True or ok == np.True_, (ok, sim)
    assert sim > 0.9
    _restore()


def test_gate_blocks_far_pose():
    """중심에서 멀면 막아야 한다 — 사용자가 겪은 '엄지만 폈는데 좌회전' 상황."""
    _install_gate(_fake_gate(0.9))
    feature = np.zeros(FEATURE_DIM)
    feature[:3] = (0.5, 1.0, 0.0)          # 중심과 이루는 각이 큼
    ok, sim = classify.gate_check(feature, "정지")
    assert not ok, (ok, sim)
    assert sim < 0.9
    _restore()


def test_gate_absent_is_permissive():
    """게이트가 없는 구버전 번들에서는 아무것도 막지 않아야 한다(하위 호환)."""
    _install_gate(None)
    ok, sim = classify.gate_check(np.ones(FEATURE_DIM), "정지")
    assert ok and sim == 0.0
    _restore()


def test_gate_unknown_class_is_permissive():
    """게이트에 없는 클래스면 통과시킨다 — 임계값이 없는데 막아버리면 전부 미판정이 된다."""
    _install_gate(_fake_gate(0.9))
    ok, _ = classify.gate_check(np.ones(FEATURE_DIM), "존재하지_않는_클래스")
    assert ok
    _restore()


def test_gate_dimension_mismatch_is_permissive():
    """특징 차원이 다르면(63 모델에 69 입력 등) 막지 말고 통과 — 조용히 전부 튕기는 것보다 낫다.

    차원 불일치 자체는 model_store의 feature_mode 검사와 inference_error 경로가 잡는다.
    """
    _install_gate(_fake_gate(0.9))
    ok, _ = classify.gate_check(np.ones(FEATURE_DIM + 6), "정지")
    assert ok
    _restore()


def test_reason_code_is_declared():
    """새 reason 코드가 계약서(shared/schemas/judgment_result.schema.json)에 있어야 한다."""
    import json

    schema = json.loads(
        (Path(__file__).resolve().parents[3] / "shared" / "schemas"
         / "judgment_result.schema.json").read_text(encoding="utf-8")
    )
    allowed = schema["properties"]["reason"]["enum"]
    assert classify.REASON_OUT_OF_DISTRIBUTION in allowed, (
        f"{classify.REASON_OUT_OF_DISTRIBUTION} 가 스키마 enum에 없다: {allowed}"
    )


def test_env_switch_disables_gate():
    """OPEN_SET_GATE=off 로 재학습 없이 끌 수 있어야 한다 (게이트가 과하게 튕길 때의 비상구)."""
    import importlib
    import os

    os.environ["OPEN_SET_GATE"] = "off"
    try:
        importlib.reload(classify)
        classify.model_store.get_open_set_gate = lambda: _fake_gate(0.9)  # type: ignore
        feature = np.zeros(FEATURE_DIM)
        feature[:3] = (0.5, 1.0, 0.0)      # 원래대로면 막혀야 하는 입력
        ok, _ = classify.gate_check(feature, "정지")
        assert ok, "OPEN_SET_GATE=off 인데도 막혔다"
    finally:
        del os.environ["OPEN_SET_GATE"]
        importlib.reload(classify)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(tests)}개 통과")
