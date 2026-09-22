# models/ — 학습된 모델 파일이 놓이는 곳

**로컬 학습이 기본이라(2026-09-21) 대부분 직접 만들면 된다.**

```bash
cd services/vision
pip install -r requirements.txt
python training/train_svm.py      # svm_classifier.joblib + sign_templates.json 자동 생성
```

| 파일 | 어디서 나오나 | 없으면 어떻게 되나 |
| --- | --- | --- |
| `svm_classifier.joblib` | [`../training/train_svm.py`](../training/train_svm.py) (또는 Colab 노트북) | vision 서비스는 뜨지만 항상 `negative`/`is_reject=true` (reason=`model_not_loaded`) |
| `sign_templates.json` | 같은 스크립트 | 데이터 담당의 `seed_templates.py` 입력용. 없어도 `match_score`는 번들 centroid로 폴백된다 |
| `hand_landmarker.task` | MediaPipe 공식 모델 번들 (05_모델카드_v3 §1의 다운로드 URL) | 카메라 실물 연동 시 Perception이 기동 실패 — `MOCK_CAMERA=true`로는 무관 |
| `cmp_*.joblib` | `train_svm.py --out models/cmp_....joblib` | 없어도 무방. 있으면 `evaluate_kpi.py`·`analyze_log.py`가 자동으로 함께 평가해 비교표를 낸다 |

## 넣은 뒤 확인

```bash
docker compose up --build vision
curl http://localhost:8001/health
# -> "model": {"loaded": true, "classes": [...], "tau": 0.xx, "metadata": {...}}
```

경로를 바꾸고 싶으면 `SVM_MODEL_PATH` 환경변수로 덮어쓸 수 있다.
파일을 교체하면 **서비스 재시작 없이도** 다음 판정부터 새 모델이 적용된다(mtime 감지).

## 주의

- `svm_classifier.joblib`에는 모델뿐 아니라 **τ(임계값)·match_score 보정값·학습 메타데이터**가 함께
  들어 있다. 모델만 바꾸고 τ를 따로 관리하면 둘이 어긋나므로, 항상 번들 파일 하나로 교체한다.
- 학습에 쓴 `normalize.py`와 서비스의 `normalize.py`가 **같은 커밋**이어야 한다. 로컬 학습은 같은
  저장소의 `src/`를 직접 import하므로 자동으로 맞는다 (05_모델카드_v3 §3-5, MODEL_TRAINING.md §7).
- 번들 메타데이터의 **`feature_mode`** 가 63차원(`landmark63`)인지 69차원(`landmark63+orient6`)인지
  알려준다. `classify.py`가 이 값을 따라 특징을 만들므로 손대지 말 것 (MODEL_TRAINING.md §2-1).
