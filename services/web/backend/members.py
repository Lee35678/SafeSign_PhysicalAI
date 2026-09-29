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
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TIMEOUT_S = float(os.getenv("SUPABASE_TIMEOUT_S", "5.0"))
PENDING_RETRY_S = float(os.getenv("RESULTS_RETRY_INTERVAL_S", "30"))
# 로컬 파일 폴더 — 쓰는 시점에 읽는다(테스트가 임시 폴더로 바꿔 끼운다)
MEMBER_DATA_DIR = Path(os.getenv("MEMBER_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data")))

MIN_PASSWORD_LEN = 6          # Supabase Auth 기본 최소 길이와 같게
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def _validate_signup(email: str, password: str, name: str) -> tuple[str, str]:
    email = (email or "").strip().lower()
    name = (name or "").strip()
    if not _EMAIL_RE.match(email):
        raise MemberError("invalid_email", "이메일 주소 형식을 확인해 주세요.")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise MemberError("weak_password", f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다.")
    if not name:
        raise MemberError("name_required", "이름을 입력해 주세요.")
    return email, name


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

    @staticmethod
    def _hash(password: str, salt: bytes) -> str:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1).hex()

    def signup(self, email: str, password: str, name: str, org: str = "") -> dict:
        email, name = _validate_signup(email, password, name)
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
        email, name = _validate_signup(email, password, name)
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
        _store = (SupabaseStore(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
                  if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else LocalStore())
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
    results = payload.get("results") or []
    record = {
        "id": str(uuid.uuid4()),
        "user_id": (member or {}).get("user_id"),
        "member_code": (member or {}).get("member_code") or "GUEST",
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at") or _now_iso(),
        "total_attempts": sum(int(r.get("attempts", 0)) for r in results),
        "first_try_correct": sum(1 for r in results
                                 if int(r.get("attempts", 0)) == 1 and not r.get("given_up")),
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
class SignupBody(BaseModel):
    email: str
    password: str
    name: str
    org: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


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
def login(body: LoginBody):
    try:
        return _ok(get_store().login(body.email, body.password))
    except MemberError as exc:
        return _error(exc)


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
