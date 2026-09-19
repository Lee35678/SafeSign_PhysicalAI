# actuation — AI Hand + micro:bit (담당: 송승호)

RACI: 하드웨어·로봇동작 **R**, 파이프라인·판정로직 **A**

> **이 서비스는 Raspberry Pi 5(카메라·AI Hand·micro:bit 고정 스테이션)에서 실행됩니다.**
> picar는 더 이상 이 서비스가 담당하지 않습니다 — 별도 서비스 [`services/picar`](../picar/README.md)가
> **Raspberry Pi 4B 8GB**에서 담당합니다 (2026-09-18, picar가 카메라와 함께 움직이는 문제 해결).

`document/02_설계문서_v2.md` §1-1·§3, `document/03_인터페이스계약서_v2.md` §5-1·§5-3 기준 담당 범위:

- **AI Hand**: 손가락 서보 5개 + 손목 서보 1개 제어 (`shared/schemas/aihand_command.schema.json`)
- **micro:bitv2**: USB 시리얼(115200 baud)로 LED 매트릭스(O/X, 진행 표시) 송신, 버튼 입력 수신
  (`shared/schemas/microbit_protocol.md`)

## 디렉터리

- `src/aihand/` — 서보 제어. `controller.py`에 7종 서보 각도 초기값(펴짐 170°/굽힘 10°/손목중립 90°) 포함
- `src/microbit/` — pyserial 기반 시리얼 브릿지 (HELLO/READY 핸드셰이크, RESULT/PROGRESS 송신, BTN 수신)
- `src/app.py` — FastAPI 진입점 (`/health`, `/command`, `/result`, `/progress`)

## MOCK_HARDWARE 모드

로컬 PC(Windows)에는 서보/micro:bit가 물리적으로 연결되어 있지 않으므로, 기본값
`MOCK_HARDWARE=true`일 때는 실제 GPIO/시리얼 호출 대신 로그만 남기고 성공 응답을 반환합니다.
하드웨어 도착 후 `MOCK_HARDWARE=false` + `devices:` 매핑(docker-compose.yml 주석 참고)으로 전환하세요.

## picar와의 관계

이전에는 이 서비스가 picar도 함께 제어했지만(RPi5 GPIO 직결 가정), picar가 실제로 주행하면 카메라도
함께 이동해버리는 문제가 있어 **picar 제어를 별도 보드(RPi4B 8GB)·별도 서비스(`services/picar`)로
분리**했습니다. `services/web`의 상태머신이 AI Hand/micro:bit는 이 서비스(`ACTUATION_URL`)로,
picar는 `services/picar`(`PICAR_URL`, Wi-Fi)로 각각 따로 호출합니다.

## 아직 확정 안 된 것 (실물 테스트 필요)

- [ ] AI Hand GPIO 핀 배정 및 연결 방식
- [ ] 서보 각도 초기값(170/10/90)의 실물 캘리브레이션
- [ ] micro:bit 실제 시리얼 코드로 프로토콜 동작 검증 -> bluetooth 방식으로 변경

# MicroPython 말고 STS를 선택한 이유
1. 실행 속도
STS는 브라우저에서 네이티브 머신코드로 컴파일되어 CODAL C++ 런타임과 직접 링크됨. 반면 MicroPython은 VM(인터프리터) 방식으로 한 줄씩 해석하며 실행.
→ micro:bit 기준 순수 C++ 대비 STS는 2.1배 느림, MicroPython은 101배 느림 (약 48배 차이)

2. 메모리 효율
VM 방식은 인터프리터 자체와 바이트코드를 위한 추가 메모리가 필요함. STS는 컴파일된 결과물이 그대로 실행되어 오버헤드가 적음.
→ RAM 사용량: MakeCode+CODAL 전체 1.8KB대 vs MicroPython 9.5KB (CircuitPython은 12.8KB)

3. 자원 제약 환경에서의 실질적 차이
micro:bit는 블루투스 스택 구동에 8KB RAM이 필요한데, MicroPython은 RAM을 이미 많이 써서 블루투스 기능 자체가 동작 불가. MakeCode/STS는 이 문제 없음.

4. 타입 안정성
STS는 정적 타입 시스템(Static TypeScript)을 써서 컴파일 시점에 오류를 잡아내고, 효율적인 코드 생성이 가능. Python은 동적 타입이라 이런 최적화가 어려움.

5. 초보자 접근성 유지하면서 성능 확보
블록 프로그래밍 ↔ STS 텍스트 코딩을 자유롭게 전환 가능하면서도, 두 방식 모두 동일한 컴파일 파이프라인을 거쳐 최종적으로 같은 성능을 냄 — "쉬운데 느린" 것이 아니라 "쉬우면서도 빠름"을 목표로 설계됨.

참고 문헌 : Devine, J., Finney, J., de Halleux, P., Moskal, M., Ball, T., & Hodges, S. (2019). MakeCode and CODAL: Intuitive and efficient embedded systems programming for education. Journal of Systems Architecture, 98, 468–483. https://doi.org/10.1016/j.sysarc.2019.05.005

# AiHand + micro:bit + BLE 연동 작업 정리

