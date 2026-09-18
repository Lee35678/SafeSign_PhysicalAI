---
aliases:
tags:
  - 임시
  - 초안
작성일: "2026-09-16"
---

# 라즈베리파이 5 4g [raspberry pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/)

### 프로세서 및 메모리
- **CPU:** Broadcom BCM2712 2.4GHz 쿼드코어 64비트 Arm Cortex-A76 (암호화 확장 기능, 코어당 512KB L2 캐시 및 2MB 공유 L3 캐시 포함)
- **GPU:** VideoCore VII GPU (OpenGL ES 3.1, Vulkan 1.3 지원)
- **RAM:** LPDDR4X-4267 SDRAM - 4GB
### 디스플레이 및 미디어
- **디스플레이 출력:** HDR을 지원하는 듀얼 4Kp60 HDMI® 출력
- **비디오 디코더:** 4Kp60 HEVC 디코더
- **카메라/디스플레이 인터페이스:** 2 × 4레인 MIPI 카메라/디스플레이 트랜시버
### 무선 및 네트워크
- **Wi-Fi:** 듀얼 밴드 802.11ac Wi-Fi®
- **블루투스:** Bluetooth 5.0 / Bluetooth Low Energy (BLE)
- **유선 네트워크:** 기가비트 이더넷 (PoE+ 지원, 별도 PoE+ HAT 필요)
### 입출력 및 확장성
- **USB 포트:** 
    - 2 × USB 3.0 포트 (동시 5Gbps 동작 지원)
    - 2 × USB 2.0 포트
- **PCIe:** 고속 주변기기용 PCIe 2.0 x1 인터페이스 (별도 M.2 HAT 또는 어댑터 필요)
- **GPIO:** 라즈베리 파이 표준 40핀 헤더
- **스토리지:** microSD 카드 슬롯 (고속 SDR104 모드 지원)
### 전원 및 기타 기능
- **전원 입력:** USB-C를 통한 5V/5A DC 전원 공급 (Power Delivery 지원)
- **RTC:** 실시간 시계 (RTC, 외부 배터리로 작동)
- **전원 버튼:** 온보드 전원 버튼 탑재

# 라즈베리 파이 4 (Raspberry Pi 4) 상세 사양

| 항목              | 상세 내용                                                           |
| :-------------- | :-------------------------------------------------------------- |
| **SoC / 프로세서**  | Broadcom BCM2711, 쿼드코어 Cortex-A72 (ARM v8) 64비트 SoC @ 1.8GHz    |
| **메모리 (RAM)**   | 1GB, 2GB, 3GB, 4GB 또는 8GB LPDDR4-3200 SDRAM *(모델별 상이)*          |
| **무선 네트워크**     | 2.4GHz / 5.0GHz IEEE 802.11ac, Bluetooth 5.0, BLE               |
| **유선 네트워크**     | 기가비트 이더넷 (Gigabit Ethernet)                                     |
| **USB 포트**      | USB 3.0 포트 2개, USB 2.0 포트 2개                                    |
| **GPIO**        | 표준 40핀 GPIO 헤더 *(이전 버전 보드와 완전 하위 호환)*                           |
| **디스플레이 출력**    | micro-HDMI® 포트 2개 *(최대 4K@60fps 지원)*                            |
| **카메라 / 디스플레이** | 2-lane MIPI DSI 디스플레이 포트, 2-lane MIPI CSI 카메라 포트                |
| **오디오 / 비디오**   | 4극 스테레오 오디오 및 컴포지트 비디오 포트                                       |
| **코덱 (비디오)**    | H.265 (4K@60fps 디코드), H.264 (1080p@60fps 디코드 / 1080p@30fps 인코드) |
| **그래픽 API**     | OpenGL ES 3.1, Vulkan 1.0                                       |
| **저장 장치**       | OS 로드 및 데이터 저장용 Micro-SD 카드 슬롯                                  |
| **전원 입력**       | • USB-C 커넥터 (5V DC, 최소 3A\*)<br>• GPIO 헤더 (5V DC, 최소 3A\*)      |
| **기타 전원**       | PoE (Power over Ethernet) 지원 *(별도 PoE HAT 필요)*                  |
| **작동 온도**       | 주위 온도 0°C ~ 50°C                                                |
# aiHand
|                      |                                                                  |
| -------------------- | ---------------------------------------------------------------- |
| Product size         | 177x105x295mm                                                    |
| Product weight       | about 0.73kg (main body + micro:bit + micro:bit expansion board) |
| Body material        | acrylic, duralumin alloy                                         |
| PTZ angle            | 180°                                                             |
| Power supply         | 7.5V 3A adapter (DC3.5*1.35)                                     |
| Main control system  | micro:bit + micro:bit expansion board                            |
| Software             | iOS/Android mobile APP                                           |
| Communication method | Bluetooth, USB                                                   |
| Servo model          | LD-1501MG servo *1; LFD-01 servo *5                              |
| Control method       | App Control (WonderCom)                                          |
| Shipping size        | 29*22*15(cm)                                                     |
| Overall weight       | about 1kg                                                        |
## 제어부
### microbit v2 [microbit v2 hardware](https://tech.microbit.org/hardware/)
![[microbit-overview-2-2.png]]
#### 주요 하드웨어 명세 (Hardware Specifications)

