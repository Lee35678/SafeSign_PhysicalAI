// SafeSign 회사 사이트: 화면 전환(#/경로), 로그인/가입/찾기, 내 정보, 수료증.
// 백엔드: services/portal/app/main.py (/api/auth/*, /api/session, /api/me). 회원 규칙은 교육장 web과 같다(members.py).
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// 교육 과정 7종: 교육장 web(state_machine CURRICULUM_INFO, main.js SIGN_PATTERNS)과 같은 정의 (10_PRD §3.2)
const SIGNALS = [
  { name: "정지", fingers: [1, 1, 1, 1, 1], aihand: "다섯 손가락 펴기 + 정면", picar: "정지, 양쪽 적색 LED 점등", source: "크레인 작업표준신호" },
  { name: "서행", fingers: [0, 1, 1, 0, 0], aihand: "검지 + 중지 펴기 + 정면", picar: "감속 주행, 양쪽 황색 LED 점멸", source: "크레인 작업표준신호" },
  { name: "좌회전 유도", fingers: [1, 1, 0, 0, 0], aihand: "엄지 + 검지 펴기", picar: "좌회전 주행, 좌측 황색 LED 점멸", source: "크레인 작업표준신호" },
  { name: "우회전 유도", fingers: [1, 0, 0, 0, 1], aihand: "엄지 + 소지 펴기", picar: "우회전 주행, 우측 황색 LED 점멸", source: "크레인 작업표준신호" },
  { name: "확인 완료", fingers: [0, 0, 0, 0, 0], aihand: "다섯 손가락 접기(주먹) + 정면", picar: "정지, 적색과 황색 LED 전부 점멸", source: "크레인 작업표준신호" },
  { name: "후진", fingers: [0, 1, 0, 0, 0], aihand: "검지만 펴기", picar: "후진 주행", source: "자체 지정" },
  { name: "주의", fingers: [0, 0, 0, 0, 1], aihand: "소지(새끼손가락)만 펴기", picar: "정지, 양쪽 황색 LED 점멸", source: "자체 지정" },
];
const FINGER_NAMES = ["엄지", "검지", "중지", "약지", "소지"];

// 최종 KPI (05_모델카드 §7-3, 2026-09-30): 팀원 3명 210시도, 공식 3연속. 수치는 바꾸지 않는다
const KPI = [
  { name: "정답률", target: "≥ 92%", value: 95.2, unit: "%", goal: 92, better: "high", ci: "91.5-97.4%" },
  { name: "오분류율", target: "≤ 3%", value: 0.0, unit: "%", goal: 3, better: "low", ci: "상한 1.8%" },
  { name: "미판정률", target: "≤ 5%", value: 4.8, unit: "%", goal: 5, better: "low", ci: "2.6-8.5%" },
  { name: "Macro F1", target: "≥ 0.90", value: 0.974, unit: "", goal: 0.9, better: "high", ci: "" },
  { name: "치명 오분류 (정지 → 다른 신호)", target: "0건", value: 0, unit: "건", goal: 0, better: "zero", ci: "정지 30시도, 상한 11.4%" },
];

let session = null;       // {member_code, name} | null
let storeBackend = null;
let meCache = null;

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-SafeSign-Portal": "1" },
  };
  const res = await fetch(path, { credentials: "same-origin", ...opts });
  let data = {};
  try { data = await res.json(); } catch (err) { /* 본문 없음 */ }
  return { ok: res.ok, status: res.status, data };
}

// ── 머리글 ──
function renderAccount() {
  $("acct-out").classList.toggle("hidden", Boolean(session));
  $("acct-in").classList.toggle("hidden", !session);
  if (session) {
    $("acct-code").textContent = session.member_code;
    $("acct-name").textContent = `${session.name} 님`;
  }
}

async function refreshSession() {
  const { data } = await api("/api/session");
  session = data.member || null;
  storeBackend = data.store && data.store.backend;
  renderAccount();
}

$("logout-btn").addEventListener("click", async () => {
  await api("/api/auth/logout", {});
  session = null;
  meCache = null;
  renderAccount();
  location.hash = "#/";
});

