"""vision 서비스 진입점.

담당: 이동혁 (파이프라인·판정로직 R)
역할: Pi Camera Module 3 -> MediaPipe(LIVE_STREAM) -> 정규화 -> 분류/일치율 산출.
입출력 스키마는 shared/schemas/landmark_frame.schema.json, judgment_result.schema.json 참고.

카메라가 이 서비스(RPi5)에 직결되어 있으므로, 실제 런타임에는 외부에서 프레임을 POST 받는 것이
아니라 이 서비스가 스스로 카메라 루프를 돌며 최신 판정 결과를 만들어 둔다 (GET /latest로 조회).
POST /predict는 카메라 없이 분류기 로직만 테스트하기 위한 개발용 엔드포인트다.
"""
import threading

from fastapi import FastAPI

from cognition import classify, smoothing
from perception import capture

app = FastAPI(title="SafeSign Vision Service")

_judgment_lock = threading.Lock()
_latest_judgment: dict = {
    "predicted_class": "negative",
    "confidence": 0.0,
    "match_score": 0,
    "is_reject": True,
    "latency_ms": 0,
}


def _cognition_loop() -> None:
    """perception.capture가 채우는 최신 랜드마크를 폴링해 판정 결과를 갱신.

    TODO(이동혁): 폴링 대신 콜백/큐 기반으로 바꿔 불필요한 재계산을 줄일 것.
    """
    global _latest_judgment
    last_seen_ts = None
    while True:
        frame = capture.get_latest_landmark_frame()
        if frame is not None and frame["timestamp"] != last_seen_ts:
            last_seen_ts = frame["timestamp"]
            result = classify.predict(frame)
            if not result["is_reject"]:
                confirmed = smoothing.push_and_check(result["predicted_class"])
                result["is_reject"] = not confirmed
            with _judgment_lock:
                _latest_judgment = result


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=capture.run_capture_loop, daemon=True).start()
    threading.Thread(target=_cognition_loop, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok", "service": "vision"}


@app.get("/latest")
def latest():
    """웹 상태머신이 폴링(또는 추후 WebSocket 구독)하는 최신 판정 결과."""
    with _judgment_lock:
        return _latest_judgment


@app.post("/predict")
def predict(landmark_frame: dict):
    """단일 landmark_frame으로 분류기만 테스트하는 개발용 엔드포인트 (카메라 미사용)."""
    return classify.predict(landmark_frame)
