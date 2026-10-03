"""회사 사이트(portal) — 쿠키 로그인, CSRF 헤더, 내 정보·수료 판정, 찾기·재설정, Supabase 조회 형식."""
import json
import time
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import members

H = {"X-SafeSign-Portal": "1"}
SIGNALS = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]


@pytest.fixture(autouse=True)
def local_store():
    members.set_store(members.LocalStore())
    for lim in (members.LOGIN_LIMIT, members.FIND_LIMIT, members.RESET_LIMIT, members.VERIFY_LIMIT):
        lim._hits.clear()
        lim._locked.clear()
    yield
    members.set_store(None)


def _client():
    return TestClient(main.app)


def _signup(c, email=None, name="박사원"):
    email = email or f"{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/api/auth/signup", json={"email": email, "password": "safe1234", "name": name, "org": "A공장"}, headers=H)
    assert r.json()["status"] == "ok", r.json()
    return email, r.json()["member"]


def _record(user_id, given_up_idx=None, n=7):
    results = []
    for i, s in enumerate(SIGNALS[:n]):
        gave = i == given_up_idx
        results.append({"order_no": i + 1, "signal": s, "attempts": 3 if gave else 1, "match_score": 40 if gave else 88,
                        "given_up": gave, "passed": not gave,
                        "last_outcome": "wrong" if gave else "correct", "last_predicted": "후진" if gave else s})
    rec = {"id": str(uuid.uuid4()), "user_id": user_id, "member_code": "SS-00001",
           "started_at": "2026-09-30T10:00:00+09:00", "completed_at": "2026-09-30T10:05:00+09:00",
           "total_attempts": sum(r["attempts"] for r in results), "first_try_correct": n - (given_up_idx is not None),
           "passed_count": sum(r["passed"] for r in results), "results": results}
    members._append_jsonl("results_local.jsonl", rec)
    return rec


def test_signup_sets_session_cookie_and_me_starts_uncertified():
    c = _client()
    email, m = _signup(c)
    assert m["member_code"].startswith("SS-") and "user_id" not in m
    assert main.COOKIE in c.cookies
    s = c.get("/api/session").json()
    assert s["member"]["name"] == "박사원" and s["store"]["backend"] == "local"
    me = c.get("/api/me").json()
    assert me["status"] == "ok" and me["member"]["email"] == email
    assert me["certified"] is False and me["sessions"] == []


def test_post_without_portal_header_is_rejected():
    r = _client().post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert r.status_code == 403


def test_me_requires_valid_cookie():
    c = _client()
    assert c.get("/api/me").status_code == 401
    c.cookies.set(main.COOKIE, "forged.token")
    assert c.get("/api/me").status_code == 401
    good = main.make_token({"user_id": "u1", "member_code": "SS-00009", "name": "x"})
    raw, sig = good.split(".")
    assert main.read_token(f"{raw}.{sig[:-2]}AA") is None                         # 서명 위조
    assert main.read_token(good, now=time.time() + main.SESSION_TTL_S + 5) is None  # 만료


def test_login_logout_and_wrong_password():
    c = _client()
    email, _ = _signup(c)
    c.post("/api/auth/logout", json={}, headers=H)
    assert c.get("/api/me").status_code == 401
    assert c.post("/api/auth/login", json={"email": email, "password": "wrong999"}, headers=H).json()["reason"] == "invalid_credentials"
    r = c.post("/api/auth/login", json={"email": email, "password": "safe1234"}, headers=H)
    assert r.json()["status"] == "ok" and c.get("/api/me").status_code == 200


def test_completed_session_makes_member_certified_with_reason_fields():
    c = _client()
    _signup(c)
    uid = members.get_store().login(c.get("/api/me").json()["member"]["email"], "safe1234")["user_id"]
    _record(uid, n=4)                         # 중간에 끝난(4종) 기록 — 수료 아님
    rec = _record(uid, given_up_idx=4)        # 7종 완료, 확인_완료 불합격
    me = c.get("/api/me").json()
    assert me["certified"] is True
    full = next(s for s in me["sessions"] if s["id"] == rec["id"])
    assert full["completed"] is True and full["passed_count"] == 6 and full["all_passed"] is False
    assert full["results"][4] == {"order_no": 5, "signal": "확인_완료", "attempts": 3, "match_score": 40,
                                  "given_up": True, "last_outcome": "wrong", "last_predicted": "후진"}
    assert [s["completed"] for s in me["sessions"]].count(False) == 1


def test_other_members_records_are_not_visible():
    c1, c2 = _client(), _client()
    _signup(c1, name="가사원")
    _signup(c2, name="나사원")
    uid1 = members.get_store().login(c1.get("/api/me").json()["member"]["email"], "safe1234")["user_id"]
    _record(uid1)
    assert c1.get("/api/me").json()["certified"] is True
    assert c2.get("/api/me").json()["sessions"] == []


def test_find_id_and_password_reset_use_same_rules_as_kiosk():
    c = _client()
    email, m = _signup(c, name="최사원")
    r = c.post("/api/auth/find-id", json={"name": "최사원", "member_code": m["member_code"]}, headers=H).json()
    assert r["status"] == "ok" and "***" in r["email_masked"]
    assert c.post("/api/auth/password/request", json={"email": email}, headers=H).json()["status"] == "ok"
    code = members.LocalStore._codes[email][0]
    r = c.post("/api/auth/password/reset", json={"email": email, "code": code, "new_password": "newpass99"}, headers=H).json()
    assert r["status"] == "ok"
    assert c.post("/api/auth/login", json={"email": email, "password": "newpass99"}, headers=H).json()["status"] == "ok"


def test_health_db_reports_store():
    r = _client().get("/health/db")
    assert r.status_code == 200 and r.json() == {"status": "ok", "store": "local", "db": "ok"}


def test_security_headers_and_no_store():
    r = _client().get("/api/session")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert _client().get("/").status_code == 200


def test_supabase_list_sessions_reads_joined_results_without_schema_change():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"id": "s1", "completed_at": "2026-09-30T01:00:00Z", "passed_count": 7,
                                          "all_passed": True, "training_results": [
                                              {"order_no": 2, "signal": "서행", "given_up": False},
                                              {"order_no": 1, "signal": "정지", "given_up": False}]}])

    store = members.SupabaseStore("https://x.supabase.co", "k", transport=httpx.MockTransport(handler))
    rows = store.list_sessions("11111111-1111-1111-1111-111111111111")
    assert "select=*,training_results(*)" in seen["url"] and "user_id=eq.11111111" in seen["url"]
    assert [r["order_no"] for r in rows[0]["results"]] == [1, 2] and "training_results" not in rows[0]


def test_missing_config_lists_secret_and_supabase():
    assert main._missing_config("x" * 32, "https://example.supabase.co", "key") == []
    assert len(main._missing_config("short", "", "")) == 2


def test_render_refuses_to_start_without_config():
    """배포에서 설정이 빠지면 임시 세션 키·컨테이너 파일 저장소로 조용히 돌던 결함 — 시작을 거부한다."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items()
           if k not in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PORTAL_SESSION_SECRET")}
    env.update(RENDER="true", SAFESIGN_NO_DOTENV="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-c", "import app.main"], cwd=Path(main.__file__).parents[1],
                          env=env, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode != 0
    assert "portal 설정 누락" in proc.stderr