// ── 홈: 손 관절 띠, 교육 과정 레지스터, 검증 결과 리드아웃 (표시 전용) ──
// Phosphor Icons 2.1.1 (MIT, icons/LICENSE.txt): 상태 라벨에 글자와 함께 쓴다
const ICON = {
  check: '<svg class="ic" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true" focusable="false"><path d="M173.66,98.34a8,8,0,0,1,0,11.32l-56,56a8,8,0,0,1-11.32,0l-24-24a8,8,0,0,1,11.32-11.32L112,148.69l50.34-50.35A8,8,0,0,1,173.66,98.34ZM232,128A104,104,0,1,1,128,24,104.11,104.11,0,0,1,232,128Zm-16,0a88,88,0,1,0-88,88A88.1,88.1,0,0,0,216,128Z"/></svg>',
  x: '<svg class="ic" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true" focusable="false"><path d="M165.66,101.66,139.31,128l26.35,26.34a8,8,0,0,1-11.32,11.32L128,139.31l-26.34,26.35a8,8,0,0,1-11.32-11.32L116.69,128,90.34,101.66a8,8,0,0,1,11.32-11.32L128,116.69l26.34-26.35a8,8,0,0,1,11.32,11.32ZM232,128A104,104,0,1,1,128,24,104.11,104.11,0,0,1,232,128Zm-16,0a88,88,0,1,0-88,88A88.1,88.1,0,0,0,216,128Z"/></svg>',
  clock: '<svg class="ic" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true" focusable="false"><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216Zm64-88a8,8,0,0,1-8,8H128a8,8,0,0,1-8-8V72a8,8,0,0,1,16,0v48h48A8,8,0,0,1,192,128Z"/></svg>',
};

function fingerIcon(pattern) {
  const label = FINGER_NAMES.map((f, i) => `${f} ${pattern[i] ? "폄" : "접음"}`).join(", ");
  return `<span class="fingers" role="img" aria-label="${esc(label)}">${pattern.map((p) => `<i class="${p ? "up" : ""}"></i>`).join("")}</span>`;
}

// 실측 손 관절 21점(hand-data.js SAFESIGN_HAND)을 SVG로 그린다. 편 손가락의 뼈대는 밝게, 끝마디는 주황.
// 점 번호: 0 손목, 1-4 엄지, 5-8 검지, 9-12 중지, 13-16 약지, 17-20 소지 (MediaPipe Hands)
function handSvg(name, fingers, label) {
  const data = typeof SAFESIGN_HAND === "undefined" ? null : SAFESIGN_HAND.signals[name.replace(/ /g, "_")];
  if (!data) return "";
  const pt = data.map(([x, y]) => [(x * 100).toFixed(1), (y * 100).toFixed(1)]);
  const fingerOf = (i) => (i === 0 ? -1 : Math.floor((i - 1) / 4));
  const bones = SAFESIGN_HAND.connections.map(([a, b]) => {
    const f = a === 0 || fingerOf(a) !== fingerOf(b) ? -1 : fingerOf(b);   // 손목에서 나가는 선과 손바닥 가로선은 손바닥
    return `<line class="${f >= 0 && fingers[f] ? "up" : ""}" x1="${pt[a][0]}" y1="${pt[a][1]}" x2="${pt[b][0]}" y2="${pt[b][1]}"/>`;
  }).join("");
  const joints = pt.map(([x, y], i) => {
    const up = i === 0 || fingers[fingerOf(i)];
    const tip = i > 0 && i % 4 === 0 && fingers[i / 4 - 1];
    return `<circle class="${tip ? "tip" : up ? "up" : ""}" cx="${x}" cy="${y}" r="${tip ? 3.4 : up ? 2 : 1.5}"/>`;
  }).join("");
  const a11y = label ? `role="img" aria-label="${esc(label)}"` : `aria-hidden="true" focusable="false"`;
  return `<svg class="hand" viewBox="-8 -8 116 116" ${a11y}>${bones}${joints}</svg>`;
}

const SIGNAL_GROUPS = [
  { source: "크레인 작업표준신호", title: "크레인 작업표준신호", cls: "reg-std" },
  { source: "자체 지정", title: "자체 지정", cls: "reg-own" },
];

