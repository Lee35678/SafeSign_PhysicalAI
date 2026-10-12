# models/ — vision 모델 파일

이 폴더에는 파일 2개가 들어간다.

| 파일 | 내용 | 받는 곳 | 없으면 |
| --- | --- | --- | --- |
| `hand_landmarker.task` | MediaPipe Hand Landmarker 모델. 영상에서 손 관절 21개를 찾는다 (Apache License 2.0) | git에 포함 | 실물 카메라로 실행할 때 캡처가 멈추고 `/health`의 `camera.state`가 `error`가 된다 |
| `svm_classifier.joblib` | 수신호 7종 판정 모델 번들 | git에 없음. 제품과 별도로 제공 | 서비스는 뜨지만 모든 판정이 미판정(`reason: model_not_loaded`) |

## svm_classifier.joblib 배치

제공받은 파일을 RPi5의 `services/vision/models/`에 복사한다. 파일이 있는 PC에서:

```bash
scp svm_classifier.joblib <사용자>@<RPi5 주소>:~/git/SafeSign_PhysicalAI/services/vision/models/
```

루트 [README](../../../README.md) §4.1 ④와 같은 절차다.

## 교체

같은 이름으로 덮어쓰면 된다. 서비스가 파일 수정 시각을 보고 다음 판정부터 새 파일을 읽으므로
재시작하지 않아도 된다. 다만 번들의 N프레임 수는 서비스 시작 때 한 번만 읽으므로, 이 값이 바뀐 번들이면
서비스를 다시 시작한다.

교체 후 확인:

```bash
curl http://localhost:8001/health
# "model": {"loaded": true, "path": ..., "sha256": ..., "classes": [...], "tau": ..., "metadata": {...}}
```

- `sha256`으로 제공받은 파일과 같은 파일이 적재됐는지 대조할 수 있다.
- 파일을 다른 곳에 두려면 `SVM_MODEL_PATH` 환경변수로 경로를 지정한다.

## 주의

- `svm_classifier.joblib` 하나에 모델과 함께 τ(판정 임계값), N프레임 수, 일치율 환산값, 소속 게이트 값,
  메타데이터(`feature_mode`, `sklearn_version` 등)가 들어 있다. 항상 파일 하나를 통째로 교체한다.
- 번들의 `feature_mode`에 따라 특징값을 만든다. 서비스 코드(`src/cognition/normalize.py`)는 번들을 만든
  코드와 같은 버전이어야 한다.
- 번들을 만든 scikit-learn과 설치된 scikit-learn의 major.minor가 다르면 기동 로그에 경고가 나온다.
  예측이 어긋나거나 파일을 못 읽을 수 있으므로 `requirements.txt` 범위대로 설치한다.
- `hand_landmarker.task`는 교체할 일이 없다. 다른 경로의 파일을 쓰려면 `HAND_LANDMARKER_MODEL` 환경변수로 지정한다.
