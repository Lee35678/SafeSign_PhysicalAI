# start_all.sh · stop_all.sh · status.sh 가 함께 쓰는 설정과 함수. 직접 실행하지 않는다.
#
# 모든 값은 환경변수로 덮어쓸 수 있다 — 예:
#   PICAR_SSH=pi@192.168.50.10 bash scripts/rpi/start_all.sh
#
# 실행 위치: RPi5(스테이션). picar(RPi4B)는 RPi5에서 SSH로 다룬다(PC → RPi4B 직접 접속은 안 된다, 07).

# ── 설정 ──────────────────────────────────────────────────────────────────────
REPO="${SAFESIGN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"   # RPi5 쪽 저장소
PICAR_HOST="${PICAR_HOST:-192.168.50.10}"
PICAR_SSH="${PICAR_SSH:-$PICAR_HOST}"          # user@host 또는 ~/.ssh/config 별칭. RPi5와 계정명이 다르면 지정할 것
# RPi4B 쪽 저장소 경로. `$HOME`은 여기서 풀지 않고 RPi4B 셸이 푼다(\$ 로 막아 둔다).
PICAR_REPO="${PICAR_REPO:-\$HOME/git/SafeSign_PhysicalAI}"
SESSION="${SESSION:-safesign}"                 # RPi5 tmux 세션: actuation · vision · web 창
PICAR_SESSION="${PICAR_SESSION:-picar}"        # RPi4B tmux 세션
LOG_ROOT="${LOG_ROOT:-$HOME/safesign_logs}"    # 창별 로그(tmux pipe-pane). 저장소 밖에 둔다

VISION_URL="${VISION_URL:-http://localhost:8001}"
ACTUATION_URL="${ACTUATION_URL:-http://localhost:8002}"
WEB_URL="${WEB_URL:-http://localhost:8000}"
PICAR_URL="${PICAR_URL:-http://${PICAR_HOST}:8000}"

# 비밀번호 로그인이어도 한 번만 묻도록 SSH 연결을 재사용한다.
SSH_OPTS=(-o ConnectTimeout=5 -o ControlMaster=auto -o "ControlPath=/tmp/safesign-ssh-%r@%h:%p" -o ControlPersist=300)

# ── 출력 ──────────────────────────────────────────────────────────────────────
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m⚠\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; }
step() { printf '\n\033[1m[%s]\033[0m %s\n' "$1" "$2"; }

# ── 공통 함수 ─────────────────────────────────────────────────────────────────
picar_ssh() { ssh "${SSH_OPTS[@]}" "$PICAR_SSH" "$@"; }

# jget URL 'python 식(d = 응답 JSON)' [타임아웃초] → 값 출력. 실패하면 빈 문자열.
jget() {
  curl -fsS --max-time "${3:-2}" "$1" 2>/dev/null \
    | python3 -c "import sys, json; d = json.load(sys.stdin); print($2)" 2>/dev/null
}

# wait_until 제한초 설명 명령... → 명령이 성공할 때까지 0.5초 간격으로 다시 시도.
wait_until() {
  local limit="$1" what="$2"; shift 2
  local deadline=$((SECONDS + limit))
  while (( SECONDS < deadline )); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  return 1
}

http_up()   { curl -fsS --max-time 2 "$1" >/dev/null 2>&1; }
http_down() { ! curl -fsS --max-time 1 "$1" >/dev/null 2>&1; }

has_session()       { tmux has-session -t "$SESSION" 2>/dev/null; }
picar_has_session() { picar_ssh "tmux has-session -t $PICAR_SESSION" 2>/dev/null; }

# picar 정지 + LED 소등 (stop_all · 비상시 공용). 성공하면 0.
# 본문은 표준입력으로 넘긴다(명령 줄 인용에 영향받지 않게), "정지"는 JSON 이스케이프로 쓴다(터미널 인코딩 무관).
picar_stop_command() {
  printf '%s' '{"command":"stop","target_signal":"정지","motor":{"action":"stop","speed":0},"led":{"red":"off","yellow_left":"off","yellow_right":"off"}}' \
    | curl -fsS --max-time 2 -H 'Content-Type: application/json' --data-binary @- \
      "$PICAR_URL/picar" >/dev/null 2>&1
}
