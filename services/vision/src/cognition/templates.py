"""수신호 템플릿 DB 조회 + cosine similarity 기반 match_score 산출.

document/03_인터페이스계약서_v2.md §4 (`match_score`), 05_모델카드_v3 §2 참고.
분류 결과(predicted_class)와 일치율(match_score)은 **분리 설계**다 — "무엇으로 판정했는가"는 SVM이,
"얼마나 비슷한가"는 템플릿과의 코사인 유사도가 답한다.

템플릿 DB(`sign_templates` 테이블)는 services/data의 seed_templates.py가 학습 데이터로 **오프라인
시드**한다(수신호 등록 기능은 범위 제외 — 03_인터페이스계약서_v2 §6). 이 모듈은 읽기 전용이다.
DB나 템플릿이 아직 없으면 match_score=0으로 안전하게 동작한다.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DB_PATH", "/data/db/signdb.sqlite3"))

_lock = threading.Lock()
_templates: dict[str, np.ndarray] = {}
_loaded_mtime: Optional[float] = None
_warned_missing = False


def _load_templates() -> dict[str, np.ndarray]:
    """sign_templates 테이블을 메모리로. 파일이 갱신되면 자동 재적재."""
    global _templates, _loaded_mtime, _warned_missing

    with _lock:
        if not DB_PATH.exists():
            if not _warned_missing:
                logger.warning(
                    "템플릿 DB가 없습니다: %s — match_score는 0으로 반환됩니다. "
                    "services/data의 init_db.py + seed_templates.py로 시드하세요.",
                    DB_PATH,
                )
                _warned_missing = True
            _templates = {}
            return _templates

        mtime = DB_PATH.stat().st_mtime
        if _templates and mtime == _loaded_mtime:
            return _templates

        loaded: dict[str, np.ndarray] = {}
        try:
            # 읽기 전용으로 연다 (vision은 템플릿을 쓰지 않는다)
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            try:
                rows = conn.execute("SELECT sign_name, vector FROM sign_templates").fetchall()
            finally:
                conn.close()
            for sign_name, vector_json in rows:
                vec = np.asarray(json.loads(vector_json), dtype=np.float64)
                loaded[sign_name] = vec
        except (sqlite3.Error, json.JSONDecodeError, ValueError) as exc:
            logger.warning("템플릿 DB 조회 실패(%s) — match_score는 0으로 반환됩니다", exc)
            loaded = {}

        _templates = loaded
        _loaded_mtime = mtime
        return _templates


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)


def similarity_to_score(similarity: float, calibration: Optional[dict] = None) -> int:
    """코사인 유사도 -> 0~100 점수.

    05_모델카드_v3 §2는 "percentile 매핑"을 요구한다. 실측 데이터가 있어야 분포를 알 수 있으므로,
    학습 노트북이 검증셋에서 뽑은 (sim_min, sim_max) = (같은 클래스 유사도의 5·95 퍼센타일)을
    번들에 실어 보내고, 여기서는 그 구간을 0~100으로 선형 매핑한다.
    보정값이 없으면(모델 없음/구버전 번들) 유사도를 그대로 0~100으로 매핑한다.
    """
    if calibration:
        lo = float(calibration.get("sim_min", 0.0))
        hi = float(calibration.get("sim_max", 1.0))
        if hi - lo > 1e-9:
            similarity = (similarity - lo) / (hi - lo)
    return int(round(float(np.clip(similarity, 0.0, 1.0)) * 100))


def match_score(feature: np.ndarray, sign_name: str, calibration: Optional[dict] = None) -> int:
    """특징벡터와 해당 클래스 템플릿의 유사도를 0~100으로. 템플릿이 없으면 0."""
    template = _load_templates().get(sign_name)
    if template is None or template.shape != feature.shape:
        return 0
    return similarity_to_score(cosine_similarity(feature, template), calibration)


def available_signs() -> list[str]:
    return sorted(_load_templates().keys())
