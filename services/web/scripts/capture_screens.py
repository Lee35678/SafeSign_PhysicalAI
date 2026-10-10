"""web 화면 캡처 — document/images/web_screens/ (14_web_구현보고서 부록 A · 09_화면목록).

담당: 조은수 (2026-10-05, ⑧)

두 가지로 돌린다.

  mock (기본) — 가짜 vision·actuation·picar를 이 스크립트가 띄우고 web도 직접 띄운다. 판정 결과·장치 이상·
                카메라 끊김을 마음대로 넣을 수 있어 정상 흐름과 오류·로딩 화면을 사람 없이 전부 찍는다.
                카메라 영상은 예시 사진 7장(2c19d9c에서 삭제, git 기록)으로 만든 MJPEG라 실물 카메라 화면이 아니다.
  --real      — RPi5에서 실제로 돌고 있는 web(`--web http://<RPi5>:8000`)에 붙는다. 장치·판정은 건드리지 않고,
                화면마다 무엇을 하라고 안내한 뒤 /api/state가 그 화면이 됐을 때 찍는다(사람이 수신호를 한다).
                오류 화면(장치 끊김 등)은 안내에 따라 실제로 케이블·전원을 빼야 나온다 — 못 찍은 화면은 건너뛴다.

    # mock — 저장소 루트에서 (fastapi·uvicorn·httpx·playwright 필요, 브라우저는 시스템 Chrome)
    python services/web/scripts/capture_screens.py
    # 실물
    python services/web/scripts/capture_screens.py --real --web http://192.168.0.2:8000

결과 파일 이름은 두 방식이 같다 — 실물로 다시 찍으면 같은 이름으로 덮어써 문서 링크를 고칠 필요가 없다.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
WEB_DIR = ROOT / "services" / "web"
OUT_DEFAULT = ROOT / "document" / "images" / "web_screens"
SIGNS = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]
COMMAND = {"정지": "stop", "서행": "slow", "좌회전_유도": "turn_left", "우회전_유도": "turn_right",
           "확인_완료": "complete", "후진": "reverse", "주의": "caution"}
PHOTO_COMMIT = "2c19d9c^"          # 예시 사진 7장이 마지막으로 있던 커밋 (mock 카메라 영상용)


# ---------------------------------------------------------------- mock 장치

class Mock:
    """가짜 장치 3종의 상태. 캡처 스크립트가 직접 바꾼다(같은 프로세스)."""

    def __init__(self, frames: dict[str, bytes]):
        self.frames = frames
        self.frame = "none"                 # 카메라 영상: 수신호 이름 또는 "none"(손 없음)
        self.judgment = {"is_reject": True, "reason": "no_hand", "predicted_class": None}
        self.stream_ok = True
        self.stream_delay = 0.0             # 첫 프레임 전 대기(초) — "카메라 연결 중" 로딩 화면용
        self.down: set[str] = set()         # /health가 응답하지 않는 장치
        self.microbit = True
        self.i2c = True
        self.button_seq = 0

    def set_hand(self, shown: str | None, target: str | None = None, prob: float = 0.93, reason: str | None = None):
        """shown 수신호를 카메라에 보여 준다. target의 확률이 화면 일치율이 된다."""
        self.frame = shown or "none"
        if shown is None:
            self.judgment = {"is_reject": True, "reason": reason or "no_hand", "predicted_class": None,
                             "confidence": 0, "match_score": 0, "latency_ms": 40}
            return
        probs = {s: 0.01 for s in SIGNS}
        probs[shown] = prob
        if target and target != shown:
            probs[target] = 0.12
        judgment = {"predicted_class": shown, "confidence": prob, "match_score": int(prob * 100),
                    "latency_ms": 42, "consecutive": 3, "class_probabilities": probs, "is_reject": False}
        if reason:                              # below_tau / out_of_distribution
            judgment.update(is_reject=True, reason=reason)
            if reason == "out_of_distribution":
                judgment.pop("class_probabilities")
        self.judgment = judgment


def _mock_apps(mock: Mock):
    from fastapi import FastAPI, Response
    from fastapi.responses import PlainTextResponse, StreamingResponse

    def health(name, body):
        if name in mock.down:
            return PlainTextResponse("down", status_code=503)     # JSON이 아님 → web은 unreachable로 본다
        return body()

    vision = FastAPI()

    @vision.get("/health")
    def v_health():
        return health("vision", lambda: {"status": "ok", "tau": 0.75, "n_frames": 3})

    @vision.get("/latest")
    def v_latest():
        return mock.judgment

    @vision.post("/reset")
    def v_reset():
        return {"status": "ok"}

    @vision.get("/stream")
    async def v_stream():
        if not mock.stream_ok:
            return Response(status_code=503)

        async def gen():
            if mock.stream_delay:
                yield b"--frame\r\n"          # 헤더만 먼저 — 브라우저는 첫 프레임을 기다린다
                await asyncio.sleep(mock.stream_delay)
            while mock.stream_ok:
                jpg = mock.frames.get(mock.frame) or mock.frames["none"]
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                await asyncio.sleep(0.2)
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    actuation = FastAPI()

    @actuation.get("/health")
    def a_health():
        return health("actuation", lambda: {"status": "ok", "microbit_connected": mock.microbit})

    @actuation.post("/command")
    def a_command():
        time.sleep(0.05)
        return {"status": "ok"}

    @actuation.post("/result")
    @actuation.post("/progress")
    def a_ok():
        return {"status": "ok"}

    @actuation.get("/button")
    def a_button():
        return {"seq": mock.button_seq}

    picar = FastAPI()

    @picar.get("/health")
    def p_health():
        return health("picar", lambda: {"status": "ok", "hardware": {"i2c": {"reachable": mock.i2c}}})

    @picar.post("/picar")
    def p_picar():
        return {"status": "ok", "motor": {"ok": True}, "led": {"ok": True}}

    return {"vision": vision, "actuation": actuation, "picar": picar}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(app, port: int):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           loop="asyncio"))   # uvloop 정책이 전역으로 깔리면 Playwright가 못 뜬다
    threading.Thread(target=server.run, daemon=True).start()
    return server


def _wait_http(url: str, timeout: float = 15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            httpx.get(url, timeout=1)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} 응답 없음")


def _load_frames() -> dict[str, bytes]:
    """예시 사진(세로 800×1067)을 카메라 영상처럼 가로 4:3(1440×1080)으로 바꾼다 — 가장자리는 같은 사진을 흐리게
    늘려 채운다. Pillow가 없으면 세로 사진 그대로(화면 양옆이 검게 나온다)."""
    frames = {}
    for sign, cmd in COMMAND.items():
        raw = subprocess.run(["git", "show", f"{PHOTO_COMMIT}:services/web/frontend/images/{cmd}.jpg"],
                             cwd=ROOT, capture_output=True, check=True).stdout
        frames[sign] = _landscape(raw)
    frames["none"] = _no_hand(frames["정지"])
    return frames


def _landscape(raw: bytes) -> bytes:
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return raw
    import io
    src = Image.open(io.BytesIO(raw)).convert("RGB")
    W, H = 1440, 1080
    bg = src.resize((W, int(src.height * W / src.width))).crop((0, 0, W, H)).filter(ImageFilter.GaussianBlur(60))
    fg = src.resize((int(src.width * H / src.height), H))
    bg.paste(fg, ((W - fg.width) // 2, 0))
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _no_hand(frame: bytes) -> bytes:
    """손이 없는 화면 — 사진의 평균색 한 가지로 채워 배경만 남긴다(손 미검출 판정은 mock 값이 정한다)."""
    try:
        from PIL import Image
    except ImportError:
        return frame
    import io
    img = Image.open(io.BytesIO(frame)).convert("RGB")
    color = img.resize((1, 1)).getpixel((0, 0))
    buf = io.BytesIO()
    Image.new("RGB", img.size, color).save(buf, "JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------- 캡처 흐름

class Capture:
    def __init__(self, page, web: str, out: Path, mock: Mock | None, timeout: float):
        self.page, self.web, self.out, self.mock, self.timeout = page, web, out, mock, timeout
        self.shots: list[str] = []
        self.skipped: list[str] = []

    def state(self) -> dict:
        return httpx.get(f"{self.web}/api/state", timeout=2).json()

    async def until(self, pred, what: str, timeout: float | None = None) -> bool:
        end = time.time() + (timeout or self.timeout)
        while time.time() < end:
            try:
                if pred(self.state()):
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.15)
        print(f"  ! 시간 초과: {what}")
        return False

    async def shot(self, name: str, settle: float = 0.6):
        await asyncio.sleep(settle)
        path = self.out / f"{name}.png"
        await self.page.screenshot(path=str(path))
        self.shots.append(name)
        print(f"  ✓ {path.name}")

    def ask(self, text: str):
        """실물 모드 안내 — 조작할 사람에게 보여 준다."""
        if self.mock is None:
            print(f"\n▶ {text}")

    async def selector(self, sel: str, timeout_ms: int = 8000):
        await self.page.wait_for_selector(sel, state="visible", timeout=timeout_ms)


async def run(cap: Capture):
    page, mock = cap.page, cap.mock
    real = mock is None

    def target(s): return s.get("target_signal")

    await page.goto(cap.web + "/")
    await cap.selector("#screen-landing.active, #screen-reentry.active")

    # --- SC-01 정상
    if not real:
        await cap.until(lambda s: (s.get("devices") or {}).get("picar"), "장치 상태")
    cap.ask("세 장치(카메라·AI Hand·picar)가 모두 정상인지 확인하세요.")
    await page.reload()
    await cap.selector("#screen-landing.active")
    await cap.shot("SC-01_landing", settle=1.5)

    # --- SC-01 장치 이상 (micro:bit 끊김 + picar 연결 안 됨)
    if not real:
        mock.microbit = False
        mock.down.add("picar")
        await cap.until(lambda s: s["devices"].get("picar", {}).get("status") == "unreachable", "장치 이상")
        await page.reload()
        await cap.selector("#screen-landing.active")
        await cap.shot("SC-01_device_error", settle=1.5)
        mock.microbit = True
        mock.down.discard("picar")
        await cap.until(lambda s: s["devices"].get("picar", {}).get("status") == "ok", "장치 복구")
        await page.reload()
        await cap.selector("#screen-landing.active")
    else:
        cap.skipped.append("SC-01_device_error (실물: picar 전원을 끄고 따로 찍는다)")

    # --- 로그인 / 회원가입
    await page.click("#start-btn")
    await cap.selector("#screen-auth.active")
    await cap.shot("AUTH_login")
    if real:
        # 실물은 Supabase에 연결돼 있을 수 있다 — 캡처용 가짜 회원을 만들지 않고 게스트로 들어간다
        cap.skipped += ["AUTH_signup_error", "AUTH_welcome (실물에서는 게스트로 진행 — mock 캡처를 그대로 쓴다)"]
        await page.click("#guest-btn")
    else:
        await page.click("#tab-signup")
        await page.fill("#signup-name", "홍길동")
        await page.fill("#signup-org", "생산1팀")
        await page.fill("#signup-email", f"capture{int(time.time())}@example.com")
        await page.fill("#signup-password", "safesign1")
        await page.fill("#signup-password2", "safesign2")
        await page.click("#signup-submit")
        await cap.selector("#signup-error:not(:empty)")
        await cap.shot("AUTH_signup_error", settle=0.3)
        await page.fill("#signup-password2", "safesign1")
        await page.click("#signup-submit")
        await cap.selector("#screen-welcome.active")
        await cap.shot("AUTH_welcome")
        await page.click("#welcome-continue-btn")

    # --- SC-02
    await cap.selector("#screen-curriculum.active")
    await cap.shot("SC-02_curriculum", settle=1.2)

    # --- SC-03: 카메라 연결 중(로딩) → 영상 끊김(오류) → 시범
    if not real:
        mock.stream_delay = 30
    await page.click("#curriculum-start-btn")
    await cap.selector("#screen-training.active")
    await cap.until(lambda s: s["state"] == "training" and s["phase"] == "demo", "시범 단계")
    if not real:
        await cap.shot("SC-03_camera_loading", settle=1.0)
        mock.stream_delay, mock.stream_ok = 0, False
        await page.evaluate("document.getElementById('camera-img').dispatchEvent(new Event('error'))")
        await page.wait_for_function("document.querySelector('#camera-placeholder span').textContent.includes('받을 수 없')")
        await cap.shot("SC-03_camera_offline", settle=0.3)
        mock.stream_ok = True
        await page.wait_for_selector("#camera-img:not(.hidden)", timeout=10000)
    else:
        await page.wait_for_selector("#camera-img:not(.hidden)", timeout=int(cap.timeout * 1000))
    cap.ask("AI Hand 시범이 끝나면 화면을 그대로 두세요(시범 단계 캡처).")
    if not real:
        mock.set_hand("정지")
    await cap.shot("SC-03_demo", settle=1.5)

    # --- 판정 단계 + 실시간 일치율 (below_tau: 손을 올리는 도중)
    cap.ask("확인(Space)을 누른 뒤, 정지 자세를 어설프게(일치율 75% 미만) 들고 있으세요.")
    if not real:
        mock.set_hand("정지", prob=0.62, reason="below_tau")
        await page.keyboard.press("Space")
    await cap.until(lambda s: s["phase"] == "judging", "판정 단계")
    await cap.until(lambda s: (s.get("last_result") or {}).get("outcome") == "below_tau", "below_tau 안내",
                    timeout=cap.timeout if real else 5)
    await cap.shot("SC-03_judging_below_tau", settle=0.8)

    # --- SC-03a 정답
    cap.ask("정지 자세를 정확히 보여 주세요(정답).")
    if not real:
        mock.set_hand("정지", prob=0.94)
    await cap.selector("#training-overlay.correct:not(.hidden)", timeout_ms=int(cap.timeout * 1000))
    await cap.shot("SC-03a_correct", settle=0.4)

    # --- 다음 수신호(서행) 판정 중 — 일치율 계기
    await cap.until(lambda s: target(s) == "서행" and s["phase"] == "demo", "서행 시범")
    if not real:
        mock.set_hand(None, reason="awaiting_consecutive_frames")
        mock.judgment = {"is_reject": True, "reason": "awaiting_consecutive_frames", "predicted_class": "서행",
                         "confidence": 0.88, "match_score": 80, "latency_ms": 40, "consecutive": 1,
                         "class_probabilities": {**{s: 0.02 for s in SIGNS}, "서행": 0.88}}
        mock.frame = "서행"
    await page.wait_for_selector("#training-overlay.hidden", state="attached", timeout=8000)
    cap.ask("확인(Space)을 누르고 서행 자세를 보여 주되, 화면을 찍을 때까지 잠시 기다리세요.")
    if not real:
        await asyncio.sleep(0.5)
        await page.keyboard.press("Space")
    await cap.until(lambda s: s["phase"] == "judging", "판정 단계")
    await cap.shot("SC-03_judging", settle=1.2)

    # --- SC-03b 오답 (서행 대신 정지) → 재시범
    cap.ask("서행 대신 다른 수신호(예: 정지)를 1초 넘게 보여 주세요(오답).")
    if not real:
        mock.set_hand("정지", target="서행", prob=0.91)
    await cap.selector("#training-overlay.wrong:not(.hidden)", timeout_ms=int(cap.timeout * 1000))
    await cap.shot("SC-03b_wrong", settle=0.4)
    await page.wait_for_selector("#training-overlay.hidden", state="attached", timeout=8000)
    if not real:
        mock.set_hand("서행")
    await cap.shot("SC-03_retry_demo", settle=1.2)

    # --- SC-04 카메라 인식 실패 (판정 단계에서 손 미검출 25회 ≈ 5초)
    cap.ask("확인(Space)을 누른 뒤 손을 카메라 밖으로 빼고 5초 넘게 기다리세요.")
    if not real:
        mock.set_hand(None)
        await page.keyboard.press("Space")
    await cap.until(lambda s: s["state"] == "camera_fail", "SC-04", timeout=cap.timeout if real else 12)
    await cap.selector("#screen-camera-fail.active")
    await cap.shot("SC-04_camera_fail", settle=0.6)

    # 재시도 → 시범 → 나머지 수신호
    cap.ask("재시도를 누르고, 남은 수신호를 끝까지 진행하세요. '후진'은 3번 모두 틀리세요(재시도 초과 화면).")
    if not real:
        mock.set_hand("서행")
        await page.click("#camera-retry-btn")
        for sign in SIGNS[1:]:
            await cap.until(lambda s, sign=sign: target(s) == sign and s["phase"] == "demo", f"{sign} 시범")
            await page.wait_for_selector("#training-overlay.hidden", state="attached", timeout=8000)
            await page.wait_for_selector("#confirm-panel:not(.hidden)", timeout=8000)
            if sign == "후진":                         # 재시도 초과(불합격) 화면 — 마지막 수신호가 아니어야 오버레이가 보인다
                for n in range(3):
                    mock.set_hand("좌회전_유도", target="후진", prob=0.88)
                    await page.wait_for_selector("#confirm-panel:not(.hidden)", timeout=8000)
                    await page.keyboard.press("Space")
                    await cap.selector("#training-overlay.wrong:not(.hidden)")
                    if n < 2:
                        mock.set_hand("후진")
                        await page.wait_for_selector("#training-overlay.hidden", state="attached", timeout=8000)
                await cap.shot("SC-03b_given_up", settle=0.4)
                continue
            mock.set_hand(sign, prob=0.9)
            await page.keyboard.press("Space")
            await cap.until(lambda s, sign=sign: target(s) != sign, f"{sign} 정답")
    else:
        await cap.until(lambda s: (s.get("last_result") or {}).get("given_up"), "재시도 초과",
                        timeout=cap.timeout * 20)
        await cap.shot("SC-03b_given_up", settle=0.3)

    # --- SC-05 / SC-06
    await cap.selector("#screen-summary.active", timeout_ms=int(cap.timeout * 1000))
    await page.wait_for_selector("#save-status.saved, #save-status.local, #save-status.failed", timeout=15000)
    await cap.shot("SC-05_summary", settle=1.2)
    await page.click("#certificate-btn")
    await cap.selector("#screen-certificate.active")
    await cap.shot("SC-06_certificate", settle=2.0)

    # --- SC-07 재접속: 교육 도중 새로고침
    cap.ask("'다시 학습하기' → '교육 시작' 뒤 브라우저를 새로고침합니다(자동).")
    await page.click("#restart-btn")
    await cap.selector("#screen-curriculum.active")          # 다시 학습하기 = 같은 학습자로 SC-02
    await page.click("#curriculum-start-btn")
    await cap.until(lambda s: s["state"] == "training", "교육 재시작")
    await page.reload()
    await cap.selector("#screen-reentry.active")
    await cap.shot("SC-07_reentry")


async def main_async(args):
    from playwright.async_api import async_playwright

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    mock = web_proc = None
    servers = []
    web = args.web
    tmp = tempfile.TemporaryDirectory(prefix="safesign_capture_")

    if not args.real:
        mock = Mock(_load_frames())
        ports = {}
        for name, app in _mock_apps(mock).items():
            ports[name] = _free_port()
            servers.append(_serve(app, ports[name]))
        web_port = _free_port()
        env = {**os.environ,
               "VISION_URL": f"http://127.0.0.1:{ports['vision']}",
               "ACTUATION_URL": f"http://127.0.0.1:{ports['actuation']}",
               "PICAR_URL": f"http://127.0.0.1:{ports['picar']}",
               "DEVICE_HEALTH_INTERVAL_S": "1.0",
               "SAFESIGN_NO_DOTENV": "1",          # 회원 저장은 로컬 모드 — 실제 Supabase에 쓰지 않는다
               "SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": "",
               "MEMBER_DATA_DIR": str(Path(tmp.name) / "data"),
               "TRIAL_LOG_DIR": str(Path(tmp.name) / "logs")}
        for name in ports:
            _wait_http(f"http://127.0.0.1:{ports[name]}/health")
        web_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1",
                                     "--port", str(web_port), "--log-level", "warning"], cwd=WEB_DIR, env=env)
        web = f"http://127.0.0.1:{web_port}"
        _wait_http(f"{web}/health")

    try:
        async with async_playwright() as p:
            # 실물은 사람이 화면을 보며 Space를 눌러야 하므로 창을 띄운다
            browser = await p.chromium.launch(channel=args.channel, headless=not (args.headed or args.real))
            w, h = (int(v) for v in args.size.split("x"))
            page = await browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=args.scale,
                                          locale="ko-KR", reduced_motion="reduce")
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            cap = Capture(page, web, out, mock, args.timeout)
            print(f"캡처 → {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}  ({args.size}, {'실물' if args.real else 'mock'})")
            await run(cap)
            await browser.close()
            print(f"\n{len(cap.shots)}장 저장" + (f", 건너뜀 {len(cap.skipped)}: {cap.skipped}" if cap.skipped else ""))
            real_errors = [e for e in errors if "camera/stream" not in e and "503" not in e]
            if real_errors:
                print("콘솔 오류:", *real_errors, sep="\n  ")
    finally:
        if web_proc:
            web_proc.terminate()
            web_proc.wait(timeout=5)
        for s in servers:
            s.should_exit = True
        tmp.cleanup()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", action="store_true", help="실물 web에 붙어 사람이 조작하는 동안 찍는다")
    ap.add_argument("--web", default="http://localhost:8000", help="--real일 때 web 주소")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--size", default="1920x1080", help="창 크기 (기준 해상도 1920x1080, 노트북 1366x768)")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--channel", default="chrome", help="Playwright 브라우저 채널 (시스템 Chrome)")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--timeout", type=float, default=20.0, help="화면 하나를 기다리는 시간(초). 실물은 60 이상 권장")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
