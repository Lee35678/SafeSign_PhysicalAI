"""Colab에서 학습해 내려받은 경량 분류기(SVM) 번들을 로드한다.

학습은 로컬 GPU 한계로 Colab에서 수행하고(services/vision/training/train_svm_colab.ipynb),
거기서 나온 `svm_classifier.joblib` 하나만 `services/vision/models/`에 넣으면 이 서비스가 바로
사용한다. 모델 파일이 아직 없으면(=데이터 수집/학습 전) **서비스는 죽지 않고** "모델 없음" 상태로
동작한다 — 이 경우 classify는 항상 negative/reject를 돌려주므로 카메라·Actuation 배선 검증은
모델 없이도 계속할 수 있다.

번들 형식 (train_svm_colab.ipynb가 저장하는 dict):
    {
      "format_version": 1,
      "model": sklearn Pipeline(StandardScaler + SVC(probability=True)),
      "classes": ["정지", ..., "negative"],
      "tau": 0.75,                      # 05_모델카드_v3 §8-1 절차로 고른 값
      "n_frames": 3,                    # §3-6 판정 안정화 기본값
      "match_score_calibration": {"sim_min": 0.x, "sim_max": 0.y},
      "metadata": {...}                 # 학습 일시, 하이퍼파라미터, 데이터 규모 등
    }
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# services/vision/src/cognition/model_store.py -> services/vision
_SERVICE_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = Path(os.getenv("SVM_MODEL_PATH", _SERVICE_ROOT / "models" / "svm_classifier.joblib"))

_lock = threading.Lock()
_bundle: Optional[dict] = None
_loaded = False
_loaded_mtime: Optional[float] = None


def _normalize_bundle(obj: Any) -> dict:
    """joblib에 estimator만 덜렁 저장된 경우도 받아준다(번들 dict로 감싸기)."""
    if isinstance(obj, dict) and "model" in obj:
        return obj
    logger.warning("모델 파일이 번들 dict가 아님 — estimator 단독으로 간주하고 기본값을 채웁니다")
    return {"format_version": 0, "model": obj, "classes": list(getattr(obj, "classes_", []))}


def load_bundle(force: bool = False) -> Optional[dict]:
    """모델 번들을 로드(캐시). 파일이 없으면 None.

    파일이 교체되면(mtime 변경) 다음 호출에서 자동으로 다시 읽는다 — Colab에서 새로 받은 모델을
    덮어쓰고 서비스만 재시작하지 않아도 반영되게 하기 위함.
    """
    global _bundle, _loaded, _loaded_mtime

    with _lock:
        if not MODEL_PATH.exists():
            if not _loaded:
                logger.warning(
                    "분류기 모델이 없습니다: %s — negative/reject만 반환합니다. "
                    "Colab 학습 결과(svm_classifier.joblib)를 이 경로에 넣으세요.",
                    MODEL_PATH,
                )
                _loaded = True
            _bundle = None
            return None

        mtime = MODEL_PATH.stat().st_mtime
        if _bundle is not None and not force and mtime == _loaded_mtime:
            return _bundle

        import joblib  # 지연 import: 모델이 없는 환경에서도 서비스가 뜨도록

        _bundle = _normalize_bundle(joblib.load(MODEL_PATH))
        _loaded = True
        _loaded_mtime = mtime
        logger.info(
            "분류기 모델 로드 완료: %s (classes=%s, tau=%s, trained_at=%s)",
            MODEL_PATH,
            _bundle.get("classes"),
            _bundle.get("tau"),
            (_bundle.get("metadata") or {}).get("trained_at"),
        )
        return _bundle


def get_model():
    bundle = load_bundle()
    return None if bundle is None else bundle.get("model")


def get_classes() -> list[str]:
    bundle = load_bundle()
    return list(bundle.get("classes", [])) if bundle else []


def get_tau(default: float) -> float:
    """번들에 저장된 τ. 환경변수(CONFIDENCE_THRESHOLD)로 항상 덮어쓸 수 있도록 호출 측에서 우선순위를 정한다."""
    bundle = load_bundle()
    if bundle and bundle.get("tau") is not None:
        return float(bundle["tau"])
    return default


def get_match_score_calibration() -> Optional[dict]:
    bundle = load_bundle()
    return (bundle or {}).get("match_score_calibration")


def describe() -> dict:
    """/health 등에서 모델 적재 상태를 노출하기 위한 요약."""
    bundle = load_bundle()
    if bundle is None:
        return {"loaded": False, "path": str(MODEL_PATH)}
    return {
        "loaded": True,
        "path": str(MODEL_PATH),
        "classes": bundle.get("classes"),
        "tau": bundle.get("tau"),
        "metadata": bundle.get("metadata", {}),
    }
