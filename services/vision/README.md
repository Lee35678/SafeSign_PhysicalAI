# vision — 카메라 수신호 판정 (RPi5)

Camera Module 3로 학습자의 손을 찍어, 지금 하고 있는 수신호가 7종 중 무엇인지 판정하는 서비스다.
RPi5에서 네이티브로 실행하며 포트 8001을 쓴다. web은 이 서비스의 `/latest`를 읽어 판정을 받고,
`/stream`을 중계해 학습 화면에 카메라 영상을 띄운다.

판정하는 수신호 7종: 정지, 서행, 좌회전_유도, 우회전_유도, 확인_완료, 후진, 주의.
7종이 아니거나 확신이 부족하면 `negative`(미판정)로 나온다.

## 1. 판정 원리

1. MediaPipe Hand Landmarker가 영상에서 손 관절 21개의 좌표를 뽑는다.
2. 좌표를 정규화(좌우 손·원점·크기·회전 맞춤)한 뒤 관절 각도·거리 23개 값으로 바꾼다.
3. SVM이 7종별 확률을 낸다. 7종 어디에도 속하지 않는 손모양은 소속 게이트가 먼저 걸러 낸다.
4. 가장 높은 확률이 τ(기본 0.75)보다 낮으면 미판정이다.
5. 같은 수신호가 N프레임(기본 3) 연속으로 나와야 판정을 확정한다.

## 2. 구성 파일

```
src/
├── app.py                  HTTP 서버 (아래 §5 API)
├── perception/
│   ├── capture.py          카메라 → MediaPipe → 손 관절 좌표
│   ├── camera_source.py    CSI(picamera2) · USB(OpenCV) 카메라 열기
│   └── preview.py          라이브 영상(MJPEG) 인코딩
└── cognition/
    ├── normalize.py        좌표 정규화 → 특징값
    ├── classify.py         SVM 판정 + 소속 게이트 + τ
    ├── smoothing.py        N프레임 연속 확인
    ├── model_store.py      판정 모델 파일 읽기
    └── templates.py        일치율(match_score) 계산
models/                     모델 파일 자리 → models/README.md
scripts/
├── run_rpi5.sh             RPi5에서 서비스 실행
└── webcam_check.py         카메라·판정을 화면으로 점검
requirements.txt
```

학습 파이프라인과 평가 도구는 개발 브랜치 `dev`에 있다.

## 3. 설치 (RPi5, 최초 1회)

전체 절차는 루트 [README](../../README.md) §4.1 ③·④에 있다. vision에 해당하는 부분만 적는다.

```bash
sudo apt update
sudo apt install -y python3-picamera2 fonts-nanum   # picamera2는 pip가 아니라 apt로 설치
rpicam-hello --list-cameras                          # imx708 (Camera Module 3)이 보여야 한다

cd ~/git/SafeSign_PhysicalAI/services/vision
python3 -m venv --system-site-packages .venv         # 이 옵션이 있어야 venv 안에서 picamera2가 보인다
source .venv/bin/activate
pip install -r requirements.txt
```

- `fonts-nanum`은 `webcam_check.py` 화면에 한글 수신호 이름을 표시할 때 쓴다.
- 판정 모델 `models/svm_classifier.joblib`은 git에 없고 제품과 별도로 제공한다.
  받은 파일을 `services/vision/models/`에 둔다. 자세한 내용은 [models/README.md](models/README.md).
- scikit-learn은 모델을 만든 버전과 major.minor가 같아야 한다(`requirements.txt`는 1.9 이상 2.0 미만).
  다르면 기동 로그에 버전 불일치 경고가 나온다.

## 4. 실행

```bash
cd ~/git/SafeSign_PhysicalAI/services/vision
bash scripts/run_rpi5.sh                 # 0.0.0.0:8001
PORT=8002 bash scripts/run_rpi5.sh       # 포트를 바꿀 때
```

`run_rpi5.sh`는 `.venv`가 있으면 켜고, `MOCK_CAMERA=false`, `CAMERA_SOURCE=csi`(미지정 시)로
uvicorn을 띄운다. 시작 전에 두 가지를 검사해 경고만 띄우고 실행은 계속한다.

- `models/svm_classifier.joblib`이 없으면: 모든 판정이 `model_not_loaded`로 나온다.
- `picamera2`를 불러올 수 없으면: apt 설치와 `--system-site-packages` venv를 확인하라고 안내한다.

환경변수는 앞에 붙여 덮어쓴다. 예: `CAPTURE_SIZE=1920x1080 CAPTURE_FPS=60 bash scripts/run_rpi5.sh`

정상 기동 확인:

```bash
curl http://localhost:8001/health    # camera.state가 running, capture_fps·result_fps가 0보다 커야 한다
curl http://localhost:8001/latest    # 손을 비추면 predicted_class가 바뀐다
```

