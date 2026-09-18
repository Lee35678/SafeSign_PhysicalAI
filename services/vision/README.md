# vision — Perception + Cognition (담당: 이동혁)

RACI: 파이프라인·판정로직 **R**, 하드웨어·로봇동작 **A**

`document/02_설계문서_v2.md` §1-1·§4, `document/05_모델카드_v3.md` 기준 담당 범위:

```
Raspberry Pi Camera Module 3 (CSI) → MediaPipe HandLandmarker (LIVE_STREAM)
  → 정규화(원점이동·스케일·회전·좌우손) → 63차원 특징벡터
  → SVM(RBF) 분류(8클래스) + N프레임 연속 확인 → predicted_class, confidence
  → cosine similarity vs DB 템플릿 → match_score(0~100)
```

## 하드웨어/실행 방식 확정 사항 (2026-09-18)

- **카메라**: Raspberry Pi Camera Module 3, CSI 직결 (범용 USB 웹캠 아님) — 15핀→22핀 변환 케이블로
  RPi5 CAM/DISP 포트 연결. 해상도/FPS는 **1920×1080 @ 60fps (Binned Mode)** 확정.
- **MediaPipe 실행 모드**: `LIVE_STREAM`(비동기 콜백) 채택. `VIDEO`(동기 루프) 대비 캡처가 추론을
  기다리지 않아 실시간 처리에 유리 — 근거는 05_모델카드_v3 §3-2.
- **RPi5는 카메라 추론(이 서비스)과 AI Hand/micro:bit(services/actuation)를 겸함.** picar는 더 이상
  RPi5가 구동하지 않는다 — picar가 주행하면 카메라도 함께 이동해버리는 문제가 있어, picar 전용
  컨트롤러를 **별도의 Raspberry Pi 4B 8GB**(`services/picar`)로 분리하고 Wi-Fi로 통신한다
  (10_PRD_v2.md §1.3 참고). 로컬 개발/통합 테스트는 지금처럼 컨테이너로 분리해도 무방하다.
- **카메라가 이 서비스에 직결**되어 있으므로, 외부에서 프레임을 받는 구조가 아니라 **이 서비스가 스스로
  카메라 루프를 돌며 최신 판정 결과를 만들어 둔다.** 다른 서비스(web)는 `GET /latest`로 폴링한다.

## 디렉터리

- `src/perception/capture.py` — 카메라 캡처(picamera2, 실물 도착 전 MOCK_CAMERA) + MediaPipe
  LIVE_STREAM 콜백 → 최신 `landmark_frame` 저장
- `src/cognition/normalize.py` — 정규화 (원점이동·스케일·회전·좌우손 반전)
- `src/cognition/smoothing.py` — N프레임 연속 동일 클래스 확인 (초기값 N=3)
- `src/cognition/classify.py` — SVM 분류 + 일치율 산출 (τ 초기값 0.75)
- `src/app.py` — FastAPI 진입점: 백그라운드로 카메라+판정 루프 실행, `/health`, `/latest`(런타임용),
  `/predict`(카메라 없이 분류기만 테스트하는 개발용)

## 아직 확정 안 된 것 (팀 결정/실측 필요)

- [ ] SVM 하이퍼파라미터(`C`, `gamma`) 최종값 (실측 데이터로 그리드서치, 05_모델카드_v3 §6)
- [ ] τ=0.75, N=3은 초기 기본값 — 카메라/데이터 확보 후 05_모델카드_v3 §8-1 절차로 재검증
- [ ] hand_landmarker.task 모델 파일 다운로드 및 `models/` 배치 (05_모델카드_v3 §1 URL)

## 로컬 실행

```bash
docker compose up --build vision
curl http://localhost:8001/health
curl http://localhost:8001/latest
```

카메라(Pi Camera Module 3)는 아직 팀에 도착하지 않았고, `picamera2`는 Raspberry Pi OS의 apt 패키지라
일반 pip/Docker(x86)에서 설치되지 않습니다. 그래서 기본값 `MOCK_CAMERA=true`로 배선만 검증하고,
실물 카메라 연동은 RPi5 확보 후 `perception/capture.py`의 TODO를 채우세요.

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.app:app --reload --port 8000
```
