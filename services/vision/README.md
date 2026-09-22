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

- **학습도 추론도 로컬에서 한다** (2026-09-21 정정). 전체 27,735건 학습이 16초라 Colab이 필요
  없었다. `python training/train_svm.py` 한 줄이면 [`models/`](models/README.md)에 번들이 생긴다.
  Colab 노트북은 대체 경로로만 남겨둔다.
- **학습 클래스는 7종이다.** `negative`는 학습하지 않고, τ 미달·소속 게이트 차단을 미판정으로
  처리해 그 출력 라벨로만 쓴다 (2026-09-21 회의 안건 2 A).
- **특징은 관절 각도·거리 23차원**(`joint23`)이다. 좌표 63차원보다 +11.1%p 낫다
  ([`MODEL_TRAINING.md`](MODEL_TRAINING.md) §2-2).
- **소속 게이트**가 "7종이 아닌 손모양"을 막는다. τ만으로는 못 막는 구조적 한계가 있어서다
  (같은 문서 §2-3).
- **손 방향 축(69차원)은 구현돼 있지만 꺼져 있다.** 손을 기울여도 100%가 나와 켤 근거가 없다.
- **모델이 없어도 서비스는 뜬다.** 데이터·카메라가 아직 없으므로 기본 동작은 "항상 미판정"이다
  (`reason: model_not_loaded`). 배선·통합 검증을 먼저 하라는 PRD 우선순위(10_PRD_v2 §11)에 맞춘 설계.
- **왜 이런 알고리즘/전처리인지**는 [`MODEL_TRAINING.md`](MODEL_TRAINING.md)에 정리했다.

## 2. 디렉터리

```
src/
├── app.py                    FastAPI 진입점 (/health, /latest, /predict, /reset)
├── perception/capture.py     Pi Camera Module 3 + MediaPipe LIVE_STREAM 콜백 → landmark_frame
└── cognition/
    ├── normalize.py          21 keypoints → 63차원(+방향 6) 특징벡터 (학습·추론 공용, 05 §3-5)
    ├── classify.py           SVM 추론 + τ 판정 + match_score → judgment_result
    ├── model_store.py        학습 번들(joblib) 로드 + feature_mode 확인 (없으면 안전하게 미판정)
    ├── templates.py          템플릿 DB 조회 + cosine similarity → 0~100 매핑
    └── smoothing.py          N프레임 연속 동일 클래스 확인 (§3-6)
training/
├── train_svm.py                 로컬 학습 스크립트 (기본 경로)
└── train_svm_colab.ipynb        Colab 노트북 (대체 경로)
scripts/
├── webcam_check.py              노트북 웹캠으로 학습된 모델을 눈으로 확인 (--log 로 진단 로그)
├── record_dataset.py            KPI 측정용 평가 데이터 촬영 (카운트다운 + 테이크 관리)
├── evaluate_kpi.py              자체 촬영 데이터로 KPI 5개 지표 계산
├── analyze_log.py               webcam_check 로그 분석 (오판정 원인 추적)
└── make_dummy_dataset.py        (데이터 오기 전) 예행연습용 더미 데이터 생성기
models/                          학습된 번들을 넣는 자리
tests/                           카메라 없이 도는 단위 테스트 (정규화 불변성 + 분류 경로)
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

### 확인 방법 두 가지 (용도가 다름)

**① 단위 테스트 — 카메라 없이, 로직만** (CI/머지 전 검증용)

```bash
cd services/vision
python tests/test_normalize.py      # 정규화 불변성 + 방향 축 + 관절 특징 21개
python tests/test_classify.py       # 모델 없이도 안전하게 미판정하는지 4개
python tests/test_gate.py           # 소속 게이트 분기 7개
# pytest가 있으면: python -m pytest tests -q
```

**② 웹캠 확인 — 학습한 모델을 실제 손으로** (사람이 눈으로 판단)

```bash
cd services/vision
python -m venv .venv && .venv\Scripts\activate    # mediapipe가 numpy를 내릴 수 있어 venv 권장
pip install -r requirements-dev.txt

