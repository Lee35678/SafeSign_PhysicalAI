// SC-01~SC-07 화면 전환 + /api/state 폴링 (09_화면목록.md).
"use strict";

const POLL_MS = 400;

let pollTimer = null;
let overlayGen = 0;
let lastOverlayKey = null;
let lastCompleted = [];   // SC-05 집계 - "결과 저장"(⑨)이 다시 쓴다
let lastTrainingState = null;  // 오버레이가 사라질 때 확인 버튼을 다시 그리는 데 쓴다 (①-b)
let confirmInFlight = false;   // 확인 요청 중복 방지 — 버튼 클릭과 스페이스바가 겹쳐도 한 번만 보낸다
let holdGen = 0;

// 수신호 → 예시 사진 (스펙 §4.3). 파일명은 picar 명령명(state_machine.py PICAR_COMMANDS의 command)과 같다.
const SIGN_IMAGES = {
  "정지": "images/stop.jpg",
  "서행": "images/slow.jpg",
  "좌회전_유도": "images/turn_left.jpg",
  "우회전_유도": "images/turn_right.jpg",
  "확인_완료": "images/complete.jpg",
  "후진": "images/reverse.jpg",
  "주의": "images/caution.jpg",
};

// 판정은 계속되고 화면 안내만 하는 사유 (스펙 §5 결정 — 물리 피드백·시도 횟수 없음)
const HOLD_OUTCOMES = ["below_tau", "out_of_distribution"];

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
  lastTrainingState = null;
  hideOverlay();
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
  document.getElementById("attempt-count").textContent =
    state.max_attempts ? `${state.attempts ?? 0} / ${state.max_attempts}` : `${state.attempts ?? 0}회`;

  const liveScore = state.live_judgment ? state.live_judgment.match_score : 0;
  setMatchScore(liveScore);

  const result = state.last_result;
  if (result) {
    const key = `${result.signal}:${result.outcome}:${result.attempt}`;
    if (key !== lastOverlayKey) {
      lastOverlayKey = key;
      if (HOLD_OUTCOMES.includes(result.outcome)) {
        showHoldHint(result);
      } else {
        showOverlay(result);
      }
    }
  }

  lastTrainingState = state;
  renderPhase(state);
}

// ---- SC-03 시범/판정 단계 (web 할 일 ①-b, 스펙 §4.2) ----

function overlayVisible() {
  return !document.getElementById("training-overlay").classList.contains("hidden");
}

// 확인 버튼이 "보이는" 조건 — 스페이스바도 이때만 받는다. 정답/오답 오버레이가 덮고 있는 동안은 받지 않는다
// (오버레이가 사라진 뒤 사진 + 확인 버튼 화면으로 이어진다, 스펙 §4.2).
function confirmAvailable() {
  const state = lastTrainingState;
  return Boolean(state) && state.state === "training" && state.phase === "demo"
    && document.getElementById("screen-training").classList.contains("active") && !overlayVisible();
}

function renderPhase(state) {
  const demo = state.phase === "demo";
  const stage = document.getElementById("training-stage");
  stage.classList.toggle("phase-demo", demo);
  stage.classList.toggle("phase-judging", !demo);
  setSignPhoto(state.target_signal);

  document.getElementById("confirm-panel").classList.toggle("hidden", !confirmAvailable());
  document.getElementById("judging-hint").classList.toggle("hidden", demo);
  // 시범 동안 vision 판정은 멈춰 있어 live_judgment는 지난 값이다 — 일치율은 판정 중에만 보인다
  document.getElementById("match-score-row").classList.toggle("hidden", demo);
  if (demo) document.getElementById("hold-hint").classList.add("hidden");

  const btn = document.getElementById("confirm-btn");
  btn.disabled = confirmInFlight;
  btn.textContent = confirmInFlight ? "확인 중…" : "확인";

  // micro:bit 버튼 A는 BLE가 끊긴 동안 입력이 사라진다(03 §7) — 끊겼으면 안내에서 빼고 Space를 쓰게 한다
  const actuation = (state.devices || {}).actuation;
  const bleDown = Boolean(actuation) && (actuation.status !== "ok" || actuation.microbit_connected === false);
  document.getElementById("confirm-keys").textContent = bleDown
    ? "Space 키로도 확인할 수 있어요 (micro:bit 연결 끊김 — A 버튼은 지금 동작하지 않아요)"
    : "Space 키 또는 micro:bit A 버튼으로도 확인할 수 있어요";
}

