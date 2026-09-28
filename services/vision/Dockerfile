FROM python:3.11-slim

WORKDIR /app

# mediapipe 런타임 의존 라이브러리 (내부적으로 OpenCV를 함께 씀)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 주의: 이 이미지로는 CSI 카메라(Pi Camera Module 3)를 쓸 수 없습니다 — RPi5에서 돌려도 같습니다.
# picamera2와 Raspberry Pi판 libcamera는 Raspberry Pi OS apt 전용이라 여기(python:3.11-slim)에 설치되지 않습니다.
# 이 이미지는 개발 PC mock·CI용이고, 실물 vision은 네이티브로 실행합니다(README "RPi5 에서 실행").

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
