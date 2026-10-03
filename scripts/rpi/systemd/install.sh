#!/usr/bin/env bash
# SafeSign systemd 유닛 설치 — 보드가 재부팅되거나 서비스가 죽으면 자동으로 다시 띄운다.
# ⚠️ 2026-10-03 작성, 실물 미검증. 시연·KPI 측정은 지금처럼 start_all.sh(tmux)로 한다.
#
#   sudo bash scripts/rpi/systemd/install.sh rpi5             # RPi5: actuation·vision·web 설치만 (켜지 않음)
#   sudo bash scripts/rpi/systemd/install.sh rpi5 --enable    # 설치 + 부팅 시 자동 시작 + 지금 시작
#   sudo bash scripts/rpi/systemd/install.sh rpi4b [--enable] # RPi4B: picar
#   sudo bash scripts/rpi/systemd/install.sh uninstall        # 끄고 지운다(그 보드에 있는 것만)
#
# tmux(start_all.sh)와 systemd는 둘 중 하나만 쓴다 — 둘 다 켜면 포트가 겹치고 micro:bit BLE 연결을 서로 뺏는다.
# systemd로 켠 상태에서 start_all.sh를 쓰려면 먼저: sudo systemctl stop safesign-web safesign-vision safesign-actuation
# 로그: journalctl -u safesign-actuation -f   ·   상태: systemctl status 'safesign-*'
# start_all.sh의 사전 점검(BLE 스캔 꺼짐, get_throttled, 두 보드 커밋 일치, picar 안전 확인)은 하지 않는다.
#
# 환경변수: PICAR_URL(기본 http://192.168.50.10:8000, web이 picar를 부르는 주소)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
PICAR_URL="${PICAR_URL:-http://192.168.50.10:8000}"
ALL_UNITS=(safesign-web safesign-vision safesign-actuation safesign-picar)

usage() { sed -n '2,15p' "$0"; }

case "${1:-}" in
  rpi5)      UNITS=(safesign-actuation safesign-vision safesign-web) ;;
  rpi4b)     UNITS=(safesign-picar) ;;
  uninstall) UNITS=() ;;
  -h|--help) usage; exit 0 ;;
  *)         usage; exit 2 ;;
esac
ENABLE=0
[[ "${2:-}" == --enable ]] && ENABLE=1

[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요: sudo bash $0 $*"; exit 1; }

if [[ "$1" == uninstall ]]; then
  for u in "${ALL_UNITS[@]}"; do
    if [[ -f "/etc/systemd/system/$u.service" ]]; then
      systemctl disable --now "$u" || true
      rm -f "/etc/systemd/system/$u.service"
      echo "제거: $u"
    fi
  done
  systemctl daemon-reload
  exit 0
fi

for u in "${UNITS[@]}"; do
  dir="$REPO/services/${u#safesign-}"
  [[ -d "$dir/.venv" ]] || { echo "$dir/.venv 가 없습니다 (README §4.1)"; exit 1; }
  sed -e "s|@REPO@|$REPO|g" -e "s|@USER@|$RUN_USER|g" -e "s|@PICAR_URL@|$PICAR_URL|g" \
    "$HERE/$u.service" > "/etc/systemd/system/$u.service"
  echo "설치: /etc/systemd/system/$u.service  (계정 $RUN_USER, 저장소 $REPO)"
done
systemctl daemon-reload

if (( ENABLE )); then
  if pgrep -af '[u]vicorn' >/dev/null; then
    pgrep -af '[u]vicorn'
    echo "uvicorn이 이미 떠 있습니다(start_all.sh tmux?) — bash scripts/rpi/stop_all.sh 로 먼저 끄세요"
    exit 1
  fi
  systemctl enable --now "${UNITS[@]}"
  systemctl --no-pager --lines=0 status "${UNITS[@]}" || true
else
  echo
  echo "설치만 했습니다(켜지 않음). 켜기: sudo systemctl enable --now ${UNITS[*]}"
fi
