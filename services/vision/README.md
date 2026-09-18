# vision — Perception + Cognition (담당: 이동혁)

RACI: 파이프라인·판정로직 **R**, 하드웨어·로봇동작 **A**

```
Raspberry Pi Camera Module 3 (CSI) → MediaPipe HandLandmarker (LIVE_STREAM)
  → 정규화(좌우손·원점·스케일·회전) → 63차원 특징벡터
  → SVM(RBF) 분류(8클래스) + τ 미달 미판정 + N프레임 연속 확인 → predicted_class, confidence
  → 템플릿 cosine similarity → match_score(0~100)
```

근거 문서: `document/05_모델카드_v3.md`(모델 카드) · `document/02_설계문서_v2.md` §1-1·§4 ·
`document/03_인터페이스계약서_v2.md` §2~4 · `document/10_PRD_v2.md`

---

## 1. 지금 바로 알아야 할 것

- **학습은 Colab에서, 추론은 여기서.** 로컬 GPU 한계로 분류기 학습은
  [`training/train_svm_colab.ipynb`](training/train_svm_colab.ipynb)에서 돌리고, 결과 파일
  `svm_classifier.joblib` 하나만 [`models/`](models/README.md)에 넣으면 서비스가 바로 쓴다.
- **모델이 없어도 서비스는 뜬다.** 데이터·카메라가 아직 없으므로 기본 동작은 "항상 미판정"이다
  (`reason: model_not_loaded`). 배선·통합 검증을 먼저 하라는 PRD 우선순위(10_PRD_v2 §11)에 맞춘 설계.
- **왜 이런 알고리즘/전처리인지**는 [`MODEL_TRAINING.md`](MODEL_TRAINING.md)에 정리했다.

## 2. 디렉터리

```
src/
├── app.py                    FastAPI 진입점 (/health, /latest, /predict, /reset)
├── perception/capture.py     Pi Camera Module 3 + MediaPipe LIVE_STREAM 콜백 → landmark_frame
└── cognition/
    ├── normalize.py          21 keypoints → 63차원 특징벡터 (학습·추론 공용, 05_모델카드_v3 §3-5)
    ├── classify.py           SVM 추론 + τ 판정 + match_score → judgment_result
    ├── model_store.py        Colab 산출 번들(joblib) 로드 (없으면 안전하게 미판정)
    ├── templates.py          템플릿 DB 조회 + cosine similarity → 0~100 매핑
    └── smoothing.py          N프레임 연속 동일 클래스 확인 (§3-6)
training/train_svm_colab.ipynb   Colab 학습 노트북
scripts/make_dummy_dataset.py    (데이터 오기 전) 예행연습용 더미 데이터 생성기
models/                          학습된 번들을 넣는 자리
tests/                           정규화 불변성 + 분류 경로 테스트
```

## 3. API

| 엔드포인트 | 용도 |
| --- | --- |
| `GET /health` | 서비스 상태 + **모델 적재 여부/τ/클래스/템플릿 목록** |
| `GET /latest` | 최신 판정 결과(judgment_result). **웹 상태머신이 폴링하는 실제 런타임 경로** |
| `POST /predict` | landmark_frame 하나를 직접 넣어 분류기만 테스트(카메라 미사용, 개발용) |
| `POST /reset` | 다음 수신호로 넘어갈 때 N프레임 누적 초기화 |

카메라가 이 서비스에 직결되어 있어서, 런타임에는 외부가 프레임을 보내는 게 아니라 **이 서비스가 스스로
카메라 루프를 돌며 최신 판정을 만들어 둔다**. 그래서 웹은 `/latest`만 읽으면 된다.

`judgment_result`에는 `reason` 필드가 붙는다 — 웹이 **SC-04(카메라 인식 실패: `no_hand`,
`normalize_failed`)** 와 **SC-03b(재시도 유도: `below_tau`, `awaiting_consecutive_frames`)** 를
구분하는 근거다 (03_인터페이스계약서_v2 §4).

## 4. 하드웨어/실행 방식 확정 사항

- **카메라**: Raspberry Pi Camera Module 3, CSI 직결(범용 USB 웹캠 아님), **1920×1080 @ 60fps (Binned Mode)**
- **MediaPipe 실행 모드**: `LIVE_STREAM`(비동기 콜백) — 캡처가 추론을 기다리지 않아 실시간에 유리 (05_모델카드_v3 §3-2)
- **RPi5는 카메라 추론 + AI Hand/micro:bit 담당**. picar는 별도 보드(RPi4B 8GB, `services/picar`)가
  Wi-Fi로 받아 구동한다 — picar가 움직이면 카메라도 같이 움직이는 문제 때문 (10_PRD_v2 §1.3)
- **τ=0.75, N=3프레임**은 실측 전 초기 기본값. 학습을 돌리면 번들에 든 τ가 자동 적용된다
  (환경변수 `CONFIDENCE_THRESHOLD`로 덮어쓰기 가능)

## 5. 로컬 실행

```bash
docker compose up --build vision
curl http://localhost:8001/health      # model.loaded, tau, n_frames 확인
curl http://localhost:8001/latest
```

카메라(Pi Camera Module 3)가 아직 없고 `picamera2`는 Raspberry Pi OS apt 패키지라 x86 Docker에
설치되지 않는다. 그래서 기본값 `MOCK_CAMERA=true`로 "손 미검출" 프레임만 흘려보내며 배선을 검증하고,
실물 카메라 연동은 RPi5 확보 후 `perception/capture.py`의 TODO를 채운다(네이티브 실행 권장).

### 테스트

```bash
cd services/vision
python tests/test_normalize.py      # 정규화 불변성(위치/크기/회전/좌우손) 10개
python tests/test_classify.py       # 모델 없이도 안전하게 미판정하는지 4개
# pytest가 있으면: python -m pytest tests -q
```

### 데이터 오기 전에 학습 파이프라인 예행연습

```bash
python scripts/make_dummy_dataset.py          # training/_dummy_dataset/ 에 합성 데이터 생성
# 노트북의 PROCESSED_DIR을 이 경로로 바꿔 한 바퀴 돌려보면 형식/배선을 미리 확인할 수 있다
```

> 합성 좌표라 정확도 수치는 아무 의미가 없다. **형식과 배선 확인용**이다.

## 6. 남은 일

- [ ] 실제 수신호 데이터 확보 후 Colab 학습 → `models/svm_classifier.joblib` 배치 (데이터 담당과 형식 합의 필요)
- [ ] `perception/capture.py`의 picamera2 연동 (카메라 도착 후)
- [ ] `hand_landmarker.task` 모델 번들 다운로드 → `models/` (05_모델카드_v3 §1 URL)
- [ ] 실측 후 τ·N프레임 재검증, 05_모델카드_v3 §7-3 실측 표 채우기
- [ ] `/latest` 폴링 → WebSocket 전환 검토 (지연 KPI 여유 없을 때)
