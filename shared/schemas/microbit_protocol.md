# micro:bit 시리얼 프로토콜 (확정, 2026-09-18)

원본: `document/03_인터페이스계약서_v2.md` §5-3. 문서가 원본(source of truth)이며, 이 파일은 코드 작성 시
빠르게 참조하기 위한 요약입니다.

## 물리 계층

- USB 시리얼, **115200 baud, 8N1**
- 텍스트 라인 기반, 필드 구분자 `:`, 각 메시지는 `\n`(LF)로 종료 (CR 없음)
- ASCII 인코딩

## 핸드셰이크 (연결 확인)

```
RPi -> micro:bit : HELLO\n
micro:bit -> RPi : READY\n
```

RPi 프로세스 시작 시 1회 전송, READY 응답으로 연결을 확인한다.

## RPi -> micro:bit

```
RESULT:<OK|NG>:<match_score>\n     예) RESULT:OK:87\n
PROGRESS:<current>:<total>\n       예) PROGRESS:3:7\n
```

- `RESULT`: 정오답(`OK|NG`) + match_score(0~100 정수) — LED 매트릭스 O/X 표시
- `PROGRESS`: 현재 몇 번째 수신호 / 전체 7종 — 진행 표시 (02_설계문서_v2 §5)

## micro:bit -> RPi

```
BTN:A\n
BTN:B\n
BTN:AB\n
```

## 에러 처리 정책 (물리 피드백 지연 P95 ≤ 2.0초 고려)

- **ACK/재전송 없음.** RESULT/PROGRESS는 이벤트마다 다시 전송되므로 한 줄이 유실/손상돼도 다음 이벤트에서
  자연 복구(self-healing)된다. 왕복 확인을 넣으면 지연 KPI에 불리해 의도적으로 생략.
- micro:bit가 파싱 실패(알 수 없는 라인)한 줄은 **조용히 버리고 이전 표시 상태 유지**. 에러 응답 없음.
- 포트 연결이 끊기면 RPi가 1초 간격으로 재오픈 시도, 지속 실패 시 화면 폴백 UI로 전환 (§7).

## 규칙

1. 필드명/포맷은 `document/03_인터페이스계약서_v2.md` §5-3과 100% 동일하게 유지.
2. 프로토콜을 바꾸면 이 파일과 03_인터페이스계약서_v2.md §5-3을 함께 갱신.
