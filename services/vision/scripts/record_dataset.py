"""자체 촬영 도구 — KPI 측정용 평가 데이터를 노트북 웹캠으로 모은다.

담당: 이동혁 (vision)

**왜 필요한가.** 지금 학습 데이터 27,735건은 전부 공개 데이터셋이고 촬영자 정보가 없어
`subject_id`가 전부 `"public"` 하나다. 인물 단위로 나눌 수 없으니 거기서 나온 점수는
"처음 보는 사람에게도 통한다"는 증거가 못 된다(04_데이터셋명세서_v2 §4).
**01_프로젝트계획서_v4의 KPI 5개 항목은 이 스크립트로 모은 데이터로만 측정할 수 있다.**

**이건 학습 데이터가 아니라 시험 데이터다.** 학습은 공개 데이터로 하고, 여기서 모은 것은
손대지 않은 채 최종 KPI 측정에만 쓴다. 그래서 분량이 적어도 된다(외부인 1~2명 × 7종 × 10회).

    python scripts/record_dataset.py --subject-id ext01

  촬영자마다 `--subject-id`를 다르게 준다. **팀원이 아닌 외부인**이어야 의미가 있다 —
  팀원으로 찍으면 "아는 사람의 손"을 외우는 같은 문제가 반복된다(08_리스크레지스터).

**방향 변형을 함께 찍는다.** 2026-09-21 회의 안건 3 A안(손 방향 축 도입)이 실제로 효과가
있는지는 자체 촬영 데이터로만 판단할 수 있다. 그래서 테이크마다 손 방향을 바꿔가며 찍고
(`정면 / 좌기울임 / 우기울임`), 나중에 `train_svm.py --with-orientation`으로 A/B 비교한다.
방향이 필요 없으면 `--orientations 정면`.

**카메라는 노트북 웹캠이 기본이고, RPi5의 Camera Module 3(CSI)로도 찍을 수 있다.**

    python scripts/record_dataset.py --subject-id ext01                # 노트북/USB 웹캠 (기본)
    python scripts/record_dataset.py --subject-id ext01 --source csi   # RPi5 + Camera Module 3
    python scripts/record_dataset.py --list-cameras                    # 뭐가 잡히는지 확인

  CSI는 libcamera 스택이라 `cv2.VideoCapture`로 못 읽는다 — `camera_source.py`가 picamera2로
  받아 준다(RPi5 준비 절차도 그 파일 참고). 어느 쪽으로 찍었는지는 저장 파일의
  `source.device`에 남으므로 나중에 카메라별로 갈라 볼 수 있다.
  **조작이 키 입력이라 창이 필요하다** — Pi에서는 데스크톱에서 직접 실행할 것(SSH면 VNC/`ssh -X`).

조작:
    SPACE  이번 테이크 촬영 (카운트다운 후 연속 캡처)
    U      직전 테이크 취소(파일 삭제)
    N      이 클래스 건너뛰기
    Q/ESC  종료 (지금까지 찍은 것은 남는다)

출력: `services/data/datasets/self_recorded/{클래스}/*.json`
      형식은 공개 데이터(04_데이터셋명세서_v2 §6)와 동일해서 `train_svm.py --data`로 바로 읽힌다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from cognition.normalize import NormalizationError, to_feature_vector  # noqa: E402

# 노트북 웹캠(OpenCV)과 RPi5 Camera Module 3(picamera2)을 같은 얼굴로 감싼 캡처 계층
from camera_source import (  # noqa: E402
    add_camera_args,
    has_display,
    list_cameras,
    open_camera,
)

# 02_설계문서_v2 §4 확정 7종 + 손가락 패턴(엄지·검지·중지·약지·소지, ● 폄 / ○ 접음).
# 외부인은 수신호를 모르므로 화면에 이 패턴을 같이 띄워 준다.
SIGN_SHAPES = [
    ("정지", "●●●●●", "다섯 손가락 모두 펴기"),
    ("서행", "○●●○○", "검지 + 중지 펴기"),
    ("좌회전_유도", "●●○○○", "엄지 + 검지 펴기"),
    ("우회전_유도", "●○○○●", "엄지 + 소지 펴기"),
    ("확인_완료", "○○○○○", "다섯 손가락 모두 접기 (주먹)"),
    ("후진", "○●○○○", "검지만 펴기"),
    ("주의", "○○○○●", "소지만 펴기"),
]
ORIENTATION_HINT = {
    "정면": "손바닥을 카메라에 정면으로",
    "좌기울임": "손목을 왼쪽으로 30도쯤 기울여서",
    "우기울임": "손목을 오른쪽으로 30도쯤 기울여서",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_sample(out_dir: Path, class_name: str, subject_id: str, frame: dict,
                take: int, seq: int, orientation: str, device: str = "laptop_webcam") -> Path:
    """공개 데이터와 같은 형식으로 1건 저장 (04_데이터셋명세서_v2 §6)."""
    folder = out_dir / class_name
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{subject_id}_{class_name}_t{take:02d}_f{seq}"
    path = folder / f"{stem}.json"
    path.write_text(
        json.dumps(
            {
                "class_name": class_name,
                "subject_id": subject_id,
                "handedness": frame["handedness"],
                "landmarks": frame["landmarks"],
                "source": {
                    "folder": class_name,
                    "file": stem,
                    "recorded_at": _now_iso(),
                    "orientation": orientation,   # 안건 3 A안 A/B용
                    "take": take,                 # 같은 테이크 = 한 번의 "시도"
                    "device": device,             # laptop_webcam / rpi5_csi_module3
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def draw_prompt(image, class_name: str, shape: str, hint: str, orientation: str,
                take: int, takes: int, saved: int, state: str, font) -> "any":
    """지금 뭘 해야 하는지를 화면 위에 크게 띄운다 (외부인이 보고 따라할 수 있게)."""
    import cv2

    h, w = image.shape[:2]
    cv2.rectangle(image, (0, 0), (w, 118), (30, 30, 30), -1)
    cv2.rectangle(image, (0, h - 34), (w, h), (30, 30, 30), -1)

    color = {"대기": (200, 200, 200), "준비": (0, 200, 255), "촬영": (0, 220, 0)}.get(
        state, (200, 200, 200)
    )
    line1 = f"{class_name}   {shape}"
    line2 = f"{hint}  /  {ORIENTATION_HINT.get(orientation, orientation)}"
    line3 = f"테이크 {take}/{takes}   저장 {saved}건   [{state}]"
    footer = "SPACE 촬영   U 직전 취소   N 클래스 건너뛰기   Q 종료"

    if font is not None:
        from PIL import Image, ImageDraw
        import numpy as np

        pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        rgb = (color[2], color[1], color[0])
        draw.text((12, 4), line1, font=font, fill=rgb)
        draw.text((12, 44), line2, font=font, fill=(210, 210, 210))
        draw.text((12, 80), line3, font=font, fill=(210, 210, 210))
        draw.text((12, h - 30), footer, font=font, fill=(150, 150, 150))
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    cv2.putText(image, shape, (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 2)
    cv2.putText(image, line3, (12, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (210, 210, 210), 1)
    cv2.putText(image, footer, (12, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    return image


def main() -> int:
    ap = argparse.ArgumentParser(description="자체 촬영: KPI 측정용 평가 데이터 수집")
    # --list-cameras 만 볼 때는 촬영자 ID가 필요 없으므로 required 대신 아래에서 직접 확인한다
    ap.add_argument("--subject-id",
                    help="촬영자 식별자. 사람마다 다르게 (예: ext01). 실명 대신 익명 ID 권장")
    ap.add_argument("--out", type=Path,
                    default=SERVICE_ROOT.parent / "data" / "datasets" / "self_recorded")
    ap.add_argument("--takes", type=int, default=10, help="클래스당 시도 횟수 (기본 10)")
    ap.add_argument("--burst", type=int, default=3, help="한 테이크에서 저장할 프레임 수 (기본 3)")
    ap.add_argument("--countdown", type=float, default=2.0, help="촬영 전 준비 시간(초)")
    ap.add_argument("--orientations", default="정면,좌기울임,우기울임",
                    help="테이크마다 돌아가며 요청할 손 방향. 쉼표 구분. 안 쓰려면 '정면'")
    ap.add_argument("--classes", default="", help="쉼표로 지정하면 그 클래스만 촬영")
    ap.add_argument("--landmarker", default=str(SERVICE_ROOT / "models" / "hand_landmarker.task"))
    ap.add_argument("--no-mirror", action="store_true")
    add_camera_args(ap, default_source="usb")   # --source/--camera/--size/--fps/--list-cameras 등
    args = ap.parse_args()

    if args.list_cameras:
        list_cameras()
        return 0
    if not args.subject_id:
        ap.error("--subject-id 는 필수입니다 (예: --subject-id ext01)")

    if not has_display():
        # 이 도구는 SPACE/U/N 키로 조작하므로 창이 없으면 아예 쓸 수 없다.
        raise SystemExit(
            "창을 띄울 수 없는 환경입니다(DISPLAY 없음). 이 도구는 키 조작이 필요합니다.\n"
            "  Pi 데스크톱에서 직접 실행하거나 VNC / `ssh -X` 로 접속해서 실행하세요."
        )

    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

    # webcam_check와 같은 준비 루틴을 재사용한다(모델 자동 다운로드, 한글 폰트)
    from webcam_check import LatestResult, _load_korean_font, ensure_landmarker

    orientations = [o.strip() for o in args.orientations.split(",") if o.strip()]
    shapes = SIGN_SHAPES
    if args.classes:
        want = {c.strip() for c in args.classes.split(",") if c.strip()}
        shapes = [s for s in SIGN_SHAPES if s[0] in want]
        missing = want - {s[0] for s in shapes}
        if missing:
            raise SystemExit(f"모르는 클래스: {sorted(missing)}")

    total_planned = len(shapes) * args.takes * args.burst
    print("=" * 70)
    print(f"자체 촬영  |  촬영자 {args.subject_id}  |  저장 위치 {args.out}")
    print("=" * 70)
    print(f"  클래스 {len(shapes)}종 × 테이크 {args.takes}회 × {args.burst}프레임 = 최대 {total_planned}건")
    print(f"  손 방향: {' / '.join(orientations)}")
    print(f"\n  ※ 이 데이터는 **학습에 쓰지 않는다.** KPI 측정 전용이다.")
    print(f"  ※ subject_id '{args.subject_id}' 는 팀원이 아닌 사람이어야 의미가 있다.\n")

    existing = sorted(args.out.glob(f"*/{args.subject_id}_*.json"))
    if existing:
        print(f"  [주의] 같은 subject_id로 이미 {len(existing)}건이 있습니다. 덮어쓸 수 있습니다.")
        print(f"         이어서 찍으려면 --takes 를 조정하거나 --classes 로 남은 것만 지정하세요.\n")

    landmarker_path = ensure_landmarker(Path(args.landmarker))
    latest = LatestResult()

    def on_result(result, output_image, timestamp_ms: int) -> None:
        world = getattr(result, "hand_world_landmarks", None) or []
        image_lms = getattr(result, "hand_landmarks", None) or []
        handedness_list = getattr(result, "handedness", None) or []
        detected = len(world) > 0
        landmarks, handedness = [], "Right"
        if detected:
            landmarks = [
                {"id": i, "x": float(lm.x), "y": float(lm.y), "z": float(lm.z)}
                for i, lm in enumerate(world[0])
            ]
            if handedness_list:
                first = handedness_list[0]
                cat = first[0] if isinstance(first, (list, tuple)) else first
                handedness = getattr(cat, "category_name", None) or "Right"
        latest.set(
            {"timestamp": int(timestamp_ms), "captured_at_ms": int(time.time() * 1000),
             "hand_detected": detected, "handedness": handedness, "landmarks": landmarks},
            image_lms[0] if image_lms else None,
        )

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(landmarker_path)),
        running_mode=RunningMode.LIVE_STREAM,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        result_callback=on_result,
    )

    camera = open_camera(args)          # CSI(picamera2) / USB(OpenCV) — read()는 둘 다 BGR
    print(f"  카메라: {camera.description}  (source.device = {camera.device_tag})\n")

    font = _load_korean_font(28)
    saved_total = 0
    per_class: dict[str, int] = {}
    last_take_files: list[Path] = []

    # 상태 머신: 대기 -> (SPACE) -> 준비(카운트다운) -> 촬영(burst) -> 대기
    cls_idx, take = 0, 1
    state, state_until, burst_left, burst_seq = "대기", 0.0, 0, 0
    last_ts_ms = 0
    quit_all = False

    try:
        with HandLandmarker.create_from_options(options) as landmarker:
            while not quit_all and cls_idx < len(shapes):
                class_name, shape, hint = shapes[cls_idx]
                orientation = orientations[(take - 1) % len(orientations)]

                frame_bgr = camera.read()
                if frame_bgr is None:
                    print("카메라 프레임을 읽지 못했습니다.")
                    break
                if not args.no_mirror:
                    frame_bgr = cv2.flip(frame_bgr, 1)

                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                ts_ms = max(int(time.monotonic() * 1000), last_ts_ms + 1)
                last_ts_ms = ts_ms
                landmarker.detect_async(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts_ms
                )
                lm_frame, image_lms = latest.get()

                now = time.monotonic()
                if state == "준비" and now >= state_until:
                    state, burst_left, burst_seq = "촬영", args.burst, 0
                    last_take_files = []

                if state == "촬영":
                    # 손이 잡히고 정규화까지 통과하는 프레임만 저장한다
                    usable = lm_frame is not None and lm_frame["hand_detected"]
                    if usable:
                        try:
                            to_feature_vector(lm_frame["landmarks"], lm_frame["handedness"])
                        except NormalizationError:
                            usable = False
                    if usable:
                        burst_seq += 1
                        p = save_sample(args.out, class_name, args.subject_id, lm_frame,
                                        take, burst_seq, orientation, camera.device_tag)
                        last_take_files.append(p)
                        saved_total += 1
                        per_class[class_name] = per_class.get(class_name, 0) + 1
                        burst_left -= 1
                        time.sleep(0.12)   # 같은 프레임을 연속 저장하지 않도록 약간 벌린다
                    if burst_left <= 0:
                        print(f"  [{class_name}] 테이크 {take}/{args.takes} ({orientation}) "
                              f"{len(last_take_files)}건 저장  (누적 {saved_total})")
                        state = "대기"
                        take += 1
                        if take > args.takes:
                            cls_idx, take = cls_idx + 1, 1

                # 손 미검출이면 그 사실을 화면에 알린다(빈손으로 카운트다운 넘기지 않게)
                shown = state
                if lm_frame is None or not lm_frame["hand_detected"]:
                    shown = "손 없음"
                elif state == "준비":
                    shown = f"준비 {max(0.0, state_until - now):.1f}s"

                from webcam_check import draw_landmarks
                draw_landmarks(frame_bgr, image_lms)
                frame_bgr = draw_prompt(frame_bgr, class_name, shape, hint, orientation,
                                        take, args.takes, per_class.get(class_name, 0),
                                        shown, font)
                cv2.imshow("SafeSign 자체 촬영 (SPACE=촬영, Q=종료)", frame_bgr)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    quit_all = True
                elif key == ord(" ") and state == "대기":
                    state, state_until = "준비", now + args.countdown
                elif key == ord("n"):
                    print(f"  [{class_name}] 건너뜀")
                    cls_idx, take, state = cls_idx + 1, 1, "대기"
                elif key == ord("u") and state == "대기" and last_take_files:
                    for p in last_take_files:
                        p.unlink(missing_ok=True)
                    saved_total -= len(last_take_files)
                    per_class[class_name] = max(0, per_class.get(class_name, 0)
                                                - len(last_take_files))
                    print(f"  직전 테이크 {len(last_take_files)}건 취소")
                    last_take_files = []
                    take = max(1, take - 1)
    finally:
        camera.close()
        cv2.destroyAllWindows()

    print("\n" + "=" * 70)
    print(f"촬영 종료 — 총 {saved_total}건")
    for name, _, _ in SIGN_SHAPES:
        if name in per_class:
            print(f"    {name:<12}{per_class[name]:>5}건")
    if saved_total:
        print(f"\n저장 위치: {args.out}")
        print("\n다음 단계:")
        print(f"  1) 형식 확인   python training/train_svm.py --data {args.out} --dry-run")
        print("  2) KPI 측정    (촬영자 2명 이상 모인 뒤) --split subject 로 평가")
        print("  3) 방향 축 A/B  train_svm.py --with-orientation 과 비교 (회의 안건 3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
