"""교육 상태머신 (09_화면목록_v1.md SC-01~SC-10 대응).

TODO(조은수):
- 세션별 현재 state 관리 (SC-08 이어하기 여부는 팀 확정 후 구현)
- /predict 결과(judgment_result)를 받아 SC-04a(정답)/SC-04b(오답)/SC-05(인식 실패) 분기
- 분야 선택(SC-02) 결과를 vision에 컨텍스트로 전달 (landmark_frame.field_id)
"""
from fastapi import APIRouter

router = APIRouter()

# SC-01~SC-10 상태값. README.md 표와 동기화 유지.
STATES = [
    "landing",
    "field_select",
    "curriculum_confirm",
    "training",
    "camera_fail",
    "field_summary",
    "certificate",
    "resume_or_restart",
    "admin_register",
]


@router.get("/state")
def get_state():
    """TODO: 세션 저장소(메모리/DB) 연동. 현재는 목업으로 초기 상태만 반환."""
    return {"state": "landing"}
