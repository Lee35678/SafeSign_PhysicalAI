# vision — Perception + Cognition (담당: 이동혁)

RACI: 파이프라인·판정로직 **R**, 하드웨어·로봇동작 **A**

`document/02_설계문서_v1.md` §1~2, `document/시스템_구성도_초안.md` 기준 담당 범위:

```
[USB 웹캠] → [MediaPipe Hand Landmarker] → 21 keypoints
          → 정규화(원점이동·스케일·회전정렬) → 63차원 특징벡터
          → 분류기(SVM/MLP) + 분야별 라벨 매핑 → predicted_class, confidence
          → cosine similarity vs DB 템플릿 → match_score(0~100)
```

## 디렉터리

- `src/perception/` — 카메라 캡처, MediaPipe 랜드마크 추출 (`shared/schemas/landmark_frame.schema.json` 출력)
- `src/cognition/` — 정규화, 분류기, 일치율(유사도) 산출 (`shared/schemas/judgment_result.schema.json` 출력)
- `src/app.py` — FastAPI 진입점 (`/health`, `/predict`)

## 아직 확정 안 된 것 (팀 결정 필요, 02_설계문서_v1 참고)

- [ ] 파이프라인 방식: 랜드마크 기반 vs 이미지 분류 기반 (§2)
- [ ] 최종 채택 5종 수신호 (§4)
- [ ] 카메라 해상도/FPS (03_인터페이스계약서_v1 §2)
- [ ] 신뢰도 임계값 τ (`.env`의 `CONFIDENCE_THRESHOLD`)

## 로컬 실행

```bash
docker compose up --build vision
curl http://localhost:8001/health
```

카메라 장치는 Windows Docker Desktop에서 컨테이너로 직접 전달되지 않으므로, 로컬 개발 중에는
가상환경(`python -m venv`)에서 직접 실행해 웹캠으로 테스트하고, 컨테이너 빌드는 배포/RPi5 대상 검증용으로 사용하세요.

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.app:app --reload --port 8000
```
