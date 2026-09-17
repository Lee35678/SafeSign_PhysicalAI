"""63차원 특징벡터 -> 분류(SVM/MLP) + DB 템플릿 대비 cosine similarity -> match_score.

TODO(이동혁):
- 분류기 로드 (02_설계문서_v1 §2 파이프라인 방식 확정 후 구현)
- data 서비스가 관리하는 수신호 템플릿 DB(signdb) 조회 연동
- 신뢰도 임계값(CONFIDENCE_THRESHOLD) 적용 -> is_reject 판단
"""


def predict(landmark_frame: dict) -> dict:
    """임시 목업 구현. judgment_result.schema.json 형식 반환."""
    return {
        "predicted_class": "unknown",
        "confidence": 0.0,
        "match_score": 0,
        "is_reject": True,
        "latency_ms": 0,
    }
