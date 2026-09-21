"""교육 상태머신 (09_화면목록_v2.md SC-01~SC-07 대응).

담당: 조은수 (웹 R, 성능측정 R)

세션별 현재 state는 메모리 딕셔너리(`_session`)로 관리한다 — SC-07은 세션 이어하기가 없어(재접속 시
항상 "처음부터", 2026-09-18 결정) DB/Redis 같은 영속 저장소가 필요 없다. 다중 학습자 동시 세션도
범위 밖이라(1대 1 교육 스테이션) 세션 ID 없이 프로세스 전역 상태 하나로 충분하다.

백그라운드 스레드(`start_polling`)가 vision의 GET /latest를 폴링해 judgment_result를 받고,
현재 커리큘럼 단계(target_signal)와 비교해 SC-03a(정답)/SC-03b(오답)로 분기한다. 정답이 확정되면:
- actuation(RPi5, ACTUATION_URL)의 POST /command(AI Hand) · /result · /progress(micro:bit) 호출
- **picar(RPi4B 8GB, PICAR_URL)의 POST /picar를 별도로 직접 호출** — actuation을 거치지 않는다.
  picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에 컴퓨트 보드를 분리했다
  (02_설계문서_v2 §1-1, 2026-09-18). httpx 요청에 timeout=PICAR_TIMEOUT_MS(기본 500ms)를 걸고,
  1회 재시도 후 실패하면 picar 없이 진행한다(03_인터페이스계약서_v2 §5-2·§7 — 예외를 삼키고 계속 진행).
  actuation 호출도 같은 정책(실패해도 학습 흐름은 막지 않음, best-effort 물리 피드백)으로 감싼다.

관리자/등록 관련 상태 없음 — 수신호 등록 기능은 범위에서 제외됨 (03_인터페이스계약서_v2 §6).

SC-05(요약)/SC-06(수료증) 화면의 실제 콘텐츠, SC-02(커리큘럼 확인) 화면 문구 등은 웹 디자인 범위라
이 모듈의 책임이 아니다 — 여기서는 상태값 전환까지만 다룬다(README "우선순위" 참고).
"""
import os
import threading
import time

import httpx
from fastapi import APIRouter

router = APIRouter()

VISION_URL = os.getenv("VISION_URL", "http://localhost:8001")
ACTUATION_URL = os.getenv("ACTUATION_URL", "http://localhost:8002")
PICAR_URL = os.getenv("PICAR_URL", "http://localhost:8003")
PICAR_TIMEOUT_MS = int(os.getenv("PICAR_TIMEOUT_MS", "500"))
ACTUATION_TIMEOUT_S = float(os.getenv("ACTUATION_TIMEOUT_S", "2.0"))
POLL_INTERVAL_S = float(os.getenv("VISION_POLL_INTERVAL_S", "0.2"))

# SC-01~SC-07 상태값. 09_화면목록_v2.md 표와 동기화 유지.
# 구 SC-02(분야 선택)·SC-08(관리자 등록)은 아키텍처 변경으로 제거됨.
STATES = [
    "landing",             # SC-01
    "curriculum_confirm",  # SC-02
    "training",            # SC-03 (+ correct/incorrect 하위 상태 SC-03a/03b)
    "camera_fail",         # SC-04
    "summary",             # SC-05
    "certificate",         # SC-06
    "reentry",             # SC-07 — 이어하기 없음, 항상 처음부터 재시작 안내만
]

# 커리큘럼 순서 — 10_PRD_v2.md §3.2 표 순서. 학습 순서 자체는 TBD(교육 설계 확정 필요), 우선
# PRD 표 순서를 기본값으로 둔다.
CURRICULUM = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]

# target_signal -> picar_command.schema.json 페이로드. `수신호에 따른 picar 동작.md` 기준.
# motor.speed는 스키마에도 "실측 후 확정"으로 TBD 표시되어 있음 — 아래 값은 잠정 placeholder.
PICAR_COMMANDS = {
    "정지": {"command": "stop", "motor": {"action": "stop", "speed": 0},
            "led": {"red": "on", "yellow_left": "off", "yellow_right": "off"}},
    "서행": {"command": "slow", "motor": {"action": "forward", "speed": 40},
            "led": {"red": "off", "yellow_left": "blink", "yellow_right": "blink"}},
    "좌회전_유도": {"command": "turn_left", "motor": {"action": "left", "speed": 60},
                "led": {"red": "off", "yellow_left": "blink", "yellow_right": "off"}},
    "우회전_유도": {"command": "turn_right", "motor": {"action": "right", "speed": 60},
                "led": {"red": "off", "yellow_left": "off", "yellow_right": "blink"}},
    "확인_완료": {"command": "complete", "motor": {"action": "stop", "speed": 0},
              "led": {"red": "blink", "yellow_left": "blink", "yellow_right": "blink"}},
    "후진": {"command": "reverse", "motor": {"action": "backward", "speed": 50},
            "led": {"red": "off", "yellow_left": "off", "yellow_right": "off"}},
    "주의": {"command": "caution", "motor": {"action": "stop", "speed": 0},
            "led": {"red": "off", "yellow_left": "blink", "yellow_right": "blink"}},
}

