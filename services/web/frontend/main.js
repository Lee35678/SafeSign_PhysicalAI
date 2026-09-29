// SC-01~SC-07 화면 전환 + /api/state 폴링 (09_화면목록.md).
"use strict";

const POLL_MS = 400;

let pollTimer = null;
let overlayGen = 0;
let lastOverlayKey = null;
let lastCompleted = [];   // SC-05 집계 - "결과 저장"(⑨)이 다시 쓴다

function show(screenId) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.remove("active"));
  document.getElementById(screenId).classList.add("active");
}

async function apiGet(path) {
  const res = await fetch(path);
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

// ---- SC-01 / SC-07 ----

async function init() {
  const state = await apiGet("/api/state");
  renderDeviceStatus(state.devices);
  if (state.state && state.state !== "landing") {
    // 09_화면목록 SC-07: 학습 중 이탈 후 재접속 — 세션 이어하기 미구현, 항상 처음부터.
    show("screen-reentry");
  } else {
    show("screen-landing");
  }
}

document.getElementById("reentry-confirm-btn").addEventListener("click", () => {
  show("screen-landing");
});

// ---- SC-01 -> SC-02 ----

document.getElementById("start-btn").addEventListener("click", async () => {
  const state = await apiGet("/api/state");
  renderCurriculumList(state.curriculum || []);
  show("screen-curriculum");
});

function renderCurriculumList(curriculum) {
  const list = document.getElementById("curriculum-list");
  list.innerHTML = "";
  curriculum.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `${item.signal} — AI Hand: ${item.aihand} / picar: ${item.picar}`;
    list.appendChild(li);
  });
}

// ---- SC-02 -> SC-03 ----

document.getElementById("curriculum-start-btn").addEventListener("click", async () => {
  await apiPost("/api/start");
  lastOverlayKey = null;
  shownSignImage = null;
  applyPhase("demo");   // /api/start는 첫 수신호 시범과 함께 phase "demo"로 시작한다
  show("screen-training");
  startPolling();
});

// ---- SC-03 (+03a/03b) / SC-04 / SC-05 ----

// 판정 타이밍 스펙 §4.3 — 예시 사진은 picar 명령명(영문)으로 저장한다(URL 한글 인코딩 회피).
// state_machine.py PICAR_COMMANDS의 command와 같은 이름이다.
const SIGN_IMAGES = {
  정지: "stop",
  서행: "slow",
  좌회전_유도: "turn_left",
  우회전_유도: "turn_right",
  확인_완료: "complete",
  후진: "reverse",
  주의: "caution",
};

let currentPhase = "demo";   // SC-03 하위 단계 — /api/state의 phase ("demo" | "judging")
let confirmPending = false;
let requestSeq = 0;          // 폴링 응답이 순서를 벗어나 도착하면(확인 직전에 보낸 요청 등) 버린다
let renderedSeq = 0;
let shownSignImage = null;

async function refreshTraining() {
  const seq = ++requestSeq;
  const state = await apiGet("/api/state");
  if (seq <= renderedSeq) return;
  renderedSeq = seq;
  renderDeviceStatus(state.devices);

  if (state.state === "camera_fail") {
    show("screen-camera-fail");
    return;
  }

  if (state.state === "summary") {
    stopPolling();
    renderSummary(state.completed || []);
    show("screen-summary");
    return;
  }

  if (state.state !== "training") {
    return;
  }

  show("screen-training");
  document.getElementById("signal-name").textContent = state.target_signal ?? "-";
  document.getElementById("signal-desc").textContent = state.signal_info
    ? `AI Hand: ${state.signal_info.aihand}  /  picar: ${state.signal_info.picar}`
    : "";
  document.getElementById("signal-progress").textContent =
    `${state.progress.current} / ${state.progress.total}`;
  document.getElementById("attempt-count").textContent = state.attempts ?? 0;
  renderSignImage(state.target_signal);
  renderPhase(state);

  // 시범 단계에서는 백엔드가 판정을 멈춰 live_judgment가 직전 판정값으로 남아 있다 — 0으로 둔다.
  const liveScore = currentPhase === "judging" && state.live_judgment ? state.live_judgment.match_score : 0;
  setMatchScore(liveScore);

  const result = state.last_result;
  if (result) {
    const key = `${result.signal}:${result.outcome}:${result.attempt}`;
    if (key !== lastOverlayKey) {
      lastOverlayKey = key;
      showOverlay(result);
    }
  }
}