python scripts/webcam_check.py                    # 기본 카메라
python scripts/webcam_check.py --list-cameras     # 카메라 인덱스 확인
python scripts/webcam_check.py --camera 1
python scripts/webcam_check.py --no-window --max-frames 60   # 창 없이 콘솔만
```

- 화면에 **예측 클래스 / confidence / match_score / N프레임 진행도 / 지연·FPS** 가 표시된다.
  `q`·`ESC` 종료, `r` 누적 초기화.
- 추론 경로는 **운영 코드와 동일**(`cognition/*`)하고 웹캠 캡처 부분만 다르다. 여기서 잘 맞히면
  RPi5에서도 같은 판정이 나온다.
- `hand_landmarker.task`가 없으면 공식 URL에서 **자동으로 받아온다**(`--no-download`로 끌 수 있음).
- **분류기가 아직 없어도 실행된다** — 랜드마크는 그려지고 판정만 `model_not_loaded`로 나오므로,
  데이터·모델이 오기 전에도 카메라·MediaPipe 배선을 확인할 수 있다.

### ③ 분류기 학습 (로컬)

```bash
cd services/vision
pip install -r requirements.txt
python training/train_svm.py --dry-run     # 데이터 분포만 확인
python training/train_svm.py               # 학습 → models/ 에 번들 + 템플릿 생성
```

처음 한 번만 JSON 적재에 100초쯤 걸리고, 이후엔 캐시로 0.7초다. 주요 옵션은
[`MODEL_TRAINING.md`](MODEL_TRAINING.md) §6-0 참고.

**공개 데이터 기준** (세션 단위 5겹): 정답률 88.68% / Macro F1 0.879 / 치명 오분류 4건.
🔴 이 수치는 **KPI 근거가 아니다** — 촬영자 정보가 없어 인물 단위 분할이 불가능하다.

### ④ KPI 측정 (자체 촬영 데이터)

```bash
python scripts/record_dataset.py --subject-id ext01     # 촬영 (팀원 안내: document/촬영안내_KPI데이터.md)
python scripts/evaluate_kpi.py                          # KPI 5개 지표 계산
```

**현재 실측** (촬영자 1명 · 35시도): 정답률 100%, 오분류 0, 미판정 0, 치명 0.
🔴 표본이 작고 촬영자가 1명이라 **아직 KPI 달성으로 볼 수 없다**(95% 신뢰 상한 8.6%).
팀원 촬영분이 들어오면 같은 명령으로 다시 계산한다.

### 데이터 없이 파이프라인만 돌려보기

```bash
python scripts/make_dummy_dataset.py                          # 합성 데이터 생성
python training/train_svm.py --data training/_dummy_dataset   # 그걸로 한 바퀴
```

> 합성 좌표라 정확도 수치는 아무 의미가 없다. **형식과 배선 확인용**이다.

## 6. 남은 일

- [x] ~~실제 수신호 데이터 확보 후 학습 → `models/svm_classifier.joblib` 배치~~ (2026-09-21 완료)
- [x] ~~촬영 도구~~ → `scripts/record_dataset.py` (2026-09-22)
- [x] ~~손 방향 축 A/B 판단~~ → **보류 확정**. 기울여도 100%라 켤 근거 없음 (2026-09-22)
- [ ] **팀원 촬영분 확보** (2명) — KPI 측정의 유일한 경로. 회의 안건 1
- [ ] 팀원 데이터 확보 후 **τ 재결정** — 지금은 잠정값 0.75
- [ ] 게이트가 못 막는 25%(정지와 매우 닮은 자세) — negative 학습(안건 2 B) 전환 검토
- [ ] `perception/capture.py`의 picamera2 연동 (카메라 도착 후)
- [ ] `hand_landmarker.task` 모델 번들 다운로드 → `models/` (05_모델카드_v3 §1 URL)
- [ ] 실측 후 τ·N프레임 재검증, 05_모델카드_v3 §7-3 실측 표 채우기
- [ ] `/latest` 폴링 → WebSocket 전환 검토 (지연 KPI 여유 없을 때)
