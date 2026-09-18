FROM python:3.11-slim

WORKDIR /app

# mediapipe 런타임 의존 라이브러리 (내부적으로 OpenCV를 함께 씀)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 주의: 이 이미지에는 picamera2를 설치하지 않습니다 (requirements.txt 참고).
# 실물 RPi5에 Pi Camera Module 3를 연동할 때는 이 컨테이너 방식 대신
# Raspberry Pi OS에서 apt로 picamera2를 설치한 네이티브 실행을 권장합니다.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
# 학습된 분류기 번들(svm_classifier.joblib)을 넣는 자리. 파일이 없어도 이미지는 빌드되고,
# 서비스는 "모델 없음" 상태로 뜬다(항상 미판정). docker-compose가 이 경로를 호스트와 바인드 마운트하므로
# 로컬에서 파일만 교체하면 재빌드 없이 반영된다.
COPY models ./models

EXPOSE 8000
# ⚠️ --app-dir src 필수: cognition/perception 패키지가 src/ 아래에 있어서, 이것 없이
#    `uvicorn src.app:app`로 띄우면 ModuleNotFoundError로 컨테이너가 즉시 죽는다.
CMD ["uvicorn", "app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
