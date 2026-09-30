"""portal 테스트 공통 설정 — 회원 파일은 임시 폴더, Supabase 키는 지워서 실제 회원 DB에 쓰지 않는다(web conftest와 같은 원칙)."""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="safesign_portal_members_")
os.environ["MEMBER_DATA_DIR"] = _tmp
os.environ["SAFESIGN_NO_DOTENV"] = "1"          # 루트 .env(실제 Supabase 키)를 읽지 않게
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
os.environ["PORTAL_SESSION_SECRET"] = "test-secret-" + "x" * 40
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
