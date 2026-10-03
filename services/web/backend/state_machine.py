"""교육 상태머신 (09_화면목록.md SC-01~SC-07 대응).

담당: 조은수 (웹 R, 성능측정 R) · 판정 로직(web 할 일 ①-a·②-a·③)은 이동혁 (2026-09-28 분담, 14 §8)

판정 타이밍 — 시범 + 확인 버튼 (document/proposals/web_판정_타이밍_스펙.md, 2026-09-27 확정)
  SC-03 안에 하위 단계 `phase`("demo" | "judging")를 둔다. 새 STATES는 만들지 않는다(09 "화면 내 상태" 원칙).
  - 수신호 시작(POST /api/start, 정답 뒤 다음 수신호) → AI Hand 시범 `/command`(demo)만 보내고 phase="demo".
    시범 단계에서는 판정하지 않고 SC-04 카운트도 세지 않는다 — 9/25 시험에서 방금 맞힌 손모양이 다음 수신호의
    오답으로 잡히고, 시범을 보는 사이 SC-04로 넘어가던 문제.
  - 학습자가 확인 버튼(POST /api/confirm, 스페이스바)을 누르면 vision /reset → phase="judging".
    micro:bit 버튼 A도 같은 확인으로 받는다(스펙 §9, 보조 입력) — 시범 단계에서만 actuation GET /button의 `seq`를
    폴링해, 시범이 끝난 뒤 적어 둔 기준값보다 커지면 확인한다. 시범 도중·판정 중에 누른 입력은 세지 않는다.
  - 정답은 즉시 확정. 오답은 **같은 오답 클래스가 WRONG_CONFIRM_S(1초) 이상 이어질 때만** 확정한다 — 버튼을
    누르고 손을 올리는 도중의 과도 자세를 거르기 위해서다. 손 미검출이 나오면 새로 센다
    (기준 구현: services/actuation/scripts/aihand_vision_picar_demo.py `_listen()`, 9/25 실물 7/7).
  - 오답이 확정되면 재시범(`/command` demo) 뒤 다시 phase="demo".
  - below_tau / out_of_distribution(스펙 §5, 이동혁 결정): **화면 안내 문구만** 띄우고 물리 피드백·시도 횟수·
    시행 로그에 넣지 않는다. 손을 올리는 도중에도 자주 나오는 값이라, 매번 AI Hand가 재시범하면 따라 할 틈이 없다.

세션별 현재 state는 메모리 딕셔너리(`_session`)로 관리한다 — SC-07은 세션 이어하기가 없어(재접속 시
항상 "처음부터", 2026-09-18 결정) DB/Redis 같은 영속 저장소가 필요 없다. 다중 학습자 동시 세션도
범위 밖이라(1대 1 교육 스테이션) 세션 ID 없이 프로세스 전역 상태 하나로 충분하다.

백그라운드 스레드(`start_polling`)가 vision의 GET /latest를 폴링해 judgment_result를 받고,
현재 커리큘럼 단계(target_signal)와 비교해 SC-03a(정답)/SC-03b(오답·below_tau·out_of_distribution)로
분기한다. `reason`(judgment_result.schema.json)에 따라:
  - no_hand / normalize_failed 가 연속 CAMERA_FAIL_STREAK_THRESHOLD회 이상 지속 -> SC-04(camera_fail)
  - below_tau / out_of_distribution -> SC-03b 안내 문구만 (자세 다듬기 / 다른 수신호 두 메시지를 구분,
    2026-09-22 추가). 물리 피드백은 보내지 않는다(위 판정 타이밍 참고)
  - awaiting_consecutive_frames / model_not_loaded / inference_error -> 과도기 상태, 오버레이 없이 대기
  - is_reject=false 이고 predicted_class != target_signal -> SC-03b 오답 (같은 클래스 1초 유지 시)
  - is_reject=false 이고 predicted_class == target_signal -> SC-03a 정답

정답이 확정되면:
- actuation(RPi5, ACTUATION_URL)의 POST /result · /command(AI Hand) · /progress(micro:bit) 호출
- **picar(RPi4B 8GB, PICAR_URL)의 POST /picar를 별도로 직접 호출** — actuation을 거치지 않는다.
  picar가 주행하면 카메라도 함께 이동해버리는 문제 때문에 컴퓨트 보드를 분리했다
  (02_설계문서 §1-1, 2026-09-18).
- vision의 POST /reset을 호출해 다음 수신호를 위한 N프레임 연속판정 누적을 초기화한다
  (vision/src/app.py 문서화: "다음 수신호로 넘어갈 때 웹 상태머신이 호출").

장치 통신 신뢰성 (2026-09-21 web_picar_통신_신뢰성_개선안.md 반영, 조은수 검토·결정):
- `_post_with_retry`는 예외뿐 아니라 4xx/5xx 응답도 실패로 간주하고, 결과를 호출부에 돌려준다
  (기존에는 반환값을 버려 "조용한 실패"를 감지할 수 없었다).
- 모든 전송 결과를 `_session["last_dispatch"]`에 남겨 `/api/state`로 노출한다.
- vision/actuation/picar의 GET /health를 주기적으로 확인해 `_session["devices"]`로 노출한다.
- `_dispatch_feedback`은 여전히 순차 블로킹이다 — micro:bit가 명령을 하나씩 처리하므로 actuation 호출은
  병렬로 보내도 빨라지지 않고, 순서 보장도 필요하다. 타임아웃은 엔드포인트별로 나눈다(2026-09-23 개선안
  §4 C′안, 송승호 실측 반영): /command는 손 동작이 끝난 뒤 회신해 실측 0.79~0.83초라 1.5초,
  /result·/progress는 실측 26~42ms라 0.5초. 최악 대기시간 = 1.5x2 + 0.5x2 + 0.5x2 + picar 0.5x2 ≈ 6초
  (기존 2.0초 일괄 시 13초). 이전에 채택했던 C안(일괄 0.6초)은 /command가 전부 timeout 나서 철회됐다.
- **호출 순서는 /picar → /result → /command → /progress** (스펙 §7.3, 2026-09-28 이동혁 결정). 예전 순서
  (/command 맨 앞)는 /command가 손 동작이 끝나야 회신(0.8초)해서 picar·micro:bit 반응이 약 0.85초 늦었다.
  picar는 다른 보드라 micro:bit 순서 제약과 무관하고, /result(ACK 26~42ms)는 /command 앞에 둬도 된다.
- **응답 판정은 본문 status까지 본다** (03 §5-5, web 할 일 ③): HTTP 200이어도 `timeout`·`error`·`partial`은
  실패. 본문 실패는 재시도하지 않는다(이미 장치에 닿았을 수 있다 — 다시 보내면 AI Hand·picar가 두 번 움직인다).
  읽기 타임아웃도 /command·/picar는 재시도하지 않는다. 연결 실패·4xx/5xx만 1회 재시도.

시행 로그 CSV (스펙 §7, web 할 일 ②-a): 판정이 확정될 때마다(정답·오답) 1행을
`TRIAL_LOG_DIR/web_trials_<기동시각>.csv`에 쓴다(UTF-8 BOM, 쓰는 즉시 파일을 닫아 flush). 앞 17열은 web 없는
데모 스크립트 CSV(`RECORD_FIELDS`)와 같은 순서라 두 결과를 한 표로 비교할 수 있다.

관리자/등록 관련 상태 없음 — 수신호 등록 기능은 범위에서 제외됨 (03_인터페이스계약서 §6).

SC-05(요약)/SC-06(수료증) 화면의 세부 레이아웃, SC-02(커리큘럼 확인) 화면 문구 등 시각 디자인은
프론트엔드(frontend/) 책임이며, 이 모듈은 그 화면들이 필요로 하는 상태값·집계 데이터까지만 만든다.
"""
import csv
import itertools
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter

from backend import members

logger = logging.getLogger(__name__)
router = APIRouter()

VISION_URL = os.getenv("VISION_URL", "http://localhost:8001")
ACTUATION_URL = os.getenv("ACTUATION_URL", "http://localhost:8002")
PICAR_URL = os.getenv("PICAR_URL", "http://localhost:8003")
PICAR_TIMEOUT_MS = int(os.getenv("PICAR_TIMEOUT_MS", "500"))
# 2026-09-23 개선안 §4 C′안 — 엔드포인트별 타임아웃 (C안 0.6초 일괄은 /command 실측 0.80초라 철회).
ACTUATION_COMMAND_TIMEOUT_S = float(os.getenv("ACTUATION_COMMAND_TIMEOUT_S", "1.5"))   # /command
ACTUATION_FEEDBACK_TIMEOUT_S = float(os.getenv("ACTUATION_FEEDBACK_TIMEOUT_S", "0.5"))  # /result, /progress
POLL_INTERVAL_S = float(os.getenv("VISION_POLL_INTERVAL_S", "0.2"))
# vision 호출 타임아웃 — 지정하지 않으면 httpx 기본 5초라 vision이 멈추면 폴링도 5초씩 멈췄다(16 §4.7 #6).
# /latest는 저장된 최신 판정을 돌려줄 뿐이라 로컬에서 수 ms다.
VISION_TIMEOUT_S = float(os.getenv("VISION_TIMEOUT_S", "0.5"))
# micro:bit 버튼 A를 확인 입력으로 쓸지 (스펙 §9). 호출 시점에 읽는다 — 테스트는 conftest에서 끄고 필요한 테스트만 켠다.
BUTTON_CONFIRM_ENABLED = os.getenv("MICROBIT_BUTTON_CONFIRM", "1").strip().lower() not in ("0", "off", "false", "no")
# actuation GET /button 타임아웃 — 보조 입력이라 짧게. 실패는 조용히 넘긴다.
BUTTON_TIMEOUT_S = float(os.getenv("BUTTON_TIMEOUT_S", "0.3"))
# 같은 오답 클래스가 이만큼 이어져야 오답 확정 (스펙 §2 #4). 호출 시점에 읽는다 — 테스트가 바꿔 끼운다.
WRONG_CONFIRM_S = float(os.getenv("WRONG_CONFIRM_S", "1.0"))
# 한 수신호에서 허용하는 최대 시도 횟수 (2026-09-29 실물 재시험에서 발견 — 상한이 없어 오답이 계속되면
# 검정에서 빠져나오지 못했다). 3 = 최초 시도 1회 + 재시도 2회. 초과하면 이 수신호는 넘기고 다음으로 진행한다
# (below_tau/OOD와 달리 손모양 자체는 명확히 인식됐으므로 "오분류"로 집계 — completed에 given_up 표시).
MAX_ATTEMPTS_PER_SIGNAL = int(os.getenv("MAX_ATTEMPTS_PER_SIGNAL", "3"))
# 판정 한 번의 제한시간 — 넘기면 `timeout`으로 시도 1회를 센다. below_tau/OOD는 안내만 하고 시도로 세지 않아(D10)
# 틀린 손모양이 확신도 낮게 잡히면 판정이 끝나지 않았고, 그러면 위 상한도 적용되지 않았다(2026-09-29 ⑥ 재시험).
# 기준 구현 aihand_vision_picar_demo.py `_listen()`의 --listen-timeout 기본값(10초)과 같다. 호출 시점에 읽는다.
JUDGING_TIMEOUT_S = float(os.getenv("JUDGING_TIMEOUT_S", "10.0"))
# 시행 로그 CSV 폴더 (스펙 §7.1). 쓰는 시점에 읽는다. 파일 이름은 web 기동 시각 — 기동마다 새 파일.
TRIAL_LOG_DIR = Path(os.getenv("TRIAL_LOG_DIR", str(Path(__file__).resolve().parents[1] / "logs")))
_TRIAL_LOG_NAME = f"web_trials_{datetime.now():%Y%m%d_%H%M%S}.csv"
DEVICE_HEALTH_INTERVAL_S = float(os.getenv("DEVICE_HEALTH_INTERVAL_S", "5.0"))
DEVICE_HEALTH_TIMEOUT_S = 1.5

# 판정 단계에서 손 미검출(no_hand/normalize_failed)이 연속 몇 회면 SC-04로 전환할지. 25회 = POLL_INTERVAL_S 0.2초 기준
# 약 5초(2026-09-29 조은수 결정, 14 §9). 9/25 실물 데모에서 판정 시작 → 정답까지 1.2~8.0초(중앙값 2.3초)라 예전 15회(3초)는
# 정상적으로 손을 올리는 학습자도 SC-04로 넘길 수 있었다. 재시험(⑥)에서 코드 수정 없이 바꿀 수 있게 환경변수로 받는다.
CAMERA_FAIL_STREAK_THRESHOLD = int(os.getenv("CAMERA_FAIL_STREAK_THRESHOLD", "25"))

# SC-01~SC-07 상태값. 09_화면목록.md 표와 동기화 유지.
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

# 커리큘럼 순서 — 10_PRD.md §3.2 표 순서. 학습 순서 자체는 TBD(교육 설계 확정 필요), 우선
# PRD 표 순서를 기본값으로 둔다.
CURRICULUM = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]

