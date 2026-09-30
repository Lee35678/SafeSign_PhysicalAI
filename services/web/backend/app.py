"""web 서비스 진입점.

담당: 조은수 (웹 R, 성능측정 R)
역할: 09_화면목록.md의 SC-01~SC-07 흐름을 담당하는 교육 상태머신 + 프론트엔드 서빙.
vision(GET /latest), actuation(POST /command, /result, /progress — AI Hand+micro:bit, RPi5)을
httpx로 호출한다. picar는 actuation이 아니라 **별도 서비스 picar(POST /picar, RPi4B 8GB, Wi-Fi)**
로 직접 호출한다 — picar가 주행하면 카메라도 함께 이동하는 문제 때문에 보드를 분리했다
(02_설계문서 §1-1, 2026-09-18). picar 호출은 타임아웃 500ms + 1회 재시도, 실패 시 picar 없이
진행 (03_인터페이스계약서 §5-2·§7).
관리자/등록 관련 라우트 없음 — 수신호 등록 기능은 범위에서 제외됨 (03_인터페이스계약서 §6).

2026-09-29 추가 (이동혁): 회원가입·로그인과 회원별 결과 저장(/api/auth/*, backend/members.py — Supabase),
카메라 라이브 영상 중계(/api/camera/stream, backend/camera.py — 수신호 예시 사진을 대신한다).
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend import members
from backend.camera import router as camera_router
from backend.state_machine import router as state_machine_router
from backend.state_machine import start_polling

app = FastAPI(title="SafeSign Web Service")

# 보안 헤더 (2026-09-30, document/18_DB설계서.md §5) — 화면은 같은 출처의 파일만 쓰므로 CSP로 외부 스크립트·프레임을 막는다.
# style-src 'unsafe-inline': 진행 막대 폭 등을 style 속성으로 넣기 때문(스크립트는 인라인 금지 그대로).
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; "
                                "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",   # 카메라는 RPi5가 직접 — 브라우저 권한 불필요
}


@app.middleware("http")
async def _security_headers(request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")     # 회원 정보가 브라우저 캐시에 남지 않게
    return response


app.include_router(state_machine_router, prefix="/api")
app.include_router(members.router, prefix="/api/auth")
app.include_router(camera_router, prefix="/api/camera")


@app.on_event("startup")
def _startup() -> None:
    start_polling()
    members.start_background()      # 오프라인 동안 쌓인 결과를 Supabase로 다시 보낸다


@app.get("/health")
def health():
    return {"status": "ok", "service": "web"}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
