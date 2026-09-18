# Raspbot_pinmap

| 분류         | 기능           | Pi 표기   | BOARD 핀 | BCM | 비고                     |
| ---------- | ------------ | ------- | ------- | --- | ---------------------- |
| 트래킹 모듈     | Left 1       | GPIO.2  | 13      | 27  |                        |
|            | Left 2       | GPIO.3  | 15      | 22  |                        |
|            | Right 1      | GPIO.0  | 11      | 17  |                        |
|            | Right 2      | GPIO.7  | 7       | 4   |                        |
| 적외선 장애물 회피 | Left         | MISO    | 21      | 9   |                        |
|            | Right        | MOSI    | 19      | 10  |                        |
| 적외선 회피 스위치 | 회피 기능 On/Off | GPIO.6  | 22      | 25  | 장시간 켜두면 발열 → 스위치로 관리   |
| 초음파 모듈     | Echo         | GPIO.5  | 18      | 24  |                        |
|            | Trig         | GPIO.4  | 16      | 23  |                        |
| 부저         | Buzzer       | GPIO.26 | 32      | 12  | 패시브 부저 (PWM 필요)        |
| 적외선 수신 센서  | IR Receiver  | GPIO.27 | 36      | 16  | 리모컨 신호 수신              |
| LED1 (적색)  | red light    | GPIO.29 | 40      | 21  |                        |
| LED2 (청색)  | blue light   | GPIO.28 | 38      | 20  |                        |
| MCU 코프로세서  | SCL          | SCL.1   | 5       | 3   | I2C로 모터·서보 구동          |
|            | SDA          | SDA.1   | 3       | 2   |                        |
| 모터/서보 포트   | S1~S4        | —       | —       | —   | 하위 MCU가 직접 구동 (Pi 비직결) |
# microbit_v2_pin

## 큰 링 핀 (악어클립/바나나 커넥터 연결 가능)

| 핀 번호 | 이름 | 용도 |
|---|---|---|
| 0 | P0 | 범용 GPIO, 아날로그 입력, 터치 센서 |
| 1 | P1 | 범용 GPIO, 아날로그 입력, 터치 센서 |
| 2 | P2 | 범용 GPIO, 아날로그 입력, 터치 센서 |
| 3V | 3V | 3.3V 출력 (전원) |
| GND | GND | 그라운드 |

## 작은 핀 (에지 커넥터 전용, 나머지 핀)

| 핀 번호 | GPIO | 기본 용도 |
|---|---|---|
| P3 | GPIO1 | 아날로그 입력, LED 디스플레이 col1 |
| P4 | GPIO2 | 아날로그 입력, LED 디스플레이 col2 |
| P5 | GPIO17 | 버튼 A (공유) |
| P6 | GPIO12 | LED 디스플레이 col9 |
| P7 | GPIO11 | LED 디스플레이 col8 |
| P8 | GPIO18 | 범용 GPIO |
| P9 | GPIO10 | LED 디스플레이 col7 |
| P10 | GPIO3 | 아날로그 입력, LED 디스플레이 col3 |
| P11 | GPIO23 | 버튼 B (공유) |
| P12 | GPIO12 | 범용 GPIO |
| P13 | GPIO17 | SPI - MOSI |
| P14 | GPIO1 | SPI - MISO |
| P15 | GPIO13 | SPI - SCK |
| P16 | GPIO14 | 범용 GPIO |
| P19 | GPIO26 | I2C - SCL |
| P20 | GPIO27 | I2C - SDA |

## 기타 내부/전용 핀

| 핀 번호 | 용도 |
|---|---|
| P17, P18 | 3V (전원) |
| P21, P22 | GND |
| P23 | 사용 안 함 (내부용, +3V 스위치 관련) |
| P24 | 내부 용도 (LED 디스플레이 row 관련) |
| P25 | 내부 용도 |