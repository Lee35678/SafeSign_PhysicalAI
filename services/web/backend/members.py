"""회원가입·로그인과 회원별 학습 결과 저장 (Supabase).

담당: 이동혁 (2026-09-29)

구조
  - 브라우저는 Supabase에 직접 접근하지 않는다. 이 모듈만 service_role 키로 Supabase REST(Auth·PostgREST)를
    부른다 — 키가 화면 코드에 나가지 않고, 새 의존성(supabase-py) 없이 이미 쓰는 httpx로 끝난다.
  - 교육 스테이션은 1대 1이라(state_machine과 같은 전제) "지금 로그인한 학습자" 하나를 프로세스 전역으로 둔다.
  - 회원코드(SS-00001 꼴)는 DB 시퀀스가 부여한다(supabase/schema.sql) — 동시에 가입해도 겹치지 않는다.

저장소 두 가지 (환경변수로 자동 선택)
  - Supabase: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY 가 있을 때.
      가입 = Auth 관리자 API로 이메일 인증을 마친 계정 생성(교육장에서 인증 메일을 볼 수 없으므로) + members 행.
      로그인 = Auth 비밀번호 로그인.  결과 = rpc/save_training_session 한 번(세션 + 수신호 7행을 한 트랜잭션).
  - 로컬: 키가 없을 때(개발·시연 준비용). data/members_local.json 에 scrypt 해시로 저장, 결과는 JSONL.

인터넷이 끊겼을 때
  - 결과: 전송 실패(연결·타임아웃·5xx)면 data/results_pending.jsonl 에 쌓고, 백그라운드가 30초마다 다시 보낸다.
    세션 ID를 web이 만들어 보내므로 재전송해도 한 번만 저장된다.
  - 로그인·가입: Supabase가 확인해야 하므로 오프라인이면 할 수 없다 → 화면이 게스트 진행을 안내한다.
    게스트 결과는 회원 DB에 올리지 않고 로컬 파일(results_local.jsonl)에만 남긴다.

아이디·비밀번호 찾기 (2026-09-30)
  - 아이디(이메일) 찾기: 이름 + 회원코드가 모두 맞으면 **가린 이메일**(k***@example.com)만 보여 준다.
  - 비밀번호 찾기: 가입 이메일로 **6자리 인증 코드**(Supabase Auth recovery OTP) → 교육장 화면에서 코드 + 새 비밀번호.
    메일 속 링크 방식은 교육장 서버가 인터넷 밖에서 열리지 않아 쓰지 않는다. 가입 여부와 관계없이 같은 안내를 돌려준다
    (이메일로 가입 여부를 캐낼 수 없게). 로컬 모드에서는 메일을 못 보내므로 코드를 서버 로그에만 찍는다(개발용).

보안 (2026-09-30, document/18_DB설계서.md §5)
  - 키: service_role 키는 서버 환경변수에만. anon·publishable 키를 넣으면 기동 시 오류 로그로 알린다.
  - 무차별 대입 방지: 로그인 실패 5회/10분이면 그 이메일·접속 주소를 10분 잠근다. 찾기·코드 요청도 횟수를 제한한다.
  - 비밀번호: 8자 이상 + 영문과 숫자 포함. 입력 길이 제한(이름 30 · 소속 50 · 이메일 254 · 비밀번호 72).
  - 로컬 모드 회원 파일은 scrypt 해시 + 파일 권한 600(POSIX).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TIMEOUT_S = float(os.getenv("SUPABASE_TIMEOUT_S", "5.0"))
PENDING_RETRY_S = float(os.getenv("RESULTS_RETRY_INTERVAL_S", "30"))
# 로컬 파일 폴더 — 쓰는 시점에 읽는다(테스트가 임시 폴더로 바꿔 끼운다)
MEMBER_DATA_DIR = Path(os.getenv("MEMBER_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data")))

MIN_PASSWORD_LEN = 8          # Supabase 기본(6)보다 엄격하게 — 영문·숫자 조합도 요구
MAX_PASSWORD_LEN = 72         # bcrypt(Supabase Auth) 입력 한계
MAX_NAME_LEN, MAX_ORG_LEN, MAX_EMAIL_LEN = 30, 50, 254
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CODE_RE = re.compile(r"^SS-\d{5}$")
RESET_CODE_TTL_S = 10 * 60     # 로컬 모드 인증 코드 유효 시간 (Supabase는 프로젝트 설정의 OTP 만료 시간)


class MemberError(Exception):
    """화면에 그대로 보여 줄 수 있는 가입·로그인 오류. reason은 화면 분기용 코드."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


