"""
AiHand 5손가락 제어 (매핑 확정 버전, 손가락 이름/제스처 번호 지원)
설치: pip install bleak
실행: python aihand_named_control_pc.py
"""

import asyncio
from bleak import BleakClient, BleakScanner

UART_RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # PC -> micro:bit (write)
UART_TX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # micro:bit -> PC (indicate)

GESTURE_NAMES = {
    1: "다섯 손가락 펴기 + 정면",
    2: "검지+중지 펴기 + 정면",
    3: "엄지 펴기 + 검지펴기",
    4: "엄지 펴기 + 소지 펴기",
    5: "엄지만 펴기 + 정면",
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


async def main():
    target = await find_microbit()
    if not target:
        print("micro:bit를 찾지 못했습니다.")
        return

    print(f"연결 시도: {target.name} ({target.address})")

    async with BleakClient(target.address) as client:
        print(f"연결 성공! (연결 상태: {client.is_connected})")
        await client.start_notify(UART_TX_UUID, notification_handler)

        print("""
=== 명령어 안내 ===
  idx <번호> <각도>       : 서보에 raw 각도 직접 전달 (반전 없음, 캘리브레이션용)
                          예) idx 2 35   -> 검지 서보에 물리적으로 35도
  g <번호>              : 체크리스트 제스처 실행 (1~7)
                          1=다섯 펴기 2=검지중지펴기 3=엄지+검지 4=엄지+소지
                          5=엄지만 6=검지만 7=소지만
  hand <5개 각도>        : 엄지,검지,중지,약지,소지 순서로 콤마 구분
                          예) hand 0,180,180,180,180
  q                      : 종료
===================
""")

        loop = asyncio.get_event_loop()
        while True:
            user_input = await loop.run_in_executor(None, input, "명령> ")
            user_input = user_input.strip()

            if user_input.lower() == "q":
                break

            if user_input.startswith("idx "):
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
                print("알 수 없는 명령입니다. g / hand / q 중 하나를 입력하세요.")


if __name__ == "__main__":
    asyncio.run(main())