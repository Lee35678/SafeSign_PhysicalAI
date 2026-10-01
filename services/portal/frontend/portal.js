// SafeSign 회사 사이트 — 화면 전환(#/경로) · 로그인/가입/찾기 · 내 정보 · 수료증.
// 백엔드: services/portal/app/main.py (/api/auth/* · /api/session · /api/me). 회원 규칙은 교육장 web과 같다(members.py).
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// 교육 과정 7종 — 교육장 web(state_machine CURRICULUM_INFO · main.js SIGN_PATTERNS)과 같은 정의 (10_PRD §3.2)
const SIGNALS = [
  { name: "정지", fingers: [1, 1, 1, 1, 1], aihand: "다섯 손가락 펴기 + 정면", picar: "정지 · 양쪽 적색 LED 점등", source: "크레인 작업표준신호" },
  { name: "서행", fingers: [0, 1, 1, 0, 0], aihand: "검지 + 중지 펴기 + 정면", picar: "감속 주행 · 양쪽 황색 LED 점멸", source: "크레인 작업표준신호" },
  { name: "좌회전 유도", fingers: [1, 1, 0, 0, 0], aihand: "엄지 + 검지 펴기", picar: "좌회전 주행 · 좌측 황색 LED 점멸", source: "크레인 작업표준신호" },
  { name: "우회전 유도", fingers: [1, 0, 0, 0, 1], aihand: "엄지 + 소지 펴기", picar: "우회전 주행 · 우측 황색 LED 점멸", source: "크레인 작업표준신호" },
  { name: "확인 완료", fingers: [0, 0, 0, 0, 0], aihand: "다섯 손가락 접기(주먹) + 정면", picar: "정지 · 적색·황색 LED 전부 점멸", source: "크레인 작업표준신호" },
  { name: "후진", fingers: [0, 1, 0, 0, 0], aihand: "검지만 펴기", picar: "후진 주행", source: "자체 지정" },
  { name: "주의", fingers: [0, 0, 0, 0, 1], aihand: "소지(새끼손가락)만 펴기", picar: "정지 · 양쪽 황색 LED 점멸", source: "자체 지정" },
];
const FINGER_NAMES = ["엄지", "검지", "중지", "약지", "소지"];

// 최종 KPI (05_모델카드 §7-3, 2026-09-30) — 팀원 3명 210시도, 공식 3연속
const KPI = [
  { name: "정답률", target: "≥ 92%", value: 95.2, unit: "%", goal: 92, better: "high", ci: "91.5 ~ 97.4%" },
  { name: "오분류율", target: "≤ 3%", value: 0.0, unit: "%", goal: 3, better: "low", ci: "상한 1.8%" },
  { name: "미판정률", target: "≤ 5%", value: 4.8, unit: "%", goal: 5, better: "low", ci: "2.6 ~ 8.5%" },
  { name: "Macro F1", target: "≥ 0.90", value: 0.974, unit: "", goal: 0.9, better: "high", ci: "—" },
  { name: "치명 오분류 (정지 → 다른 신호)", target: "0건", value: 0, unit: "건", goal: 0, better: "zero", ci: "정지 30시도 · 상한 11.4%" },
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

// ── 홈: 교육 과정 · 검증 결과 표 ──
function fingerIcon(pattern) {
  const label = FINGER_NAMES.map((f, i) => `${f} ${pattern[i] ? "폄" : "접음"}`).join(", ");
  return `<span class="fingers" role="img" aria-label="${esc(label)}">${pattern.map((p) => `<i class="${p ? "up" : ""}"></i>`).join("")}</span>`;
}

function renderHome() {
  $("signal-rows").innerHTML = SIGNALS.map((s) => `
    <tr><td>${esc(s.name)}</td><td>${fingerIcon(s.fingers)}</td><td>${esc(s.aihand)}</td>
        <td>${esc(s.picar)}</td><td class="source">${esc(s.source)}</td></tr>`).join("");

  $("kpi-rows").innerHTML = KPI.map((k) => {
    // 막대: 한 색 채움 + 목표선 눈금 (목표를 넘으면 정상색). 낮을수록 좋은 지표는 목표의 2배 폭을 척도로 쓴다.
    const scale = k.better === "high" ? (k.unit === "%" ? 100 : 1) : Math.max(k.goal * 2, 1);
    const met = k.better === "high" ? k.value >= k.goal : k.value <= k.goal;
    const fill = Math.min(100, (k.value / scale) * 100);
    const tick = k.better === "zero" ? 0 : Math.min(100, (k.goal / scale) * 100);
    const shown = k.unit === "" ? k.value.toFixed(3) : `${k.value}${k.unit}`;
    return `<tr><td>${esc(k.name)}</td><td class="num">${esc(k.target)}${k.better === "low" ? '<small class="dir">낮을수록 좋음</small>' : ""}</td>
      <td class="num val">${esc(shown)} ${met ? '<span class="pass">달성</span>' : '<span class="fail">미달</span>'}</td>
      <td><div class="meter" aria-hidden="true"><i class="${met ? "ok" : ""}" style="width:${fill}%"></i>${k.better === "zero" ? "" : `<b style="left:${tick}%"></b>`}</div></td>
      <td class="num muted">${esc(k.ci)}</td></tr>`;
  }).join("");
}

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

  if (!head || SECTIONS.includes(head)) {
    showView("view-home");
    if (head) document.getElementById(head).scrollIntoView({ behavior: "smooth", block: "start" });
    else window.scrollTo({ top: 0 });
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

// ── 로그인 · 가입 · 찾기 ──
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
    $("login-error").textContent = data.message || "비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요.";
  });
});

