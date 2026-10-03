"""evaluate_kpi의 판정 규칙·KPI 계산 — 제출 수치(정답률·오분류율·미판정률·Macro F1·Wilson 상한)를 만드는 코드.

train_svm의 특징 캐시 지문도 여기서 고정한다(특징 코드가 바뀌면 캐시를 버려야 한다).

실행: python -m pytest tests/test_evaluate_kpi.py -q
"""
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    # scripts/·training/은 패키지가 아니다 — 경로로 적재하고 고유 이름을 준다
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ek = _load("vision_evaluate_kpi", "scripts/evaluate_kpi.py")


def _f(cls=None, reason=None):
    """프레임 판정 한 건. cls=None이면 미판정."""
    if cls is None:
        return {"is_reject": True, "predicted_class": "negative", "reason": reason or "low_confidence"}
    return {"is_reject": False, "predicted_class": cls}


# ── 공식 규칙: n프레임 연속 ───────────────────────────────────────────────────
def test_consecutive_takes_the_first_run_of_n():
    judged = [_f("서행"), _f("정지"), _f("정지"), _f("정지"), _f("서행")]
    assert ek.judge_consecutive(judged, n=3) == ("정지", False, None)


def test_consecutive_run_is_broken_by_a_reject():
    judged = [_f("정지"), _f("정지"), _f(None), _f("정지"), _f("정지")]
    pred, rejected, reason = ek.judge_consecutive(judged, n=3)
    assert (pred, rejected, reason) == ("negative", True, "low_confidence")


def test_consecutive_without_any_reject_reports_awaiting():
    judged = [_f("정지"), _f("서행"), _f("정지")]
    assert ek.judge_consecutive(judged, n=3) == ("negative", True, "awaiting_consecutive_frames")


# ── 참고 규칙: 최빈값 ──────────────────────────────────────────────────────────
def test_mode_ignores_rejects_and_takes_the_most_common():
    judged = [_f("서행"), _f(None), _f("정지"), _f("정지")]
    assert ek.judge_mode(judged) == ("정지", False, None)


def test_mode_with_only_rejects_is_a_reject():
    assert ek.judge_mode([_f(None, "no_hand")]) == ("negative", True, "no_hand")


# ── Wilson 95% 상한 ───────────────────────────────────────────────────────────
def test_wilson_upper_for_zero_out_of_59():
    """"0건" 주장에 붙이는 상한(16 §5.7) — 0/59면 약 6.1%."""
    assert ek.wilson_upper(0, 59) == pytest.approx(6.11, abs=0.01)


def test_wilson_upper_is_never_below_the_observed_rate():
    for k, n in [(0, 1), (3, 10), (10, 10), (5, 200)]:
        assert ek.wilson_upper(k, n) >= k / n * 100


def test_wilson_upper_without_samples_is_100():
    assert ek.wilson_upper(0, 0) == 100.0


# ── KPI 표 ────────────────────────────────────────────────────────────────────
def _row(cls, pred, reject=False):
    return {"cls": cls, "pred": pred, "reject": reject}


def test_kpi_table_counts_correct_wrong_reject_and_critical():
    rows = [
        _row("정지", "정지"),
        _row("정지", "서행"),                 # 오분류 + 치명(정지를 다른 것으로)
        _row("서행", "negative", reject=True),
        _row("서행", "서행"),
        _row(ek.AMBIGUOUS, "정지"),           # 수신호가 아닌 클래스는 분모에서 뺀다
    ]
    k = ek.kpi_table(rows)
    assert k["n"] == 4
    assert k["accuracy"] == pytest.approx(50.0)
    assert k["misclass"] == pytest.approx(25.0)
    assert k["reject"] == pytest.approx(25.0)
    assert k["critical"] == 1


def test_kpi_table_macro_f1_is_one_when_every_class_is_right():
    rows = [_row(c, c) for c in ek.CLASSES]
    assert ek.kpi_table(rows)["macro_f1"] == pytest.approx(1.0)


def test_kpi_table_counts_rejects_as_misses_in_f1():
    """미판정도 학습자 입장에선 실패 — 해당 클래스 재현율을 깎는다."""
    rows = [_row(c, c) for c in ek.CLASSES] + [_row(ek.CLASSES[0], "negative", reject=True)]
    assert ek.kpi_table(rows)["macro_f1"] < 1.0


def test_kpi_table_without_sign_rows_is_empty():
    assert ek.kpi_table([_row(ek.AMBIGUOUS, "정지")]) == {}


def test_mode_rule_rows_swap_in_the_mode_prediction():
    row = {"cls": "정지", "pred": "negative", "reject": True, "reason": "x",
           "mode_pred": "정지", "mode_reject": False, "mode_reason": None}
    assert ek.as_mode_rule([row])[0]["pred"] == "정지"
    assert ek.as_mode_rule([row])[0]["reject"] is False


# ── 학습 특징 캐시 지문 ───────────────────────────────────────────────────────
def test_cache_signature_changes_when_feature_code_changes(tmp_path, monkeypatch):
    """normalize.py를 고쳐도 지문이 같으면 옛 특징으로 학습돼 실행 시 특징과 어긋난다."""
    ts = _load("vision_train_svm", "training/train_svm.py")
    fake_root = tmp_path / "svc"
    src = fake_root / "src" / "cognition" / "normalize.py"
    src.parent.mkdir(parents=True)
    src.write_text("v1", encoding="utf-8")
    monkeypatch.setattr(ts, "SERVICE_ROOT", fake_root)

    before = ts._cache_signature(tmp_path, "joint23", None)
    src.write_text("v2", encoding="utf-8")
    assert ts._cache_signature(tmp_path, "joint23", None) != before
