"""교육 상태머신 (09_화면목록_v2.md SC-01~SC-07 대응).

TODO(조은수):
- 세션별 현재 state 관리 (SC-07은 세션 이어하기 미구현 — 재접속 시 항상 "처음부터"만 지원, 2026-09-18 결정)
- vision 서비스의 GET /latest를 폴링(또는 추후 WebSocket 구독)해 judgment_result를 받아
  SC-03a(정답)/SC-03b(오답)/SC-04(인식 실패) 분기
- 정답 확정 시 actuation의 POST /command(AI Hand), POST /picar(picar), POST /result(micro:bit),
  POST /progress(micro:bit 진행 표시) 호출
- 관리자/등록 관련 상태 없음 — 수신호 등록 기능은 범위에서 제외됨 (03_인터페이스계약서_v2 §6)
"""
from fastapi import APIRouter

router = APIRouter()

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


@router.get("/state")
def get_state():
    """TODO: 세션 저장소(메모리/DB) 연동. 현재는 목업으로 초기 상태만 반환."""
    return {"state": "landing"}
