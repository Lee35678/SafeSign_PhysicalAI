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
  **부저는 사용하지 않음**(2026-09-21 실측 확정) — `music.playTone()`이 BLE SoftDevice와 충돌해
  패닉 070(SD_ASSERT)을 일으킨다. 펌웨어의 `BUZZER_ENABLED = false`로 비활성, LED O/X만 사용
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

micro:bit v2 보드 최대 공급 전류(~300mA) < 손가락 서보(LFD-01) 구속 전류(최대 700mA, 6V) —
서보 1개만 구동해도 보드 공급 한계를 넘어서 2개 이상 동시 구동 시 전압 강하로 BLE 연결이 끊긴다.
모든 코드는 손가락 간 200ms 텀을 둔 완전 순차 이동만 사용한다 (`services/actuation/doc/hardware_spec.md`).

## 에러 처리 정책 (물리 피드백 지연 P95 ≤ 2.0초 고려)

- RPi는 `G{n}` 전송 후 `OK{n}` 응답을 최대 2초 대기하되, 왕복 재확인(ACK) 프로토콜을 반복하지 않음 —
  응답이 없으면 타임아웃 처리하고 다음 이벤트에서 다시 시도(self-healing).
- BLE 쓰기 실패(연결 끊김 등) 시 RPi가 재연결을 1회 시도 후 재전송(`services/actuation/src/microbit/ble_bridge.py`).
- 재시도 후에도 실패하면 에러 상태를 반환하고 다음 이벤트에서 자연 복구.

## 규칙

1. 필드명/포맷은 `document/03_인터페이스계약서_v2.md` §5-3과 100% 동일하게 유지.
2. 프로토콜을 바꾸면 이 파일과 03_인터페이스계약서_v2.md §5-3을 함께 갱신.
