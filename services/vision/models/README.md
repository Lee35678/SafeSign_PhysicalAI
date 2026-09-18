# models/ — 학습된 모델 파일을 넣는 곳

이 폴더는 **Colab에서 학습해 내려받은 파일을 그대로 떨어뜨리는 자리**다. 코드를 고칠 필요는 없다.

| 파일 | 어디서 나오나 | 없으면 어떻게 되나 |
| --- | --- | --- |
| `svm_classifier.joblib` | [`../training/train_svm_colab.ipynb`](../training/train_svm_colab.ipynb) 마지막 셀 | vision 서비스는 뜨지만 항상 `negative`/`is_reject=true` (reason=`model_not_loaded`) |
| `hand_landmarker.task` | MediaPipe 공식 모델 번들 (05_모델카드_v3 §1의 다운로드 URL) | 카메라 실물 연동 시 Perception이 기동 실패 — `MOCK_CAMERA=true`로는 무관 |

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
- 학습에 쓴 `normalize.py`와 서비스의 `normalize.py`가 **같은 커밋**이어야 한다. 번들 메타데이터의
  `repo_commit`으로 확인할 수 있다 (05_모델카드_v3 §3-5, MODEL_TRAINING.md §7).
