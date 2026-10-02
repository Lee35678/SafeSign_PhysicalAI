"""scripts/aggregate_kpi.py — 온라인 KPI 집계(16 §5.7 규칙) 단위 테스트."""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "aggregate_kpi.py"
_spec = importlib.util.spec_from_file_location("aggregate_kpi", _SCRIPT)
agg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agg)

WEB_FIELDS = [
    "time", "signal", "attempt", "outcome", "predicted", "match_score", "confidence",
    "vision_latency_ms", "demo_ok", "demo_ms", "observe_ms", "listen_ms",
    "picar_ok", "picar_ms", "microbit_ok", "microbit_ms", "feedback_ms",
    "aihand_ok", "aihand_ms", "feedback_done_ms", "aihand_status", "microbit_status",
    "picar_status", "picar_led_ok", "mocked", "subject",
]
DEMO_FIELDS = WEB_FIELDS[:17]


def _write(path: Path, fields: list[str], rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as f:   # web 로그와 같은 UTF-8 BOM
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    return path


def _row(signal, outcome, predicted=None, latency=100, feedback=40, done=900, mocked="False", subject="JH"):
    return {"signal": signal, "outcome": outcome, "predicted": predicted or signal,
            "vision_latency_ms": latency, "feedback_ms": feedback, "feedback_done_ms": done,
            "mocked": mocked, "subject": subject}


def test_p95_is_nearest_rank():
    assert agg.p95(list(range(1, 101))) == 95
    assert agg.p95([10, 20]) == 20
    assert agg.p95([7]) == 7
    assert agg.p95([]) is None


def test_wilson_upper_for_zero_errors():
    lo, hi = agg.wilson(0, 100)
    assert lo == 0.0
    assert 3.6 < hi < 3.8   # 0/100의 Wilson 95% 상한 ≈ 3.7%


def test_web_exclusions_rates_and_critical(tmp_path):
    path = _write(tmp_path / "web_trials_1.csv", WEB_FIELDS, [
        _row("정지", "correct"),
        _row("정지", "wrong", predicted="서행"),       # 치명 오분류
        _row("서행", "correct"),
        _row("주의", "below_tau", predicted=""),       # 미판정
        _row("후진", "correct", mocked="True"),        # 제외
    ])
    groups = agg.load([path])
    assert len(groups["web"]) == 5 and not groups["demo"]

    kept, excluded = agg.split_rows(groups["web"], include_mocked=False)
    assert excluded == {"mocked=true": 1}
    k = agg.classify_rows(kept)
    assert (k["n"], k["correct"], k["wrong"], k["rejected"]) == (4, 2, 1, 1)
    assert k["accuracy"] + k["misclass"] + k["reject"] == pytest.approx(100)
    assert k["critical"] == 1 and k["stop_n"] == 2


def test_stop_to_reject_is_not_critical():
    """안건 4 잠정치(A안) — 정지 → 미판정은 치명이 아니라 별도 집계."""
    k = agg.classify_rows([_row("정지", "below_tau", predicted="")])
    assert k["critical"] == 0 and k["stop_rejected"] == 1


def test_demo_csv_detected_and_timeout_skip_excluded(tmp_path):
    path = _write(tmp_path / "aihand_vision_picar_1.csv", DEMO_FIELDS, [
        _row("정지", "correct"), _row("서행", "timeout"), _row("주의", "skip"),
    ])
    groups = agg.load([path])
    assert len(groups["demo"]) == 3 and not groups["web"]
    kept, excluded = agg.split_rows(groups["demo"], include_mocked=False)
    assert len(kept) == 1
    assert excluded == {"timeout": 1, "skip": 1}


def test_decision_latency_uses_correct_rows_only_by_default():
    """안건 2 잠정치(A안) — 오답은 1초 유지 대기가 들어가 있어 판정 지연 모수에서 뺀다."""
    rows = [_row("정지", "correct", latency=100), _row("정지", "wrong", predicted="서행", latency=1200)]
    assert agg.latencies(rows, include_wrong=False)["decision"] == [100]
    assert agg.latencies(rows, include_wrong=True)["decision"] == [100, 1200]
    assert agg.latencies(rows, include_wrong=False)["feedback"] == [40]


def test_feedback_uses_correct_rows_only_by_default():
    """D2(2026-10-01) — 오답 행은 picar를 부르지 않아 micro:bit만 반영되므로 물리 피드백 모수에서 뺀다."""
    rows = [_row("정지", "correct", feedback=300, done=1500), _row("정지", "wrong", predicted="서행", feedback=30, done=1030)]
    lat = agg.latencies(rows, include_wrong=False)
    assert lat["feedback"] == [300] and lat["feedback_done"] == [1500]
    lat = agg.latencies(rows, include_wrong=False, feedback_include_wrong=True)
    assert lat["feedback"] == [300, 30]


def test_hand_based_upper_adds_decision_latency_and_poll_wait():
    """D1 — 손 기준 보수적 상한 = 판정 지연 + 폴링 대기(200ms) + 반응 시작."""
    rows = [_row("정지", "correct", latency=60, feedback=300), _row("서행", "correct", latency="", feedback=300)]
    assert agg.latencies(rows, include_wrong=False)["feedback_hand"] == [60 + agg.POLL_WAIT_MS + 300]


def test_p95_upper_needs_59_samples():
    """D4 — 0.95^59 < 0.05라 59개부터 P95의 95% 상한(= 최댓값)을 낼 수 있다. 표본이 많으면 최댓값보다 아래로 내려온다."""
    assert agg.p95_upper(list(range(58))) is None
    assert agg.p95_upper(list(range(1, 60))) == 59
    up = agg.p95_upper(list(range(1, 201)))
    assert agg.p95(list(range(1, 201))) <= up < 200


def test_small_sample_marks_provisional_pass():
    """점추정은 목표를 넘어도 Wilson 하한이 목표보다 낮으면 '잠정 달성'(§5.7). 지연도 n<59면 '잠정 달성'(D4)."""
    rows = [_row(s, "correct") for s in agg.SIGNS]
    k = agg.classify_rows(rows)
    lat = agg.latencies(rows, include_wrong=False)
    verdicts = {name: status for name, _, _, status in agg.verdict_rows(k, lat)}
    assert verdicts["정답률"] == "잠정 달성"
    assert verdicts["Macro F1"] == "달성"
    assert verdicts["판정 지연 (P95)"] == "잠정 달성"


def test_latency_pass_with_59_samples_and_fail_over_target():
    rows = [_row(agg.SIGNS[i % 7], "correct", latency=80, feedback=400) for i in range(59)]
    verdicts = {name: status for name, _, _, status in agg.verdict_rows(agg.classify_rows(rows),
                                                                           agg.latencies(rows, include_wrong=False))}
    assert verdicts["판정 지연 (P95)"] == "달성"
    assert verdicts["물리 피드백 지연 (P95, 반응 시작)"] == "달성"
    rows += [_row("정지", "correct", latency=1500) for _ in range(10)]   # 69개 중 10개 초과 → P95 초과
    verdicts = {name: status for name, _, _, status in agg.verdict_rows(agg.classify_rows(rows),
                                                                           agg.latencies(rows, include_wrong=False))}
    assert verdicts["판정 지연 (P95)"] == "미달"


def test_report_notes_guest_rows_without_subject(tmp_path, capsys):
    """D5 — LOG_SUBJECT 없이 진행하면 subject는 사원 코드, 게스트 회차는 빈 값 → 보고서에 건수를 적는다."""
    path = _write(tmp_path / "web_trials_4.csv", WEB_FIELDS,
                  [_row("정지", "correct", subject="SS-00001"), _row("서행", "correct", subject="")])
    assert agg.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "대상자 미기재 1행" in out and "손 기준 상한" in out


def test_main_writes_report(tmp_path, capsys):
    path = _write(tmp_path / "web_trials_2.csv", WEB_FIELDS, [_row(s, "correct") for s in agg.SIGNS])
    out = tmp_path / "out"
    assert agg.main([str(path), "--out", str(out)]) == 0
    text = (out / "kpi_report.md").read_text(encoding="utf-8")
    assert "2-1. 요약" in text and "2-2. 혼동행렬" in text and "2-3. 지연 분포" in text and "2-4. 대상자별" in text
    assert "web_trials_2.csv" in text   # 재현성 — 입력 파일을 남긴다


def test_main_rejects_missing_file(tmp_path):
    assert agg.main([str(tmp_path / "nope.csv")]) == 2


def test_web_timeout_excluded_by_default_or_counted_as_reject(tmp_path):
    """web `timeout`(판정 제한시간 초과) — 기본은 §5.7대로 제외·건수 보고, 옵션이면 미판정(16 §6.4 선택지)."""
    path = _write(tmp_path / "web_trials_3.csv", WEB_FIELDS, [_row("정지", "correct"), _row("주의", "timeout", predicted="")])
    rows = agg.load([path])["web"]
    kept, excluded = agg.split_rows(rows, include_mocked=False)
    assert len(kept) == 1 and excluded == {"timeout": 1}
    kept, excluded = agg.split_rows(rows, include_mocked=False, timeout_as_reject=True)
    assert len(kept) == 2 and not excluded
    k = agg.classify_rows(kept)
    assert (k["correct"], k["rejected"]) == (1, 1)
