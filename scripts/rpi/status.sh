#!/usr/bin/env bash
# 실물 구성 상태 한 번에 보기 — README §4.3 확인 4종 + 온도·스로틀링 + tmux 세션. RPi5에서 실행.
#
#   bash scripts/rpi/status.sh
#   watch -n5 bash scripts/rpi/status.sh      # 시연 중 계속 보기
#
# 읽기만 한다 — 장치를 움직이는 요청은 보내지 않는다.
# 자세한 사용법·문제 해결: document/17_실물실행_스크립트_사용법.md
set -u -o pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

[[ "${1:-}" == --no-header ]] || printf '\033[1mSafeSign 상태\033[0m  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')"

show() {   # show 이름 URL 'python 식'
  local name="$1" url="$2" expr="$3" out
  out=$(jget "$url" "$expr")
  if [[ -n "$out" ]]; then ok "$(printf '%-10s' "$name") $out"; else fail "$(printf '%-10s' "$name") 응답 없음 ($url)"; fi
}

step "서비스" ""
show vision "$VISION_URL/health" \
  '"camera=%s  fps=%s  model=%s  tau=%s  N=%s" % (d["camera"]["state"], d["camera"].get("result_fps"), d["model"]["loaded"], d.get("tau"), d.get("n_frames"))'
show actuation "$ACTUATION_URL/health" \
  '"microbit_connected=%s  mock=%s" % (d["microbit_connected"], d["mock_hardware"])'
show picar "$PICAR_URL/health" \
  '"status=%s  i2c=%s  motion=%s  stop_error=%s  max_speed=%s  mock=%s" % (d["status"], d["hardware"]["i2c"]["reachable"], d["hardware"]["motion_active"], d["hardware"]["last_stop_error"], d["hardware"]["max_speed_pct"], d["mock_hardware"])'
show web "$WEB_URL/api/state" \
  '"state=%s  progress=%s/%s  devices=%s" % (d["state"], d["progress"]["current"], d["progress"]["total"], {k: v.get("status") for k, v in d["devices"].items()})'

step "보드" ""
ok "RPi5   $(vcgencmd measure_temp 2>/dev/null)  $(vcgencmd get_throttled 2>/dev/null)"
remote=$(picar_ssh 'vcgencmd measure_temp; vcgencmd get_throttled' 2>/dev/null | tr '\n' ' ')
if [[ -n "$remote" ]]; then ok "RPi4B  $remote"; else warn "RPi4B  SSH로 읽지 못함 ($PICAR_SSH)"; fi

step "tmux" ""
if has_session; then ok "RPi5 '$SESSION': $(tmux list-windows -t "$SESSION" -F '#I:#W' | tr '\n' ' ')"
else warn "RPi5 '$SESSION' 세션 없음"; fi
if picar_has_session; then ok "RPi4B '$PICAR_SESSION' 세션 있음"; else warn "RPi4B '$PICAR_SESSION' 세션 없음"; fi
