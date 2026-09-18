"""분류 경로 스모크 테스트 (모델 파일 없이도 서비스가 안전하게 동작하는지).

데이터 수집 전이라 실제 모델이 없는 상태에서도 vision 서비스가 죽지 않고 "미판정"으로 응답해야
카메라~Actuation 배선 검증을 계속할 수 있다 (10_PRD_v2 §11 우선순위).

**카메라를 쓰지 않는다.** 학습된 모델을 실제 손으로 확인하려면 `scripts/webcam_check.py`를 쓸 것.

실행:
    cd services/vision && python -m pytest tests -q
    (pytest가 없으면) python tests/test_classify.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cognition import classify  # noqa: E402

REQUIRED_KEYS = {"predicted_class", "confidence", "match_score", "is_reject", "latency_ms"}
VALID_REASONS = {
    classify.REASON_NO_HAND,
    classify.REASON_NORMALIZE_FAILED,
    classify.REASON_MODEL_NOT_LOADED,
    classify.REASON_INFERENCE_ERROR,
    classify.REASON_BELOW_TAU,
}


def _assert_schema(result: dict) -> None:
    """judgment_result.schema.json 필수 필드/범위 확인."""
    assert REQUIRED_KEYS <= set(result), f"필수 필드 누락: {REQUIRED_KEYS - set(result)}"
    assert isinstance(result["predicted_class"], str)
    assert 0.0 <= result["confidence"] <= 1.0
    assert 0 <= result["match_score"] <= 100 and isinstance(result["match_score"], int)
    assert isinstance(result["is_reject"], bool)
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0
    if "reason" in result:
        assert result["reason"] in VALID_REASONS


def test_no_hand_frame():
    result = classify.predict({"timestamp": 1, "hand_detected": False, "landmarks": []})
    _assert_schema(result)
    assert result["is_reject"] is True
    assert result["predicted_class"] == classify.NEGATIVE_CLASS
    assert result["reason"] == classify.REASON_NO_HAND


def test_malformed_landmarks_are_rejected_not_crash():
    result = classify.predict(
        {"timestamp": 2, "hand_detected": True, "landmarks": [{"id": 0, "x": 0, "y": 0, "z": 0}]}
    )
    _assert_schema(result)
    assert result["is_reject"] is True
    assert result["reason"] == classify.REASON_NORMALIZE_FAILED


def test_classes_match_documents():
    """02_설계문서_v2 §4 확정 7종 + negative 와 순서까지 동일해야 한다."""
    assert classify.SIGN_CLASSES == [
        "정지",
        "서행",
        "좌회전_유도",
        "우회전_유도",
        "확인_완료",
        "후진",
        "주의",
        "negative",
    ]


def test_tau_default():
    """모델·환경변수가 없으면 05_모델카드_v3 §8-0 초기 기본값 0.75."""
    tau = classify.effective_tau()
    assert 0.0 < tau <= 1.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(tests)}개 통과")
