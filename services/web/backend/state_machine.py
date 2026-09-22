"""교육 상태머신 (09_화면목록_v2.md SC-01~SC-07 대응).

담당: 조은수 (웹 R, 성능측정 R)

세션별 현재 state는 메모리 딕셔너리(`_session`)로 관리한다 — SC-07은 세션 이어하기가 없어(재접속 시
항상 "처음부터", 2026-09-18 결정) DB/Redis 같은 영속 저장소가 필요 없다. 다중 학습자 동시 세션도
범위 밖이라(1대 1 교육 스테이션) 세션 ID 없이 프로세스 전역 상태 하나로 충분하다.

백그라운드 스레드(`start_polling`)가 vision의 GET /latest를 폴링해 judgment_result를 받고,
현재 커리큘럼 단계(target_signal)와 비교해 SC-03a(정답)/SC-03b(오답·below_tau·out_of_distribution)로
분기한다. `reason`(judgment_result.schema.json)에 따라:
  - no_hand / normalize_failed 가 연속 CAMERA_FAIL_STREAK_THRESHOLD회 이상 지속 -> SC-04(camera_fail)
  - below_tau / out_of_distribution -> SC-03b (자세 다듬기 / 다른 수신호 두 메시지를 구분, 2026-09-22 추가)
  - awaiting_consecutive_frames / model_not_loaded / inference_error -> 과도기 상태, 오버레이 없이 대기
  - is_reject=false 이고 predicted_class != target_signal -> SC-03b 오답
  - is_reject=false 이고 predicted_class == target_signal -> SC-03a 정답

정답이 확정되면:
- actuation(RPi5, ACTUATION_URL)의 POST /command(AI Hand) · /result · /progress(micro:bit) 호출
- **picar(RPi4B 8GB, PICAR_URL)의 POST /picar를 별도로 직접 호출** — actuation을 거치지 않는다.
  picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에 컴퓨트 보드를 분리했다
  (02_설계문서_v2 §1-1, 2026-09-18).
- vision의 POST /reset을 호출해 다음 수신호를 위한 N프레임 연속판정 누적을 초기화한다
  (vision/src/app.py 문서화: "다음 수신호로 넘어갈 때 웹 상태머신이 호출").

장치 통신 신뢰성 (2026-09-21 web_picar_통신_신뢰성_개선안.md 반영, 조은수 검토·결정):
- `_post_with_retry`는 예외뿐 아니라 4xx/5xx 응답도 실패로 간주하고, 결과를 호출부에 돌려준다
  (기존에는 반환값을 버려 "조용한 실패"를 감지할 수 없었다).
- 모든 전송 결과를 `_session["last_dispatch"]`에 남겨 `/api/state`로 노출한다.
- vision/actuation/picar의 GET /health를 주기적으로 확인해 `_session["devices"]`로 노출한다.
- `_dispatch_feedback`은 여전히 순차 블로킹이다(§4 A/B/C 중 C안 채택: 순서 보장이 필요하고 로컬 통신이라
  구조 변경의 이득이 크지 않다는 판단). 대신 ACTUATION_TIMEOUT_S를 2.0 -> 0.6초로 낮춰 최악 대기시간을
  줄인다(actuation 3회 x (0.6초 x 2회) + picar 0.5초 x 2회 ≈ 4.6초, 기존 13초 대비 1/3 이하).
  BLE 정상 응답은 0.6초보다 훨씬 빠르다는 전제이며, 실측 후 필요하면 재조정한다.

관리자/등록 관련 상태 없음 — 수신호 등록 기능은 범위에서 제외됨 (03_인터페이스계약서_v2 §6).

SC-05(요약)/SC-06(수료증) 화면의 세부 레이아웃, SC-02(커리큘럼 확인) 화면 문구 등 시각 디자인은
프론트엔드(frontend/) 책임이며, 이 모듈은 그 화면들이 필요로 하는 상태값·집계 데이터까지만 만든다.
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
# 2026-09-21 개선안 §4 C안 채택 (조은수 결정) — 2.0초 -> 0.6초, 최악 폴링 정지시간 완화.
ACTUATION_TIMEOUT_S = float(os.getenv("ACTUATION_TIMEOUT_S", "0.6"))
POLL_INTERVAL_S = float(os.getenv("VISION_POLL_INTERVAL_S", "0.2"))
DEVICE_HEALTH_INTERVAL_S = float(os.getenv("DEVICE_HEALTH_INTERVAL_S", "5.0"))
DEVICE_HEALTH_TIMEOUT_S = 1.5

# 손 미검출(no_hand/normalize_failed)이 연속 몇 회 지속되면 SC-04로 전환할지 — 09_화면목록_v2.md가
# "임계값 필요"라고만 표시하고 수치는 정의하지 않아, POLL_INTERVAL_S 0.2초 기준 약 3초에 해당하는
# 잠정치를 둔다. PICAR_COMMANDS의 motor.speed와 동일하게 실측 후 조정 대상(TBD).
CAMERA_FAIL_STREAK_THRESHOLD = 15

# SC-01~SC-07 상태값. 09_화면목록_v2.md 표와 동기화 유지.
# 구 SC-02(분야 선택)·SC-08(관리자 등록)은 아키텍처 변경으로 제거됨.
STATES = [
    "landing",             # SC-01
    "curriculum_confirm",  # SC-02
    "training",            # SC-03 (+ correct/wrong/below_tau/out_of_distribution 하위 상태 SC-03a/03b)
    "camera_fail",         # SC-04
    "summary",             # SC-05
    "certificate",         # SC-06
    "reentry",             # SC-07 — 이어하기 없음, 항상 처음부터 재시작 안내만 (프론트엔드가 판단)
]

# 커리큘럼 순서 — 10_PRD_v2.md §3.2 표 순서. 학습 순서 자체는 TBD(교육 설계 확정 필요), 우선
# PRD 표 순서를 기본값으로 둔다.
CURRICULUM = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]

# SC-02/SC-03 표시용 설명. 10_PRD_v2.md §3.2 · 수신호에 따른 picar 동작.md 기준(2026-09-20 확정본).
CURRICULUM_INFO = {
    "정지": {"aihand": "다섯 손가락 펴기 + 정면", "picar": "정지 + 양쪽 적색 LED 점등"},
    "서행": {"aihand": "검지 + 중지 펴기 + 정면", "picar": "감속 주행 + 양쪽 황색 LED 점멸"},
    "좌회전_유도": {"aihand": "엄지 + 검지 펴기", "picar": "좌회전 주행 + 좌측 황색 LED 점멸"},
    "우회전_유도": {"aihand": "엄지 + 소지 펴기 (2026-09-20 변경: 약지→소지)",
                "picar": "우회전 주행 + 우측 황색 LED 점멸"},
    # 10_PRD_v2 §3.2·03_인터페이스계약서_v2 표는 "다섯 손가락 접기(주먹)"으로 확정(2026-09-20 팀 승인)했으나,
    # 실제 actuation 코드(controller.py DEFAULT_SERVO_ANGLES·firmware gesture5)는 아직 이전 값인
    # "엄지만 펴기"로 남아 있다 — actuation 쪽 동기화가 필요한 미해결 gap(2026-09-21 팀 확인,
    # 03_인터페이스계약서_v2 §5-1 changelog에도 명시). 여기서는 팀이 확정한 최종 스펙을 표시한다.
    "확인_완료": {"aihand": "다섯 손가락 접기(주먹) + 정면", "picar": "적색·황색 LED 번갈아 2회 점멸 후 소등"},
    "후진": {"aihand": "검지만 펴기", "picar": "후진 주행"},
    "주의": {"aihand": "소지(새끼손가락)만 펴기", "picar": "정지 + 양쪽 황색 LED 점멸"},
}

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

NEGATIVE_LABEL = "negative"  # vision/src/cognition/classify.py NEGATIVE_CLASS와 동일

# judgment_result.schema.json의 reason enum 분류
CAMERA_FAIL_REASONS = {"no_hand", "normalize_failed"}
HOLD_REASONS = {"below_tau", "out_of_distribution"}  # SC-03b, 메시지만 다름
SILENT_REASONS = {"awaiting_consecutive_frames", "model_not_loaded", "inference_error"}

# SC-03b 안내 문구 (03_인터페이스계약서_v2 §4, 2026-09-22 추가: below_tau/out_of_distribution 구분)
OUTCOME_MESSAGES = {
    "wrong": "다시 시도하세요",
    "below_tau": "조금 더 정확히 해주세요",
    "out_of_distribution": "다른 수신호를 하고 계세요",
}

_lock = threading.Lock()
_session: dict = {}


def _fresh_session() -> dict:
    return {
        "state": "landing",
        "curriculum_index": 0,
        "last_result": None,       # {"outcome", "predicted_class", "match_score", "confidence", "message", ...}
        "_last_dispatched": None,  # (idx, outcome, predicted/reason) 중복 물리 피드백 방지용
        "attempts": {},            # signal -> 현재 회차 시도 횟수
        "completed": [],           # [{"signal", "attempts", "match_score"}] 완료 순서대로
        "camera_fail_streak": 0,
        "last_dispatch": None,     # 최근 _dispatch_feedback 결과 (actuation/picar 성공 여부)
        "devices": {},             # vision/actuation/picar 최근 /health 스냅샷
        "live_judgment": None,     # 매 폴링 갱신되는 실시간 match_score (SC-03 진행 표시용)
        "certificate_issued_at": None,
    }


_session = _fresh_session()


def _current_target_signal() -> "str | None":
    idx = _session["curriculum_index"]
    return CURRICULUM[idx] if idx < len(CURRICULUM) else None


def _recommended_retry_count(match_score: int) -> int:
    """권장 재도전 횟수(SC-03b) — 09_화면목록_v2.md가 표시 항목으로 요구하나 산식은 어느 문서에도
    정의돼 있지 않다. match_score 구간별 잠정치이며 PICAR_COMMANDS의 motor.speed와 같은 성격의
    TBD 값이다. 실측 후 팀 확정 필요."""
    if match_score >= 70:
        return 1
    if match_score >= 40:
        return 2
    return 3


def _post_with_retry(url: str, json: dict, timeout_s: float) -> dict:
    """실패해도 예외를 삼키고 계속 진행하되, 결과는 호출부에 돌려준다
    (03_인터페이스계약서_v2 §7 — 장치 실패가 학습 흐름을 막지 않는 정책은 유지).

    httpx.post()는 4xx/5xx에 예외를 던지지 않으므로 status_code를 직접 확인한다 — 이전 구현은
    반환값을 버려 서버 오류를 성공으로 셌다(2026-09-21 web_picar_통신_신뢰성_개선안.md §1-1)."""
    last_error = None
    for _ in range(2):
        try:
            response = httpx.post(url, json=json, timeout=timeout_s)
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
            continue

        if response.status_code >= 400:
            last_error = f"http_{response.status_code}"
            continue

        try:
            body = response.json()
        except ValueError:
            body = None
        return {"ok": True, "body": body}

    return {"ok": False, "error": last_error}


def _dispatch_feedback(target_signal: str, outcome: str, judgment: dict) -> dict:
    is_correct = outcome == "correct"
    match_score = judgment.get("match_score", 0)
    aihand_command = "correct_pose" if is_correct else "demo"

    results = {
        "aihand": _post_with_retry(f"{ACTUATION_URL}/command", {
            "command": aihand_command,
            "target_signal": target_signal,
            "servo_angles": _PLACEHOLDER_SERVO_ANGLES,
        }, ACTUATION_TIMEOUT_S),
        "result": _post_with_retry(f"{ACTUATION_URL}/result", {
            "is_correct": is_correct, "match_score": match_score,
        }, ACTUATION_TIMEOUT_S),
        "progress": _post_with_retry(f"{ACTUATION_URL}/progress", {
            "current": _session["curriculum_index"] + 1, "total": len(CURRICULUM),
        }, ACTUATION_TIMEOUT_S),
    }

    if is_correct:
        picar_command = PICAR_COMMANDS[target_signal]
        results["picar"] = _post_with_retry(f"{PICAR_URL}/picar", {
            "target_signal": target_signal, **picar_command,
        }, PICAR_TIMEOUT_MS / 1000)

    return results


def _poll_once(vision_client: httpx.Client) -> None:
    with _lock:
        state = _session["state"]
        if state not in ("training", "camera_fail"):
            return
        target_signal = _current_target_signal()
    if target_signal is None:
        return

    try:
        judgment = vision_client.get(f"{VISION_URL}/latest").json()
    except httpx.HTTPError:
        return

    is_reject = judgment.get("is_reject", True)
    reason = judgment.get("reason")
    predicted = judgment.get("predicted_class")

    # 확정된 정답/오답 이벤트와 별개로, SC-03의 실시간 match_score 진행 표시를 위해 매 폴링마다
    # 갱신한다(아래 dedup은 물리 피드백 중복 방지용이지 화면 표시용이 아니다).
    with _lock:
        _session["live_judgment"] = {
            "predicted_class": predicted,
            "confidence": judgment.get("confidence", 0),
            "match_score": judgment.get("match_score", 0),
            "is_reject": is_reject,
            "reason": reason,
        }

    if is_reject and reason in CAMERA_FAIL_REASONS:
        with _lock:
            _session["camera_fail_streak"] += 1
            if _session["camera_fail_streak"] >= CAMERA_FAIL_STREAK_THRESHOLD:
                _session["state"] = "camera_fail"
        return

    # 손이 다시 보이면 미검출 스트릭을 초기화하고, SC-04였다면 SC-03으로 자동 복귀한다.
    with _lock:
        _session["camera_fail_streak"] = 0
        if _session["state"] == "camera_fail":
            _session["state"] = "training"
        elif _session["state"] != "training":
            return

    if is_reject and reason in SILENT_REASONS:
        return  # 과도기 상태(모델 로딩/N프레임 누적 중 등) — 오버레이 없이 대기

    if is_reject and reason in HOLD_REASONS:
        outcome = reason  # "below_tau" | "out_of_distribution"
        dispatch_key = (_session["curriculum_index"], "reject", reason)
    elif not is_reject and predicted and predicted != NEGATIVE_LABEL:
        outcome = "correct" if predicted == target_signal else "wrong"
        dispatch_key = (_session["curriculum_index"], outcome, predicted)
    else:
        return

    with _lock:
        if _session["_last_dispatched"] == dispatch_key:
            return  # 같은 판정이 계속 들어오는 동안 물리 피드백/시도횟수를 반복 집계하지 않음
        _session["_last_dispatched"] = dispatch_key
        _session["attempts"][target_signal] = _session["attempts"].get(target_signal, 0) + 1
        attempt_no = _session["attempts"][target_signal]

    dispatch_results = _dispatch_feedback(target_signal, outcome, judgment)

    match_score = judgment.get("match_score", 0)
    finished = False
    with _lock:
        _session["last_dispatch"] = dispatch_results
        _session["last_result"] = {
            "signal": target_signal,  # 정답 시 curriculum_index가 이미 다음으로 넘어가므로 별도 보관
            "outcome": outcome,
            "predicted_class": predicted,
            "match_score": match_score,
            "confidence": judgment.get("confidence", 0),
            "attempt": attempt_no,
            "message": OUTCOME_MESSAGES.get(outcome),
            "recommended_retry": _recommended_retry_count(match_score),
        }
        if outcome == "correct":
            _session["completed"].append({
                "signal": target_signal, "attempts": attempt_no, "match_score": match_score,
            })
            _session["curriculum_index"] += 1
            _session["_last_dispatched"] = None
            if _session["curriculum_index"] >= len(CURRICULUM):
                _session["state"] = "summary"
                finished = True

    if outcome == "correct" and not finished:
        try:
            vision_client.post(f"{VISION_URL}/reset")
        except httpx.HTTPError:
            pass


def _poll_loop() -> None:
    with httpx.Client() as vision_client:
        while True:
            _poll_once(vision_client)
            time.sleep(POLL_INTERVAL_S)


def _check_devices(client: httpx.Client) -> dict:
    """vision/actuation/picar의 GET /health를 확인 — 실패해도 학습 흐름에는 영향 없음
    (2026-09-21 web_picar_통신_신뢰성_개선안.md §3)."""
    status = {}
    for name, url in (("vision", VISION_URL), ("actuation", ACTUATION_URL), ("picar", PICAR_URL)):
        try:
            body = client.get(f"{url}/health", timeout=DEVICE_HEALTH_TIMEOUT_S).json()
        except (httpx.HTTPError, ValueError):
            status[name] = {"status": "unreachable"}
            continue

        entry = {"status": body.get("status", "unknown")}
        if name == "actuation":
            entry["microbit_connected"] = body.get("microbit_connected")
        if name == "picar":
            hardware = body.get("hardware") or {}
            entry["i2c_reachable"] = (hardware.get("i2c") or {}).get("reachable")
        status[name] = entry
    return status


def _device_health_loop() -> None:
    with httpx.Client() as client:
        while True:
            devices = _check_devices(client)
            with _lock:
                _session["devices"] = devices
            time.sleep(DEVICE_HEALTH_INTERVAL_S)


def start_polling() -> None:
    threading.Thread(target=_poll_loop, daemon=True).start()
    threading.Thread(target=_device_health_loop, daemon=True).start()


@router.get("/state")
def get_state():
    with _lock:
        target_signal = _current_target_signal()
        return {
            "state": _session["state"],
            "target_signal": target_signal,
            "signal_info": CURRICULUM_INFO.get(target_signal) if target_signal else None,
            "curriculum": [
                {"signal": s, **CURRICULUM_INFO[s]} for s in CURRICULUM
            ],
            "progress": {"current": _session["curriculum_index"] + 1, "total": len(CURRICULUM)},
            "last_result": _session["last_result"],
            "live_judgment": _session["live_judgment"],
            "attempts": _session["attempts"].get(target_signal, 0) if target_signal else 0,
            "last_dispatch": _session["last_dispatch"],
            "devices": _session["devices"],
            "completed": _session["completed"],
            "certificate_issued_at": _session["certificate_issued_at"],
        }


@router.post("/start")
def start():
    """SC-01/02 -> SC-03: 커리큘럼을 처음부터 시작 (세션 이어하기 없음, 2026-09-18 결정)."""
    with _lock:
        devices = _session["devices"]  # 장치 상태는 세션 리셋과 무관하게 유지
        _session.clear()
        _session.update(_fresh_session())
        _session["state"] = "training"
        _session["devices"] = devices
    return {"state": "training", "target_signal": CURRICULUM[0]}


@router.post("/certificate")
def issue_certificate():
    """SC-05 -> SC-06: 7종 전체 완료 후 수료증 발급. 실물 이미지/PDF 렌더링은 프론트엔드 담당이며,
    여기서는 발급 시각과 최종 집계만 확정해 내려준다."""
    with _lock:
        if len(_session["completed"]) < len(CURRICULUM):
            return {"status": "error", "reason": "not_completed"}
        _session["state"] = "certificate"
        if _session["certificate_issued_at"] is None:
            _session["certificate_issued_at"] = time.time()
        return {
            "status": "ok",
            "state": "certificate",
            "issued_at": _session["certificate_issued_at"],
            "completed": _session["completed"],
        }