OFFLINE_MESSAGE = "인터넷에 연결되지 않아 회원 확인을 할 수 없습니다. 게스트로 학습할 수 있어요."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _public(member: Optional[dict]) -> Optional[dict]:
    """화면에 내보낼 회원 정보 — user_id·해시 같은 내부 값은 빼고."""
    if member is None:
        return None
    return {k: member.get(k) for k in ("member_code", "name", "email", "org", "guest")}


def _validate_password(password: str) -> None:
    pw = password or ""
    if len(pw) > MAX_PASSWORD_LEN:
        raise MemberError("weak_password", f"비밀번호는 {MAX_PASSWORD_LEN}자 이하로 해 주세요.")
    if len(pw) < MIN_PASSWORD_LEN or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise MemberError("weak_password", f"비밀번호는 {MIN_PASSWORD_LEN}자 이상, 영문과 숫자를 함께 넣어 주세요.")


def _clean_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        raise MemberError("invalid_email", "이메일 주소 형식을 확인해 주세요.")
    return email


def _validate_signup(email: str, password: str, name: str, org: str = "") -> tuple[str, str]:
    email = _clean_email(email)
    _validate_password(password)
    name = (name or "").strip()
    if not name:
        raise MemberError("name_required", "이름을 입력해 주세요.")
    if len(name) > MAX_NAME_LEN:
        raise MemberError("name_too_long", f"이름은 {MAX_NAME_LEN}자 이하로 입력해 주세요.")
    if len((org or "").strip()) > MAX_ORG_LEN:
        raise MemberError("org_too_long", f"소속은 {MAX_ORG_LEN}자 이하로 입력해 주세요.")
    return email, name


def mask_email(email: str) -> str:
    """k***@example.com — 아이디 찾기에서 전체 이메일을 보여 주지 않는다."""
    local, _, domain = (email or "").partition("@")
    return f"{local[:1]}***@{domain}" if local and domain else "***"


def _check_service_key(key: str) -> None:
    """anon·publishable 키를 넣으면 가입·저장이 RLS에 막혀 이상하게 실패한다 — 기동 때 바로 알린다."""
    if key.startswith("sb_publishable_"):
        logger.error("SUPABASE_SERVICE_ROLE_KEY에 publishable(공개) 키가 들어 있습니다 — secret/service_role 키를 넣으세요")
        return
    parts = key.split(".")
    if len(parts) == 3:
        import base64
        try:
            pad = "=" * (-len(parts[1]) % 4)
            role = json.loads(base64.urlsafe_b64decode(parts[1] + pad)).get("role")
        except (ValueError, TypeError):
            return
        if role != "service_role":
            logger.error("SUPABASE_SERVICE_ROLE_KEY의 역할이 '%s'입니다 — service_role 키를 넣으세요", role)


class _Limiter:
    """메모리 기반 시도 제한 — 창(window) 안에서 max회 넘으면 lock초 동안 막는다. 교육 스테이션 1대라 메모리로 충분하다."""

    def __init__(self, max_hits: int, window_s: float, lock_s: float):
        self.max_hits, self.window_s, self.lock_s = max_hits, window_s, lock_s
        self._hits: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}
        self._lk = threading.Lock()

    def locked_for(self, key: str) -> int:
        with self._lk:
            until = self._locked.get(key, 0.0)
            return max(0, int(until - time.monotonic() + 0.999))

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lk:
            hits = [h for h in self._hits.get(key, []) if now - h < self.window_s] + [now]
            self._hits[key] = hits
            if len(hits) >= self.max_hits:
                self._locked[key] = now + self.lock_s
                self._hits[key] = []

    def clear(self, key: str) -> None:
        with self._lk:
            self._hits.pop(key, None)
            self._locked.pop(key, None)


