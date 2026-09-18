FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

EXPOSE 8000
# ⚠️ --app-dir src 필수: aihand/microbit 패키지가 src/ 아래에 있어서, 이것 없이
#    `uvicorn src.app:app`로 띄우면 ModuleNotFoundError로 컨테이너가 즉시 죽는다.
CMD ["uvicorn", "app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