# aihand_command.schema.json이 servo_angles를 필수로 요구하지만, 현재 actuation은 BLE G{n} 제스처를
# target_signal만으로 결정하고 servo_angles는 쓰지 않는다(services/actuation/src/aihand/controller.py
# 참고). 스키마 호환을 위한 placeholder 값 — 실제 서보 각도에는 영향 없음.
_PLACEHOLDER_SERVO_ANGLES = {
    "thumb": 170, "index": 170, "middle": 170, "ring": 170, "pinky": 170, "wrist_rotation": 90,
}

_lock = threading.Lock()
_session = {
    "state": "landing",
    "curriculum_index": 0,
    "last_result": None,       # {"predicted_class", "is_correct", "match_score"}
    "_last_dispatched": None,  # (curriculum_index, predicted_class) 중복 물리 피드백 방지용
}


def _current_target_signal() -> "str | None":
    idx = _session["curriculum_index"]
    return CURRICULUM[idx] if idx < len(CURRICULUM) else None


def _post_with_retry(url: str, json: dict, timeout_s: float) -> None:
    """실패해도 예외를 삼키고 계속 진행 — 1회 재시도 후에도 실패하면 그냥 넘어간다
    (03_인터페이스계약서_v2 §7, picar/actuation 모두 동일 정책 적용)."""
    for _ in range(2):
        try:
            httpx.post(url, json=json, timeout=timeout_s)
            return
        except httpx.HTTPError:
            continue


def _dispatch_feedback(target_signal: str, is_correct: bool, judgment: dict) -> None:
    match_score = judgment.get("match_score", 0)
    aihand_command = "correct_pose" if is_correct else "demo"

    _post_with_retry(f"{ACTUATION_URL}/command", {
        "command": aihand_command,
        "target_signal": target_signal,
        "servo_angles": _PLACEHOLDER_SERVO_ANGLES,
    }, ACTUATION_TIMEOUT_S)

    _post_with_retry(f"{ACTUATION_URL}/result", {
        "is_correct": is_correct, "match_score": match_score,
    }, ACTUATION_TIMEOUT_S)

    _post_with_retry(f"{ACTUATION_URL}/progress", {
        "current": _session["curriculum_index"] + 1, "total": len(CURRICULUM),
    }, ACTUATION_TIMEOUT_S)

    if is_correct:
        picar_command = PICAR_COMMANDS[target_signal]
        _post_with_retry(f"{PICAR_URL}/picar", {
            "target_signal": target_signal, **picar_command,
        }, PICAR_TIMEOUT_MS / 1000)


def _poll_once(vision_client: httpx.Client) -> None:
    with _lock:
        if _session["state"] != "training":
            return
        target_signal = _current_target_signal()
    if target_signal is None:
        return

    try:
        judgment = vision_client.get(f"{VISION_URL}/latest").json()
    except httpx.HTTPError:
        return

    if judgment.get("is_reject", True) or judgment.get("predicted_class") == "negative":
        return

    predicted = judgment["predicted_class"]

    with _lock:
        idx = _session["curriculum_index"]
        dispatch_key = (idx, predicted)
        if _session["_last_dispatched"] == dispatch_key:
            return  # 같은 판정이 계속 들어오는 동안 물리 피드백을 반복 트리거하지 않음
        _session["_last_dispatched"] = dispatch_key

    is_correct = predicted == target_signal
    _dispatch_feedback(target_signal, is_correct, judgment)

    with _lock:
        _session["last_result"] = {
            "predicted_class": predicted, "is_correct": is_correct,
            "match_score": judgment.get("match_score", 0),
        }
        if is_correct:
            _session["curriculum_index"] += 1
            _session["_last_dispatched"] = None
            if _session["curriculum_index"] >= len(CURRICULUM):
                _session["state"] = "summary"


def _poll_loop() -> None:
    with httpx.Client() as vision_client:
        while True:
            _poll_once(vision_client)
            time.sleep(POLL_INTERVAL_S)


def start_polling() -> None:
    threading.Thread(target=_poll_loop, daemon=True).start()


@router.get("/state")
def get_state():
    with _lock:
        return {
            "state": _session["state"],
            "target_signal": _current_target_signal(),
            "progress": {"current": _session["curriculum_index"] + 1, "total": len(CURRICULUM)},
            "last_result": _session["last_result"],
        }


@router.post("/start")
def start():
    """SC-01/02 -> SC-03: 커리큘럼을 처음부터 시작 (세션 이어하기 없음, 2026-09-18 결정)."""
    with _lock:
        _session["state"] = "training"
        _session["curriculum_index"] = 0
        _session["last_result"] = None
        _session["_last_dispatched"] = None
    return {"state": "training", "target_signal": CURRICULUM[0]}
