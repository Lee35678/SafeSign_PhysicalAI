# 회사 사이트(portal) — 빌드 문맥은 services/ 폴더 (교육장 web의 회원 모듈을 함께 넣는다)
#   docker build -f portal/Dockerfile -t safesign-portal services
FROM python:3.11-slim
WORKDIR /srv
COPY portal/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY web/backend/members.py ./web/backend/members.py
COPY portal/app ./portal/app
COPY portal/frontend ./portal/frontend
WORKDIR /srv/portal
ENV SAFESIGN_WEB_BACKEND=/srv/web/backend MEMBER_DATA_DIR=/srv/data
EXPOSE 8100
# --proxy-headers: HTTPS를 앞단(로드밸런서·호스팅)이 끝낼 때 쿠키 Secure 판단에 X-Forwarded-Proto를 쓴다
# 포트: 호스팅이 주는 $PORT(Render 등) → 없으면 8100
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8100} --proxy-headers --forwarded-allow-ips '*'"]
