### AI Hand 검증 — 2026-09-23 16:07

- 실행 환경: **Rpi5 네이티브**
- micro:bit 재부팅 후 첫 회차: y
- `/health` 전: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': {'_value': True}}`
- `/health` 후: `{'status': 'ok', 'service': 'actuation', 'mock_hardware': False, 'microbit_connected': {'_value': True}}`

| 시각 | 회차 | 명령 | HTTP(ms) | status | 회신 | **완료(s)** | 판정 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16:05:01 | 1 | G1 정지 | 1050 | ok | `OK1` | 1.96 | 정상 |  |
| 16:05:08 | 1 | G2 서행 | 1040 | ok | `OK2` | 1.83 | 정상 |  |
| 16:05:16 | 1 | G3 좌회전_유도 | 1046 | ok | `OK3` | 1.49 | 정상 |  |
| 16:05:22 | 1 | G4 우회전_유도 | 1042 | ok | `OK4` | 1.66 | 정상 |  |
| 16:05:38 | 1 | G5 확인_완료 | 1041 | ok | `OK5` | 1.76 | 정상 |  |
| 16:05:45 | 1 | G6 후진 | 1054 | ok | `OK6` | 1.85 | 정상 |  |
| 16:05:53 | 1 | G7 주의 | 1049 | ok | `OK7` | 1.84 | 정상 |  |
| 16:06:13 | 1 | result correct | 2042 | timeout | `-` | 3.52 | 정상 |  |
| 16:06:34 | 1 | result incorrect | 2037 | timeout | `-` | 0.62 | 정상 |  |
| 16:06:56 | 1 | progress 3/7 | 35 | ok | `OKP37` | 5.63 | 정상 |  |
| 16:07:10 | 1 | progress 1/7 | 33 | ok | `OKP17` | 2.50 | 정상 |  |

- **펌웨어 보고 완료**(G1~G7 HTTP): 중앙 1046ms · 최대 1054ms  (7건) — 회신이 손 동작 **이후**라 동작 시간 포함
- **완료**(육안): 중앙 1.84s · 최대 5.63s  (11건)
  > KPI 2.0초를 **어느 쪽으로 재느냐**가 팀 결정이다 (`proposals/picar_주행시간_스키마_변경안.md` 결정 2).