// ── 내 정보 ──
const fmt = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}. ${p(d.getMonth() + 1)}. ${p(d.getDate())}. ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const signalLabel = (s) => String(s || "").replace(/_/g, " ");

// 마지막 시도가 어떻게 끝났는가 (training_results.last_outcome · last_predicted — 18_DB설계서 §2-3)
function lastTry(r) {
  if (r.last_outcome === "correct" || (!r.given_up && !r.last_outcome)) return "정답";
  if (r.last_outcome === "timeout") return "시간 초과";
  if (r.last_outcome === "wrong") {
    const seen = r.last_predicted && r.last_predicted !== "negative" ? ` · 인식: ${signalLabel(r.last_predicted)}` : "";
    return `오답${seen}`;
  }
  return r.given_up ? "재시도 상한 초과" : "—";
}

async function loadMe() {
  const res = await api("/api/me");
  if (res.status === 401) { session = null; renderAccount(); return null; }
  if (!res.ok || res.data.status !== "ok") throw new Error(res.data.message || "load_failed");
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
    return;
  }
  if (!me) { location.hash = "#/login"; return; }
  const m = me.member;
  $("me-name").textContent = m.name;
  $("me-code").textContent = m.member_code;
  $("me-status").className = `status-card ${me.certified ? "done" : "todo"}`;
  $("me-status").innerHTML = me.certified
    ? `<p class="st"><i></i>수료 완료</p><p>처음 수료 ${esc(fmt(me.certified_at))} · 수료증 발급 가능</p>`
    : `<p class="st"><i></i>미수료</p><p>교육장 키트에서 7종 교육을 마치면 수료로 바뀝니다</p>`;
  $("me-profile").innerHTML = [
    ["이름", m.name], ["사원 코드", m.member_code, "code"], ["이메일", m.email], ["소속", m.org || "—"], ["가입일", fmt(m.created_at)],
  ].map(([k, v, cls]) => `<div><dt>${k}</dt><dd class="${cls || ""}">${esc(v)}</dd></div>`).join("");

  const rows = me.sessions;
  $("me-count").textContent = rows.length ? `${rows.length}회` : "";
  $("history-empty").classList.toggle("hidden", rows.length > 0);
  $("history-rows").innerHTML = rows.map((s, i) => `
    <tr data-i="${i}"><td class="num">${esc(fmt(s.completed_at))}</td>
      <td>${s.all_passed ? '<span class="pass">전부 합격</span>' : `<span class="fail">합격 ${s.passed_count}/${s.results.length}</span>`}</td>
      <td class="num">${esc(s.total_attempts)}회</td><td class="num">${esc(s.first_try_correct)}종</td>
      <td class="actions"><button class="btn btn-sm btn-ghost" type="button" data-detail="${i}">결과 보기</button>
        ${s.completed ? `<a class="btn btn-sm" href="#/certificate/${esc(s.id)}">수료증</a>` : ""}</td></tr>`).join("");
  $("detail").classList.add("hidden");
  if (rows.length) showDetail(0);
}

function showDetail(i) {
  const s = meCache.sessions[i];
  document.querySelectorAll("#history-rows tr").forEach((tr) => tr.classList.toggle("sel", tr.dataset.i === String(i)));
  $("detail").classList.remove("hidden");
  $("detail-when").textContent = `· ${fmt(s.completed_at)}`;
  $("detail-cert").classList.toggle("hidden", !s.completed);
  $("detail-cert").setAttribute("href", `#/certificate/${s.id}`);
  $("detail-rows").innerHTML = s.results.map((r) => {
    const score = Math.max(0, Math.min(100, r.match_score || 0));
    return `<tr><td><b>${esc(signalLabel(r.signal))}</b></td>
      <td>${r.given_up ? '<span class="fail">불합격</span>' : '<span class="pass">합격</span>'}</td>
      <td class="num">${esc(r.attempts)}회</td>
      <td><div class="score"><div class="meter" aria-hidden="true"><i class="${score >= 75 ? "ok" : ""}" style="width:${score}%"></i><b style="left:75%"></b></div><span>${score}%</span></div></td>
      <td class="reason">${esc(lastTry(r))}</td></tr>`;
  }).join("");
}

$("history-rows").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-detail]");
  if (btn) showDetail(Number(btn.dataset.detail));
});

// ── 수료증 ──
async function showCertificate(id) {
  if (!session) { location.hash = "#/login"; return; }
  const me = meCache || await loadMe().catch(() => null);
  const s = me && me.sessions.find((x) => x.id === id && x.completed);
  if (!s) { location.hash = "#/me"; return; }
  showView("view-cert");
  window.scrollTo({ top: 0 });
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

// ── 시작 ──
(async () => {
  renderHome();
  try { await refreshSession(); } catch (err) { /* 서버가 없으면 로그인 전 화면으로 */ }
  route();
})();
