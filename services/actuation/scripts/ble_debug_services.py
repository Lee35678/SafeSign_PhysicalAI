"""
micro:bit가 실제로 제공하는 BLE 서비스/캐릭터리스틱을 전부 출력해서
UART RX/TX의 정확한 UUID와 속성(notify/write 등)을 확인하는 디버그 스크립트
설치: pip install bleak
"""

import asyncio
from bleak import BleakClient, BleakScanner


async def main():
    print("micro:bit 스캔 중... (5초)")
    devices = await BleakScanner.discover(timeout=5.0)
    target = next((d for d in devices if d.name and "BBC micro:bit" in d.name), None)

    if not target:
        print("micro:bit를 찾지 못했습니다.")
        return

    print(f"연결 시도: {target.name} ({target.address})")

    async with BleakClient(target.address) as client:
        print(f"연결 성공! (연결 상태: {client.is_connected})\n")
        print("=== 서비스/캐릭터리스틱 목록 ===")

        for service in client.services:
            print(f"\n[서비스] {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  - [캐릭터리스틱] {char.uuid}")
                print(f"      속성: {props}")
                print(f"      핸들: {char.handle}")


if __name__ == "__main__":
    asyncio.run(main())
