# -*- coding: utf-8 -*-
"""단일 프레임 판정 — Evidential Deep Learning (vision_research 브랜치).

이 브랜치가 feature/vision 과 다른 점
  feature/vision:  SVM(7클래스) -> 소속 게이트(거리) -> τ(확신도) -> N프레임
                   "7종 밖"을 분류기 **바깥**에서 거리로 판단한다. 수치를 사람이 맞춰야 했다.

  vision_research: EDL 신경망 -> 불확실성 u -> N프레임
                   "7종 밖"을 모델이 **직접** 말한다. 게이트도 τ도 없다.

왜 softmax 로는 안 되는가
  softmax 는 K개 클래스 안에서 합이 1이 되도록 정규화한다. 학습한 적 없는 손이 들어와도
  "그나마 가장 비슷한" 클래스가 높은 확률을 받는다 — 7종 밖이라는 선택지가 문법에 없다.
  EDL 은 디리클레 분포를 내므로 **믿음 질량 b 와 불확실성 u 의 합이 1** 이 되고,
  u 가 "어느 클래스도 아님"의 자리를 맡는다. (기대 확률 p 는 그 자체로 합이 1이라
  여전히 그 자리가 없다 — 그래서 거부 판단에는 p 가 아니라 b 와 u 를 쓴다.)

거부 규칙 (환경변수 EDL_REJECT 로 바꾼다)
  relative  (기본)  u > max_k b_k        임계값이 없다 (b = 믿음 질량)
  threshold         u > EDL_TAU_U        임계값을 쓸 때. 고르는 데이터와 채점 데이터를
                                         반드시 분리할 것 (11 §8-6 의 교훈)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np

from cognition import model_store, templates
from cognition.edl import REJECT_RULE_RELATIVE, REJECT_RULE_THRESHOLD, reject_mask
from cognition.normalize import (
    NormalizationError, joint_features, landmarks_to_array, normalize_landmarks,
)

logger = logging.getLogger(__name__)

# 03_인터페이스계약서_v2 §4 — 학습 클래스 7종
SIGN_CLASSES = [
    "정지",
    "서행",
    "좌회전_유도",
    "우회전_유도",
    "확인_완료",
    "후진",
    "주의",
]

# 미판정 시 predicted_class 에 넣는 라벨. 학습 클래스가 아니라 **출력 전용 값**이다.
NEGATIVE_CLASS = "negative"

# reason 코드 — 웹 상태머신이 SC-04(인식 실패)와 SC-03b(미판정)를 구분하는 데 쓴다.
REASON_NO_HAND = "no_hand"
REASON_NORMALIZE_FAILED = "normalize_failed"
REASON_MODEL_NOT_LOADED = "model_not_loaded"
REASON_INFERENCE_ERROR = "inference_error"
# EDL 에서는 "확신 부족"과 "7종 밖"이 하나의 값(u)으로 합쳐진다. 웹 계약을 깨지 않도록
# 기존 코드를 그대로 쓰되, 의미는 "불확실성이 너무 높다"이다.
REASON_OUT_OF_DISTRIBUTION = "out_of_distribution"

_RULE = os.getenv("EDL_REJECT", REJECT_RULE_RELATIVE).strip().lower()
_TAU_U: Optional[float] = (
    float(os.environ["EDL_TAU_U"]) if os.getenv("EDL_TAU_U") else None
)
_DEFAULT_TAU_U = 0.4


def effective_rule() -> tuple[str, float]:
    """실제로 적용되는 (거부 규칙, 임계값)."""
    rule = _RULE if _RULE in (REJECT_RULE_RELATIVE, REJECT_RULE_THRESHOLD) else REJECT_RULE_RELATIVE
    return rule, (_TAU_U if _TAU_U is not None else _DEFAULT_TAU_U)


def _reject_result(latency_ms: int, reason: str, match: int = 0,
                   uncertainty: float | None = None) -> dict:
    out = {
        "predicted_class": NEGATIVE_CLASS,
        "confidence": 0.0,
        "match_score": match,
        "is_reject": True,
        "latency_ms": latency_ms,
        "reason": reason,
    }
    if uncertainty is not None:
        out["uncertainty"] = round(uncertainty, 4)
    return out


def _elapsed_ms(started_perf: float, landmark_frame: dict) -> int:
    """판정 지연(ms). 프레임에 captured_at_ms 가 있으면 캡처~판정 완료까지를 잰다."""
    captured_at = landmark_frame.get("captured_at_ms")
    if captured_at:
        return max(0, int(time.time() * 1000 - float(captured_at)))
    return int((time.perf_counter() - started_perf) * 1000)


def infer(canonical: np.ndarray) -> Optional[tuple[str, float, float, float]]:
    """canonical (21,3) -> (예측 클래스, 기대 확률 p, 불확실성 u, 최대 믿음 b). 없으면 None.

    구조(MLP/HandFormer)·앙상블·증거 활성 함수는 번들이 정한다 — cognition.evidential 참고.
    """
    pred = model_store.get_predictor()
    if pred is None:
        return None
    out = pred(canonical[None].astype(np.float32))
    i = int(out["pred"][0])
    return (pred.classes[i], float(out["p"][0, i]), float(out["u"][0]),
            float(out["b_max"][0]))


def predict(landmark_frame: dict) -> dict:
    """landmark_frame -> judgment_result (03_인터페이스계약서_v2 §4).

    N프레임 연속 판정은 호출 측(app.py)에서 적용한다 — 여기는 단일 프레임만 본다.
    """
    started = time.perf_counter()

    if not landmark_frame.get("hand_detected"):
        return _reject_result(_elapsed_ms(started, landmark_frame), REASON_NO_HAND)
    try:
        canonical = normalize_landmarks(
            landmarks_to_array(landmark_frame.get("landmarks")),
            handedness=landmark_frame.get("handedness", "Right"),
        )
        feature = joint_features(canonical)       # 일치율(match_score) 계산용
    except (NormalizationError, ValueError, TypeError, KeyError) as exc:
        logger.debug("정규화 실패: %s", exc)
        return _reject_result(_elapsed_ms(started, landmark_frame), REASON_NORMALIZE_FAILED)

    try:
        out = infer(canonical)
    except Exception:
        logger.exception("EDL 추론 실패")
        return _reject_result(_elapsed_ms(started, landmark_frame), REASON_INFERENCE_ERROR)
    if out is None:
        return _reject_result(_elapsed_ms(started, landmark_frame), REASON_MODEL_NOT_LOADED)

    predicted_class, confidence, uncertainty, belief = out

    # 거부 판정 — 게이트도 τ도 아닌 **하나의 값**으로 끝난다
    import torch

    rule, tau_u = effective_rule()
    rejected = bool(reject_mask(torch.tensor([[belief]]),
                                torch.tensor([[uncertainty]]), rule, tau_u)[0])
    if rejected:
        return _reject_result(_elapsed_ms(started, landmark_frame),
                              REASON_OUT_OF_DISTRIBUTION, uncertainty=uncertainty)

    score = templates.match_score(
        feature, predicted_class, model_store.get_match_score_calibration()
    )
    return {
        "predicted_class": predicted_class,
        "confidence": round(confidence, 4),
        "uncertainty": round(uncertainty, 4),
        "match_score": score,
        "is_reject": False,
        "latency_ms": _elapsed_ms(started, landmark_frame),
    }
