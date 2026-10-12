"""학습된 경량 분류기(SVM) 번들을 로드한다.

모델 파일(`svm_classifier.joblib`)은 저장소에 포함하지 않고 제품과 별도로 제공한다.
`services/vision/models/`에 두면 된다. 학습 파이프라인은 개발 브랜치(dev)의 `services/vision/training/`에 있다.

모델 파일이 아직 없으면 **서비스는 죽지 않고** "모델 없음" 상태로 동작한다 — 이 경우 classify는
항상 negative/reject를 돌려주므로 카메라·Actuation 배선 검증은 모델 없이도 계속할 수 있다.

번들 형식:
    {
      "format_version": 2,
      "model": sklearn Pipeline(StandardScaler + CalibratedClassifierCV(SVC)),
      "classes": ["정지", ..., "주의"],   # 7종. negative는 학습 클래스가 아니다 (안건 2 A)
      "tau": 0.75,                      # 05_모델카드 §8-1 절차로 고른 값
      "n_frames": 3,                    # §3-6 판정 안정화 기본값
      "match_score_calibration": {"sim_min": 0.x, "sim_max": 0.y},
      "metadata": {
        "feature_mode": "landmark63" | "landmark63+orient6",   # 추론이 반드시 따라야 하는 값
        "sklearn_version": "...", "trained_at": "...", ...
      }
    }

format_version 2에서 바뀐 것 (2026-09-21 회의 결정 반영):
  - classes가 8종 -> **7종**. negative는 학습하지 않고 τ 미달 시 판정 결과로만 쓴다 (안건 2 A).
  - metadata에 **feature_mode** 추가. 손 방향 축 도입(안건 3 A)으로 특징 차원이 63/69 두 가지가
    되었으므로, 학습 때 쓴 모드를 번들이 들고 다녀야 추론이 어긋나지 않는다.
"""
from __future__ import annotations

import hashlib
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
# 읽기에 실패한 (경로, mtime). 같은 파일이면 다시 읽지 않는다 — predict가 프레임마다 load_bundle을
# 여러 번 부르므로, 기억하지 않으면 손상 번들 하나로 초당 수백 번 joblib.load·traceback이 반복된다.
_failed_key: Optional[tuple] = None
# 적재한 번들 파일의 sha256 — Pi에서 도는 번들이 KPI를 잰 번들과 같은지 /health·KPI 리포트로 대조한다.
_loaded_sha256: Optional[str] = None


def _normalize_bundle(obj: Any) -> dict:
    """joblib에 estimator만 덜렁 저장된 경우도 받아준다(번들 dict로 감싸기)."""
    if isinstance(obj, dict) and "model" in obj:
        return obj
    logger.warning("모델 파일이 번들 dict가 아님 — estimator 단독으로 간주하고 기본값을 채웁니다")
    return {"format_version": 0, "model": obj, "classes": list(getattr(obj, "classes_", []))}


def _warn_if_sklearn_mismatch(bundle: dict) -> None:
    """학습(Colab)과 추론(여기)의 scikit-learn 버전이 어긋나면 경고한다.

    joblib 직렬화 모델은 버전이 크게 다르면 조용히 이상하게 동작하거나 로드가 깨진다.
    번들 metadata에 기록된 학습 시점 버전과 현재 설치 버전의 major.minor를 비교한다.
    """
    trained_with = (bundle.get("metadata") or {}).get("sklearn_version")
    if not trained_with:
        return
    try:
        import sklearn
    except ImportError:
        return
    if trained_with.split(".")[:2] != sklearn.__version__.split(".")[:2]:
        logger.warning(
            "scikit-learn 버전 불일치: 학습 %s vs 현재 %s — 예측이 어긋나거나 로드가 깨질 수 있습니다. "
            "requirements.txt의 scikit-learn 범위를 학습 환경에 맞추거나, 같은 환경에서 재학습하세요.",
            trained_with,
            sklearn.__version__,
        )