function setMatchScore(score) {
  const value = Math.max(0, Math.min(100, score || 0));
  document.getElementById("match-score-fill").style.width = `${value}%`;
  document.getElementById("match-score-value").textContent = `${value}%`;
}

function showOverlay(result) {
  const overlay = document.getElementById("training-overlay");
  const myGen = ++overlayGen;
  overlay.classList.remove("hidden");

  if (result.outcome === "correct") {
    overlay.className = "overlay correct";
    overlay.innerHTML = `
      <h2>정답!</h2>
      <p>일치율 ${result.match_score}%</p>
      <p>picar 동작 중…</p>
    `;
    setTimeout(() => {
      if (myGen === overlayGen) overlay.classList.add("hidden");
    }, 2000);
  } else {
    // wrong / below_tau / out_of_distribution 모두 SC-03b, 메시지만 다르다
    // (03_인터페이스계약서 §4 — 자세를 다듬으라는 뜻과 다른 수신호를 하고 있다는 뜻을 구분).
    overlay.className = "overlay wrong";
    overlay.innerHTML = `
      <h2>${result.message ?? "다시 시도하세요"}</h2>
      <p>일치율 ${result.match_score}%</p>
      <p>권장 재도전 횟수 ${result.recommended_retry}회 · 현재 시도 ${result.attempt}회</p>
    `;
    setTimeout(() => {
      if (myGen === overlayGen) overlay.classList.add("hidden");
    }, 2500);
  }
}

// ---- SC-03 시범 단계: 예시 사진 + 확인 버튼 (판정 타이밍 스펙 §4.2) ----

function renderSignImage(signal) {
  if (signal === shownSignImage) return;
  shownSignImage = signal;
  const figure = document.getElementById("sign-example");
  const img = document.getElementById("sign-image");
  const name = SIGN_IMAGES[signal];
  document.getElementById("sign-image-missing").textContent = name
    ? `예시 사진 준비 중 (images/${name}.jpg)`
    : "예시 사진 준비 중";
  if (!name) {
    figure.classList.add("missing");
    img.removeAttribute("src");
    return;
  }
  // 사진이 아직 저장소에 없으면 error 이벤트로 자리표시 문구를 보여준다
  figure.classList.remove("missing");
  img.alt = `${signal} 예시 사진`;
  img.src = `images/${name}.jpg`;
}

document.getElementById("sign-image").addEventListener("error", () => {
  document.getElementById("sign-example").classList.add("missing");
});

document.getElementById("sign-image").addEventListener("load", () => {
  document.getElementById("sign-example").classList.remove("missing");
});

function applyPhase(phase) {
  currentPhase = phase === "judging" ? "judging" : "demo";
  const screen = document.getElementById("screen-training");
  screen.classList.toggle("phase-demo", currentPhase === "demo");
  screen.classList.toggle("phase-judging", currentPhase === "judging");
  document.getElementById("phase-badge").textContent = currentPhase === "demo" ? "시범" : "판정 중";
}

function renderPhase(state) {
  applyPhase(state.phase);
  // 오답 뒤 시범 단계면 AI Hand가 다시 보여주는 중이다 (스펙 §3 — 오답 피드백 + 재시범 + 사진 + 확인)
  const result = state.last_result;
  const retrying = result && result.signal === state.target_signal && result.outcome === "wrong";
  // micro:bit 버튼 A도 확인 입력이다(스펙 §9) — BLE가 끊기면 입력이 사라지므로 연결돼 있을 때만 안내한다
  const actuation = (state.devices || {}).actuation || {};
  const keys = actuation.microbit_connected ? "Space 또는 micro:bit A" : "Space";
  document.getElementById("demo-guide").textContent = retrying
    ? `AI Hand가 다시 보여줍니다. 사진과 비교해 보고, 준비되면 확인을 누르세요 (${keys})`
    : `AI Hand와 사진을 보고, 준비되면 확인을 누르세요 (${keys})`;
}