| 구분            | 주요 사양                 | 상세 내용                                                |
| :------------ | :-------------------- | :--------------------------------------------------- |
| **메인 프로세서**   | Nordic nRF52833       | Arm Cortex-M4 32-bit (64 MHz, FPU 포함)                |
| **메모리**       | Flash / RAM           | 512KB Flash, 128KB RAM                               |
| **무선 통신**     | Bluetooth 5.1 & Radio | Bluetooth Low Energy (BLE) 및 2.4GHz micro:bit 전용 라디오 |
| **디스플레이**     | 5x5 LED Matrix        | 25개 Red LED (디스플레이 및 주변 광량 측정 겸용)                    |
| **입력 장치**     | 버튼 및 터치               | 프로그래밍 버튼 2개(A, B), 정전식 터치 센서(Logo), 리셋 버튼            |
| **오디오**       | 스피커 및 마이크             | 내장 자성 스피커, MEMS 마이크로폰 (LED 동작 표시등 포함)                |
| **센서**        | 모션 및 온도               | 3축 가속도계, 3축 지자기 센서 (컴퍼스), 코어 내장 온도 센서                |
| **전원 supply** | USB / Battery         | USB 5V 지원, JST 커넥터 (3V 배터리 전원)                       |

#### 입출력 인터페이스 (Edge Connector)
micro:bit 하단부의 **엣지 커넥터(Edge Connector)**를 통해 외부 부품 및 확장 보드와 연결합니다.
```
+-------------------------------------------------------------+
|  [P0]  [P1]  [P2]         [3V]  [GND]   (바나나 잭 / 집게용)  |
|  | | | | | | | | | | | | | | | | | | |   (총 19개 GPIO)       |
+-------------------------------------------------------------+
```

#### 주요 핀 구성 및 기능
![[v2-2-block.svg|527]]
- * **Large Rings (P0, P1, P2, 3V, GND):** 바나나 플러그나 악어 집게(Alligator clips)를 연결하기 쉬운 대형 링.
* **GPIO (General Purpose Input/Output):** 총 19개의 할당 가능한 디지털/아날로그 핀 제공.
* **주요 인터페이스 지원:**
  * PWM (Pulse Width Modulation)
  * I2C 및 SPI 버스 통신
  * Analog In (아날로그 입력)
  * Touch Sensing (정전식 터치)
#### 전원 시스템 및 동작 사양

* **입력 전원:**
  * Micro-USB 포트: **5V DC**
  * JST 배터리 커넥터: **3V DC** (AAA 배터리 2개 사용)
* **전력 공급 능력:**
  * 최대 보드 공급 전류: 약 **300mA**
  * 외부 핀(3V ring)을 통해 사용 가능한 최대 전류: 약 **190mA**
* **전원 관리 기능:**
  * 후면 Reset/Power 버튼을 길게 누르면 저전력 대기 모드(Sleep Mode)로 전환 가능.
### 확장 보드
![[마이크로비트 확장보드 포트셋.jpg|568]]

## 구동부

### 서보모터
#### LD-1501MG(손목) [LD-1501MG_datasheet](https://servodatabase.com/servo/power-hd/hd-1501mg)
- **구동 및 제어 방식:**
    - 아날로그 모듈레이션 (Analog Modulation)
    - PWM 신호 제어 (Pulse Width: 500 ~ 2100 µs / 주기: 20 ms / 리프레시율: 50 Hz)
    - 데드 밴드 (Dead Band): 2 µs
        