def _file_sha256(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def load_bundle(force: bool = False) -> Optional[dict]:
    """모델 번들을 로드(캐시). 파일이 없으면 None.

    파일이 교체되면(mtime 변경) 다음 호출에서 자동으로 다시 읽는다 — Colab에서 새로 받은 모델을
    덮어쓰고 서비스만 재시작하지 않아도 반영되게 하기 위함.
    """
    global _bundle, _loaded, _loaded_mtime, _failed_key, _loaded_sha256

    with _lock:
        if not MODEL_PATH.exists():
            if not _loaded:
                logger.warning(
                    "분류기 모델이 없습니다: %s — negative/reject만 반환합니다. "
                    "모델 파일은 제품과 별도로 제공된다 — 받은 svm_classifier.joblib을 이 경로에 두세요(README §4.1 ④).",
                    MODEL_PATH,
                )
                _loaded = True
            _bundle = None
            return None

        mtime = MODEL_PATH.stat().st_mtime
        if _bundle is not None and not force and mtime == _loaded_mtime:
            return _bundle
        if _bundle is None and not force and (MODEL_PATH, mtime) == _failed_key:
            return None  # 이미 실패한 파일 — 교체(mtime 변경)될 때까지 다시 읽지 않는다

        # 지연 import + 실패 흡수: 모델 파일이 있어도 joblib 미설치·번들 손상으로 서비스가
        # 죽으면 안 된다. 이 경우 "모델 없음"으로 떨어뜨려 classify가 미판정을 돌려주게 한다.
        try:
            import joblib

            _bundle = _normalize_bundle(joblib.load(MODEL_PATH))
        except ImportError:
            logger.error(
                "joblib이 설치되어 있지 않아 모델(%s)을 읽을 수 없습니다 — negative/reject만 "
                "반환합니다. `pip install -r requirements.txt`",
                MODEL_PATH,
            )
            _bundle, _loaded, _loaded_mtime, _failed_key = None, True, None, (MODEL_PATH, mtime)
            return None
        except Exception:
            logger.exception(
                "모델 번들을 읽지 못했습니다: %s — negative/reject만 반환합니다. "
                "제공받은 모델 파일로 다시 교체하세요(README §4.1 ④).",
                MODEL_PATH,
            )
            _bundle, _loaded, _loaded_mtime, _failed_key = None, True, None, (MODEL_PATH, mtime)
            return None

        _loaded = True
        _loaded_mtime = mtime
        _failed_key = None
        _loaded_sha256 = _file_sha256(MODEL_PATH)
        _warn_if_sklearn_mismatch(_bundle)
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


_gate_cache: Optional[dict] = None
_gate_cache_key: Optional[int] = None


def get_open_set_gate() -> Optional[dict]:
    """1단계 소속 게이트 파라미터. 없으면(구버전 번들/게이트 끔) None.

    반환: {"thresholds": {클래스: float}, "centroids": {클래스: np.ndarray}, ...}
    번들에는 centroid가 list로 들어 있으므로 여기서 한 번만 ndarray로 바꿔 캐시한다
    (프레임마다 변환하면 30fps에서 낭비가 크다).
    """
    global _gate_cache, _gate_cache_key

    bundle = load_bundle()
    raw = (bundle or {}).get("open_set_gate")
    if not raw:
        return None
    if _gate_cache is not None and _gate_cache_key == id(bundle):
        return _gate_cache

    import numpy as np

    _gate_cache = {
        "kind": raw.get("kind", "centroid_cosine"),
        "percentile": raw.get("percentile"),
        "thresholds": {str(k): float(v) for k, v in (raw.get("thresholds") or {}).items()},
        "centroids": {
            str(k): np.asarray(v, dtype=float) for k, v in (raw.get("centroids") or {}).items()
        },
    }
    _gate_cache_key = id(bundle)
    return _gate_cache


def get_feature_mode(default: str) -> str:
    """학습 때 쓴 특징 모드. 추론은 반드시 이 값을 따라야 한다.

    번들에 없으면(format_version 1 이하) 방향 축 도입 이전이므로 63차원으로 간주한다.
    """
    bundle = load_bundle()
    if not bundle:
        return default
    return str((bundle.get("metadata") or {}).get("feature_mode") or default)


def describe() -> dict:
    """/health 등에서 모델 적재 상태를 노출하기 위한 요약."""
    bundle = load_bundle()
    if bundle is None:
        return {"loaded": False, "path": str(MODEL_PATH)}
    return {
        "loaded": True,
        "path": str(MODEL_PATH),
        "sha256": _loaded_sha256,
        "classes": bundle.get("classes"),
        "tau": bundle.get("tau"),
        "feature_mode": (bundle.get("metadata") or {}).get("feature_mode"),
        "open_set_gate": (
            None if not bundle.get("open_set_gate")
            else {
                "kind": bundle["open_set_gate"].get("kind"),
                "percentile": bundle["open_set_gate"].get("percentile"),
                "thresholds": bundle["open_set_gate"].get("thresholds"),
            }
        ),
        "metadata": bundle.get("metadata", {}),
    }
