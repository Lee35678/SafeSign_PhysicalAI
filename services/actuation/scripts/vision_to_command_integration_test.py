"""vision(MediaPipe) 판정 결과 -> actuation `/command` 연동을 미리 검증하는 통합 테스트.

아직 web의 상태머신(services/web/backend/state_machine.py)이 vision `/latest`를 폴링해
actuation `/command`를 호출하는 부분은 구현되어 있지 않다(TODO). 그 전에 이 스크립트로
"vision이 내놓는 JudgmentResult 형태의 값 -> AiHandCommand -> micro:bit G{n} 제스처"
경로가 실제로 동작하는지 먼저 검증한다.

judgment_result.schema.json의 predicted_class(정지/서행/...·negative)를
aihand_command.schema.json의 target_signal로 그대로 매핑해서 사용하며, is_reject 또는
predicted_class=="negative"인 경우는 AiHand로 보내지 않는다(둘 다 실제 상태머신이 따라야 할 규칙).

설치: pip install httpx
실행: python vision_to_command_integration_test.py [--url http://localhost:8002] [--loop]

MOCK_HARDWARE=true(기본값)인 actuation 인스턴스를 대상으로 하면 BLE 없이도 매핑/응답 형식을
검증할 수 있고, 실물 micro:bit에 연결된 MOCK_HARDWARE=false 인스턴스를 대상으로 하면 실제
제스처가 재현되는지까지 확인할 수 있다.
"""
import argparse
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from aihand.controller import DEFAULT_SERVO_ANGLES, GESTURE_MAP  # noqa: E402

# vision이 아직 카메라/MediaPipe 없이 목업(negative)만 내놓는 단계이므로, 여기서는 vision의
# `/latest` 대신 "손 정지 후 확정된 판정"을 흉내 낸 샘플 JudgmentResult를 순서대로 재생한다.
SAMPLE_JUDGMENTS = [
    {"predicted_class": name, "confidence": 0.95, "match_score": 88, "is_reject": False, "latency_ms": 320}
    for name in GESTURE_MAP
] + [
    {"predicted_class": "negative", "confidence": 0.2, "match_score": 0, "is_reject": True, "latency_ms": 150},
]


def judgment_to_command(judgment: dict) -> "dict | None":
    """JudgmentResult -> AiHandCommand. reject/negative는 AiHand로 보내지 않는다(None 반환)."""
    if judgment["is_reject"] or judgment["predicted_class"] == "negative":
        return None
    target_signal = judgment["predicted_class"]
    return {
        "command": "demo",
        "target_signal": target_signal,
        "servo_angles": DEFAULT_SERVO_ANGLES[target_signal],
    }


def run(base_url: str, loop: bool) -> bool:
    ok = True
    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        health = client.get("/health").json()
        print(f"[health] {health}")

        judgments = SAMPLE_JUDGMENTS
        while True:
            for judgment in judgments:
                aihand_command = judgment_to_command(judgment)
                if aihand_command is None:
                    print(f"[skip] predicted_class={judgment['predicted_class']!r} (reject/negative)")
                    continue

                response = client.post("/command", json=aihand_command)
                body = response.json()
                expected_gesture = GESTURE_MAP[aihand_command["target_signal"]]
                passed = response.status_code == 200 and body.get("gesture") == expected_gesture
                ok = ok and passed
                mark = "OK" if passed else "FAIL"
                print(f"[{mark}] {aihand_command['target_signal']} -> G{expected_gesture}: {body}")
                time.sleep(1)

            if not loop:
                break
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8002", help="actuation base URL")
    parser.add_argument("--loop", action="store_true", help="샘플 판정 목록을 계속 반복 재생")
    args = parser.parse_args()

    passed = run(args.url, args.loop)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
