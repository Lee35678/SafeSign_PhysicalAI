// SafeSign 학습자 화면 — SC-01~SC-07 + 회원(로그인·가입) (09_화면목록.md, 2026-09-29 Gemini 디자인).
// 백엔드: /api/state·/api/start·/api/confirm·/api/camera_retry·/api/certificate (state_machine.py)
//        /api/auth/* (members.py — Supabase) · /api/camera/stream (camera.py — Camera Module 3 라이브 영상)
"use strict";

const POLL_MS = 400;
const SAVE_POLL_MS = 1500;
const CAMERA_RETRY_MS = 3000;

// 커리큘럼 순서·손가락 패턴 (엄지·검지·중지·약지·소지, 1=폄) — 02_설계문서 §4, record_dataset.py SIGN_SHAPES와 같다.
// 예시 사진 대신 이 패턴으로 정답 손모양을 보여 준다(2026-09-29 회의: 사진은 빼고 라이브 영상만).
const FINGERS = ["엄지", "검지", "중지", "약지", "소지"];
const SIGN_PATTERNS = {
  "정지": [1, 1, 1, 1, 1],
  "서행": [0, 1, 1, 0, 0],
  "좌회전_유도": [1, 1, 0, 0, 0],
  "우회전_유도": [1, 0, 0, 0, 1],
  "확인_완료": [0, 0, 0, 0, 0],
  "후진": [0, 1, 0, 0, 0],
  "주의": [0, 0, 0, 0, 1],
};
const SIGN_ORDER = Object.keys(SIGN_PATTERNS);

// 판정은 계속되고 화면 안내만 하는 사유 (스펙 §5 결정 — 물리 피드백·시도 횟수 없음)
const HOLD_OUTCOMES = ["below_tau", "out_of_distribution"];
const HOLD_SUBTEXT = {
  below_tau: "손 모양은 비슷하지만 확신이 부족합니다. 손가락을 더 분명하게 펴거나 접어 보세요.",
  out_of_distribution: "7종 중 어느 손 모양과도 다릅니다. 위의 정답 손 모양을 다시 확인하세요.",
};

// ---- 표시 전용 도우미 (2026-10-02 리뉴얼). 서버 값·상태 전환은 건드리지 않고 화면 글자·그림만 만든다 ----

// 내부 식별자(좌회전_유도)를 화면 글자(좌회전 유도)로. 비교·dataset에는 원래 값을 그대로 쓴다.
function signLabel(signal) { return String(signal ?? "").replace(/_/g, " "); }
// AI Hand 설명에 붙은 변경 이력 괄호("(2026-09-20 변경: …)")는 학습자 화면에서 뺀다 (API 값은 그대로)
function aihandText(text) { return String(text ?? "").replace(/\s*\(\d{4}-\d{2}-\d{2}\s*변경[^)]*\)/g, ""); }
// 02_설계문서 §4: 크레인 작업표준신호 5종 + 자체 지정 2종(후진, 주의)
const SELF_SIGNS = ["후진", "주의"];

