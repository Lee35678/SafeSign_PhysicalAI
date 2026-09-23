# -*- coding: utf-8 -*-
"""Evidential 모델 번들을 읽어 캐시한다 (vision_research 브랜치 — 딥러닝 전용).

이 브랜치의 설계
  분류기 바깥에 거리 기반 소속 게이트를 덧대지 않는다. "7종 밖"을 모델이 직접 말한다.
  그래서 번들에 게이트도 τ도 없다 — 신경망이 클래스 확률과 **불확실성 u** 를 함께 낸다.
  (SVM + 게이트 + τ 구성은 feature/vision 브랜치에 있다.)

어떤 번들을 읽는가
  1. 환경변수 EDL_MODEL_PATH
  2. models/handformer_edl.pt   training/train_handformer.py --final 이 만든다
  구조·앙상블·증거 활성 함수는 번들 안에 적혀 있고, cognition.evidential 이 알아서 되살린다.

모델이 없거나 깨져 있으면 **조용히 None 을 돌려준다.** 호출 측이 model_not_loaded 로
안전하게 빠지도록 하기 위해서다 — 여기서 예외를 던지면 서비스가 통째로 죽는다.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
_CANDIDATES = (SERVICE_ROOT / "models" / "handformer_edl.pt",)

_predictor: Any = None
_raw_meta: dict = {}
_key_loaded: Optional[tuple] = None
_failed: set[tuple] = set()


def model_path() -> Path:
    env = os.getenv("EDL_MODEL_PATH")
    if env:
        return Path(env)
    for p in _CANDIDATES:
        if p.exists():
            return p
    return _CANDIDATES[-1]


def _key(path: Path) -> Optional[tuple]:
    try:
        st = path.stat()
        return (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def get_predictor():
    """추론기(EvidentialPredictor). 파일이 바뀌면 다시 읽는다. 없으면 None."""
    global _predictor, _raw_meta, _key_loaded
    p = model_path()
    k = _key(p)
    if k is None:
        return None
    if k == _key_loaded and _predictor is not None:
        return _predictor
    if k in _failed:
        return None
    try:
        import torch

        from cognition.evidential import EvidentialPredictor
        raw = torch.load(p, weights_only=False, map_location="cpu")
        pred = EvidentialPredictor.from_bundle(raw, "cpu")
    except Exception:
        logger.exception("Evidential 번들을 읽지 못했습니다: %s", p)
        _failed.add(k)
        return None
    _predictor = pred
    _raw_meta = {k2: v for k2, v in raw.items()
                 if k2 not in ("members", "state_dict", "mu", "sd", "member_info")}
    _key_loaded = k
    logger.info("Evidential 번들 로드: %s (%s, 멤버 %d개)", p, pred.arch, len(pred.members))
    return pred


def get_classes() -> list[str]:
    pred = get_predictor()
    return list(pred.classes) if pred else []


def get_feature_mode(default: str = "joint23") -> str:
    return str(_raw_meta.get("feature_mode", default)) if get_predictor() else default


def get_match_score_calibration() -> Optional[dict]:
    """일치율 표시용 보정값. 없으면 templates 가 기본 범위를 쓴다."""
    return _raw_meta.get("match_score_calibration") if get_predictor() else None


def describe() -> dict:
    """진단용 요약 (webcam_check, /health 등에서 쓴다)."""
    pred = get_predictor()
    if not pred:
        return {"loaded": False, "path": str(model_path())}
    return {
        "loaded": True,
        "path": str(model_path()),
        "kind": "evidential",
        "arch": pred.arch,
        "members": len(pred.members),
        "activation": pred.activation,
        "classes": list(pred.classes),
        "feature_mode": get_feature_mode(),
        "n_train": _raw_meta.get("n_train"),
    }


def load_bundle(path: Path | None = None) -> Optional[dict]:
    """예전 호출(app.py 기동 로그, smoothing 의 n_frames)을 위한 호환 함수.

    번들의 메타데이터(가중치 제외)를 dict 로 돌려준다. 모델이 없으면 None.
    """
    if path is not None:
        os.environ["EDL_MODEL_PATH"] = str(path)
    return dict(_raw_meta) if get_predictor() else None
