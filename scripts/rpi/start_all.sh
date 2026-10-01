#!/usr/bin/env bash
# 실물 시연 기동 — README §4.2의 "터미널 4개"를 tmux로 자동화한다. RPi5에서 실행.
#
#   bash scripts/rpi/start_all.sh        # 사전 점검 → picar(RPi4B) → actuation → vision → web
#   bash scripts/rpi/start_all.sh -y     # picar 안전 확인 질문 생략
#   bash scripts/rpi/start_all.sh -h     # 이 도움말
#
# 자세한 사용법·문제 해결: document/17_실물실행_스크립트_사용법.md
#
# 끝나면  tmux attach -t safesign   (창 이동 Ctrl+b 0~2, 빠져나오기 Ctrl+b d — 서비스는 계속 돈다)
# picar   ssh -t <RPi4B> tmux attach -t picar
# 종료    bash scripts/rpi/stop_all.sh   (역순 Ctrl+C. kill -9 금지 — BLE 연결이 BlueZ에 남는다)
#
# SSH가 끊겨도 서비스는 tmux 안에서 계속 돈다(README §4.5의 "SSH 끊김 → BLE 연결 잔류" 방지).
set -u -o pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

ASSUME_YES=0
case "${1:-}" in
  -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
  -y)        ASSUME_YES=1 ;;
  "")        ;;
  *)         echo "알 수 없는 옵션: $1  (bash scripts/rpi/start_all.sh -h)"; exit 2 ;;
esac

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$LOG_ROOT/$TS"

abort() {
  fail "$*"
  echo
  echo "중단했습니다. 이미 띄운 서비스가 있으면: bash scripts/rpi/stop_all.sh"
  exit 1
}

# 창 하나를 만들고 명령을 입력한다 — 사람이 터미널에 치는 것과 같아서, 끝난 뒤에도 셸이 남아
# ↑ Enter로 다시 띄울 수 있다.
start_window() {
  local name="$1" dir="$2" cmd="$3"
  if [[ "$name" == actuation ]]; then
    tmux new-session -d -s "$SESSION" -n "$name" -c "$dir" || return 1
    tmux set-option -t "$SESSION" mouse on >/dev/null
  else
    tmux new-window -t "$SESSION" -n "$name" -c "$dir" || return 1
  fi
  tmux pipe-pane -t "$SESSION:$name" -o "cat >> '$LOG_DIR/$name.log'"
  tmux send-keys -t "$SESSION:$name" "$cmd" Enter
}

# ── 0. 사전 점검 ──────────────────────────────────────────────────────────────
step 0 "사전 점검"
command -v tmux >/dev/null || abort "RPi5에 tmux가 없습니다 → sudo apt install -y tmux"
command -v curl >/dev/null || abort "RPi5에 curl이 없습니다 → sudo apt install -y curl"
has_session && abort "tmux 세션 '$SESSION'이 이미 있습니다 → 상태: bash scripts/rpi/status.sh · 종료: bash scripts/rpi/stop_all.sh"
# '[u]vicorn': 이 검사 명령 자체(원격 실행 시 셸 명령 줄)가 걸리지 않게 하는 패턴
if pgrep -af '[u]vicorn' >/dev/null; then
  pgrep -af '[u]vicorn'
  abort "RPi5에 uvicorn이 이미 떠 있습니다 — 포트가 겹치고 micro:bit는 BLE 연결을 하나만 받습니다. 먼저 끄세요"
fi
ok "RPi5: tmux 있음, 남아 있는 uvicorn 없음"

disc=$(bluetoothctl show 2>/dev/null | awk '/Discovering/ {print $2}')
[[ "$disc" == yes ]] && abort "BLE 스캔이 켜져 있습니다(Discovering: yes) → scan on 켠 창에서 scan off, 모르면 pkill bluetoothctl"
if [[ -n "$disc" ]]; then ok "BLE Discovering: $disc"; else warn "bluetoothctl 상태를 읽지 못했습니다"; fi

[[ -f "$REPO/services/vision/models/svm_classifier.joblib" ]] \
  || abort "vision 분류 모델 없음: services/vision/models/svm_classifier.joblib (git에 없음 — 노트북에서 scp로 복사)"
[[ -f "$REPO/services/vision/models/hand_landmarker.task" ]] \
  || abort "MediaPipe 모델 없음: services/vision/models/hand_landmarker.task (git에 포함 — git pull 또는 checkout 확인)"
ok "vision 모델 파일 2개 있음"
for d in actuation web; do
  [[ -f "$REPO/services/$d/.venv/bin/activate" ]] || abort "services/$d/.venv 가 없습니다 (README §4.1)"
done
ok "actuation · web 가상환경 있음"

thr=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
if [[ "$thr" == 0x0 ]]; then ok "RPi5 get_throttled=0x0"
else warn "RPi5 get_throttled=${thr:-?} — 한 번 선 비트는 재부팅 전까지 남습니다. KPI 측정이면 재부팅 후 다시 시작하세요"; fi