# SC-02/SC-03 표시용 설명. 10_PRD.md §3.2 · 02_설계문서.md §4 기준(구 `수신호에 따른 picar 동작.md`).
CURRICULUM_INFO = {
    "정지": {"aihand": "다섯 손가락 펴기 + 정면", "picar": "정지 + 양쪽 적색 LED 점등"},
    "서행": {"aihand": "검지 + 중지 펴기 + 정면", "picar": "감속 주행 + 양쪽 황색 LED 점멸"},
    "좌회전_유도": {"aihand": "엄지 + 검지 펴기", "picar": "좌회전 주행 + 좌측 황색 LED 점멸"},
    "우회전_유도": {"aihand": "엄지 + 소지 펴기 (2026-09-20 변경: 약지→소지)",
                "picar": "우회전 주행 + 우측 황색 LED 점멸"},
    # picar LED는 "번갈아 점멸"을 채택하지 않고 전부 동시 점멸로 확정(2026-09-27), 2초 뒤 picar가 자동 소등한다
    # (2026-09-28, 13_picar_하드웨어_검증리포트 §5 #8).
    "확인_완료": {"aihand": "다섯 손가락 접기(주먹) + 정면", "picar": "정지 + 적색·황색 LED 전부 동시 점멸"},
    "후진": {"aihand": "검지만 펴기", "picar": "후진 주행"},
    "주의": {"aihand": "소지(새끼손가락)만 펴기", "picar": "정지 + 양쪽 황색 LED 점멸"},
}

