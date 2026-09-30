// SafeSign 수료증 — 교육장 키트(services/web/frontend/main.js drawCertificate)와 같은 디자인을 회사 사이트용으로 옮긴 것.
// 두 곳의 모양을 맞춰 두기 위해, 한쪽을 고치면 다른 쪽도 같이 고친다(차이: 이 파일은 사람·회차를 인자로 받는다).
"use strict";

const CERT = { w: 1123, h: 794, scale: 2 };
const CERT_C = {
  paper: "#F4F6F8", ink: "#111820", ink2: "#2A3440", steel: "#687582", steelLight: "#9AA5B1",
  line: "#D5DAE0", orange: "#F28C28", green: "#15803D", greenBg: "#E3F4E8", red: "#C62828", redBg: "#FBE7E7",
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

// 직인 — 붉은 정사각 도장. 찍힌 느낌을 위해 살짝 기울이고, 종이색 점으로 인주가 덜 묻은 자리를 만든다(회원코드로 정해진 무늬).
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

// person = {name, member_code, org} (없으면 게스트) · completed = 수신호 결과 · completedAt/issuedAt = 초(epoch)
async function drawCertificate(canvas, person, completed, completedAt, issuedAt) {
  // 캔버스는 CSS 글꼴이 준비되기 전에 그리면 대체 글꼴로 굳어 버린다
  try {
    await Promise.all([
      document.fonts.load(`800 40px "SUIT Variable"`), document.fonts.load(`700 20px "Inter Variable"`),
    ]);
  } catch (err) { /* 글꼴이 없어도 대체 글꼴로 그린다 */ }

  canvas.width = CERT.w * CERT.scale;
  canvas.height = CERT.h * CERT.scale;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(CERT.scale, 0, 0, CERT.scale, 0, 0);
  const W = CERT.w, H = CERT.h, L = 56, R = W - 56;
  const issued = new Date((issuedAt || Date.now() / 1000) * 1000);
  const done = new Date((completedAt || issuedAt || Date.now() / 1000) * 1000);   // 수료 일시 = 교육을 마친 시각
  const guest = !person || person.guest;
  const code = guest ? "" : person.member_code;
  const firstTry = (item) => item.attempts === 1 && !item.given_up;
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
  ctx.fillText(`No. ${certNumber(code, done)}`, L, 164);
  ctx.fillStyle = CERT_C.ink;
  ctx.font = `800 70px ${CERT_KR}`;
  ctx.letterSpacing = "6px";
  ctx.fillText("수료증", L - 3, 238);
  ctx.letterSpacing = "0px";

  const stamp = (d) => `${d.getFullYear()}. ${pad2(d.getMonth() + 1)}. ${pad2(d.getDate())}.  ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  const when = stamp(done);
  const rows = [
    ["성명", guest ? "게스트 학습자" : person.name],
    ["사원 코드", guest ? "— (게스트)" : code],
    ["소속", (!guest && person.org) ? person.org : "—"],
    ["수료 일시", when],
  ];
  let y = 292;
  rows.forEach(([label, value]) => {
    ctx.fillStyle = CERT_C.steel;
    ctx.font = `600 12.5px ${CERT_KR}`;
    ctx.fillText(label, L, y);
    ctx.fillStyle = CERT_C.ink;
    ctx.font = label === "사원 코드" ? `700 21px ${CERT_MONO}` : `700 22px ${CERT_SANS}`;
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
  ctx.fillText("이수 기준: 수신호 7종 전 과정 · 합격 = 수신호마다 시도 3회 안에 정답", L, 624);

  // ── 오른쪽: 교육 결과표
  const TX = 620, TR = R;
  ctx.fillStyle = CERT_C.ink;
  ctx.font = `800 16px ${CERT_KR}`;
  ctx.fillText("교육 결과", TX, 164);
  ctx.textAlign = "right";
  ctx.fillStyle = CERT_C.steel;
  ctx.font = `600 13px ${CERT_KR}`;
  ctx.fillText(`합격 ${passed} / ${completed.length}종 · 첫 시도 정답 ${first}종`, TR, 164);

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

    // 일치율 막대 — 웹과 같이 한 색 채움 + 옅은 트랙, 판정 기준 75% 눈금
    const score = Math.max(0, Math.min(100, item.match_score || 0));
    const mw = 80, mx = col.meter;
    ctx.fillStyle = "rgba(242, 140, 40, 0.18)";
    ctx.fillRect(mx, y - 9, mw, 7);
    ctx.fillStyle = fail ? CERT_C.steelLight : CERT_C.orange;
    ctx.fillRect(mx, y - 9, mw * score / 100, 7);
    ctx.fillStyle = CERT_C.ink;
    ctx.fillRect(mx + mw * 0.75, y - 12, 1.5, 13);
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
  ctx.fillText("판정: 카메라 AI 비전 · 3프레임 연속 확정 · 막대의 눈금 = 판정 기준 75%", TX, y + 8);

  // ── 하단: 발급일 · 발급 기관 · 직인
  ctx.fillStyle = CERT_C.ink;
  ctx.fillRect(L, 668, R - L, 1.5);
  ctx.textAlign = "left";
  ctx.font = `800 20px ${CERT_KR}`;
  ctx.fillText(`${done.getFullYear()}년 ${done.getMonth() + 1}월 ${done.getDate()}일`, L, 712);
  ctx.fillStyle = CERT_C.steel;
  ctx.font = `500 12px ${CERT_KR}`;
  ctx.fillText(`발급 ${stamp(issued)}:${pad2(issued.getSeconds())}`, L, 736);

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

