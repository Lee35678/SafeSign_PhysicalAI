"""model_store.swapped_bundle — 비교 도구(evaluate_kpi·analyze_log)가 모델을 바꿔 끼운 뒤 원래 모델로 되돌리는지.

실행: python -m pytest tests/test_model_store_swap.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cognition import model_store  # noqa: E402


def test_swapped_bundle_restores_model_path(tmp_path):
    original = model_store.MODEL_PATH
    missing = tmp_path / "none.joblib"

    with model_store.swapped_bundle(missing) as bundle:
        assert model_store.MODEL_PATH == missing
        assert bundle is None  # 파일이 없으면 None

    assert model_store.MODEL_PATH == original


def test_swapped_bundle_restores_even_on_error(tmp_path):
    original = model_store.MODEL_PATH

    with pytest.raises(RuntimeError):
        with model_store.swapped_bundle(tmp_path / "none.joblib"):
            raise RuntimeError("비교 중 실패")

    assert model_store.MODEL_PATH == original


def test_swapped_bundle_none_keeps_current_path():
    original = model_store.MODEL_PATH

    with model_store.swapped_bundle(None):
        assert model_store.MODEL_PATH == original

    assert model_store.MODEL_PATH == original
