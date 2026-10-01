"""학습자 화면 일치율 = 목표 수신호의 확률 × 100 (2026-09-30) — state_machine `_target_score`.

예전에는 vision match_score(예측 클래스 템플릿과의 코사인)를 그대로 써서, 다른 손동작을 해도
"그 틀린 동작과는 잘 맞는다"는 뜻으로 85~99%가 떴다(서행 목표에 정지 손 → 99%).

실행: cd services/web && python -m pytest tests/test_target_score.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import state_machine as sm  # noqa: E402


class _Resp:
    status_code = 200

    def __init__(self, payload=None):
        self._p = payload if payload is not None else {"status": "ok"}

    def json(self):
        return self._p


class _Vision:
    def __init__(self, judgment):
        self.judgment = judgment

    def get(self, url):
        return _Resp(self.judgment)

    def post(self, url, **_):
        return _Resp()


def _reset():
    sm._session.clear()
    sm._session.update(sm._fresh_session())
    sm._session["state"] = "training"
    sm._session["phase"] = "judging"


def _probs(**kw):
    p = dict.fromkeys(sm.CURRICULUM, 0.0)
    p.update(kw)
    return p


def test_score_is_target_probability():
    j = {"match_score": 99, "class_probabilities": _probs(정지=0.97, 서행=0.02)}
    assert sm._target_score(j, "정지") == 97
    assert sm._target_score(j, "서행") == 2, "정지 손을 서행 목표로 보면 2점 — 99점이 아니다"


def test_falls_back_to_vision_match_score_without_probabilities():
    assert sm._target_score({"match_score": 64}, "정지") == 64          # 구버전 vision · 게이트 차단
    assert sm._target_score({}, "정지") == 0


def test_wrong_gesture_shows_low_score_for_target():
    """목표 정지에 서행 손을 1초 넘게 들면 오답 — 화면 일치율은 정지 기준으로 낮아야 한다."""
    _reset()
    wrong = {"predicted_class": "서행", "confidence": 0.95, "match_score": 96, "is_reject": False,
             "latency_ms": 40, "class_probabilities": _probs(서행=0.95, 정지=0.03)}
    saved = sm.WRONG_CONFIRM_S
    sm.WRONG_CONFIRM_S = 0.0
    try:
        with patch.object(sm.httpx, "post", lambda *a, **k: _Resp()):
            v = _Vision(wrong)
            sm._poll_once(v)
            assert sm._session["live_judgment"]["match_score"] == 3, "실시간 막대도 목표 기준"
            sm._poll_once(v)
    finally:
        sm.WRONG_CONFIRM_S = saved
    r = sm._session["last_result"]
    assert r["outcome"] == "wrong" and r["match_score"] == 3
    assert r["recommended_retry"] == 3, "낮은 일치율이면 재도전을 더 권한다"


def test_correct_records_target_probability():
    _reset()
    ok = {"predicted_class": "정지", "confidence": 0.91, "match_score": 55, "is_reject": False,
          "latency_ms": 40, "class_probabilities": _probs(정지=0.91, 서행=0.05)}
    with patch.object(sm.httpx, "post", lambda *a, **k: _Resp()):
        sm._poll_once(_Vision(ok))
    assert sm._session["last_result"]["outcome"] == "correct"
    assert sm._session["completed"][0]["match_score"] == 91, "SC-05 '정답 시 일치율' = 목표 확률"
