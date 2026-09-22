# micro:bit BLE 프로토콜 (2026-09-21 갱신 — 시리얼에서 BLE로 전환)

원본: `document/03_인터페이스계약서_v2.md` §5-3. 문서가 원본(source of truth)이며, 이 파일은 코드 작성 시
빠르게 참조하기 위한 요약입니다.

> 이 문서가 2026-09-18에 확정했던 방식은 USB 시리얼이었으나, micro:bit v2가 하드웨어 UART를 1개만
> 가져서 AI Hand 서보 초기화(`StartbitV2.startbit_Init()`)가 그 UART를 서보 채널로 가져가 버리는
> 제약이 구현 착수 후 실측으로 드러나 **BLE로 전환**했다. 전환 경위는 03_인터페이스계약서_v2.md §5-3
> 참고.

## 물리 계층

- **BLE**, Nordic UART Service(NUS) 프로파일
- 이 micro:bit 펌웨어는 표준 NUS와 RX/TX UUID가 **반대로 배정**되어 있음 — 표준 코드 그대로 쓰면 안 됨
  - `6e400003-b5a3-f393-e0a9-e50e24dcca9e` : **쓰기용** (RPi/PC -> micro:bit)
  - `6e400002-b5a3-f393-e0a9-e50e24dcca9e` : **알림용** (micro:bit -> RPi/PC)
- 텍스트, `\n`(LF)로 종료. 콜론 구분자 없음(운영 펌웨어는 힙 할당을 줄이기 위해 최소 글자 수만 사용)

## RPi -> micro:bit

```
G1\n ~ G7\n          예) G3\n        (수신호 7종에 대응하는 제스처 실행)
correct\n            판정 결과 LED에 O 표시(2초) 후 소등 (부저 없음)
incorrect\n          판정 결과 LED에 X 표시(2초) 후 소등 (부저 없음)
P<current><total>\n  예) P37\n       (3/7번째. 둘 다 한 자리 숫자, LED 표시 없음 — 회신만)
```

- `G{n}`: `target_signal` <-> `G{n}` 매핑은 `services/actuation/src/aihand/controller.py`의
  `GESTURE_MAP` 참고
- `correct`/`incorrect`: match_score는 전달하지 않음(펌웨어가 쓰지 않음) — is_correct만 반영.
  🔴 **소리는 쓰지 않는다 — 하드웨어 제약(확정).** micro:bit v2에서 BLE SoftDevice와 `music`
  라이브러리는 **같은 타이머/PWM 자원을 공유**해 함께 쓸 수 없다. `music.*` 호출 시 소리가 나야 할
  시점에 패닉 070(SD_ASSERT)이 나고 BLE가 끊긴다. **우회 방법은 없으며**, 펌웨어에서 해당 호출을
  전부 제거했다. 판정 피드백은 **LED O/X만** 사용한다
- `P<current><total>`: 진행 표시는 LED로 하지 않음(2026-09-21 결정, web 화면 쪽 담당) — 수신
  확인만 목적

## micro:bit -> RPi

```
OK<n>\n              예) OK3\n          (G{n} 제스처 실행 완료)
OK:CORRECT\n / OK:INCORRECT\n         (correct/incorrect 처리 완료)
OKP<current><total>\n예) OKP37\n        (P<current><total> 처리 완료)
```

> ⚠️ **미구현**: `BTN:A|B|AB`(버튼 입력)는 BLE 전환 후 아직 펌웨어에 없음. 필요 시 구현하면 이
> 파일에 형식을 추가할 것.

## 손가락 서보 동시 구동 금지

7.5V 3A 어댑터 하나가 확장보드를 거쳐 micro:bit와 서보를 같은 레일에서 먹이는데, 손가락 서보
(LFD-01) 구속 전류가 개당 700mA라 5개 동시 기동 시 3.5A로 어댑터 용량을 넘긴다 (2026-09-21 정정:
이전의 "micro:bit 300mA" 근거는 틀렸다 — 서보는 micro:bit를 거치지 않는다) —
서보 1개만 구동해도 보드 공급 한계를 넘어서 2개 이상 동시 구동 시 전압 강하로 BLE 연결이 끊긴다.
모든 코드는 손가락 간 200ms 텀을 둔 완전 순차 이동만 사용한다 (`document/11_하드웨어설계서_v1.md` §4.4).

## 에러 처리 정책 (물리 피드백 지연 P95 ≤ 2.0초 고려)

- RPi는 `G{n}` 전송 후 `OK{n}` 응답을 최대 2초 대기하되, 왕복 재확인(ACK) 프로토콜을 반복하지 않음 —
  응답이 없으면 타임아웃 처리하고 다음 이벤트에서 다시 시도(self-healing).
- BLE 쓰기 실패(연결 끊김 등) 시 RPi가 재연결을 1회 시도 후 재전송(`services/actuation/src/microbit/ble_bridge.py`).
- 재시도 후에도 실패하면 에러 상태를 반환하고 다음 이벤트에서 자연 복구.

## 규칙

1. 필드명/포맷은 `document/03_인터페이스계약서_v2.md` §5-3과 100% 동일하게 유지.
2. 프로토콜을 바꾸면 이 파일과 03_인터페이스계약서_v2.md §5-3을 함께 갱신.
