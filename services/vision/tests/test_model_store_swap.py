"""model_store.swapped_bundle — 비교 도구(evaluate_kpi·analyze_log)가 모델을 바꿔 끼운 뒤 원래 모델로 되돌리는지.

실행: python -m pytest tests/test_model_store_swap.py -q
"""
import sys
import types
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


def test_swapped_bundle_reloads_original_bundle(tmp_path, monkeypatch):
    """경로만 되돌리고 캐시를 안 비우면 비교 모델이 _bundle에 남아 이후 판정에 쓰일 수 있다."""
    original, compare = tmp_path / "orig.joblib", tmp_path / "cmp.joblib"
    original.touch()
    compare.touch()
    fake_joblib = types.SimpleNamespace(load=lambda p: {"model": Path(p).name})
    monkeypatch.setitem(sys.modules, "joblib", fake_joblib)
    monkeypatch.setattr(model_store, "MODEL_PATH", original)
    for name in ("_bundle", "_loaded", "_loaded_mtime"):
        monkeypatch.setattr(model_store, name, getattr(model_store, name))

    with model_store.swapped_bundle(compare) as bundle:
        assert bundle["model"] == "cmp.joblib"

    assert model_store._bundle["model"] == "orig.joblib"


def test_gate_cache_follows_the_bundle_not_its_id(monkeypatch):
    """게이트 캐시 키가 id(bundle)이면, 이전 번들이 해제된 뒤 같은 id를 받은 새 번들에 옛 게이트가 쓰인다
    (모델 파일 교체·evaluate_kpi --compare로 번들이 바뀔 때)."""
    def _bundle(th):
        return {"model": "m", "open_set_gate": {"thresholds": {"정지": th}, "centroids": {"정지": [1.0, 0.0]}}}

    holder = {"b": _bundle(0.1)}
    monkeypatch.setattr(model_store, "load_bundle", lambda force=False: holder["b"])
    monkeypatch.setattr(model_store, "_gate_cache", None)
    monkeypatch.setattr(model_store, "_gate_cache_key", None)
    # 옛 구현(id 키) 회귀 재현용 — 해제된 번들의 id를 새 번들이 다시 받는 상황을 매번 만든다.
    # 지금 구현은 id()를 쓰지 않으므로 이 패치와 무관하게 통과해야 한다.
    monkeypatch.setattr(model_store, "id", lambda _obj: 1, raising=False)

    assert model_store.get_open_set_gate()["thresholds"]["정지"] == 0.1
    holder["b"] = _bundle(0.9)
    assert model_store.get_open_set_gate()["thresholds"]["정지"] == 0.9


def test_swapped_bundle_none_keeps_current_path():
    original = model_store.MODEL_PATH

    with model_store.swapped_bundle(None):
        assert model_store.MODEL_PATH == original

    assert model_store.MODEL_PATH == original


def test_corrupt_bundle_is_not_reloaded_every_call(tmp_path, monkeypatch):
    """손상 번들은 파일이 바뀔 때까지 다시 읽지 않는다 — predict가 프레임마다 load_bundle을
    여러 번 불러, 기억하지 않으면 초당 수백 번 joblib.load·traceback이 반복됐다."""
    import os

    path = tmp_path / "broken.joblib"
    path.touch()
    calls = []

    def _load(p):
        calls.append(p)
        raise ValueError("corrupt")

    monkeypatch.setitem(sys.modules, "joblib", types.SimpleNamespace(load=_load))
    monkeypatch.setattr(model_store, "MODEL_PATH", path)
    for name in ("_bundle", "_loaded", "_loaded_mtime", "_failed_key"):
        monkeypatch.setattr(model_store, name, None if name != "_loaded" else False)

    assert model_store.load_bundle() is None
    assert model_store.load_bundle() is None
    assert len(calls) == 1, "같은 손상 파일을 다시 읽었다"

    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 10))   # 파일 교체
    model_store.load_bundle()
    assert len(calls) == 2, "파일이 바뀌었는데 다시 읽지 않았다"


def test_describe_reports_the_loaded_bundle_sha256(tmp_path, monkeypatch):
    """Pi에서 도는 번들이 KPI를 잰 번들과 같은지 /health로 대조할 수 있어야 한다."""
    import hashlib

    path = tmp_path / "bundle.joblib"
    path.write_bytes(b"bundle-bytes")
    monkeypatch.setitem(sys.modules, "joblib", types.SimpleNamespace(load=lambda p: {"model": "m"}))
    monkeypatch.setattr(model_store, "MODEL_PATH", path)
    for name in ("_bundle", "_loaded", "_loaded_mtime", "_failed_key", "_loaded_sha256"):
        monkeypatch.setattr(model_store, name, None if name != "_loaded" else False)

    assert model_store.describe()["sha256"] == hashlib.sha256(b"bundle-bytes").hexdigest()
