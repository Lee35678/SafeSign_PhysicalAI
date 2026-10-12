"""AiHandCommand(target_signal) -> micro:bit BLE 제스처 전송.

2026-09-21: RPi5가 서보 각도(servo_angles)를 직접 계산해 GPIO로 구동하는 방식에서, micro:bit
펌웨어(aihand_control.ts, TEST_MODE=false)에 미리 캘리브레이션된 "G1~G7" 제스처를 BLE로 호출하는 방식으로
전환했다 — micro:bit 하드웨어 UART가 1개뿐이라 USB 시리얼과 서보 초기화가 충돌하는 제약 때문
(doc/aihand_gesture_checklist_final.md 세션 1). servo_angles 필드는 인터페이스 계약(§5-1)
하위 호환을 위해 요청에는 남아있지만, 실제 구동에는 target_signal만 사용한다.

target_signal <-> G{n} 매핑은 10_PRD.md §3.2 표 순서와 동일하다. 우회전_유도(G4)는 설계
문서상 "엄지+약지"이나 실제 펌웨어(aihand_control.ts)는 "엄지+소지"로 구현되어 있다 —
펌웨어 쪽이 최종 확정판이며 문서 갱신은 별도로 필요하다(2026-09-21 팀 확인).
"""
from microbit import ble_bridge

GESTURE_MAP = {
    "정지": 1,
    "서행": 2,
    "좌회전_유도": 3,
    "우회전_유도": 4,
    "확인_완료": 5,
    "후진": 6,
    "주의": 7,
}


async def execute(aihand_command: dict, mock: bool = True) -> dict:
    target_signal = aihand_command.get("target_signal")
    gesture_num = GESTURE_MAP.get(target_signal)
    if gesture_num is None:
        return {"status": "error", "reason": "unknown_target_signal", "target_signal": target_signal}

    result = await ble_bridge.send_gesture(gesture_num, mock=mock)
    return {**result, "target_signal": target_signal, "gesture": gesture_num}