LOGIN_LIMIT = _Limiter(max_hits=5, window_s=600, lock_s=600)       # 실패 5회/10분 → 10분 잠금
FIND_LIMIT = _Limiter(max_hits=10, window_s=600, lock_s=600)       # 아이디 찾기 10회/10분
RESET_LIMIT = _Limiter(max_hits=3, window_s=600, lock_s=600)       # 코드 요청 3회/10분 (메일 발송 제한 보호)
VERIFY_LIMIT = _Limiter(max_hits=5, window_s=600, lock_s=600)      # 코드 입력 실패 5회/10분


def _locked_error(seconds: int) -> MemberError:
    minutes = max(1, (seconds + 59) // 60)
    return MemberError("too_many_attempts", f"시도가 너무 많습니다. {minutes}분 뒤에 다시 시도해 주세요.")


# ══ 로컬 저장소 (키가 없을 때) ═══════════════════════════════════════════════════
class LocalStore:
    backend = "local"

    def __init__(self):
        self._lock = threading.Lock()

    def _path(self) -> Path:
        return Path(MEMBER_DATA_DIR) / "members_local.json"

    def _load(self) -> dict:
        p = self._path()
        if not p.exists():
            return {"next_no": 1, "users": {}}
        return json.loads(p.read_text(encoding="utf-8"))

    def _save(self, db: dict) -> None:
        p = self._path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)      # 쓰다 죽어도 반쪽 파일이 남지 않게
        try:
            os.chmod(p, 0o600)   # 비밀번호 해시가 들어 있다 — 소유자만 읽게 (Windows에서는 효과가 제한적)
        except OSError:
            pass

    @staticmethod
    def _hash(password: str, salt: bytes) -> str:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1).hex()

    def signup(self, email: str, password: str, name: str, org: str = "") -> dict:
        email, name = _validate_signup(email, password, name, org)
        with self._lock:
            db = self._load()
            if email in db["users"]:
                raise MemberError("email_taken", "이미 가입된 이메일입니다. 로그인해 주세요.")
            salt = secrets.token_bytes(16)
            member = {
                "user_id": str(uuid.uuid4()),
                "member_code": f"SS-{db['next_no']:05d}",
                "email": email, "name": name, "org": (org or "").strip() or None,
                "created_at": _now_iso(),
                "salt": salt.hex(), "hash": self._hash(password, salt),
            }
            db["users"][email] = member
            db["next_no"] += 1
            self._save(db)
        return member

    def login(self, email: str, password: str) -> dict:
        email = (email or "").strip().lower()
        with self._lock:
            member = self._load()["users"].get(email)
        if member is None or not hmac.compare_digest(
                member["hash"], self._hash(password or "", bytes.fromhex(member["salt"]))):
            raise MemberError("invalid_credentials", "이메일 또는 비밀번호가 맞지 않습니다.")
        return member

    def save_session(self, payload: dict) -> None:
        _append_jsonl("results_local.jsonl", payload)

    def find_email(self, name: str, member_code: str) -> Optional[str]:
        with self._lock:
            users = self._load()["users"].values()
        for m in users:
            if m["member_code"] == member_code and m["name"] == name:
                return m["email"]
        return None

    # 로컬 모드 인증 코드: {email: (code, 만료 monotonic)} — 메일을 못 보내므로 서버 로그로만 알린다(개발용)
    _codes: dict[str, tuple[str, float]] = {}

    def request_reset(self, email: str) -> None:
        with self._lock:
            known = email in self._load()["users"]
        if not known:
            return
        code = f"{secrets.randbelow(10 ** 6):06d}"
        LocalStore._codes[email] = (code, time.monotonic() + RESET_CODE_TTL_S)
        logger.warning("[로컬 모드] 비밀번호 재설정 인증 코드 %s → %s (10분 유효, 메일 대신 로그에만 표시)", mask_email(email), code)

    def confirm_reset(self, email: str, code: str, new_password: str) -> None:
        saved = LocalStore._codes.get(email)
        if not saved or saved[1] < time.monotonic() or not hmac.compare_digest(saved[0], (code or "").strip()):
            raise MemberError("invalid_code", "인증 코드가 맞지 않거나 만료됐습니다.")
        with self._lock:
            db = self._load()
            member = db["users"].get(email)
            if member is None:
                raise MemberError("invalid_code", "인증 코드가 맞지 않거나 만료됐습니다.")
            salt = secrets.token_bytes(16)
            member["salt"], member["hash"] = salt.hex(), self._hash(new_password, salt)
            self._save(db)
        LocalStore._codes.pop(email, None)