function isConfirmVisible() {
  // 오버레이(정답/오답 연출)가 떠 있는 동안은 버튼이 가려져 있다 — 사라진 뒤에만 받는다 (스펙 §4.2)
  return (
    document.getElementById("screen-training").classList.contains("active") &&
    currentPhase === "demo" &&
    document.getElementById("training-overlay").classList.contains("hidden")
  );
}

async function confirmJudging() {
  if (!isConfirmVisible() || confirmPending) return;
  confirmPending = true;
  const btn = document.getElementById("confirm-btn");
  btn.disabled = true;
  try {
    const result = await apiPost("/api/confirm");
    if (result.status === "ok") {
      renderedSeq = requestSeq;   // 확인 전에 보낸 폴링 응답("demo")이 늦게 와서 화면을 되돌리지 않게
      applyPhase("judging");
      setMatchScore(0);
    }
  } catch (err) {
    // 네트워크 오류 — 다음 폴링이 실제 phase로 화면을 맞춘다
  } finally {
    confirmPending = false;
    btn.disabled = false;
  }
}

document.getElementById("confirm-btn").addEventListener("click", (event) => {
  // 마우스로 누른 뒤 포커스가 남으면 다음 스페이스바가 버튼 기본 동작과 겹친다
  event.currentTarget.blur();
  confirmJudging();
});

document.addEventListener("keydown", (event) => {
  if (event.code !== "Space" || !isConfirmVisible()) return;
  event.preventDefault();   // 페이지 스크롤 방지
  if (event.repeat) return; // 누르고 있을 때의 반복 입력 무시
  confirmJudging();
});

document.getElementById("camera-retry-btn").addEventListener("click", () => {
  // 손이 다시 보이면 상태머신이 자동으로 SC-03에 복귀한다(state_machine.py _poll_once) — 이 버튼은
  // 즉시 한 번 더 확인해 대기감을 줄이기 위한 용도.
  refreshTraining();
});

// ---- SC-05 ----

// 09_화면목록 §미확정: "성공률" 정의는 KPI 정답률과 혼동될 수 있어 확인 대기 중.
// 정의가 바뀌면 이 함수만 고치면 화면·수료증·CSV가 함께 따라간다.
function successRate(item) {
  return Math.round(100 / item.attempts);
}

function renderSummary(completed) {
  lastCompleted = completed;
  const tbody = document.getElementById("summary-tbody");
  tbody.innerHTML = "";
  completed.forEach((item) => {
    const tr = document.createElement("tr");
    const accuracy = successRate(item);
    tr.innerHTML = `
      <td>${item.signal}</td>
      <td>${item.attempts}회</td>
      <td>${item.match_score}% (${accuracy}% 성공률)</td>
    `;
    tbody.appendChild(tr);
  });
}

// ---- SC-05 결과 저장 (web 할 일 ⑨, 09_화면목록 SC-05 "교육자용 결과 파일 저장") ----
// 프론트엔드만으로 처리한다 - 집계는 이미 /api/state의 completed로 받아와 있어 서버 호출이 없다.