> 목표: AI비전으로 8가지 수신호를 인식 → 라즈베리파이 → micro:bit(BLE) → AiHand 서보모터로 손동작 재현

---

## 세션 1. USB 시리얼과 AiHand 서보 제어 충돌

**문제**
micro:bit로 AiHand 서보를 제어하면서 동시에 USB로 PC와 시리얼 통신을 하려 했으나, 둘 중 하나만 작동함.

**원인**
micro:bit(nRF52832)는 하드웨어 UART가 1개뿐이며, `StartbitV2.startbit_Init()` 호출 시 `serial.redirect(P12, P8, 115200)`가 실행되어 UART 전체가 P12/P8(AiHand 서보 컨트롤러 채널)로 이동함. 이 순간 USB 시리얼 채널은 완전히 죽음.

**결과**
테스트 코드로 실측 검증: 초기화 전엔 USB 시리얼 정상 → 초기화 후 USB로 재전송 시도 시 PC에 아무것도 안 찍힘 → 가설 확정.

**해결**
USB 시리얼 대신 **BLE(무선)**로 라즈베리파이와 통신하기로 결정. BLE는 UART와 별개 하드웨어라 서보 제어 채널과 충돌하지 않음.

---

## 세션 2. 라즈베리파이 연동 방식 검토

**문제**
라즈베리파이와 어떤 방식으로 통신할지 결정 필요 (I2C / 여유 GPIO 시리얼 / USB / 블루투스).

**원인**
- I2C: micro:bit가 슬레이브 모드를 지원하지 않아 구현 난이도 높음
- 여유 GPIO 소프트웨어 시리얼: 응답속도 요구사항이 낮아 굳이 배선할 필요 없음, 양방향 구현도 번거로움
- USB: 세션 1과 동일한 UART 충돌 문제 재발

**결과**
요구사항 확인 결과 응답속도는 "초 단위 여유 있음", 방향은 "양방향 필요"로 확인됨.

**해결**
**BLE(UART 서비스)**로 최종 결정. 배선 불필요, 서보 채널과 무관, 양방향 지원.

---

## 세션 3. PC ↔ micro:bit 순수 시리얼 테스트 (초기 디버깅)

**문제**
A버튼(초기화 전 USB 시리얼 테스트)을 눌러도 PuTTY에 아무것도 안 찍힘. B버튼(서보 제어)도 서보가 안 움직임.

**원인 (복합)**
1. **서보 미동작**: `setBusServo()`(버스 서보용 명령, cmd 0x35)를 사용했는데, 실제 AiHand는 **PWM 서보 인터페이스**에 연결되어 있어 `setPwmServo()`(cmd 0x03)를 써야 했음 — API 선택 오류
2. **시리얼 미출력**: PuTTY 설정 문제 (COM 포트 오선택 및/또는 Flow control 기본값 문제)