function renderHome() {
  // 7종 목록: 번호 + 실측 손 관절 + 이름 + 손가락 패턴. 누르면 7종 영상이 그 신호로 이동한다
  const strip = $("hand-strip");
  if (strip) {
    strip.innerHTML = SIGNALS.map((s, i) => `
      <li><button class="hi" type="button" data-reel="${i}" aria-label="${esc(s.name)} 손모양 보기">
        <span class="hi-no">${String(i + 1).padStart(2, "0")}</span>${handSvg(s.name, s.fingers, "")}<span class="hi-name">${esc(s.name)}</span>${fingerIcon(s.fingers)}</button></li>`).join("");
  }

  // 교육 과정: 크레인 표준 5종 / 자체 지정 2종 두 묶음 (번호 = 실제 교육 순서)
  $("signal-rows").innerHTML = SIGNAL_GROUPS.map((g) => {
    const list = SIGNALS.filter((s) => s.source === g.source);
    return `<div class="reg-group ${g.cls}">
      <h3 class="reg-head">${esc(g.title)} <span>${list.length}종</span></h3>
      <ol class="reg-list">${list.map((s) => `
        <li><span class="reg-no">${SIGNALS.indexOf(s) + 1}</span>${fingerIcon(s.fingers)}<b class="reg-name">${esc(s.name)}</b>
          <span class="reg-cell"><small>AI Hand 시범</small>${esc(s.aihand)}</span>
          <span class="reg-cell"><small>picar 동작</small>${esc(s.picar)}</span></li>`).join("")}
      </ol></div>`;
  }).join("");

  // 검증 결과: 측정값을 크게, 목표와 95% 구간은 작게, 달성 여부는 글자 + 아이콘 (채운 막대 없음)
  $("kpi-rows").innerHTML = KPI.map((k) => {
    const met = k.better === "high" ? k.value >= k.goal : k.value <= k.goal;
    const num = k.unit === "" ? k.value.toFixed(3) : String(k.value);
    const lead = k.name === "오분류율";
    // 표시 전용: 이름 끝 괄호 묶음, 예: '(정지 → 다른 신호)'는 좁은 화면에서도 한 줄로 둔다
    const name = esc(k.name).replace(/ \(([^)]+)\)$/, ' <span class="nw">($1)</span>');
    return `<div class="kpi${lead ? " kpi-lead" : ""}">
      <p class="kpi-name">${name}</p>
      <p class="kpi-val">${esc(num)}${k.unit ? `<small>${esc(k.unit)}</small>` : ""}</p>
      ${lead ? '<p class="kpi-sub">210시도 중 다른 신호로 잘못 판정한 경우 0건</p>' : ""}
      <dl class="kpi-meta">
        <div><dt>목표</dt><dd>${esc(k.target)}${k.better === "low" ? ' <small class="dir">낮을수록 좋음</small>' : ""}</dd></div>
        ${k.ci ? `<div><dt>95% 신뢰구간</dt><dd>${esc(k.ci)}</dd></div>` : ""}
      </dl>
      <p class="kpi-state">${met ? `<span class="pass">${ICON.check}달성</span>` : `<span class="fail">${ICON.x}미달</span>`}</p>
    </div>`;
  }).join("");
}

// 아직 없는 화면 캡처(img/*.png)는 깨진 그림 대신 빈 베젤 패널로 둔다 (표시 전용)
document.querySelectorAll("img.shot-img").forEach((img) => {
  const missing = () => img.closest(".shot").classList.add("is-missing");
  if (img.complete && img.naturalWidth === 0) missing();
  else img.addEventListener("error", missing);
});

// ── 화면 전환 ──
const SECTIONS = ["product", "curriculum", "results", "company", "contact"];
const AUTH_FORMS = { login: "login-form", signup: "signup-form", "find-id": "find-id-form", reset: "reset-request-form", "reset-confirm": "reset-confirm-form" };
const AUTH_TITLES = { login: "로그인", signup: "회원가입", "find-id": "아이디 찾기", reset: "비밀번호 찾기", "reset-confirm": "새 비밀번호" };

function showView(id) {
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.id !== id));
}

async function route() {
  const path = (location.hash || "#/").replace(/^#\/?/, "");
  const [head, arg] = path.split("/");
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("on", a.getAttribute("href") === `#/${head}`));
  markCurrent(head);

  if (!head || SECTIONS.includes(head)) {
    showView("view-home");
    if (head) {
      const target = document.getElementById(head);
      target.scrollIntoView({ behavior: scrollMotion(), block: "start" });
      focusHeading(target.querySelector("h2"));
    } else window.scrollTo({ top: 0 });
    return;
  }
  if (AUTH_FORMS[head]) {
    if (session && head !== "reset-confirm") { location.hash = "#/me"; return; }
    showAuth(head);
    return;
  }
  if (head === "me") { await showMe(); return; }
  if (head === "certificate") { await showCertificate(arg); return; }
  location.hash = "#/";
}