- **모터 및 기어 구조:**
    - 표준 DC 모터 (Cored DC Motor)
    - 메탈 기어 (Metal Gear)
    - 듀얼 베어링 지원 (Dual Bearings) 및 25T 스플라인 (Spline)
- **작동 전압 (Operating Voltage):** DC 4.8V ~ 6.0V (공식 권장 전압)
- **출력 토크 (Stall Torque):**
    - **4.8V:** 15.50 kg·cm (215.3 oz-in)
    - **6.0V:** 17.00 kg·cm (236.1 oz-in)
    - _(7.2V 인가 시 추정치: 약 20.45 kg·cm)_
- **작동 속도 (Operating Speed):**
    - **4.8V:** 0.16 sec / 60°
    - **6.0V:** 0.14 sec / 60°
- **소비 전류 (Current Consumption):**
    - 대기 전류 (Idle Current): 5 mA
    - 구동/구속 전류 (Stall Current): 2.3A ~ 2.5A (2300 ~ 2500 mA)
- **작동 범위:**
    - 기본 제어 범위: 90°
    - 기계적 제한 범위 (Mechanical Limit): 180°
- **외형 및 물리 스펙:**
    - 크기: 41.9 × 20.6 × 39.6 mm (Standard 사이즈)
    - 무게: 60.0g
    - 커넥터 및 배선: JR Universal 타입 / 케이블 길이 300 mm
- **작동 온도:** -10°C ~ 60°C
#### LFD-01(손가락)[LFD-01 구매처](https://www.hiwonder.com/products/lfd-01?srsltid=AU7gw4WKG4A461YFXduO6JZ-yW2ctmfBx_RwIaNkvXLuC7GvmFkbt1vn)
- **구동 및 제어 방식:** PWM 펄스 폭 제어 (500 ~ 2500 µs, 0° ~ 180° 대응)
- **기어/소재 사양:** 플라스틱 기어 (Plastic Teeth)
- **작동 전압:** DC 4.8V ~ 6.0V
- **최대 토크:** ≥ 1.4 kg·cm (6.0V 기준)
- **작동 속도:** ≤ 0.11 sec / 60° (6.0V 기준)
- **소비 전류:** 무부하 전류 ≤ 60mA / 구속(Stall) 전류 700mA (6.0V 기준)
- **제어 각도:** 0° ~ 180°
- **크기 및 무게:** 22.3 × 12.0 × 23.2 mm / 약 10g
- **주요 특징:**
    - 내장형 안티 블로킹(Anti-blocking) 알고리즘 탑재 (부하 구속 시 소자 파손 및 과열 방지)
    - 케이블 길이 약 245mm
    - Arduino, STM32, C51 소스 코드 및 예제 라이브러리 제공
## 할일
- [ ] aihand의 각 손가락의 최대 와 최소 확인하기
- [ ] PWM 분해능 확인하기

## csi 카메라

### Raspberry Pi Camera Module 3 [판매처](https://www.devicemart.co.kr/goods/view?no=14917048&srsltid=AU7gw4WzZn40bqSY_13q7Qbe4LkVyOLig4mQo5Q84dM8l8PvDJFPKSga)

### 스펙

| 항목        | 사양                                             |
| --------- | ---------------------------------------------- |
| 이미지 센서    | Sony IMX708                                    |
| 해상도       | 12MP (4608 x 2592)                             |
| 센서 크기     | 1/2.43인치                                       |
| 초점 방식     | 오토포커스 (PDAF, Phase Detection Autofocus)        |
| 조리개(F값)   | F1.79                                          |
| 시야각(FOV)  | 표준 75°, Wide 버전 102°                           |
| 화각(초점 범위) | 표준: 5cm ~ 무한대 / Wide: 3cm ~ 무한대                |
| HDR       | 지원 (센서 자체 HDR)                                 |
| 인터페이스     | CSI-2 (15pin 표준 케이블, Pi 5는 22pin 어댑터 필요할 수 있음) |
| IR 필터     | 일반 버전은 IR 컷 필터 있음, NoIR 버전은 없음 (야간/IR 촬영용)     |

### 지원 해상도 / 프레임레이트 (모드별)

|모드|해상도|프레임레이트|
|---|---|---|
|Full|4608 x 2592|~14fps|
|2x2 binned|2304 x 1296|~56fps|
|1080p|1920 x 1080|~50fps|
|720p|1280 x 720|~100fps (크롭 모드)|


