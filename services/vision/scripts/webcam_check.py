"""노트북 웹캠으로 학습된 모델을 눈으로 확인하는 도구.

담당: 이동혁 (vision)

**이건 단위 테스트가 아니라 "사람이 보고 판단하는" 확인 도구다.**
`tests/`의 테스트들은 합성 좌표로 정규화·분류 로직만 검증하고 카메라를 쓰지 않는다. 반면 이 스크립트는
실제 손을 카메라에 비춰서 **학습된 분류기가 제대로 맞히는지**를 화면으로 확인한다.

추론 경로는 **운영 코드와 동일**하다 — `cognition/`의 normalize → classify → smoothing을 그대로
쓴다(웹캠 캡처 부분만 다름). 그래서 여기서 잘 동작하면 RPi5에서도 같은 판정이 나온다.

  운영(RPi5)          : Pi Camera Module 3 (CSI, picamera2) → MediaPipe LIVE_STREAM → cognition/*
  이 스크립트(노트북) : USB/내장 웹캠 (OpenCV)              → MediaPipe LIVE_STREAM → cognition/*

사용법:
    # 준비(최초 1회): 가상환경에 확인용 의존성 설치
    python -m venv .venv && .venv\\Scripts\\activate
    pip install -r requirements-dev.txt

    # 실행
    python scripts/webcam_check.py                 # 기본 카메라(0번)
    python scripts/webcam_check.py --camera 1      # 카메라가 여러 개면
    python scripts/webcam_check.py --list-cameras  # 어떤 인덱스가 되는지 확인
    python scripts/webcam_check.py --no-window --max-frames 60   # 창 없이 콘솔 출력만

    q 또는 ESC : 종료 / r : N프레임 누적 초기화
    1~7 : 지금 하려는 수신호 지정(정답 라벨) / 0 : 7종 아닌 애매한 자세 / ` : 라벨 해제

진단 로그 (--log):
    무엇이 어떻게 틀렸는지 오프라인에서 분석하려면 로그를 남긴다.

        python scripts/webcam_check.py --log

    숫자키로 "지금 내가 하려는 동작"을 찍어두면, 그게 정답 라벨이 되어 오판정을 셀 수 있다.
    로그에는 **원본 랜드마크 21개**가 함께 들어가므로 나중에 다른 특징 모드로 다시 계산해
    비교할 수 있다. 분석은 `python scripts/analyze_log.py <로그파일>`.

모델이 아직 없어도 실행된다 — 그 경우 랜드마크만 그려주므로 **카메라·MediaPipe 배선 확인**에는
지금 당장 쓸 수 있다(판정은 계속 model_not_loaded). 모델을 만들려면
`python training/train_svm.py` (로컬, 16초).

**평가 데이터를 모으는 것은 이 스크립트가 아니라 `record_dataset.py`다.** 여기는 눈으로 보는 확인만.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

# 05_모델카드_v3 §1: MediaPipe Hand Landmarker 공식 모델 번들 (Apache License 2.0)
LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

# 화면에 한글 폰트가 없을 때 쓸 표기 (cv2.putText는 한글을 못 그린다)
ROMAN = {
    "정지": "STOP",
    "서행": "SLOW",
    "좌회전_유도": "TURN LEFT",
    "우회전_유도": "TURN RIGHT",
    "확인_완료": "CONFIRM",
    "후진": "REVERSE",
    "주의": "CAUTION",
    "negative": "(none)",
}

# 숫자키 -> 정답 라벨. "지금 내가 하려는 동작"을 찍어두면 오판정을 셀 수 있다.
LABEL_KEYS = {
    "1": "정지", "2": "서행", "3": "좌회전_유도", "4": "우회전_유도",
    "5": "확인_완료", "6": "후진", "7": "주의",
    "0": "애매한자세",        # 7종 중 아무것도 아닌 자세 (소속 게이트 검증용)
}

# MediaPipe 손 랜드마크 연결 (그리기용)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),            # 엄지
    (0, 5), (5, 6), (6, 7), (7, 8),            # 검지
    (5, 9), (9, 10), (10, 11), (11, 12),       # 중지
    (9, 13), (13, 14), (14, 15), (15, 16),     # 약지
    (13, 17), (17, 18), (18, 19), (19, 20),    # 소지
    (0, 17),                                    # 손바닥 아래
]


# --------------------------------------------------------------------------------------
# 최신 추론 결과 보관 (LIVE_STREAM 콜백은 다른 스레드에서 호출된다)
# --------------------------------------------------------------------------------------
class LatestResult:
    def __init__(self) -> None:
        import threading

        self._lock = threading.Lock()
        self.frame: Optional[dict] = None       # landmark_frame (world landmarks, 운영과 동일 스키마)
        self.image_landmarks: Optional[list] = None  # 화면에 그릴 이미지 좌표(0~1)

    def set(self, frame: dict, image_landmarks: Optional[list]) -> None:
        with self._lock:
            self.frame = frame
            self.image_landmarks = image_landmarks

    def get(self):
        with self._lock:
            return self.frame, self.image_landmarks


def ensure_landmarker(path: Path, allow_download: bool = True) -> Path:
    """hand_landmarker.task 가 없으면 공식 URL에서 받아온다."""
    if path.exists():
        return path
    if not allow_download:
        raise SystemExit(
            f"MediaPipe 모델 파일이 없습니다: {path}\n"
            f"  {LANDMARKER_URL} 를 받아 위 경로에 두거나, --download 옵션을 쓰세요."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"MediaPipe 모델 다운로드 중... ({LANDMARKER_URL})")
    urllib.request.urlretrieve(LANDMARKER_URL, path)
    print(f"  저장 완료: {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return path


def list_cameras(max_index: int = 5) -> None:
    import cv2

    print("사용 가능한 카메라 인덱스를 찾는 중...")
    found = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if sys.platform == "win32" else 0)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                found.append((idx, frame.shape[1], frame.shape[0]))
        cap.release()
    if found:
        for idx, w, h in found:
            print(f"  --camera {idx}   ({w}x{h})")
    else:
        print("  열리는 카메라가 없습니다. 다른 앱이 카메라를 쓰고 있는지, 권한이 있는지 확인하세요.")


# --------------------------------------------------------------------------------------
# 화면 그리기
# --------------------------------------------------------------------------------------
def _load_korean_font(size: int = 26):
    """한글 표시용 폰트. 없으면 None (영문 표기로 폴백)."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    candidates = [
        "C:/Windows/Fonts/malgun.ttf",          # Windows 맑은 고딕
        "C:/Windows/Fonts/malgunsl.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def draw_overlay(image, result: dict, fps: float, n_frames: int, font,
                 intended: Optional[str] = None, logged: int = 0) -> "any":
    """판정 결과를 화면 위에 올린다. 한글 폰트가 있으면 PIL로, 없으면 영문으로."""
    import cv2

    is_reject = result.get("is_reject", True)
    cls = result.get("predicted_class", "negative")
    color = (0, 200, 0) if not is_reject else (60, 60, 220)  # BGR: 확정=초록, 미판정=빨강

    # 배경 박스
    cv2.rectangle(image, (0, 0), (image.shape[1], 92), (30, 30, 30), -1)

    conf = result.get("confidence", 0.0)
    score = result.get("match_score", 0)
    reason = result.get("reason", "")
    consecutive = result.get("consecutive", 0)
    line2 = (
        f"conf {conf:.2f}   match {score:3d}   "
        f"{consecutive}/{n_frames} frames   {result.get('latency_ms', 0):3d}ms   {fps:4.1f}fps"
    )

    if font is not None:
        from PIL import Image, ImageDraw
        import numpy as np

        pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        label = cls if not is_reject else f"{cls}  (미판정: {reason})"
        draw.text((12, 6), label, font=font, fill=(color[2], color[1], color[0]))
        image = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    else:
        label = ROMAN.get(cls, cls)
        if is_reject:
            label = f"{label}  (reject: {reason})"
        cv2.putText(image, label, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    cv2.putText(image, line2, (12, 76), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1)

    if intended is not None:
        # 정답 라벨과 예측이 맞는지 한눈에 — 초록 일치 / 빨강 불일치
        hit = (not is_reject) and cls == intended
        c = (0, 200, 0) if hit else (0, 100, 255)
        h = image.shape[0]
        cv2.rectangle(image, (0, h - 40), (image.shape[1], h), (30, 30, 30), -1)
        txt = f"[{ROMAN.get(intended, intended)}]  logged {logged}"
        if font is not None:
            from PIL import Image, ImageDraw
            import numpy as np

            pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            ImageDraw.Draw(pil).text((12, h - 36), f"의도: {intended}    기록 {logged}줄",
                                     font=font, fill=(c[2], c[1], c[0]))
            image = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        else:
            cv2.putText(image, txt, (12, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)
    return image


def draw_landmarks(image, image_landmarks) -> None:
    import cv2

    if not image_landmarks:
        return
    h, w = image.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in image_landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(image, pts[a], pts[b], (200, 200, 200), 2)
    for i, p in enumerate(pts):
        # 정규화의 기준점(손목 0, 검지 MCP 5, 중지 MCP 9, 새끼 MCP 17)은 눈에 띄게
        key = i in (0, 5, 9, 17)
        cv2.circle(image, p, 6 if key else 4, (0, 165, 255) if key else (80, 220, 80), -1)


# --------------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="노트북 웹캠으로 학습된 수신호 분류기를 확인한다")
    parser.add_argument("--camera", type=int, default=0, help="카메라 인덱스 (기본 0)")
    parser.add_argument("--landmarker", default=str(SERVICE_ROOT / "models" / "hand_landmarker.task"))
    parser.add_argument("--no-download", action="store_true", help="MediaPipe 모델 자동 다운로드 끄기")
    parser.add_argument("--no-window", action="store_true", help="창 없이 콘솔로만 출력")
    parser.add_argument("--max-frames", type=int, default=0, help="N프레임 처리 후 자동 종료 (0=무제한)")
    parser.add_argument("--no-mirror", action="store_true", help="좌우 반전(거울 모드) 끄기")
    parser.add_argument("--list-cameras", action="store_true", help="열리는 카메라 인덱스만 확인하고 종료")
    parser.add_argument("--log", nargs="?", const="AUTO", default=None, metavar="PATH",
                        help="진단 로그(JSONL) 기록. 경로를 생략하면 logs/ 아래 자동 생성. "
                             "원본 랜드마크까지 남기므로 나중에 다른 특징 모드로 재계산 가능")
    parser.add_argument("--log-every", type=int, default=1,
                        help="N프레임마다 한 줄씩 기록 (기본 1 = 전부)")
    args = parser.parse_args()

    if args.list_cameras:
        list_cameras()
        return

    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

    from cognition import classify, model_store, smoothing, templates

    # 1) 모델 상태 출력 — 분류기가 없으면 판정은 계속 model_not_loaded로 나온다
    info = model_store.describe()
    if info["loaded"]:
        meta = info.get("metadata", {})
        print(f"분류기: {info['path']}")
        print(f"  클래스 {len(info['classes'])}종  {info['classes']}")
        print(f"  특징 모드 {info.get('feature_mode')}  |  학습 {meta.get('trained_on')} "
              f"{meta.get('trained_at')}  |  샘플 {meta.get('n_samples'):,}건"
              if meta.get("n_samples") else f"  특징 모드 {info.get('feature_mode')}")
        if meta.get("cv_accuracy") is not None:
            print(f"  공개 데이터 성적({meta.get('split')} 분할): 정답률 "
                  f"{meta['cv_accuracy'] * 100:.2f}%  MacroF1 {meta.get('cv_macro_f1')}  "
                  f"치명 오분류 {meta.get('cv_critical_errors')}건")
            print("  ※ 이 수치는 KPI가 아니다 — 촬영자 정보가 없는 공개 데이터 기준 (04 §4)")
    else:
        print(f"[주의] 분류기 모델이 없습니다: {info['path']}")
        print("       랜드마크는 그려지지만 판정은 계속 'model_not_loaded'입니다.")
        print("       `python training/train_svm.py` 로 학습하면 이 경로에 생깁니다.")
    print(f"판정 설정: tau={classify.effective_tau()}  N={smoothing.N_FRAMES}프레임")
    if not model_store.get_match_score_calibration() or not templates.available_signs():
        print("[참고] 템플릿 DB가 비어 있어 match_score는 0으로 나옵니다 "
              "(services/data의 seed_templates.py 담당: 김지훈). 판정 자체와는 무관합니다.")

    landmarker_path = ensure_landmarker(Path(args.landmarker), allow_download=not args.no_download)

    latest = LatestResult()

    def on_result(result, output_image, timestamp_ms: int) -> None:
        """LIVE_STREAM 콜백 — 운영(perception/capture.py)과 같은 형식으로 landmark_frame을 만든다."""
        world = getattr(result, "hand_world_landmarks", None) or []
        image_lms = getattr(result, "hand_landmarks", None) or []
        handedness_list = getattr(result, "handedness", None) or []

        hand_detected = len(world) > 0
        landmarks, handedness = [], "Right"
        if hand_detected:
            landmarks = [
                {"id": i, "x": float(lm.x), "y": float(lm.y), "z": float(lm.z)}
                for i, lm in enumerate(world[0])
            ]
            if handedness_list:
                first = handedness_list[0]
                category = first[0] if isinstance(first, (list, tuple)) else first
                handedness = getattr(category, "category_name", None) or "Right"

        latest.set(
            {
                "timestamp": int(timestamp_ms),
                "captured_at_ms": int(time.time() * 1000),
                "hand_detected": hand_detected,
                "handedness": handedness,
                "landmarks": landmarks,
            },
            image_lms[0] if image_lms else None,
        )

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(landmarker_path)),
        running_mode=RunningMode.LIVE_STREAM,       # 운영과 동일 (05_모델카드_v3 §3-2)
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        result_callback=on_result,
    )

    backend = cv2.CAP_DSHOW if sys.platform == "win32" else 0
    cap = cv2.VideoCapture(args.camera, backend)
    if not cap.isOpened():
        raise SystemExit(
            f"카메라 {args.camera}번을 열 수 없습니다. --list-cameras 로 인덱스를 확인하거나, "
            "다른 앱이 카메라를 점유 중인지 확인하세요."
        )

    font = _load_korean_font()
    if font is None and not args.no_window:
        print("[참고] 한글 폰트를 찾지 못해 클래스명을 영문으로 표시합니다 (pillow 설치 시 한글 표시).")

    # ---- 진단 로그 준비 ----
    log_file = None
    if args.log:
        path = (Path(args.log) if args.log != "AUTO"
                else SERVICE_ROOT / "logs" /
                f"webcam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        log_file = path.open("w", encoding="utf-8")
        # 첫 줄은 헤더 — 어떤 모델로 찍은 로그인지 남겨야 나중에 해석이 된다
        log_file.write(json.dumps({
            "record": "header",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "model": info,
            "tau": classify.effective_tau(),
            "n_frames": smoothing.N_FRAMES,
            "camera": args.camera,
            "mirror": not args.no_mirror,
        }, ensure_ascii=False, default=str) + "\n")
        print(f"진단 로그: {path}")
        print("  숫자키로 '지금 하려는 동작'을 찍어주세요 — 그래야 오판정을 셀 수 있습니다.")
        for k, v in LABEL_KEYS.items():
            print(f"    {k} = {v}")
        print("    ` = 라벨 해제")

    print("\n손을 카메라에 비춰보세요.  q/ESC=종료,  r=N프레임 누적 초기화\n")
    intended: Optional[str] = None
    logged = 0

    last_printed = None
    frame_count = 0
    fps, fps_t0, fps_n = 0.0, time.perf_counter(), 0
    last_ts_ms = 0

    try:
        with HandLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame_bgr = cap.read()
                if not ok:
                    print("카메라 프레임을 읽지 못했습니다.")
                    break
                if not args.no_mirror:
                    frame_bgr = cv2.flip(frame_bgr, 1)  # 거울처럼 보이게(사용자 편의)

                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                # LIVE_STREAM은 타임스탬프가 반드시 단조 증가해야 한다
                ts_ms = max(int(time.monotonic() * 1000), last_ts_ms + 1)
                last_ts_ms = ts_ms
                landmarker.detect_async(mp_image, ts_ms)

                # 운영 app.py의 _cognition_loop와 동일한 판정 흐름
                lm_frame, image_lms = latest.get()
                if lm_frame is not None:
                    result = classify.predict(lm_frame)
                    observed = None if result["is_reject"] else result["predicted_class"]
                    confirmed = smoothing.push_and_check(observed)
                    if not result["is_reject"] and not confirmed:
                        result["is_reject"] = True
                        result["reason"] = "awaiting_consecutive_frames"
                    result["consecutive"] = smoothing.streak()
                else:
                    result = {"predicted_class": "negative", "is_reject": True, "reason": "no_frame",
                              "confidence": 0.0, "match_score": 0, "latency_ms": 0, "consecutive": 0}

                # ---- 로그 기록 ----
                # 원본 랜드마크를 그대로 남긴다. 예측값만 남기면 "다른 특징 모드였다면
                # 어땠을까"를 나중에 확인할 수 없다.
                if log_file is not None and frame_count % max(1, args.log_every) == 0:
                    rec = {
                        "record": "frame",
                        "t": round(time.time(), 3),
                        "intended": intended,
                        "predicted": result.get("predicted_class"),
                        "confidence": result.get("confidence"),
                        "match_score": result.get("match_score"),
                        "is_reject": result.get("is_reject"),
                        "reason": result.get("reason"),
                        "consecutive": result.get("consecutive"),
                        "hand_detected": bool(lm_frame and lm_frame.get("hand_detected")),
                    }
                    if lm_frame and lm_frame.get("hand_detected"):
                        rec["handedness"] = lm_frame.get("handedness")
                        rec["landmarks"] = [
                            {"id": p["id"], "x": round(p["x"], 6),
                             "y": round(p["y"], 6), "z": round(p["z"], 6)}
                            for p in lm_frame["landmarks"]
                        ]
                    log_file.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    logged += 1

                fps_n += 1
                if fps_n >= 10:
                    now = time.perf_counter()
                    fps = fps_n / (now - fps_t0)
                    fps_t0, fps_n = now, 0

                if args.no_window:
                    key = (result["predicted_class"], result["is_reject"], result.get("reason"))
                    if key != last_printed:
                        print(
                            f"  {result['predicted_class']:<12} conf={result['confidence']:.2f} "
                            f"match={result['match_score']:3d} "
                            f"{'CONFIRMED' if not result['is_reject'] else 'reject:' + str(result.get('reason'))}"
                        )
                        last_printed = key
                else:
                    draw_landmarks(frame_bgr, image_lms)
                    frame_bgr = draw_overlay(frame_bgr, result, fps, smoothing.N_FRAMES, font,
                                             intended, logged)
                    cv2.imshow("SafeSign webcam check (q=quit, r=reset)", frame_bgr)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        break
                    if key == ord("r"):
                        smoothing.reset()
                        print("  N프레임 누적 초기화")
                    pressed = chr(key) if 32 <= key < 127 else ""
                    if pressed in LABEL_KEYS:
                        intended = LABEL_KEYS[pressed]
                        smoothing.reset()   # 동작을 바꿨으니 N프레임 누적도 새로
                        print(f"  의도 = {intended}")
                    elif pressed == "`":
                        intended = None
                        print("  의도 해제")

                frame_count += 1
                if args.max_frames and frame_count >= args.max_frames:
                    break
    finally:
        cap.release()
        if not args.no_window:
            cv2.destroyAllWindows()
        if log_file is not None:
            log_file.close()

    print(f"\n종료 ({frame_count} 프레임 처리)")
    if args.log:
        print(f"로그 {logged}줄 기록됨 -> {path}")
        print(f"분석: python scripts/analyze_log.py {path}")


if __name__ == "__main__":
    main()