# ══ Supabase 저장소 ══════════════════════════════════════════════════════════════
class SupabaseOffline(Exception):
    """연결 실패·타임아웃·5xx — 요청이 처리되지 않았으니 나중에 다시 보낼 수 있다."""


class SupabaseRejected(Exception):
    """4xx — 다시 보내도 같은 결과(데이터·설정 문제)."""

    def __init__(self, status: int, body):
        super().__init__(f"http_{status}: {body}")
        self.status = status
        self.body = body


class SupabaseStore:
    backend = "supabase"

    def __init__(self, url: str, service_key: str, transport: Optional[httpx.BaseTransport] = None):
        self.url = url.rstrip("/")
        self.key = service_key
        self.transport = transport       # 테스트용 (httpx.MockTransport)

    def _request(self, method: str, path: str, json_body=None, *, prefer: str = "") -> object:
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}",
                   "Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        try:
            with httpx.Client(timeout=SUPABASE_TIMEOUT_S, transport=self.transport) as client:
                r = client.request(method, f"{self.url}{path}", json=json_body, headers=headers)
        except httpx.HTTPError as exc:
            raise SupabaseOffline(type(exc).__name__) from exc
        if r.status_code >= 500:
            raise SupabaseOffline(f"http_{r.status_code}")
        try:
            body = r.json() if r.content else None
        except ValueError:
            body = r.text
        if r.status_code >= 400:
            raise SupabaseRejected(r.status_code, body)
        return body

    @staticmethod
    def _error_text(body) -> str:
        if isinstance(body, dict):
            return " ".join(str(body.get(k, "")) for k in ("error_code", "code", "msg", "message",
                                                           "error", "error_description")).lower()
        return str(body).lower()

    def _member_row(self, user_id: str) -> Optional[dict]:
        rows = self._request("GET", f"/rest/v1/members?user_id=eq.{user_id}&select=*")
        return rows[0] if rows else None

    def _insert_member(self, user_id: str, email: str, name: str, org: Optional[str]) -> dict:
        rows = self._request("POST", "/rest/v1/members",
                             {"user_id": user_id, "email": email, "name": name, "org": org},
                             prefer="return=representation")
        return rows[0]

    def signup(self, email: str, password: str, name: str, org: str = "") -> dict:
        email, name = _validate_signup(email, password, name, org)
        org = (org or "").strip() or None
        try:
            user = self._request("POST", "/auth/v1/admin/users", {
                "email": email, "password": password, "email_confirm": True,
                "user_metadata": {"name": name, "org": org},
            })
        except SupabaseOffline:
            raise MemberError("offline", OFFLINE_MESSAGE)
        except SupabaseRejected as exc:
            text = self._error_text(exc.body)
            if "exist" in text or "registered" in text:
                raise MemberError("email_taken", "이미 가입된 이메일입니다. 로그인해 주세요.")
            if "password" in text:
                raise MemberError("weak_password", "비밀번호가 너무 약합니다. 더 길게 만들어 주세요.")
            logger.error("Supabase 가입 거부: %s", exc)
            raise MemberError("signup_failed", "가입하지 못했습니다. 잠시 후 다시 시도해 주세요.")

        user_id = (user or {}).get("id")
        try:
            row = self._insert_member(user_id, email, name, org)
        except (SupabaseOffline, SupabaseRejected) as exc:
            # 계정만 생기고 회원 행이 없으면 다음 가입이 "이미 가입됨"으로 막힌다 — 계정을 되돌린다
            logger.error("members 행을 만들지 못해 Auth 계정을 되돌립니다: %s", exc)
            try:
                self._request("DELETE", f"/auth/v1/admin/users/{user_id}")
            except (SupabaseOffline, SupabaseRejected):
                logger.exception("Auth 계정 되돌리기 실패 — Supabase 대시보드에서 %s 를 지워 주세요", email)
            if isinstance(exc, SupabaseOffline):
                raise MemberError("offline", OFFLINE_MESSAGE)
            raise MemberError("signup_failed", "가입하지 못했습니다. schema.sql을 실행했는지 확인해 주세요.")
        return {**row, "user_id": user_id}

    def login(self, email: str, password: str) -> dict:
        email = (email or "").strip().lower()
        try:
            token = self._request("POST", "/auth/v1/token?grant_type=password",
                                  {"email": email, "password": password or ""})
        except SupabaseOffline:
            raise MemberError("offline", OFFLINE_MESSAGE)
        except SupabaseRejected as exc:
            if exc.status in (400, 401):
                raise MemberError("invalid_credentials", "이메일 또는 비밀번호가 맞지 않습니다.")
            logger.error("Supabase 로그인 거부: %s", exc)
            raise MemberError("login_failed", "로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.")

        user = (token or {}).get("user") or {}
        user_id = user.get("id")
        try:
            row = self._member_row(user_id)
            if row is None:        # 대시보드에서 직접 만든 계정 등 — 회원 행을 채워 넣는다
                meta = user.get("user_metadata") or {}
                row = self._insert_member(user_id, email, meta.get("name") or email.split("@")[0],
                                          meta.get("org"))
        except SupabaseOffline:
            raise MemberError("offline", OFFLINE_MESSAGE)
        except SupabaseRejected as exc:
            logger.error("members 조회 실패: %s", exc)
            raise MemberError("login_failed", "회원 정보를 불러오지 못했습니다.")
        return {**row, "user_id": user_id}

    def save_session(self, payload: dict) -> None:
        """실패 시 SupabaseOffline(다시 보낼 것) 또는 SupabaseRejected(보내도 안 됨)."""
        self._request("POST", "/rest/v1/rpc/save_training_session", {"payload": payload})

    def find_email(self, name: str, member_code: str) -> Optional[str]:
        try:
            rows = self._request("GET", f"/rest/v1/members?member_code=eq.{member_code}&select=email,name")
        except SupabaseOffline:
            raise MemberError("offline", OFFLINE_MESSAGE)
        except SupabaseRejected as exc:
            logger.error("아이디 찾기 조회 실패: %s", exc)
            raise MemberError("find_failed", "지금은 찾을 수 없습니다. 잠시 후 다시 시도해 주세요.")
        for row in rows or []:
            if row.get("name") == name:          # 이름 비교는 URL 인코딩 문제를 피하려고 여기서 한다
                return row.get("email")
        return None

    def request_reset(self, email: str) -> None:
        """Supabase Auth가 재설정 메일을 보낸다 — 메일 템플릿에 {{ .Token }}(6자리 코드)이 있어야 한다(supabase/README.md)."""
        try:
            self._request("POST", "/auth/v1/recover", {"email": email})
        except SupabaseOffline:
            raise MemberError("offline", OFFLINE_MESSAGE)
        except SupabaseRejected as exc:
            # 없는 이메일·발송 제한 등 — 가입 여부를 드러내지 않도록 화면에는 같은 안내를 보낸다
            logger.warning("재설정 메일 요청 거부(%s): %s", mask_email(email), exc)

    def confirm_reset(self, email: str, code: str, new_password: str) -> None:
        try:
            verified = self._request("POST", "/auth/v1/verify",
                                     {"type": "recovery", "email": email, "token": (code or "").strip()})
        except SupabaseOffline:
            raise MemberError("offline", OFFLINE_MESSAGE)
        except SupabaseRejected:
            raise MemberError("invalid_code", "인증 코드가 맞지 않거나 만료됐습니다.")
        user_id = ((verified or {}).get("user") or {}).get("id")
        if not user_id:
            raise MemberError("invalid_code", "인증 코드가 맞지 않거나 만료됐습니다.")
        try:
            self._request("PUT", f"/auth/v1/admin/users/{user_id}", {"password": new_password})
        except SupabaseOffline:
            raise MemberError("offline", OFFLINE_MESSAGE)
        except SupabaseRejected as exc:
            logger.error("비밀번호 변경 거부: %s", exc)
            raise MemberError("reset_failed", "비밀번호를 바꾸지 못했습니다. 잠시 후 다시 시도해 주세요.")


