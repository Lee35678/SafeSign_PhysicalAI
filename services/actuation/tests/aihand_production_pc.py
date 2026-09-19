"""
AiHand 운영용(경량화 버전) PC 테스트 스크립트
micro:bit 쪽 aihand_production.ts 와 짝을 이루는 스크립트입니다.
명령 형식이 "G1"~"G7" (콜론 없음) 인 것에 주의하세요.

설치: pip install bleak
실행: python aihand_production_pc.py
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


async def send_gesture(client, g: int):
    msg = f"G{g}\n"  # 콜론 없이 "G1" ~ "G7" 형식
    await client.write_gatt_char(UART_RX_UUID, msg.encode())
    name = GESTURE_NAMES.get(g, "알수없음")
    print(f"[송신] {msg.strip()}  ({name})")


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
=== 명령어 안내 (운영용 경량 버전) ===
  <번호>   : 제스처 실행 (1~7)
             1=다섯펴기 2=검지중지 3=엄지+검지 4=엄지+소지
             5=엄지만 6=검지만 7=소지만
  loop     : 1~7번을 순서대로 5회 반복 (내구성/안정성 테스트용)
  q        : 종료
=====================================
""")

        loop = asyncio.get_event_loop()
        while True:
            user_input = (await loop.run_in_executor(None, input, "명령> ")).strip()

            if user_input.lower() == "q":
                break

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


if __name__ == "__main__":
    asyncio.run(main())