picar_ssh true || abort "RPi4B에 SSH로 붙지 못했습니다($PICAR_SSH) → 계정이 다르면 PICAR_SSH=계정@$PICAR_HOST 로 지정, 연결은 ping $PICAR_HOST"
picar_ssh 'command -v tmux' >/dev/null || abort "RPi4B에 tmux가 없습니다 → ssh $PICAR_SSH 'sudo apt install -y tmux'"
picar_has_session && abort "RPi4B에 tmux 세션 '$PICAR_SESSION'이 이미 있습니다 → stop_all.sh"
if picar_ssh "pgrep -af '[u]vicorn'"; then abort "RPi4B에 uvicorn이 이미 떠 있습니다 — 먼저 끄세요"; fi
picar_ssh "test -f $PICAR_REPO/services/picar/.venv/bin/activate" || abort "RPi4B에 services/picar/.venv 가 없습니다 (README §4.1)"
pthr=$(picar_ssh 'vcgencmd get_throttled' 2>/dev/null | cut -d= -f2)
if [[ "$pthr" == 0x0 ]]; then ok "RPi4B get_throttled=0x0"
else warn "RPi4B get_throttled=${pthr:-?} — 저전압 비트면 배터리 잔량을 확인하세요(13 §4)"; fi
ok "RPi4B: SSH · tmux · 가상환경 확인"

