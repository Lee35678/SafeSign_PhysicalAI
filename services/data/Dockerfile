FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# 이 서비스는 상시 API가 아니라 도구 스크립트 실행용입니다 (docker-compose.yml profiles: tools 참고).
CMD ["python", "src/init_db.py"]
