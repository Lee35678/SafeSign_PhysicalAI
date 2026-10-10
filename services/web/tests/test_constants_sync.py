"""여러 곳에 따로 적힌 수신호 정의가 서로 어긋나지 않는지 — 교육장 web(Python·JS), 회사 사이트(portal),
vision(분류 클래스·촬영 스크립트), picar 스키마.

하나로 합치려면 프런트엔드가 API로 정의를 받아 오게 바꿔야 해서(2026-10-03 tech-debt 2단계 보류), 대신
같아야 하는 값을 여기서 대조한다. 화면 문구(picar 설명의 "+" ↔ "," 같은 표기)는 일부러 다르게 쓰므로
비교하지 않는다. 다른 서비스 코드는 import하지 않고 글자로 읽는다(서비스별 CI 환경에 그쪽 의존성이 없다).
"""
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import state_machine as sm  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
MAIN_JS = (REPO / "services/web/frontend/main.js").read_text(encoding="utf-8")
PORTAL_JS = (REPO / "services/portal/frontend/portal.js").read_text(encoding="utf-8")


def _py_literal(rel: str, name: str):
    """다른 서비스 파일의 모듈 수준 리터럴 상수를 import 없이 읽는다."""
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{rel}에 {name}이 없다")


def _main_js_patterns() -> dict:
    block = re.search(r"const SIGN_PATTERNS = \{(.*?)\};", MAIN_JS, re.S).group(1)
    return {name: json.loads(arr) for name, arr in re.findall(r'"([^"]+)":\s*(\[[\d,\s]+\])', block)}


def _portal_signals() -> list:
    block = re.search(r"const SIGNALS = \[(.*?)\];", PORTAL_JS, re.S).group(1)
    return [{"name": n, "fingers": json.loads(f), "aihand": a}
            for n, f, a in re.findall(r'name: "([^"]+)", fingers: (\[[\d,\s]+\]), aihand: "([^"]+)"', block)]


def test_station_js_patterns_follow_the_curriculum():
    assert list(_main_js_patterns()) == sm.CURRICULUM


def test_portal_lists_the_same_signs_in_the_same_order():
    names = [s["name"] for s in _portal_signals()]
    assert names == [c.replace("_", " ") for c in sm.CURRICULUM]


def test_portal_fingers_match_the_station():
    station = _main_js_patterns()
    for s in _portal_signals():
        assert s["fingers"] == station[s["name"].replace(" ", "_")], s["name"]


def test_portal_aihand_text_matches_the_station():
    """station 화면은 변경 이력 괄호("(2026-09-20 변경: …)")를 빼고 보여 준다 — portal도 그 글자와 같아야 한다."""
    for s in _portal_signals():
        info = sm.CURRICULUM_INFO[s["name"].replace(" ", "_")]["aihand"]
        shown = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\s*변경[^)]*\)", "", info)
        assert s["aihand"] == shown, s["name"]


def test_vision_classes_are_the_curriculum():
    assert list(_py_literal("services/vision/src/cognition/classify.py", "SIGN_CLASSES")) == sm.CURRICULUM


def test_recording_script_shapes_match_the_station():
    """촬영 스크립트(record_dataset.py)의 ●/○ 손모양 = 화면의 손가락 패턴."""
    station = _main_js_patterns()
    for name, dots, _desc in _py_literal("services/vision/scripts/record_dataset.py", "SIGN_SHAPES"):
        assert [1 if d == "●" else 0 for d in dots] == station[name], name


def test_portal_curriculum_size_is_the_curriculum_length():
    size = int(re.search(r"^CURRICULUM_SIZE = (\d+)", (REPO / "services/portal/app/main.py")
                         .read_text(encoding="utf-8"), re.M).group(1))
    assert size == len(sm.CURRICULUM)


def test_web_scripts_use_the_curriculum():
    """오프라인 도구(KPI 집계·화면 캡처)에 따로 적힌 7종 목록과 picar command."""
    assert _py_literal("services/web/scripts/aggregate_kpi.py", "SIGNS") == sm.CURRICULUM
    assert _py_literal("services/web/scripts/capture_screens.py", "SIGNS") == sm.CURRICULUM


def test_capture_script_commands_match_picar_commands():
    command = _py_literal("services/web/scripts/capture_screens.py", "COMMAND")
    assert command == {s: c["command"] for s, c in sm.PICAR_COMMANDS.items()}


def test_picar_speeds_stay_within_the_schema_maximum():
    schema = json.loads((REPO / "shared/schemas/picar_command.schema.json").read_text(encoding="utf-8"))
    maximum = schema["properties"]["motor"]["properties"]["speed"]["maximum"]
    assert all(c["motor"]["speed"] <= maximum for c in sm.PICAR_COMMANDS.values())
