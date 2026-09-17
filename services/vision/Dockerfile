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

EXPOSE 8000
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
