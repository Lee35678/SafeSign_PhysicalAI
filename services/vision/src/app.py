"""vision 서비스 진입점.

담당: 이동혁 (파이프라인·판정로직 R)
역할: Pi Camera Module 3 -> MediaPipe(LIVE_STREAM) -> 정규화 -> 분류/일치율 산출.
입출력 스키마는 shared/schemas/landmark_frame.schema.json, judgment_result.schema.json 참고.

카메라가 이 서비스(RPi5)에 직결되어 있으므로, 실제 런타임에는 외부에서 프레임을 POST 받는 것이
아니라 이 서비스가 스스로 카메라 루프를 돌며 최신 판정 결과를 만들어 둔다 (GET /latest로 조회).
POST /predict는 카메라 없이 분류기 로직만 테스트하기 위한 개발용 엔드포인트다.
"""
import logging
import threading
import time

from fastapi import FastAPI

from cognition import classify, model_store, smoothing, templates
from perception import capture

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="SafeSign Vision Service")

_judgment_lock = threading.Lock()
_latest_judgment: dict = {
    "predicted_class": classify.NEGATIVE_CLASS,
    "confidence": 0.0,
    "match_score": 0,
    "is_reject": True,
    "latency_ms": 0,
    "reason": classify.REASON_NO_HAND,
}


def _cognition_loop() -> None:
    """perception.capture가 채우는 최신 랜드마크를 폴링해 판정 결과를 갱신.

    N프레임 연속 판정(05_모델카드_v3 §3-6)은 여기서 적용한다: 단일 프레임 판정이 τ를 넘겨도
    N프레임 연속 같은 클래스가 아니면 아직 미판정으로 둔다.

    TODO(이동혁): 폴링 대신 capture 콜백에서 큐로 밀어주는 구조로 바꿔 불필요한 재계산 제거.
    """
    global _latest_judgment
    last_seen_ts = None
    idle_sleep_s = 0.005  # 새 프레임이 없을 때 CPU를 점유하지 않도록 (RPi5는 추론에 CPU를 다 써야 함)
    while True:
        frame = capture.get_latest_landmark_frame()
        if frame is None or frame.get("timestamp") == last_seen_ts:
            time.sleep(idle_sleep_s)
            continue
        last_seen_ts = frame.get("timestamp")

        result = classify.predict(frame)

        # 프레임 단위로 τ를 통과한 클래스만 누적, 그 외(미판정)는 누적을 끊는다
        observed = None if result["is_reject"] else result["predicted_class"]
        confirmed = smoothing.push_and_check(observed)
        if not result["is_reject"] and not confirmed:
            result["is_reject"] = True
            result["reason"] = "awaiting_consecutive_frames"
        result["consecutive"] = smoothing.streak()

        with _judgment_lock:
            _latest_judgment = result


@app.on_event("startup")
def _startup() -> None:
    model_store.load_bundle()  # 모델 상태를 기동 시점에 로그로 남긴다(없어도 계속 진행)
    threading.Thread(target=capture.run_capture_loop, daemon=True).start()
    threading.Thread(target=_cognition_loop, daemon=True).start()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "vision",
        "model": model_store.describe(),
        "tau": classify.effective_tau(),
        "n_frames": smoothing.N_FRAMES,
        "templates": templates.available_signs(),
    }


@app.get("/latest")
def latest():
    """웹 상태머신이 폴링(또는 추후 WebSocket 구독)하는 최신 판정 결과."""
    with _judgment_lock:
        return _latest_judgment


@app.post("/predict")
def predict(landmark_frame: dict):
    """단일 landmark_frame으로 분류기만 테스트하는 개발용 엔드포인트 (카메라 미사용)."""
    return classify.predict(landmark_frame)


@app.post("/reset")
def reset():
    """다음 수신호로 넘어갈 때 웹 상태머신이 호출 — N프레임 누적을 초기화한다."""
    smoothing.reset()
    return {"status": "ok"}