window.addEventListener("hashchange", route);

// 표시 전용: 움직임 줄이기 설정이면 부드러운 스크롤을 쓰지 않는다
function scrollMotion() {
  return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}

// 표시 전용: 현재 위치를 보조 기술에도 알린다 (메뉴는 aria-current, 머리글 계정 링크는 현재 화면이면 흐리게)
function markCurrent(head) {
  document.querySelectorAll(".nav a, #acct-out a").forEach((a) => {
    if (a.getAttribute("href") === `#/${head}`) a.setAttribute("aria-current", a.closest(".nav") ? "location" : "page");
    else a.removeAttribute("aria-current");
  });
}

// 표시 전용: 화면이 바뀌면 새 화면 제목으로 포커스를 옮겨 스크린리더가 제목부터 읽게 한다 (스크롤은 그대로)
function focusHeading(el) {
  if (!el) return;
  if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
  el.classList.add("route-focus");
  el.focus({ preventScroll: true });
}

// 표시 전용: 건너뛰기 링크는 해시를 바꾸지 않고 본문(main)으로 포커스만 옮긴다 (해시 '#main'은 route()가 홈으로 돌려보냄)
document.querySelector(".skip").addEventListener("click", (e) => {
  e.preventDefault();
  $("main").focus({ preventScroll: true });
});

// 표시 전용: 비밀번호 재설정 성공 안내는 #login-error에 들어가지만 오류가 아니므로 안내 모양(role=status)으로 보인다
function loginNotice(on) {
  $("login-error").classList.toggle("is-notice", on);
  $("login-error").setAttribute("role", on ? "status" : "alert");
}

// ── 로그인, 가입, 찾기 ──
function showAuth(view) {
  showView("view-auth");
  window.scrollTo({ top: 0 });
  $("auth-title").textContent = AUTH_TITLES[view];
  $("store-note").classList.toggle("hidden", storeBackend !== "local");
  Object.entries(AUTH_FORMS).forEach(([k, id]) => $(id).classList.toggle("hidden", k !== view));
  const first = $(AUTH_FORMS[view]).querySelector("input");
  if (first) first.focus();
}

function passwordProblem(pw, pw2) {
  if (pw.length < 8) return "비밀번호는 8자 이상이어야 합니다.";
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "비밀번호에 영문과 숫자를 함께 넣어 주세요.";
  if (pw2 !== undefined && pw !== pw2) return "비밀번호 확인이 일치하지 않습니다.";
  return "";
}

async function submitForm(form, errorId, run) {
  const btn = form.querySelector("button[type=submit]");
  $(errorId).textContent = "";
  btn.disabled = true;
  try {
    await run();
  } catch (err) {
    $(errorId).textContent = "서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.";
  } finally {
    btn.disabled = false;
  }
}

$("login-form").addEventListener("submit", (e) => {
  e.preventDefault();
  loginNotice(false);
  submitForm(e.target, "login-error", async () => {
    const { data } = await api("/api/auth/login", { email: $("login-email").value, password: $("login-password").value });
    if (data.status !== "ok") { $("login-error").textContent = data.message || "로그인하지 못했습니다."; return; }
    $("login-password").value = "";
    session = { member_code: data.member.member_code, name: data.member.name };
    renderAccount();
    location.hash = "#/me";
  });
});

$("signup-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const pw = $("signup-password").value;
  const problem = !$("signup-name").value.trim() ? "이름을 입력해 주세요." : passwordProblem(pw, $("signup-password2").value);
  if (problem) { $("signup-error").textContent = problem; return; }
  submitForm(e.target, "signup-error", async () => {
    const { data } = await api("/api/auth/signup", {
      name: $("signup-name").value, org: $("signup-org").value, email: $("signup-email").value, password: pw,
    });
    if (data.status !== "ok") { $("signup-error").textContent = data.message || "가입하지 못했습니다."; return; }
    e.target.reset();
    session = { member_code: data.member.member_code, name: data.member.name };
    renderAccount();
    location.hash = "#/me";
  });
});

