"""회원가입·로그인·결과 저장(backend/members.py) 단위 테스트 — 실제 Supabase 없이.

Supabase는 httpx.MockTransport 로 흉내 낸다(Auth 관리자 API · 비밀번호 로그인 · PostgREST · rpc).
로컬 저장소는 임시 폴더를 쓴다(conftest.py 의 MEMBER_DATA_DIR).

실행: cd services/web && python -m pytest tests/test_members.py -q
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import members  # noqa: E402


class FakeSupabase:
    """아주 작은 가짜 Supabase — 계정·회원·세션을 메모리에 둔다. online=False면 연결 실패를 흉내 낸다."""

    def __init__(self):
        self.users = {}          # email -> {id, password, meta}
        self.members = {}        # user_id -> row
        self.sessions = {}       # id -> payload
        self.seq = 0
        self.online = True
        self.fail_members_insert = False
        self.codes = {}          # email -> 재설정 인증 코드

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.online:
            raise httpx.ConnectError("offline", request=request)
        assert request.headers["apikey"] == "service-key"
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else None

        if path == "/auth/v1/admin/users" and method == "POST":
            if body["email"] in self.users:
                return httpx.Response(422, json={"code": 422, "error_code": "email_exists",
                                                 "msg": "A user with this email address has already been registered"})
            uid = str(uuid.uuid4())
            self.users[body["email"]] = {"id": uid, "password": body["password"], "meta": body["user_metadata"]}
            assert body["email_confirm"] is True
            return httpx.Response(200, json={"id": uid, "email": body["email"]})
        if path.startswith("/auth/v1/admin/users/") and method == "DELETE":
            uid = path.rsplit("/", 1)[-1]
            self.users = {e: u for e, u in self.users.items() if u["id"] != uid}
            return httpx.Response(200, json={})
        if path == "/auth/v1/token" and method == "POST":
            u = self.users.get(body["email"])
            if not u or u["password"] != body["password"]:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Invalid login credentials"})
            return httpx.Response(200, json={"access_token": "t", "user": {"id": u["id"], "user_metadata": u["meta"]}})
        if path == "/rest/v1/members" and method == "POST":
            if self.fail_members_insert:
                return httpx.Response(404, json={"message": "relation public.members does not exist"})
            self.seq += 1
            row = {**body, "member_code": f"SS-{self.seq:05d}", "created_at": "2026-09-29T00:00:00Z"}
            self.members[body["user_id"]] = row
            return httpx.Response(201, json=[row])
        if path == "/rest/v1/members" and method == "GET":
            if "member_code" in request.url.params:
                code = request.url.params["member_code"].removeprefix("eq.")
                return httpx.Response(200, json=[{"email": r["email"], "name": r["name"]}
                                                 for r in self.members.values() if r["member_code"] == code])
            uid = request.url.params["user_id"].removeprefix("eq.")
            row = self.members.get(uid)
            return httpx.Response(200, json=[row] if row else [])
        if path == "/auth/v1/recover" and method == "POST":
            if body["email"] in self.users:
                self.codes[body["email"]] = "123456"      # 실제로는 메일로 간다
            return httpx.Response(200, json={})
        if path == "/auth/v1/verify" and method == "POST":
            u = self.users.get(body["email"])
            if not u or body.get("type") != "recovery" or self.codes.get(body["email"]) != body["token"]:
                return httpx.Response(403, json={"error_code": "otp_expired", "msg": "Token has expired or is invalid"})
            self.codes.pop(body["email"])
            return httpx.Response(200, json={"access_token": "t", "user": {"id": u["id"]}})
        if path.startswith("/auth/v1/admin/users/") and method == "PUT":
            uid = path.rsplit("/", 1)[-1]
            for u in self.users.values():
                if u["id"] == uid:
                    u["password"] = body["password"]
                    return httpx.Response(200, json={"id": uid})
            return httpx.Response(404, json={})
        if path == "/rest/v1/rpc/save_training_session" and method == "POST":
            p = body["payload"]
            self.sessions.setdefault(p["id"], p)      # on conflict do nothing
            return httpx.Response(200, json=p["id"])
        return httpx.Response(404, json={"message": f"no route {method} {path}"})


@pytest.fixture(autouse=True)
def _clear_limits():
    for lim in (members.LOGIN_LIMIT, members.FIND_LIMIT, members.RESET_LIMIT, members.VERIFY_LIMIT):
        lim._hits.clear()
        lim._locked.clear()
    members.LocalStore._codes.clear()
    yield


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(members, "MEMBER_DATA_DIR", tmp_path)
    fs = FakeSupabase()
    members.set_store(members.SupabaseStore("https://proj.supabase.co", "service-key",
                                            transport=httpx.MockTransport(fs.handler)))
    members._set_member(None)
    yield fs
    members.set_store(None)
    members._set_member(None)


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(members, "MEMBER_DATA_DIR", tmp_path)
    members.set_store(members.LocalStore())
    members._set_member(None)
    yield tmp_path
    members.set_store(None)
    members._set_member(None)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(members.router, prefix="/api/auth")
    return TestClient(app)


RESULTS = {"started_at": "2026-09-29T06:00:00+00:00", "completed_at": "2026-09-29T06:09:00+00:00",
           "results": [{"order_no": 1, "signal": "정지", "attempts": 1, "match_score": 92},
                       {"order_no": 2, "signal": "서행", "attempts": 3, "match_score": 81}]}


# ── Supabase ────────────────────────────────────────────────────────────────
def test_signup_assigns_member_code_and_logs_in(fake):
    r = _client().post("/api/auth/signup", json={"email": "Kim@Example.com", "password": "secret12",
                                                 "name": "김학습", "org": "A공장"}).json()
    assert r["status"] == "ok"
    assert r["member"]["member_code"] == "SS-00001" and r["member"]["email"] == "kim@example.com"
    assert "user_id" not in r["member"], "내부 ID는 화면에 내보내지 않는다"
    assert members.current_member()["member_code"] == "SS-00001"


def test_second_signup_gets_next_code_and_duplicate_is_refused(fake):
    c = _client()
    c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    r2 = c.post("/api/auth/signup", json={"email": "b@x.kr", "password": "secret12", "name": "나"}).json()
    assert r2["member"]["member_code"] == "SS-00002"
    dup = c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"}).json()
    assert dup["status"] == "error" and dup["reason"] == "email_taken"


@pytest.mark.parametrize("body, reason", [
    ({"email": "not-an-email", "password": "secret12", "name": "가"}, "invalid_email"),
    ({"email": "a@x.kr", "password": "123", "name": "가"}, "weak_password"),
    ({"email": "a@x.kr", "password": "abcdefgh", "name": "가"}, "weak_password"),     # 숫자 없음
    ({"email": "a@x.kr", "password": "12345678", "name": "가"}, "weak_password"),     # 영문 없음
    ({"email": "a@x.kr", "password": "secret12", "name": "가" * 31}, "name_too_long"),
    ({"email": "a@x.kr", "password": "secret12", "name": "  "}, "name_required"),
])
def test_signup_validation(fake, body, reason):
    r = _client().post("/api/auth/signup", json=body).json()
    assert r["status"] == "error" and r["reason"] == reason
    assert fake.users == {}, "검증에 걸리면 Supabase를 부르지 않는다"


def test_failed_member_row_rolls_back_auth_user(fake):
    fake.fail_members_insert = True
    r = _client().post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"}).json()
    assert r["status"] == "error"
    assert fake.users == {}, "회원 행이 없으면 Auth 계정도 되돌린다 — 안 그러면 다시 가입할 수 없다"


def test_login_and_wrong_password(fake):
    c = _client()
    c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    c.post("/api/auth/logout")
    assert members.current_member() is None
    bad = c.post("/api/auth/login", json={"email": "a@x.kr", "password": "nope"}).json()
    assert bad["reason"] == "invalid_credentials"
    ok = c.post("/api/auth/login", json={"email": "A@x.kr ", "password": "secret12"}).json()
    assert ok["status"] == "ok" and ok["member"]["member_code"] == "SS-00001"


def test_offline_signup_and_login_say_offline(fake):
    fake.online = False
    c = _client()
    assert c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"}).json()["reason"] == "offline"
    assert c.post("/api/auth/login", json={"email": "a@x.kr", "password": "secret12"}).json()["reason"] == "offline"


def test_results_saved_per_member(fake):
    _client().post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    state = members.save_session_results(RESULTS)
    assert state["status"] == "saved"
    (saved,) = fake.sessions.values()
    assert saved["member_code"] == "SS-00001" and saved["user_id"] == members.current_member()["user_id"]
    assert saved["total_attempts"] == 4 and saved["first_try_correct"] == 1
    assert [r["signal"] for r in saved["results"]] == ["정지", "서행"]


def test_offline_results_are_queued_then_flushed_once(fake):
    _client().post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    fake.online = False
    assert members.save_session_results(RESULTS)["status"] == "queued"
    assert members.pending_count() == 1 and fake.sessions == {}
    assert members.flush_pending() == {"sent": 0, "left": 1}, "아직 오프라인이면 대기열을 그대로 둔다"
    fake.online = True
    assert members.flush_pending() == {"sent": 1, "left": 0}
    assert len(fake.sessions) == 1 and members.pending_count() == 0
    assert members.store_status()["last_save"]["status"] == "saved"


def test_guest_results_stay_local(fake):
    c = _client()
    assert c.post("/api/auth/guest").json()["member"]["guest"] is True
    assert members.save_session_results(RESULTS)["status"] == "saved_local"
    assert fake.sessions == {}, "게스트 결과는 회원 DB에 올리지 않는다"
    lines = (members.MEMBER_DATA_DIR / "results_local.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["member_code"] == "GUEST"


# ── 로컬 저장소 (키 없음) ───────────────────────────────────────────────────
def test_local_store_signup_login_and_hash(local):
    c = _client()
    r = c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"}).json()
    assert r["member"]["member_code"] == "SS-00001"
    raw = (local / "members_local.json").read_text(encoding="utf-8")
    assert "secret12" not in raw, "비밀번호 원문을 저장하면 안 된다"
    assert c.post("/api/auth/login", json={"email": "a@x.kr", "password": "x"}).json()["reason"] == "invalid_credentials"
    assert c.post("/api/auth/login", json={"email": "a@x.kr", "password": "secret12"}).json()["status"] == "ok"
    assert members.save_session_results(RESULTS)["status"] == "saved_local"
    assert c.get("/api/auth/me").json()["store"]["backend"] == "local"


# ── state_machine 연결 ─────────────────────────────────────────────────────
def test_finished_session_is_saved_for_the_member_who_started(fake, monkeypatch):
    import time
    from datetime import datetime
    from unittest.mock import patch
    from backend import state_machine as sm

    c = _client()
    c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    with patch.object(sm.httpx, "post", lambda *a, **k: httpx.Response(200, json={"status": "ok"})):
        sm.start()                                          # 가(SS-00001)로 시작
    c.post("/api/auth/logout")
    c.post("/api/auth/signup", json={"email": "b@x.kr", "password": "secret12", "name": "나"})   # 도중에 다른 사람

    sm._session["completed"] = [{"signal": s, "attempts": 1, "match_score": 90} for s in sm.CURRICULUM]
    sm._session["completed"][3] = {"signal": sm.CURRICULUM[3], "attempts": 3, "match_score": 40, "given_up": True}
    sm._save_member_results(sm._session["_gen"])
    end = time.monotonic() + 3
    while not fake.sessions and time.monotonic() < end:
        time.sleep(0.02)
    (saved,) = fake.sessions.values()
    assert saved["member_code"] == "SS-00001", "시작한 사람의 기록이다"
    assert len(saved["results"]) == 7 and saved["results"][3]["given_up"] is True
    assert saved["first_try_correct"] == 6
    assert sm.get_state()["member"]["member_code"] == "SS-00001"

    monkeypatch.delenv("LOG_SUBJECT", raising=False)
    row = sm._trial_row(when=datetime.now(), t_dec=0.0, target_signal="정지", attempt=1, outcome="correct",
                        judgment={}, trial={}, dispatch={})
    assert row["subject"] == "SS-00001", "KPI 시행 로그 대상자 열 = 회원코드"
    monkeypatch.setenv("LOG_SUBJECT", "ext04")
    row = sm._trial_row(when=datetime.now(), t_dec=0.0, target_signal="정지", attempt=1, outcome="correct",
                        judgment={}, trial={}, dispatch={})
    assert row["subject"] == "ext04", "LOG_SUBJECT가 있으면 그것이 우선"


# ── 합격 / 불합격 ────────────────────────────────────────────────────────────
def test_results_carry_passed_flag(fake):
    _client().post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    payload = {**RESULTS, "results": RESULTS["results"] + [
        {"order_no": 3, "signal": "좌회전_유도", "attempts": 3, "match_score": 30, "given_up": True}]}
    members.save_session_results(payload)
    (saved,) = fake.sessions.values()
    assert [r["passed"] for r in saved["results"]] == [True, True, False], "합격 = 상한 안에 정답, 불합격 = given_up"
    assert saved["passed_count"] == 2


# ── 아이디 찾기 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("store", ["fake", "local"])
def test_find_id_returns_masked_email(store, request):
    request.getfixturevalue(store)
    c = _client()
    code = c.post("/api/auth/signup", json={"email": "kim@example.com", "password": "secret12", "name": "김학습"}).json()["member"]["member_code"]
    r = c.post("/api/auth/find-id", json={"name": "김학습", "member_code": code.lower()}).json()
    assert r == {"status": "ok", "email_masked": "k***@example.com"}, "전체 이메일은 보여 주지 않는다"
    assert c.post("/api/auth/find-id", json={"name": "다른사람", "member_code": code}).json()["reason"] == "not_found"
    assert c.post("/api/auth/find-id", json={"name": "김학습", "member_code": "abc"}).json()["reason"] == "invalid_input"


# ── 비밀번호 찾기 ────────────────────────────────────────────────────────────
def test_password_reset_with_code_supabase(fake):
    c = _client()
    c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    r = c.post("/api/auth/password/request", json={"email": "a@x.kr"}).json()
    assert r["status"] == "ok" and "6자리" in r["message"]
    unknown = c.post("/api/auth/password/request", json={"email": "nobody@x.kr"}).json()
    assert unknown["message"] == r["message"], "가입 여부와 관계없이 같은 안내 (이메일로 가입 여부를 캐낼 수 없게)"

    bad = c.post("/api/auth/password/reset", json={"email": "a@x.kr", "code": "000000", "new_password": "newpass99"}).json()
    assert bad["reason"] == "invalid_code"
    weak = c.post("/api/auth/password/reset", json={"email": "a@x.kr", "code": "123456", "new_password": "short"}).json()
    assert weak["reason"] == "weak_password"
    ok = c.post("/api/auth/password/reset", json={"email": "a@x.kr", "code": "123456", "new_password": "newpass99"}).json()
    assert ok["status"] == "ok"
    assert c.post("/api/auth/login", json={"email": "a@x.kr", "password": "secret12"}).json()["reason"] == "invalid_credentials"
    assert c.post("/api/auth/login", json={"email": "a@x.kr", "password": "newpass99"}).json()["status"] == "ok"


def test_password_reset_with_code_local(local, caplog):
    c = _client()
    c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    with caplog.at_level("WARNING"):
        r = c.post("/api/auth/password/request", json={"email": "a@x.kr"}).json()
    assert "로컬 모드" in r["message"]
    code = members.LocalStore._codes["a@x.kr"][0]
    assert code in caplog.text, "로컬 모드는 메일 대신 서버 로그에 코드를 찍는다"
    assert c.post("/api/auth/password/reset", json={"email": "a@x.kr", "code": code, "new_password": "newpass99"}).json()["status"] == "ok"
    assert c.post("/api/auth/login", json={"email": "a@x.kr", "password": "newpass99"}).json()["status"] == "ok"
    again = c.post("/api/auth/password/reset", json={"email": "a@x.kr", "code": code, "new_password": "other999"}).json()
    assert again["reason"] == "invalid_code", "코드는 한 번만 쓴다"


# ── 무차별 대입 방지 ─────────────────────────────────────────────────────────
def test_login_is_locked_after_repeated_failures(local):
    c = _client()
    c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    for _ in range(5):
        assert c.post("/api/auth/login", json={"email": "a@x.kr", "password": "wrong999"}).json()["reason"] == "invalid_credentials"
    locked = c.post("/api/auth/login", json={"email": "a@x.kr", "password": "secret12"}).json()
    assert locked["reason"] == "too_many_attempts", "맞는 비밀번호도 잠금 동안은 막는다"


def test_reset_code_guessing_is_limited(fake):
    c = _client()
    c.post("/api/auth/signup", json={"email": "a@x.kr", "password": "secret12", "name": "가"})
    c.post("/api/auth/password/request", json={"email": "a@x.kr"})
    for _ in range(5):
        c.post("/api/auth/password/reset", json={"email": "a@x.kr", "code": "999999", "new_password": "newpass99"})
    r = c.post("/api/auth/password/reset", json={"email": "a@x.kr", "code": "123456", "new_password": "newpass99"}).json()
    assert r["reason"] == "too_many_attempts"


def test_anon_key_is_reported(caplog):
    import base64
    import json as _json
    payload = base64.urlsafe_b64encode(_json.dumps({"role": "anon"}).encode()).decode().rstrip("=")
    with caplog.at_level("ERROR"):
        members._check_service_key(f"xx.{payload}.yy")
    assert "service_role" in caplog.text


def test_security_headers_on_every_response():
    from backend import app as web_app
    c = TestClient(web_app.app)
    r = c.get("/health")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert c.get("/api/auth/me").headers["cache-control"] == "no-store", "회원 정보가 캐시에 남지 않게"
