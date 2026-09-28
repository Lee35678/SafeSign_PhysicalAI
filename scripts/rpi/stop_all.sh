#!/usr/bin/env bash
# 실물 시연 종료 — README §4.5 "역순, 반드시 Ctrl+C"를 자동화한다. RPi5에서 실행.
#
#   bash scripts/rpi/stop_all.sh
#
# 순서: picar에 정지 명령 → web → vision → actuation → picar(RPi4B) 에 Ctrl+C → 세션 정리
# kill -9는 쓰지 않는다 — actuation이 BLE를 끊지 못하고 죽으면 다음 실행 때 micro:bit가 안 보인다.
# 주행 중에 프로세스를 끝내면 모터는 마지막 명령을 유지하므로 정지 명령을 가장 먼저 보낸다.
# 자세한 사용법·문제 해결: document/17_실물실행_스크립트_사용법.md
set -u -o pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

STUCK=0

# 창에 Ctrl+C를 보내고 포트가 닫힐 때까지 기다린다. $3=1 이면 한 번 더 보내도 된다.
stop_window() {
  local name="$1" url="$2" allow_second="$3"
  if ! tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null | grep -qx "$name"; then
    warn "$name 창 없음 (건너뜀)"; return
  fi
  tmux send-keys -t "$SESSION:$name" C-c
  if wait_until 20 "$name" http_down "$url"; then ok "$name 종료"; return; fi
  if [[ "$allow_second" == 1 ]]; then
    tmux send-keys -t "$SESSION:$name" C-c
    if wait_until 10 "$name" http_down "$url"; then ok "$name 종료 (Ctrl+C 두 번)"; return; fi
  fi
  fail "$name 이 아직 떠 있습니다 → tmux attach -t $SESSION 으로 확인 (kill -9 금지)"
  STUCK=1
}

step 1 "picar 정지 명령"
if picar_stop_command; then
  ok "정지 + LED 소등 전송"
  motion=$(jget "$PICAR_URL/health" 'd["hardware"]["motion_active"]')
  err=$(jget "$PICAR_URL/health" 'd["hardware"]["last_stop_error"]')
  [[ "$err" == None || -z "$err" ]] || warn "last_stop_error=$err — 바퀴가 멈췄는지 눈으로 확인하세요"
  [[ "$motion" == True ]] && warn "motion_active=true — 바퀴가 멈췄는지 눈으로 확인하세요"
else
  warn "picar에 정지 명령을 보내지 못했습니다 — 바퀴가 돌고 있으면 배터리 스위치 OFF"
fi

step 2 "RPi5 서비스 종료 (web → vision → actuation)"
if has_session; then
  stop_window web "$WEB_URL/health" 1
  stop_window vision "$VISION_URL/health" 1
  # actuation은 두 번째 Ctrl+C를 보내지 않는다 — 강제 종료되면 BLE 연결 해제(shutdown)를 건너뛴다
  stop_window actuation "$ACTUATION_URL/health" 0
else
  warn "RPi5에 tmux 세션 '$SESSION'이 없습니다"
fi

step 3 "picar 종료 (RPi4B)"
if picar_has_session; then
  picar_ssh "tmux send-keys -t $PICAR_SESSION:picar C-c"
  if wait_until 20 picar http_down "$PICAR_URL/health"; then ok "picar 종료"
  else fail "picar가 아직 떠 있습니다 → ssh -t $PICAR_SSH tmux attach -t $PICAR_SESSION"; STUCK=1; fi
else
  warn "RPi4B에 tmux 세션 '$PICAR_SESSION'이 없거나 SSH로 붙지 못했습니다"
fi

step 4 "세션 정리"
if (( STUCK )); then
  warn "아직 떠 있는 서비스가 있어 tmux 세션을 남겨 뒀습니다 (로그 확인용)"
  exit 1
fi
has_session && tmux kill-session -t "$SESSION" && ok "RPi5 세션 '$SESSION' 닫음"
picar_has_session && picar_ssh "tmux kill-session -t $PICAR_SESSION" && ok "RPi4B 세션 '$PICAR_SESSION' 닫음"

echo
echo "picar 전원을 끌 때: ssh $PICAR_SSH 'sudo shutdown -h now' → LED가 꺼지면 배터리 스위치 OFF (README §4.5)"