$("find-id-form").addEventListener("submit", (e) => {
  e.preventDefault();
  $("find-result").classList.add("hidden");
  submitForm(e.target, "find-error", async () => {
    const { data } = await api("/api/auth/find-id", { name: $("find-name").value, member_code: $("find-code").value.trim().toUpperCase() });
    if (data.status !== "ok") { $("find-error").textContent = data.message || "찾지 못했습니다."; return; }
    $("find-result").textContent = `가입한 이메일: ${data.email_masked}`;
    $("find-result").classList.remove("hidden");
  });
});

let resetEmail = "";
$("reset-request-form").addEventListener("submit", (e) => {
  e.preventDefault();
  submitForm(e.target, "reset-request-error", async () => {
    resetEmail = $("reset-email").value.trim();
    const { data } = await api("/api/auth/password/request", { email: resetEmail });
    if (data.status !== "ok") { $("reset-request-error").textContent = data.message || "요청하지 못했습니다."; return; }
    $("reset-sent").textContent = data.message;
    location.hash = "#/reset-confirm";
  });
});

$("reset-confirm-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const pw = $("reset-password").value;
  const problem = passwordProblem(pw, $("reset-password2").value);
  if (problem) { $("reset-confirm-error").textContent = problem; return; }
  submitForm(e.target, "reset-confirm-error", async () => {
    const { data } = await api("/api/auth/password/reset", { email: resetEmail, code: $("reset-code").value.trim(), new_password: pw });
    if (data.status !== "ok") { $("reset-confirm-error").textContent = data.message || "바꾸지 못했습니다."; return; }
    e.target.reset();
    location.hash = "#/login";
    $("login-error").textContent = "";
    $("login-email").value = resetEmail;
    loginNotice(true);   // 문구를 넣기 전에 안내 모양(role=status)으로 바꿔 경보로 읽히지 않게 한다
    $("login-error").textContent = data.message || "비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요.";
  });
});

// ── 내 정보 ──
const fmt = (iso) => {
  if (!iso) return "-";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}. ${p(d.getMonth() + 1)}. ${p(d.getDate())}. ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const signalLabel = (s) => String(s || "").replace(/_/g, " ");

// 마지막 시도가 어떻게 끝났는가 (training_results.last_outcome, last_predicted: 18_DB설계서 §2-3)
function lastTry(r) {
  if (r.last_outcome === "correct" || (!r.given_up && !r.last_outcome)) return "정답";
  if (r.last_outcome === "timeout") return "시간 초과";
  if (r.last_outcome === "wrong") {
    const seen = r.last_predicted && r.last_predicted !== "negative" ? ` (인식: ${signalLabel(r.last_predicted)})` : "";
    return `오답${seen}`;
  }
  return r.given_up ? "재시도 상한 초과" : "-";
}

async function loadMe() {
  const res = await api("/api/me");
  if (res.status === 401) { session = null; renderAccount(); return null; }
  if (!res.ok || res.data.status !== "ok") throw new Error(res.data.message || "잠시 후 다시 시도해 주세요.");
  meCache = res.data;
  return meCache;
}