# target_signal -> picar_command.schema.json 페이로드. 02_설계문서.md §4 기준.
# motor.speed는 2026-09-23 바닥 주행 테스트로 확정(13_picar_하드웨어_검증리포트.md §4.5):
# 서행 20, 좌/우회전·후진 40. 60은 "너무 빠름"으로 기각, picar 서비스가 50 초과를 잘라내지만
# (응답 motor.speed_capped_from) 안전망일 뿐이므로 처음부터 이 값을 보낸다.
PICAR_COMMANDS = {
    "정지": {"command": "stop", "motor": {"action": "stop", "speed": 0},
            "led": {"red": "on", "yellow_left": "off", "yellow_right": "off"}},
    "서행": {"command": "slow", "motor": {"action": "forward", "speed": 20},
            "led": {"red": "off", "yellow_left": "blink", "yellow_right": "blink"}},
    "좌회전_유도": {"command": "turn_left", "motor": {"action": "left", "speed": 40},
                "led": {"red": "off", "yellow_left": "blink", "yellow_right": "off"}},
    "우회전_유도": {"command": "turn_right", "motor": {"action": "right", "speed": 40},
                "led": {"red": "off", "yellow_left": "off", "yellow_right": "blink"}},
    "확인_완료": {"command": "complete", "motor": {"action": "stop", "speed": 0},
              "led": {"red": "blink", "yellow_left": "blink", "yellow_right": "blink"}},
    "후진": {"command": "reverse", "motor": {"action": "backward", "speed": 40},
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

# SC-03b 안내 문구 (03_인터페이스계약서 §4, 2026-09-22 추가: below_tau/out_of_distribution 구분)
OUTCOME_MESSAGES = {
    "wrong": "다시 시도하세요",
    "timeout": "시간이 초과됐습니다 — 다시 시도하세요",
    "below_tau": "조금 더 정확히 해주세요",
    "out_of_distribution": "다른 수신호를 하고 계세요",
}

# 장치 본문 status 중 성공으로 치는 값 (03 §5-5). mocked는 성공이되 CSV `mocked` 열로 표시한다.
OK_STATUSES = ("ok", "mocked")

# 시행 로그 열 (스펙 §7.2). 앞 17열 = 데모 스크립트 RECORD_FIELDS와 같은 이름·순서, 뒤는 web에만 있는 값.
TRIAL_FIELDS = (
    "time", "signal", "attempt", "outcome", "predicted", "match_score", "confidence",
    "vision_latency_ms", "demo_ok", "demo_ms", "observe_ms", "listen_ms",
    "picar_ok", "picar_ms", "microbit_ok", "microbit_ms", "feedback_ms",
    "aihand_ok", "aihand_ms", "feedback_done_ms", "aihand_status", "microbit_status",
    "picar_status", "picar_led_ok", "mocked", "subject",
    "target_score",     # 2026-09-30 — 학습자 화면의 일치율(목표 수신호 확률 × 100). match_score 열은 vision 원값 그대로
)

_lock = threading.Lock()
_confirm_lock = threading.Lock()   # 확인 버튼 연타 — vision /reset이 끝나기 전의 두 번째 입력을 막는다
_csv_lock = threading.Lock()
_session: dict = {}
_generation = itertools.count(1)   # 세션 번호 — 재시작 뒤 도착한 옛 세션의 전송 결과를 버리는 데 쓴다


def _fresh_session() -> dict:
    return {
        "state": "landing",
        "phase": "demo",           # SC-03 하위 단계: "demo"(시범·판정 멈춤) | "judging"(판정 중) — 스펙 §4.1
        "curriculum_index": 0,
        "last_result": None,       # {"outcome", "predicted_class", "match_score", "confidence", "message", ...}
        "_last_dispatched": None,  # (idx, "reject", reason) — 같은 안내 문구를 매 폴링 다시 쓰지 않게
        "_gen": next(_generation),
        "wrong_cls": None,         # 오답 1초 유지 추적 — 지금 보이는 오답 클래스와
        "wrong_since": 0.0,        # 그 클래스가 처음 보인 시각(monotonic)
        # 이번 시도의 시각 기준점(monotonic) — 시행 로그 demo_ms·observe_ms·listen_ms (스펙 §7.2)
        "trial": {},               # t_demo, t_demo_done, demo_ok, demo_ms, t_confirm
        # micro:bit 버튼 A 기준 seq — 시범 단계에서 처음 조회한 값. None이면 다음 조회 때 기준값만 잡는다(스펙 §9)
        "button_seq_base": None,
        "last_confirm_source": None,  # 최근 확인 입력: "web"(버튼·스페이스바) | "microbit_button"
        "attempts": {},            # signal -> 현재 회차 시도 횟수
        "completed": [],           # [{"signal", "attempts", "match_score"}] 완료 순서대로
        "camera_fail_streak": 0,
        "last_dispatch": None,     # 최근 _dispatch_feedback 결과 (actuation/picar 성공 여부)
        "last_demo": None,         # 최근 시범 /command 결과
        "devices": {},             # vision/actuation/picar 최근 /health 스냅샷
        "live_judgment": None,     # 매 폴링 갱신되는 실시간 match_score (SC-03 진행 표시용)
        "certificate_issued_at": None,
        # 회원 (2026-09-29, backend/members.py) — /api/start 때 로그인해 있던 학습자로 고정한다.
        # 도중에 로그아웃·다른 사람 로그인이 있어도 이 회차 기록은 시작한 사람에게 저장된다.
        "member": None,
        "started_at": None,        # ISO 8601 — 회원 결과 저장용
    }


_session = _fresh_session()


def _current_target_signal() -> "str | None":
    idx = _session["curriculum_index"]
    return CURRICULUM[idx] if idx < len(CURRICULUM) else None


def _target_score(judgment: dict, target_signal: "str | None") -> int:
    """학습자 화면의 일치율 = 분류기가 본 **목표 수신호의 확률 × 100** (2026-09-30 이동혁).

    판정(confidence·τ)에 쓰는 바로 그 값이라, 목표를 제대로 하면 높고(τ 0.75 → 75점 이상이어야 정답),
    다른 손동작이면 낮다. 예전 값(vision `match_score` = 예측 클래스 템플릿과의 코사인)은 7종을 가르는 값이
    아니어서(주의↔우회전 대표 손끼리 0.958), 오답인데 85%·정답인데 55%가 나왔다.
    vision이 `class_probabilities`를 주지 않으면(구버전·손 미검출·소속 게이트 차단) vision `match_score`를 쓴다."""
    probs = judgment.get("class_probabilities")
    if isinstance(probs, dict) and target_signal in probs:
        try:
            return int(round(max(0.0, min(1.0, float(probs[target_signal]))) * 100))
        except (TypeError, ValueError):
            pass
    try:
        return int(judgment.get("match_score", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _recommended_retry_count(match_score: int) -> int:
    """권장 재도전 횟수(SC-03b) — 09_화면목록.md가 표시 항목으로 요구하나 산식은 어느 문서에도
    정의돼 있지 않다. match_score 구간별 잠정치(TBD)이며 실측 후 팀 확정 필요."""
    if match_score >= 70:
        return 1
    if match_score >= 40:
        return 2
    return 3


def _body_status(body) -> "str | None":
    """응답 본문의 결과 표기 — `ok`, `timeout`, `error:write_failed`, `partial:i2c_failed` 꼴 (스펙 §7.2).
    본문에 status가 없으면 None(판정 근거가 없으므로 HTTP 층 결과를 따른다)."""
    if not isinstance(body, dict) or "status" not in body:
        return None
    status = str(body["status"])
    if status in OK_STATUSES:
        return status
    motor = body.get("motor") if isinstance(body.get("motor"), dict) else {}
    reason = body.get("reason") or motor.get("reason")
    return f"{status}:{reason}" if reason else status


def _is_mocked(body) -> bool:
    if not isinstance(body, dict):
        return False
    led = body.get("led") if isinstance(body.get("led"), dict) else {}
    parts = [body, body.get("motor"), *led.values()]
    return any(isinstance(p, dict) and p.get("status") == "mocked" for p in parts)


def _led_ok(body) -> "bool | str":
    """picar LED 채널이 전부 ok/mocked인지 — LED 실패는 최상위 status에 반영되지 않는다(03 §5-2)."""
    led = body.get("led") if isinstance(body, dict) else None
    if not isinstance(led, dict):
        return ""
    return all(isinstance(v, dict) and v.get("status") in OK_STATUSES for v in led.values())


def _post_with_retry(url: str, json: dict, timeout_s: float, *, retry_read_timeout: bool = True) -> dict:
    """실패해도 예외를 삼키고 계속 진행하되, 결과는 호출부에 돌려준다
    (03_인터페이스계약서 §7 — 장치 실패가 학습 흐름을 막지 않는 정책은 유지).

    판정 기준은 03 §5-5 (web 할 일 ③):
    - 연결 실패·4xx/5xx → 1회 재시도 (요청이 장치에 가지 않았거나 서버가 처리하지 못함).
    - 읽기(쓰기) 타임아웃 → `retry_read_timeout=False`면 재시도하지 않는다. 요청이 이미 갔을 수 있어서,
      /command·/picar를 다시 보내면 AI Hand·picar가 두 번 움직인다(web 1.5초 < actuation ACK 대기 2.0초).
    - HTTP 200이어도 본문 status가 ok/mocked가 아니면(`timeout`·`error`·`partial`) 실패. **재시도하지 않는다.**
    - 본문에 status가 없으면 HTTP 결과대로 성공.

    반환: {"ok", "status"(결과 표기), "ms"(재시도 포함 소요), "body" | "error", "mocked", "_t0", "_t1"}.
    `_t0`·`_t1`은 시행 로그용 monotonic 시각이라 /api/state에는 내보내지 않는다(`_public`)."""
    t0 = time.monotonic()
    last_error = None
    for _ in range(2):
        try:
            response = httpx.post(url, json=json, timeout=timeout_s)
        except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            last_error = type(exc).__name__
            if not retry_read_timeout:
                break
            continue
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
            continue

        # httpx.post()는 4xx/5xx에 예외를 던지지 않으므로 status_code를 직접 확인한다 — 이전 구현은
        # 반환값을 버려 서버 오류를 성공으로 셌다(2026-09-21 web_picar_통신_신뢰성_개선안.md §1-1).
        if response.status_code >= 400:
            last_error = f"http_{response.status_code}"
            continue

        try:
            body = response.json()
        except ValueError:
            body = None
        t1 = time.monotonic()
        status = _body_status(body)
        ok = status is None or status in OK_STATUSES
        result = {"ok": ok, "status": status or "ok", "ms": round((t1 - t0) * 1000), "body": body,
                  "mocked": _is_mocked(body), "_t0": t0, "_t1": t1}
        if not ok:
            result["error"] = status
        return result

    t1 = time.monotonic()
    return {"ok": False, "status": last_error, "error": last_error, "ms": round((t1 - t0) * 1000),
            "mocked": False, "_t0": t0, "_t1": t1}


def _public(result: "dict | None") -> "dict | None":
    return None if result is None else {k: v for k, v in result.items() if not k.startswith("_")}


def _aihand_payload(command: str, target_signal: str) -> dict:
    return {"command": command, "target_signal": target_signal, "servo_angles": _PLACEHOLDER_SERVO_ANGLES}


def _dispatch_feedback(target_signal: str, outcome: str, judgment: dict, *, resend_demo: bool = True) -> dict:
    """판정 뒤 물리 피드백. 순서 /picar → /result → /command → /progress (스펙 §7.3).

    `resend_demo`: 오답일 때만 의미가 있다. True(기본)면 이 /command가 곧 다음 시도의 재시범이다(같은 수신호).
    False면 재시도 상한을 넘겨 다음 수신호로 넘어가는 경우라 여기서는 재시범을 보내지 않는다 — 다음 수신호의
    시범은 호출부가 `_send_demo`로 따로 보낸다(정답 뒤 다음 시범과 같은 경로, 이중 전송 방지)."""
    is_correct = outcome == "correct"
    match_score = _target_score(judgment, target_signal)
    results = {}

    if is_correct:
        picar_command = PICAR_COMMANDS[target_signal]
        results["picar"] = _post_with_retry(f"{PICAR_URL}/picar", {
            "target_signal": target_signal, **picar_command,
        }, PICAR_TIMEOUT_MS / 1000, retry_read_timeout=False)

    results["result"] = _post_with_retry(f"{ACTUATION_URL}/result", {
        "is_correct": is_correct, "match_score": match_score,
    }, ACTUATION_FEEDBACK_TIMEOUT_S)
    if is_correct or resend_demo:
        # 정답: 정답 자세 / 오답(재시도 여지 있음): 재시범 — 오답의 이 /command가 곧 다음 시도의 시범이다.
        results["aihand"] = _post_with_retry(
            f"{ACTUATION_URL}/command", _aihand_payload("correct_pose" if is_correct else "demo", target_signal),
            ACTUATION_COMMAND_TIMEOUT_S, retry_read_timeout=False)
    results["progress"] = _post_with_retry(f"{ACTUATION_URL}/progress", {
        "current": _session["curriculum_index"] + 1, "total": len(CURRICULUM),
    }, ACTUATION_FEEDBACK_TIMEOUT_S)
    return results


def _record_demo(result: dict) -> None:
    """시범 /command 결과를 이번 시도의 기준점으로 남긴다 (_lock 안에서 부른다)."""
    _session["trial"].update(t_demo=result["_t0"], t_demo_done=result["_t1"],
                             demo_ok=result["ok"], demo_ms=result["ms"])
    _session["last_demo"] = _public(result)


def _send_demo(target_signal: str, gen: int) -> None:
    """수신호 시작 시범 — `/command`(demo)만 보낸다. /result·/progress·picar는 보내지 않는다 (스펙 §4.1)."""
    with _lock:
        if _session.get("_gen") != gen:
            return
        _session["trial"] = {}
    result = _post_with_retry(f"{ACTUATION_URL}/command", _aihand_payload("demo", target_signal),
                              ACTUATION_COMMAND_TIMEOUT_S, retry_read_timeout=False)
    with _lock:
        if _session.get("_gen") == gen:       # 그사이 재시작됐으면 옛 결과는 버린다
            _record_demo(result)
            _session["button_seq_base"] = None  # 시범 도중 누른 버튼 A는 세지 않는다 — 시범이 끝난 뒤로 기준을 다시 잡는다


def _ms(start: "float | None", end: "float | None"):
    return "" if start is None or end is None else round((end - start) * 1000)


def _trial_row(*, when: datetime, t_dec: float, target_signal: str, attempt: int, outcome: str,
               judgment: dict, trial: dict, dispatch: dict) -> dict:
    """시행 로그 1행 (스펙 §7.2). 장치 지연은 전부 판정 확정 시각 t_dec 기준."""
    row = dict.fromkeys(TRIAL_FIELDS, "")
    t_done, t_confirm = trial.get("t_demo_done"), trial.get("t_confirm")
    observed = t_done is not None and t_confirm is not None and t_confirm >= t_done
    row.update(
        time=when.isoformat(timespec="milliseconds"), signal=target_signal, attempt=attempt,
        outcome=outcome, predicted=judgment.get("predicted_class", ""),
        match_score=judgment.get("match_score", ""), confidence=judgment.get("confidence", ""),
        vision_latency_ms=judgment.get("latency_ms", ""),
        demo_ok=trial.get("demo_ok", ""), demo_ms=trial.get("demo_ms", ""),
        # 시범 응답 전에 확인을 눌렀으면 "본 시간"은 정의되지 않는다 — 음수 대신 빈 값
        observe_ms=_ms(t_done, t_confirm) if observed else "",
        listen_ms=_ms(t_confirm, t_dec),
        # 대상자: LOG_SUBJECT(외부인 KPI 시행용 ID)가 우선, 없으면 로그인한 회원코드 (supabase/README.md §5)
        subject=os.getenv("LOG_SUBJECT") or (_session.get("member") or {}).get("member_code") or "",
        target_score=_target_score(judgment, target_signal),
    )
    for key, col in (("picar", "picar"), ("result", "microbit"), ("aihand", "aihand")):
        r = dispatch.get(key)
        if r:
            row[f"{col}_ok"] = r["ok"]
            row[f"{col}_ms"] = _ms(t_dec, r["_t1"])
            row[f"{col}_status"] = r["status"]
    if dispatch.get("picar"):
        row["picar_led_ok"] = _led_ok(dispatch["picar"].get("body"))

    picar_ms, microbit_ms, aihand_ms = (row[c] if row[c] != "" else None
                                        for c in ("picar_ms", "microbit_ms", "aihand_ms"))
    starts = [v for v in (picar_ms, microbit_ms) if v is not None]
    row["feedback_ms"] = max(starts) if starts else ""       # 반응 시작 기준 (데모 CSV와 같음)
    done = [v for v in (aihand_ms, None if microbit_ms is None else microbit_ms + 1000) if v is not None]
    row["feedback_done_ms"] = max(done) if done else ""     # 완료 기준 (LED O/X 1초 포함, picar 주행 제외)
    row["mocked"] = any(r.get("mocked") for r in dispatch.values())
    return row


def _write_trial_row(row: dict) -> None:
    """한 행 쓰고 바로 닫는다 — 시연 중 web이 죽어도 그때까지의 행은 남는다. 실패해도 학습 흐름은 계속."""
    path = Path(TRIAL_LOG_DIR) / _TRIAL_LOG_NAME
    try:
        with _csv_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            new = not path.exists()
            # utf-8-sig는 파일을 열 때마다 첫 쓰기에 BOM을 붙이므로 새 파일일 때만 쓴다
            with path.open("w" if new else "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=TRIAL_FIELDS)
                if new:
                    writer.writeheader()
                writer.writerow(row)
    except OSError:
        logger.exception("시행 로그를 쓰지 못했습니다: %s", path)


def _poll_once(vision_client: httpx.Client) -> None:
    with _lock:
        state = _session["state"]
        if state not in ("training", "camera_fail"):
            return
        judging = _session["phase"] == "judging"
        target_signal = _current_target_signal()
        gen = _session["_gen"]
    # 시범 단계 — 판정도, 손 미검출 집계도 하지 않는다 (스펙 §4.1). micro:bit 버튼 A만 본다 (스펙 §9)
    if not judging:
        _poll_button()
        return
    # SC-04 — micro:bit 버튼 A를 재시도 입력으로 받는다. 손이 다시 보이면 아래 판정 경로가 자동 복귀시킨다.
    if state == "camera_fail":
        _poll_retry_button()
        with _lock:
            if _session["state"] != "camera_fail":
                return                       # 방금 재시도로 시범 단계가 됐다
    if target_signal is None:
        return

    try:
        judgment = vision_client.get(f"{VISION_URL}/latest").json()
    except (httpx.HTTPError, ValueError):   # ValueError = JSON이 아닌 응답 — 전에는 폴링 스레드가 죽었다
        return
    if not isinstance(judgment, dict):
        return

    is_reject = judgment.get("is_reject", True)
    reason = judgment.get("reason")
    predicted = judgment.get("predicted_class")

    # 확정된 정답/오답 이벤트와 별개로, SC-03의 실시간 match_score 진행 표시를 위해 매 폴링마다 갱신한다.
    with _lock:
        _session["live_judgment"] = {
            "predicted_class": predicted,
            "confidence": judgment.get("confidence", 0),
            "match_score": _target_score(judgment, target_signal),     # 목표 수신호 기준 (화면 일치율)
            "is_reject": is_reject,
            "reason": reason,
        }

    if is_reject and reason in CAMERA_FAIL_REASONS:
        with _lock:
            # vision을 조회하는 사이 재시도·확인으로 시범 단계가 됐으면 세지 않는다 — 시범 단계를 SC-04로 되돌리면 갇힌다
            if _session["_gen"] != gen or _session["phase"] != "judging":
                return
            _session["wrong_cls"] = None   # 손을 내렸다 다시 들면 오답 유지 시간을 새로 센다
            _session["camera_fail_streak"] += 1
            if _session["camera_fail_streak"] >= CAMERA_FAIL_STREAK_THRESHOLD and _session["state"] != "camera_fail":
                _session["state"] = "camera_fail"
                _session["button_seq_base"] = None   # 판정 중에 누른 버튼 A가 재시도로 새지 않게 여기서 기준을 새로 잡는다
        return

    # 손이 다시 보이면 미검출 스트릭을 초기화하고, SC-04였다면 SC-03으로 자동 복귀한다.
    with _lock:
        if _session["_gen"] != gen or _session["phase"] != "judging":
            return
        _session["camera_fail_streak"] = 0
        if _session["state"] == "camera_fail":
            _session["state"] = "training"
            _session["trial"]["t_judge_start"] = time.monotonic()   # SC-04에 있던 시간은 제한시간에서 뺀다
        elif _session["state"] != "training":
            return
        judge_started = _session["trial"].get("t_judge_start")

    # 제한시간을 넘겼으면 이번 판정은 timeout으로 끝낸다 — 단, 바로 이 프레임이 정답이면 정답이 우선
    correct_now = not is_reject and predicted == target_signal
    timed_out = judge_started is not None and time.monotonic() - judge_started >= JUDGING_TIMEOUT_S

    if timed_out and not correct_now:
        outcome = "timeout"
    elif is_reject and reason in SILENT_REASONS:
        return  # 과도기 상태(모델 로딩/N프레임 누적 중 등) — 오버레이 없이 대기
    elif is_reject and reason in HOLD_REASONS:
        # 화면 안내만 — 물리 피드백·시도 횟수·시행 로그 없음, 판정 단계 유지 (스펙 §5, 이동혁 결정)
        match_score = _target_score(judgment, target_signal)
        with _lock:
            key = (_session["curriculum_index"], "reject", reason)
            if _session["_last_dispatched"] == key:
                return  # 같은 안내가 계속 들어오는 동안 다시 쓰지 않는다
            _session["_last_dispatched"] = key
            _session["last_result"] = {
                "signal": target_signal, "outcome": reason, "predicted_class": predicted,
                "match_score": match_score, "confidence": judgment.get("confidence", 0),
                "attempt": _session["attempts"].get(target_signal, 0),
                "message": OUTCOME_MESSAGES.get(reason),
                "recommended_retry": _recommended_retry_count(match_score),
            }
        return
    elif is_reject or not predicted or predicted == NEGATIVE_LABEL:
        return
    elif predicted == target_signal:
        outcome = "correct"                  # 정답은 즉시 확정
    else:
        now = time.monotonic()
        with _lock:
            if _session["wrong_cls"] != predicted:     # 새 오답 클래스 — 여기서부터 센다
                _session["wrong_cls"], _session["wrong_since"] = predicted, now
                return
            if now - _session["wrong_since"] < WRONG_CONFIRM_S:
                return                                 # 아직 손을 올리는 도중의 과도 자세일 수 있다
        outcome = "wrong"

    t_dec, when = time.monotonic(), datetime.now()
    with _lock:
        if _session.get("_gen") != gen or _session["phase"] != "judging":
            return
        _session["wrong_cls"] = None
        _session["attempts"][target_signal] = _session["attempts"].get(target_signal, 0) + 1
        attempt_no = _session["attempts"][target_signal]
        trial = dict(_session["trial"])
        given_up = outcome != "correct" and attempt_no >= MAX_ATTEMPTS_PER_SIGNAL   # 오답·timeout 모두 시도로 센다

    dispatch_results = _dispatch_feedback(target_signal, outcome, judgment, resend_demo=not given_up)

    match_score = _target_score(judgment, target_signal)
    next_signal = None
    finished = False
    with _lock:
        if _session.get("_gen") != gen:
            return                            # 전송하는 사이 재시작됨 — 새 세션을 건드리지 않는다
        _session["last_dispatch"] = {k: _public(v) for k, v in dispatch_results.items()}
        _session["last_result"] = {
            "signal": target_signal,  # 정답 시 curriculum_index가 이미 다음으로 넘어가므로 별도 보관
            "outcome": outcome,
            "predicted_class": predicted,
            "match_score": match_score,
            "confidence": judgment.get("confidence", 0),
            "attempt": attempt_no,
            "message": OUTCOME_MESSAGES.get(outcome),
            "recommended_retry": _recommended_retry_count(match_score),
            "given_up": given_up,
        }
        _session["_last_dispatched"] = None
        # 정답이면 다음 수신호 시범, 오답이면 방금 보낸 재시범을 볼 차례 — 확인 버튼을 기다린다
        _session["phase"] = "demo"
        _session["trial"] = {}
        _session["button_seq_base"] = None   # 판정 중에 누른 버튼 A가 확인으로 새지 않게 기준을 다시 잡는다
        if outcome == "correct" or given_up:
            _session["completed"].append({
                "signal": target_signal, "attempts": attempt_no, "match_score": match_score,
                # 마지막 시도가 어떻게 끝났는지 남긴다 (18_DB설계서 §2-3).
                #   given_up 하나로는 불합격 사유가 "3회 오답"인지 "시간 초과"인지 구분되지 않고,
                #   학습자가 실제로 무슨 수신호를 한 것으로 읽혔는지도 사라진다.
                #   좌회전_유도↔후진·우회전_유도↔주의는 엄지 하나로 갈려(10_PRD §3.2) 이 값이 있어야
                #   "무엇을 어떻게 틀렸는가"를 교육 결과로 설명할 수 있다.
                "last_outcome": outcome,        # correct · wrong · timeout
                "last_predicted": predicted,    # 마지막 시도에 인식된 수신호 (없으면 None)
                **({"given_up": True} if given_up else {}),
            })
            _session["curriculum_index"] += 1
            if _session["curriculum_index"] >= len(CURRICULUM):
                _session["state"] = "summary"
                finished = True
            else:
                next_signal = _current_target_signal()
        else:
            _record_demo(dispatch_results["aihand"])

    _write_trial_row(_trial_row(when=when, t_dec=t_dec, target_signal=target_signal, attempt=attempt_no,
                                outcome=outcome, judgment=judgment, trial=trial, dispatch=dispatch_results))

    if finished:
        _save_member_results(gen)

    if next_signal is not None:
        try:
            vision_client.post(f"{VISION_URL}/reset")
        except httpx.HTTPError:
            pass
        # 정답 자세(/command correct_pose)가 끝난 뒤에 보낸다 — /command는 손 동작 후 회신하므로 순서가 보장된다
        _send_demo(next_signal, gen)


def _save_member_results(gen: int) -> None:
    """7종을 끝낸 회차를 회원 기록에 저장한다 (SC-05 "결과 저장" — 예전 CSV 내려받기를 대신한다).

    Supabase 호출은 최대 수 초가 걸릴 수 있어 폴링 스레드를 막지 않게 따로 보낸다. 오프라인이면 members가
    대기열에 넣고 나중에 다시 보낸다. 저장 상태는 /api/state `result_save`로 화면에 나간다."""
    with _lock:
        if _session.get("_gen") != gen:
            return
        member = _session.get("member")
        payload = {
            "started_at": _session.get("started_at"),
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "results": [
                {"order_no": i + 1, "signal": c["signal"], "attempts": c["attempts"],
                 "match_score": c["match_score"], "given_up": bool(c.get("given_up")),
                 "last_outcome": c.get("last_outcome"), "last_predicted": c.get("last_predicted")}
                for i, c in enumerate(_session["completed"])
            ],
        }
    threading.Thread(target=members.save_session_results, args=(payload, member), daemon=True).start()


def _poll_loop() -> None:
    with httpx.Client(timeout=VISION_TIMEOUT_S) as vision_client:
        while True:
            try:
                _poll_once(vision_client)
            except Exception:  # noqa: BLE001 — 예상 못 한 오류로 폴링 스레드가 죽으면 교육이 멈춘다
                logger.exception("판정 폴링 중 오류 — 다음 폴링을 계속합니다")
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
        if not isinstance(body, dict):
            status[name] = {"status": "unknown"}
            continue

        entry = {"status": body.get("status", "unknown")}
        if name == "vision":
            # 판정 규칙(τ·N프레임) — 화면 일치율 막대의 기준선·수료증 문구가 이 값을 쓴다(2026-10-01, 하드코딩 75 대체)
            entry["tau"] = body.get("tau")
            entry["n_frames"] = body.get("n_frames")
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
            try:
                devices = _check_devices(client)
                with _lock:
                    _session["devices"] = devices
            except Exception:  # noqa: BLE001 — 스레드가 죽으면 장치 상태가 마지막 값("정상")에 멈춘다
                logger.exception("장치 상태 확인 중 오류 — 다음 확인을 계속합니다")
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
            "phase": _session["phase"],    # SC-03 하위 단계 — "demo"면 예시 사진 + 확인 버튼 (스펙 §4.1)
            "target_signal": target_signal,
            "signal_info": CURRICULUM_INFO.get(target_signal) if target_signal else None,
            "curriculum": [
                {"signal": s, **CURRICULUM_INFO[s]} for s in CURRICULUM
            ],
            "progress": {"current": _session["curriculum_index"] + 1, "total": len(CURRICULUM)},
            "last_result": _session["last_result"],
            "live_judgment": _session["live_judgment"],
            "attempts": _session["attempts"].get(target_signal, 0) if target_signal else 0,
            "max_attempts": MAX_ATTEMPTS_PER_SIGNAL,   # 화면 "시도 n / 3" 표시 — 실물에 새 코드가 올라갔는지도 이 키로 확인
            "last_dispatch": _session["last_dispatch"],
            "last_demo": _session["last_demo"],
            "last_confirm_source": _session["last_confirm_source"],
            "devices": _session["devices"],
            "completed": _session["completed"],
            "certificate_issued_at": _session["certificate_issued_at"],
            # 회원 (2026-09-29) — 이 회차의 학습자와 회원 기록 저장 상태(saved·queued·saved_local·failed)
            "member": members._public(_session.get("member")),
            "result_save": _store_status_safe(),
            # vision /health의 τ·N프레임 (아직 못 받았으면 None — 화면이 기본값 0.75·3을 쓴다)
            "judge_rule": {k: (_session["devices"].get("vision") or {}).get(k) for k in ("tau", "n_frames")},
        }


def _store_status_safe() -> dict:
    """회원 저장 상태 — 여기서 난 오류가 /api/state 전체를 500으로 만들어 교육 화면을 멈추면 안 된다."""
    try:
        return members.store_status()
    except Exception:  # noqa: BLE001
        logger.exception("회원 저장 상태를 읽지 못했습니다 — 화면에는 상태 없이 보냅니다")
        return {"backend": "unknown", "pending": None, "last_save": None}


@router.post("/start")
def start():
    """SC-01/02 -> SC-03: 커리큘럼을 처음부터 시작 (세션 이어하기 없음, 2026-09-18 결정)."""
    with _lock:
        devices = _session["devices"]  # 장치 상태는 세션 리셋과 무관하게 유지
        _session.clear()
        _session.update(_fresh_session())
        _session["state"] = "training"
        _session["devices"] = devices
        _session["member"] = members.current_member()     # 이 회차의 학습자로 고정 (게스트·미로그인이면 게스트/None)
        _session["started_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        gen = _session["_gen"]
    members.reset_last_save()
    # 첫 수신호 시범 — /command는 손 동작 뒤 회신(최대 1.5초 × 2)이라 응답을 늦추지 않게 스레드로 보낸다 (스펙 §4.1)
    threading.Thread(target=_send_demo, args=(CURRICULUM[0], gen), daemon=True).start()
    return {"state": "training", "phase": "demo", "target_signal": CURRICULUM[0]}


def _confirm(source: str) -> dict:
    """확인 입력 처리 — 화면 확인 버튼·스페이스바(`POST /api/confirm`)와 micro:bit 버튼 A가 같은 경로를 쓴다 (스펙 §4.1·§9).

    `phase == "demo"`일 때만 받는다(판정 중 연타·두 입력의 동시 도착은 무시). vision `/reset`으로 시범 동안 쌓인 N프레임
    연속판정 누적을 버린 뒤 판정 단계로 넘어간다 — 그래야 시범 전에 들고 있던 손모양이 곧바로 판정되지 않는다."""
    with _confirm_lock:
        with _lock:
            if _session["state"] != "training" or _session["phase"] != "demo":
                return {"status": "ignored", "state": _session["state"], "phase": _session["phase"]}
            gen = _session["_gen"]
        # /reset이 실패해도 학습은 막지 않는다 — 직전 누적이 남아 있을 수 있다는 것만 기록한다
        reset = _post_with_retry(f"{VISION_URL}/reset", {}, VISION_TIMEOUT_S)
        with _lock:
            if _session["_gen"] != gen or _session["phase"] != "demo":
                return {"status": "ignored", "state": _session["state"], "phase": _session["phase"]}
            _session["phase"] = "judging"
            _session["trial"]["t_confirm"] = time.monotonic()
            _session["trial"]["t_judge_start"] = _session["trial"]["t_confirm"]   # JUDGING_TIMEOUT_S 기준점
            _session["_last_dispatched"] = None
            _session["wrong_cls"] = None
            _session["camera_fail_streak"] = 0
            _session["button_seq_base"] = None
            _session["last_confirm_source"] = source
        return {"status": "ok", "phase": "judging", "source": source, "vision_reset": _public(reset)}


def _read_button_seq() -> "int | None":
    """actuation `GET /button`의 누른 횟수 `seq`. 버튼은 보조 입력이라 조회 실패는 None으로 조용히 넘긴다."""
    try:
        response = httpx.get(f"{ACTUATION_URL}/button", timeout=BUTTON_TIMEOUT_S)
        if response.status_code >= 400:
            return None
        return int(response.json()["seq"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def _poll_button() -> None:
    """시범 단계에서 micro:bit 버튼 A(actuation `GET /button`)를 확인 입력으로 받는다 (스펙 §9, 03 §5-3).

    actuation이 누른 횟수 `seq`를 세고 web이 폴링한다(pull). 시범 단계에서 처음 읽은 값을 기준으로 적고,
    그보다 커지면 `_confirm`을 부른다. 기준값은 시범이 끝날 때·판정이 확정될 때 비워 두므로 시범 도중·판정 중에
    누른 입력은 확인으로 새지 않는다. seq가 기준보다 작으면 actuation이 재시작된 것이라 기준만 다시 잡는다.
    버튼은 보조 입력이다 — 조회 실패(연결 실패·타임아웃·이상한 응답)는 조용히 넘긴다(BLE가 끊긴 동안 누른 입력은
    actuation에도 올라오지 않으므로 화면 확인 버튼·스페이스바를 항상 함께 둔다, 03 §7).

    🔴 2026-09-29 실물에서 발견: `start()`는 첫 시범을 **백그라운드 스레드**로 보낸다(응답까지 실측 약 0.8초).
    그동안 이 폴링(0.2초 간격)이 먼저 돌면 `button_seq_base`가 시범이 끝나기도 전에 잡혀서, 시범 도중 누른
    입력이 시범이 끝나기 전에 확인으로 확정돼 버렸다(오답 재시범·정답 후 다음 시범은 `_send_demo`가 폴링 루프
    안에서 동기로 돌아 같은 문제가 없다 — 오직 세션 시작 직후만 해당). → 이번 시범이 실제로 응답할 때까지는
    아예 조회하지 않는다."""
    if not BUTTON_CONFIRM_ENABLED:
        return
    with _lock:
        if _session["state"] != "training" or _session["phase"] != "demo":
            return
        if _session["trial"].get("t_demo_done") is None:
            return
        gen, base = _session["_gen"], _session["button_seq_base"]
    seq = _read_button_seq()
    if seq is None:
        return
    with _lock:
        # 조회하는 사이 재시작·단계 전환·기준 재설정이 있었으면 이번 값은 버린다
        if _session["_gen"] != gen or _session["phase"] != "demo" or _session["button_seq_base"] != base:
            return
        if base is None or seq < base:
            _session["button_seq_base"] = seq
            return
        if seq == base:
            return
    logger.info("micro:bit 버튼 A 확인 (seq %d → %d)", base, seq)
    _confirm("microbit_button")


@router.post("/confirm")
def confirm():
    """확인 버튼(스페이스바) — 시범을 본 학습자가 판정을 시작한다 (스펙 §4.1). 처리는 `_confirm`."""
    return _confirm("web")


def _camera_retry(source: str) -> dict:
    """SC-04(camera_fail) 재시도 — 화면 "재시도" 버튼·Space(`POST /api/camera_retry`)와 micro:bit 버튼 A가 같은 경로를 쓴다.

    판정 단계가 아니라 **시범 단계**로 되돌리고 현재 수신호를 AI Hand가 다시 보여 준다. 판정 단계로 바로 돌리면
    학습자가 버튼을 누르느라 손이 카메라 밖에 있어 약 3초 뒤 다시 SC-04로 튕겨 나갔다(2026-09-29 ⑥ 재시험).
    시범 단계에서는 손 미검출을 세지 않으므로, 학습자가 준비된 뒤 확인을 누르면 판정이 새로 시작된다.
    재시도는 시도 횟수에 넣지 않는다."""
    with _lock:
        if _session["state"] != "camera_fail":
            return {"status": "ignored", "state": _session["state"], "phase": _session["phase"]}
        target_signal = _current_target_signal()
        gen = _session["_gen"]
        _session["state"] = "training"
        _session["phase"] = "demo"
        _session["camera_fail_streak"] = 0
        _session["wrong_cls"] = None
        _session["_last_dispatched"] = None
        _session["trial"] = {}
        _session["button_seq_base"] = None
    logger.info("SC-04 재시도 (%s) — 시범 단계로 복귀", source)
    if target_signal is not None:
        # /command는 손 동작 뒤 회신(약 0.8초)이라 요청·폴링을 붙잡지 않게 스레드로 보낸다 (start()와 같은 방식).
        # 버튼 A는 `t_demo_done` 게이트가 있어 시범이 끝나기 전 입력이 확인으로 새지 않는다.
        threading.Thread(target=_send_demo, args=(target_signal, gen), daemon=True).start()
    return {"status": "ok", "state": "training", "phase": "demo", "source": source}


def _poll_retry_button() -> None:
    """SC-04에서 micro:bit 버튼 A를 재시도 입력으로 받는다. 기준값 처리는 `_poll_button`과 같다 —
    SC-04에 들어온 뒤 처음 읽은 seq를 기준으로 적고, 그보다 커지면 재시도한다."""
    if not BUTTON_CONFIRM_ENABLED:
        return
    with _lock:
        if _session["state"] != "camera_fail":
            return
        gen, base = _session["_gen"], _session["button_seq_base"]
    seq = _read_button_seq()
    if seq is None:
        return
    with _lock:
        if _session["_gen"] != gen or _session["state"] != "camera_fail" or _session["button_seq_base"] != base:
            return
        if base is None or seq < base:
            _session["button_seq_base"] = seq
            return
        if seq == base:
            return
    _camera_retry("microbit_button")


@router.post("/camera_retry")
def camera_retry():
    """SC-04 "재시도" 버튼·Space. 처리는 `_camera_retry`."""
    return _camera_retry("web")


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
