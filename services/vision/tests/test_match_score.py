"""일치율(match_score) 환산 — 클래스별 보정(per_class)이 있으면 그것을, 없으면 공통 구간을 쓰는가 (2026-09-30).

실행: python tests/test_match_score.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cognition import templates  # noqa: E402

CAL = {"sim_min": 0.92, "sim_max": 1.0,
       "per_class": {"확인_완료": {"sim_min": 0.60, "sim_max": 1.0}}}


def test_per_class_range_is_used_for_that_class():
    # 공통 구간이면 0.98 → 75점, 확인_완료 자기 구간(0.60~1.0)이면 95점
    assert templates.similarity_to_score(0.98, CAL, "확인_완료") == 95
    assert templates.similarity_to_score(0.98, CAL) == 75


def test_other_classes_fall_back_to_common_range():
    assert templates.similarity_to_score(0.98, CAL, "정지") == 75


def test_old_bundle_without_per_class_still_works():
    old = {"sim_min": 0.92, "sim_max": 1.0}
    assert templates.similarity_to_score(0.98, old, "확인_완료") == 75
    assert templates.similarity_to_score(0.5, None) == 50


def test_score_is_clipped():
    assert templates.similarity_to_score(0.10, CAL, "확인_완료") == 0
    assert templates.similarity_to_score(1.50, CAL, "확인_완료") == 100


if __name__ == "__main__":
    _passed = []
    for _n, _f in sorted(globals().copy().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
            _passed.append(_n)
            print(f"  ok  {_n}")
    print(f"{len(_passed)}개 통과")
