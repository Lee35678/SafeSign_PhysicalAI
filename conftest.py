"""저장소 공통 pytest 설정.

hw 마커가 붙은 테스트는 실물 장치가 있어야 하므로 기본으로 건너뛴다.
실물 보드에서 돌릴 때만 `pytest --run-hw -m hw`로 켠다.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-hw",
        action="store_true",
        default=False,
        help="실물 장치가 필요한 hw 마커 테스트까지 실행한다",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-hw"):
        return
    skip_hw = pytest.mark.skip(reason="실물 장치 필요 — --run-hw로 실행")
    for item in items:
        if item.get_closest_marker("hw"):
            item.add_marker(skip_hw)