# ══ 파일 도우미 · 대기열 ═════════════════════════════════════════════════════════
_file_lock = threading.Lock()


def _append_jsonl(name: str, record: dict) -> None:
    path = Path(MEMBER_DATA_DIR) / name
    with _file_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(name: str) -> list[dict]:
    path = Path(MEMBER_DATA_DIR) / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _rewrite_jsonl(name: str, records: list[dict]) -> None:
    path = Path(MEMBER_DATA_DIR) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    tmp.replace(path)


PENDING_FILE = "results_pending.jsonl"
REJECTED_FILE = "results_rejected.jsonl"


# ══ 현재 학습자 · 공개 함수 ══════════════════════════════════════════════════════
_store = None
_lock = threading.Lock()
_member: Optional[dict] = None
_last_save: Optional[dict] = None      # 최근 결과 저장 상태 — SC-05 화면 표시용
_flush_lock = threading.Lock()


def get_store():
    """환경변수를 보고 저장소를 고른다(한 번만). 테스트는 set_store로 바꿔 끼운다."""
    global _store
    if _store is None:
        if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
            _check_service_key(SUPABASE_SERVICE_ROLE_KEY)
            _store = SupabaseStore(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        else:
            _store = LocalStore()
    return _store


def set_store(store) -> None:
    global _store
    _store = store


def current_member() -> Optional[dict]:
    with _lock:
        return dict(_member) if _member else None


def _set_member(member: Optional[dict]) -> None:
    global _member, _last_save
    with _lock:
        _member = member
        _last_save = None


def reset_last_save() -> None:
    """새 회차를 시작할 때 부른다 — 지난 회차의 "저장됨"이 새 회차 SC-05에 잠깐 비치지 않게."""
    global _last_save
    with _lock:
        _last_save = None


def pending_count() -> int:
    with _file_lock:
        return len(_read_jsonl(PENDING_FILE))


_SENTINEL = object()


def save_session_results(payload: dict, member=_SENTINEL) -> dict:
    """학습을 끝까지 마친 기록 1건을 회원 이름으로 저장한다. 실패해도 예외를 올리지 않는다.

    member: 교육을 시작할 때의 회원(state_machine이 /api/start 시점에 잡아 둔다). 생략하면 지금 로그인한 회원.
    payload: {started_at, completed_at, results: [{order_no, signal, attempts, match_score, given_up}]}
    반환 status: saved(DB) · saved_local(로컬 모드·게스트) · queued(오프라인 — 나중에 자동 전송) · failed
    """
    global _last_save
    if member is _SENTINEL:
        member = current_member()
    # 합격 = 시도 상한(3회) 안에 정답, 불합격 = 상한을 넘겨 넘어감(given_up). DB는 given_up에서 passed를 계산하고,
    # 로컬 파일에도 같은 값을 남긴다 (document/18_DB설계서.md §3)
    results = [{**r, "passed": not r.get("given_up")} for r in (payload.get("results") or [])]
    record = {
        "id": str(uuid.uuid4()),
        "user_id": (member or {}).get("user_id"),
        "member_code": (member or {}).get("member_code") or "GUEST",
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at") or _now_iso(),
        "total_attempts": sum(int(r.get("attempts", 0)) for r in results),
        "first_try_correct": sum(1 for r in results
                                 if int(r.get("attempts", 0)) == 1 and not r.get("given_up")),
        "passed_count": sum(1 for r in results if r["passed"]),
        "results": results,
    }
    store = get_store()
    if member is None or member.get("guest") or store.backend == "local":
        LocalStore().save_session(record)
        state = {"status": "saved_local", "at": _now_iso()}
    else:
        try:
            store.save_session(record)
            state = {"status": "saved", "at": _now_iso()}
        except SupabaseOffline as exc:
            _append_jsonl(PENDING_FILE, record)
            logger.warning("Supabase에 저장하지 못해 대기열에 넣었습니다(%s)", exc)
            state = {"status": "queued", "at": _now_iso()}
        except SupabaseRejected as exc:
            _append_jsonl(REJECTED_FILE, {**record, "error": str(exc)})
            logger.error("Supabase가 결과 저장을 거부했습니다: %s", exc)
            state = {"status": "failed", "at": _now_iso(), "error": str(exc)}
    state["session_id"] = record["id"]
    with _lock:
        _last_save = state
    return state


def flush_pending() -> dict:
    """대기열을 다시 보낸다. 반환: {sent, left}. 연결이 안 되면 첫 실패에서 멈춘다."""
    global _last_save
    store = get_store()
    if store.backend != "supabase":
        return {"sent": 0, "left": pending_count()}
    with _flush_lock:
        with _file_lock:
            records = _read_jsonl(PENDING_FILE)
        sent, left = 0, []
        for i, rec in enumerate(records):
            try:
                store.save_session(rec)
                sent += 1
            except SupabaseOffline:
                left = records[i:]
                break
            except SupabaseRejected as exc:
                _append_jsonl(REJECTED_FILE, {**rec, "error": str(exc)})
        with _file_lock:
            # 보내는 사이 새로 쌓인 것까지 남긴다
            new = _read_jsonl(PENDING_FILE)[len(records):]
            _rewrite_jsonl(PENDING_FILE, left + new)
        if sent:
            with _lock:
                if _last_save and _last_save.get("status") == "queued" and not left:
                    _last_save = {**_last_save, "status": "saved", "at": _now_iso()}
        return {"sent": sent, "left": len(left) + len(new)}


def store_status() -> dict:
    with _lock:
        last = dict(_last_save) if _last_save else None
    return {"backend": get_store().backend, "pending": pending_count(), "last_save": last}


def _retry_loop() -> None:
    while True:
        time.sleep(PENDING_RETRY_S)
        try:
            if pending_count():
                result = flush_pending()
                if result["sent"]:
                    logger.info("대기 중이던 결과 %d건을 Supabase에 저장했습니다(남은 %d건)",
                                result["sent"], result["left"])
        except Exception:  # noqa: BLE001 — 재전송 스레드가 죽으면 대기열이 영영 안 비워진다
            logger.exception("결과 재전송 중 오류")


def start_background() -> None:
    threading.Thread(target=_retry_loop, daemon=True).start()


# ══ API (/api/auth/*) ═══════════════════════════════════════════════════════════
# max_length는 큰 입력으로 서버를 괴롭히지 못하게 하는 상한 — 화면용 안내는 _validate_* 가 한다
class SignupBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=128)
    name: str = Field(max_length=100)
    org: str = Field(default="", max_length=200)


class LoginBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=128)


class FindIdBody(BaseModel):
    name: str = Field(max_length=100)
    member_code: str = Field(max_length=20)


class ResetRequestBody(BaseModel):
    email: str = Field(max_length=320)


class ResetConfirmBody(BaseModel):
    email: str = Field(max_length=320)
    code: str = Field(max_length=20)
    new_password: str = Field(max_length=128)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _ok(member: dict) -> dict:
    _set_member(member)
    return {"status": "ok", "member": _public(member)}


def _error(exc: MemberError) -> dict:
    return {"status": "error", "reason": exc.reason, "message": exc.message}


@router.post("/signup")
def signup(body: SignupBody):
    try:
        return _ok(get_store().signup(body.email, body.password, body.name, body.org))
    except MemberError as exc:
        return _error(exc)


@router.post("/login")
def login(body: LoginBody, request: Request):
    email = (body.email or "").strip().lower()
    keys = (f"email:{email}", f"ip:{_client_ip(request)}")
    wait = max(LOGIN_LIMIT.locked_for(k) for k in keys)
    if wait:
        return _error(_locked_error(wait))
    try:
        member = get_store().login(body.email, body.password)
    except MemberError as exc:
        if exc.reason == "invalid_credentials":
            for k in keys:
                LOGIN_LIMIT.hit(k)
        return _error(exc)
    LOGIN_LIMIT.clear(keys[0])
    return _ok(member)


