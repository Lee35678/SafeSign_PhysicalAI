"""정규화된 특징벡터 -> SVM 분류(7클래스) + 템플릿 대비 cosine similarity -> judgment_result.

문서 근거:
- 분류기/특징: document/05_모델카드_v3.md §3-5(정규화), §5(SVM 채택 근거), §6(학습 방법)
- τ(신뢰도 임계값): §8-0 초기 기본값 0.75, §8-1 실측 확정 절차
- 출력 스키마: document/03_인터페이스계약서_v2.md §4 / shared/schemas/judgment_result.schema.json

**negative는 학습 클래스가 아니다** (2026-09-21 회의 안건 2 A안).
"손은 있는데 7종 중 아무것도 아닌 자세"는 종류가 무한해서 하나의 클래스로 학습시킬 수 없고,
실제로 공개 데이터의 negative는 0건이었다. 대신 τ(신뢰도 임계값) 미달을 미판정으로 처리하고,
그 출력 라벨로만 "negative"를 쓴다. 미판정률 KPI(≤5%)는 τ로 조절한다.

모델 파일이 없으면(학습 전) 항상 negative/reject를 반환한다 — 카메라~Actuation 배선 검증은
모델 없이도 진행할 수 있어야 하기 때문.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np

from cognition import model_store, templates
from cognition.normalize import (
    FEATURE_MODE_BASE,
    FEATURE_MODE_ORIENTED,
    NormalizationError,
    frame_to_feature_vector,
)

logger = logging.getLogger(__name__)

# document/02_설계문서_v2 §4 확정 7종 (04_데이터셋명세서_v2 §1과 동일 순서 유지).
# 분류기가 실제로 학습하는 클래스 목록이다 — negative는 여기 없다 (안건 2 A).
SIGN_CLASSES = [
    "정지",
    "서행",
    "좌회전_유도",
    "우회전_유도",
    "확인_완료",
    "후진",
    "주의",
]

# 미판정(reject) 시 predicted_class에 넣는 라벨. 학습 클래스가 아니라 **출력 전용 값**이다.
# Macro F1 계산에서도 제외된다 (05_모델카드_v3 §7-1).
NEGATIVE_CLASS = "negative"

# judgment_result.reason 코드 (03_인터페이스계약서_v2 §4).
# 웹 상태머신이 SC-04(카메라 인식 실패)와 SC-03b(오답/미판정)를 구분하는 데 쓴다.
REASON_NO_HAND = "no_hand"                 # 손 미검출 -> SC-04 후보
REASON_NORMALIZE_FAILED = "normalize_failed"  # 랜드마크는 왔지만 정규화 불가 -> SC-04 후보
REASON_MODEL_NOT_LOADED = "model_not_loaded"  # 분류기 미배치(학습 전)
REASON_INFERENCE_ERROR = "inference_error"
REASON_BELOW_TAU = "below_tau"             # 신뢰도 부족 -> 재시도 유도(SC-03b)

# 05_모델카드_v3 §8-0 초기 기본값. 환경변수 > 모델 번들 > 이 기본값 순으로 우선한다.
_DEFAULT_TAU = 0.75
_ENV_TAU: Optional[float] = (
    float(os.environ["CONFIDENCE_THRESHOLD"]) if os.getenv("CONFIDENCE_THRESHOLD") else None
)


def effective_tau() -> float:
    """실제로 적용되는 τ.

    우선순위: 환경변수 CONFIDENCE_THRESHOLD > 모델 번들에 저장된 값 > 기본값(0.75).
    (운영 중 임계값만 급히 바꿔야 할 때 모델 재학습 없이 환경변수로 덮어쓸 수 있게 한 것)
    """
    if _ENV_TAU is not None:
        return _ENV_TAU
    return model_store.get_tau(_DEFAULT_TAU)


def _reject_result(latency_ms: int, reason: str, match: int = 0) -> dict:
    return {
        "predicted_class": NEGATIVE_CLASS,
        "confidence": 0.0,
        "match_score": match,
        "is_reject": True,
        "latency_ms": latency_ms,
        "reason": reason,
    }


def _elapsed_ms(started_perf: float, landmark_frame: dict) -> int:
    """판정 지연(ms).

    프레임에 `captured_at_ms`(벽시계 기준 캡처 시각)가 있으면 캡처~판정 완료까지를 재고,
    없으면 이 함수 내부 처리 시간만 잰다. KPI(판정 지연 P95 ≤ 1.0초, 01_프로젝트계획서_v4)는
    전자 기준이므로 perception이 captured_at_ms를 채워주는 것이 정확하다.
    """
    captured_at = landmark_frame.get("captured_at_ms")
    if captured_at:
        return max(0, int(time.time() * 1000 - float(captured_at)))
    return int((time.perf_counter() - started_perf) * 1000)


def predict(landmark_frame: dict) -> dict:
    """landmark_frame -> judgment_result (03_인터페이스계약서_v2 §4).

    N프레임 연속 판정(smoothing)은 호출 측(app.py)에서 적용한다 — 이 함수는 단일 프레임 판정만 한다.
    """
    started = time.perf_counter()

    # 1) 특징 추출 (손 미검출/정규화 실패는 곧바로 미판정)
    if not landmark_frame.get("hand_detected"):
        return _reject_result(_elapsed_ms(started, landmark_frame), REASON_NO_HAND)
    try:
        # 학습 때 쓴 특징 모드를 그대로 따라간다 (train-serve skew 방지).
        # 번들이 없으면 기본 63차원 — 어차피 아래에서 model_not_loaded로 빠진다.
        with_orientation = (
            model_store.get_feature_mode(FEATURE_MODE_BASE) == FEATURE_MODE_ORIENTED
        )
        feature = frame_to_feature_vector(landmark_frame, with_orientation=with_orientation)
    except NormalizationError as exc:
        logger.debug("정규화 실패: %s", exc)
        return _reject_result(_elapsed_ms(started, landmark_frame), REASON_NORMALIZE_FAILED)

    # 2) 분류기 (모델이 아직 없으면 미판정으로 안전하게 빠진다)
    model = model_store.get_model()
    if model is None:
        return _reject_result(_elapsed_ms(started, landmark_frame), REASON_MODEL_NOT_LOADED)

    try:
        proba = model.predict_proba(feature.reshape(1, -1))[0]
        classes = list(getattr(model, "classes_", model_store.get_classes()))
    except Exception:  # 모델/특징 차원 불일치 등
        logger.exception("분류기 추론 실패")
        return _reject_result(_elapsed_ms(started, landmark_frame), REASON_INFERENCE_ERROR)

    best_idx = int(np.argmax(proba))
    predicted_class = str(classes[best_idx])
    confidence = float(proba[best_idx])

    # 3) τ 미달이면 미판정(is_reject) — 미판정률 KPI(≤5%)의 분자가 되는 지점
    is_reject = confidence < effective_tau()

    # 4) 일치율: 예측 클래스 템플릿과의 코사인 유사도 (분류와 별개 지표)
    score = templates.match_score(
        feature, predicted_class, model_store.get_match_score_calibration()
    )

    result = {
        "predicted_class": predicted_class,
        "confidence": round(confidence, 4),
        "match_score": score,
        "is_reject": is_reject,
        "latency_ms": _elapsed_ms(started, landmark_frame),
    }
    if is_reject:
        result["reason"] = REASON_BELOW_TAU
    return result
