FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

EXPOSE 8000
# --app-dir src: app.py 안의 `from aihand import ...` / `from microbit import ...`가 절대 임포트라
# src 디렉터리 자체가 sys.path에 있어야 한다. "uvicorn src.app:app"(app-dir=".")로 실행하면
# aihand/microbit가 top-level 모듈로 보이지 않아 ModuleNotFoundError가 난다.
CMD ["uvicorn", "app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