// 실측 손 관절 21점(hand-data.js, KPI 촬영 RPi5 Camera Module 3)을 SVG로 그린다.
// 펴는 손가락(SIGN_PATTERNS)의 뼈대는 강조색, 나머지는 회색. 데이터가 없으면 빈 문자열.
const FINGER_OF_JOINT = (j) => (j >= 1 && j <= 4 ? 0 : j >= 6 && j <= 8 ? 1 : j >= 10 && j <= 12 ? 2 : j >= 14 && j <= 16 ? 3 : j >= 18 ? 4 : -1);
function handSvg(signal) {
  const data = typeof HAND_LANDMARKS === "undefined" ? null : HAND_LANDMARKS;
  const pts = data && data.signals[signal];
  if (!pts) return "";
  const pattern = SIGN_PATTERNS[signal] || [0, 0, 0, 0, 0];
  const P = (p) => [(p[0] * 84 + 8).toFixed(1), (p[1] * 84 + 8).toFixed(1)];
  const bones = data.connections.map(([a, b]) => {
    const f = FINGER_OF_JOINT(b);
    const [x1, y1] = P(pts[a]), [x2, y2] = P(pts[b]);
    return `<line class="${f >= 0 && pattern[f] ? "b-up" : "b-dn"}" pathLength="1" style="--i:${b}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
  }).join("");
  const joints = pts.map((p, i) => {
    const [x, y] = P(p);
    return `<circle class="${i === 0 ? "j-wrist" : "j"}" style="--i:${i}" cx="${x}" cy="${y}" r="${i === 0 ? 2.8 : 1.9}"/>`;
  }).join("");
  // 장식으로 숨긴다: 이 그림이 쓰이는 곳마다 수신호 이름 글자가 바로 옆에 있어 스크린 리더가 같은 이름을 두 번 읽게 된다
  return `<svg class="hand-svg" viewBox="0 0 100 100" aria-hidden="true" focusable="false">${bones}${joints}</svg>`;
}
function paintHands(root) {
  root.querySelectorAll("[data-hand]").forEach((el) => { el.innerHTML = handSvg(el.dataset.hand); });
}

// ---- 표시 전용 모션: 손 관절 (움직임 줄이기 설정이면 모두 끈다) ----
const REDUCED_MOTION = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

// 안내 손그림: 이전 손모양에서 새 손모양으로 관절을 옮겨 그린다. 손목이 먼저, 손가락 끝이 조금 늦게 따라온다
function morphHand(box, signal) {
  const read = (svg) => svg ? {
    lines: Array.from(svg.querySelectorAll("line"), (l) => ["x1", "y1", "x2", "y2"].map((a) => +l.getAttribute(a))),
    joints: Array.from(svg.querySelectorAll("circle"), (c) => [+c.getAttribute("cx"), +c.getAttribute("cy")]),
  } : null;
  const from = read(box.querySelector("svg"));
  box.innerHTML = handSvg(signal);
  const svg = box.querySelector("svg");
  const to = read(svg);
  if (REDUCED_MOTION || !from || !to || from.lines.length !== to.lines.length || from.joints.length !== to.joints.length) return;
  const lines = svg.querySelectorAll("line"), joints = svg.querySelectorAll("circle");
  const conn = HAND_LANDMARKS.connections;
  const lag = (j) => (j === 0 ? 0 : ((j - 1) % 4) * 45 + 25);   // ms
  const DUR = 560, t0 = performance.now(), token = {};
  box._morph = token;
  const frame = (now) => {
    if (box._morph !== token || !svg.isConnected) return;
    let running = false;
    const k = (j) => { const p = Math.min(1, Math.max(0, (now - t0 - lag(j)) / DUR)); if (p < 1) running = true; return easeInOutCubic(p); };
    joints.forEach((c, i) => {
      const e = k(i);
      c.setAttribute("cx", (from.joints[i][0] + (to.joints[i][0] - from.joints[i][0]) * e).toFixed(2));
      c.setAttribute("cy", (from.joints[i][1] + (to.joints[i][1] - from.joints[i][1]) * e).toFixed(2));
    });
    lines.forEach((l, n) => {
      const [a, b] = conn[n], ea = k(a), eb = k(b), f = from.lines[n], t = to.lines[n];
      l.setAttribute("x1", (f[0] + (t[0] - f[0]) * ea).toFixed(2)); l.setAttribute("y1", (f[1] + (t[1] - f[1]) * ea).toFixed(2));
      l.setAttribute("x2", (f[2] + (t[2] - f[2]) * eb).toFixed(2)); l.setAttribute("y2", (f[3] + (t[3] - f[3]) * eb).toFixed(2));
    });
    if (running) requestAnimationFrame(frame);
  };
  frame(t0);
  requestAnimationFrame(frame);
}

// 첫 화면 7종 띠: 들어올 때 한 번 그려지고, 머무는 동안 2.4초마다 한 신호씩 차례로 밝아진다(키오스크 대기 화면)
let handCycleTimer = null;
function startHandStrip() {
  const strip = document.querySelector("#screen-landing .hand-strip");
  if (!strip || REDUCED_MOTION) return;
  const items = Array.from(strip.querySelectorAll("li"));
  items.forEach((li, h) => li.querySelector(".hand-svg")?.style.setProperty("--h", h));
  strip.classList.remove("draw", "cycling");
  void strip.offsetWidth;   // 다시 들어올 때도 그리기 애니메이션을 처음부터
  strip.classList.add("draw");
  let cur = -1;
  const next = () => {
    items.forEach((li) => li.classList.remove("cur"));
    cur = (cur + 1) % items.length;
    items[cur].classList.add("cur");
  };
  clearInterval(handCycleTimer);
  handCycleTimer = setTimeout(() => {
    strip.classList.add("cycling"); next();
    handCycleTimer = setInterval(next, 2400);
  }, 1500);
}
function stopHandStrip() {
  clearTimeout(handCycleTimer); clearInterval(handCycleTimer); handCycleTimer = null;
  const strip = document.querySelector("#screen-landing .hand-strip");
  if (strip) { strip.classList.remove("cycling"); strip.querySelectorAll("li.cur").forEach((li) => li.classList.remove("cur")); }
}

// 상태 스트립의 공정 경로 — 지금 화면이 어느 단계인지 표시만 한다
const ROUTE_OF_SCREEN = {
  "screen-auth": "auth", "screen-welcome": "auth", "screen-curriculum": "course",
  "screen-training": "train", "screen-camera-fail": "train", "screen-summary": "result", "screen-certificate": "cert",
};
function renderRoute(screenId) {
  const step = ROUTE_OF_SCREEN[screenId] || "";
  document.querySelectorAll("#route li").forEach((li) => {
    if (li.dataset.route === step) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  });
}

let member = null;              // 로그인한 학습자 {member_code, name, email, org, guest}
let storeInfo = null;           // 회원 저장소 상태 {backend: supabase|local, pending, last_save}
let curriculumInfo = {};        // signal -> {aihand, picar}
let pollTimer = null;
let saveTimer = null;
let overlayGen = 0;
let lastOverlayKey = null;
let lastTrainingState = null;   // 오버레이가 사라질 때 확인 버튼을 다시 그리는 데 쓴다 (①-b)
let confirmInFlight = false;    // 확인 요청 중복 방지 — 버튼 클릭과 스페이스바가 겹쳐도 한 번만 보낸다
let retryInFlight = false;
let holdGen = 0;

const $ = (id) => document.getElementById(id);

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function show(screenId) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.remove("active"));
  $(screenId).classList.add("active");
  if (screenId === "screen-landing") startHandStrip(); else stopHandStrip();   // 표시 전용 모션
  // 라이브 영상은 SC-03에서만 받는다 — 다른 화면에서는 vision이 JPEG를 만들 필요가 없다
  if (screenId === "screen-training") startCamera(); else stopCamera();
  if (screenId !== "screen-summary") stopSavePolling();
  renderMember();
  renderRoute(screenId);   // 표시 전용: 상태 스트립 공정 경로
  focusScreenTitle(screenId);
}

// 접근성(표시 전용): 화면이 바뀌면 누른 버튼이 숨겨져 포커스가 BODY로 빠진다 — 새 화면의 제목(h1)으로 옮겨
// 스크린 리더가 새 화면을 읽고 Tab이 그 화면에서 이어지게 한다. showAuth는 이 뒤에 입력칸으로 다시 옮긴다.
function focusScreenTitle(screenId) {
  const title = $(screenId).querySelector("h1");
  if (!title) return;
  if (!title.hasAttribute("tabindex")) title.setAttribute("tabindex", "-1");
  title.focus({ preventScroll: true });
}

async function apiGet(path) {
  const res = await fetch(path, { cache: "no-store" });
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

// ---- 손가락 패턴 ----

function fingerPattern(signal, large = false) {
  const pattern = SIGN_PATTERNS[signal] || [0, 0, 0, 0, 0];
  const label = FINGERS.map((f, i) => `${f} ${pattern[i] ? "폄" : "접음"}`).join(", ");
  return `<div class="finger-pattern${large ? " large" : ""}" role="img" aria-label="${esc(label)}">` +
    FINGERS.map((f, i) => `<span class="finger${pattern[i] ? " up" : ""}"><i></i><small>${f}</small></span>`).join("") +
    "</div>";
}

// ---- 상단: 학습자 · 장치 상태 ----

function renderMember() {
  const chip = $("member-chip");
  if (!member) {
    chip.classList.add("hidden");
    return;
  }
  chip.classList.remove("hidden");
  $("member-code").textContent = member.guest ? "GUEST" : member.member_code;
  $("member-name").textContent = member.guest ? "게스트" : `${member.name} 님`;
  // 교육 중에는 로그아웃을 숨긴다 — 기록이 시작한 사람에게 저장되더라도 화면이 헷갈리지 않게
  const training = $("screen-training").classList.contains("active") || $("screen-camera-fail").classList.contains("active");
  $("logout-btn").classList.toggle("hidden", training);
}

// 장치 하나의 이상 사유(표시 전용). 빈 문자열 = 정상. 상단 스트립·SC-01 패널·요약이 모두 이 한 기준을 쓴다
// (예전에는 요약만 status === "ok"로 세어, BLE·I2C 이상이 있어도 "장치 3/3 정상"이라고 적었다).
function deviceProblem(name, info) {
  let extra = "";
  if (name === "actuation" && info.microbit_connected === false) extra = "micro:bit 끊김";
  if (name === "picar" && info.i2c_reachable === false) extra = "응답 없음";
  if (info.status !== "ok") extra = extra || "연결 안 됨";
  return extra;
}

function renderDeviceStatus(devices) {
  const el = $("device-status-bar");
  renderAboutSys(devices);
  if (!devices || Object.keys(devices).length === 0) {
    el.innerHTML = "";
    $("station-devices").innerHTML = "";   // 표시 전용: SC-01 스테이션 준비 패널
    return;
  }
  const labels = { vision: "카메라", actuation: "AI Hand", picar: "picar" };
  const cells = Object.entries(devices).map(([name, info]) => {
    const extra = deviceProblem(name, info);
    const bad = Boolean(extra);
    // 표시: 칸마다 라벨/값. 정상 = 회색 글자, 이상 = 칸 전체 경보색(station.css .device.bad)
    return { name, bad, extra, html: `<span class="device${bad ? " bad" : ""}"><b>${esc(labels[name] ?? name)}</b><small>${esc(extra || "정상")}</small></span>` };
  });
  el.innerHTML = cells.map((c) => c.html).join("");
  // 표시 전용: SC-01 스테이션 준비 패널 = 교육 흐름도(AI Hand 시범 > 카메라 판정 > picar 동작).
  // 정상 상태 글자는 상단 스트립과 요약에 이미 있으므로 여기서는 이상일 때만 칸을 경보색으로 바꾸고 사유를 적는다.
  const FLOW = [["actuation", "수신호 시범"], ["vision", "손 모양 판정"], ["picar", "신호대로 동작"]];
  const byName = Object.fromEntries(cells.map((c) => [c.name, c]));
  const ordered = [...FLOW.filter(([n]) => byName[n]), ...cells.filter((c) => !FLOW.some(([n]) => n === c.name)).map((c) => [c.name, ""])];
  $("station-devices").innerHTML = ordered.map(([n, role]) => {
    const c = byName[n];
    return `<span class="device${c.bad ? " bad" : ""}"><b>${esc(labels[n] ?? n)}</b><em>${esc(role)}</em>${c.bad ? `<small>${esc(c.extra)}</small>` : ""}</span>`;
  }).join("");
}

// SC-01 스테이션 준비의 장치 요약: 상단 스트립과 같은 기준(deviceProblem)으로 센다
function renderAboutSys(devices) {
  const box = $("about-sys");
  const entries = Object.entries(devices || {});
  const bad = entries.filter(([name, info]) => deviceProblem(name, info)).length;
  const good = entries.length - bad;
  box.classList.toggle("warn", !entries.length || bad > 0);
  box.textContent = !entries.length ? "장치 정보 없음"
    : bad ? `장치 이상 ${bad}대, 정상 ${good}/${entries.length}` : `장치 ${good}/${entries.length} 정상`;
}

// ---- SC-07 / SC-01 ----

async function init() {
  try {
    const me = await apiGet("/api/auth/me");
    member = me.member;
    storeInfo = me.store;
  } catch (err) {
    console.warn("회원 상태를 불러오지 못함", err);
  }
  const state = await apiGet("/api/state");
  rememberCurriculum(state.curriculum);
  renderDeviceStatus(state.devices);
  applyJudgeRule(state.judge_rule);
  // 09_화면목록 SC-07: 학습 중 이탈 후 재접속 — 세션 이어하기 미구현, 항상 처음부터.
  show(state.state && state.state !== "landing" ? "screen-reentry" : "screen-landing");
}

function rememberCurriculum(curriculum) {
  (curriculum || []).forEach((item) => { curriculumInfo[item.signal] = item; });
}

$("reentry-confirm-btn").addEventListener("click", () => show("screen-landing"));

$("start-btn").addEventListener("click", () => {
  if (member) goCurriculum();
  else showAuth("login");
});

// ---- 회원: 로그인 / 가입 / 게스트 ----

function showAuth(tab) {
  setAuthTab(tab);
  const note = $("auth-store-note");
  note.textContent = storeInfo && storeInfo.backend === "local"
    ? "회원 기록 서버에 연결되지 않아 회원 정보가 이 교육장 기기에만 저장됩니다."
    : "";
  show("screen-auth");
  (tab === "signup" ? $("signup-name") : $("login-email")).focus();
}

// 인증 화면의 보기: login · signup · find(아이디 찾기) · reset(비밀번호 찾기 1단계) · reset2(코드 + 새 비밀번호)
const AUTH_VIEWS = {
  login: { form: "login-form", title: "교육 시작 전 로그인" },
  signup: { form: "signup-form", title: "사원 코드 받기" },
  find: { form: "find-id-form", title: "아이디(이메일) 찾기" },
  reset: { form: "reset-request-form", title: "비밀번호 찾기" },
  reset2: { form: "reset-confirm-form", title: "비밀번호 재설정" },
};

function setAuthTab(view) {
  Object.entries(AUTH_VIEWS).forEach(([name, v]) => $(v.form).classList.toggle("hidden", name !== view));
  $("tab-login").setAttribute("aria-selected", String(view === "login"));
  $("tab-signup").setAttribute("aria-selected", String(view === "signup"));
  $("auth-title").textContent = AUTH_VIEWS[view].title;
  document.querySelectorAll("#screen-auth .form-error, #screen-auth .form-result").forEach((el) => { el.textContent = ""; });
}

// 서버와 같은 규칙(8자 이상 + 영문·숫자) — 서버가 최종으로 다시 검사한다
function passwordProblem(pw, pw2) {
  if (pw.length < 8 || !/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "비밀번호는 8자 이상, 영문과 숫자를 함께 넣어 주세요.";
  if (pw !== pw2) return "비밀번호 확인이 일치하지 않습니다.";
  return "";
}

$("tab-login").addEventListener("click", () => setAuthTab("login"));
$("tab-signup").addEventListener("click", () => setAuthTab("signup"));

async function submitAuth(path, body, errorEl, submitBtn, busyText) {
  const idle = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = busyText;
  errorEl.textContent = "";
  try {
    const res = await apiPost(path, body);
    if (res.status !== "ok") {
      errorEl.textContent = res.message || "요청을 처리하지 못했습니다.";
      if (res.reason === "offline") $("guest-btn").focus();
      return null;
    }
    member = res.member;
    return res.member;
  } catch (err) {
    errorEl.textContent = "서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.";
    return null;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = idle;
  }
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const ok = await submitAuth("/api/auth/login", {
    email: $("login-email").value, password: $("login-password").value,
  }, $("login-error"), $("login-submit"), "확인 중…");
  if (ok) {
    $("login-form").reset();
    goCurriculum();
  }
});

$("signup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const problem = passwordProblem($("signup-password").value, $("signup-password2").value);
  if (problem) {
    $("signup-error").textContent = problem;
    return;
  }
  const ok = await submitAuth("/api/auth/signup", {
    name: $("signup-name").value, org: $("signup-org").value,
    email: $("signup-email").value, password: $("signup-password").value,
  }, $("signup-error"), $("signup-submit"), "가입 중…");
  if (ok) {
    $("signup-form").reset();
    $("welcome-name").textContent = ok.name;
    $("welcome-code").textContent = ok.member_code;
    show("screen-welcome");
  }
});

$("welcome-continue-btn").addEventListener("click", () => goCurriculum());

// ---- 아이디(이메일) 찾기 · 비밀번호 찾기 ----

$("goto-find-id").addEventListener("click", () => { setAuthTab("find"); $("find-name").focus(); });
$("goto-reset").addEventListener("click", () => {
  setAuthTab("reset");
  $("reset-email").value = $("login-email").value;
  $("reset-email").focus();
});
document.querySelectorAll(".back-to-login").forEach((b) => b.addEventListener("click", () => setAuthTab("login")));

async function authCall(path, body, errorEl, submitBtn, busyText) {
  const idle = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = busyText;
  errorEl.textContent = "";
  try {
    const res = await apiPost(path, body);
    if (res.status !== "ok") {
      errorEl.textContent = res.message || "요청을 처리하지 못했습니다.";
      return null;
    }
    return res;
  } catch (err) {
    errorEl.textContent = "서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.";
    return null;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = idle;
  }
}

$("find-id-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("find-id-result").textContent = "";
  const res = await authCall("/api/auth/find-id", {
    name: $("find-name").value, member_code: $("find-code").value.trim().toUpperCase(),
  }, $("find-id-error"), $("find-id-submit"), "찾는 중…");
  if (res) {
    $("find-id-result").textContent = `가입한 이메일: ${res.email_masked}`;
  }
});

$("reset-request-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = $("reset-email").value.trim();
  const res = await authCall("/api/auth/password/request", { email },
    $("reset-request-error"), $("reset-request-submit"), "보내는 중…");
  if (res) {
    setAuthTab("reset2");
    $("reset-confirm-form").dataset.email = email;
    $("reset-sent").textContent = res.message;
    $("reset-code").focus();
  }
});

$("reset-confirm-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const problem = passwordProblem($("reset-password").value, $("reset-password2").value);
  if (problem) {
    $("reset-confirm-error").textContent = problem;
    return;
  }
  const email = $("reset-confirm-form").dataset.email || "";
  const res = await authCall("/api/auth/password/reset", {
    email, code: $("reset-code").value, new_password: $("reset-password").value,
  }, $("reset-confirm-error"), $("reset-confirm-submit"), "바꾸는 중…");
  if (res) {
    $("reset-confirm-form").reset();
    setAuthTab("login");
    $("login-email").value = email;
    $("login-error").textContent = "";
    $("login-password").focus();
    // 성공 안내는 로그인 폼 위 결과 줄 대신 오류 줄을 재사용하지 않고 제목 아래 안내로 보여 준다
    $("auth-store-note").textContent = res.message;
  }
});

// ---- 자리 비움 자동 로그아웃 (공용 교육장 PC) ----
// 교육 중(SC-03·SC-04)이 아닐 때 5분 동안 입력이 없으면 로그아웃한다 — 다음 사람의 기록이 앞사람 계정에 쌓이지 않게.
// 교육 중에는 입력이 없어도 활동으로 본다(2026-10-01): 확인·재시도를 micro:bit A로만 하면 키보드·마우스 입력이 없어서,
// 5분 넘게 교육한 사람이 SC-05에 들어가자마자 로그아웃돼 결과표·수료증을 못 봤다. 5분은 교육이 끝난 뒤부터 센다.
const IDLE_LOGOUT_MS = 5 * 60 * 1000;
let lastInputAt = Date.now();
["pointerdown", "keydown", "touchstart"].forEach((ev) =>
  document.addEventListener(ev, () => { lastInputAt = Date.now(); }, { passive: true }));
setInterval(() => {
  if (!member) return;
  const training = $("screen-training").classList.contains("active") || $("screen-camera-fail").classList.contains("active");
  if (training) {
    lastInputAt = Date.now();
    return;
  }
  if (Date.now() - lastInputAt > IDLE_LOGOUT_MS) {
    lastInputAt = Date.now();
    logout();
  }
}, 15000);

$("guest-btn").addEventListener("click", async () => {
  const res = await apiPost("/api/auth/guest");
  member = res.member;
  goCurriculum();
});

async function logout() {
  await apiPost("/api/auth/logout");
  member = null;
  show("screen-landing");
}

$("logout-btn").addEventListener("click", (event) => {
  event.currentTarget.blur();
  logout();
});

// ---- SC-02 ----

async function goCurriculum() {
  const state = await apiGet("/api/state");
  rememberCurriculum(state.curriculum);
  renderCurriculumList(state.curriculum || []);
  renderCourseSpec(state);   // 표시 전용: 오른쪽 과정 사양
  show("screen-curriculum");
}

// 신호 레지스터 (2026-10-02 리뉴얼, 표시 전용): 행마다 순서 | 수신호 | 실측 손 관절 + 손가락 글리프 | AI Hand | picar.
// 크레인 표준 / 자체 지정 묶음 머리 행(li.register-group)은 장식이 아닌 분류 표시다.
function renderCurriculumList(curriculum) {
  const list = $("curriculum-list");
  list.innerHTML = "";
  let group = null;
  curriculum.forEach((item, i) => {
    const self = SELF_SIGNS.includes(item.signal);
    const groupName = self ? "자체 지정" : "크레인 작업표준신호";
    const firstOfGroup = group !== self;
    if (firstOfGroup) {
      group = self;
      // 보이는 묶음 머리는 스크린 리더에서 숨기고(목록이 7항목으로 읽히게), 묶음 이름은 그 묶음 첫 행에 붙인다
      const head = document.createElement("li");
      head.className = "register-group";
      head.setAttribute("aria-hidden", "true");
      head.textContent = groupName;
      list.appendChild(head);
    }
    const li = document.createElement("li");
    li.className = `sign-card${self ? " self" : ""}`;
    li.innerHTML = `${firstOfGroup ? `<span class="sr-only">${groupName}: </span>` : ""}
      <span class="sign-card-no">${String(i + 1).padStart(2, "0")}</span>
      <p class="sign-card-name">${esc(signLabel(item.signal))}</p>
      <div class="sign-card-figure"><span class="hand-fig">${handSvg(item.signal)}</span>${fingerPattern(item.signal)}</div>
      <p class="sign-card-hand">${esc(aihandText(item.aihand))}</p>
      <p class="sign-card-picar">${esc(item.picar)}</p>`;
    list.appendChild(li);
  });
}

function renderCourseSpec(state) {
  const n = (state.curriculum || []).length;
  if (n) $("spec-count").textContent = n;
  if (state.max_attempts) $("spec-attempts").textContent = state.max_attempts;
}

$("curriculum-back-btn").addEventListener("click", () => show("screen-landing"));

$("curriculum-start-btn").addEventListener("click", async () => {
  await apiPost("/api/start");
  lastOverlayKey = null;
  lastTrainingState = null;
  hideOverlay();
  show("screen-training");
  startPolling();
});

// ---- 라이브 영상 (Camera Module 3 → vision /stream → web /api/camera/stream) ----

let cameraWanted = false;
let cameraRetryTimer = null;
let cameraCheckTimer = null;

function startCamera() {
  if (cameraWanted) return;
  cameraWanted = true;
  connectCamera();
}

function connectCamera() {
  clearTimeout(cameraRetryTimer);
  if (!cameraWanted) return;
  setCameraOnline(false, "카메라 연결 중…");
  const img = $("camera-img");
  img.src = `/api/camera/stream?t=${Date.now()}`;      // 매번 새 연결 (캐시된 스트림을 다시 쓰지 않게)
  // MJPEG는 브라우저마다 load 이벤트가 다르게 온다 — 첫 프레임이 그려졌는지(naturalWidth)로 판단한다
  clearInterval(cameraCheckTimer);
  cameraCheckTimer = setInterval(() => {
    if (img.naturalWidth > 0) {
      setCameraOnline(true);
      clearInterval(cameraCheckTimer);
    }
  }, 300);
}

function stopCamera() {
  cameraWanted = false;
  clearTimeout(cameraRetryTimer);
  clearInterval(cameraCheckTimer);
  $("camera-img").removeAttribute("src");                // 연결을 끊어 vision 인코딩도 멈춘다
  setCameraOnline(false, "카메라 연결 중…");
}

function setCameraOnline(online, text) {
  $("camera-img").classList.toggle("hidden", !online);
  $("camera-placeholder").classList.toggle("hidden", online);
  $("camera-preview").classList.toggle("offline", !online);
  if (text) $("camera-placeholder").querySelector("span").textContent = text;
}

$("camera-img").addEventListener("error", () => {
  if (!cameraWanted) return;
  clearInterval(cameraCheckTimer);
  setCameraOnline(false, "카메라 영상을 받을 수 없습니다");
  cameraRetryTimer = setTimeout(connectCamera, CAMERA_RETRY_MS);
});

// ---- SC-03 (+03a/03b) / SC-04 / SC-05 ----

function startPolling() {
  stopPolling();
  pollTimer = setInterval(refreshTraining, POLL_MS);
  refreshTraining();
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function refreshTraining() {
  let state;
  try {
    state = await apiGet("/api/state");
  } catch (err) {
    return;                        // web이 잠깐 응답하지 않아도 다음 폴링에서 이어간다
  }
  renderDeviceStatus(state.devices);
  applyJudgeRule(state.judge_rule);
  rememberCurriculum(state.curriculum);

  if (state.state === "camera_fail") {
    if (!$("screen-camera-fail").classList.contains("active")) show("screen-camera-fail");
    return;
  }

  if (state.state === "summary") {
    stopPolling();
    renderSummary(state);
    show("screen-summary");
    startSavePolling();
    return;
  }

  if (state.state !== "training") return;

  if (!$("screen-training").classList.contains("active")) show("screen-training");
  renderHeader(state);
  setMatchScore(state.live_judgment ? state.live_judgment.match_score : 0);
  renderHud(state.live_judgment);

  const result = state.last_result;
  if (result) {
    const key = `${result.signal}:${result.outcome}:${result.attempt}`;
    if (key !== lastOverlayKey) {
      lastOverlayKey = key;
      if (HOLD_OUTCOMES.includes(result.outcome)) showHoldHint(result);
      else showOverlay(result, state);
    }
  }

  lastTrainingState = state;
  renderPhase(state);
}

function renderHeader(state) {
  const signal = state.target_signal ?? "-";
  const info = state.signal_info || curriculumInfo[signal] || {};
  $("signal-name").textContent = signLabel(signal);
  $("signal-desc").textContent = info.aihand ? `AI Hand: ${aihandText(info.aihand)}` : "";
  $("signal-picar-text").textContent = info.picar || "";
  $("signal-progress").innerHTML = `<b>${state.progress.current}</b> / ${state.progress.total}`;
  // 공정 레일: 칸마다 수신호 이름을 함께 적는다(표시 전용, 순서는 커리큘럼 그대로)
  const order = (state.curriculum || []).map((c) => c.signal);
  $("progress-steps").innerHTML = Array.from({ length: state.progress.total }, (_, i) => {
    const n = i + 1;
    const name = order[i] ?? SIGN_ORDER[i] ?? "";
    const st = n < state.progress.current ? "done" : n === state.progress.current ? "current" : "";
    const sr = st === "done" ? '<span class="sr-only"> 마침</span>' : st === "current" ? '<span class="sr-only"> 현재</span>' : "";
    return `<i class="${st}"${st === "current" ? ' aria-current="step"' : ""}><span>${esc(signLabel(name))}</span>${sr}</i>`;
  }).join("");
  $("attempt-count").textContent = state.attempts ?? 0;
  $("attempt-max").textContent = state.max_attempts ? ` / ${state.max_attempts}회` : "회";
  const guide = $("guide-fingers");
  if (guide.dataset.signal !== signal) {
    guide.dataset.signal = signal;
    guide.innerHTML = fingerPattern(signal, true);
    $("guide-text").textContent = aihandText(info.aihand || "");
    morphHand($("guide-hand"), signal);   // 표시 전용: 실측 손 관절, 이전 신호에서 옮겨 그린다
  }
}

// ---- SC-03 시범/판정 단계 (web 할 일 ①-b, 스펙 §4.2) ----

function overlayVisible() {
  return !$("training-overlay").classList.contains("hidden");
}

// 확인 버튼이 "보이는" 조건 — 스페이스바도 이때만 받는다. 정답/오답 오버레이가 덮고 있는 동안은 받지 않는다.
function confirmAvailable() {
  const state = lastTrainingState;
  return Boolean(state) && state.state === "training" && state.phase === "demo"
    && $("screen-training").classList.contains("active") && !overlayVisible();
}

function renderPhase(state) {
  const demo = state.phase === "demo";
  const stage = $("training-stage");
  stage.classList.toggle("phase-demo", demo);
  stage.classList.toggle("phase-judging", !demo);

  $("confirm-panel").classList.toggle("hidden", !confirmAvailable());
  $("judging-hint").classList.toggle("hidden", demo);
  // 시범 동안 vision 판정은 멈춰 있어 live_judgment는 지난 값이다 — 일치율은 판정 중에만 보인다
  $("match-score-row").classList.toggle("hidden", demo);
  if (demo) $("hold-hint").classList.add("hidden");

  const btn = $("confirm-btn");
  btn.disabled = confirmInFlight;
  btn.textContent = confirmInFlight ? "확인 중…" : "확인";

  // micro:bit 버튼 A는 BLE가 끊긴 동안 입력이 사라진다(03 §7) — 끊겼으면 안내에서 빼고 Space를 쓰게 한다
  const actuation = (state.devices || {}).actuation;
  const bleDown = Boolean(actuation) && (actuation.status !== "ok" || actuation.microbit_connected === false);
  $("confirm-keys").innerHTML = bleDown
    ? "<kbd>Space</kbd> 키만 됩니다. micro:bit 연결이 끊겨 A 버튼은 지금 동작하지 않습니다."
    : "<kbd>Space</kbd> 키 또는 micro:bit <kbd>A</kbd> 버튼";
}

async function confirmReady() {
  if (confirmInFlight || !confirmAvailable()) return;
  confirmInFlight = true;
  renderPhase(lastTrainingState);
  try {
    // 판정 중이거나 이미 확인됐으면(micro:bit A가 먼저 눌린 경우 등) 서버가 {"status": "ignored"}를 돌려준다
    await apiPost("/api/confirm");
  } catch (err) {
    console.warn("확인 요청 실패", err);
  } finally {
    confirmInFlight = false;
  }
  refreshTraining();
}

$("confirm-btn").addEventListener("click", (event) => {
  // 포커스가 남으면 다음 Space가 버튼 클릭으로도 들어간다 — 아래 keydown 처리와 겹치지 않게 푼다
  event.currentTarget.blur();
  confirmReady();
});

document.addEventListener("keydown", (event) => {
  if (event.code !== "Space") return;
  if ($("screen-camera-fail").classList.contains("active")) {
    event.preventDefault();
    if (!event.repeat) cameraRetry();
    return;
  }
  if (!confirmAvailable()) return;
  event.preventDefault();          // 페이지 스크롤 방지
  if (event.repeat) return;        // 누르고 있을 때의 반복 입력은 무시
  confirmReady();
});

function showHoldHint(result) {
  const myGen = ++holdGen;
  // 표시 전용: below_tau 백엔드 문구("…해주세요")는 화면의 다른 문구와 띄어쓰기만 달라 화면 문구로 쓴다. 그 밖은 백엔드 문구 그대로
  $("hold-title").textContent = result.outcome === "below_tau" ? "조금 더 정확히 해 주세요" : (result.message ?? "조금 더 정확히 해 주세요");
  $("hold-sub").textContent = `${HOLD_SUBTEXT[result.outcome] ?? ""} (일치율 ${result.match_score}%)`;
  $("hold-hint").classList.remove("hidden");
  setTimeout(() => {
    if (myGen === holdGen) $("hold-hint").classList.add("hidden");
  }, 3000);
}

function hideOverlay() {
  overlayGen++;
  $("training-overlay").classList.add("hidden");
  $("hold-hint").classList.add("hidden");
}

// 판정 규칙(τ·N프레임) — web이 vision /health 값을 /api/state `judge_rule`로 넘긴다(2026-10-01, 하드코딩 75 대체).
// 아직 못 받았거나 값이 이상하면 기본값(05 §8-0: τ 0.75, 3프레임)을 그대로 쓴다.
let judgeRule = { tau: 0.75, n_frames: 3 };
function tauPct() { return Math.round(judgeRule.tau * 100); }
function applyJudgeRule(rule) {
  const tau = Number(rule && rule.tau);
  const n = Number(rule && rule.n_frames);
  if (tau > 0 && tau < 1) judgeRule.tau = tau;
  if (Number.isInteger(n) && n > 0) judgeRule.n_frames = n;
  const tick = document.querySelector(".match-tick");
  tick.style.left = `${tauPct()}%`;
  tick.querySelector("b").textContent = `판정 기준 ${tauPct()}%`;
  $("hud-rule").textContent = `${judgeRule.n_frames}프레임 연속, ${tauPct()}% 이상`;   // 눈금 라벨·과정 사양과 같은 표기(τ 기호는 학습자에게 개발 용어)
  // 표시 전용: SC-02 과정 사양·SC-05 KPI 띠의 판정 기준도 같은 값으로
  $("spec-tau").textContent = tauPct();
  $("spec-frames").textContent = judgeRule.n_frames;
  $("kpi-tau").textContent = tauPct();
  $("th-tau").textContent = tauPct();
}

function setMatchScore(score) {
  const value = Math.max(0, Math.min(100, score || 0));
  $("match-score-fill").style.width = `${value}%`;
  $("match-score-value").textContent = `${value}%`;
  // 판정 기준(τ) 이상이면 막대를 정상색으로 — 색만으로 알리지 않도록 글자도 함께 (05 §10 일치율)
  const pass = value >= tauPct();
  $("match-score-fill").classList.toggle("pass", pass);
  $("match-score-state").textContent = pass ? "기준 이상" : "";
}

// 카메라 계기판 — vision이 지금 보고 있는 것 (판정 중에만 보인다, station.css .phase-judging .camera-hud)
const NO_HAND_REASONS = ["no_hand", "normalize_failed"];
function renderHud(live) {
  const hand = $("hud-hand"), pred = $("hud-pred"), conf = $("hud-conf");
  if (!live) {
    hand.textContent = pred.textContent = conf.textContent = "-";
    hand.className = "";
    return;
  }
  const noHand = live.is_reject && NO_HAND_REASONS.includes(live.reason);
  hand.textContent = noHand ? "찾는 중" : "검출";
  hand.className = noHand ? "warn" : "ok";
  // vision이 미판정(OOD·모델 없음·추론 오류)일 때 보내는 내부 라벨 'negative'는 학습자에게 개발 용어라 "-"로 보인다(표시 전용)
  pred.textContent = noHand || !live.predicted_class || live.predicted_class === "negative" ? "-" : signLabel(live.predicted_class);
  conf.textContent = noHand ? "-" : `${Math.round((live.confidence || 0) * 100)}%`;
}

// Phosphor Icons 2.1.1 (MIT, icons/LICENSE.txt): check / x
const ICON_CHECK = '<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M229.66,77.66l-128,128a8,8,0,0,1-11.32,0l-56-56a8,8,0,0,1,11.32-11.32L96,188.69,218.34,66.34a8,8,0,0,1,11.32,11.32Z"/></svg>';
const ICON_X = '<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z"/></svg>';

function showOverlay(result, state) {
  const overlay = $("training-overlay");
  const myGen = ++overlayGen;
  const correct = result.outcome === "correct";
  const holdMs = correct ? 2000 : 2500;
  const info = curriculumInfo[result.signal] || {};
  let body;

  // 안돈 판 배치(표시 전용, 2026-10-02): 왼쪽 7열 = 판정 단어, 오른쪽 5열 = 데이터, 맨 아래 = 남은 시간 띠
  const timer = `<div class="overlay-timer"><span style="animation-duration:${holdMs}ms"></span></div>`;
  // 긴 문구(백엔드 메시지)는 판정 단어 크기를 줄여 두 줄 안에 둔다
  const verdict = (icon, title) => `<div class="ov-verdict"><div class="overlay-icon">${icon}</div><h2${String(title).length > 9 ? ' class="is-long"' : ""}>${title}</h2></div>`;
  const score = `<p class="overlay-score">일치율<b>${esc(result.match_score)}%</b></p>`;
  if (correct) {
    const next = state.state === "training" && state.target_signal !== result.signal ? state.target_signal : null;
    body = `
      ${verdict(ICON_CHECK, "정답입니다")}
      <div class="ov-data">
        ${score}
        ${info.picar ? `<p class="overlay-picar"><span class="chip">picar</span><strong>${esc(info.picar)}</strong></p>` : ""}
        <p class="overlay-next">${next ? `다음 수신호: ${esc(signLabel(next))}` : "모든 수신호를 마쳤습니다"}</p>
      </div>
      ${timer}`;
  } else if (result.given_up) {
    // 재시도 상한 초과: 같은 수신호를 다시 보여주지 않고 다음으로 넘어간다(state_machine.py MAX_ATTEMPTS_PER_SIGNAL)
    // 표시 전용(2026-10-02): 백엔드 문구("…다시 시도하세요")는 실제 동작(다음 수신호로 이동)과 반대라 제목으로 쓰지 않고,
    // 판정 단어 자리에 실제로 일어나는 일을, 데이터 열에 사유(오답/시간 초과)와 시도 수를 적는다.
    const why = result.outcome === "timeout" ? "시간 초과" : "오답";
    body = `
      ${verdict(ICON_X, "다음 수신호로 넘어갑니다")}
      <div class="ov-data">
        ${score}
        <dl class="overlay-stats">
          <div><dt>마지막 판정</dt><dd>${why}</dd></div>
          <div><dt>사용한 시도</dt><dd>${esc(result.attempt)}${state.max_attempts ? ` / ${esc(state.max_attempts)}` : ""}회</dd></div>
        </dl>
        <p class="overlay-next">시도 횟수를 모두 써서 이 수신호는 불합격입니다</p>
      </div>
      ${timer}`;
  } else {
    // 오답(SC-03b). below_tau / out_of_distribution은 오버레이 대신 showHoldHint()로 문구만 띄운다(스펙 §5)
    // 표시 전용(2026-10-02): 시간 초과는 백엔드 문구("시간이 초과됐습니다 — 다시 시도하세요")를 판정 단어로 쓰지 않고
    // given_up 분기와 같은 방식으로 판정 단어 "시간 초과" + 데이터 열 "다시 시도하세요"로 나눠 적는다.
    const timeout = result.outcome === "timeout";
    const word = timeout ? "시간 초과" : esc(result.message ?? "다시 시도하세요");
    body = `
      ${verdict(ICON_X, word)}
      <div class="ov-data">
        ${score}
        <dl class="overlay-stats">
          <div><dt>현재 시도</dt><dd>${esc(result.attempt)}${state.max_attempts ? ` / ${esc(state.max_attempts)}` : ""}회</dd></div>
          <div><dt>권장 재도전</dt><dd>${esc(result.recommended_retry)}회</dd></div>
        </dl>
        <p class="overlay-next">${timeout ? "다시 시도하세요. " : ""}AI Hand가 다시 보여 줍니다</p>
      </div>
      ${timer}`;
  }

  overlay.className = `overlay ${correct ? "correct" : "wrong"}`;
  overlay.innerHTML = `<div class="overlay-card">${body}</div>`;
  setTimeout(() => {
    if (myGen === overlayGen) {
      overlay.classList.add("hidden");
      if (lastTrainingState) renderPhase(lastTrainingState);   // 다음 시범(또는 재시범) + 확인 버튼으로
    }
  }, holdMs);
}

// SC-04 재시도 — 시범 단계(AI Hand 재시범 + 확인 버튼)로 돌아간다(state_machine.py _camera_retry).
async function cameraRetry() {
  if (retryInFlight) return;
  retryInFlight = true;
  try {
    await apiPost("/api/camera_retry");
    await refreshTraining();
  } finally {
    retryInFlight = false;
  }
}

$("camera-retry-btn").addEventListener("click", (event) => {
  event.currentTarget.blur();
  cameraRetry();
});

// ---- SC-05 — 결과는 회원 기록(Supabase)에 자동 저장 (예전 CSV 내려받기를 대신한다) ----

function firstTry(item) {
  return item.attempts === 1 && !item.given_up;
}

function renderSummary(state) {
  const completed = state.completed || [];
  const first = completed.filter(firstTry).length;
  const gaveUp = completed.filter((c) => c.given_up).length;
  $("summary-sub").textContent =
    `합격 ${completed.length - gaveUp} / ${completed.length}종, 첫 시도 정답 ${first}종${gaveUp ? `, 불합격 ${gaveUp}종` : ""}`;
  // 표시 전용: 성적서 KPI 띠 (합격 n/7, 첫 시도 정답, 총 시도)
  $("kpi-pass").textContent = completed.length - gaveUp;
  $("kpi-of").textContent = `/ ${completed.length}종`;
  $("kpi-first").textContent = first;
  $("kpi-attempts").textContent = completed.reduce((sum, c) => sum + (Number(c.attempts) || 0), 0);

  const tbody = $("summary-tbody");
  tbody.innerHTML = "";
  completed.forEach((item) => {
    const tr = document.createElement("tr");
    const score = Math.max(0, Math.min(100, item.match_score || 0));
    const delta = score - tauPct();
    // given_up: 재시도 상한 초과로 넘어간 수신호. match_score는 마지막 오답의 값이라 "정답 시 일치율"이 아니다
    // 합격 = 시도 상한(3회) 안에 정답, 불합격 = 상한을 넘겨 넘어감. DB training_results.passed와 같은 정의
    // 일치율은 트랙 없는 숫자 + 판정 기준(τ) 대비 차이로 적는다
    tr.className = item.given_up ? "is-fail" : "";
    tr.innerHTML = `
      <td><span class="col-sign"><span class="hand-fig sm">${handSvg(item.signal)}</span>${esc(signLabel(item.signal))}</span></td>
      <td>${item.given_up ? '<span class="result-chip fail">불합격</span>' : '<span class="result-chip pass">합격</span>'}</td>
      <td class="col-attempts"><b>${esc(item.attempts)}</b>회${firstTry(item) ? `<span class="first-mark" title="첫 시도 정답">${ICON_CHECK}<span class="sr-only">첫 시도 정답</span></span>` : ""}</td>
      <td class="col-score"><b>${score}</b>%<small>${delta >= 0 ? "+" : "−"}${Math.abs(delta)}</small></td>`;
    tbody.appendChild(tr);
  });
  renderSaveStatus(state);
}

function renderSaveStatus(state) {
  const el = $("save-status");
  const who = state.member;
  const save = (state.result_save || {}).last_save;
  const pending = (state.result_save || {}).pending || 0;
  let cls = "pending";
  let title = "회원 기록에 저장하는 중…";
  let sub = "";
  let final = false;

  if (!who || who.guest) {
    cls = "local"; final = true;
    title = "게스트 학습";
    sub = "게스트 학습 기록은 회원 기록에 저장되지 않습니다.";
  } else if (save && save.status === "saved") {
    cls = "saved"; final = true;
    title = `${who.member_code} 회원 기록에 저장했습니다`;
    sub = `${who.name} 님의 학습 기록으로 저장되었습니다.`;
  } else if (save && save.status === "saved_local") {
    cls = "local"; final = true;
    title = "이 교육장 기기에 저장했습니다";
    sub = "회원 기록 서버에 연결되지 않아 학습 기록을 이 기기에만 저장했습니다.";
  } else if (save && save.status === "queued") {
    cls = "queued";
    title = "인터넷 연결을 기다리는 중";
    sub = `연결되면 자동으로 회원 기록에 저장됩니다(대기 ${pending}건). 화면을 닫아도 기록은 남습니다.`;
  } else if (save && save.status === "failed") {
    cls = "failed"; final = true;
    title = "회원 기록에 저장하지 못했습니다";
    sub = "교육 담당자에게 알려 주세요. 기록은 교육장 기기에 따로 보관되어 있습니다.";
  }
  el.className = `save-status ${cls}`;
  el.innerHTML = `<div><b>${esc(title)}</b>${esc(sub)}</div>`;
  $("save-retry-btn").classList.toggle("hidden", cls !== "queued");
  return final;
}

function startSavePolling() {
  stopSavePolling();
  saveTimer = setInterval(async () => {
    try {
      const state = await apiGet("/api/state");
      if (renderSaveStatus(state)) stopSavePolling();
    } catch (err) { /* 다음에 다시 */ }
  }, SAVE_POLL_MS);
}

function stopSavePolling() {
  if (saveTimer) {
    clearInterval(saveTimer);
    saveTimer = null;
  }
}

$("save-retry-btn").addEventListener("click", async (event) => {
  const btn = event.currentTarget;
  btn.disabled = true;
  try {
    await apiPost("/api/auth/results/retry");
    renderSaveStatus(await apiGet("/api/state"));
  } finally {
    btn.disabled = false;
  }
});

$("certificate-btn").addEventListener("click", async () => {
  const result = await apiPost("/api/certificate");
  if (result.status !== "ok") return;
  await drawCertificate(result.completed, result.issued_at);
  show("screen-certificate");
});

// ---- SC-06 ----

// 웹 화면과 같은 디자인 언어: Industrial Black 머리띠 + 안전 표지 사선 띠, 강철 회색 라벨, 합격 칩·일치율 막대.
// A4 가로 비율(1123×794 논리 크기)을 2배로 그려 인쇄·이미지 저장에도 선명하다.
// 발급 기관 "주식회사 심기일전"은 시연용 가상 기관이다(팀 이름) — 증서 하단에 그렇게 적는다.
const CERT = { w: 1123, h: 794, scale: 2 };
const CERT_C = {
  paper: "#F8FAFC", ink: "#0F172A", ink2: "#334155", steel: "#64748B", steelLight: "#94A3B8",
  line: "#E2E8F0", orange: "#EA580C", green: "#15803D", greenBg: "#E3F4E8", red: "#C62828", redBg: "#FBE7E7",
  seal: "#C62828",
};
const CERT_SANS = '"Inter Variable", "SUIT Variable", "Pretendard Variable", "Malgun Gothic", "맑은 고딕", system-ui, sans-serif';
const CERT_KR = '"SUIT Variable", "Pretendard Variable", "Malgun Gothic", "맑은 고딕", system-ui, sans-serif';
const CERT_MONO = '"JetBrains Mono", "Cascadia Mono", Consolas, ui-monospace, monospace';

function pad2(n) { return String(n).padStart(2, "0"); }

function certNumber(code, d) {
  const stamp = `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}-${pad2(d.getHours())}${pad2(d.getMinutes())}`;
  return `${code || "GUEST"}-${stamp}`;
}

// 글자를 폭 안에서 줄바꿈 (한글은 글자 단위로도 끊는다)
function wrapLines(ctx, text, maxWidth) {
  const lines = [];
  let line = "";
  for (const word of text.split(" ")) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width <= maxWidth) { line = test; continue; }
    if (line) lines.push(line);
    line = word;
  }
  if (line) lines.push(line);
  return lines;
}

function hazardBand(ctx, x, y, w, h) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();
  ctx.fillStyle = CERT_C.ink;
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = CERT_C.orange;
  for (let sx = x - h; sx < x + w + h; sx += 20) {
    ctx.beginPath();
    ctx.moveTo(sx, y + h);
    ctx.lineTo(sx + 10, y + h);
    ctx.lineTo(sx + 10 + h, y);
    ctx.lineTo(sx + h, y);
    ctx.closePath();
    ctx.fill();
  }
  ctx.restore();
}

// 직인 — 붉은 정사각 도장. 찍힌 느낌을 위해 살짝 기울이고, 종이색 점으로 인주가 덜 묻은 자리를 만든다(사원 코드로 정해진 무늬).
function drawSeal(ctx, cx, cy, size, seedText) {
  let seed = [...(seedText || "SAFESIGN")].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) >>> 0, 7);
  const rand = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(-0.07);
  ctx.globalCompositeOperation = "multiply";
  ctx.globalAlpha = 0.9;
  ctx.strokeStyle = CERT_C.seal;
  ctx.fillStyle = CERT_C.seal;
  const s = size / 2;
  ctx.lineWidth = 4;
  ctx.strokeRect(-s, -s, size, size);
  ctx.lineWidth = 1.4;
  ctx.strokeRect(-s + 6, -s + 6, size - 12, size - 12);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `800 ${Math.round(size * 0.17)}px ${CERT_KR}`;
  ["심기일전", "교육센터", "직    인"].forEach((t, i) => ctx.fillText(t, 0, -s + size * (0.29 + i * 0.21)));
  ctx.globalCompositeOperation = "source-over";
  ctx.globalAlpha = 0.55;
  ctx.fillStyle = CERT_C.paper;
  for (let i = 0; i < 90; i++) {
    const r = rand() * 1.6 + 0.4;
    ctx.beginPath();
    ctx.arc((rand() - 0.5) * size, (rand() - 0.5) * size, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

async function drawCertificate(completed, issuedAt) {
  // 캔버스는 CSS 글꼴이 준비되기 전에 그리면 대체 글꼴로 굳어 버린다
  try {
    await Promise.all([
      document.fonts.load(`800 40px "SUIT Variable"`), document.fonts.load(`700 20px "Inter Variable"`),
    ]);
  } catch (err) { /* 글꼴이 없어도 대체 글꼴로 그린다 */ }

  const canvas = $("certificate-canvas");
  canvas.width = CERT.w * CERT.scale;
  canvas.height = CERT.h * CERT.scale;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(CERT.scale, 0, 0, CERT.scale, 0, 0);
  const W = CERT.w, H = CERT.h, L = 56, R = W - 56;
  const issued = new Date((issuedAt || Date.now() / 1000) * 1000);
  const guest = !member || member.guest;
  const code = guest ? "" : member.member_code;
  const passed = completed.filter((c) => !c.given_up).length;
  const first = completed.filter(firstTry).length;

  // 종이 · 머리띠 · 사선 띠
  ctx.fillStyle = CERT_C.paper;
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = CERT_C.ink;
  ctx.fillRect(0, 0, W, 104);
  hazardBand(ctx, 0, 104, W, 10);
  ctx.fillStyle = CERT_C.orange;
  ctx.fillRect(0, H - 6, W, 6);

  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  ctx.fillStyle = CERT_C.paper;
  ctx.font = `800 36px ${CERT_SANS}`;
  ctx.letterSpacing = "-1px";
  ctx.fillText("SafeSign", L, 66);
  const markW = ctx.measureText("SafeSign").width;
  ctx.letterSpacing = "0px";
  ctx.fillStyle = CERT_C.orange;
  ctx.fillRect(L + markW + 5, 57, 9, 9);

  ctx.textAlign = "right";
  ctx.fillStyle = CERT_C.steelLight;
  ctx.font = `600 12px ${CERT_SANS}`;
  ctx.letterSpacing = "2.5px";
  ctx.fillText("CERTIFICATE OF COMPLETION", R, 46);
  ctx.letterSpacing = "0px";
  ctx.fillStyle = CERT_C.paper;
  ctx.font = `700 19px ${CERT_KR}`;
  ctx.fillText("산업 안전 수신호 교육", R, 74);

  // ── 왼쪽: 제목 · 수료자 정보 · 증명 문구
  ctx.textAlign = "left";
  ctx.fillStyle = CERT_C.steel;
  ctx.font = `600 12px ${CERT_MONO}`;
  ctx.fillText(`No. ${certNumber(code, issued)}`, L, 164);
  ctx.fillStyle = CERT_C.ink;
  ctx.font = `800 70px ${CERT_KR}`;
  ctx.letterSpacing = "6px";
  ctx.fillText("수료증", L - 3, 238);
  ctx.letterSpacing = "0px";

  const when = `${issued.getFullYear()}. ${pad2(issued.getMonth() + 1)}. ${pad2(issued.getDate())}.  ${pad2(issued.getHours())}:${pad2(issued.getMinutes())}`;
  const rows = [
    ["성명", guest ? "게스트 학습자" : member.name],
    ["사원 코드", guest ? "게스트" : code],
    ["소속", (!guest && member.org) ? member.org : "없음"],
    ["수료 일시", when],
  ];
  let y = 292;
  rows.forEach(([label, value]) => {
    ctx.fillStyle = CERT_C.steel;
    ctx.font = `600 12.5px ${CERT_KR}`;
    ctx.fillText(label, L, y);
    ctx.fillStyle = CERT_C.ink;
    ctx.font = label === "사원 코드" && !guest ? `700 21px ${CERT_MONO}` : `700 22px ${CERT_SANS}`;   // 게스트는 한글이라 고정폭(라틴) 글꼴 대신 본문 글꼴
    ctx.fillText(value, L + 108, y + 1);
    ctx.fillStyle = CERT_C.line;
    ctx.fillRect(L, y + 18, 480, 1);
    y += 54;
  });

  ctx.fillStyle = CERT_C.ink2;
  ctx.font = `500 16px ${CERT_KR}`;
  const statement = `위 사람은 SafeSign 산업 안전 수신호 교육 과정(크레인 작업표준신호 5종 + 자체 지정 2종)을 이수하였기에 이 증서를 수여합니다.`;
  wrapLines(ctx, statement, 480).forEach((line, i) => ctx.fillText(line, L, 540 + i * 27));
  ctx.fillStyle = CERT_C.steel;
  ctx.font = `500 12px ${CERT_KR}`;
  ctx.fillText("이수 기준: 수신호 7종 전 과정. 합격은 수신호마다 시도 3회 안에 정답", L, 624);

  // ── 오른쪽: 교육 결과표
  const TX = 620, TR = R;
  ctx.fillStyle = CERT_C.ink;
  ctx.font = `800 16px ${CERT_KR}`;
  ctx.fillText("교육 결과", TX, 164);
  ctx.textAlign = "right";
  ctx.fillStyle = CERT_C.steel;
  ctx.font = `600 13px ${CERT_KR}`;
  ctx.fillText(`합격 ${passed} / ${completed.length}종, 첫 시도 정답 ${first}종`, TR, 164);

  const col = { sign: TX, result: TX + 178, tries: TX + 258, meter: TX + 316 };
  ctx.textAlign = "left";
  ctx.font = `600 11.5px ${CERT_KR}`;
  ctx.fillStyle = CERT_C.steel;
  [["수신호", col.sign], ["결과", col.result], ["시도", col.tries], ["일치율", col.meter]].forEach(([t, x]) => ctx.fillText(t, x, 196));
  ctx.fillStyle = CERT_C.ink;
  ctx.fillRect(TX, 206, TR - TX, 1.5);

  y = 238;
  completed.forEach((item) => {
    const fail = Boolean(item.given_up);
    ctx.textAlign = "left";
    ctx.fillStyle = CERT_C.ink;
    ctx.font = `700 16px ${CERT_KR}`;
    ctx.fillText(String(item.signal).replace(/_/g, " "), col.sign, y);

    // 결과 칩 — 색과 글자를 함께
    const label = fail ? "불합격" : "합격";
    ctx.font = `700 12px ${CERT_KR}`;
    const cw = ctx.measureText(label).width + 16;
    ctx.fillStyle = fail ? CERT_C.redBg : CERT_C.greenBg;
    ctx.fillRect(col.result, y - 16, cw, 22);
    ctx.strokeStyle = fail ? CERT_C.red : CERT_C.green;
    ctx.lineWidth = 1;
    ctx.strokeRect(col.result + 0.5, y - 15.5, cw - 1, 21);
    ctx.fillStyle = fail ? CERT_C.red : CERT_C.green;
    ctx.fillText(label, col.result + 8, y);

    ctx.fillStyle = CERT_C.ink;
    ctx.font = `600 15px ${CERT_SANS}`;
    ctx.fillText(`${item.attempts}회`, col.tries, y);

    // 일치율 막대 — 웹과 같이 한 색 채움 + 옅은 트랙, 판정 기준(τ) 눈금
    const score = Math.max(0, Math.min(100, item.match_score || 0));
    const mw = 80, mx = col.meter;
    ctx.fillStyle = "rgba(242, 140, 40, 0.18)";
    ctx.fillRect(mx, y - 9, mw, 7);
    ctx.fillStyle = fail ? CERT_C.steelLight : CERT_C.orange;
    ctx.fillRect(mx, y - 9, mw * score / 100, 7);
    ctx.fillStyle = CERT_C.ink;
    ctx.fillRect(mx + mw * judgeRule.tau, y - 12, 1.5, 13);
    ctx.textAlign = "right";
    ctx.font = `700 15px ${CERT_SANS}`;
    ctx.fillText(`${score}%`, TR, y);

    ctx.fillStyle = CERT_C.line;
    ctx.fillRect(TX, y + 14, TR - TX, 1);
    y += 44;
  });
  ctx.textAlign = "left";
  ctx.fillStyle = CERT_C.steel;
  ctx.font = `500 11.5px ${CERT_KR}`;
  ctx.fillText(`판정: 카메라 AI 비전, ${judgeRule.n_frames}프레임 연속 확정. 막대의 눈금 = 판정 기준 ${tauPct()}%`, TX, y + 8);

  // ── 하단: 발급일 · 발급 기관 · 직인
  ctx.fillStyle = CERT_C.ink;
  ctx.fillRect(L, 668, R - L, 1.5);
  ctx.textAlign = "left";
  ctx.font = `800 20px ${CERT_KR}`;
  ctx.fillText(`${issued.getFullYear()}년 ${issued.getMonth() + 1}월 ${issued.getDate()}일`, L, 712);
  ctx.fillStyle = CERT_C.steel;
  ctx.font = `500 12px ${CERT_KR}`;
  ctx.fillText(`발급 ${when}:${pad2(issued.getSeconds())}`, L, 736);

  const sealCx = R - 40, sealCy = 712;
  ctx.textAlign = "right";
  ctx.fillStyle = CERT_C.ink;
  ctx.font = `800 24px ${CERT_KR}`;
  ctx.fillText("주식회사 심기일전", sealCx - 58, 708);
  ctx.fillStyle = CERT_C.ink2;
  ctx.font = `600 14px ${CERT_KR}`;
  ctx.fillText("산업안전교육센터장", sealCx - 58, 732);
  drawSeal(ctx, sealCx, sealCy, 84, code || "GUEST");

  ctx.textAlign = "left";
  ctx.fillStyle = CERT_C.steelLight;
  ctx.font = `500 10.5px ${CERT_KR}`;
  ctx.fillText("※ SafeSign 교육 시연용으로 발급한 증서입니다. 발급 기관은 가상 기관입니다.", L, H - 20);
}

$("certificate-download-btn").addEventListener("click", () => {
  const link = document.createElement("a");
  link.download = `safesign-certificate${member && member.member_code ? `-${member.member_code}` : ""}.png`;
  link.href = $("certificate-canvas").toDataURL("image/png");
  link.click();
});

$("certificate-print-btn").addEventListener("click", () => window.print());
$("restart-btn").addEventListener("click", () => goCurriculum());      // 같은 학습자로 다시
$("finish-btn").addEventListener("click", () => logout());             // 다음 학습자를 위해 로그아웃

// ---- 상단 관제 시계 ----
function tickClock() {
  const d = new Date();
  $("sys-clock").textContent = [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}
tickClock();
setInterval(tickClock, 1000);

paintHands(document);   // 표시 전용: SC-01 실측 손 관절 띠(data-hand)
init();
