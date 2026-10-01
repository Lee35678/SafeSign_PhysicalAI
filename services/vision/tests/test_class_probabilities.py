"""판정 결과의 7종별 확률(class_probabilities, 2026-09-30) — web 일치율의 근거가 되는 값.

  · 분류기가 돌면(정답 후보·τ 미달 모두) 7종 확률이 들어가고, 합이 1이며, confidence와 같은 값을 담는가
  · 손 미검출·소속 게이트 차단(OOD)에는 들어가지 않는가 (OOD에 높은 확률이 보이면 안내와 모순)

가짜 모델·가짜 특징을 끼워서 모델 파일 없이 돈다.
실행: python tests/test_class_probabilities.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cognition import classify, model_store  # noqa: E402
from cognition.normalize import FEATURE_DIM  # noqa: E402

CLASSES = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]
FRAME = {"hand_detected": True, "handedness": "Right", "landmarks": []}


class FakeModel:
    classes_ = np.array(CLASSES)

    def __init__(self, probs):
        self.probs = np.asarray(probs, dtype=float)

    def predict_proba(self, X):
        return self.probs.reshape(1, -1)


def _run(probs, gate=None):
    saved = (classify.frame_to_feature_vector, model_store.get_model, model_store.get_open_set_gate,
             model_store.get_feature_mode)
    classify.frame_to_feature_vector = lambda frame, mode=None: np.ones(FEATURE_DIM)
    model_store.get_model = lambda: FakeModel(probs)
    model_store.get_open_set_gate = lambda: gate
    model_store.get_feature_mode = lambda default=None: default
    try:
        return classify.predict(FRAME)
    finally:
        (classify.frame_to_feature_vector, model_store.get_model, model_store.get_open_set_gate,
         model_store.get_feature_mode) = saved


def test_probabilities_are_reported_for_confident_frame():
    r = _run([0.02, 0.9, 0.02, 0.02, 0.02, 0.01, 0.01])
    assert r["predicted_class"] == "서행" and r["is_reject"] is False
    p = r["class_probabilities"]
    assert set(p) == set(CLASSES) and abs(sum(p.values()) - 1) < 1e-3
    assert p["서행"] == r["confidence"], "확률표의 예측 클래스 값 = confidence"
    assert p["정지"] == 0.02, "목표가 정지라면 이 손의 일치율은 2점이 된다(다른 손동작 → 낮음)"


def test_probabilities_are_reported_below_tau():
    r = _run([0.30, 0.35, 0.10, 0.10, 0.05, 0.05, 0.05])
    assert r["is_reject"] is True and r["reason"] == classify.REASON_BELOW_TAU
    assert r["class_probabilities"]["서행"] == 0.35


def test_no_probabilities_when_gate_blocks():
    far = np.zeros(FEATURE_DIM)
    far[0] = 1.0                      # 가짜 특징(전부 1)과 방향이 크게 다른 중심
    gate = {"kind": "centroid_cosine", "percentile": 10, "thresholds": {"서행": 0.99}, "centroids": {"서행": far}}
    r = _run([0.02, 0.9, 0.02, 0.02, 0.02, 0.01, 0.01], gate=gate)
    assert r["reason"] == classify.REASON_OUT_OF_DISTRIBUTION
    assert "class_probabilities" not in r


def test_no_probabilities_without_hand():
    r = classify.predict({"hand_detected": False, "landmarks": []})
    assert r["reason"] == classify.REASON_NO_HAND and "class_probabilities" not in r


if __name__ == "__main__":
    _passed = []
    for _n, _f in sorted(globals().copy().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
            _passed.append(_n)
            print(f"  ok  {_n}")
    print(f"{len(_passed)}개 통과")