@router.post("/find-id")
def find_id(body: FindIdBody, request: Request):
    """아이디(이메일) 찾기 — 이름 + 회원코드가 모두 맞으면 가린 이메일만 돌려준다."""
    key = f"ip:{_client_ip(request)}"
    wait = FIND_LIMIT.locked_for(key)
    if wait:
        return _error(_locked_error(wait))
    FIND_LIMIT.hit(key)
    name, code = (body.name or "").strip(), (body.member_code or "").strip().upper()
    if not name or not _CODE_RE.match(code):
        return _error(MemberError("invalid_input", "이름과 회원코드(예: SS-00001)를 확인해 주세요."))
    try:
        email = get_store().find_email(name, code)
    except MemberError as exc:
        return _error(exc)
    if not email:
        return _error(MemberError("not_found", "일치하는 회원이 없습니다. 이름과 회원코드를 확인해 주세요."))
    return {"status": "ok", "email_masked": mask_email(email)}


RESET_SENT_MESSAGE = "가입된 이메일이면 인증 코드를 보냈습니다. 메일의 6자리 코드를 입력해 주세요."


@router.post("/password/request")
def password_request(body: ResetRequestBody, request: Request):
    """비밀번호 재설정 인증 코드 요청. 가입 여부와 관계없이 같은 안내를 돌려준다."""
    try:
        email = _clean_email(body.email)
    except MemberError as exc:
        return _error(exc)
    keys = (f"email:{email}", f"ip:{_client_ip(request)}")
    wait = max(RESET_LIMIT.locked_for(k) for k in keys)
    if wait:
        return _error(_locked_error(wait))
    for k in keys:
        RESET_LIMIT.hit(k)
    store = get_store()
    try:
        store.request_reset(email)
    except MemberError as exc:
        return _error(exc)
    note = " (로컬 모드: 메일 대신 서버 로그에 코드가 찍힙니다)" if store.backend == "local" else ""
    return {"status": "ok", "message": RESET_SENT_MESSAGE + note}