async function showMe() {
  if (!session) { location.hash = "#/login"; return; }
  showView("view-me");
  window.scrollTo({ top: 0 });
  let me;
  try {
    me = await loadMe();
  } catch (err) {
    $("me-status").innerHTML = `<p class="st">불러오지 못했습니다</p><p>${esc(err.message)}</p>`;
    focusHeading($("me-title"));
    return;
  }
  if (!me) { location.hash = "#/login"; return; }
  const m = me.member;
  $("me-name").textContent = m.name;
  $("me-code").textContent = m.member_code;
  $("me-status").className = `status-card ${me.certified ? "done" : "todo"}`;
  $("me-status").innerHTML = me.certified
    ? `<p class="st">${ICON.check}수료 완료</p><p>처음 수료 ${esc(fmt(me.certified_at))}, 수료증 발급 가능</p>`
    : `<p class="st">${ICON.clock}미수료</p><p>교육장 키트에서 7종 교육을 마치면 수료로 바뀝니다</p>`;
  $("me-profile").innerHTML = [
    ["이름", m.name], ["사원 코드", m.member_code, "code"], ["이메일", m.email], ["소속", m.org || "없음"], ["가입일", fmt(m.created_at)],
  ].map(([k, v, cls]) => `<div><dt>${k}</dt><dd class="${cls || ""}">${esc(v)}</dd></div>`).join("");

  const rows = me.sessions;
  $("me-count").textContent = rows.length ? `${rows.length}회` : "";
  $("history-empty").classList.toggle("hidden", rows.length > 0);
  $("history-rows").innerHTML = rows.map((s, i) => `
    <tr data-i="${i}"><td class="num">${esc(fmt(s.completed_at))}</td>
      <td>${s.all_passed ? `<span class="pass">${ICON.check}합격 ${s.passed_count} / ${s.results.length}종</span>` : `<span class="part">합격 ${s.passed_count} / ${s.results.length}종</span>`}</td>
      <td class="num">${esc(s.total_attempts)}회</td><td class="num">${esc(s.first_try_correct)}종</td>
      <td class="actions"><button class="btn btn-sm btn-ghost" type="button" data-detail="${i}" aria-label="${esc(fmt(s.completed_at))} 결과 보기">결과 보기</button>
        ${s.completed ? `<a class="row-link" href="#/certificate/${esc(s.id)}" aria-label="${esc(fmt(s.completed_at))} 수료증">수료증</a>` : ""}</td></tr>`).join("");
  $("detail").classList.add("hidden");
  if (rows.length) showDetail(0);
  focusHeading($("me-title"));
}

function showDetail(i) {
  const s = meCache.sessions[i];
  document.querySelectorAll("#history-rows tr").forEach((tr) => {
    tr.classList.toggle("sel", tr.dataset.i === String(i));
    if (tr.dataset.i === String(i)) tr.setAttribute("aria-current", "true"); else tr.removeAttribute("aria-current");   // 표시 전용
  });
  $("detail").classList.remove("hidden");
  $("detail-when").textContent = fmt(s.completed_at);
  $("detail-cert").classList.toggle("hidden", !s.completed);
  $("detail-cert").setAttribute("href", `#/certificate/${s.id}`);
  $("detail-rows").innerHTML = s.results.map((r) => {
    const score = Math.max(0, Math.min(100, r.match_score || 0));
    const at = (v) => Math.max(0, Math.min(100, (v - 50) * 2));   // 표시 전용: 게이지 눈금 위치(50~100%)
    return `<tr><td><b>${esc(signalLabel(r.signal))}</b></td>
      <td>${r.given_up ? '<span class="fail">불합격</span>' : '<span class="pass">합격</span>'}</td>
      <td class="num">${esc(r.attempts)}회</td>
      <td class="num"><div class="score"><span class="${score >= 75 ? "ok" : ""}">${score}%</span><span class="gauge" aria-hidden="true"><b style="left:${at(75)}%"></b><i class="${score >= 75 ? "ok" : score < 50 ? "low" : ""}" style="left:${at(score)}%"></i></span></div></td>
      <td class="reason">${esc(lastTry(r))}</td></tr>`;
  }).join("");
}

$("history-rows").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-detail]");
  if (!btn) return;
  showDetail(Number(btn.dataset.detail));
  // 표시 전용: 아래 표가 바뀐 것을 스크린리더에 알린다 (role=status)
  $("detail-status").textContent = `${fmt(meCache.sessions[Number(btn.dataset.detail)].completed_at)} 회차의 수신호별 결과를 아래에 표시했습니다.`;
});