# 두 보드가 같은 코드로 도는지 — KPI 기록(06 §1-1)의 "기준 커밋"이 된다
commit5=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)
commit4=$(picar_ssh "git -C $PICAR_REPO rev-parse --short HEAD" 2>/dev/null)
if [[ -n "$commit5" && "$commit5" == "$commit4" ]]; then ok "두 보드 커밋 같음 ($commit5)"
else warn "커밋이 다릅니다 — RPi5 ${commit5:-?} · RPi4B ${commit4:-?} (양쪽에서 git pull 권장)"; fi
if [[ -n "$(git -C "$REPO" status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
  warn "RPi5 작업 트리에 커밋 안 된 수정이 있습니다 — KPI 기록의 기준 커밋이 불명확해집니다"
fi

if (( ! ASSUME_YES )); then
  echo
  echo "  picar 안전 확인"
  echo "   - 바퀴를 띄웠거나 주행 공간이 비어 있다"
  echo "   - RPi4B에 USB-C 어댑터가 꽂혀 있지 않다 (배터리 급전과 동시 연결 금지, README §4.2)"
  echo "   - 배터리 스위치가 손 닿는 곳에 있다 (비상정지 수단)"
  read -r -p "  모두 확인했으면 y 입력: " ans
  [[ "$ans" == y ]] || abort "취소했습니다"
fi

mkdir -p "$LOG_DIR"
ENV_FILE="$LOG_DIR/env.txt"   # 06 §1-1 테스트 환경 기록에 그대로 옮길 수 있게 남긴다
{
  echo "시작        $(date '+%Y-%m-%d %H:%M:%S')"
  echo "RPi5 커밋   ${commit5:-?}"
  echo "RPi4B 커밋  ${commit4:-?}"
  echo "RPi5        $(vcgencmd measure_temp 2>/dev/null)  get_throttled=${thr:-?}"
  echo "RPi4B       get_throttled=${pthr:-?}"
  echo "PICAR_URL   $PICAR_URL"
} > "$ENV_FILE"

# ── 1. picar (RPi4B) ─────────────────────────────────────────────────────────
step 1 "picar 기동 (RPi4B $PICAR_HOST)"
PICAR_CMD='source .venv/bin/activate && MOCK_HARDWARE=false uvicorn app:app --app-dir src --host 0.0.0.0 --port 8000'
picar_ssh "mkdir -p \$HOME/safesign_logs/$TS \
  && tmux new-session -d -s $PICAR_SESSION -n picar -c $PICAR_REPO/services/picar \
  && tmux set-option -t $PICAR_SESSION mouse on >/dev/null \
  && tmux pipe-pane -t $PICAR_SESSION:picar -o 'cat >> \$HOME/safesign_logs/$TS/picar.log' \
  && tmux send-keys -t $PICAR_SESSION:picar '$PICAR_CMD' Enter" \
  || abort "RPi4B에 tmux 세션을 만들지 못했습니다"
wait_until 25 picar http_up "$PICAR_URL/health" \
  || abort "picar /health 응답 없음 → ssh -t $PICAR_SSH tmux attach -t $PICAR_SESSION 으로 로그 확인"
[[ "$(jget "$PICAR_URL/health" 'd["mock_hardware"]')" == False ]] \
  || abort "picar가 mock 모드입니다 — MOCK_HARDWARE=false로 떴는지 확인"
i2c=$(jget "$PICAR_URL/health" 'd["hardware"]["i2c"]["reachable"]')
if [[ "$i2c" == True ]]; then ok "picar 정상 (i2c.reachable=true)"
else warn "picar는 떴지만 i2c.reachable=$i2c — 모터가 안 움직입니다(sudo raspi-config nonint do_i2c 0, 배선 확인)"; fi

# ── 2. actuation (RPi5) ──────────────────────────────────────────────────────
step 2 "actuation 기동 (AI Hand + micro:bit BLE)"
start_window actuation "$REPO/services/actuation" \
  'source .venv/bin/activate && MOCK_HARDWARE=false uvicorn app:app --app-dir src --host 0.0.0.0 --port 8002' \
  || abort "tmux 세션을 만들지 못했습니다"
# 기동 때 BLE 스캔(최대 5초) + 연결이 끝나야 /health가 응답한다
wait_until 40 actuation http_up "$ACTUATION_URL/health" \
  || abort "actuation /health 응답 없음 → tmux attach -t $SESSION (창 0) 로그 확인"
[[ "$(jget "$ACTUATION_URL/health" 'd["mock_hardware"]')" == False ]] || abort "actuation이 mock 모드입니다"
if [[ "$(jget "$ACTUATION_URL/health" 'd["microbit_connected"]')" == True ]]; then
  ok "actuation 정상 (micro:bit BLE 연결됨)"
else
  warn "micro:bit 미연결 — micro:bit 리셋 후 첫 명령 때 재연결을 시도합니다. 안 되면 README §4.6(bluetoothctl disconnect)"
fi

# ── 3. vision (RPi5) ─────────────────────────────────────────────────────────
step 3 "vision 기동 (CSI 카메라 + 판정)"
start_window vision "$REPO/services/vision" 'bash scripts/run_rpi5.sh' || abort "vision 창을 만들지 못했습니다"
wait_until 60 vision http_up "$VISION_URL/health" \
  || abort "vision /health 응답 없음 → tmux attach -t $SESSION (창 1) 로그 확인"
camera_running() { [[ "$(jget "$VISION_URL/health" 'd["camera"]["state"]')" == running ]]; }
if wait_until 30 camera camera_running; then
  ok "vision 카메라 running ($(jget "$VISION_URL/health" '"%s fps" % d["camera"].get("result_fps")'))"
else
  abort "카메라 상태 $(jget "$VISION_URL/health" 'd["camera"]["state"]'): $(jget "$VISION_URL/health" 'd["camera"].get("error")')"
fi
[[ "$(jget "$VISION_URL/health" 'd["model"]["loaded"]')" == True ]] \
  && ok "분류 모델 로드됨" || warn "분류 모델이 로드되지 않았습니다 — 모든 판정이 model_not_loaded"

# ── 4. web (RPi5) ────────────────────────────────────────────────────────────
step 4 "web 기동"
# URL 3개를 모두 명시한다 — web은 기동 때 저장소 루트 .env를 읽어 빈 환경변수를 채우는데(members._load_dotenv),
# .env.example을 복사한 .env에는 docker-compose용 http://vision:8000 · http://actuation:8000 이 들어 있다
start_window web "$REPO/services/web" \
  "source .venv/bin/activate && VISION_URL=$VISION_URL ACTUATION_URL=$ACTUATION_URL PICAR_URL=$PICAR_URL uvicorn backend.app:app --host 0.0.0.0 --port 8000" \
  || abort "web 창을 만들지 못했습니다"
wait_until 30 web http_up "$WEB_URL/health" \
  || abort "web /health 응답 없음 → tmux attach -t $SESSION (창 2) 로그 확인"
devices_ok() {
  [[ "$(jget "$WEB_URL/api/state" 'all(v.get("status") == "ok" for v in d["devices"].values())')" == True ]]
}
# web은 장치 상태를 5초마다 확인한다
if wait_until 15 devices devices_ok; then ok "web 정상 (장치 3개 ok)"
else warn "web 장치 상태: $(jget "$WEB_URL/api/state" 'd["devices"]')"; fi

# ── 5. 요약 ──────────────────────────────────────────────────────────────────
# 서비스별 /health 원문 — vision은 모델 번들 메타데이터(trained_at·sklearn_version 등)를 담고 있다
for pair in "vision $VISION_URL/health" "actuation $ACTUATION_URL/health" "picar $PICAR_URL/health"; do
  set -- $pair
  printf '%-11s %s\n' "$1" "$(curl -fsS --max-time 2 "$2" 2>/dev/null)" >> "$ENV_FILE"
done

step 5 "상태"
bash "$(dirname "${BASH_SOURCE[0]}")/status.sh" --no-header

ip_eth=$(ip -4 addr show eth0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1)
echo
echo "브라우저:   http://${ip_eth:-<RPi5 유선 주소>}:8000"
echo "로그 보기:  tmux attach -t $SESSION   (창 0 actuation · 1 vision · 2 web, 빠져나오기 Ctrl+b d)"
echo "로그 파일:  $LOG_DIR/  (env.txt = 실행 환경 기록, picar 로그는 RPi4B ~/safesign_logs/$TS/)"
echo "종료:       bash scripts/rpi/stop_all.sh"
