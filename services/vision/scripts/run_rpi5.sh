#!/usr/bin/env bash
# RPi5 + Camera Module 3(CSI) 에서 vision 서비스를 네이티브로 띄운다 (Docker 아님).
#
#   cd services/vision
#   bash scripts/run_rpi5.sh            # 0.0.0.0:8001
#   PORT=8002 bash scripts/run_rpi5.sh
#
# 준비는 README "RPi5 에서 실행" 참고 (apt python3-picamera2 · --system-site-packages venv · 모델 복사).
# 환경변수는 그대로 덮어쓸 수 있다 — 예: CAPTURE_SIZE=1920x1080 CAPTURE_FPS=60 bash scripts/run_rpi5.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .venv/bin/activate ] && source .venv/bin/activate

if [ ! -f models/svm_classifier.joblib ]; then
  echo "⚠️  models/svm_classifier.joblib 이 없습니다 (git 에 없음 — 노트북에서 scp 로 복사)."
  echo "    지금 띄우면 모든 판정이 model_not_loaded 로 나옵니다."
fi
if ! python -c "import picamera2" 2>/dev/null; then
  echo "⚠️  picamera2 를 불러올 수 없습니다."
  echo "    sudo apt install -y python3-picamera2  +  venv 는 --system-site-packages 로 만들 것"
fi

export MOCK_CAMERA=false
export CAMERA_SOURCE="${CAMERA_SOURCE:-csi}"
export PYTHONIOENCODING=utf-8

exec python -m uvicorn app:app --app-dir src --host "${HOST:-0.0.0.0}" --port "${PORT:-8001}"
