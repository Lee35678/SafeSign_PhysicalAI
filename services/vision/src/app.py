"""vision 서비스 진입점.

담당: 이동혁 (파이프라인·판정로직 R)
역할: 카메라 프레임 -> MediaPipe 랜드마크 -> 정규화 -> 분류/일치율 산출.
입출력 스키마는 shared/schemas/landmark_frame.schema.json, judgment_result.schema.json 참고.
"""
from fastapi import FastAPI

from cognition import classify

app = FastAPI(title="SafeSign Vision Service")


@app.get("/health")
def health():
    return {"status": "ok", "service": "vision"}


@app.post("/predict")
def predict(landmark_frame: dict):
    """landmark_frame.schema.json 형식의 입력을 받아 judgment_result.schema.json 형식으로 반환.

    TODO(이동혁): 실제 정규화 + 분류기/유사도 로직 연결 (현재는 목업 응답).
    """
    return classify.predict(landmark_frame)