function csvCell(value) {
  const text = String(value ?? "");
  // 쉼표·따옴표·줄바꿈이 들어가면 셀이 밀린다. 수신호 이름엔 없지만 규칙대로 감싼다.
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function toCsv(rows) {
  return rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
}

function localTimestamp(date) {
  const p2 = (n) => String(n).padStart(2, "0");
  const d = `${date.getFullYear()}-${p2(date.getMonth() + 1)}-${p2(date.getDate())}`;
  const t = `${p2(date.getHours())}:${p2(date.getMinutes())}:${p2(date.getSeconds())}`;
  return { date: d, time: t, file: `${d.replace(/-/g, "")}_${t.replace(/:/g, "")}` };
}

function downloadCsv(filename, csvText) {
  // 엑셀은 BOM이 없으면 UTF-8 한글을 깨뜨린다 (스펙 §7.1이 시행 로그에 BOM을 요구하는 것과 같은 이유).
  const blob = new Blob(["\uFEFF" + csvText], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  // 즉시 해제하면 브라우저가 내려받기를 시작하기 전에 주소가 사라질 수 있다.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

document.getElementById("export-btn").addEventListener("click", () => {
  const status = document.getElementById("export-status");
  if (!lastCompleted.length) {
    status.textContent = "저장할 결과가 없습니다.";
    return;
  }
  const stamp = localTimestamp(new Date());
  const rows = [["저장일자", "저장시각", "수신호", "시도 횟수", "정답 시 일치율(%)", "성공률(%)"]];
  lastCompleted.forEach((item) => {
    rows.push([stamp.date, stamp.time, item.signal, item.attempts, item.match_score, successRate(item)]);
  });
  downloadCsv(`safesign_result_${stamp.file}.csv`, toCsv(rows));
  status.textContent = `결과 ${lastCompleted.length}건을 저장했습니다.`;
});

document.getElementById("certificate-btn").addEventListener("click", async () => {
  const result = await apiPost("/api/certificate");
  if (result.status !== "ok") return;
  drawCertificate(result.completed, result.issued_at);
  show("screen-certificate");
});

// ---- SC-06 ----

function drawCertificate(completed, issuedAt) {
  const canvas = document.getElementById("certificate-canvas");
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#2563eb";
  ctx.lineWidth = 6;
  ctx.strokeRect(12, 12, canvas.width - 24, canvas.height - 24);

  ctx.fillStyle = "#111827";
  ctx.textAlign = "center";
  ctx.font = "bold 32px system-ui, sans-serif";
  ctx.fillText("수 료 증", canvas.width / 2, 90);

  ctx.font = "18px system-ui, sans-serif";
  ctx.fillText("SafeSign 산업 안전 수신호 교육", canvas.width / 2, 130);

  ctx.textAlign = "left";
  ctx.font = "16px system-ui, sans-serif";
  ctx.fillText("아래 학습자는 안전 수신호 7종 교육을 모두 이수하였음을 증명합니다.", 60, 180);

  let y = 230;
  ctx.font = "15px system-ui, sans-serif";
  completed.forEach((item, i) => {
    const accuracy = successRate(item);
    ctx.fillText(
      `${i + 1}. ${item.signal}  —  시도 ${item.attempts}회 / 최종 일치율 ${item.match_score}% (${accuracy}% 성공률)`,
      60,
      y
    );
    y += 30;
  });

  ctx.font = "14px system-ui, sans-serif";
  ctx.fillStyle = "#666";
  const issuedDate = new Date(issuedAt * 1000).toLocaleString("ko-KR");
  ctx.fillText(`발급일시: ${issuedDate}`, 60, canvas.height - 40);
}

document.getElementById("certificate-download-btn").addEventListener("click", () => {
  const canvas = document.getElementById("certificate-canvas");
  const link = document.createElement("a");
  link.download = "safesign-certificate.png";
  link.href = canvas.toDataURL("image/png");
  link.click();
});

document.getElementById("certificate-print-btn").addEventListener("click", () => {
  window.print();
});

document.getElementById("restart-btn").addEventListener("click", () => {
  show("screen-landing");
});

// ---- 장치 상태 표시줄 ----

function renderDeviceStatus(devices) {
  const el = document.getElementById("device-status-bar");
  if (!el) return;
  if (!devices || Object.keys(devices).length === 0) {
    el.textContent = "";
    return;
  }
  const labels = { vision: "인식(vision)", actuation: "AI Hand/micro:bit", picar: "picar" };
  el.innerHTML = Object.entries(devices)
    .map(([name, info]) => {
      const ok = info.status === "ok";
      let extra = "";
      if (name === "actuation" && info.microbit_connected === false) extra = " · BLE 끊김";
      if (name === "picar" && info.i2c_reachable === false) extra = " · I2C 응답 없음";
      return `<span class="device ${ok ? "ok" : "bad"}">${labels[name] ?? name}${extra}</span>`;
    })
    .join(" ");
}

init();
