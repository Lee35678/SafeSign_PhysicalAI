"""
AiHand PC 테스트 스크립트 (운영/테스트 통합)
micro:bit 쪽 aihand_control.ts와 짝을 이루는 스크립트입니다.
TEST_MODE 한 줄만 바꿔서 운영/테스트 모드를 전환합니다 (micro:bit 쪽 TEST_MODE 값과 동일하게 맞출 것).
  - TEST_MODE = False (운영): "G1"~"G7" (콜론 없음) 명령. 입력은 1~7 숫자 또는 loop/q.
  - TEST_MODE = True  (테스트/캘리브레이션): "IDX:", "HAND:", "G:" 명령. 입력은 idx/g/hand/q.

설치: pip install bleak
실행: python aihand_control_pc.py
"""

import asyncio
from bleak import BleakClient, BleakScanner

TEST_MODE = False

UART_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # PC -> micro:bit (write)
UART_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # micro:bit -> PC (indicate)

GESTURE_NAMES = {
    1: "다섯 손가락 펴기 + 정면",
    2: "검지+중지 펴기 + 정면",
    3: "엄지 펴기 + 검지펴기",
    4: "엄지 펴기 + 소지 펴기",
    5: "주먹 (다섯 손가락 접기)",
    6: "검지 펴기",
    7: "소지 펴기",
}


def notification_handler(sender, data):
    msg = data.decode("utf-8", errors="replace").strip()
    print(f"[수신] {msg}")


async def find_microbit():
    print("micro:bit 스캔 중... (5초)")
    devices = await BleakScanner.discover(timeout=5.0)
    return next((d for d in devices if d.name and "BBC micro:bit" in d.name), None)


async def send_gesture(client, g: int):
    msg = f"G{g}\n"  # 콜론 없이 "G1" ~ "G7" 형식 (운영 모드)
    await client.write_gatt_char(UART_RX_UUID, msg.encode())
    name = GESTURE_NAMES.get(g, "알수없음")
    print(f"[송신] {msg.strip()}  ({name})")


async def send_result(client, is_correct: bool):
    # TEST_MODE와 무관하게 항상 지원
    # "correct"   -> LED 'O' 2초 표시 후 소등, "OK:CORRECT" 회신
    # "incorrect" -> LED 'X' 2초 표시 후 소등, "OK:INCORRECT" 회신
    # 소리(부저)는 쓰지 않는다 — BLE 시작 후 music.* 호출은 패닉 070을 유발한다
    # (aihand_control.ts 최상단 "절대 규칙" 참고)
    msg = "correct\n" if is_correct else "incorrect\n"
    await client.write_gatt_char(UART_RX_UUID, msg.encode())
    print(f"[송신] {msg.strip()}")


async def send_progress(client, current: int, total: int):
    # TEST_MODE와 무관하게 항상 지원. "P<current><total>" (둘 다 한 자리 숫자). LED 표시 없이 회신만.
    msg = f"P{current}{total}\n"
    await client.write_gatt_char(UART_RX_UUID, msg.encode())
    print(f"[송신] {msg.strip()}  ({current}/{total}번째)")


async def run_production(client):
    # ==== 시연용 코드 (실전 배포, TEST_MODE=False일 때 실행) ====
    print("""
=== 명령어 안내 (운영용 경량 버전) ===
  <번호>   : 제스처 실행 (1~7)
             1=다섯펴기 2=검지중지 3=엄지+검지 4=엄지+소지
             5=엄지만 6=검지만 7=소지만
  loop     : 1~7번을 순서대로 5회 반복 (내구성/안정성 테스트용)
  correct   : 판정 결과 LED에 O 표시(2초, 소리 없음)
  incorrect : 판정 결과 LED에 X 표시(2초, 소리 없음)
  progress <current> <total> : 진행 표시 전송 (LED 표시 없음, 회신만 확인)
                          예) progress 3 7
  q        : 종료
=====================================
""")

    loop = asyncio.get_event_loop()
    while True:
        user_input = (await loop.run_in_executor(None, input, "명령> ")).strip()

        if user_input.lower() == "q":
            break

        if user_input.lower() in ("correct", "incorrect"):
            try:
                await send_result(client, user_input.lower() == "correct")
            except Exception as e:
                print(f"전송 실패: {e}")
                print("BLE 연결이 끊겼을 수 있습니다. micro:bit LED 상태를 확인하세요.")
                break
            continue

        if user_input.lower().startswith("progress "):
            try:
                _, current, total = user_input.split()
                await send_progress(client, int(current), int(total))
            except ValueError:
                print("형식: progress <current> <total>  예) progress 3 7")
            except Exception as e:
                print(f"전송 실패: {e}")
                print("BLE 연결이 끊겼을 수 있습니다. micro:bit LED 상태를 확인하세요.")
                break
            continue

        if user_input.lower() == "loop":
            print("반복 테스트 시작 (5회 x 7가지 제스처, 각 1초 간격)")
            try:
                for round_num in range(1, 6):
                    print(f"--- {round_num}회차 ---")
                    for g in range(1, 8):
                        await send_gesture(client, g)
                        await asyncio.sleep(1)
                print("반복 테스트 완료. 크래시/끊김 없었는지 micro:bit 상태 확인하세요.")
            except Exception as e:
                print(f"반복 중 오류 발생: {e}")
                print("BLE 연결이 끊겼을 수 있습니다. micro:bit LED 상태를 확인하세요.")
                break
            continue

        try:
            g = int(user_input)
        except ValueError:
            print("1~7 사이 숫자, 'loop', 또는 'q'를 입력하세요.")
            continue

        if not (1 <= g <= 7):
            print("1~7 사이 값만 가능합니다.")
            continue

        try:
            await send_gesture(client, g)
        except Exception as e:
            print(f"전송 실패: {e}")
            print("BLE 연결이 끊겼을 수 있습니다. micro:bit LED 상태를 확인하세요.")
            break


