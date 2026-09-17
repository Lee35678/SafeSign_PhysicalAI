"""정규화된 63차원 특징벡터 -> SVM 분류(8클래스) + DB 템플릿 대비 cosine similarity -> match_score.

TODO(이동혁):
- 학습된 SVM 모델 로드 (joblib, 하이퍼파라미터는 document/05_모델카드_v3 §6에 기재된 값 사용)
- normalize.py 결과(63차원 벡터)를 입력으로 사용
- services/data가 seed_templates.py로 채운 수신호 템플릿 DB(signdb) 조회해 cosine similarity 계산
- smoothing.push_and_check로 N프레임 연속 확인 후에만 판정 확정 (그 전까지는 is_reject 유지 권장)
"""
import os

# document/05_모델카드_v3 §8-0 초기 기본값 (실물/실측 데이터 확보 전 잠정, 카메라 도착 후 재검증)
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))

# document/02_설계문서_v2 §4 확정 7종 + negative (04_데이터셋명세서_v2 §1과 동일 순서 유지)
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


def predict(landmark_frame: dict) -> dict:
    """임시 목업 구현. judgment_result.schema.json 형식 반환.

    landmark_frame.hand_detected가 false거나 목업 상태이면 negative + reject로 응답한다.
    """
    if not landmark_frame.get("hand_detected"):
        return {
            "predicted_class": "negative",
            "confidence": 0.0,
            "match_score": 0,
            "is_reject": True,
            "latency_ms": 0,
        }

    # TODO: normalize.py -> SVM.predict_proba -> CONFIDENCE_THRESHOLD 비교 -> is_reject 결정
    return {
        "predicted_class": "negative",
        "confidence": 0.0,
        "match_score": 0,
        "is_reject": True,
        "latency_ms": 0,
    }