function setSignPhoto(signal) {
  const img = document.getElementById("sign-photo-img");
  const src = SIGN_IMAGES[signal] || "";
  if (img.dataset.src === src) return;
  img.dataset.src = src;
  img.alt = signal ? `${signal} 정답 자세` : "";
  setPhotoMissing(!src);
  if (src) img.src = src;
  else img.removeAttribute("src");
}

function setPhotoMissing(missing) {
  document.getElementById("sign-photo-img").classList.toggle("hidden", missing);
  document.getElementById("sign-photo-missing").classList.toggle("hidden", !missing);
}

document.getElementById("sign-photo-img").addEventListener("error", () => setPhotoMissing(true));
document.getElementById("sign-photo-img").addEventListener("load", () => setPhotoMissing(false));

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

document.getElementById("confirm-btn").addEventListener("click", (event) => {
  // 포커스가 남으면 다음 Space가 버튼 클릭으로도 들어간다 — 아래 keydown 처리와 겹치지 않게 푼다
  event.currentTarget.blur();
  confirmReady();
});

document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && document.getElementById("screen-camera-fail").classList.contains("active")) {
    event.preventDefault();
    if (!event.repeat) cameraRetry();
    return;
  }
  if (event.code !== "Space" || !confirmAvailable()) return;
  event.preventDefault();          // 페이지 스크롤 방지
  if (event.repeat) return;        // 누르고 있을 때의 반복 입력은 무시
  confirmReady();
});

function showHoldHint(result) {
  const hint = document.getElementById("hold-hint");
  const myGen = ++holdGen;
  hint.textContent = `${result.message ?? "조금 더 정확히 해주세요"} (일치율 ${result.match_score}%)`;
  hint.classList.remove("hidden");
  setTimeout(() => {
    if (myGen === holdGen) hint.classList.add("hidden");
  }, 3000);
}

function hideOverlay() {
  overlayGen++;
  document.getElementById("training-overlay").classList.add("hidden");
  document.getElementById("hold-hint").classList.add("hidden");
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
      if (myGen === overlayGen) {
        overlay.classList.add("hidden");
        if (lastTrainingState) renderPhase(lastTrainingState);   // 다음 수신호 시범 화면으로
      }
    }, 2000);
  } else {
    // 오답(SC-03b). below_tau / out_of_distribution은 오버레이 대신 showHoldHint()로 문구만 띄운다
    // (스펙 §5 결정 — 판정이 계속되므로 화면을 덮지 않는다. 두 사유의 문구 구분은 03 §4 그대로).
    // 재시도 상한 초과(given_up)면 같은 수신호를 다시 보여주지 않고 다음으로 넘어간다(state_machine.py).
    overlay.className = "overlay wrong";
    overlay.innerHTML = result.given_up
      ? `
      <h2>${result.message ?? "다시 시도하세요"}</h2>
      <p>일치율 ${result.match_score}%</p>
      <p>재시도 횟수를 초과해 다음 수신호로 넘어갑니다</p>
    `
      : `
      <h2>${result.message ?? "다시 시도하세요"}</h2>
      <p>일치율 ${result.match_score}%</p>
      <p>권장 재도전 횟수 ${result.recommended_retry}회 · 현재 시도 ${result.attempt}회</p>
      <p>AI Hand가 다시 보여줍니다</p>
    `;
    setTimeout(() => {
      if (myGen === overlayGen) {
        overlay.classList.add("hidden");
        if (lastTrainingState) renderPhase(lastTrainingState);   // 재시범 사진 + 확인 버튼으로
      }
    }, 2500);
  }
}

// SC-04 재시도 — 시범 단계(AI Hand 재시범 + 확인 버튼)로 돌아간다(state_machine.py _camera_retry).
// 판정 단계로 바로 돌리면 버튼을 누르느라 손이 카메라 밖이라 다시 SC-04로 튕겼다(2026-09-29 ⑥ 재시험).
let retryInFlight = false;
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

document.getElementById("camera-retry-btn").addEventListener("click", (event) => {
  event.currentTarget.blur();
  cameraRetry();
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
    // given_up: 재시도 상한(state_machine.py MAX_ATTEMPTS_PER_SIGNAL) 초과로 넘어간 수신호 — match_score는
    // 마지막 오답의 값이라 "정답 시 일치율"이 아니므로 표에서 구분해 보여준다.
    tr.innerHTML = `
      <td>${item.signal}${item.given_up ? " ⚠ 미완주" : ""}</td>
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
    const signal = item.given_up ? `${item.signal} (미완주)` : item.signal;
    rows.push([stamp.date, stamp.time, signal, item.attempts, item.match_score, successRate(item)]);
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
