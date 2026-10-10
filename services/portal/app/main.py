"""SafeSign 회사 웹사이트 (portal) — 항상 켜 두는 회사 서버용.

담당: 이동혁 (2026-09-30)

왜 따로 두나
  - 교육장 web(services/web)은 RPi5에서 켜야만 돌아간다 → 사원이 미리 회원가입하거나 수료증을 다시 받으려면 RPi5가 필요했다.
  - 이 서버는 RPi5·카메라 없이 회사 서버(클라우드 VM·컨테이너 호스팅 등)에서 상시 돌며, **같은 회원 DB(Supabase)** 를 쓴다.
    회원가입·로그인·아이디/비밀번호 찾기는 교육장과 똑같고, 로그인하면 내 정보·수료 여부·수료증을 본다.
  - 카메라 영상(Camera Module 3)은 받지 않는다 — 교육 자체는 교육장 키트에서만 한다.

DB
  - 스키마(services/web/supabase/schema.sql)는 **바꾸지 않는다.** 가입은 교육장과 같은 경로(Auth 계정 + members 행)이고,
    학습 기록(training_sessions·training_results)은 **읽기만** 한다.
  - 가입·로그인·찾기·조회 코드는 교육장 web의 backend/members.py 저장소(LocalStore·SupabaseStore)를 그대로 쓴다 — 규칙
    (비밀번호 8자+영문·숫자, 로그인 5회 실패 잠금, 가린 이메일, 6자리 코드)이 두 사이트에서 어긋나지 않게.

로그인 상태
  - 교육장은 화면 1대라 "지금 학습자"를 전역으로 두지만, 회사 사이트는 여러 사람이 동시에 쓴다 → 사람마다 **서명된 쿠키**.
    쿠키 = base64(json{uid, code, name, exp}) + HMAC-SHA256(PORTAL_SESSION_SECRET). HttpOnly · SameSite=Lax · HTTPS면 Secure.
  - POST 요청은 `X-SafeSign-Portal: 1` 헤더가 있어야 받는다 — 다른 사이트의 폼이 쿠키를 싣고 보내는 요청(CSRF)을 막는다
    (이 헤더는 다른 출처에서 사전 확인 없이 붙일 수 없다).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

SERVICE_ROOT = Path(__file__).resolve().parents[1]
# 교육장 web의 회원 모듈을 그대로 쓴다 (Docker 이미지에는 같은 경로로 복사된다 — Dockerfile)
WEB_BACKEND = Path(os.getenv("SAFESIGN_WEB_BACKEND", str(SERVICE_ROOT.parent / "web" / "backend")))
sys.path.insert(0, str(WEB_BACKEND))
import members  # noqa: E402  (services/web/backend/members.py)

logger = logging.getLogger("portal")

COOKIE = "ss_portal"
SESSION_TTL_S = int(os.getenv("PORTAL_SESSION_TTL_S", str(8 * 3600)))
COOKIE_SECURE = os.getenv("PORTAL_COOKIE_SECURE", "auto").lower()      # auto(HTTPS일 때만) · 1 · 0
CURRICULUM_SIZE = 7

# 배포(Render는 RENDER 환경변수를 자동으로 넣는다)에서는 설정 누락이면 시작하지 않는다. 그냥 넘어가면
# 세션 키는 재시작마다 바뀌어 전원 로그아웃되고, 회원은 재배포 때 지워지는 컨테이너 파일(LocalStore)에 쌓인다.
# 로컬 개발은 기존처럼 경고만 하고 임시 값으로 돈다.
STRICT_CONFIG = os.getenv("PORTAL_STRICT_CONFIG", "1" if os.getenv("RENDER") else "0") == "1"


def _missing_config(secret: str, supabase_url: str, supabase_key: str) -> list:
    missing = []
    if len(secret) < 32:
        missing.append("PORTAL_SESSION_SECRET(32자 이상)")
    if not (supabase_url and supabase_key):
        missing.append("SUPABASE_URL·SUPABASE_SERVICE_ROLE_KEY")
    return missing


_secret_env = os.getenv("PORTAL_SESSION_SECRET", "")
_missing = _missing_config(_secret_env, members.SUPABASE_URL, members.SUPABASE_SERVICE_ROLE_KEY)
if _missing and STRICT_CONFIG:
    raise RuntimeError(f"portal 설정 누락: {', '.join(_missing)} — Render 대시보드의 환경변수를 확인하세요")
if len(_secret_env) < 32:
    logger.warning("PORTAL_SESSION_SECRET이 없거나 짧습니다(32자 미만) — 임시 키를 만듭니다. 서버를 다시 켜면 모두 로그아웃됩니다.")
    _secret_env = secrets.token_hex(32)
SECRET = _secret_env.encode("utf-8")


# ── 세션 쿠키 ──────────────────────────────────────────────────────────────────
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(member: dict, now: Optional[float] = None) -> str:
    body = {"uid": member["user_id"], "code": member.get("member_code"), "name": member.get("name"),
            "exp": int((now or time.time()) + SESSION_TTL_S)}
    raw = _b64(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return f"{raw}.{_sign(raw)}"


def _sign(raw: str) -> str:
    return _b64(hmac.new(SECRET, raw.encode("ascii"), hashlib.sha256).digest())


def read_token(token: Optional[str], now: Optional[float] = None) -> Optional[dict]:
    if not token or token.count(".") != 1:
        return None
    raw, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(raw)):
        return None
    try:
        body = json.loads(_unb64(raw))
    except ValueError:   # json.JSONDecodeError·잘못된 base64 모두 ValueError
        return None
    if body.get("exp", 0) < (now or time.time()):
        return None
    return body


def _secure(request: Request) -> bool:
    if COOKIE_SECURE in ("1", "true", "yes"):
        return True
    if COOKIE_SECURE in ("0", "false", "no"):
        return False
    return request.url.scheme == "https"


def _login_response(request: Request, member: dict) -> JSONResponse:
    resp = JSONResponse({"status": "ok", "member": members._public(member)})
    resp.set_cookie(COOKIE, make_token(member), max_age=SESSION_TTL_S, httponly=True,
                    samesite="lax", secure=_secure(request), path="/")
    return resp


def _session(request: Request) -> Optional[dict]:
    return read_token(request.cookies.get(COOKIE))


def _err(exc: "members.MemberError", status: int = 200) -> JSONResponse:
    return JSONResponse({"status": "error", "reason": exc.reason, "message": exc.message}, status_code=status)


# ── 앱 ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="SafeSign Portal")

SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; "
                                "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def _guard(request: Request, call_next):
    if request.method == "POST" and request.url.path.startswith("/api/") \
            and request.headers.get("x-safesign-portal") != "1":
        return JSONResponse({"status": "error", "reason": "bad_request", "message": "잘못된 요청입니다."}, status_code=403)
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


class SignupBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    name: str = Field(max_length=60)
    org: str = Field(default="", max_length=100)


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


@app.post("/api/auth/signup")
def signup(body: SignupBody, request: Request):
    try:
        member = members.get_store().signup(body.email, body.password, body.name, body.org)
    except members.MemberError as exc:
        return _err(exc)
    return _login_response(request, member)


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request):
    # 교육장과 같은 잠금 규칙(실패 5회/10분 → 10분) — 두 사이트가 같은 카운터를 쓰지는 않는다(프로세스가 다름)
    email = (body.email or "").strip().lower()
    keys = (f"email:{email}", f"ip:{members._client_ip(request)}")
    wait = max(members.LOGIN_LIMIT.locked_for(k) for k in keys)
    if wait:
        return _err(members._locked_error(wait))
    try:
        member = members.get_store().login(body.email, body.password)
    except members.MemberError as exc:
        if exc.reason == "invalid_credentials":
            for k in keys:
                members.LOGIN_LIMIT.hit(k)
        return _err(exc)
    members.LOGIN_LIMIT.clear(keys[0])
    return _login_response(request, member)


@app.post("/api/auth/logout")
def logout():
    resp = JSONResponse({"status": "ok"})
    resp.delete_cookie(COOKIE, path="/")
    return resp


# 아이디 찾기 · 비밀번호 재설정은 교육장과 완전히 같은 함수(횟수 제한·안내 문구 포함)
@app.post("/api/auth/find-id")
def find_id(body: members.FindIdBody, request: Request):
    return members.find_id(body, request)


@app.post("/api/auth/password/request")
def password_request(body: members.ResetRequestBody, request: Request):
    return members.password_request(body, request)


@app.post("/api/auth/password/reset")
def password_reset(body: members.ResetConfirmBody, request: Request):
    return members.password_reset(body, request)


@app.get("/api/session")
def session(request: Request):
    s = _session(request)
    return {"member": {"member_code": s["code"], "name": s["name"]} if s else None,
            "store": {"backend": members.get_store().backend}}     # local이면 화면이 "로컬 모드"를 알린다


def _summarize(row: dict) -> dict:
    results = row.get("results") or []
    passed = sum(1 for r in results if not r.get("given_up"))
    return {
        "id": row.get("id"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "total_attempts": row.get("total_attempts"),
        "first_try_correct": row.get("first_try_correct"),
        "passed_count": row.get("passed_count", passed),
        "all_passed": bool(row.get("all_passed", passed == len(results) and len(results) > 0)),
        "completed": len(results) >= CURRICULUM_SIZE,          # 7종 전 과정을 마쳤는가 = 수료
        "results": [{k: r.get(k) for k in ("order_no", "signal", "attempts", "match_score", "given_up",
                                          "last_outcome", "last_predicted")} for r in results],
    }


@app.get("/api/me")
def me(request: Request):
    s = _session(request)
    if not s:
        return JSONResponse({"status": "error", "reason": "login_required", "message": "로그인이 필요합니다."},
                            status_code=401)
    store = members.get_store()
    try:
        profile = store.get_member(s["uid"])
        sessions = [_summarize(r) for r in store.list_sessions(s["uid"])]
    except members.MemberError as exc:
        return _err(exc, status=503)
    if profile is None:          # 계정이 지워졌다 — 쿠키도 지운다
        resp = JSONResponse({"status": "error", "reason": "login_required", "message": "회원 정보가 없습니다."},
                            status_code=401)
        resp.delete_cookie(COOKIE, path="/")
        return resp
    done = [x for x in sessions if x["completed"]]
    return {
        "status": "ok",
        "member": {k: profile.get(k) for k in ("member_code", "name", "email", "org", "created_at")},
        "certified": bool(done),
        "certified_at": done[-1]["completed_at"] if done else None,      # 처음 수료한 회차 (sessions는 최근 순)
        "sessions": sessions,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "portal", "store": members.get_store().backend}


@app.get("/health/db")
def health_db():
    """DB까지 확인한다. 상시 운영 때 외부 모니터가 5분마다 부르면 서버(무료 호스팅의 잠들기)와
    Supabase 무료 프로젝트(7일 무요청 시 일시 정지)를 함께 깨워 둔다 — README "항상 켜 두기"."""
    store = members.get_store()
    ok = store.ping()
    return JSONResponse({"status": "ok" if ok else "error", "store": store.backend, "db": "ok" if ok else "unreachable"},
                        status_code=200 if ok else 503)


app.mount("/", StaticFiles(directory=str(SERVICE_ROOT / "frontend"), html=True), name="frontend")
