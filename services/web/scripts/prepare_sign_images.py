"""수신호 예시 사진 7장을 웹 화면 규격에 맞게 변환한다.

담당: 김지훈
근거: document/proposals/web_판정_타이밍_스펙.md §4.3

하는 일 (사진 1장당):
    1) 세로로 찍힌 사진 바로 세우기 (휴대폰 EXIF 회전 정보 반영)
    2) 짧은 변을 800px로 축소 (이미 800px 이하면 그대로 둔다 - 늘리면 흐려진다)
    3) 200KB 이하가 될 때까지 JPEG 품질을 낮춰가며 저장
    4) 규격 파일명(stop.jpg 등)으로 services/web/frontend/images/ 에 저장

사용법:
    python services/web/scripts/prepare_sign_images.py --src <사진이_들어있는_폴더>

    사진 파일 이름에 클래스 키워드가 들어 있으면 자동으로 알아본다.
    예) "정지.jpg", "stop_1.jpg", "IMG_정지.jpeg" -> stop.jpg
    못 알아보면 해당 파일은 건너뛰고 목록으로 알려준다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps

SHORT_SIDE = 800       # 스펙 §4.3: 짧은 변 약 800px
MAX_BYTES = 200 * 1024 # 스펙 §4.3: 장당 200KB 이하
QUALITIES = [92, 88, 84, 80, 75, 70, 65, 60]

REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO / "services" / "web" / "frontend" / "images"

# 출력 파일명 -> (한글 클래스명, 파일 이름에서 찾아볼 키워드들)
# 스펙 §4.3의 7개 파일명. negative는 예시 사진이 필요 없다.
TARGETS: list[tuple[str, str, tuple[str, ...]]] = [
    ("stop.jpg",       "정지",      ("정지", "stop")),
    ("slow.jpg",       "서행",      ("서행", "slow")),
    ("turn_left.jpg",  "좌회전_유도", ("좌회전", "turn_left", "turnleft", "left")),
    ("turn_right.jpg", "우회전_유도", ("우회전", "turn_right", "turnright", "right")),
    ("complete.jpg",   "확인_완료",  ("확인", "완료", "complete", "ok")),
    ("reverse.jpg",    "후진",      ("후진", "reverse", "back")),
    ("caution.jpg",    "주의",      ("주의", "caution", "warn")),
]

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic"}


def match_target(stem: str) -> str | None:
    """파일 이름에서 클래스를 알아낸다. 애매하면 None.

    'turn_left'가 'left'보다 먼저 걸리도록 키워드가 긴 순서로 본다.
    (안 그러면 turn_left.jpg가 left 규칙에도 걸려 판단이 뒤집힐 수 있다)
    """
    low = stem.lower()
    hits = [
        (len(kw), out)
        for out, _, kws in TARGETS
        for kw in kws
        if kw in low
    ]
    if not hits:
        return None
    hits.sort(reverse=True)
    return hits[0][1]


def convert(src: Path, dst: Path) -> tuple[int, tuple[int, int], int]:
    """사진 1장을 규격에 맞춰 저장한다. -> (바이트수, (가로,세로), 품질)"""
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)   # 휴대폰으로 세로로 찍은 사진 바로 세우기
    img = img.convert("RGB")             # PNG 투명도/회색조를 JPEG가 읽는 형식으로

    w, h = img.size
    short = min(w, h)
    if short > SHORT_SIDE:
        scale = SHORT_SIDE / short
        img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

    dst.parent.mkdir(parents=True, exist_ok=True)
    for q in QUALITIES:
        img.save(dst, "JPEG", quality=q, optimize=True, progressive=True)
        if dst.stat().st_size <= MAX_BYTES:
            return dst.stat().st_size, img.size, q
    # 마지막 품질로도 넘치면 그대로 두고 호출한 쪽에서 경고한다
    return dst.stat().st_size, img.size, QUALITIES[-1]


def main() -> None:
    ap = argparse.ArgumentParser(description="수신호 예시 사진 7장 규격 변환")
    ap.add_argument("--src", required=True, help="촬영한 사진이 들어 있는 폴더")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"저장 폴더 (기본: {DEFAULT_OUT})")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.is_dir():
        sys.exit(f"[오류] --src 폴더가 없습니다: {src}")
    out = Path(args.out)

    files = sorted(p for p in src.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)
    if not files:
        sys.exit(f"[오류] {src} 안에 사진이 없습니다 (확장자: {', '.join(sorted(IMAGE_EXT))})")

    print(f"입력: {src}  (사진 {len(files)}장)")
    print(f"출력: {out}\n")

    picked: dict[str, Path] = {}
    unmatched: list[Path] = []
    for f in files:
        name = match_target(f.stem)
        if name is None:
            unmatched.append(f)
        elif name in picked:
            print(f"  [중복] {name} 에 해당하는 사진이 둘 이상입니다. "
                  f"먼저 찾은 '{picked[name].name}' 을 씁니다 (무시: {f.name})")
        else:
            picked[name] = f

    oversize = []
    for name, korean, _ in TARGETS:
        if name not in picked:
            print(f"  [없음] {name:<14} {korean}")
            continue
        size, dims, q = convert(picked[name], out / name)
        kb = size / 1024
        flag = "OK  " if size <= MAX_BYTES else "초과"
        print(f"  [{flag}] {name:<14} {korean:<7} {dims[0]}x{dims[1]}  {kb:5.0f}KB  (품질 {q})"
              f"   <- {picked[name].name}")
        if size > MAX_BYTES:
            oversize.append(name)

    print("\n" + "=" * 62)
    print(f"완료 {len(picked)}/{len(TARGETS)}장")

    missing = [k for k, _, _ in TARGETS if k not in picked]
    if missing:
        print(f"\n[부족] 아직 없는 사진: {', '.join(missing)}")
        print("       파일 이름에 클래스 키워드(정지/서행/좌회전/우회전/확인/후진/주의)를 넣어 주세요.")
    if unmatched:
        print(f"\n[이름을 못 알아봄] {len(unmatched)}장 - 파일 이름을 바꾼 뒤 다시 실행하세요:")
        for f in unmatched:
            print(f"       {f.name}")
    if oversize:
        print(f"\n[경고] 품질을 최저({QUALITIES[-1]})로 낮춰도 200KB를 넘습니다: {', '.join(oversize)}")
        print("       배경이 복잡하면 용량이 커집니다. 단색 벽 앞에서 다시 찍어 주세요.")
    if not missing and not oversize:
        print("\n7장 모두 규격을 만족합니다. 이대로 커밋하면 됩니다.")


if __name__ == "__main__":
    main()
