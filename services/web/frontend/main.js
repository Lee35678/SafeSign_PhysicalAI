// SC-01~SC-07 화면 전환 + /api/state 폴링 (09_화면목록_v2.md).
"use strict";

const POLL_MS = 400;

let pollTimer = null;
let overlayGen = 0;
let lastOverlayKey = null;

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
    // 09_화면목록_v2 SC-07: 학습 중 이탈 후 재접속 — 세션 이어하기 미구현, 항상 처음부터.
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
  show("screen-training");
  startPolling();
});

// ---- SC-03 (+03a/03b) / SC-04 / SC-05 ----

async function refreshTraining() {
  const state = await apiGet("/api/state");
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

  const liveScore = state.live_judgment ? state.live_judgment.match_score : 0;
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
    // (03_인터페이스계약서_v2 §4 — 자세를 다듬으라는 뜻과 다른 수신호를 하고 있다는 뜻을 구분).
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

document.getElementById("camera-retry-btn").addEventListener("click", () => {
  // 손이 다시 보이면 상태머신이 자동으로 SC-03에 복귀한다(state_machine.py _poll_once) — 이 버튼은
  // 즉시 한 번 더 확인해 대기감을 줄이기 위한 용도.
  refreshTraining();
});

// ---- SC-05 ----

function renderSummary(completed) {
  const tbody = document.getElementById("summary-tbody");
  tbody.innerHTML = "";
  completed.forEach((item) => {
    const tr = document.createElement("tr");
    const accuracy = Math.round(100 / item.attempts);
    tr.innerHTML = `
      <td>${item.signal}</td>
      <td>${item.attempts}회</td>
      <td>${item.match_score}% (${accuracy}% 성공률)</td>
    `;
    tbody.appendChild(tr);
  });
}

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
    const accuracy = Math.round(100 / item.attempts);
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