@router.post("/password/reset")
def password_reset(body: ResetConfirmBody, request: Request):
    """인증 코드 + 새 비밀번호로 재설정한다. 성공해도 로그인시키지 않는다(새 비밀번호로 다시 로그인)."""
    try:
        email = _clean_email(body.email)
        _validate_password(body.new_password)
    except MemberError as exc:
        return _error(exc)
    key = f"email:{email}"
    wait = VERIFY_LIMIT.locked_for(key)
    if wait:
        return _error(_locked_error(wait))
    try:
        get_store().confirm_reset(email, body.code, body.new_password)
    except MemberError as exc:
        if exc.reason == "invalid_code":
            VERIFY_LIMIT.hit(key)
        return _error(exc)
    VERIFY_LIMIT.clear(key)
    LOGIN_LIMIT.clear(f"email:{email}")
    return {"status": "ok", "message": "비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요."}


@router.post("/guest")
def guest():
    return _ok({"member_code": None, "name": "게스트", "email": None, "org": None, "guest": True})


@router.post("/logout")
def logout():
    _set_member(None)
    return {"status": "ok"}


@router.get("/me")
def me():
    return {"member": _public(current_member()), "store": store_status()}


@router.post("/results/retry")
def retry_results():
    return {"status": "ok", **flush_pending(), "store": store_status()}