**결과**
- 함수를 `setPwmServo()`로 교체 → 서보 정상 동작 확인
- PuTTY를 Serial/115200/8N1/**Flow control: None**으로 재설정, 정확한 COM 포트 확인 → 시리얼 정상 수신 확인

**해결**
두 원인 모두 해결하여 A/B버튼 테스트, A+B(초기화 후 USB 재전송 실패) 테스트까지 전부 예상대로 재현 및 검증 완료.

---

## 세션 4. BLE 통신 연결 및 UUID 문제

**문제**
`bleak`로 연결은 성공했으나 `start_notify()` 호출 시 `characteristic does not support notifications or indications` 에러 발생.

**원인**
표준 Nordic UART Service의 RX/TX UUID(`6e400002`=RX, `6e400003`=TX)를 그대로 사용했으나, **이 micro:bit(MakeCode Bluetooth 확장)는 두 UUID의 속성이 반대로 배정**되어 있었음:
- `6e400003` → `write, write-without-response` (실제 RX)
- `6e400002` → `indicate` (실제 TX, notify 아닌 indicate)

**결과**
서비스/캐릭터리스틱 전체 목록을 출력하는 디버그 스크립트로 실제 속성 확인.

**해결**
UUID를 스왑하여 코드 수정 (`bleak`의 `start_notify()`는 notify/indicate 모두 자동 처리). 이후 양방향 통신(A버튼 → PC 수신, PC → micro:bit 자동 전송) 정상 확인.

---

## 세션 5. AiHand 5손가락 제어 및 방향/범위 캘리브레이션

**문제 1: 손가락 매핑 확인 필요**
서보 인덱스와 실제 손가락의 대응 관계를 몰라 5개를 한번에 제어할 수 없음.

**해결**: `IDX:인덱스,각도` 명령으로 하나씩 테스트 → `1=엄지, 2=검지, 3=중지, 4=약지, 5=소지` 확정.

---

**문제 2: 엄지만 방향이 반대**
`hand 0,0,0,0,0` 실행 시 엄지만 다른 손가락과 반대로 움직임.

**원인**: 엄지 서보만 물리적으로 반대 방향 장착.

**해결**: 초기엔 `moveThumb()`로 엄지에만 반전(`180-각도`) 적용 → 이후 사용자 확인 결과 **엄지는 정상, 검지/중지/약지/소지가 반대**였음이 재확인되어 반전 대상을 엄지에서 나머지 4개로 수정 (`moveInverted()`).

---

**문제 3: 서보 스톨(과부하)로 자체 정지**
`hand 90,90,90,90,90` → `hand 10,10,10,10,10` 이동 시 서보가 기계적 한계에 부딪혀 멈춤.

**원인**: 손가락마다 실제 안전 가동범위가 다른데 전체에 동일한 범위(0~180, 이후 10~170)를 적용함.

**해결**: raw 각도 직접 테스트(`IDX` 명령)로 손가락별 실제 min/max 실측:

| 손가락 | min | max |
|---|---|---|
| 엄지 | 60 | 170 |
| 검지 | 20 | 135 |
| 중지 | 25 | 135 |
| 약지 | 25 | 125 |
| 소지 | 30 | 120 |

코드에 `fingerMinAngle[]`, `fingerMaxAngle[]` 배열로 반영, `moveServo()` 내부에서 자동 clamp 처리.

---

## 세션 6. BLE 연결 끊김 (Unreachable 에러)

**문제**
`hand 170,170,170,170,170`(5개 손가락 동시 극단 이동) 실행 시 `BleakError: ... Unreachable`, micro:bit LED에 연결 끊김(X) 표시.

**원인**
5개 서보를 동시에(또는 짧은 텀으로 겹치게) 극단 각도로 구동 시 **순간 전류가 급증 → 전압 강하 → BLE 연결 불안정**. 개별 손가락은 문제없었으나 동시 구동 시 누적 부하로 간헐적 발생.

**결과**
손가락 사이 텀을 550ms(완전 순차) → 150ms(2개씩 묶음) → 100ms(완전 개별 순차)로 단계적으로 조정하며 안정성 테스트. `g 1`/`g 2` 반복 실행은 안정적으로 확인됨 (일부는 우연히 성공했을 가능성도 있어 반복 검증 지속).

**해결**
현재 **손가락 하나씩 순차 이동 + 100ms 텀**으로 설정한 상태. 완전한 해결은 세션 7과 연결됨 (근본 원인이 다른 데 있었음).

---

## 세션 7. 패닉 코드 070 (SD_ASSERT) — BLE와 사운드 충돌

**문제**
반복 테스트 중 micro:bit LED에 ☹(슬픈 얼굴) + **070** 패닉 코드 표시.

**원인 규명 과정**
1. 처음엔 "서보 각도 문제를 라이브러리가 감지해서 멈추는 기능"으로 의심 → 라이브러리 소스 확인 결과 그런 기능 자체가 없음(관련 코드는 전부 미완성 주석 처리 상태)
2. 070이 micro:bit 런타임(CODAL)의 **패닉 코드**임을 확인
3. 사용자가 공식 정보 제공: **070 = `MICROBIT_PANIC_SD_ASSERT`**, 즉 **BLE SoftDevice와의 상호작용 문제**
4. 라이브러리 내부 코드 재검토 → `startbit_Init()`의 `basic.forever()` 루프 안에 배터리 전압이 6.8V 미만일 때 `music.playTone()`을 호출하는 저전압 경고음 코드 발견
5. **`music.playTone()`은 micro:bit v2에서 BLE SoftDevice와 동일한 하드웨어 타이머 자원을 사용** → 배터리 소모로 전압이 낮아지며 이 경고음이 반복 실행되고, BLE 활성 상태와 충돌하여 SD_ASSERT(070) 발생

**결과**
장시간 반복 구동(`loop` 테스트)으로 배터리 소모 → 저전압 임계값 도달 → 경고음 반복 → 패닉, 이라는 인과관계가 지금까지의 증상(반복 테스트 중 간헐적 발생)과 일치함을 확인.

**해결**
`StartbitV2` 라이브러리를 GitHub 확장이 아닌 **프로젝트 내 직접 파일로 복사**하여 `music.playTone()` 호출부를 **LED 아이콘 표시로 대체**한 패치본(`StartbitV2_patched.ts`) 제작 완료. (내일 적용 및 재검증 예정)

---

## 세션 8. 코드 최적화 — 메모리/통신 경량화

**문제**
BLE + 서보 제어 반복 사용 시 안정성 우려, 명령 파싱 방식이 무거움.

**원인**
`HAND:170,170,170,170,170` 같은 명령은 `substr()` + `split(",")` + `parseInt()` 5회 호출로 힙 메모리 할당이 잦음. micro:bit는 RAM이 작아 누적되면 불안정 요소가 될 수 있음.

**해결**
- 캘리브레이션용 코드(`IDX`, `HAND` 명령)와 운영용 코드를 분리
- 운영용 최종 코드(`aihand_production.ts`)는 **`G1`~`G7` 형식만 지원**, `charCodeAt()`으로 직접 문자 비교하여 `substr`/`split`/`parseInt` 호출 자체를 제거 → 힙 할당 최소화


## 로컬 실행

```bash
docker compose up --build actuation
curl http://localhost:8002/health



```