// ── 수료증 ──
async function showCertificate(id) {
  if (!session) { location.hash = "#/login"; return; }
  const me = meCache || await loadMe().catch(() => null);
  const s = me && me.sessions.find((x) => x.id === id && x.completed);
  if (!s) { location.hash = "#/me"; return; }
  showView("view-cert");
  window.scrollTo({ top: 0 });
  if ($("cert-meta")) {
    $("cert-meta").innerHTML = [["사원 코드", me.member.member_code, "code"], ["수료 일시", fmt(s.completed_at)], ["결과", `합격 ${s.passed_count} / ${s.results.length}종`]]
      .map(([k, v, cls]) => `<div><dt>${k}</dt><dd class="${cls || ""}">${esc(v)}</dd></div>`).join("");
  }
  // 표시 전용: 캔버스 그림 안의 내용(수신호별 결과, 하단 고지)을 글로도 읽을 수 있게 한다 (#cert-canvas aria-describedby)
  $("cert-desc").textContent = `${me.member.name}, 사원 코드 ${me.member.member_code}, 수료 일시 ${fmt(s.completed_at)}. 수신호별 결과: `
    + s.results.map((r) => `${signalLabel(r.signal)} ${r.given_up ? "불합격" : "합격"}, 시도 ${r.attempts}회, 일치율 ${Math.max(0, Math.min(100, r.match_score || 0))}%`).join(". ")
    + ". 교육 시연용으로 발급한 증서이며 발급 기관은 가상 기관입니다.";
  focusHeading($("cert-title"));
  const completed = s.results.map((r) => ({ signal: r.signal, attempts: r.attempts, match_score: r.match_score, given_up: r.given_up }));
  await drawCertificate($("cert-canvas"), me.member, completed, Date.parse(s.completed_at) / 1000, Date.now() / 1000);
}

$("cert-download").addEventListener("click", () => {
  const link = document.createElement("a");
  link.download = `safesign-certificate-${session ? session.member_code : "member"}.png`;
  link.href = $("cert-canvas").toDataURL("image/png");
  link.click();
});
$("cert-print").addEventListener("click", () => window.print());

// ── 표시 전용: 홈 영상 2개(Hyperframes로 렌더링한 MP4)와 스크롤 등장 ──
// 움직임 줄이기 설정이면 자동 재생하지 않고 포스터(정지 화면)를 보인다. 화면 밖이거나 다른 화면이면 멈춘다
const REDUCED_MOTION = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
const REEL_STEP = 2;   // signal-reel.mp4에서 신호 하나가 차지하는 시간(초). 순서는 SIGNALS와 같다

function setupVideo(video) {
  const btn = document.querySelector(`.vid-toggle[data-video="${video.id}"]`);
  let held = REDUCED_MOTION;   // 사용자가 멈춘 상태
  let visible = false;
  const sync = () => {
    if (!btn) return;
    btn.classList.toggle("is-paused", video.paused);
    btn.setAttribute("aria-label", video.paused ? "영상 재생" : "영상 일시정지");
    const lab = btn.querySelector(".vt-label");
    if (lab) lab.textContent = video.paused ? "재생" : "일시정지";
  };
  const play = () => { const p = video.play(); if (p && p.catch) p.catch(sync); };
  video.addEventListener("play", sync);
  video.addEventListener("pause", sync);
  if (btn) btn.addEventListener("click", () => {
    if (video.paused) { held = false; play(); } else { held = true; video.pause(); }
  });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible && !held) play(); else if (!visible) video.pause();
    }, { threshold: 0.2 }).observe(video);
  } else if (!held) play();
  sync();
}

function setupReelIndex(video) {
  const buttons = Array.from(document.querySelectorAll(".hi[data-reel]"));
  if (!buttons.length) return;
  let current = -1;
  const mark = () => {
    const k = ((Math.floor(video.currentTime / REEL_STEP) % SIGNALS.length) + SIGNALS.length) % SIGNALS.length;
    if (k === current) return;
    current = k;
    buttons.forEach((b, i) => { if (i === k) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current"); });
  };
  if ("requestVideoFrameCallback" in video) {
    const onFrame = () => { mark(); video.requestVideoFrameCallback(onFrame); };
    video.requestVideoFrameCallback(onFrame);
  }
  video.addEventListener("timeupdate", mark);
  video.addEventListener("seeked", mark);
  buttons.forEach((b) => b.addEventListener("click", () => {
    video.currentTime = Number(b.dataset.reel) * REEL_STEP + 0.9;   // 모핑이 끝나고 손모양이 멈춘 지점
    mark();
  }));
  mark();
}

function setupReveal() {
  if (REDUCED_MOTION || !("IntersectionObserver" in window)) return;
  document.documentElement.classList.add("reveal-on");
  const io = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { rootMargin: "0px 0px -6% 0px" });
  document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
}

// ── 시작 ──
(async () => {
  renderHome();
  document.querySelectorAll("#hero-video, #reel-video").forEach(setupVideo);
  if ($("reel-video")) setupReelIndex($("reel-video"));
  setupReveal();
  try { await refreshSession(); } catch (err) { /* 서버가 없으면 로그인 전 화면으로 */ }
  route();
})();
