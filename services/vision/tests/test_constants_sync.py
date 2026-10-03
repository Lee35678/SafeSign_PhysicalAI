"""판정 파라미터·클래스가 운영(classify·smoothing), 학습(train_svm), KPI 평가(evaluate_kpi)에서 같은지.

세 곳이 서로를 import하지 않는 이유: train_svm이 classify·smoothing을 import하면 모듈 적재 때 현재 번들을
읽는다(sklearn이 필요하고, 새로 학습하는 중엔 옛 번들이다). 그래서 값을 따로 두고 여기서 대조한다.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from cognition import classify, smoothing  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ts = _load("vision_train_svm_sync", "training/train_svm.py")
ek = _load("vision_evaluate_kpi_sync", "scripts/evaluate_kpi.py")


def test_default_tau_is_the_same_for_serving_and_training():
    assert classify._DEFAULT_TAU == ts.DEFAULT_TAU


def test_n_frames_is_the_same_for_serving_training_and_kpi():
    assert smoothing.DEFAULT_N_FRAMES == ts.N_FRAMES == ek.N_CONSECUTIVE


def test_training_classes_are_the_serving_classes():
    assert list(ts.SIGN_CLASSES) == list(classify.SIGN_CLASSES)


def test_kpi_targets_agree_between_training_and_evaluation():
    """train_svm은 비율(0.92), evaluate_kpi는 백분율(92.0)로 적는다."""
    assert ts.KPI["macro_f1"] == ek.KPI["macro_f1"]
    for key in ("accuracy", "misclass", "reject"):
        assert ts.KPI[key] * 100 == pytest.approx(ek.KPI[key]), key