web을 다른 기기에서 띄우면 그쪽 `VISION_URL`을 `http://<RPi5 주소>:8001`로 준다.

## 5. HTTP API

| 엔드포인트 | 내용 |
| --- | --- |
| `GET /health` | 서비스 상태. `model`(적재 여부·경로·sha256·클래스·τ·메타데이터), `camera`(state·capture_fps·result_fps·error), `preview`(viewers·encoder·fps·width), `tau`, `n_frames`, `templates` |
| `GET /latest` | 최신 판정 결과. web이 주기적으로 읽는다 |
| `POST /reset` | N프레임 누적과 직전 판정을 초기화. web이 다음 수신호로 넘어갈 때·확인 버튼 때 호출 |
| `GET /stream` | 카메라 라이브 영상(MJPEG). 보는 화면이 있을 때만 인코딩한다. JPEG 인코더가 없으면 503 |
| `GET /snapshot.jpg` | 최신 프레임 한 장(점검용). 프레임이 없으면 503 |
| `POST /predict` | 손 관절 좌표 한 프레임을 직접 넣어 판정만 해 본다(카메라 미사용, 점검용) |

이 서비스는 카메라가 직결돼 있어 스스로 캡처·판정을 계속 돌리며 최신 결과를 만들어 둔다.
그래서 web은 `/latest`만 읽으면 된다. 카메라가 없거나 열리지 않으면 `/stream`에는
"NO CAMERA" 안내 화면이 나온다.

`/latest` 응답 필드:

| 필드 | 뜻 |
| --- | --- |
| `predicted_class` | 판정한 수신호. 미판정이면 `negative` |
| `confidence` | 판정 클래스의 확률(0~1) |
| `is_reject` | `true`면 미판정 |
| `reason` | 미판정 이유 (아래 표) |
| `class_probabilities` | 7종별 확률. web은 목표 수신호의 확률 × 100을 학습자 화면의 일치율로 쓴다 |
| `match_score` | 대표 손모양과의 유사도(0~100). 참고용 |
| `latency_ms` | 캡처부터 판정까지 걸린 시간(ms) |
| `consecutive` | 지금까지 연속으로 같은 판정이 나온 프레임 수 |

| `reason` | 뜻 |
| --- | --- |
| `no_hand` | 손이 보이지 않음 |
| `normalize_failed` | 관절은 잡혔지만 정규화 불가 |
| `model_not_loaded` | 판정 모델 파일이 없음 |
| `inference_error` | 모델 추론 실패(모델과 특징 형식 불일치 등) |
| `out_of_distribution` | 7종 어디에도 속하지 않는 손모양 |
| `below_tau` | 확률이 τ보다 낮음 |
| `awaiting_consecutive_frames` | τ는 넘었지만 아직 N프레임 연속이 안 됨 |

## 6. 환경변수

`run_rpi5.sh`가 설정하는 값 외에는 모두 기본값으로 운영한다.

| 이름 | 기본 | 뜻 |
| --- | --- | --- |
| `MOCK_CAMERA` | `true` | `false`여야 실물 카메라를 쓴다. `run_rpi5.sh`가 `false`로 설정 |
| `CAMERA_SOURCE` | `csi` | `csi` · `usb` · `auto`(CSI 먼저, 안 되면 USB) |
| `CAMERA_INDEX` | `0` | 카메라 번호 |
| `CAPTURE_SIZE` | `1280x720` | 캡처 해상도 |
| `CAPTURE_FPS` | `30` | CSI 목표 프레임률 |
| `CAMERA_MIRROR` | `true` | 좌우 반전. 판정 결과에는 영향 없음 |
| `CAMERA_SWAP_RB` | `false` | 빨강·파랑이 뒤집혀 보일 때 `true` |
| `CAMERA_AUTOFOCUS` | `true` | Camera Module 3 연속 자동초점. `false`면 끈다 |
| `CONFIDENCE_THRESHOLD` | (없음) | τ를 직접 지정. 없으면 모델 파일의 값, 그것도 없으면 0.75 |
| `N_FRAMES` | (없음) | 연속 확인 프레임 수. 없으면 모델 파일의 값, 그것도 없으면 3 |
| `OPEN_SET_GATE` | (없음) | `off`·`false`·`0`·`no`면 소속 게이트를 끈다. 정상 자세가 계속 `out_of_distribution`으로 막힐 때만 |
| `SVM_MODEL_PATH` | `models/svm_classifier.joblib` | 판정 모델 파일 경로 |
| `HAND_LANDMARKER_MODEL` | `models/hand_landmarker.task` | MediaPipe 모델 파일 경로(실행 폴더 기준) |
| `DB_PATH` | `/data/db/signdb.sqlite3` | 일치율 템플릿 DB. 기본 운영에서는 쓰지 않는다(아래 참고) |
| `STREAM_FPS` | `15` | 라이브 영상 최대 프레임률 |
| `STREAM_WIDTH` | `640` | 라이브 영상 최대 가로 픽셀 |
| `STREAM_QUALITY` | `70` | 라이브 영상 JPEG 품질(1~100) |
| `HOST` / `PORT` | `0.0.0.0` / `8001` | `run_rpi5.sh`의 수신 주소·포트 |

