"""web 테스트 공통 설정.

state_machine은 판정이 확정될 때마다 시행 로그 CSV(TRIAL_LOG_DIR, 기본 services/web/logs/)에 1행을 쓴다.
테스트가 만든 가짜 판정이 실물 시행 로그 폴더에 섞이면 KPI 원본 데이터가 오염되므로, 테스트 동안에는
임시 폴더를 쓰게 한다. state_machine을 import하기 전에 환경변수를 정해야 해서 여기(conftest)에서 한다.
CSV 내용을 보는 테스트는 따로 tmp_path로 바꿔 끼운다(test_judging_timing_spec.py `log_dir`).

micro:bit 버튼 A 폴링(시범 단계마다 actuation `GET /button`)도 기본으로 끈다 — 켜 두면 시범 단계를 다루는 테스트마다
실제 `localhost:8002`로 요청이 나가 느려지고, 로컬에 actuation이 떠 있으면 결과가 흔들린다.
버튼 테스트(test_microbit_button_confirm.py)만 `BUTTON_CONFIRM_ENABLED`를 켜고 `httpx.get`을 바꿔 끼운다.

회원·결과 저장(backend/members.py)도 같다 — 로컬 회원 파일·결과 대기열은 임시 폴더에 두고, 셸에 Supabase 키가
있어도 테스트가 실제 회원 DB에 가짜 회원·결과를 쓰지 않게 키를 지운다(가짜 Supabase는 test_members.py가 끼운다).
"""
import atexit
import os
import shutil
import tempfile

_tmp_log_dir = tempfile.mkdtemp(prefix="safesign_web_trials_")
os.environ["TRIAL_LOG_DIR"] = _tmp_log_dir
os.environ["MICROBIT_BUTTON_CONFIRM"] = "0"
atexit.register(shutil.rmtree, _tmp_log_dir, ignore_errors=True)

_tmp_member_dir = tempfile.mkdtemp(prefix="safesign_web_members_")
os.environ["MEMBER_DATA_DIR"] = _tmp_member_dir
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
atexit.register(shutil.rmtree, _tmp_member_dir, ignore_errors=True)
