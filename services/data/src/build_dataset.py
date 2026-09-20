"""수집한 사진 -> 랜드마크 JSON 변환 (학습 데이터 생성).

담당: 김지훈
근거/사용법: services/data/README.md · document/04_데이터셋명세서_v2.md

이 스크립트가 하는 일:
    클래스별 사진 폴더  ->  MediaPipe로 손 관절 21개 좌표 추출
                        ->  services/vision 학습 노트북이 읽는 JSON 형식으로 저장

우리 AI(SVM)는 사진이 아니라 좌표만 본다. 그래서 사진에서 손을 찾지 못하면 그 장은 학습에
쓸 수 없고, "원본 장수"와 "실제 확보 장수"가 달라진다. 이 스크립트는 그 차이를 표로 보고한다.

입력 폴더 구조 (폴더 이름은 아래 FOLDER_TO_CLASS의 키 중 하나):
    <src>/정지/*.jpg   <src>/서행/*.jpg   ...

출력 (04_데이터셋명세서_v2 §6 · make_dummy_dataset.py와 동일 형식):
    <out>/{class_name}/{subject_id}_{index}.json
    {"class_name":..., "subject_id":..., "handedness":"Left|Right",
     "landmarks":[{"id":0,"x":..,"y":..,"z":..}, ... 21개], "source":{...}}
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# 05_모델카드_v3 §1에 기재된 공식 모델 번들 (Apache License 2.0)
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models" / "hand_landmarker.task"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "datasets" / "processed"

# 04_데이터셋명세서_v2 §1 확정 클래스명 (학습 노트북이 이 이름만 인식한다)
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

# 수집 폴더 이름 -> 확정 클래스명. 약칭으로 모아둔 폴더도 그대로 받아준다.
FOLDER_TO_CLASS = {
    "정지": "정지",
    "서행": "서행",
    "좌회전": "좌회전_유도",
    "좌회전_유도": "좌회전_유도",
    "우회전": "우회전_유도",
    "우회전_유도": "우회전_유도",
    "확인": "확인_완료",
    "확인_완료": "확인_완료",
    "후진": "후진",
    "주의": "주의",
    "nothing": "negative",
    "negative": "negative",
}

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MIN_PER_CLASS = 300  # 04_데이터셋명세서_v2 §2 클래스당 목표


def ensure_model(path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"모델 파일이 없어 내려받습니다 (약 7.8MB): {MODEL_URL}")
    urllib.request.urlretrieve(MODEL_URL, path)
    print(f"저장 완료: {path}")
    return path


def imread_unicode(path: Path):
    """한글이 포함된 경로에서도 이미지를 읽는다 (cv2.imread는 Windows에서 실패)."""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def extract(landmarker, path: Path):
    """사진 1장 -> (handedness, landmarks 21개). 손을 못 찾으면 None."""
    bgr = imread_unicode(path)
    if bgr is None:
        return None
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

    # 05_모델카드_v3 §3-4: 카메라 거리 변화에 강한 world landmarks 채택
    if not result.hand_world_landmarks:
        return None
    world = result.hand_world_landmarks[0]
    if len(world) != 21:
        return None

    handedness = "Right"
    if result.handedness and result.handedness[0]:
        handedness = result.handedness[0][0].category_name

    # world landmarks는 미터 단위(손 전체가 약 0.1m)라 소수점 6자리면 1마이크로미터 정밀도다.
    # 원본 부동소수점을 그대로 쓰면 파일만 2배가 되고 그만한 정밀도는 쓰이지 않는다.
    landmarks = [
        {"id": i, "x": round(float(p.x), 6), "y": round(float(p.y), 6), "z": round(float(p.z), 6)}
        for i, p in enumerate(world)
    ]
    return handedness, landmarks


def collect_folders(src: Path) -> dict[str, list[Path]]:
    """<src> 아래 클래스 폴더를 찾아 {확정클래스명: [폴더, ...]}로 모은다."""
    found: dict[str, list[Path]] = {}
    for d in sorted(p for p in src.iterdir() if p.is_dir()):
        cls = FOLDER_TO_CLASS.get(d.name)
        if cls is None:
            print(f"  [건너뜀] 알 수 없는 폴더: {d.name}")
            continue
        found.setdefault(cls, []).append(d)
    return found


def images_in(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXT)


def main() -> None:
    ap = argparse.ArgumentParser(description="사진 -> 랜드마크 JSON 변환")
    ap.add_argument("--src", required=True, help="클래스별 사진 폴더가 들어 있는 상위 폴더")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"출력 폴더 (기본: {DEFAULT_OUT})")
    ap.add_argument("--subject-id", default="public",
                    help="촬영자 ID로 기록할 값. 공개 데이터셋은 촬영자 정보가 없어 하나로 통일된다")
    ap.add_argument("--model", default=str(DEFAULT_MODEL), help="hand_landmarker.task 경로")
    ap.add_argument("--per-class", type=int, default=0,
                    help="클래스당 최대 변환 장수 (0=전부). 클래스 간 장수 균형을 맞출 때 사용")
    ap.add_argument("--probe", type=int, default=0,
                    help="사전 점검: 클래스당 N장만 처리해 검출률만 보고 (파일 저장 안 함)")
    ap.add_argument("--clean", action="store_true",
                    help="변환 전에 출력 폴더의 기존 클래스 폴더를 비운다 (이전 결과와 섞이지 않게)")
    ap.add_argument("--classes", nargs="+", metavar="클래스",
                    help=f"이 클래스만 변환 (기본: 전부). 선택 가능: {' '.join(SIGN_CLASSES)}")
    args = ap.parse_args()

    targets = SIGN_CLASSES
    if args.classes:
        unknown = [c for c in args.classes if c not in SIGN_CLASSES]
        if unknown:
            sys.exit(f"[오류] 알 수 없는 클래스: {', '.join(unknown)}\n"
                     f"       선택 가능: {', '.join(SIGN_CLASSES)}")
        targets = [c for c in SIGN_CLASSES if c in args.classes]

    src = Path(args.src)
    if not src.is_dir():
        sys.exit(f"[오류] --src 경로가 없습니다: {src}")

    print(f"입력: {src}")
    folders = collect_folders(src)
    if not folders:
        sys.exit("[오류] 클래스 폴더를 찾지 못했습니다. 폴더 이름을 확인하세요 "
                 f"(인식 가능: {', '.join(FOLDER_TO_CLASS)})")

    probe = args.probe > 0
    limit = args.probe if probe else args.per_class
    out_root = Path(args.out)
    print(f"출력: {'(사전 점검 모드 - 저장 안 함)' if probe else out_root}")
    print(f"클래스 {len(folders)}개 인식 · 변환 대상 {len(targets)}개: {', '.join(targets)}\n")

    landmarker_opts = vision.HandLandmarkerOptions(
        # 경로가 아니라 바이트로 넘긴다 - MediaPipe 네이티브 코드는 한글이 들어간 경로를
        # 열지 못한다 (Windows 사용자명이 한글이면 반드시 이 방식이어야 한다).
        base_options=mp_python.BaseOptions(model_asset_buffer=ensure_model(Path(args.model)).read_bytes()),
        running_mode=vision.RunningMode.IMAGE,
        num_hands=1,  # 05_모델카드_v3 §3-3: 학습자 1명의 손 1개만
        min_hand_detection_confidence=0.3,
        min_hand_presence_confidence=0.3,
        min_tracking_confidence=0.3,
    )

    stats: dict[str, tuple[int, int]] = {}
    started = time.time()

    with vision.HandLandmarker.create_from_options(landmarker_opts) as landmarker:
        for cls in targets:
            if cls not in folders:
                continue
            files: list[Path] = []
            for d in folders[cls]:
                files += images_in(d)
            if limit and len(files) > limit:
                # 앞쪽만 쓰면 한 출처에 치우칠 수 있어 고르게 솎아낸다
                files = files[:: max(1, len(files) // limit)][:limit]

            class_dir = out_root / cls
            if not probe:
                if args.clean and class_dir.exists():
                    shutil.rmtree(class_dir)
                class_dir.mkdir(parents=True, exist_ok=True)

            ok = 0
            for i, path in enumerate(files):
                got = extract(landmarker, path)
                if got is None:
                    continue
                if not probe:
                    handedness, landmarks = got
                    doc = {
                        "class_name": cls,
                        "subject_id": args.subject_id,
                        "handedness": handedness,
                        "landmarks": landmarks,
                        "source": {"folder": path.parent.name, "file": path.name},
                    }
                    out_path = class_dir / f"{args.subject_id}_{ok:05d}.json"
                    out_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
                ok += 1
                if not probe and (i + 1) % 500 == 0:
                    print(f"    {cls}: {i + 1}/{len(files)}장 처리 중...")

            stats[cls] = (ok, len(files))
            rate = ok / len(files) * 100 if files else 0.0
            print(f"  {cls:<10} {ok:>6}/{len(files):<6}장  검출률 {rate:5.1f}%")

    elapsed = time.time() - started
    total_ok = sum(v[0] for v in stats.values())
    total_try = sum(v[1] for v in stats.values())
    print("\n" + "=" * 58)
    print(f"전체 {total_ok}/{total_try}장 "
          f"({total_ok / total_try * 100 if total_try else 0:.1f}%) · 소요 {elapsed / 60:.1f}분")

    if probe:
        print("\n[사전 점검 모드] 파일을 저장하지 않았습니다.")
        print("검출률이 30% 이상이면 --probe 없이 다시 실행해 전체 변환을 진행하세요.")
        return

    print(f"\n클래스별 확보 장수 (04_데이터셋명세서_v2 §2 기준 {MIN_PER_CLASS}장 이상 필요):")
    shortage = []
    for cls in targets:
        if cls not in stats:
            print(f"  [없음] {cls}: 폴더가 없습니다")
            shortage.append(cls)
            continue
        n = stats[cls][0]
        print(f"  [{'OK ' if n >= MIN_PER_CLASS else '부족'}] {cls}: {n}장")
        if n < MIN_PER_CLASS:
            shortage.append(cls)
    if shortage:
        print(f"\n[경고] {MIN_PER_CLASS}장 미달: {', '.join(shortage)}")
        print("       자체 촬영으로 보충하거나 데이터 출처를 재검토하세요.")
    print(f"\n출력 위치: {out_root}")


if __name__ == "__main__":
    main()