- `CAPTURE_SIZE`·`CAPTURE_FPS`를 1920x1080·60으로 올릴 수 있지만, 같은 RPi5에서 MediaPipe까지 돌리기에는
  무겁다. MediaPipe는 내부에서 영상을 줄여 쓰므로 해상도를 올려도 정확도 이득이 적다.
- `DB_PATH` 파일이 없으면 모델 파일에 든 클래스별 대표값으로 일치율을 계산한다. 판정에는 영향이 없다.

## 7. 카메라 점검 — webcam_check.py

서비스를 띄우기 전에 카메라와 판정을 눈으로 확인하는 도구다. 판정 경로는 서비스와 같은 코드
(`src/cognition/`)를 쓰고 카메라에서 영상을 받는 부분만 다르므로, 여기서 잘 맞으면 서비스에서도 같은 판정이 나온다.

```bash
cd ~/git/SafeSign_PhysicalAI/services/vision
source .venv/bin/activate
python scripts/webcam_check.py --list-cameras              # 잡히는 CSI·USB 카메라 목록
python scripts/webcam_check.py --source csi                # 모니터 연결 시 — 창에 판정 표시
python scripts/webcam_check.py --source csi --no-window    # SSH로만 접속했을 때 — 콘솔에 판정 출력
```

- 기본 `--source`는 `usb`이므로 Camera Module 3를 볼 때는 `--source csi`를 붙인다.
- 화면이 없으면(`DISPLAY` 없음) 자동으로 `--no-window`로 바뀐다.
- 창에는 판정 수신호, confidence, match_score, N프레임 진행, 지연(ms), FPS가 표시된다.
  `q`·`ESC` 종료, `r` 누적 초기화.
- 모델 파일이 없어도 실행된다. 관절은 그려지고 판정만 `model_not_loaded`로 나오므로 카메라와 MediaPipe만 따로 확인할 수 있다.
- 그 밖의 옵션: `--camera N`(카메라 번호), `--size`, `--fps`, `--swap-rb`(색 뒤집힘), `--no-autofocus`,
  `--no-mirror`, `--max-frames N`(N프레임 후 종료), `--log`(진단 로그를 `logs/`에 JSONL로 기록).
- `models/hand_landmarker.task`가 없으면 MediaPipe 공식 주소에서 자동으로 받는다(`--no-download`로 끔).

## 8. 문제 해결

카메라가 열리지 않아도 서비스는 꺼지지 않는다. "손 미검출"로 계속 응답하고, 원인을 `/health`의
`camera.state`(`error`)와 `camera.error`에 남긴다. 아래 표와 루트 [README](../../README.md) §4.6도 함께 본다.

| 증상 | 원인 · 조치 |
| --- | --- |
| `camera.state`가 `mock` | `MOCK_CAMERA=false` 없이 uvicorn을 직접 띄움 → `bash scripts/run_rpi5.sh`로 실행 |
| `camera.error`에 `picamera2를 불러올 수 없습니다` | apt 설치가 안 됐거나 venv를 `--system-site-packages` 없이 만듦 → §3대로 venv 다시 생성 |
| `numpy.dtype size changed` 류 오류 | apt picamera2(시스템 numpy)와 venv의 pip numpy가 충돌 → `pip install --upgrade simplejpeg` 후 재시도 |
| `rpicam-hello`에 카메라가 안 보임 | 케이블 방향·커넥터 확인. RPi5는 22핀 미니 커넥터라 전용 케이블이 필요 |
| 판정이 계속 `model_not_loaded` | `models/svm_classifier.joblib` 없음 → [models/README.md](models/README.md) |
| `camera.state`가 `error`, `캡처 루프 중단` | MediaPipe 모델(`models/hand_landmarker.task`)을 못 읽었는지 기동 로그 확인 |
| `result_fps`가 `capture_fps`보다 한참 낮음 | MediaPipe가 밀리는 중. 밀린 프레임은 자동으로 버리므로 정상이지만, 판정이 늦으면 `CAPTURE_SIZE=960x540`으로 낮춘다 |
| 화면 색이 뒤집혀 보임 | `CAMERA_SWAP_RB=true` (점검 도구는 `--swap-rb`) |
| 초점이 계속 움직여 거슬림 | `CAMERA_AUTOFOCUS=false` (점검 도구는 `--no-autofocus`) |
| 정상 자세가 계속 `out_of_distribution` | 손을 기울이면 게이트가 막는 경우가 있다. 손을 세워 다시 해 보고, 계속되면 `OPEN_SET_GATE=off` |