async def run_test(client):
    # ==== 테스트용 코드 (캘리브레이션/디버깅, 시연 때는 사용 안 함) ====
    print("""
=== 명령어 안내 (테스트/캘리브레이션용) ===
  idx <번호> <각도>       : 서보에 raw 각도 직접 전달 (반전 없음, 캘리브레이션용)
                          예) idx 2 35   -> 검지 서보에 물리적으로 35도
  g <번호>              : 체크리스트 제스처 실행 (1~7)
                          1=다섯 펴기 2=검지중지펴기 3=엄지+검지 4=엄지+소지
                          5=엄지만 6=검지만 7=소지만
  hand <5개 각도>        : 엄지,검지,중지,약지,소지 순서로 콤마 구분
                          예) hand 0,180,180,180,180
  correct                : 판정 결과 LED에 O 표시(2초, 소리 없음)
  incorrect              : 판정 결과 LED에 X 표시(2초, 소리 없음)
  progress <current> <total> : 진행 표시 전송 (LED 표시 없음, 회신만 확인)
  q                      : 종료
===================
""")

    loop = asyncio.get_event_loop()
    while True:
        user_input = await loop.run_in_executor(None, input, "명령> ")
        user_input = user_input.strip()

        if user_input.lower() == "q":
            break

        if user_input.lower() in ("correct", "incorrect"):
            try:
                await send_result(client, user_input.lower() == "correct")
            except Exception as e:
                print(f"전송 실패: {e}")
                print("BLE 연결이 끊겼을 수 있습니다.")
                break

        elif user_input.lower().startswith("progress "):
            try:
                _, current, total = user_input.split()
                await send_progress(client, int(current), int(total))
            except ValueError:
                print("형식: progress <current> <total>  예) progress 3 7")
            except Exception as e:
                print(f"전송 실패: {e}")
                print("BLE 연결이 끊겼을 수 있습니다.")
                break

        elif user_input.startswith("idx "):
            try:
                _, idx, angle = user_input.split()
                msg = f"IDX:{idx},{angle}\n"
                await client.write_gatt_char(UART_RX_UUID, msg.encode())
                print(f"[송신] {msg.strip()}  (raw, 반전 없음)")
            except ValueError:
                print("형식: idx <번호> <각도>  예) idx 2 35")
            except Exception as e:
                print(f"전송 실패: {e}")
                print("BLE 연결이 끊겼을 수 있습니다.")
                break

        elif user_input.startswith("g "):
            try:
                g = int(user_input.split()[1])
                msg = f"G:{g}\n"
                await client.write_gatt_char(UART_RX_UUID, msg.encode())
                name = GESTURE_NAMES.get(g, "알수없음")
                print(f"[송신] {msg.strip()}  ({name})")
            except (ValueError, IndexError):
                print("형식: g <번호>  예) g 3")
            except Exception as e:
                print(f"전송 실패: {e}")
                print("BLE 연결이 끊겼을 수 있습니다. micro:bit 상태(LED)를 확인하고 스크립트를 재실행하세요.")
                break

        elif user_input.startswith("hand "):
            angles = user_input[5:].strip()
            if len(angles.split(",")) != 5:
                print("각도 5개를 콤마로 구분해서 입력하세요. 예) hand 0,170,170,170,170")
                continue
            msg = f"HAND:{angles}\n"
            try:
                await client.write_gatt_char(UART_RX_UUID, msg.encode())
                print(f"[송신] {msg.strip()}  (엄지,검지,중지,약지,소지)")
            except Exception as e:
                print(f"전송 실패: {e}")
                print("BLE 연결이 끊겼을 수 있습니다. micro:bit 상태(LED)를 확인하고 스크립트를 재실행하세요.")
                break

        else:
            print("알 수 없는 명령입니다. idx / g / hand / correct / incorrect / progress / q 중 하나를 입력하세요.")


async def main():
    target = await find_microbit()
    if not target:
        print("micro:bit를 찾지 못했습니다.")
        return

    print(f"연결 시도: {target.name} ({target.address})")

    async with BleakClient(target.address) as client:
        print(f"연결 성공! (연결 상태: {client.is_connected})")
        await client.start_notify(UART_TX_UUID, notification_handler)

        if TEST_MODE:
            await run_test(client)
        else:
            await run_production(client)


if __name__ == "__main__":
    asyncio.run(main())
